package probe

import (
	"bytes"
	"crypto/tls"
	"fmt"
	"io"
	"net/http"
	"net/http/httptrace"
	"strings"
	"time"
)

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
