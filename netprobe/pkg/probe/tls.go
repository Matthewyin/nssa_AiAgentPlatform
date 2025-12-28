package probe

import (
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"strings"
	"time"
)

// TLSProbeUnified 执行 TLS 探测并返回统一结果结构
func TLSProbeUnified(opts TLSOptions) *UnifiedResult {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.tls"
	}
	if opts.TimeoutSec <= 0 {
		opts.TimeoutSec = 10
	}

	// 创建统一结果
	target := TargetInfo{
		Domain:   opts.Host,
		Port:     opts.Port,
		Protocol: "tls",
	}
	result := NewUnifiedResult(toolName, target)

	addr := fmt.Sprintf("%s:%d", opts.Host, opts.Port)

	// 配置 TLS
	tlsCfg := &tls.Config{
		InsecureSkipVerify: opts.Insecure,
	}
	if opts.ServerName != "" {
		tlsCfg.ServerName = opts.ServerName
	} else {
		tlsCfg.ServerName = opts.Host
	}

	// 加载 CA 证书
	if opts.CACert != "" {
		caBytes, err := os.ReadFile(opts.CACert)
		if err != nil {
			result.SetError(ErrTLSCertInvalid, fmt.Sprintf("read ca_cert failed: %v", err), nil)
			return result
		}
		pool := x509.NewCertPool()
		pool.AppendCertsFromPEM(caBytes)
		tlsCfg.RootCAs = pool
	}

	// 加载客户端证书 (mTLS)
	hasMTLSConfig := false
	if opts.ClientCert != "" && opts.ClientKey != "" {
		cert, err := tls.LoadX509KeyPair(opts.ClientCert, opts.ClientKey)
		if err != nil {
			result.SetError(ErrTLSCertInvalid, fmt.Sprintf("load client cert/key failed: %v", err), nil)
			return result
		}
		tlsCfg.Certificates = []tls.Certificate{cert}
		hasMTLSConfig = true
	}

	// 阶段1: TCP 连接
	tcpStart := time.Now()
	tcpConn, err := net.DialTimeout("tcp", addr, time.Duration(opts.TimeoutSec)*time.Second)
	tcpDuration := time.Since(tcpStart)

	if err != nil {
		errCode := classifyTCPError(err)
		result.SetError(errCode, fmt.Sprintf("tcp connect failed: %v", err), nil)
		result.DurationMs = float64(tcpDuration.Milliseconds())
		return result
	}
	defer tcpConn.Close()

	// 阶段2: TLS 握手
	tlsStart := time.Now()
	tlsConn := tls.Client(tcpConn, tlsCfg)
	err = tlsConn.SetDeadline(time.Now().Add(time.Duration(opts.TimeoutSec) * time.Second))
	if err != nil {
		result.SetError(ErrInternalError, fmt.Sprintf("set deadline failed: %v", err), nil)
		return result
	}

	err = tlsConn.Handshake()
	tlsDuration := time.Since(tlsStart)
	totalDuration := time.Since(tcpStart)

	if err != nil {
		errCode := classifyTLSError(err)
		result.SetError(errCode, fmt.Sprintf("tls handshake failed: %v", err), nil)
		result.DurationMs = float64(totalDuration.Milliseconds())
		return result
	}
	defer tlsConn.Close()

	// 获取连接状态
	state := tlsConn.ConnectionState()

	// 构建 TLS 结果
	tlsResult := buildTLSResult(state, tcpDuration, tlsDuration, totalDuration, hasMTLSConfig)

	result.SetSuccess(float64(totalDuration.Milliseconds()), tlsResult)
	return result
}

// buildTLSResult 构建 TLS 结果结构
func buildTLSResult(state tls.ConnectionState, tcpDuration, tlsDuration, totalDuration time.Duration, hasMTLSConfig bool) *TLSResult {
	tlsResult := &TLSResult{
		Connection: TLSConnection{
			Protocol:    tls.VersionName(state.Version),
			CipherSuite: tls.CipherSuiteName(state.CipherSuite),
			ALPN:        state.NegotiatedProtocol,
			ServerName:  state.ServerName,
			IsMutualTLS: hasMTLSConfig && state.HandshakeComplete,
		},
		Timing: TLSTiming{
			TCPConnectMs:   float64(tcpDuration.Microseconds()) / 1000.0,
			TLSHandshakeMs: float64(tlsDuration.Microseconds()) / 1000.0,
			TotalMs:        float64(totalDuration.Microseconds()) / 1000.0,
		},
		Security: TLSSecurity{
			Warnings: []string{},
		},
	}

	// 提取证书信息
	if len(state.PeerCertificates) > 0 {
		cert := state.PeerCertificates[0]
		tlsResult.Certificate = extractCertificateInfo(cert)

		// 检查证书过期警告
		if tlsResult.Certificate.IsExpiringSoon {
			tlsResult.Security.Warnings = append(tlsResult.Security.Warnings,
				fmt.Sprintf("Certificate expires in %d days", tlsResult.Certificate.DaysRemaining))
		}
		if tlsResult.Certificate.IsExpired {
			tlsResult.Security.Warnings = append(tlsResult.Security.Warnings, "Certificate has expired")
		}
	}

	// 检查 TLS 版本警告
	if state.Version < tls.VersionTLS12 {
		tlsResult.Security.Warnings = append(tlsResult.Security.Warnings,
			fmt.Sprintf("Weak TLS version: %s", tls.VersionName(state.Version)))
	}

	// 计算安全等级
	tlsResult.Security.Grade = calculateSecurityGrade(state, tlsResult.Certificate)

	return tlsResult
}

// extractCertificateInfo 提取证书详细信息
func extractCertificateInfo(cert *x509.Certificate) CertificateInfo {
	now := time.Now()
	daysRemaining := int(cert.NotAfter.Sub(now).Hours() / 24)
	isExpired := now.After(cert.NotAfter)
	isExpiringSoon := !isExpired && daysRemaining < 30

	// 计算 SHA256 指纹
	fingerprint := sha256.Sum256(cert.Raw)
	fingerprintHex := hex.EncodeToString(fingerprint[:])

	// 提取密钥算法和大小
	keyAlgorithm, keySize := extractKeyInfo(cert)

	return CertificateInfo{
		Subject:           extractSubject(cert.Subject),
		Issuer:            extractSubject(cert.Issuer),
		SerialNumber:      cert.SerialNumber.String(),
		NotBefore:         cert.NotBefore,
		NotAfter:          cert.NotAfter,
		DaysRemaining:     daysRemaining,
		IsExpired:         isExpired,
		IsExpiringSoon:    isExpiringSoon,
		FingerprintSHA256: fingerprintHex,
		DNSNames:          cert.DNSNames,
		KeyAlgorithm:      keyAlgorithm,
		KeySize:           keySize,
	}
}

// extractSubject 提取证书主题信息
func extractSubject(name pkix.Name) CertSubject {
	subject := CertSubject{
		CommonName: name.CommonName,
	}
	if len(name.Organization) > 0 {
		subject.Organization = name.Organization[0]
	}
	if len(name.OrganizationalUnit) > 0 {
		subject.OrganizationalUnit = name.OrganizationalUnit[0]
	}
	if len(name.Country) > 0 {
		subject.Country = name.Country[0]
	}
	if len(name.Province) > 0 {
		subject.State = name.Province[0]
	}
	if len(name.Locality) > 0 {
		subject.Locality = name.Locality[0]
	}
	return subject
}

// extractKeyInfo 提取密钥算法和大小
func extractKeyInfo(cert *x509.Certificate) (algorithm string, size int) {
	switch cert.PublicKeyAlgorithm {
	case x509.RSA:
		algorithm = "RSA"
		if rsaKey, ok := cert.PublicKey.(interface{ Size() int }); ok {
			size = rsaKey.Size() * 8
		}
	case x509.ECDSA:
		algorithm = "ECDSA"
		if ecKey, ok := cert.PublicKey.(interface{ Params() interface{ BitSize() int } }); ok {
			if params := ecKey.Params(); params != nil {
				size = params.BitSize()
			}
		}
	case x509.Ed25519:
		algorithm = "Ed25519"
		size = 256
	case x509.DSA:
		algorithm = "DSA"
	default:
		algorithm = "Unknown"
	}
	return
}

// calculateSecurityGrade 计算安全等级
func calculateSecurityGrade(state tls.ConnectionState, certInfo CertificateInfo) string {
	score := 100

	// TLS 版本评分
	switch state.Version {
	case tls.VersionTLS13:
		// 满分
	case tls.VersionTLS12:
		score -= 10
	case tls.VersionTLS11:
		score -= 30
	case tls.VersionTLS10:
		score -= 50
	default:
		score -= 70
	}

	// 证书状态评分
	if certInfo.IsExpired {
		score -= 50
	} else if certInfo.IsExpiringSoon {
		score -= 20
	}

	// 密钥强度评分
	if certInfo.KeyAlgorithm == "RSA" && certInfo.KeySize < 2048 {
		score -= 20
	}

	// 转换为等级
	switch {
	case score >= 90:
		return "A"
	case score >= 80:
		return "B"
	case score >= 60:
		return "C"
	default:
		return "F"
	}
}

// classifyTCPError 分类 TCP 错误
func classifyTCPError(err error) string {
	errStr := err.Error()
	switch {
	case strings.Contains(errStr, "timeout") || strings.Contains(errStr, "i/o timeout"):
		return ErrTCPTimeout
	case strings.Contains(errStr, "connection refused"):
		return ErrTCPRefused
	case strings.Contains(errStr, "no route to host") || strings.Contains(errStr, "network is unreachable"):
		return ErrTCPUnreachable
	case strings.Contains(errStr, "connection reset"):
		return ErrTCPReset
	default:
		return ErrTCPTimeout
	}
}

// classifyTLSError 分类 TLS 错误
func classifyTLSError(err error) string {
	errStr := err.Error()
	switch {
	case strings.Contains(errStr, "certificate has expired"):
		return ErrTLSCertExpired
	case strings.Contains(errStr, "certificate is not trusted") || strings.Contains(errStr, "unknown authority"):
		return ErrTLSCertNotTrusted
	case strings.Contains(errStr, "certificate") || strings.Contains(errStr, "x509"):
		return ErrTLSCertInvalid
	case strings.Contains(errStr, "protocol"):
		return ErrTLSProtocolError
	default:
		return ErrTLSHandshakeFailed
	}
}

// TLSProbe 执行 TLS 探测 (保留旧接口以保持兼容性)
// Deprecated: 请使用 TLSProbeUnified 替代
func TLSProbe(opts TLSOptions) Result {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.tls"
	}
	if opts.TimeoutSec <= 0 {
		opts.TimeoutSec = 10
	}

	addr := fmt.Sprintf("%s:%d", opts.Host, opts.Port)

	tlsCfg := &tls.Config{
		InsecureSkipVerify: opts.Insecure,
	}
	if opts.ServerName != "" {
		tlsCfg.ServerName = opts.ServerName
	} else {
		tlsCfg.ServerName = opts.Host
	}

	if opts.CACert != "" {
		caBytes, err := os.ReadFile(opts.CACert)
		if err != nil {
			return Result{
				Success: false,
				Tool:    toolName,
				Host:    opts.Host,
				Port:    opts.Port,
				Error:   fmt.Sprintf("read ca_cert failed: %v", err),
			}
		}
		pool := x509.NewCertPool()
		pool.AppendCertsFromPEM(caBytes)
		tlsCfg.RootCAs = pool
	}

	if opts.ClientCert != "" && opts.ClientKey != "" {
		cert, err := tls.LoadX509KeyPair(opts.ClientCert, opts.ClientKey)
		if err != nil {
			return Result{
				Success: false,
				Tool:    toolName,
				Host:    opts.Host,
				Port:    opts.Port,
				Error:   fmt.Sprintf("load client cert/key failed: %v", err),
			}
		}
		tlsCfg.Certificates = []tls.Certificate{cert}
	}

	dialer := &tls.Dialer{
		NetDialer: &net.Dialer{
			Timeout: time.Duration(opts.TimeoutSec) * time.Second,
		},
		Config: tlsCfg,
	}

	start := time.Now()
	conn, err := dialer.Dial("tcp", addr)
	latency := time.Since(start)

	if err != nil {
		return Result{
			Success: false,
			Tool:    toolName,
			Host:    opts.Host,
			Port:    opts.Port,
			Error:   fmt.Sprintf("tls dial failed: %v", err),
		}
	}
	defer conn.Close()

	tlsConn, ok := conn.(*tls.Conn)
	if !ok {
		return Result{
			Success: false,
			Tool:    toolName,
			Host:    opts.Host,
			Port:    opts.Port,
			Error:   "connection is not TLS",
		}
	}
	if err := tlsConn.Handshake(); err != nil {
		return Result{
			Success: false,
			Tool:    toolName,
			Host:    opts.Host,
			Port:    opts.Port,
			Error:   fmt.Sprintf("handshake failed: %v", err),
		}
	}

	state := tlsConn.ConnectionState()
	details := map[string]any{
		"mutual_auth":      state.HandshakeComplete && len(state.PeerCertificates) > 0 && len(state.VerifiedChains) > 0 && len(state.VerifiedChains[0]) > 0,
		"negotiated_proto": state.NegotiatedProtocol,
		"alpn_proto":       state.NegotiatedProtocol,
		"server_name":      state.ServerName,
	}
	if state.CipherSuite != 0 {
		details["cipher_suite"] = tls.CipherSuiteName(state.CipherSuite)
	}
	details["tls_version"] = tls.VersionName(state.Version)

	if len(state.PeerCertificates) > 0 {
		cert := state.PeerCertificates[0]
		details["cert_subject"] = cert.Subject.String()
		details["cert_issuer"] = cert.Issuer.String()
		details["cert_not_before"] = cert.NotBefore
		details["cert_not_after"] = cert.NotAfter
		details["cert_dns_names"] = cert.DNSNames
		details["cert_days_remaining"] = int(time.Until(cert.NotAfter).Hours() / 24)
	}

	return Result{
		Success:   true,
		Tool:      toolName,
		Host:      opts.Host,
		Port:      opts.Port,
		LatencyMs: float64(latency.Milliseconds()),
		Protocol:  "tls",
		Details:   details,
	}
}
