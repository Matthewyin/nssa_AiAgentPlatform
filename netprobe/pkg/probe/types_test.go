package probe

import (
	"encoding/json"
	"testing"
	"testing/quick"
	"time"
)

// ============================================================================
// Property Tests for Unified Result Structure
// Feature: network-probe-optimization, Property 9: 所有探测结果符合统一结构
// Validates: Requirements 5.1, 5.2, 5.3
// ============================================================================

// TestProperty9_UnifiedResultHasRequiredFields tests that all UnifiedResult instances
// contain the required fields: tool, success, timestamp, duration_ms, target
func TestProperty9_UnifiedResultHasRequiredFields(t *testing.T) {
	// Property: For any UnifiedResult, when serialized to JSON, it must contain
	// tool (string), success (bool), timestamp (ISO8601), duration_ms (positive number), target (object)
	
	f := func(tool string, success bool, durationMs float64) bool {
		// Skip invalid inputs
		if tool == "" {
			return true
		}
		if durationMs < 0 {
			durationMs = -durationMs // Make positive
		}

		result := &UnifiedResult{
			Tool:       tool,
			Success:    success,
			Timestamp:  time.Now(),
			DurationMs: durationMs,
			Target: TargetInfo{
				Domain: "example.com",
			},
		}

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

		// Check required fields exist
		if _, ok := m["tool"]; !ok {
			t.Log("Missing 'tool' field")
			return false
		}
		if _, ok := m["success"]; !ok {
			t.Log("Missing 'success' field")
			return false
		}
		if _, ok := m["timestamp"]; !ok {
			t.Log("Missing 'timestamp' field")
			return false
		}
		if _, ok := m["duration_ms"]; !ok {
			t.Log("Missing 'duration_ms' field")
			return false
		}
		if _, ok := m["target"]; !ok {
			t.Log("Missing 'target' field")
			return false
		}

		// Check types
		if _, ok := m["tool"].(string); !ok {
			t.Log("'tool' is not a string")
			return false
		}
		if _, ok := m["success"].(bool); !ok {
			t.Log("'success' is not a bool")
			return false
		}
		if _, ok := m["timestamp"].(string); !ok {
			t.Log("'timestamp' is not a string")
			return false
		}
		if _, ok := m["duration_ms"].(float64); !ok {
			t.Log("'duration_ms' is not a number")
			return false
		}
		if _, ok := m["target"].(map[string]interface{}); !ok {
			t.Log("'target' is not an object")
			return false
		}

		return true
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 9 failed: %v", err)
	}
}

// TestProperty9_TimestampIsISO8601 tests that timestamp is in ISO8601 format
func TestProperty9_TimestampIsISO8601(t *testing.T) {
	f := func(year int, month int, day int) bool {
		// Normalize inputs to valid date ranges
		if year < 2000 {
			year = 2000 + (year % 100)
		}
		if year > 2100 {
			year = 2000 + (year % 100)
		}
		month = (month%12 + 12) % 12
		if month == 0 {
			month = 1
		}
		day = (day%28 + 28) % 28
		if day == 0 {
			day = 1
		}

		ts := time.Date(year, time.Month(month), day, 12, 0, 0, 0, time.UTC)
		result := &UnifiedResult{
			Tool:       "test",
			Success:    true,
			Timestamp:  ts,
			DurationMs: 100.0,
			Target:     TargetInfo{Domain: "example.com"},
		}

		jsonBytes, err := json.Marshal(result)
		if err != nil {
			return false
		}

		var m map[string]interface{}
		if err := json.Unmarshal(jsonBytes, &m); err != nil {
			return false
		}

		tsStr, ok := m["timestamp"].(string)
		if !ok {
			return false
		}

		// Try to parse as RFC3339 (ISO8601 compatible)
		_, err = time.Parse(time.RFC3339Nano, tsStr)
		return err == nil
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 9 (timestamp format) failed: %v", err)
	}
}

// TestProperty9_AllToolTypesProduceValidStructure tests that all tool types produce valid structure
func TestProperty9_AllToolTypesProduceValidStructure(t *testing.T) {
	tools := []string{"ping", "tcp", "tls", "http", "nslookup", "mtr", "traceroute", "diagnose"}

	for _, tool := range tools {
		t.Run(tool, func(t *testing.T) {
			result := NewUnifiedResult(tool, TargetInfo{
				Domain: "example.com",
				IP:     "1.2.3.4",
				Port:   443,
			})
			result.SetSuccess(100.5, map[string]string{"key": "value"})

			jsonBytes, err := json.Marshal(result)
			if err != nil {
				t.Fatalf("Failed to marshal %s result: %v", tool, err)
			}

			var m map[string]interface{}
			if err := json.Unmarshal(jsonBytes, &m); err != nil {
				t.Fatalf("Failed to unmarshal %s result: %v", tool, err)
			}

			// Verify required fields
			requiredFields := []string{"tool", "success", "timestamp", "duration_ms", "target"}
			for _, field := range requiredFields {
				if _, ok := m[field]; !ok {
					t.Errorf("Tool %s: missing required field '%s'", tool, field)
				}
			}

			// Verify tool name matches
			if m["tool"] != tool {
				t.Errorf("Tool name mismatch: expected %s, got %v", tool, m["tool"])
			}
		})
	}
}

// TestProperty9_FailedResultHasErrorStructure tests that failed results have proper error structure
func TestProperty9_FailedResultHasErrorStructure(t *testing.T) {
	errorCodes := []string{
		ErrDNSTimeout, ErrDNSNXDomain, ErrDNSServFail,
		ErrTCPTimeout, ErrTCPRefused, ErrTCPUnreachable,
		ErrTLSHandshakeFailed, ErrTLSCertExpired,
		ErrHTTPTimeout, ErrHTTPError,
	}

	for _, code := range errorCodes {
		t.Run(code, func(t *testing.T) {
			result := NewUnifiedResult("test", TargetInfo{Domain: "example.com"})
			result.SetError(code, "Test error message", nil)

			jsonBytes, err := json.Marshal(result)
			if err != nil {
				t.Fatalf("Failed to marshal: %v", err)
			}

			var m map[string]interface{}
			if err := json.Unmarshal(jsonBytes, &m); err != nil {
				t.Fatalf("Failed to unmarshal: %v", err)
			}

			// Verify success is false
			if m["success"] != false {
				t.Error("Failed result should have success=false")
			}

			// Verify error field exists and has proper structure
			errObj, ok := m["error"].(map[string]interface{})
			if !ok {
				t.Fatal("Missing or invalid 'error' field")
			}

			if errObj["code"] != code {
				t.Errorf("Error code mismatch: expected %s, got %v", code, errObj["code"])
			}

			if _, ok := errObj["message"].(string); !ok {
				t.Error("Error message should be a string")
			}
		})
	}
}

// TestProperty9_TargetInfoSerialization tests that TargetInfo serializes correctly
func TestProperty9_TargetInfoSerialization(t *testing.T) {
	f := func(domain, ip string, port uint16, protocol string) bool {
		target := TargetInfo{
			Domain:   domain,
			IP:       ip,
			Port:     int(port),
			Protocol: protocol,
		}

		result := &UnifiedResult{
			Tool:       "test",
			Success:    true,
			Timestamp:  time.Now(),
			DurationMs: 100.0,
			Target:     target,
		}

		jsonBytes, err := json.Marshal(result)
		if err != nil {
			return false
		}

		var decoded UnifiedResult
		if err := json.Unmarshal(jsonBytes, &decoded); err != nil {
			return false
		}

		// Verify round-trip
		return decoded.Target.Domain == domain &&
			decoded.Target.IP == ip &&
			decoded.Target.Port == int(port) &&
			decoded.Target.Protocol == protocol
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 9 (TargetInfo serialization) failed: %v", err)
	}
}

// TestProperty9_SourceInfoOptional tests that SourceInfo is optional
func TestProperty9_SourceInfoOptional(t *testing.T) {
	// Without source
	result1 := NewUnifiedResult("test", TargetInfo{Domain: "example.com"})
	result1.SetSuccess(100.0, nil)

	jsonBytes1, _ := json.Marshal(result1)
	var m1 map[string]interface{}
	json.Unmarshal(jsonBytes1, &m1)

	if _, ok := m1["source"]; ok {
		t.Error("Source should be omitted when nil")
	}

	// With source
	result2 := NewUnifiedResult("test", TargetInfo{Domain: "example.com"})
	result2.SetSuccess(100.0, nil)
	result2.SetSource("probe-1", "1.2.3.4", "Beijing", "China Telecom")

	jsonBytes2, _ := json.Marshal(result2)
	var m2 map[string]interface{}
	json.Unmarshal(jsonBytes2, &m2)

	source, ok := m2["source"].(map[string]interface{})
	if !ok {
		t.Fatal("Source should be present when set")
	}

	if source["probe_id"] != "probe-1" {
		t.Error("Source probe_id mismatch")
	}
}
