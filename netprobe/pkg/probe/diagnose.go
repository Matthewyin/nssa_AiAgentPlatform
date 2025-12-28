package probe

import (
	"fmt"
	"net"
	"net/url"
	"strings"
	"sync"
	"time"
)

// Diagnose 执行综合网络诊断
// 按照 DNS → TCP → TLS → HTTP 的顺序执行探测链
func Diagnose(opts DiagnoseOptions) *UnifiedResult {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.diagnose"
	}
	if opts.TimeoutSec <= 0 {
		opts.TimeoutSec = 30
	}
	if opts.Port <= 0 {
		opts.Port = 443
	}

	startTime := time.Now()

	// 解析目标
	diagTarget, err := parseTarget(opts.Target, opts.Port)
	if err != nil {
		result := NewUnifiedResult(toolName, TargetInfo{Domain: opts.Target})
		result.SetError(ErrInvalidArgument, fmt.Sprintf("invalid target: %v", err), nil)
		return result
	}

	// 创建统一结果
	target := TargetInfo{
		Domain:   diagTarget.Domain,
		Port:     diagTarget.Port,
		Protocol: diagTarget.Protocol,
		URL:      diagTarget.Input,
	}
	result := NewUnifiedResult(toolName, target)

	// 初始化诊断结果
	diagResult := &DiagnoseResult{
		Target: *diagTarget,
		Summary: DiagnoseSummary{
			StageStatus: make(map[string]string),
			Issues:      []string{},
		},
		Recommendations: []string{},
	}

	// 检查是否跳过某个步骤
	skipSet := make(map[string]bool)
	for _, s := range opts.Skip {
		skipSet[strings.ToLower(s)] = true
	}

	// 阶段1: DNS 解析
	if !skipSet[StageDNS] {
		dnsResult := executeDNSStage(diagTarget.Domain, opts.TimeoutSec)
		diagResult.DNS = dnsResult
		if dnsResult != nil && len(dnsResult.ResolvedIPs) > 0 {
			diagResult.Summary.StageStatus[StageDNS] = StatusSuccess
		} else {
			diagResult.Summary.StageStatus[StageDNS] = StatusFailed
			diagResult.Summary.Issues = append(diagResult.Summary.Issues, "DNS resolution failed")
		}
	} else {
		diagResult.Summary.StageStatus[StageDNS] = StatusSkipped
	}

	// 获取要探测的 IP 列表
	var ipsToProbe []string
	if diagResult.DNS != nil && len(diagResult.DNS.ResolvedIPs) > 0 {
		ipsToProbe = diagResult.DNS.ResolvedIPs
	} else if !skipSet[StageDNS] {
		// DNS 失败且未跳过，无法继续
		totalDuration := time.Since(startTime)
		diagResult.Summary.OverallStatus = StatusFailed
		diagResult.Summary.TotalDurationMs = float64(totalDuration.Microseconds()) / 1000.0
		diagResult.Recommendations = append(diagResult.Recommendations, "Check DNS configuration or try a different DNS server")
		result.SetSuccess(float64(totalDuration.Microseconds())/1000.0, diagResult)
		return result
	} else {
		// DNS 被跳过，尝试直接使用目标作为 IP
		if net.ParseIP(diagTarget.Domain) != nil {
			ipsToProbe = []string{diagTarget.Domain}
		} else {
			// 无法获取 IP
			totalDuration := time.Since(startTime)
			diagResult.Summary.OverallStatus = StatusFailed
			diagResult.Summary.TotalDurationMs = float64(totalDuration.Microseconds()) / 1000.0
			diagResult.Summary.Issues = append(diagResult.Summary.Issues, "No IP addresses to probe (DNS skipped and target is not an IP)")
			result.SetSuccess(float64(totalDuration.Microseconds())/1000.0, diagResult)
			return result
		}
	}

	// 阶段2: TCP 连接探测
	if !skipSet[StageTCP] {
		tcpResults := executeTCPStage(ipsToProbe, diagTarget.Port, opts.TimeoutSec, opts.Parallel)
		diagResult.TCP = tcpResults

		// 检查 TCP 结果
		successCount := 0
		var fastestIP string
		var fastestTime float64 = -1
		for _, tcpRes := range tcpResults {
			if tcpRes.Success {
				successCount++
				if fastestTime < 0 || tcpRes.ConnectTimeMs < fastestTime {
					fastestTime = tcpRes.ConnectTimeMs
					fastestIP = tcpRes.IP
				}
			}
		}

		if successCount == len(tcpResults) {
			diagResult.Summary.StageStatus[StageTCP] = StatusSuccess
		} else if successCount > 0 {
			diagResult.Summary.StageStatus[StageTCP] = StatusPartial
			diagResult.Summary.Issues = append(diagResult.Summary.Issues,
				fmt.Sprintf("TCP connection failed for %d/%d IPs", len(tcpResults)-successCount, len(tcpResults)))
		} else {
			diagResult.Summary.StageStatus[StageTCP] = StatusFailed
			diagResult.Summary.Issues = append(diagResult.Summary.Issues, "All TCP connections failed")
		}

		if fastestIP != "" {
			diagResult.Summary.RecommendedIP = fastestIP
		}
	} else {
		diagResult.Summary.StageStatus[StageTCP] = StatusSkipped
	}

	// 阶段3: TLS 探测 (仅当端口为 443 或协议为 https 时)
	if !skipSet[StageTLS] && (diagTarget.Port == 443 || diagTarget.Protocol == "https") {
		// 选择一个成功的 IP 进行 TLS 探测
		targetIP := selectTargetIP(diagResult.TCP, ipsToProbe)
		if targetIP != "" {
			tlsResult := executeTLSStage(targetIP, diagTarget.Domain, diagTarget.Port, opts.TimeoutSec)
			diagResult.TLS = tlsResult

			if tlsResult != nil {
				diagResult.Summary.StageStatus[StageTLS] = StatusSuccess
				// 设置证书状态
				if tlsResult.Certificate.IsExpired {
					diagResult.Summary.CertStatus = CertStatusExpired
					diagResult.Summary.Issues = append(diagResult.Summary.Issues, "TLS certificate has expired")
				} else if tlsResult.Certificate.IsExpiringSoon {
					diagResult.Summary.CertStatus = CertStatusExpiringSoon
					diagResult.Summary.Issues = append(diagResult.Summary.Issues,
						fmt.Sprintf("TLS certificate expires in %d days", tlsResult.Certificate.DaysRemaining))
				} else {
					diagResult.Summary.CertStatus = CertStatusValid
				}
			} else {
				diagResult.Summary.StageStatus[StageTLS] = StatusFailed
				diagResult.Summary.CertStatus = CertStatusInvalid
				diagResult.Summary.Issues = append(diagResult.Summary.Issues, "TLS handshake failed")
			}
		} else {
			diagResult.Summary.StageStatus[StageTLS] = StatusFailed
			diagResult.Summary.Issues = append(diagResult.Summary.Issues, "No available IP for TLS probe")
		}
	} else if skipSet[StageTLS] {
		diagResult.Summary.StageStatus[StageTLS] = StatusSkipped
	}

	// 阶段4: HTTP 探测 (如果启用)
	if opts.IncludeHTTP && !skipSet[StageHTTP] {
		httpURL := buildHTTPURL(diagTarget)
		httpResult := executeHTTPStage(httpURL, opts.TimeoutSec)
		diagResult.HTTP = httpResult

		if httpResult != nil && httpResult.Response.StatusCode > 0 && httpResult.Response.StatusCode < 400 {
			diagResult.Summary.StageStatus[StageHTTP] = StatusSuccess
		} else if httpResult != nil && httpResult.Response.StatusCode >= 400 {
			diagResult.Summary.StageStatus[StageHTTP] = StatusPartial
			diagResult.Summary.Issues = append(diagResult.Summary.Issues,
				fmt.Sprintf("HTTP returned status %d", httpResult.Response.StatusCode))
		} else {
			diagResult.Summary.StageStatus[StageHTTP] = StatusFailed
			diagResult.Summary.Issues = append(diagResult.Summary.Issues, "HTTP request failed")
		}
	} else if skipSet[StageHTTP] {
		diagResult.Summary.StageStatus[StageHTTP] = StatusSkipped
	}

	// 阶段5: MTR 探测 (如果启用)
	if opts.IncludeMTR && !skipSet[StageMTR] {
		targetIP := selectTargetIP(diagResult.TCP, ipsToProbe)
		if targetIP != "" {
			mtrResult := executeMTRStage(targetIP, opts.TimeoutSec)
			diagResult.MTR = mtrResult

			if mtrResult != nil && mtrResult.Summary.TargetReached {
				diagResult.Summary.StageStatus[StageMTR] = StatusSuccess
			} else if mtrResult != nil {
				diagResult.Summary.StageStatus[StageMTR] = StatusPartial
				if len(mtrResult.Summary.HighLossHops) > 0 {
					diagResult.Summary.Issues = append(diagResult.Summary.Issues,
						fmt.Sprintf("High packet loss detected at hops: %v", mtrResult.Summary.HighLossHops))
				}
			} else {
				diagResult.Summary.StageStatus[StageMTR] = StatusFailed
			}
		}
	} else if skipSet[StageMTR] {
		diagResult.Summary.StageStatus[StageMTR] = StatusSkipped
	}

	// 计算总耗时
	totalDuration := time.Since(startTime)
	diagResult.Summary.TotalDurationMs = float64(totalDuration.Microseconds()) / 1000.0

	// 计算整体状态
	diagResult.Summary.OverallStatus = calculateOverallStatus(diagResult.Summary.StageStatus)

	// 生成建议
	diagResult.Recommendations = generateRecommendations(diagResult)

	result.SetSuccess(float64(totalDuration.Microseconds())/1000.0, diagResult)
	return result
}


// parseTarget 解析目标字符串，支持域名、IP、URL 格式
func parseTarget(target string, defaultPort int) (*DiagnoseTarget, error) {
	result := &DiagnoseTarget{
		Input:    target,
		Port:     defaultPort,
		Protocol: "tcp",
	}

	// 尝试解析为 URL
	if strings.Contains(target, "://") {
		parsedURL, err := url.Parse(target)
		if err != nil {
			return nil, fmt.Errorf("invalid URL: %v", err)
		}
		result.Domain = parsedURL.Hostname()
		result.Protocol = parsedURL.Scheme

		if parsedURL.Port() != "" {
			fmt.Sscanf(parsedURL.Port(), "%d", &result.Port)
		} else if parsedURL.Scheme == "https" {
			result.Port = 443
		} else if parsedURL.Scheme == "http" {
			result.Port = 80
		}
		return result, nil
	}

	// 检查是否包含端口
	if strings.Contains(target, ":") {
		host, portStr, err := net.SplitHostPort(target)
		if err == nil {
			result.Domain = host
			fmt.Sscanf(portStr, "%d", &result.Port)
			return result, nil
		}
	}

	// 纯域名或 IP
	result.Domain = target
	if result.Port == 443 {
		result.Protocol = "https"
	}
	return result, nil
}

// executeDNSStage 执行 DNS 解析阶段
func executeDNSStage(domain string, timeoutSec int) *DNSResult {
	unifiedResult := NslookupUnified(NslookupOptions{
		Target:     domain,
		RecordType: "A",
		TimeoutSec: timeoutSec,
		Tool:       "network.nslookup",
	})

	if !unifiedResult.Success {
		return nil
	}

	if dnsResult, ok := unifiedResult.Data.(*DNSResult); ok {
		return dnsResult
	}
	return nil
}

// executeTCPStage 执行 TCP 连接探测阶段
func executeTCPStage(ips []string, port int, timeoutSec int, parallel bool) []TCPResult {
	results := make([]TCPResult, len(ips))

	if parallel && len(ips) > 1 {
		// 并行探测
		var wg sync.WaitGroup
		for i, ip := range ips {
			wg.Add(1)
			go func(idx int, ipAddr string) {
				defer wg.Done()
				results[idx] = probeTCP(ipAddr, port, timeoutSec)
			}(i, ip)
		}
		wg.Wait()
	} else {
		// 串行探测
		for i, ip := range ips {
			results[i] = probeTCP(ip, port, timeoutSec)
		}
	}

	return results
}

// probeTCP 执行单个 TCP 连接探测
func probeTCP(ip string, port int, timeoutSec int) TCPResult {
	addr := net.JoinHostPort(ip, fmt.Sprintf("%d", port))
	start := time.Now()

	conn, err := net.DialTimeout("tcp", addr, time.Duration(timeoutSec)*time.Second)
	duration := time.Since(start)

	result := TCPResult{
		IP:            ip,
		Port:          port,
		ConnectTimeMs: float64(duration.Microseconds()) / 1000.0,
	}

	if err != nil {
		result.Success = false
		errCode := classifyTCPError(err)
		result.Error = &ErrorInfo{
			Code:    errCode,
			Message: err.Error(),
		}
	} else {
		result.Success = true
		conn.Close()
	}

	return result
}

// executeTLSStage 执行 TLS 探测阶段
func executeTLSStage(ip string, serverName string, port int, timeoutSec int) *TLSResult {
	unifiedResult := TLSProbeUnified(TLSOptions{
		Host:       ip,
		Port:       port,
		ServerName: serverName,
		TimeoutSec: timeoutSec,
		Insecure:   false,
		Tool:       "network.tls",
	})

	if !unifiedResult.Success {
		return nil
	}

	if tlsResult, ok := unifiedResult.Data.(*TLSResult); ok {
		return tlsResult
	}
	return nil
}

// executeHTTPStage 执行 HTTP 探测阶段
func executeHTTPStage(targetURL string, timeoutSec int) *HTTPResult {
	unifiedResult := HTTPProbeUnified(HTTPOptions{
		URL:        targetURL,
		Method:     "GET",
		TimeoutSec: timeoutSec,
		Tool:       "network.http",
	})

	if httpResult, ok := unifiedResult.Data.(HTTPResult); ok {
		return &httpResult
	}
	return nil
}

// executeMTRStage 执行 MTR 探测阶段
func executeMTRStage(target string, timeoutSec int) *MTRResult {
	unifiedResult := MtrEnhanced(MtrOptions{
		Target:       target,
		Count:        5,
		ReportCycles: 5,
		TimeoutSec:   timeoutSec,
		Tool:         "network.mtr",
	})

	if !unifiedResult.Success {
		return nil
	}

	if mtrResult, ok := unifiedResult.Data.(*MTRResult); ok {
		return mtrResult
	}
	return nil
}

// selectTargetIP 从 TCP 结果中选择一个可用的 IP
func selectTargetIP(tcpResults []TCPResult, fallbackIPs []string) string {
	// 优先选择 TCP 连接成功且最快的 IP
	var fastestIP string
	var fastestTime float64 = -1

	for _, tcpRes := range tcpResults {
		if tcpRes.Success {
			if fastestTime < 0 || tcpRes.ConnectTimeMs < fastestTime {
				fastestTime = tcpRes.ConnectTimeMs
				fastestIP = tcpRes.IP
			}
		}
	}

	if fastestIP != "" {
		return fastestIP
	}

	// 如果没有成功的 TCP 连接，返回第一个 IP
	if len(fallbackIPs) > 0 {
		return fallbackIPs[0]
	}

	return ""
}

// buildHTTPURL 构建 HTTP URL
func buildHTTPURL(target *DiagnoseTarget) string {
	scheme := "http"
	if target.Port == 443 || target.Protocol == "https" {
		scheme = "https"
	}

	if target.Port == 80 || target.Port == 443 {
		return fmt.Sprintf("%s://%s/", scheme, target.Domain)
	}
	return fmt.Sprintf("%s://%s:%d/", scheme, target.Domain, target.Port)
}

// calculateOverallStatus 计算整体状态
func calculateOverallStatus(stageStatus map[string]string) string {
	failedCount := 0
	successCount := 0
	totalCount := 0

	for _, status := range stageStatus {
		if status == StatusSkipped {
			continue
		}
		totalCount++
		switch status {
		case StatusSuccess:
			successCount++
		case StatusFailed:
			failedCount++
		}
	}

	if totalCount == 0 {
		return StatusSuccess
	}

	if failedCount == totalCount {
		return StatusFailed
	}
	if successCount == totalCount {
		return StatusSuccess
	}
	return StatusPartial
}

// generateRecommendations 生成诊断建议
func generateRecommendations(diagResult *DiagnoseResult) []string {
	recommendations := []string{}

	// 根据各阶段状态生成建议
	if diagResult.Summary.StageStatus[StageDNS] == StatusFailed {
		recommendations = append(recommendations, "DNS resolution failed. Check DNS configuration or try a different DNS server.")
	}

	if diagResult.Summary.StageStatus[StageTCP] == StatusFailed {
		recommendations = append(recommendations, "TCP connection failed. Check if the target port is open and accessible.")
	} else if diagResult.Summary.StageStatus[StageTCP] == StatusPartial {
		recommendations = append(recommendations, "Some TCP connections failed. Consider using the recommended IP address.")
	}

	if diagResult.Summary.StageStatus[StageTLS] == StatusFailed {
		recommendations = append(recommendations, "TLS handshake failed. Check certificate configuration and TLS version compatibility.")
	}

	if diagResult.Summary.CertStatus == CertStatusExpired {
		recommendations = append(recommendations, "Certificate has expired! Renew the certificate immediately.")
	} else if diagResult.Summary.CertStatus == CertStatusExpiringSoon {
		recommendations = append(recommendations,
			fmt.Sprintf("Certificate expires soon. Plan for renewal within %d days.", diagResult.TLS.Certificate.DaysRemaining))
	}

	if diagResult.Summary.StageStatus[StageHTTP] == StatusFailed {
		recommendations = append(recommendations, "HTTP request failed. Check if the web server is running and responding.")
	}

	if diagResult.MTR != nil && len(diagResult.MTR.Summary.HighLossHops) > 0 {
		recommendations = append(recommendations, "High packet loss detected in network path. Contact network administrator.")
	}

	// 如果一切正常
	if diagResult.Summary.OverallStatus == StatusSuccess && len(recommendations) == 0 {
		recommendations = append(recommendations, "All checks passed. Network connectivity is healthy.")
	}

	// 添加推荐 IP
	if diagResult.Summary.RecommendedIP != "" && len(diagResult.TCP) > 1 {
		recommendations = append(recommendations,
			fmt.Sprintf("Recommended IP: %s (fastest connection)", diagResult.Summary.RecommendedIP))
	}

	return recommendations
}
