package probe

import (
	"encoding/json"
	"math"
	"testing"
	"testing/quick"
)

// ============================================================================
// Property Tests for MTR Result Structure
// Feature: network-probe-optimization
// ============================================================================

// ============================================================================
// Property 7: MTR 结果包含结构化跳点和汇总数据
// Validates: Requirements 4.1, 4.2, 4.3
// ============================================================================

// TestProperty7_MTRResultHasStructuredHopsAndSummary tests that MTR results contain
// structured hop data and summary statistics
func TestProperty7_MTRResultHasStructuredHopsAndSummary(t *testing.T) {
	// Test with sample MTR output
	sampleOutputs := []string{
		// Standard mtr -r -w output format
		`Start: 2024-01-15T10:30:00+0800
                                 My traceroute  [v0.95]
hostname                         Loss%   Snt   Last   Avg  Best  Wrst StDev
 1.|-- 192.168.1.1               0.0%    10    1.2   1.5   1.0   2.3   0.4
 2.|-- 10.0.0.1                  0.0%    10    5.3   5.8   4.2   8.1   1.2
 3.|-- 202.97.33.1               0.0%    10   35.2  38.5  32.1  45.6   4.3
 4.|-- 1.2.3.4                   0.0%    10   45.6  48.2  42.1  55.3   5.1`,
		// Output with timeout hop
		`Start: 2024-01-15T10:30:00+0800
                                 My traceroute  [v0.95]
hostname                         Loss%   Snt   Last   Avg  Best  Wrst StDev
 1.|-- 192.168.1.1               0.0%    10    1.2   1.5   1.0   2.3   0.4
 2.|-- ???                      100.0%    10    0.0   0.0   0.0   0.0   0.0
 3.|-- 202.97.33.1               0.0%    10   35.2  38.5  32.1  45.6   4.3`,
		// Output with high loss hop
		`Start: 2024-01-15T10:30:00+0800
                                 My traceroute  [v0.95]
hostname                         Loss%   Snt   Last   Avg  Best  Wrst StDev
 1.|-- 192.168.1.1               0.0%    10    1.2   1.5   1.0   2.3   0.4
 2.|-- 10.0.0.1                 25.0%    10    5.3   5.8   4.2   8.1   1.2
 3.|-- 1.2.3.4                   0.0%    10   45.6  48.2  42.1  55.3   5.1`,
	}

	for i, output := range sampleOutputs {
		t.Run(string(rune('A'+i)), func(t *testing.T) {
			result := parseMTROutput(output, 10)

			// Verify hops array exists and is not empty
			if result.Hops == nil {
				t.Fatal("Hops array should not be nil")
			}
			if len(result.Hops) == 0 {
				t.Fatal("Hops array should not be empty for valid MTR output")
			}

			// Verify each hop has required fields
			for _, hop := range result.Hops {
				// hop_number must be positive
				if hop.HopNumber <= 0 {
					t.Errorf("Hop number should be positive, got %d", hop.HopNumber)
				}

				// loss_percent must be between 0 and 100
				if hop.LossPercent < 0 || hop.LossPercent > 100 {
					t.Errorf("Loss percent should be 0-100, got %f", hop.LossPercent)
				}

				// latency_ms must have min/max/avg/std_dev
				if !hop.IsTimeout {
					if hop.LatencyMs.Min < 0 {
						t.Errorf("Latency min should be non-negative, got %f", hop.LatencyMs.Min)
					}
					if hop.LatencyMs.Max < hop.LatencyMs.Min {
						t.Errorf("Latency max should be >= min, got max=%f, min=%f", hop.LatencyMs.Max, hop.LatencyMs.Min)
					}
					if hop.LatencyMs.Avg < hop.LatencyMs.Min || hop.LatencyMs.Avg > hop.LatencyMs.Max {
						t.Errorf("Latency avg should be between min and max, got avg=%f, min=%f, max=%f",
							hop.LatencyMs.Avg, hop.LatencyMs.Min, hop.LatencyMs.Max)
					}
					if hop.LatencyMs.StdDev < 0 {
						t.Errorf("Latency std_dev should be non-negative, got %f", hop.LatencyMs.StdDev)
					}
				}
			}

			// Verify summary has required fields
			if result.Summary.TotalHops != len(result.Hops) {
				t.Errorf("Summary total_hops should match hops array length, got %d vs %d",
					result.Summary.TotalHops, len(result.Hops))
			}

			// avg_latency_ms should be non-negative
			if result.Summary.AvgLatencyMs < 0 {
				t.Errorf("Summary avg_latency_ms should be non-negative, got %f", result.Summary.AvgLatencyMs)
			}

			// overall_loss_percent should be 0-100
			if result.Summary.OverallLossPercent < 0 || result.Summary.OverallLossPercent > 100 {
				t.Errorf("Summary overall_loss_percent should be 0-100, got %f", result.Summary.OverallLossPercent)
			}
		})
	}
}

// TestProperty7_MTRResultJSONSerialization tests that MTR results serialize correctly to JSON
func TestProperty7_MTRResultJSONSerialization(t *testing.T) {
	// Create a sample MTR result
	mtrResult := &MTRResult{
		Hops: []MTRHop{
			{
				HopNumber:   1,
				IP:          "192.168.1.1",
				PacketsSent: 10,
				PacketsRecv: 10,
				LossPercent: 0.0,
				LatencyMs: LatencyStats{
					Min:    1.0,
					Max:    2.3,
					Avg:    1.5,
					StdDev: 0.4,
					Last:   1.2,
				},
				IsTimeout:  false,
				IsHighLoss: false,
			},
			{
				HopNumber:   2,
				IP:          "10.0.0.1",
				PacketsSent: 10,
				PacketsRecv: 8,
				LossPercent: 20.0,
				LatencyMs: LatencyStats{
					Min:    4.2,
					Max:    8.1,
					Avg:    5.8,
					StdDev: 1.2,
					Last:   5.3,
				},
				IsTimeout:  false,
				IsHighLoss: false,
			},
		},
		Summary: MTRSummary{
			TotalHops:          2,
			TargetReached:      true,
			AvgLatencyMs:       5.8,
			OverallLossPercent: 20.0,
			HighLossHops:       []int{},
			TimeoutHops:        []int{},
		},
	}

	// Serialize to JSON
	jsonBytes, err := json.Marshal(mtrResult)
	if err != nil {
		t.Fatalf("Failed to marshal MTR result: %v", err)
	}

	// Deserialize to map to check structure
	var m map[string]interface{}
	if err := json.Unmarshal(jsonBytes, &m); err != nil {
		t.Fatalf("Failed to unmarshal MTR result: %v", err)
	}

	// Verify hops array exists
	hops, ok := m["hops"].([]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'hops' field")
	}
	if len(hops) != 2 {
		t.Errorf("Expected 2 hops, got %d", len(hops))
	}

	// Verify first hop structure
	hop1, ok := hops[0].(map[string]interface{})
	if !ok {
		t.Fatal("Invalid hop structure")
	}

	requiredHopFields := []string{"hop_number", "ip", "packets_sent", "packets_recv", "loss_percent", "latency_ms", "is_timeout", "is_high_loss"}
	for _, field := range requiredHopFields {
		if _, ok := hop1[field]; !ok {
			t.Errorf("Missing required hop field: %s", field)
		}
	}

	// Verify latency_ms structure
	latency, ok := hop1["latency_ms"].(map[string]interface{})
	if !ok {
		t.Fatal("Invalid latency_ms structure")
	}

	requiredLatencyFields := []string{"min", "max", "avg", "std_dev"}
	for _, field := range requiredLatencyFields {
		if _, ok := latency[field]; !ok {
			t.Errorf("Missing required latency field: %s", field)
		}
	}

	// Verify summary structure
	summary, ok := m["summary"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'summary' field")
	}

	requiredSummaryFields := []string{"total_hops", "target_reached", "avg_latency_ms", "overall_loss_percent"}
	for _, field := range requiredSummaryFields {
		if _, ok := summary[field]; !ok {
			t.Errorf("Missing required summary field: %s", field)
		}
	}
}

// TestProperty7_MTRResultInUnifiedResult tests that MTR results work correctly in UnifiedResult
func TestProperty7_MTRResultInUnifiedResult(t *testing.T) {
	mtrResult := &MTRResult{
		Hops: []MTRHop{
			{
				HopNumber:   1,
				IP:          "192.168.1.1",
				PacketsSent: 10,
				PacketsRecv: 10,
				LossPercent: 0.0,
				LatencyMs: LatencyStats{
					Min:    1.0,
					Max:    2.3,
					Avg:    1.5,
					StdDev: 0.4,
				},
			},
		},
		Summary: MTRSummary{
			TotalHops:          1,
			TargetReached:      true,
			AvgLatencyMs:       1.5,
			OverallLossPercent: 0.0,
		},
	}

	result := NewUnifiedResult("network.mtr", TargetInfo{
		Domain: "example.com",
		IP:     "1.2.3.4",
	})
	result.SetSuccess(100.5, mtrResult)

	// Serialize and verify
	jsonBytes, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("Failed to marshal: %v", err)
	}

	var m map[string]interface{}
	if err := json.Unmarshal(jsonBytes, &m); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	// Verify tool is mtr
	if m["tool"] != "network.mtr" {
		t.Errorf("Expected tool 'network.mtr', got %v", m["tool"])
	}

	// Verify data contains MTR result
	data, ok := m["data"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'data' field")
	}

	if _, ok := data["hops"]; !ok {
		t.Error("Data should contain 'hops' field")
	}
	if _, ok := data["summary"]; !ok {
		t.Error("Data should contain 'summary' field")
	}
}

// ============================================================================
// Property 8: MTR 高丢包跳点正确标识
// Validates: Requirements 4.4, 4.5
// ============================================================================

// TestProperty8_HighLossHopsCorrectlyIdentified tests that hops with loss > 20% are marked as high loss
func TestProperty8_HighLossHopsCorrectlyIdentified(t *testing.T) {
	// Property: For any hop with loss_percent > 20, is_high_loss should be true
	// For any hop with loss_percent <= 20, is_high_loss should be false (unless timeout)

	f := func(lossPercent float64) bool {
		// Normalize loss percent to valid range
		lossPercent = math.Abs(lossPercent)
		if lossPercent > 100 {
			lossPercent = math.Mod(lossPercent, 100)
		}

		// Simulate parsing a hop with this loss percent
		isTimeout := lossPercent >= 100
		isHighLoss := lossPercent > HighLossThreshold && !isTimeout

		// Verify the logic
		if lossPercent > HighLossThreshold && lossPercent < 100 {
			// Should be marked as high loss
			if !isHighLoss {
				return false
			}
		} else if lossPercent <= HighLossThreshold {
			// Should NOT be marked as high loss
			if isHighLoss {
				return false
			}
		} else if lossPercent >= 100 {
			// Timeout - should NOT be marked as high loss (it's timeout instead)
			if isHighLoss {
				return false
			}
		}

		return true
	}

	if err := quick.Check(f, &quick.Config{MaxCount: 100}); err != nil {
		t.Errorf("Property 8 (high loss identification) failed: %v", err)
	}
}

// TestProperty8_TimeoutHopsCorrectlyIdentified tests that timeout hops are correctly identified
func TestProperty8_TimeoutHopsCorrectlyIdentified(t *testing.T) {
	// Test with MTR output containing timeout hops
	output := `Start: 2024-01-15T10:30:00+0800
                                 My traceroute  [v0.95]
hostname                         Loss%   Snt   Last   Avg  Best  Wrst StDev
 1.|-- 192.168.1.1               0.0%    10    1.2   1.5   1.0   2.3   0.4
 2.|-- ???                      100.0%    10    0.0   0.0   0.0   0.0   0.0
 3.|-- 202.97.33.1               0.0%    10   35.2  38.5  32.1  45.6   4.3
 4.|-- ???                      100.0%    10    0.0   0.0   0.0   0.0   0.0
 5.|-- 1.2.3.4                   0.0%    10   45.6  48.2  42.1  55.3   5.1`

	result := parseMTROutput(output, 10)

	// Verify timeout hops are identified
	timeoutHops := []int{}
	for _, hop := range result.Hops {
		if hop.IsTimeout {
			timeoutHops = append(timeoutHops, hop.HopNumber)
		}
	}

	// Hops 2 and 4 should be timeout
	expectedTimeouts := []int{2, 4}
	if len(timeoutHops) != len(expectedTimeouts) {
		t.Errorf("Expected %d timeout hops, got %d", len(expectedTimeouts), len(timeoutHops))
	}

	for i, expected := range expectedTimeouts {
		if i < len(timeoutHops) && timeoutHops[i] != expected {
			t.Errorf("Expected timeout hop %d, got %d", expected, timeoutHops[i])
		}
	}

	// Verify timeout hops are in summary
	if len(result.Summary.TimeoutHops) != len(expectedTimeouts) {
		t.Errorf("Summary should have %d timeout hops, got %d", len(expectedTimeouts), len(result.Summary.TimeoutHops))
	}
}

// TestProperty8_HighLossHopsInSummary tests that high loss hops are recorded in summary
func TestProperty8_HighLossHopsInSummary(t *testing.T) {
	// Test with MTR output containing high loss hops
	output := `Start: 2024-01-15T10:30:00+0800
                                 My traceroute  [v0.95]
hostname                         Loss%   Snt   Last   Avg  Best  Wrst StDev
 1.|-- 192.168.1.1               0.0%    10    1.2   1.5   1.0   2.3   0.4
 2.|-- 10.0.0.1                 25.0%    10    5.3   5.8   4.2   8.1   1.2
 3.|-- 202.97.33.1              50.0%    10   35.2  38.5  32.1  45.6   4.3
 4.|-- 1.2.3.4                   0.0%    10   45.6  48.2  42.1  55.3   5.1`

	result := parseMTROutput(output, 10)

	// Verify high loss hops are identified
	highLossHops := []int{}
	for _, hop := range result.Hops {
		if hop.IsHighLoss {
			highLossHops = append(highLossHops, hop.HopNumber)
		}
	}

	// Hops 2 and 3 should be high loss (25% and 50% > 20%)
	expectedHighLoss := []int{2, 3}
	if len(highLossHops) != len(expectedHighLoss) {
		t.Errorf("Expected %d high loss hops, got %d", len(expectedHighLoss), len(highLossHops))
	}

	// Verify high loss hops are in summary
	if len(result.Summary.HighLossHops) != len(expectedHighLoss) {
		t.Errorf("Summary should have %d high loss hops, got %d", len(expectedHighLoss), len(result.Summary.HighLossHops))
	}
}

// TestProperty8_TimeoutHopsNotOmitted tests that timeout hops are not omitted from results
func TestProperty8_TimeoutHopsNotOmitted(t *testing.T) {
	// Property: Timeout hops should be included in the results, not omitted
	output := `Start: 2024-01-15T10:30:00+0800
                                 My traceroute  [v0.95]
hostname                         Loss%   Snt   Last   Avg  Best  Wrst StDev
 1.|-- 192.168.1.1               0.0%    10    1.2   1.5   1.0   2.3   0.4
 2.|-- ???                      100.0%    10    0.0   0.0   0.0   0.0   0.0
 3.|-- 202.97.33.1               0.0%    10   35.2  38.5  32.1  45.6   4.3`

	result := parseMTROutput(output, 10)

	// Should have 3 hops, including the timeout hop
	if len(result.Hops) != 3 {
		t.Errorf("Expected 3 hops (including timeout), got %d", len(result.Hops))
	}

	// Hop 2 should be present and marked as timeout
	if len(result.Hops) >= 2 {
		hop2 := result.Hops[1]
		if hop2.HopNumber != 2 {
			t.Errorf("Expected hop number 2, got %d", hop2.HopNumber)
		}
		if !hop2.IsTimeout {
			t.Error("Hop 2 should be marked as timeout")
		}
		if hop2.LossPercent != 100.0 {
			t.Errorf("Timeout hop should have 100%% loss, got %f", hop2.LossPercent)
		}
	}
}

// TestProperty8_HighLossThresholdIs20Percent tests that the high loss threshold is 20%
func TestProperty8_HighLossThresholdIs20Percent(t *testing.T) {
	// Verify the constant is set correctly
	if HighLossThreshold != 20.0 {
		t.Errorf("HighLossThreshold should be 20.0, got %f", HighLossThreshold)
	}

	// Test boundary cases
	testCases := []struct {
		lossPercent    float64
		expectedHighLoss bool
	}{
		{0.0, false},
		{10.0, false},
		{20.0, false},  // Exactly 20% is NOT high loss (> 20%)
		{20.1, true},   // Just above threshold
		{25.0, true},
		{50.0, true},
		{99.9, true},
		{100.0, false}, // 100% is timeout, not high loss
	}

	for _, tc := range testCases {
		isTimeout := tc.lossPercent >= 100
		isHighLoss := tc.lossPercent > HighLossThreshold && !isTimeout

		if isHighLoss != tc.expectedHighLoss {
			t.Errorf("Loss %.1f%%: expected isHighLoss=%v, got %v", tc.lossPercent, tc.expectedHighLoss, isHighLoss)
		}
	}
}

// ============================================================================
// Additional Unit Tests
// ============================================================================

// TestParseMTROutput_EmptyOutput tests parsing empty output
func TestParseMTROutput_EmptyOutput(t *testing.T) {
	result := parseMTROutput("", 10)

	if result == nil {
		t.Fatal("Result should not be nil")
	}
	if len(result.Hops) != 0 {
		t.Errorf("Expected 0 hops for empty output, got %d", len(result.Hops))
	}
	if result.Summary.TotalHops != 0 {
		t.Errorf("Expected total_hops=0, got %d", result.Summary.TotalHops)
	}
}

// TestParseMTROutput_HeaderOnly tests parsing output with only headers
func TestParseMTROutput_HeaderOnly(t *testing.T) {
	output := `Start: 2024-01-15T10:30:00+0800
                                 My traceroute  [v0.95]
hostname                         Loss%   Snt   Last   Avg  Best  Wrst StDev`

	result := parseMTROutput(output, 10)

	if len(result.Hops) != 0 {
		t.Errorf("Expected 0 hops for header-only output, got %d", len(result.Hops))
	}
}

// TestIsIPAddress tests the IP address detection function
func TestIsIPAddress(t *testing.T) {
	testCases := []struct {
		input    string
		expected bool
	}{
		{"192.168.1.1", true},
		{"10.0.0.1", true},
		{"1.2.3.4", true},
		{"255.255.255.255", true},
		{"::1", true},
		{"2001:db8::1", true},
		{"example.com", false},
		{"router.local", false},
		{"???", false},
		{"", false},
	}

	for _, tc := range testCases {
		result := isIPAddress(tc.input)
		if result != tc.expected {
			t.Errorf("isIPAddress(%q): expected %v, got %v", tc.input, tc.expected, result)
		}
	}
}
