package probe

import (
	"encoding/json"
	"testing"
	"testing/quick"
)

// ============================================================================
// Property Tests for DNS Result Structure
// Feature: network-probe-optimization
// ============================================================================

// ============================================================================
// Property 1: DNS 成功结果包含必要字段
// For any 成功的 DNS 解析结果，结果 JSON 应包含 resolution_chain（数组）、
// resolved_ips（数组）、dns_server（字符串）、resolution_time_ms（正数）字段，
// 且 resolution_chain 中每条记录包含 name、type、value、ttl 字段。
// Validates: Requirements 1.1, 1.2, 1.3, 1.4
// ============================================================================

// TestProperty1_DNSSuccessResultHasRequiredFields tests that successful DNS results
// contain all required fields: resolution_chain, resolved_ips, dns_server, resolution_time_ms
func TestProperty1_DNSSuccessResultHasRequiredFields(t *testing.T) {
	// Property: For any successful DNS result, the data field must contain
	// resolution_chain (array), resolved_ips (array), dns_server (string),
	// resolution_time_ms (positive number), query_type (string)

	f := func(domain string, ip1, ip2 string, ttl1, ttl2 int, resTimeMs float64) bool {
		// Skip invalid inputs
		if domain == "" || ip1 == "" {
			return true
		}
		if resTimeMs < 0 {
			resTimeMs = -resTimeMs
		}
		if ttl1 < 0 {
			ttl1 = -ttl1
		}
		if ttl2 < 0 {
			ttl2 = -ttl2
		}

		// Create a valid DNS result
		dnsResult := &DNSResult{
			QueryType: "A",
			ResolutionChain: []DNSRecord{
				{Name: domain, Type: "A", Value: ip1, TTL: ttl1},
				{Name: domain, Type: "A", Value: ip2, TTL: ttl2},
			},
			ResolvedIPs:      []string{ip1, ip2},
			DNSServer:        "8.8.8.8",
			ResolutionTimeMs: resTimeMs,
		}

		result := NewUnifiedResult("network.nslookup", TargetInfo{Domain: domain, Protocol: "dns"})
		result.SetSuccess(resTimeMs, dnsResult)

		// Serialize to JSON
		jsonBytes, err := json.Marshal(result)
		if err != nil {
			t.Logf("Failed to marshal: %v", err)
			return false
		}

		// Deserialize to map to check fields
		var m map[string]interface{}
		if err := json.Unmarshal(jsonBytes, &m); err != nil {
			t.Logf("Failed to unmarshal: %v", err)
			return false
		}

		// Check success is true
		if m["success"] != true {
			t.Log("success should be true")
			return false
		}

		// Check data field exists
		data, ok := m["data"].(map[string]interface{})
		if !ok {
			t.Log("Missing or invalid 'data' field")
			return false
		}

		// Check required fields in data
		requiredFields := []string{"resolution_chain", "resolved_ips", "dns_server", "resolution_time_ms", "query_type"}
		for _, field := range requiredFields {
			if _, ok := data[field]; !ok {
				t.Logf("Missing required field in data: %s", field)
				return false
			}
		}

		// Check resolution_chain is an array
		chain, ok := data["resolution_chain"].([]interface{})
		if !ok {
			t.Log("resolution_chain should be an array")
			return false
		}

		// Check each record in resolution_chain has required fields
		for i, record := range chain {
			rec, ok := record.(map[string]interface{})
			if !ok {
				t.Logf("resolution_chain[%d] should be an object", i)
				return false
			}

			recordFields := []string{"name", "type", "value", "ttl"}
			for _, field := range recordFields {
				if _, ok := rec[field]; !ok {
					t.Logf("resolution_chain[%d] missing field: %s", i, field)
					return false
				}
			}
		}

		// Check resolved_ips is an array
		if _, ok := data["resolved_ips"].([]interface{}); !ok {
			t.Log("resolved_ips should be an array")
			return false
		}

		// Check dns_server is a string
		if _, ok := data["dns_server"].(string); !ok {
			t.Log("dns_server should be a string")
			return false
		}

		// Check resolution_time_ms is a positive number
		resTime, ok := data["resolution_time_ms"].(float64)
		if !ok {
			t.Log("resolution_time_ms should be a number")
			return false
		}
		if resTime < 0 {
			t.Log("resolution_time_ms should be positive")
			return false
		}

		// Check query_type is a string
		if _, ok := data["query_type"].(string); !ok {
			t.Log("query_type should be a string")
			return false
		}

		return true
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 1 failed: %v", err)
	}
}

// TestProperty1_DNSRecordHasAllFields tests that each DNS record has all required fields
func TestProperty1_DNSRecordHasAllFields(t *testing.T) {
	recordTypes := []string{"A", "AAAA", "CNAME", "MX", "NS", "TXT"}

	for _, recordType := range recordTypes {
		t.Run(recordType, func(t *testing.T) {
			record := DNSRecord{
				Name:  "example.com",
				Type:  recordType,
				Value: "test-value",
				TTL:   300,
			}
			if recordType == "MX" {
				record.Priority = 10
			}

			jsonBytes, err := json.Marshal(record)
			if err != nil {
				t.Fatalf("Failed to marshal: %v", err)
			}

			var m map[string]interface{}
			if err := json.Unmarshal(jsonBytes, &m); err != nil {
				t.Fatalf("Failed to unmarshal: %v", err)
			}

			// Check required fields
			requiredFields := []string{"name", "type", "value", "ttl"}
			for _, field := range requiredFields {
				if _, ok := m[field]; !ok {
					t.Errorf("Missing required field: %s", field)
				}
			}

			// Check MX has priority
			if recordType == "MX" {
				if _, ok := m["priority"]; !ok {
					t.Error("MX record should have priority field")
				}
			}
		})
	}
}

// TestProperty1_DNSResultRoundTrip tests that DNS results can be serialized and deserialized
func TestProperty1_DNSResultRoundTrip(t *testing.T) {
	f := func(domain string, ip string, ttl int, resTimeMs float64) bool {
		if domain == "" || ip == "" {
			return true
		}
		if ttl < 0 {
			ttl = -ttl
		}
		if resTimeMs < 0 {
			resTimeMs = -resTimeMs
		}

		original := &DNSResult{
			QueryType: "A",
			ResolutionChain: []DNSRecord{
				{Name: domain, Type: "A", Value: ip, TTL: ttl},
			},
			ResolvedIPs:      []string{ip},
			DNSServer:        "8.8.8.8",
			ResolutionTimeMs: resTimeMs,
		}

		// Serialize
		jsonBytes, err := json.Marshal(original)
		if err != nil {
			return false
		}

		// Deserialize
		var decoded DNSResult
		if err := json.Unmarshal(jsonBytes, &decoded); err != nil {
			return false
		}

		// Verify round-trip
		if decoded.QueryType != original.QueryType {
			return false
		}
		if decoded.DNSServer != original.DNSServer {
			return false
		}
		if decoded.ResolutionTimeMs != original.ResolutionTimeMs {
			return false
		}
		if len(decoded.ResolvedIPs) != len(original.ResolvedIPs) {
			return false
		}
		if len(decoded.ResolutionChain) != len(original.ResolutionChain) {
			return false
		}

		return true
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 1 (round-trip) failed: %v", err)
	}
}

// ============================================================================
// Property 2: DNS 失败结果包含结构化错误
// For any 失败的 DNS 解析结果，结果 JSON 应包含 error 对象，其中 code 字段为
// 预定义错误码之一（DNS_TIMEOUT、DNS_NXDOMAIN、DNS_SERVFAIL 等），
// message 字段为非空字符串。
// Validates: Requirements 1.5
// ============================================================================

// TestProperty2_DNSFailureResultHasStructuredError tests that failed DNS results
// contain structured error with code and message
func TestProperty2_DNSFailureResultHasStructuredError(t *testing.T) {
	// Property: For any failed DNS result, the error field must contain
	// code (predefined error code) and message (non-empty string)

	errorCodes := []string{
		ErrDNSTimeout,
		ErrDNSNXDomain,
		ErrDNSServFail,
		ErrDNSRefused,
		ErrDNSNoAnswer,
	}

	for _, code := range errorCodes {
		t.Run(code, func(t *testing.T) {
			result := NewUnifiedResult("network.nslookup", TargetInfo{
				Domain:   "example.com",
				Protocol: "dns",
			})
			result.SetError(code, "Test error message for "+code, map[string]any{
				"original_error": "underlying error",
				"query_type":     "A",
			})

			// Serialize to JSON
			jsonBytes, err := json.Marshal(result)
			if err != nil {
				t.Fatalf("Failed to marshal: %v", err)
			}

			// Deserialize to map
			var m map[string]interface{}
			if err := json.Unmarshal(jsonBytes, &m); err != nil {
				t.Fatalf("Failed to unmarshal: %v", err)
			}

			// Check success is false
			if m["success"] != false {
				t.Error("Failed result should have success=false")
			}

			// Check error field exists
			errObj, ok := m["error"].(map[string]interface{})
			if !ok {
				t.Fatal("Missing or invalid 'error' field")
			}

			// Check error code
			errCode, ok := errObj["code"].(string)
			if !ok {
				t.Fatal("Error code should be a string")
			}
			if errCode != code {
				t.Errorf("Error code mismatch: expected %s, got %s", code, errCode)
			}

			// Check error message is non-empty
			errMsg, ok := errObj["message"].(string)
			if !ok {
				t.Fatal("Error message should be a string")
			}
			if errMsg == "" {
				t.Error("Error message should not be empty")
			}
		})
	}
}

// TestProperty2_DNSErrorCodeIsValid tests that DNS error codes are from predefined set
func TestProperty2_DNSErrorCodeIsValid(t *testing.T) {
	validCodes := map[string]bool{
		ErrDNSTimeout:  true,
		ErrDNSNXDomain: true,
		ErrDNSServFail: true,
		ErrDNSRefused:  true,
		ErrDNSNoAnswer: true,
	}

	f := func(errorMsg string) bool {
		if errorMsg == "" {
			return true
		}

		// Test each valid error code
		for code := range validCodes {
			result := NewUnifiedResult("network.nslookup", TargetInfo{Domain: "test.com"})
			result.SetError(code, errorMsg, nil)

			jsonBytes, err := json.Marshal(result)
			if err != nil {
				return false
			}

			var m map[string]interface{}
			if err := json.Unmarshal(jsonBytes, &m); err != nil {
				return false
			}

			errObj, ok := m["error"].(map[string]interface{})
			if !ok {
				return false
			}

			errCode, ok := errObj["code"].(string)
			if !ok {
				return false
			}

			// Verify the code is in the valid set
			if !validCodes[errCode] {
				return false
			}
		}

		return true
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 2 failed: %v", err)
	}
}

// TestProperty2_DNSErrorHasDetails tests that DNS errors can include details
func TestProperty2_DNSErrorHasDetails(t *testing.T) {
	result := NewUnifiedResult("network.nslookup", TargetInfo{Domain: "test.com"})
	result.SetError(ErrDNSNXDomain, "Domain not found", map[string]any{
		"original_error": "lookup test.com: no such host",
		"query_type":     "A",
	})

	jsonBytes, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("Failed to marshal: %v", err)
	}

	var m map[string]interface{}
	if err := json.Unmarshal(jsonBytes, &m); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	errObj := m["error"].(map[string]interface{})
	details, ok := errObj["details"].(map[string]interface{})
	if !ok {
		t.Fatal("Error details should be present")
	}

	if _, ok := details["original_error"]; !ok {
		t.Error("Details should contain original_error")
	}
	if _, ok := details["query_type"]; !ok {
		t.Error("Details should contain query_type")
	}
}

// ============================================================================
// Integration Tests for NslookupUnified
// ============================================================================

// TestNslookupUnified_ValidDomain tests DNS lookup for a valid domain
func TestNslookupUnified_ValidDomain(t *testing.T) {
	result := NslookupUnified(NslookupOptions{
		Target:     "localhost",
		RecordType: "A",
		TimeoutSec: 5,
	})

	// Verify basic structure
	if result.Tool != "network.nslookup" {
		t.Errorf("Tool should be network.nslookup, got %s", result.Tool)
	}

	if result.Target.Domain != "localhost" {
		t.Errorf("Target domain should be localhost, got %s", result.Target.Domain)
	}

	if result.Target.Protocol != "dns" {
		t.Errorf("Target protocol should be dns, got %s", result.Target.Protocol)
	}

	// Duration should be positive
	if result.DurationMs <= 0 {
		t.Error("Duration should be positive")
	}

	// Timestamp should be set
	if result.Timestamp.IsZero() {
		t.Error("Timestamp should be set")
	}
}

// TestNslookupUnified_InvalidDomain tests DNS lookup for an invalid domain
func TestNslookupUnified_InvalidDomain(t *testing.T) {
	result := NslookupUnified(NslookupOptions{
		Target:     "this-domain-definitely-does-not-exist-12345.invalid",
		RecordType: "A",
		TimeoutSec: 5,
	})

	// This might succeed or fail depending on DNS configuration
	// Just verify the structure is valid
	if result.Tool != "network.nslookup" {
		t.Errorf("Tool should be network.nslookup, got %s", result.Tool)
	}

	// If it failed, verify error structure
	if !result.Success && result.Error != nil {
		if result.Error.Code == "" {
			t.Error("Error code should not be empty")
		}
		if result.Error.Message == "" {
			t.Error("Error message should not be empty")
		}
	}
}

// TestNslookupUnified_DifferentRecordTypes tests different DNS record types
func TestNslookupUnified_DifferentRecordTypes(t *testing.T) {
	recordTypes := []string{"A", "AAAA", "MX", "NS", "TXT", "CNAME"}

	for _, rt := range recordTypes {
		t.Run(rt, func(t *testing.T) {
			result := NslookupUnified(NslookupOptions{
				Target:     "localhost",
				RecordType: rt,
				TimeoutSec: 5,
			})

			// Verify basic structure regardless of success/failure
			if result.Tool != "network.nslookup" {
				t.Errorf("Tool should be network.nslookup, got %s", result.Tool)
			}

			// If successful, verify data structure
			if result.Success && result.Data != nil {
				dnsResult, ok := result.Data.(*DNSResult)
				if !ok {
					t.Error("Data should be *DNSResult")
					return
				}

				if dnsResult.QueryType != rt {
					t.Errorf("QueryType should be %s, got %s", rt, dnsResult.QueryType)
				}
			}
		})
	}
}

// TestNslookupUnified_WithProbeID tests that probe ID is correctly set
func TestNslookupUnified_WithProbeID(t *testing.T) {
	result := NslookupUnified(NslookupOptions{
		Target:     "localhost",
		RecordType: "A",
		TimeoutSec: 5,
	})

	// Set source info
	result.SetSource("probe-test-01", "192.168.1.1", "Beijing", "China Telecom")

	if result.Source == nil {
		t.Fatal("Source should be set")
	}

	if result.Source.ProbeID != "probe-test-01" {
		t.Errorf("ProbeID should be probe-test-01, got %s", result.Source.ProbeID)
	}

	if result.Source.IP != "192.168.1.1" {
		t.Errorf("IP should be 192.168.1.1, got %s", result.Source.IP)
	}

	if result.Source.Location != "Beijing" {
		t.Errorf("Location should be Beijing, got %s", result.Source.Location)
	}

	if result.Source.ISP != "China Telecom" {
		t.Errorf("ISP should be China Telecom, got %s", result.Source.ISP)
	}
}
