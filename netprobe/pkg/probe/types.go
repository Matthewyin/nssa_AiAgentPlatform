package probe

// Result 定义统一的输出结构，便于 JSON 序列化后由 Python MCP 直接透传。
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
