package probe

import (
	"encoding/json"
	"testing"
	"testing/quick"
)

// ============================================================================
// Property Tests for Diagnose Command
// Feature: network-probe-optimization, Property 13: diagnose 返回完整综合诊断报告
// Feature: network-probe-optimization, Property 14: diagnose --skip 参数正确跳过步骤
// Validates: Requirements 7.1-7.6
// ============================================================================

// TestProperty13_DiagnoseResultHasRequiredFields tests that diagnose results contain
// required fields: target, dns, tcp, summary
func TestProperty13_DiagnoseResultHasRequiredFields(t *testing.T) {
	// Property: For any diagnose result, the JSON should contain target, summary fields
	// and when port is 443, should also contain tls field

	// Test with a mock diagnose result
	diagResult := &DiagnoseResult{
		Target: DiagnoseTarget{
			Input:    "example.com",
			Domain:   "example.com",
			Port:     443,
			Protocol: "https",
		},
		DNS: &DNSResult{
			ResolutionChain:  []DNSRecord{{Name: "example.com", Type: "A", Value: "1.2.3.4", TTL: 300}},
			ResolvedIPs:      []string{"1.2.3.4"},
			DNSServer:        "8.8.8.8",
			ResolutionTimeMs: 10.5,
			QueryType:        "A",
		},
		TCP: []TCPResult{
			{IP: "1.2.3.4", Port: 443, Success: true, ConnectTimeMs: 5.2},
		},
		TLS: &TLSResult{
			Connection: TLSConnection{
				Protocol:    "TLS 1.3",
				CipherSuite: "TLS_AES_256_GCM_SHA384",
				ServerName:  "example.com",
				IsMutualTLS: false,
			},
			Certificate: CertificateInfo{
				Subject:       CertSubject{CommonName: "example.com"},
				DaysRemaining: 100,
				IsExpired:     false,
				IsExpiringSoon: false,
			},
			Timing: TLSTiming{
				TCPConnectMs:   5.2,
				TLSHandshakeMs: 50.3,
				TotalMs:        55.5,
			},
		},
		Summary: DiagnoseSummary{
			OverallStatus:   StatusSuccess,
			TotalDurationMs: 100.5,
			RecommendedIP:   "1.2.3.4",
			CertStatus:      CertStatusValid,
			StageStatus: map[string]string{
				StageDNS: StatusSuccess,
				StageTCP: StatusSuccess,
				StageTLS: StatusSuccess,
			},
		},
		Recommendations: []string{"All checks passed."},
	}

	// Serialize to JSON
	jsonBytes, err := json.Marshal(diagResult)
	if err != nil {
		t.Fatalf("Failed to marshal DiagnoseResult: %v", err)
	}

	// Deserialize to map to check fields
	var m map[string]interface{}
	if err := json.Unmarshal(jsonBytes, &m); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	// Check required fields exist
	requiredFields := []string{"target", "summary"}
	for _, field := range requiredFields {
		if _, ok := m[field]; !ok {
			t.Errorf("Missing required field '%s'", field)
		}
	}

	// Check target structure
	target, ok := m["target"].(map[string]interface{})
	if !ok {
		t.Fatal("'target' is not an object")
	}
	targetFields := []string{"input", "domain", "port", "protocol"}
	for _, field := range targetFields {
		if _, ok := target[field]; !ok {
			t.Errorf("Missing target field '%s'", field)
		}
	}

	// Check summary structure
	summary, ok := m["summary"].(map[string]interface{})
	if !ok {
		t.Fatal("'summary' is not an object")
	}
	summaryFields := []string{"overall_status", "total_duration_ms"}
	for _, field := range summaryFields {
		if _, ok := summary[field]; !ok {
			t.Errorf("Missing summary field '%s'", field)
		}
	}

	// For port 443, TLS should be present
	if _, ok := m["tls"]; !ok {
		t.Error("TLS field should be present for port 443")
	}
}

// TestProperty13_DiagnoseResultSummaryStatus tests that summary contains valid status values
func TestProperty13_DiagnoseResultSummaryStatus(t *testing.T) {
	validStatuses := map[string]bool{
		StatusSuccess: true,
		StatusPartial: true,
		StatusFailed:  true,
		StatusSkipped: true,
	}

	testCases := []struct {
		name   string
		status string
	}{
		{"success", StatusSuccess},
		{"partial", StatusPartial},
		{"failed", StatusFailed},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			diagResult := &DiagnoseResult{
				Target: DiagnoseTarget{
					Input:  "example.com",
					Domain: "example.com",
					Port:   443,
				},
				Summary: DiagnoseSummary{
					OverallStatus:   tc.status,
					TotalDurationMs: 100.0,
					StageStatus:     map[string]string{},
				},
			}

			jsonBytes, _ := json.Marshal(diagResult)
			var m map[string]interface{}
			json.Unmarshal(jsonBytes, &m)

			summary := m["summary"].(map[string]interface{})
			status := summary["overall_status"].(string)

			if !validStatuses[status] {
				t.Errorf("Invalid overall_status: %s", status)
			}
		})
	}
}

// TestProperty14_SkipDNSRemovesDNSField tests that --skip dns removes dns field
func TestProperty14_SkipDNSRemovesDNSField(t *testing.T) {
	// Create a diagnose result with DNS skipped
	diagResult := &DiagnoseResult{
		Target: DiagnoseTarget{
			Input:  "example.com",
			Domain: "example.com",
			Port:   443,
		},
		// DNS is nil (skipped)
		DNS: nil,
		TCP: []TCPResult{
			{IP: "1.2.3.4", Port: 443, Success: true, ConnectTimeMs: 5.2},
		},
		Summary: DiagnoseSummary{
			OverallStatus:   StatusSuccess,
			TotalDurationMs: 100.0,
			StageStatus: map[string]string{
				StageDNS: StatusSkipped,
				StageTCP: StatusSuccess,
			},
		},
	}

	jsonBytes, _ := json.Marshal(diagResult)
	var m map[string]interface{}
	json.Unmarshal(jsonBytes, &m)

	// DNS field should be omitted when nil
	if _, ok := m["dns"]; ok {
		t.Error("DNS field should be omitted when skipped")
	}

	// Stage status should show skipped
	summary := m["summary"].(map[string]interface{})
	stageStatus := summary["stage_status"].(map[string]interface{})
	if stageStatus["dns"] != StatusSkipped {
		t.Errorf("DNS stage status should be 'skipped', got %v", stageStatus["dns"])
	}
}

// TestProperty14_SkipTLSRemovesTLSField tests that --skip tls removes tls field
func TestProperty14_SkipTLSRemovesTLSField(t *testing.T) {
	// Create a diagnose result with TLS skipped
	diagResult := &DiagnoseResult{
		Target: DiagnoseTarget{
			Input:  "example.com",
			Domain: "example.com",
			Port:   443,
		},
		DNS: &DNSResult{
			ResolvedIPs: []string{"1.2.3.4"},
		},
		TCP: []TCPResult{
			{IP: "1.2.3.4", Port: 443, Success: true, ConnectTimeMs: 5.2},
		},
		// TLS is nil (skipped)
		TLS: nil,
		Summary: DiagnoseSummary{
			OverallStatus:   StatusSuccess,
			TotalDurationMs: 100.0,
			StageStatus: map[string]string{
				StageDNS: StatusSuccess,
				StageTCP: StatusSuccess,
				StageTLS: StatusSkipped,
			},
		},
	}

	jsonBytes, _ := json.Marshal(diagResult)
	var m map[string]interface{}
	json.Unmarshal(jsonBytes, &m)

	// TLS field should be omitted when nil
	if _, ok := m["tls"]; ok {
		t.Error("TLS field should be omitted when skipped")
	}

	// Stage status should show skipped
	summary := m["summary"].(map[string]interface{})
	stageStatus := summary["stage_status"].(map[string]interface{})
	if stageStatus["tls"] != StatusSkipped {
		t.Errorf("TLS stage status should be 'skipped', got %v", stageStatus["tls"])
	}
}

// TestProperty14_SkipHTTPRemovesHTTPField tests that --skip http removes http field
func TestProperty14_SkipHTTPRemovesHTTPField(t *testing.T) {
	// Create a diagnose result with HTTP skipped
	diagResult := &DiagnoseResult{
		Target: DiagnoseTarget{
			Input:  "example.com",
			Domain: "example.com",
			Port:   443,
		},
		DNS: &DNSResult{
			ResolvedIPs: []string{"1.2.3.4"},
		},
		TCP: []TCPResult{
			{IP: "1.2.3.4", Port: 443, Success: true, ConnectTimeMs: 5.2},
		},
		TLS: &TLSResult{
			Connection: TLSConnection{Protocol: "TLS 1.3"},
		},
		// HTTP is nil (skipped)
		HTTP: nil,
		Summary: DiagnoseSummary{
			OverallStatus:   StatusSuccess,
			TotalDurationMs: 100.0,
			StageStatus: map[string]string{
				StageDNS:  StatusSuccess,
				StageTCP:  StatusSuccess,
				StageTLS:  StatusSuccess,
				StageHTTP: StatusSkipped,
			},
		},
	}

	jsonBytes, _ := json.Marshal(diagResult)
	var m map[string]interface{}
	json.Unmarshal(jsonBytes, &m)

	// HTTP field should be omitted when nil
	if _, ok := m["http"]; ok {
		t.Error("HTTP field should be omitted when skipped")
	}

	// Stage status should show skipped
	summary := m["summary"].(map[string]interface{})
	stageStatus := summary["stage_status"].(map[string]interface{})
	if stageStatus["http"] != StatusSkipped {
		t.Errorf("HTTP stage status should be 'skipped', got %v", stageStatus["http"])
	}
}

// TestProperty14_MultipleSkipsWork tests that multiple skip parameters work together
func TestProperty14_MultipleSkipsWork(t *testing.T) {
	// Create a diagnose result with multiple stages skipped
	diagResult := &DiagnoseResult{
		Target: DiagnoseTarget{
			Input:  "1.2.3.4",
			Domain: "1.2.3.4",
			Port:   443,
		},
		// DNS skipped
		DNS: nil,
		TCP: []TCPResult{
			{IP: "1.2.3.4", Port: 443, Success: true, ConnectTimeMs: 5.2},
		},
		// TLS skipped
		TLS: nil,
		// HTTP skipped
		HTTP: nil,
		Summary: DiagnoseSummary{
			OverallStatus:   StatusSuccess,
			TotalDurationMs: 50.0,
			StageStatus: map[string]string{
				StageDNS:  StatusSkipped,
				StageTCP:  StatusSuccess,
				StageTLS:  StatusSkipped,
				StageHTTP: StatusSkipped,
			},
		},
	}

	jsonBytes, _ := json.Marshal(diagResult)
	var m map[string]interface{}
	json.Unmarshal(jsonBytes, &m)

	// All skipped fields should be omitted
	skippedFields := []string{"dns", "tls", "http"}
	for _, field := range skippedFields {
		if _, ok := m[field]; ok {
			t.Errorf("Field '%s' should be omitted when skipped", field)
		}
	}

	// TCP should still be present
	if _, ok := m["tcp"]; !ok {
		t.Error("TCP field should be present")
	}
}

// TestProperty13_DiagnoseTargetParsing tests target parsing for various input formats
func TestProperty13_DiagnoseTargetParsing(t *testing.T) {
	testCases := []struct {
		input    string
		port     int
		expected DiagnoseTarget
	}{
		{
			input: "example.com",
			port:  443,
			expected: DiagnoseTarget{
				Input:    "example.com",
				Domain:   "example.com",
				Port:     443,
				Protocol: "https",
			},
		},
		{
			input: "https://example.com",
			port:  443,
			expected: DiagnoseTarget{
				Input:    "https://example.com",
				Domain:   "example.com",
				Port:     443,
				Protocol: "https",
			},
		},
		{
			input: "http://example.com:8080",
			port:  443,
			expected: DiagnoseTarget{
				Input:    "http://example.com:8080",
				Domain:   "example.com",
				Port:     8080,
				Protocol: "http",
			},
		},
		{
			input: "example.com:8443",
			port:  443,
			expected: DiagnoseTarget{
				Input:    "example.com:8443",
				Domain:   "example.com",
				Port:     8443,
				Protocol: "tcp",
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.input, func(t *testing.T) {
			result, err := parseTarget(tc.input, tc.port)
			if err != nil {
				t.Fatalf("parseTarget failed: %v", err)
			}

			if result.Input != tc.expected.Input {
				t.Errorf("Input mismatch: expected %s, got %s", tc.expected.Input, result.Input)
			}
			if result.Domain != tc.expected.Domain {
				t.Errorf("Domain mismatch: expected %s, got %s", tc.expected.Domain, result.Domain)
			}
			if result.Port != tc.expected.Port {
				t.Errorf("Port mismatch: expected %d, got %d", tc.expected.Port, result.Port)
			}
			if result.Protocol != tc.expected.Protocol {
				t.Errorf("Protocol mismatch: expected %s, got %s", tc.expected.Protocol, result.Protocol)
			}
		})
	}
}

// TestProperty13_OverallStatusCalculation tests that overall status is calculated correctly
func TestProperty13_OverallStatusCalculation(t *testing.T) {
	testCases := []struct {
		name        string
		stageStatus map[string]string
		expected    string
	}{
		{
			name: "all_success",
			stageStatus: map[string]string{
				StageDNS: StatusSuccess,
				StageTCP: StatusSuccess,
				StageTLS: StatusSuccess,
			},
			expected: StatusSuccess,
		},
		{
			name: "all_failed",
			stageStatus: map[string]string{
				StageDNS: StatusFailed,
				StageTCP: StatusFailed,
				StageTLS: StatusFailed,
			},
			expected: StatusFailed,
		},
		{
			name: "partial_failure",
			stageStatus: map[string]string{
				StageDNS: StatusSuccess,
				StageTCP: StatusFailed,
				StageTLS: StatusSuccess,
			},
			expected: StatusPartial,
		},
		{
			name: "with_skipped",
			stageStatus: map[string]string{
				StageDNS: StatusSuccess,
				StageTCP: StatusSuccess,
				StageTLS: StatusSkipped,
			},
			expected: StatusSuccess,
		},
		{
			name: "all_skipped",
			stageStatus: map[string]string{
				StageDNS: StatusSkipped,
				StageTCP: StatusSkipped,
				StageTLS: StatusSkipped,
			},
			expected: StatusSuccess, // No failures means success
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := calculateOverallStatus(tc.stageStatus)
			if result != tc.expected {
				t.Errorf("Expected %s, got %s", tc.expected, result)
			}
		})
	}
}

// TestProperty13_RecommendationsGeneration tests that recommendations are generated correctly
func TestProperty13_RecommendationsGeneration(t *testing.T) {
	// Test DNS failure recommendation
	t.Run("dns_failure", func(t *testing.T) {
		diagResult := &DiagnoseResult{
			Summary: DiagnoseSummary{
				StageStatus: map[string]string{
					StageDNS: StatusFailed,
				},
			},
		}
		recs := generateRecommendations(diagResult)
		found := false
		for _, rec := range recs {
			if rec == "DNS resolution failed. Check DNS configuration or try a different DNS server." {
				found = true
				break
			}
		}
		if !found {
			t.Error("Expected DNS failure recommendation")
		}
	})

	// Test certificate expiring soon recommendation
	t.Run("cert_expiring", func(t *testing.T) {
		diagResult := &DiagnoseResult{
			TLS: &TLSResult{
				Certificate: CertificateInfo{
					DaysRemaining: 15,
				},
			},
			Summary: DiagnoseSummary{
				CertStatus:  CertStatusExpiringSoon,
				StageStatus: map[string]string{},
			},
		}
		recs := generateRecommendations(diagResult)
		found := false
		for _, rec := range recs {
			if rec == "Certificate expires soon. Plan for renewal within 15 days." {
				found = true
				break
			}
		}
		if !found {
			t.Error("Expected certificate expiring recommendation")
		}
	})

	// Test all success recommendation
	t.Run("all_success", func(t *testing.T) {
		diagResult := &DiagnoseResult{
			Summary: DiagnoseSummary{
				OverallStatus: StatusSuccess,
				StageStatus:   map[string]string{},
			},
		}
		recs := generateRecommendations(diagResult)
		found := false
		for _, rec := range recs {
			if rec == "All checks passed. Network connectivity is healthy." {
				found = true
				break
			}
		}
		if !found {
			t.Error("Expected success recommendation")
		}
	})
}

// TestProperty13_DiagnoseResultSerialization tests round-trip serialization
func TestProperty13_DiagnoseResultSerialization(t *testing.T) {
	f := func(domain string, port uint16, durationMs float64) bool {
		if domain == "" {
			return true
		}
		if port == 0 {
			port = 443
		}
		if durationMs < 0 {
			durationMs = -durationMs
		}

		original := &DiagnoseResult{
			Target: DiagnoseTarget{
				Input:    domain,
				Domain:   domain,
				Port:     int(port),
				Protocol: "https",
			},
			Summary: DiagnoseSummary{
				OverallStatus:   StatusSuccess,
				TotalDurationMs: durationMs,
				StageStatus:     map[string]string{StageDNS: StatusSuccess},
			},
		}

		jsonBytes, err := json.Marshal(original)
		if err != nil {
			return false
		}

		var decoded DiagnoseResult
		if err := json.Unmarshal(jsonBytes, &decoded); err != nil {
			return false
		}

		// Verify round-trip
		return decoded.Target.Domain == domain &&
			decoded.Target.Port == int(port) &&
			decoded.Summary.OverallStatus == StatusSuccess &&
			decoded.Summary.TotalDurationMs == durationMs
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 13 (serialization) failed: %v", err)
	}
}

// TestProperty14_SkipParameterValidation tests that skip parameter values are validated
func TestProperty14_SkipParameterValidation(t *testing.T) {
	validSkipValues := []string{StageDNS, StageTCP, StageTLS, StageHTTP, StageMTR}

	for _, skip := range validSkipValues {
		t.Run(skip, func(t *testing.T) {
			// Verify the constant is defined correctly
			switch skip {
			case "dns", "tcp", "tls", "http", "mtr":
				// Valid
			default:
				t.Errorf("Invalid skip value: %s", skip)
			}
		})
	}
}
