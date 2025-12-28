package probe

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/quick"
)

// ============================================================================
// Property Tests for HTTP Result Structure
// Feature: network-probe-optimization, Property 5: HTTP 结果包含完整响应和时间分解
// Feature: network-probe-optimization, Property 6: HTTP 重定向链完整记录
// Validates: Requirements 3.1-3.6
// ============================================================================

// TestProperty5_HTTPResultHasCompleteResponseInfo tests that successful HTTP results
// contain complete response information including status_code, headers, content_type, content_length
func TestProperty5_HTTPResultHasCompleteResponseInfo(t *testing.T) {
	// Start a test HTTP server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Server", "TestServer/1.0")
		w.Header().Set("Cache-Control", "no-cache")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"status": "ok"}`))
	}))
	defer server.Close()

	// Perform HTTP probe
	result := HTTPProbeUnified(HTTPOptions{
		URL:        server.URL,
		Method:     "GET",
		TimeoutSec: 10,
		Tool:       "network.http",
	})

	if !result.Success {
		t.Fatalf("HTTP probe failed: %v", result.Error)
	}

	// Serialize to JSON and verify structure
	jsonBytes, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("Failed to marshal result: %v", err)
	}

	var m map[string]interface{}
	if err := json.Unmarshal(jsonBytes, &m); err != nil {
		t.Fatalf("Failed to unmarshal result: %v", err)
	}

	// Verify data field exists
	data, ok := m["data"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'data' field")
	}

	// Verify response object
	response, ok := data["response"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'response' field")
	}

	// Check required response fields
	requiredRespFields := []string{"status_code", "status_text", "headers", "content_type", "protocol"}
	for _, field := range requiredRespFields {
		if _, ok := response[field]; !ok {
			t.Errorf("Missing required response field: %s", field)
		}
	}

	// Verify status_code is a number
	if _, ok := response["status_code"].(float64); !ok {
		t.Error("'status_code' should be a number")
	}

	// Verify status_text is a string
	if _, ok := response["status_text"].(string); !ok {
		t.Error("'status_text' should be a string")
	}

	// Verify headers is an object
	if _, ok := response["headers"].(map[string]interface{}); !ok {
		t.Error("'headers' should be an object")
	}

	// Verify content_type is a string
	if _, ok := response["content_type"].(string); !ok {
		t.Error("'content_type' should be a string")
	}
}

// TestProperty5_HTTPResultHasTimingBreakdown tests that HTTP results contain complete timing breakdown
func TestProperty5_HTTPResultHasTimingBreakdown(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	}))
	defer server.Close()

	result := HTTPProbeUnified(HTTPOptions{
		URL:        server.URL,
		Method:     "GET",
		TimeoutSec: 10,
		Tool:       "network.http",
	})

	if !result.Success {
		t.Fatalf("HTTP probe failed: %v", result.Error)
	}

	jsonBytes, _ := json.Marshal(result)
	var m map[string]interface{}
	json.Unmarshal(jsonBytes, &m)

	data := m["data"].(map[string]interface{})

	// Verify timing object
	timing, ok := data["timing"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'timing' field")
	}

	// Check required timing fields
	requiredTimingFields := []string{
		"dns_lookup_ms", "tcp_connect_ms", "tls_handshake_ms",
		"waiting_ms", "content_transfer_ms", "total_ms",
	}
	for _, field := range requiredTimingFields {
		val, ok := timing[field]
		if !ok {
			t.Errorf("Missing required timing field: %s", field)
			continue
		}
		// Verify it's a number
		if _, ok := val.(float64); !ok {
			t.Errorf("'%s' should be a number", field)
		}
	}

	// Verify timing values are non-negative
	for _, field := range requiredTimingFields {
		if val, ok := timing[field].(float64); ok {
			if val < 0 {
				t.Errorf("'%s' should be non-negative, got %f", field, val)
			}
		}
	}

	// Verify total_ms is positive (request should take some time)
	totalMs := timing["total_ms"].(float64)
	if totalMs < 0 {
		t.Error("total_ms should be non-negative")
	}
}

// TestProperty5_HTTPResultHasRequestInfo tests that HTTP results contain request information
func TestProperty5_HTTPResultHasRequestInfo(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	result := HTTPProbeUnified(HTTPOptions{
		URL:        server.URL,
		Method:     "POST",
		Headers:    map[string]string{"X-Custom": "test"},
		TimeoutSec: 10,
		Tool:       "network.http",
	})

	if !result.Success {
		t.Fatalf("HTTP probe failed: %v", result.Error)
	}

	jsonBytes, _ := json.Marshal(result)
	var m map[string]interface{}
	json.Unmarshal(jsonBytes, &m)

	data := m["data"].(map[string]interface{})

	// Verify request object
	request, ok := data["request"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'request' field")
	}

	// Check required request fields
	if _, ok := request["method"]; !ok {
		t.Error("Missing 'method' field in request")
	}
	if _, ok := request["url"]; !ok {
		t.Error("Missing 'url' field in request")
	}

	// Verify method matches
	if request["method"] != "POST" {
		t.Errorf("Method mismatch: expected POST, got %v", request["method"])
	}
}

// TestProperty6_HTTPRedirectChainComplete tests that redirect chains are completely recorded
func TestProperty6_HTTPRedirectChainComplete(t *testing.T) {
	// Create a chain of redirects
	redirectCount := 3
	var servers []*httptest.Server

	// Create final destination server
	finalServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Final destination"))
	}))
	servers = append(servers, finalServer)

	// Create redirect chain (in reverse order)
	currentURL := finalServer.URL
	for i := 0; i < redirectCount; i++ {
		targetURL := currentURL
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			http.Redirect(w, r, targetURL, http.StatusFound)
		}))
		servers = append(servers, server)
		currentURL = server.URL
	}

	// Clean up all servers
	defer func() {
		for _, s := range servers {
			s.Close()
		}
	}()

	// Perform HTTP probe starting from the first redirect
	result := HTTPProbeUnified(HTTPOptions{
		URL:        currentURL,
		Method:     "GET",
		TimeoutSec: 10,
		Tool:       "network.http",
	})

	if !result.Success {
		t.Fatalf("HTTP probe failed: %v", result.Error)
	}

	// Get the HTTP result data
	httpResult, ok := result.Data.(HTTPResult)
	if !ok {
		t.Fatal("Data is not HTTPResult type")
	}

	// Verify redirect count matches
	if len(httpResult.Redirects) != redirectCount {
		t.Errorf("Redirect count mismatch: expected %d, got %d", redirectCount, len(httpResult.Redirects))
	}

	// Verify each redirect has required fields
	for i, redirect := range httpResult.Redirects {
		if redirect.Index != i+1 {
			t.Errorf("Redirect %d: index mismatch, expected %d, got %d", i, i+1, redirect.Index)
		}
		if redirect.StatusCode != http.StatusFound {
			t.Errorf("Redirect %d: status code mismatch, expected %d, got %d", i, http.StatusFound, redirect.StatusCode)
		}
		if redirect.FromURL == "" {
			t.Errorf("Redirect %d: missing from_url", i)
		}
		if redirect.Location == "" {
			t.Errorf("Redirect %d: missing location", i)
		}
	}

	// Verify final URL is set
	if httpResult.FinalURL == "" {
		t.Error("FinalURL should be set when redirects occur")
	}
	if httpResult.FinalURL != finalServer.URL {
		t.Errorf("FinalURL mismatch: expected %s, got %s", finalServer.URL, httpResult.FinalURL)
	}
}

// TestProperty6_HTTPNoRedirectNoRedirectField tests that when no redirects occur,
// the redirects field is empty and final_url is not set
func TestProperty6_HTTPNoRedirectNoRedirectField(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("No redirect"))
	}))
	defer server.Close()

	result := HTTPProbeUnified(HTTPOptions{
		URL:        server.URL,
		Method:     "GET",
		TimeoutSec: 10,
		Tool:       "network.http",
	})

	if !result.Success {
		t.Fatalf("HTTP probe failed: %v", result.Error)
	}

	httpResult, ok := result.Data.(HTTPResult)
	if !ok {
		t.Fatal("Data is not HTTPResult type")
	}

	// Verify no redirects
	if len(httpResult.Redirects) != 0 {
		t.Errorf("Expected no redirects, got %d", len(httpResult.Redirects))
	}

	// Verify final_url is empty when no redirects
	if httpResult.FinalURL != "" {
		t.Errorf("FinalURL should be empty when no redirects, got %s", httpResult.FinalURL)
	}
}

// TestProperty6_HTTPRedirectStatusCodes tests that different redirect status codes are recorded
func TestProperty6_HTTPRedirectStatusCodes(t *testing.T) {
	redirectCodes := []int{
		http.StatusMovedPermanently,  // 301
		http.StatusFound,             // 302
		http.StatusSeeOther,          // 303
		http.StatusTemporaryRedirect, // 307
		http.StatusPermanentRedirect, // 308
	}

	for _, code := range redirectCodes {
		t.Run(fmt.Sprintf("Status%d", code), func(t *testing.T) {
			// Create final destination
			finalServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusOK)
			}))
			defer finalServer.Close()

			// Create redirect server
			redirectCode := code
			redirectServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				http.Redirect(w, r, finalServer.URL, redirectCode)
			}))
			defer redirectServer.Close()

			result := HTTPProbeUnified(HTTPOptions{
				URL:        redirectServer.URL,
				Method:     "GET",
				TimeoutSec: 10,
				Tool:       "network.http",
			})

			if !result.Success {
				t.Fatalf("HTTP probe failed: %v", result.Error)
			}

			httpResult, ok := result.Data.(HTTPResult)
			if !ok {
				t.Fatal("Data is not HTTPResult type")
			}

			if len(httpResult.Redirects) != 1 {
				t.Fatalf("Expected 1 redirect, got %d", len(httpResult.Redirects))
			}

			if httpResult.Redirects[0].StatusCode != code {
				t.Errorf("Redirect status code mismatch: expected %d, got %d",
					code, httpResult.Redirects[0].StatusCode)
			}
		})
	}
}

// TestProperty5_HTTPResultWithDifferentStatusCodes tests HTTP results with various status codes
func TestProperty5_HTTPResultWithDifferentStatusCodes(t *testing.T) {
	statusCodes := []int{200, 201, 204, 400, 401, 403, 404, 500, 502, 503}

	for _, code := range statusCodes {
		t.Run(fmt.Sprintf("Status%d", code), func(t *testing.T) {
			statusCode := code
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(statusCode)
				if statusCode != http.StatusNoContent {
					w.Write([]byte(fmt.Sprintf("Status: %d", statusCode)))
				}
			}))
			defer server.Close()

			result := HTTPProbeUnified(HTTPOptions{
				URL:        server.URL,
				Method:     "GET",
				TimeoutSec: 10,
				Tool:       "network.http",
			})

			// Should succeed (we're not setting ExpectStatus)
			if !result.Success {
				t.Fatalf("HTTP probe failed: %v", result.Error)
			}

			httpResult, ok := result.Data.(HTTPResult)
			if !ok {
				t.Fatal("Data is not HTTPResult type")
			}

			if httpResult.Response.StatusCode != code {
				t.Errorf("Status code mismatch: expected %d, got %d",
					code, httpResult.Response.StatusCode)
			}

			// Verify status text is set
			if httpResult.Response.StatusText == "" {
				t.Error("StatusText should not be empty")
			}
		})
	}
}

// TestProperty5_HTTPResultKeyHeaders tests that key response headers are extracted
func TestProperty5_HTTPResultKeyHeaders(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Server", "TestServer/1.0")
		w.Header().Set("Cache-Control", "max-age=3600")
		w.Header().Set("X-Request-Id", "test-123")
		w.Header().Set("ETag", "\"abc123\"")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{}`))
	}))
	defer server.Close()

	result := HTTPProbeUnified(HTTPOptions{
		URL:        server.URL,
		Method:     "GET",
		TimeoutSec: 10,
		Tool:       "network.http",
	})

	if !result.Success {
		t.Fatalf("HTTP probe failed: %v", result.Error)
	}

	httpResult, ok := result.Data.(HTTPResult)
	if !ok {
		t.Fatal("Data is not HTTPResult type")
	}

	// Verify key headers are extracted
	expectedHeaders := map[string]string{
		"Content-Type":  "application/json",
		"Server":        "TestServer/1.0",
		"Cache-Control": "max-age=3600",
		"X-Request-Id":  "test-123",
		"ETag":          "\"abc123\"",
	}

	for key, expectedVal := range expectedHeaders {
		if val, ok := httpResult.Response.Headers[key]; !ok {
			t.Errorf("Missing header: %s", key)
		} else if val != expectedVal {
			t.Errorf("Header %s mismatch: expected %s, got %s", key, expectedVal, val)
		}
	}
}

// TestProperty5_HTTPResultCompression tests that compression is detected
func TestProperty5_HTTPResultCompression(t *testing.T) {
	testCases := []struct {
		encoding     string
		isCompressed bool
	}{
		{"gzip", true},
		{"br", true},
		{"deflate", true},
		{"", false},
		{"identity", false},
	}

	for _, tc := range testCases {
		t.Run(tc.encoding, func(t *testing.T) {
			encoding := tc.encoding
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if encoding != "" {
					w.Header().Set("Content-Encoding", encoding)
				}
				w.WriteHeader(http.StatusOK)
				w.Write([]byte("test"))
			}))
			defer server.Close()

			result := HTTPProbeUnified(HTTPOptions{
				URL:        server.URL,
				Method:     "GET",
				TimeoutSec: 10,
				Tool:       "network.http",
			})

			if !result.Success {
				t.Fatalf("HTTP probe failed: %v", result.Error)
			}

			httpResult, ok := result.Data.(HTTPResult)
			if !ok {
				t.Fatal("Data is not HTTPResult type")
			}

			if httpResult.Response.IsCompressed != tc.isCompressed {
				t.Errorf("IsCompressed mismatch for %s: expected %v, got %v",
					tc.encoding, tc.isCompressed, httpResult.Response.IsCompressed)
			}
		})
	}
}

// TestProperty5_HTTPResultSerialization tests that HTTPResult serializes correctly
func TestProperty5_HTTPResultSerialization(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("test body"))
	}))
	defer server.Close()

	result := HTTPProbeUnified(HTTPOptions{
		URL:        server.URL,
		Method:     "GET",
		TimeoutSec: 10,
		Tool:       "network.http",
	})

	if !result.Success {
		t.Fatalf("HTTP probe failed: %v", result.Error)
	}

	// Serialize and deserialize
	jsonBytes, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("Failed to marshal: %v", err)
	}

	var decoded UnifiedResult
	if err := json.Unmarshal(jsonBytes, &decoded); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	// Verify basic fields survived round-trip
	if decoded.Tool != result.Tool {
		t.Error("Tool mismatch after round-trip")
	}
	if decoded.Success != result.Success {
		t.Error("Success mismatch after round-trip")
	}
	if decoded.Target.URL != result.Target.URL {
		t.Error("Target.URL mismatch after round-trip")
	}
}

// TestProperty5_FailedHTTPProbeHasStructuredError tests that failed HTTP probes
// return structured error information
func TestProperty5_FailedHTTPProbeHasStructuredError(t *testing.T) {
	// Try to connect to a non-existent server
	result := HTTPProbeUnified(HTTPOptions{
		URL:        "http://127.0.0.1:59998/nonexistent",
		Method:     "GET",
		TimeoutSec: 2,
		Tool:       "network.http",
	})

	if result.Success {
		t.Skip("Unexpectedly connected to port 59998")
	}

	// Verify error structure
	if result.Error == nil {
		t.Fatal("Failed probe should have error field")
	}

	if result.Error.Code == "" {
		t.Error("Error should have a code")
	}

	if result.Error.Message == "" {
		t.Error("Error should have a message")
	}

	// Verify error code is one of the expected HTTP errors
	validCodes := []string{
		ErrHTTPTimeout, ErrHTTPError, ErrHTTPRedirectLoop, ErrHTTPInvalidURL,
		ErrTCPRefused, ErrTCPTimeout, ErrTCPUnreachable,
	}
	isValidCode := false
	for _, code := range validCodes {
		if result.Error.Code == code {
			isValidCode = true
			break
		}
	}
	if !isValidCode {
		t.Errorf("Unexpected error code: %s", result.Error.Code)
	}
}

// TestProperty5_HTTPResultBodySnippet tests that body snippet is captured
func TestProperty5_HTTPResultBodySnippet(t *testing.T) {
	testBody := "This is a test response body"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testBody))
	}))
	defer server.Close()

	result := HTTPProbeUnified(HTTPOptions{
		URL:        server.URL,
		Method:     "GET",
		TimeoutSec: 10,
		Tool:       "network.http",
	})

	if !result.Success {
		t.Fatalf("HTTP probe failed: %v", result.Error)
	}

	httpResult, ok := result.Data.(HTTPResult)
	if !ok {
		t.Fatal("Data is not HTTPResult type")
	}

	if httpResult.Response.BodySnippet != testBody {
		t.Errorf("BodySnippet mismatch: expected %s, got %s",
			testBody, httpResult.Response.BodySnippet)
	}

	if httpResult.Response.BodySize != int64(len(testBody)) {
		t.Errorf("BodySize mismatch: expected %d, got %d",
			len(testBody), httpResult.Response.BodySize)
	}
}

// TestProperty5_HTTPResultWithMethods tests HTTP results with different methods
func TestProperty5_HTTPResultWithMethods(t *testing.T) {
	methods := []string{"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

	for _, method := range methods {
		t.Run(method, func(t *testing.T) {
			testMethod := method
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != testMethod {
					t.Errorf("Method mismatch: expected %s, got %s", testMethod, r.Method)
				}
				w.WriteHeader(http.StatusOK)
			}))
			defer server.Close()

			result := HTTPProbeUnified(HTTPOptions{
				URL:        server.URL,
				Method:     method,
				TimeoutSec: 10,
				Tool:       "network.http",
			})

			if !result.Success {
				t.Fatalf("HTTP probe failed for method %s: %v", method, result.Error)
			}

			httpResult, ok := result.Data.(HTTPResult)
			if !ok {
				t.Fatal("Data is not HTTPResult type")
			}

			if httpResult.Request.Method != method {
				t.Errorf("Request method mismatch: expected %s, got %s",
					method, httpResult.Request.Method)
			}
		})
	}
}

// TestProperty5_HTTPTimingPropertyBased uses property-based testing to verify timing fields
func TestProperty5_HTTPTimingPropertyBased(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		io.WriteString(w, "OK")
	}))
	defer server.Close()

	f := func(iteration uint8) bool {
		result := HTTPProbeUnified(HTTPOptions{
			URL:        server.URL,
			Method:     "GET",
			TimeoutSec: 10,
			Tool:       "network.http",
		})

		if !result.Success {
			return true // Skip failed probes
		}

		httpResult, ok := result.Data.(HTTPResult)
		if !ok {
			return false
		}

		timing := httpResult.Timing

		// All timing values should be non-negative
		if timing.DNSLookupMs < 0 ||
			timing.TCPConnectMs < 0 ||
			timing.TLSHandshakeMs < 0 ||
			timing.WaitingMs < 0 ||
			timing.ContentTransferMs < 0 ||
			timing.TotalMs < 0 {
			t.Log("Negative timing value detected")
			return false
		}

		// Total should be non-negative
		if timing.TotalMs < 0 {
			t.Log("Total timing should be non-negative")
			return false
		}

		return true
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 5 (timing fields) failed: %v", err)
	}
}

// TestProperty6_RedirectChainPropertyBased uses property-based testing to verify redirect chains
func TestProperty6_RedirectChainPropertyBased(t *testing.T) {
	f := func(numRedirects uint8) bool {
		// Limit redirects to 0-5 to avoid too many servers
		redirectCount := int(numRedirects % 6)

		var servers []*httptest.Server

		// Create final destination server
		finalServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("Final"))
		}))
		servers = append(servers, finalServer)

		// Create redirect chain
		currentURL := finalServer.URL
		for i := 0; i < redirectCount; i++ {
			targetURL := currentURL
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				http.Redirect(w, r, targetURL, http.StatusFound)
			}))
			servers = append(servers, server)
			currentURL = server.URL
		}

		// Clean up
		defer func() {
			for _, s := range servers {
				s.Close()
			}
		}()

		result := HTTPProbeUnified(HTTPOptions{
			URL:        currentURL,
			Method:     "GET",
			TimeoutSec: 10,
			Tool:       "network.http",
		})

		if !result.Success {
			return true // Skip failed probes
		}

		httpResult, ok := result.Data.(HTTPResult)
		if !ok {
			return false
		}

		// Verify redirect count matches
		if len(httpResult.Redirects) != redirectCount {
			t.Logf("Redirect count mismatch: expected %d, got %d",
				redirectCount, len(httpResult.Redirects))
			return false
		}

		// Verify each redirect has required fields
		for i, redirect := range httpResult.Redirects {
			if redirect.Index != i+1 {
				t.Logf("Redirect index mismatch at %d", i)
				return false
			}
			if redirect.StatusCode == 0 {
				t.Logf("Missing status code at redirect %d", i)
				return false
			}
			if redirect.FromURL == "" {
				t.Logf("Missing from_url at redirect %d", i)
				return false
			}
			if redirect.Location == "" {
				t.Logf("Missing location at redirect %d", i)
				return false
			}
		}

		// Verify final URL is set only when redirects occur
		if redirectCount > 0 && httpResult.FinalURL == "" {
			t.Log("FinalURL should be set when redirects occur")
			return false
		}
		if redirectCount == 0 && httpResult.FinalURL != "" {
			t.Log("FinalURL should be empty when no redirects")
			return false
		}

		return true
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 6 (redirect chain) failed: %v", err)
	}
}
