package probe

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net"
	"os"
	"time"
)

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
