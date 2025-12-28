package probe

import (
	"bytes"
	"crypto/tls"
	"fmt"
	"io"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"strings"
	"time"
)

// HTTPProbeUnified 执行 HTTP 探测并返回统一结构结果
// 支持完整的时间分解、重定向链追踪和关键响应头提取
func HTTPProbeUnified(opts HTTPOptions) *UnifiedResult {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.http"
	}
	if opts.TimeoutSec <= 0 {
		opts.TimeoutSec = 15
	}
	method := strings.ToUpper(opts.Method)
	if method == "" {
		method = "GET"
	}

	// 解析 URL 获取目标信息
	parsedURL, err := url.Parse(opts.URL)
	if err != nil {
		result := NewUnifiedResult(toolName, TargetInfo{URL: opts.URL})
		result.SetError(ErrHTTPInvalidURL, fmt.Sprintf("invalid URL: %v", err), nil)
		return result
	}

	// 构建目标信息
	target := TargetInfo{
		URL:      opts.URL,
		Domain:   parsedURL.Hostname(),
		Protocol: parsedURL.Scheme,
	}
	if parsedURL.Port() != "" {
		fmt.Sscanf(parsedURL.Port(), "%d", &target.Port)
	} else if parsedURL.Scheme == "https" {
		target.Port = 443
	} else {
		target.Port = 80
	}

	result := NewUnifiedResult(toolName, target)
	startTime := time.Now()

	// 构建请求
	var bodyReader io.Reader
	var bodySnippet string
	if opts.Body != "" {
		bodyReader = bytes.NewBufferString(opts.Body)
		if len(opts.Body) > 256 {
			bodySnippet = opts.Body[:256] + "..."
		} else {
			bodySnippet = opts.Body
		}
	}

	req, err := http.NewRequest(method, opts.URL, bodyReader)
	if err != nil {
		result.DurationMs = float64(time.Since(startTime).Milliseconds())
		result.SetError(ErrHTTPInvalidURL, fmt.Sprintf("build request failed: %v", err), nil)
		return result
	}

	// 设置请求头
	for k, v := range opts.Headers {
		req.Header.Set(k, v)
	}

	// 时间追踪变量
	var dnsStart, connectStart, tlsHandshakeStart, gotConn, gotFirstByte, wroteRequest time.Time
	var dnsDuration, connectDuration, tlsDuration, waitDuration, requestSentDuration time.Duration

	trace := &httptrace.ClientTrace{
		DNSStart: func(dsi httptrace.DNSStartInfo) {
			dnsStart = time.Now()
		},
		DNSDone: func(ddi httptrace.DNSDoneInfo) {
			dnsDuration = time.Since(dnsStart)
		},
		ConnectStart: func(network, addr string) {
			connectStart = time.Now()
		},
		ConnectDone: func(network, addr string, err error) {
			connectDuration = time.Since(connectStart)
		},
		TLSHandshakeStart: func() {
			tlsHandshakeStart = time.Now()
		},
		TLSHandshakeDone: func(cs tls.ConnectionState, err error) {
			tlsDuration = time.Since(tlsHandshakeStart)
		},
		GotConn: func(gci httptrace.GotConnInfo) {
			gotConn = time.Now()
		},
		WroteRequest: func(wri httptrace.WroteRequestInfo) {
			wroteRequest = time.Now()
			if !gotConn.IsZero() {
				requestSentDuration = time.Since(gotConn)
			}
		},
		GotFirstResponseByte: func() {
			gotFirstByte = time.Now()
			if !wroteRequest.IsZero() {
				waitDuration = time.Since(wroteRequest)
			} else if !gotConn.IsZero() {
				waitDuration = time.Since(gotConn)
			}
		},
	}
	req = req.WithContext(httptrace.WithClientTrace(req.Context(), trace))

	// 重定向追踪 - 使用手动重定向跟踪
	var redirects []HTTPRedirect
	maxRedirects := 10

	// 创建不自动跟随重定向的客户端
	transport := &http.Transport{
		TLSClientConfig:    &tls.Config{InsecureSkipVerify: false},
		DisableCompression: true, // 禁用自动解压，以便我们能看到原始的 Content-Encoding 头
	}
	client := &http.Client{
		Timeout:   time.Duration(opts.TimeoutSec) * time.Second,
		Transport: transport,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			// 阻止自动重定向，我们手动处理
			return http.ErrUseLastResponse
		},
	}

	// 手动跟踪重定向
	currentReq := req
	var resp *http.Response
	redirectCount := 0

	for {
		resp, err = client.Do(currentReq)
		if err != nil {
			totalDuration := time.Since(startTime)
			result.DurationMs = float64(totalDuration.Microseconds()) / 1000.0
			errCode := ErrHTTPError
			if strings.Contains(err.Error(), "timeout") {
				errCode = ErrHTTPTimeout
			}
			result.SetError(errCode, fmt.Sprintf("request failed: %v", err), nil)
			return result
		}

		// 检查是否是重定向响应
		if resp.StatusCode >= 300 && resp.StatusCode < 400 {
			location := resp.Header.Get("Location")
			if location == "" {
				// 没有 Location 头，不是有效的重定向
				break
			}

			redirectCount++
			if redirectCount > maxRedirects {
				resp.Body.Close()
				totalDuration := time.Since(startTime)
				result.DurationMs = float64(totalDuration.Microseconds()) / 1000.0
				result.SetError(ErrHTTPRedirectLoop, "stopped after 10 redirects", nil)
				return result
			}

			// 记录重定向
			redirects = append(redirects, HTTPRedirect{
				Index:      redirectCount,
				FromURL:    currentReq.URL.String(),
				StatusCode: resp.StatusCode,
				Location:   location,
			})

			// 解析新的 URL
			newURL, err := currentReq.URL.Parse(location)
			if err != nil {
				resp.Body.Close()
				totalDuration := time.Since(startTime)
				result.DurationMs = float64(totalDuration.Microseconds()) / 1000.0
				result.SetError(ErrHTTPInvalidURL, fmt.Sprintf("invalid redirect URL: %v", err), nil)
				return result
			}

			// 关闭当前响应体
			resp.Body.Close()

			// 创建新请求
			newReq, err := http.NewRequest(method, newURL.String(), nil)
			if err != nil {
				totalDuration := time.Since(startTime)
				result.DurationMs = float64(totalDuration.Microseconds()) / 1000.0
				result.SetError(ErrHTTPInvalidURL, fmt.Sprintf("failed to create redirect request: %v", err), nil)
				return result
			}

			// 复制原始请求头
			for k, v := range req.Header {
				newReq.Header[k] = v
			}

			currentReq = newReq
			continue
		}

		// 不是重定向，退出循环
		break
	}

	defer resp.Body.Close()

	totalDuration := time.Since(startTime)

	// 读取响应体
	bodyBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	respBodySnippet := string(bodyBytes)
	bodySize := int64(len(bodyBytes))
	transferDuration := time.Since(gotFirstByte)

	// 提取关键响应头
	respHeaders := extractKeyHeaders(resp.Header)

	// 构建 HTTP 结果
	httpResult := HTTPResult{
		Request: HTTPRequest{
			Method:      method,
			URL:         opts.URL,
			Headers:     opts.Headers,
			BodySnippet: bodySnippet,
		},
		Response: HTTPResponse{
			StatusCode:      resp.StatusCode,
			StatusText:      http.StatusText(resp.StatusCode),
			Headers:         respHeaders,
			ContentType:     resp.Header.Get("Content-Type"),
			ContentLength:   resp.ContentLength,
			ContentEncoding: resp.Header.Get("Content-Encoding"),
			Server:          resp.Header.Get("Server"),
			Protocol:        resp.Proto,
			BodySnippet:     respBodySnippet,
			BodySize:        bodySize,
			IsCompressed:    isCompressed(resp.Header.Get("Content-Encoding")),
		},
		Timing: HTTPTiming{
			DNSLookupMs:       float64(dnsDuration.Microseconds()) / 1000.0,
			TCPConnectMs:      float64(connectDuration.Microseconds()) / 1000.0,
			TLSHandshakeMs:    float64(tlsDuration.Microseconds()) / 1000.0,
			RequestSentMs:     float64(requestSentDuration.Microseconds()) / 1000.0,
			WaitingMs:         float64(waitDuration.Microseconds()) / 1000.0,
			ContentTransferMs: float64(transferDuration.Microseconds()) / 1000.0,
			TotalMs:           float64(totalDuration.Microseconds()) / 1000.0,
		},
		Redirects: redirects,
	}

	// 设置最终 URL（如果有重定向）
	if len(redirects) > 0 {
		httpResult.FinalURL = currentReq.URL.String()
	}

	// 检查期望条件
	var expectErr string
	if opts.ExpectStatus != 0 && resp.StatusCode != opts.ExpectStatus {
		expectErr = fmt.Sprintf("expect status %d, got %d", opts.ExpectStatus, resp.StatusCode)
	}
	if opts.ExpectContains != "" && !strings.Contains(respBodySnippet, opts.ExpectContains) {
		if expectErr != "" {
			expectErr += "; "
		}
		expectErr += "response not contains expected substring"
	}

	if expectErr != "" {
		result.DurationMs = float64(totalDuration.Microseconds()) / 1000.0
		result.SetError(ErrHTTPError, expectErr, map[string]any{
			"status_code": resp.StatusCode,
			"body_size":   bodySize,
		})
		result.Data = httpResult
		return result
	}

	result.SetSuccess(float64(totalDuration.Microseconds())/1000.0, httpResult)
	return result
}

// extractKeyHeaders 提取关键响应头
func extractKeyHeaders(headers http.Header) map[string]string {
	keyHeaders := []string{
		"Content-Type",
		"Content-Length",
		"Content-Encoding",
		"Server",
		"Cache-Control",
		"Expires",
		"Last-Modified",
		"ETag",
		"X-Powered-By",
		"X-Request-Id",
		"X-Response-Time",
		"Strict-Transport-Security",
		"X-Content-Type-Options",
		"X-Frame-Options",
		"X-XSS-Protection",
		"Access-Control-Allow-Origin",
		"Set-Cookie",
		"Location",
		"Vary",
		"Date",
	}

	result := make(map[string]string)
	for _, key := range keyHeaders {
		if val := headers.Get(key); val != "" {
			result[key] = val
		}
	}
	return result
}

// isCompressed 检查是否使用压缩
func isCompressed(encoding string) bool {
	if encoding == "" {
		return false
	}
	encoding = strings.ToLower(encoding)
	return strings.Contains(encoding, "gzip") ||
		strings.Contains(encoding, "br") ||
		strings.Contains(encoding, "deflate") ||
		strings.Contains(encoding, "compress")
}

// HTTPProbe 执行 HTTP 探测（保留旧接口以保持兼容性）
// Deprecated: 请使用 HTTPProbeUnified 替代
func HTTPProbe(opts HTTPOptions) Result {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.http"
	}
	if opts.TimeoutSec <= 0 {
		opts.TimeoutSec = 15
	}
	method := strings.ToUpper(opts.Method)
	if method == "" {
		method = "GET"
	}

	var bodyReader io.Reader
	if opts.Body != "" {
		bodyReader = bytes.NewBufferString(opts.Body)
	}

	req, err := http.NewRequest(method, opts.URL, bodyReader)
	if err != nil {
		return Result{
			Success: false,
			Tool:    toolName,
			URL:     opts.URL,
			Error:   fmt.Sprintf("build request failed: %v", err),
		}
	}

	for k, v := range opts.Headers {
		req.Header.Set(k, v)
	}

	var dnsStart, connectStart, tlsHandshakeStart, gotConn, gotFirstByte time.Time
	var dnsDuration, connectDuration, tlsDuration, waitDuration time.Duration

	trace := &httptrace.ClientTrace{
		DNSStart: func(dsi httptrace.DNSStartInfo) { dnsStart = time.Now() },
		DNSDone: func(ddi httptrace.DNSDoneInfo) {
			dnsDuration = time.Since(dnsStart)
		},
		ConnectStart: func(network, addr string) { connectStart = time.Now() },
		ConnectDone: func(network, addr string, err error) {
			connectDuration = time.Since(connectStart)
		},
		TLSHandshakeStart: func() { tlsHandshakeStart = time.Now() },
		TLSHandshakeDone: func(cs tls.ConnectionState, err error) {
			tlsDuration = time.Since(tlsHandshakeStart)
		},
		GotConn: func(gci httptrace.GotConnInfo) { gotConn = time.Now() },
		GotFirstResponseByte: func() {
			gotFirstByte = time.Now()
			waitDuration = time.Since(gotConn)
		},
	}
	req = req.WithContext(httptrace.WithClientTrace(req.Context(), trace))

	client := &http.Client{
		Timeout: time.Duration(opts.TimeoutSec) * time.Second,
	}

	start := time.Now()
	resp, err := client.Do(req)
	totalDuration := time.Since(start)

	if err != nil {
		return Result{
			Success: false,
			Tool:    toolName,
			URL:     opts.URL,
			Error:   fmt.Sprintf("request failed: %v", err),
		}
	}
	defer resp.Body.Close()

	bodyBytes, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	bodySnippet := string(bodyBytes)
	transferDuration := time.Since(gotFirstByte)

	details := map[string]any{
		"response_headers":     resp.Header,
		"body_snippet":         bodySnippet,
		"content_length":       resp.ContentLength,
		"protocol":             resp.Proto,
		"compressed":           strings.Contains(resp.Header.Get("Content-Encoding"), "gzip") || strings.Contains(resp.Header.Get("Content-Encoding"), "br"),
		"dns_lookup_ms":        float64(dnsDuration.Milliseconds()),
		"tcp_connection_ms":    float64(connectDuration.Milliseconds()),
		"tls_handshake_ms":     float64(tlsDuration.Milliseconds()),
		"server_processing_ms": float64(waitDuration.Milliseconds()),
		"content_transfer_ms":  float64(transferDuration.Milliseconds()),
		"total_time_ms":        float64(totalDuration.Milliseconds()),
	}

	var expectErr string
	if opts.ExpectStatus != 0 && resp.StatusCode != opts.ExpectStatus {
		expectErr = fmt.Sprintf("expect status %d, got %d", opts.ExpectStatus, resp.StatusCode)
	}
	if opts.ExpectContains != "" && !strings.Contains(bodySnippet, opts.ExpectContains) {
		if expectErr != "" {
			expectErr += "; "
		}
		expectErr += "response not contains expected substring"
	}

	success := expectErr == ""

	return Result{
		Success:    success,
		Tool:       toolName,
		URL:        opts.URL,
		StatusCode: resp.StatusCode,
		LatencyMs:  float64(totalDuration.Milliseconds()),
		Details:    details,
		Error:      expectErr,
	}
}
