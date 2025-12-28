package probe

import "time"

// ============================================================================
// Error Codes - 预定义错误码
// ============================================================================

const (
	// DNS 相关错误码
	ErrDNSTimeout   = "DNS_TIMEOUT"   // DNS 解析超时
	ErrDNSNXDomain  = "DNS_NXDOMAIN"  // 域名不存在
	ErrDNSServFail  = "DNS_SERVFAIL"  // DNS 服务器错误
	ErrDNSRefused   = "DNS_REFUSED"   // DNS 查询被拒绝
	ErrDNSNoAnswer  = "DNS_NO_ANSWER" // DNS 无应答

	// TCP 相关错误码
	ErrTCPTimeout     = "TCP_TIMEOUT"     // TCP 连接超时
	ErrTCPRefused     = "TCP_REFUSED"     // 连接被拒绝
	ErrTCPUnreachable = "TCP_UNREACHABLE" // 目标不可达
	ErrTCPReset       = "TCP_RESET"       // 连接被重置

	// TLS 相关错误码
	ErrTLSHandshakeFailed = "TLS_HANDSHAKE_FAILED" // TLS 握手失败
	ErrTLSCertExpired     = "TLS_CERT_EXPIRED"     // 证书已过期
	ErrTLSCertInvalid     = "TLS_CERT_INVALID"     // 证书无效
	ErrTLSCertNotTrusted  = "TLS_CERT_NOT_TRUSTED" // 证书不受信任
	ErrTLSProtocolError   = "TLS_PROTOCOL_ERROR"   // TLS 协议错误

	// HTTP 相关错误码
	ErrHTTPTimeout       = "HTTP_TIMEOUT"        // HTTP 请求超时
	ErrHTTPError         = "HTTP_ERROR"          // HTTP 错误响应
	ErrHTTPRedirectLoop  = "HTTP_REDIRECT_LOOP"  // 重定向循环
	ErrHTTPInvalidURL    = "HTTP_INVALID_URL"    // 无效的 URL
	ErrHTTPBodyTooLarge  = "HTTP_BODY_TOO_LARGE" // 响应体过大

	// 系统相关错误码
	ErrCommandNotFound  = "COMMAND_NOT_FOUND"  // 系统命令不存在
	ErrPermissionDenied = "PERMISSION_DENIED"  // 权限不足
	ErrInvalidArgument  = "INVALID_ARGUMENT"   // 无效参数
	ErrInternalError    = "INTERNAL_ERROR"     // 内部错误
)

// ============================================================================
// Unified Result Structure - 统一结果结构
// ============================================================================

// UnifiedResult 统一的探测结果结构
// 所有探测工具都使用此结构返回结果，确保一致性
type UnifiedResult struct {
	// 基础信息
	Tool       string    `json:"tool"`                  // 工具名称: ping, tcp, tls, http, nslookup, mtr, traceroute, diagnose
	Success    bool      `json:"success"`               // 探测是否成功
	Timestamp  time.Time `json:"timestamp"`             // 探测时间戳 (ISO8601 格式)
	DurationMs float64   `json:"duration_ms"`           // 探测总耗时 (毫秒)

	// 目标信息
	Target TargetInfo `json:"target"` // 探测目标信息

	// 探测源信息（可选）
	Source *SourceInfo `json:"source,omitempty"` // 探测源信息

	// 探测数据（类型特定）
	Data any `json:"data,omitempty"` // 探测结果数据，根据工具类型不同而不同

	// 错误信息
	Error *ErrorInfo `json:"error,omitempty"` // 错误信息，仅在 Success=false 时存在

	// 原始输出（调试用，可选）
	RawOutput string `json:"raw_output,omitempty"` // 原始命令输出，用于调试
}

// TargetInfo 探测目标信息
type TargetInfo struct {
	Domain   string `json:"domain,omitempty"`   // 目标域名
	IP       string `json:"ip,omitempty"`       // 目标 IP 地址
	Port     int    `json:"port,omitempty"`     // 目标端口
	URL      string `json:"url,omitempty"`      // 完整 URL (HTTP 探测)
	Protocol string `json:"protocol,omitempty"` // 协议: tcp, udp, http, https
}

// SourceInfo 探测源信息
type SourceInfo struct {
	ProbeID  string `json:"probe_id,omitempty"` // 探测源标识符
	IP       string `json:"ip,omitempty"`       // 探测源出口 IP
	Location string `json:"location,omitempty"` // 探测源位置
	ISP      string `json:"isp,omitempty"`      // 探测源 ISP
}

// ErrorInfo 结构化错误信息
type ErrorInfo struct {
	Code    string `json:"code"`              // 错误码 (预定义常量)
	Message string `json:"message"`           // 错误消息
	Details any    `json:"details,omitempty"` // 错误详情
}

// ============================================================================
// DNS Result Structure - DNS 解析结果结构
// ============================================================================

// DNSResult DNS 解析结果
// 包含完整的解析链路、TTL、DNS 服务器等信息
type DNSResult struct {
	// 解析链路 - 包括所有 CNAME 跳转
	ResolutionChain []DNSRecord `json:"resolution_chain"`

	// 最终解析的 IP 列表
	ResolvedIPs []string `json:"resolved_ips"`

	// 使用的 DNS 服务器
	DNSServer string `json:"dns_server"`

	// 解析耗时 (毫秒)
	ResolutionTimeMs float64 `json:"resolution_time_ms"`

	// 查询的记录类型: A, AAAA, CNAME, MX, NS, TXT, etc.
	QueryType string `json:"query_type"`
}

// DNSRecord DNS 记录
// 表示解析链路中的单条记录
type DNSRecord struct {
	// 记录名称 (域名)
	Name string `json:"name"`

	// 记录类型: A, AAAA, CNAME, MX, NS, TXT, etc.
	Type string `json:"type"`

	// 记录值: IP 地址、CNAME 目标、MX 主机等
	Value string `json:"value"`

	// TTL 值 (秒)
	TTL int `json:"ttl"`

	// MX 记录优先级 (仅 MX 记录有效)
	Priority int `json:"priority,omitempty"`
}

// ============================================================================
// TLS Result Structure - TLS 探测结果结构
// ============================================================================

// TLSResult TLS 探测结果
// 包含完整的证书信息、连接信息、时间分解和安全评估
type TLSResult struct {
	// 连接信息
	Connection TLSConnection `json:"connection"`

	// 证书信息
	Certificate CertificateInfo `json:"certificate"`

	// 时间分解
	Timing TLSTiming `json:"timing"`

	// 安全评估
	Security TLSSecurity `json:"security"`
}

// TLSConnection TLS 连接信息
type TLSConnection struct {
	// 协议版本: TLSv1.0, TLSv1.1, TLSv1.2, TLSv1.3
	Protocol string `json:"protocol"`

	// 协商使用的加密套件
	CipherSuite string `json:"cipher_suite"`

	// ALPN 协商的协议 (如 h2, http/1.1)
	ALPN string `json:"alpn,omitempty"`

	// SNI 服务器名称
	ServerName string `json:"server_name"`

	// 是否为双向 TLS (mTLS)
	IsMutualTLS bool `json:"is_mutual_tls"`

	// 支持的 TLS 协议版本列表
	SupportedVersions []string `json:"supported_versions,omitempty"`
}

// CertificateInfo 证书详细信息
type CertificateInfo struct {
	// 证书主题
	Subject CertSubject `json:"subject"`

	// 证书颁发者
	Issuer CertSubject `json:"issuer"`

	// 证书序列号
	SerialNumber string `json:"serial_number"`

	// 证书生效时间
	NotBefore time.Time `json:"not_before"`

	// 证书过期时间
	NotAfter time.Time `json:"not_after"`

	// 剩余有效天数
	DaysRemaining int `json:"days_remaining"`

	// 证书是否已过期
	IsExpired bool `json:"is_expired"`

	// 证书是否即将过期 (< 30 天)
	IsExpiringSoon bool `json:"is_expiring_soon"`

	// SHA256 指纹
	FingerprintSHA256 string `json:"fingerprint_sha256"`

	// 证书包含的 DNS 名称 (SAN)
	DNSNames []string `json:"dns_names"`

	// 密钥算法: RSA, ECDSA, Ed25519
	KeyAlgorithm string `json:"key_algorithm"`

	// 密钥长度 (bits)
	KeySize int `json:"key_size"`
}

// CertSubject 证书主题/颁发者信息
type CertSubject struct {
	// Common Name
	CommonName string `json:"cn"`

	// Organization
	Organization string `json:"o,omitempty"`

	// Organizational Unit
	OrganizationalUnit string `json:"ou,omitempty"`

	// Country
	Country string `json:"c,omitempty"`

	// State/Province
	State string `json:"st,omitempty"`

	// Locality
	Locality string `json:"l,omitempty"`
}

// TLSTiming TLS 连接时间分解
type TLSTiming struct {
	// TCP 连接耗时 (毫秒)
	TCPConnectMs float64 `json:"tcp_connect_ms"`

	// TLS 握手耗时 (毫秒)
	TLSHandshakeMs float64 `json:"tls_handshake_ms"`

	// 总耗时 (毫秒)
	TotalMs float64 `json:"total_ms"`
}

// TLSSecurity TLS 安全评估
type TLSSecurity struct {
	// 安全警告列表
	Warnings []string `json:"warnings,omitempty"`

	// 安全等级: A, B, C, F
	Grade string `json:"grade,omitempty"`
}

// ============================================================================
// HTTP Result Structure - HTTP 探测结果结构
// ============================================================================

// HTTPResult HTTP 探测结果
// 包含完整的请求信息、响应信息、时间分解和重定向链
type HTTPResult struct {
	// 请求信息
	Request HTTPRequest `json:"request"`

	// 响应信息
	Response HTTPResponse `json:"response"`

	// 时间分解
	Timing HTTPTiming `json:"timing"`

	// 重定向链（如有）
	Redirects []HTTPRedirect `json:"redirects,omitempty"`

	// 最终 URL（重定向后）
	FinalURL string `json:"final_url,omitempty"`
}

// HTTPRequest HTTP 请求信息
type HTTPRequest struct {
	// 请求方法: GET, POST, PUT, DELETE, etc.
	Method string `json:"method"`

	// 请求 URL
	URL string `json:"url"`

	// 请求头
	Headers map[string]string `json:"headers,omitempty"`

	// 请求体（截断）
	BodySnippet string `json:"body_snippet,omitempty"`
}

// HTTPResponse HTTP 响应信息
type HTTPResponse struct {
	// HTTP 状态码
	StatusCode int `json:"status_code"`

	// 状态文本: OK, Not Found, etc.
	StatusText string `json:"status_text"`

	// 响应头（关键字段）
	Headers map[string]string `json:"headers"`

	// Content-Type
	ContentType string `json:"content_type"`

	// Content-Length (字节)
	ContentLength int64 `json:"content_length"`

	// Content-Encoding: gzip, br, deflate, etc.
	ContentEncoding string `json:"content_encoding,omitempty"`

	// Server 头
	Server string `json:"server,omitempty"`

	// HTTP 协议版本: HTTP/1.1, HTTP/2, etc.
	Protocol string `json:"protocol"`

	// 响应体片段（截断）
	BodySnippet string `json:"body_snippet,omitempty"`

	// 响应体大小（实际读取的字节数）
	BodySize int64 `json:"body_size"`

	// 是否压缩
	IsCompressed bool `json:"is_compressed"`
}

// HTTPTiming HTTP 请求时间分解
type HTTPTiming struct {
	// DNS 解析耗时 (毫秒)
	DNSLookupMs float64 `json:"dns_lookup_ms"`

	// TCP 连接耗时 (毫秒)
	TCPConnectMs float64 `json:"tcp_connect_ms"`

	// TLS 握手耗时 (毫秒)，非 HTTPS 时为 0
	TLSHandshakeMs float64 `json:"tls_handshake_ms"`

	// 请求发送耗时 (毫秒)
	RequestSentMs float64 `json:"request_sent_ms"`

	// 等待响应耗时 (毫秒) - 服务器处理时间
	WaitingMs float64 `json:"waiting_ms"`

	// 内容传输耗时 (毫秒)
	ContentTransferMs float64 `json:"content_transfer_ms"`

	// 总耗时 (毫秒)
	TotalMs float64 `json:"total_ms"`
}

// HTTPRedirect HTTP 重定向记录
type HTTPRedirect struct {
	// 重定向序号（从 1 开始）
	Index int `json:"index"`

	// 原始 URL
	FromURL string `json:"from_url"`

	// 重定向状态码: 301, 302, 303, 307, 308
	StatusCode int `json:"status_code"`

	// 重定向目标 URL (Location 头)
	Location string `json:"location"`
}

// ============================================================================
// MTR Result Structure - MTR 探测结果结构
// ============================================================================

// MTRResult MTR 探测结果
// 包含结构化的跳点数据和汇总统计
type MTRResult struct {
	// 跳点列表
	Hops []MTRHop `json:"hops"`

	// 汇总统计
	Summary MTRSummary `json:"summary"`
}

// MTRHop MTR 单跳信息
// 表示路径中的单个网络跳点
type MTRHop struct {
	// 跳数（从 1 开始）
	HopNumber int `json:"hop_number"`

	// 跳点 IP 地址
	IP string `json:"ip"`

	// 跳点主机名（如果可解析）
	Hostname string `json:"hostname,omitempty"`

	// 发送的探测包数量
	PacketsSent int `json:"packets_sent"`

	// 接收的响应包数量
	PacketsRecv int `json:"packets_recv"`

	// 丢包率（百分比，0-100）
	LossPercent float64 `json:"loss_percent"`

	// 延迟统计（毫秒）
	LatencyMs LatencyStats `json:"latency_ms"`

	// 是否超时（无响应）
	IsTimeout bool `json:"is_timeout"`

	// 是否高丢包（> 20%）
	IsHighLoss bool `json:"is_high_loss"`
}

// LatencyStats 延迟统计信息
type LatencyStats struct {
	// 最小延迟（毫秒）
	Min float64 `json:"min"`

	// 最大延迟（毫秒）
	Max float64 `json:"max"`

	// 平均延迟（毫秒）
	Avg float64 `json:"avg"`

	// 标准差（毫秒）
	StdDev float64 `json:"std_dev"`

	// 最后一次延迟（毫秒）
	Last float64 `json:"last,omitempty"`
}

// MTRSummary MTR 汇总统计
type MTRSummary struct {
	// 总跳数
	TotalHops int `json:"total_hops"`

	// 是否到达目标
	TargetReached bool `json:"target_reached"`

	// 平均延迟（毫秒）- 最后一跳的平均延迟
	AvgLatencyMs float64 `json:"avg_latency_ms"`

	// 整体丢包率（百分比）- 最后一跳的丢包率
	OverallLossPercent float64 `json:"overall_loss_percent"`

	// 高丢包跳点列表（跳数）
	HighLossHops []int `json:"high_loss_hops,omitempty"`

	// 超时跳点列表（跳数）
	TimeoutHops []int `json:"timeout_hops,omitempty"`
}

// HighLossThreshold 高丢包阈值（百分比）
const HighLossThreshold = 20.0

// ============================================================================
// Diagnose Result Structure - 综合诊断结果结构
// ============================================================================

// DiagnoseResult 综合诊断结果
// 包含 DNS → TCP → TLS → HTTP 完整探测链的结果
type DiagnoseResult struct {
	// 目标信息
	Target DiagnoseTarget `json:"target"`

	// DNS 解析结果
	DNS *DNSResult `json:"dns,omitempty"`

	// TCP 连接结果（多 IP 时为数组）
	TCP []TCPResult `json:"tcp,omitempty"`

	// TLS 探测结果
	TLS *TLSResult `json:"tls,omitempty"`

	// HTTP 探测结果
	HTTP *HTTPResult `json:"http,omitempty"`

	// MTR 探测结果
	MTR *MTRResult `json:"mtr,omitempty"`

	// 汇总信息
	Summary DiagnoseSummary `json:"summary"`

	// 诊断建议
	Recommendations []string `json:"recommendations,omitempty"`
}

// DiagnoseTarget 诊断目标信息
type DiagnoseTarget struct {
	// 用户原始输入
	Input string `json:"input"`

	// 解析出的域名
	Domain string `json:"domain"`

	// 目标端口
	Port int `json:"port"`

	// 协议: http, https, tcp
	Protocol string `json:"protocol"`
}

// DiagnoseSummary 诊断汇总信息
type DiagnoseSummary struct {
	// 整体状态: success, partial, failed
	OverallStatus string `json:"overall_status"`

	// 总耗时（毫秒）
	TotalDurationMs float64 `json:"total_duration_ms"`

	// 推荐使用的 IP（连接最快的）
	RecommendedIP string `json:"recommended_ip,omitempty"`

	// 证书状态: valid, expiring_soon, expired, invalid
	CertStatus string `json:"cert_status,omitempty"`

	// 发现的问题列表
	Issues []string `json:"issues,omitempty"`

	// 各阶段状态
	StageStatus map[string]string `json:"stage_status,omitempty"`
}

// TCPResult TCP 连接探测结果
type TCPResult struct {
	// 目标 IP
	IP string `json:"ip"`

	// 目标端口
	Port int `json:"port"`

	// 是否连接成功
	Success bool `json:"success"`

	// 连接耗时（毫秒）
	ConnectTimeMs float64 `json:"connect_time_ms"`

	// 错误信息（如果失败）
	Error *ErrorInfo `json:"error,omitempty"`
}

// DiagnoseOptions 诊断命令选项
type DiagnoseOptions struct {
	// 目标（域名或 URL）
	Target string

	// 端口（默认 443）
	Port int

	// 超时时间（秒）
	TimeoutSec int

	// 跳过的步骤: dns, tcp, tls, http, mtr
	Skip []string

	// 是否并行探测多 IP
	Parallel bool

	// 是否执行 MTR
	IncludeMTR bool

	// 是否执行 HTTP 探测
	IncludeHTTP bool

	// 工具标识
	Tool string
}

// DiagnoseStage 诊断阶段常量
const (
	StageDNS  = "dns"
	StageTCP  = "tcp"
	StageTLS  = "tls"
	StageHTTP = "http"
	StageMTR  = "mtr"
)

// DiagnoseStatus 诊断状态常量
const (
	StatusSuccess = "success"
	StatusPartial = "partial"
	StatusFailed  = "failed"
	StatusSkipped = "skipped"
)

// CertStatus 证书状态常量
const (
	CertStatusValid       = "valid"
	CertStatusExpiringSoon = "expiring_soon"
	CertStatusExpired     = "expired"
	CertStatusInvalid     = "invalid"
)

// ============================================================================
// Legacy Result Structure - 保留旧结构以保持兼容性
// ============================================================================

// Result 定义统一的输出结构，便于 JSON 序列化后由 Python MCP 直接透传。
// Deprecated: 请使用 UnifiedResult 替代
type Result struct {
	Success      bool           `json:"success"`
	Tool         string         `json:"tool,omitempty"`
	Error        string         `json:"error,omitempty"`
	Target       string         `json:"target,omitempty"`
	Host         string         `json:"host,omitempty"`
	Port         int            `json:"port,omitempty"`
	URL          string         `json:"url,omitempty"`
	RecordType   string         `json:"record_type,omitempty"`
	Count        int            `json:"count,omitempty"`
	MaxHops      int            `json:"max_hops,omitempty"`
	ReportCycles int            `json:"report_cycles,omitempty"`
	LatencyMs    float64        `json:"latency_ms,omitempty"`
	StatusCode   int            `json:"status_code,omitempty"`
	Protocol     string         `json:"protocol,omitempty"`
	Cipher       string         `json:"cipher,omitempty"`
	RawOutput    any            `json:"raw_output,omitempty"`
	Summary      map[string]any `json:"summary,omitempty"`
	Details      map[string]any `json:"details,omitempty"`
}

// ============================================================================
// Helper Functions - 辅助函数
// ============================================================================

// NewUnifiedResult 创建一个新的统一结果结构
func NewUnifiedResult(tool string, target TargetInfo) *UnifiedResult {
	return &UnifiedResult{
		Tool:      tool,
		Success:   false,
		Timestamp: time.Now(),
		Target:    target,
	}
}

// SetSuccess 设置探测成功
func (r *UnifiedResult) SetSuccess(durationMs float64, data any) {
	r.Success = true
	r.DurationMs = durationMs
	r.Data = data
}

// SetError 设置探测失败
func (r *UnifiedResult) SetError(code, message string, details any) {
	r.Success = false
	r.Error = &ErrorInfo{
		Code:    code,
		Message: message,
		Details: details,
	}
}

// SetSource 设置探测源信息
func (r *UnifiedResult) SetSource(probeID, ip, location, isp string) {
	r.Source = &SourceInfo{
		ProbeID:  probeID,
		IP:       ip,
		Location: location,
		ISP:      isp,
	}
}

type PingOptions struct {
	Target     string
	Count      int
	TimeoutSec int
	Tool       string
}

type TraceOptions struct {
	Target     string
	MaxHops    int
	TimeoutSec int
	Tool       string
}

type MtrOptions struct {
	Target       string
	Count        int
	ReportCycles int
	TimeoutSec   int
	Tool         string
}

type NslookupOptions struct {
	Target     string
	RecordType string
	TimeoutSec int
	Tool       string
}

type TCPOptions struct {
	Host       string
	Port       int
	TimeoutSec int
	Retry      int
	Tool       string
}

type TLSOptions struct {
	Host       string
	Port       int
	ServerName string
	TimeoutSec int
	Insecure   bool
	CACert     string
	ClientCert string
	ClientKey  string
	Tool       string
}

type HTTPOptions struct {
	URL            string
	Method         string
	Headers        map[string]string
	Body           string
	TimeoutSec     int
	ExpectStatus   int
	ExpectContains string
	Tool           string
}
