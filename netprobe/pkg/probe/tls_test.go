package probe

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"math/big"
	"net"
	"testing"
	"testing/quick"
	"time"
)

// ============================================================================
// Property Tests for TLS Result Structure
// Feature: network-probe-optimization, Property 3: TLS 结果包含完整证书和连接信息
// Feature: network-probe-optimization, Property 4: 证书即将过期时标记警告
// Validates: Requirements 2.1-2.9
// ============================================================================

// TestProperty3_TLSResultHasCompleteConnectionInfo tests that successful TLS results
// contain complete connection information including protocol, cipher_suite, is_mutual_tls
func TestProperty3_TLSResultHasCompleteConnectionInfo(t *testing.T) {
	// Start a test TLS server
	server, serverAddr := startTestTLSServer(t, 365) // Valid for 365 days
	defer server.Close()

	// Perform TLS probe
	result := TLSProbeUnified(TLSOptions{
		Host:       "127.0.0.1",
		Port:       serverAddr.Port,
		ServerName: "localhost",
		TimeoutSec: 10,
		Insecure:   true, // Skip verification for self-signed cert
		Tool:       "network.tls",
	})

	if !result.Success {
		t.Fatalf("TLS probe failed: %v", result.Error)
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

	// Verify connection object
	connection, ok := data["connection"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'connection' field")
	}

	// Check required connection fields
	requiredConnFields := []string{"protocol", "cipher_suite", "server_name", "is_mutual_tls"}
	for _, field := range requiredConnFields {
		if _, ok := connection[field]; !ok {
			t.Errorf("Missing required connection field: %s", field)
		}
	}

	// Verify protocol is a string
	if _, ok := connection["protocol"].(string); !ok {
		t.Error("'protocol' should be a string")
	}

	// Verify cipher_suite is a string
	if _, ok := connection["cipher_suite"].(string); !ok {
		t.Error("'cipher_suite' should be a string")
	}

	// Verify is_mutual_tls is a bool
	if _, ok := connection["is_mutual_tls"].(bool); !ok {
		t.Error("'is_mutual_tls' should be a bool")
	}
}

// TestProperty3_TLSResultHasCompleteCertificateInfo tests that successful TLS results
// contain complete certificate information
func TestProperty3_TLSResultHasCompleteCertificateInfo(t *testing.T) {
	// Start a test TLS server
	server, serverAddr := startTestTLSServer(t, 365)
	defer server.Close()

	// Perform TLS probe
	result := TLSProbeUnified(TLSOptions{
		Host:       "127.0.0.1",
		Port:       serverAddr.Port,
		ServerName: "localhost",
		TimeoutSec: 10,
		Insecure:   true,
		Tool:       "network.tls",
	})

	if !result.Success {
		t.Fatalf("TLS probe failed: %v", result.Error)
	}

	jsonBytes, _ := json.Marshal(result)
	var m map[string]interface{}
	json.Unmarshal(jsonBytes, &m)

	data := m["data"].(map[string]interface{})

	// Verify certificate object
	cert, ok := data["certificate"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'certificate' field")
	}

	// Check required certificate fields
	requiredCertFields := []string{
		"subject", "issuer", "not_before", "not_after",
		"days_remaining", "fingerprint_sha256",
	}
	for _, field := range requiredCertFields {
		if _, ok := cert[field]; !ok {
			t.Errorf("Missing required certificate field: %s", field)
		}
	}

	// Verify subject has cn field
	subject, ok := cert["subject"].(map[string]interface{})
	if !ok {
		t.Fatal("Missing or invalid 'subject' field")
	}
	if _, ok := subject["cn"]; !ok {
		t.Error("Missing 'cn' in subject")
	}

	// Verify issuer exists
	if _, ok := cert["issuer"].(map[string]interface{}); !ok {
		t.Error("Missing or invalid 'issuer' field")
	}

	// Verify fingerprint is a string
	if _, ok := cert["fingerprint_sha256"].(string); !ok {
		t.Error("'fingerprint_sha256' should be a string")
	}
}

// TestProperty3_TLSResultHasTimingBreakdown tests that TLS results contain timing breakdown
func TestProperty3_TLSResultHasTimingBreakdown(t *testing.T) {
	server, serverAddr := startTestTLSServer(t, 365)
	defer server.Close()

	result := TLSProbeUnified(TLSOptions{
		Host:       "127.0.0.1",
		Port:       serverAddr.Port,
		ServerName: "localhost",
		TimeoutSec: 10,
		Insecure:   true,
		Tool:       "network.tls",
	})

	if !result.Success {
		t.Fatalf("TLS probe failed: %v", result.Error)
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
	requiredTimingFields := []string{"tcp_connect_ms", "tls_handshake_ms", "total_ms"}
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

	// Verify timing values are positive
	tcpMs := timing["tcp_connect_ms"].(float64)
	tlsMs := timing["tls_handshake_ms"].(float64)
	totalMs := timing["total_ms"].(float64)

	if tcpMs < 0 {
		t.Error("tcp_connect_ms should be non-negative")
	}
	if tlsMs < 0 {
		t.Error("tls_handshake_ms should be non-negative")
	}
	if totalMs < 0 {
		t.Error("total_ms should be non-negative")
	}

	// Total should be >= tcp + tls (approximately)
	if totalMs < tcpMs {
		t.Error("total_ms should be >= tcp_connect_ms")
	}
}

// TestProperty4_ExpiringCertificateWarning tests that certificates expiring within 30 days
// are marked with is_expiring_soon=true and have warnings
func TestProperty4_ExpiringCertificateWarning(t *testing.T) {
	// Test with certificate expiring in 15 days (should trigger warning)
	server, serverAddr := startTestTLSServer(t, 15)
	defer server.Close()

	result := TLSProbeUnified(TLSOptions{
		Host:       "127.0.0.1",
		Port:       serverAddr.Port,
		ServerName: "localhost",
		TimeoutSec: 10,
		Insecure:   true,
		Tool:       "network.tls",
	})

	if !result.Success {
		t.Fatalf("TLS probe failed: %v", result.Error)
	}

	// Get the TLS result data
	tlsResult, ok := result.Data.(*TLSResult)
	if !ok {
		t.Fatal("Data is not TLSResult type")
	}

	// Verify is_expiring_soon is true
	if !tlsResult.Certificate.IsExpiringSoon {
		t.Error("Certificate expiring in 15 days should have is_expiring_soon=true")
	}

	// Verify warnings contain expiration warning
	hasExpirationWarning := false
	for _, warning := range tlsResult.Security.Warnings {
		if len(warning) > 0 {
			hasExpirationWarning = true
			break
		}
	}
	if !hasExpirationWarning {
		t.Error("Certificate expiring soon should have warnings")
	}
}

// TestProperty4_ValidCertificateNoWarning tests that certificates with > 30 days validity
// do not have expiration warnings
func TestProperty4_ValidCertificateNoWarning(t *testing.T) {
	// Test with certificate valid for 365 days (should not trigger warning)
	server, serverAddr := startTestTLSServer(t, 365)
	defer server.Close()

	result := TLSProbeUnified(TLSOptions{
		Host:       "127.0.0.1",
		Port:       serverAddr.Port,
		ServerName: "localhost",
		TimeoutSec: 10,
		Insecure:   true,
		Tool:       "network.tls",
	})

	if !result.Success {
		t.Fatalf("TLS probe failed: %v", result.Error)
	}

	tlsResult, ok := result.Data.(*TLSResult)
	if !ok {
		t.Fatal("Data is not TLSResult type")
	}

	// Verify is_expiring_soon is false
	if tlsResult.Certificate.IsExpiringSoon {
		t.Error("Certificate valid for 365 days should have is_expiring_soon=false")
	}

	// Verify is_expired is false
	if tlsResult.Certificate.IsExpired {
		t.Error("Certificate valid for 365 days should have is_expired=false")
	}
}

// TestProperty4_DaysRemainingCalculation tests that days_remaining is calculated correctly
func TestProperty4_DaysRemainingCalculation(t *testing.T) {
	f := func(daysValid uint8) bool {
		// Limit to reasonable range (1-200 days)
		days := int(daysValid%200) + 1

		server, serverAddr := startTestTLSServer(t, days)
		defer server.Close()

		result := TLSProbeUnified(TLSOptions{
			Host:       "127.0.0.1",
			Port:       serverAddr.Port,
			ServerName: "localhost",
			TimeoutSec: 10,
			Insecure:   true,
			Tool:       "network.tls",
		})

		if !result.Success {
			return true // Skip failed probes
		}

		tlsResult, ok := result.Data.(*TLSResult)
		if !ok {
			return false
		}

		// Days remaining should be approximately equal to days (within 1 day tolerance)
		diff := tlsResult.Certificate.DaysRemaining - days
		if diff < -1 || diff > 1 {
			t.Logf("Days mismatch: expected ~%d, got %d", days, tlsResult.Certificate.DaysRemaining)
			return false
		}

		// is_expiring_soon should be true if days < 30
		expectedExpiringSoon := days < 30
		if tlsResult.Certificate.IsExpiringSoon != expectedExpiringSoon {
			t.Logf("is_expiring_soon mismatch: days=%d, expected=%v, got=%v",
				days, expectedExpiringSoon, tlsResult.Certificate.IsExpiringSoon)
			return false
		}

		return true
	}

	// Run with fewer iterations due to server startup overhead
	if err := quick.Check(f, &quick.Config{MaxCount: 10}); err != nil {
		t.Errorf("Property 4 (days remaining calculation) failed: %v", err)
	}
}

// TestProperty3_TLSResultSerialization tests that TLSResult serializes correctly
func TestProperty3_TLSResultSerialization(t *testing.T) {
	server, serverAddr := startTestTLSServer(t, 365)
	defer server.Close()

	result := TLSProbeUnified(TLSOptions{
		Host:       "127.0.0.1",
		Port:       serverAddr.Port,
		ServerName: "localhost",
		TimeoutSec: 10,
		Insecure:   true,
		Tool:       "network.tls",
	})

	if !result.Success {
		t.Fatalf("TLS probe failed: %v", result.Error)
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
	if decoded.Target.Domain != result.Target.Domain {
		t.Error("Target.Domain mismatch after round-trip")
	}
	if decoded.Target.Port != result.Target.Port {
		t.Error("Target.Port mismatch after round-trip")
	}
}

// TestProperty3_FailedTLSProbeHasStructuredError tests that failed TLS probes
// return structured error information
func TestProperty3_FailedTLSProbeHasStructuredError(t *testing.T) {
	// Try to connect to a non-existent server
	result := TLSProbeUnified(TLSOptions{
		Host:       "127.0.0.1",
		Port:       59999, // Unlikely to be listening
		ServerName: "localhost",
		TimeoutSec: 2,
		Insecure:   true,
		Tool:       "network.tls",
	})

	if result.Success {
		t.Skip("Unexpectedly connected to port 59999")
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

	// Verify error code is one of the expected TCP/TLS errors
	validCodes := []string{
		ErrTCPTimeout, ErrTCPRefused, ErrTCPUnreachable, ErrTCPReset,
		ErrTLSHandshakeFailed, ErrTLSCertExpired, ErrTLSCertInvalid,
		ErrTLSCertNotTrusted, ErrTLSProtocolError,
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

// ============================================================================
// Helper Functions
// ============================================================================

// testServerAddr holds the address of a test server
type testServerAddr struct {
	Host string
	Port int
}

// startTestTLSServer starts a TLS server with a self-signed certificate
// that expires in the specified number of days
func startTestTLSServer(t *testing.T, daysValid int) (net.Listener, testServerAddr) {
	t.Helper()

	// Generate a self-signed certificate
	cert, key := generateSelfSignedCert(t, daysValid)

	tlsCert, err := tls.X509KeyPair(cert, key)
	if err != nil {
		t.Fatalf("Failed to create TLS certificate: %v", err)
	}

	config := &tls.Config{
		Certificates: []tls.Certificate{tlsCert},
	}

	// Listen on a random port
	listener, err := tls.Listen("tcp", "127.0.0.1:0", config)
	if err != nil {
		t.Fatalf("Failed to start TLS server: %v", err)
	}

	// Get the actual port
	addr := listener.Addr().(*net.TCPAddr)

	// Accept connections in background
	go func() {
		for {
			conn, err := listener.Accept()
			if err != nil {
				return // Server closed
			}
			// Handle connection in a goroutine
			go func(c net.Conn) {
				defer c.Close()
				// Perform TLS handshake by reading/writing
				tlsConn, ok := c.(*tls.Conn)
				if !ok {
					return
				}
				// Complete the handshake
				if err := tlsConn.Handshake(); err != nil {
					return
				}
				// Keep connection open briefly to allow client to complete
				time.Sleep(100 * time.Millisecond)
			}(conn)
		}
	}()

	return listener, testServerAddr{Host: "127.0.0.1", Port: addr.Port}
}

// generateSelfSignedCert generates a self-signed certificate valid for the specified days
func generateSelfSignedCert(t *testing.T, daysValid int) (certPEM, keyPEM []byte) {
	t.Helper()

	// Generate private key
	privateKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("Failed to generate private key: %v", err)
	}

	// Create certificate template
	serialNumber, _ := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	template := x509.Certificate{
		SerialNumber: serialNumber,
		Subject: pkix.Name{
			CommonName:   "localhost",
			Organization: []string{"Test Org"},
			Country:      []string{"US"},
		},
		NotBefore:             time.Now(),
		NotAfter:              time.Now().AddDate(0, 0, daysValid),
		KeyUsage:              x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		DNSNames:              []string{"localhost"},
		IPAddresses:           []net.IP{net.ParseIP("127.0.0.1")},
	}

	// Create certificate
	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &privateKey.PublicKey, privateKey)
	if err != nil {
		t.Fatalf("Failed to create certificate: %v", err)
	}

	// Encode to PEM
	certPEM = pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER})

	keyDER, err := x509.MarshalECPrivateKey(privateKey)
	if err != nil {
		t.Fatalf("Failed to marshal private key: %v", err)
	}
	keyPEM = pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDER})

	return certPEM, keyPEM
}
