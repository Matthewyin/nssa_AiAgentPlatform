# Design Document: Network Probe Optimization

## Overview

本设计文档描述网络探测工具（netprobe）和 MCP Server 的优化方案。核心目标是：
1. 增强各探测命令的输出结构，提供更丰富的诊断信息
2. 统一所有探测结果的 JSON 格式，便于后续处理和存储
3. 新增综合诊断命令，支持一键完成完整探测链
4. 增强 MCP Server 的参数验证和批量探测能力

## Architecture

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        LLM Agent (ReAct)                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Server (Python)                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Tool Registry                                           │   │
│  │  ├── Parameter Validation                                │   │
│  │  ├── Batch Execution Support                             │   │
│  │  └── Audit Logging                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Netprobe CLI (Go)                          │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐      │
│  │   ping   │   tcp    │   tls    │   http   │ diagnose │      │
│  ├──────────┼──────────┼──────────┼──────────┼──────────┤      │
│  │   mtr    │ nslookup │  trace   │          │          │      │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Unified Result Structure                                │   │
│  │  ├── BaseResult (tool, success, timestamp, duration)     │   │
│  │  ├── TargetInfo (domain, ip, port, url)                  │   │
│  │  ├── ProbeData (type-specific structured data)           │   │
│  │  └── ErrorInfo (code, message, details)                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### diagnose 命令流程

```
diagnose --target example.com --port 443

    ┌─────────────┐
    │  DNS 解析   │ → resolved_ips: [1.2.3.4, 1.2.3.5]
    └──────┬──────┘
           │
           ▼ (for each IP, parallel if --parallel)
    ┌─────────────┐
    │  TCP 探测   │ → connect_time_ms, success
    └──────┬──────┘
           │
           ▼ (if port 443 or --tls)
    ┌─────────────┐
    │  TLS 探测   │ → cert_info, handshake_time_ms
    └──────┬──────┘
           │
           ▼ (if --http or URL input)
    ┌─────────────┐
    │  HTTP 探测  │ → status_code, timing_breakdown
    └──────┬──────┘
           │
           ▼ (if --mtr)
    ┌─────────────┐
    │  MTR 探测   │ → hops[], packet_loss
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │  汇总报告   │ → summary, recommendations
    └─────────────┘
```

## Components and Interfaces

### 1. Netprobe CLI 增强

#### 1.1 统一结果结构 (types.go)

```go
// UnifiedResult 统一的探测结果结构
type UnifiedResult struct {
    // 基础信息
    Tool       string    `json:"tool"`
    Success    bool      `json:"success"`
    Timestamp  time.Time `json:"timestamp"`
    DurationMs float64   `json:"duration_ms"`
    
    // 目标信息
    Target     TargetInfo `json:"target"`
    
    // 探测源信息（可选）
    Source     *SourceInfo `json:"source,omitempty"`
    
    // 探测数据（类型特定）
    Data       any        `json:"data,omitempty"`
    
    // 错误信息
    Error      *ErrorInfo `json:"error,omitempty"`
    
    // 原始输出（调试用，可选）
    RawOutput  string     `json:"raw_output,omitempty"`
}

type TargetInfo struct {
    Domain   string `json:"domain,omitempty"`
    IP       string `json:"ip,omitempty"`
    Port     int    `json:"port,omitempty"`
    URL      string `json:"url,omitempty"`
    Protocol string `json:"protocol,omitempty"`
}

type SourceInfo struct {
    ProbeID  string `json:"probe_id,omitempty"`
    IP       string `json:"ip,omitempty"`
    Location string `json:"location,omitempty"`
    ISP      string `json:"isp,omitempty"`
}

type ErrorInfo struct {
    Code    string `json:"code"`
    Message string `json:"message"`
    Details any    `json:"details,omitempty"`
}
```

#### 1.2 DNS 解析结果结构

```go
type DNSResult struct {
    // 解析链路
    ResolutionChain []DNSRecord `json:"resolution_chain"`
    
    // 最终解析的 IP 列表
    ResolvedIPs []string `json:"resolved_ips"`
    
    // 使用的 DNS 服务器
    DNSServer string `json:"dns_server"`
    
    // 解析耗时
    ResolutionTimeMs float64 `json:"resolution_time_ms"`
    
    // 查询的记录类型
    QueryType string `json:"query_type"`
}

type DNSRecord struct {
    Name       string `json:"name"`
    Type       string `json:"type"`       // A, AAAA, CNAME, MX, etc.
    Value      string `json:"value"`
    TTL        int    `json:"ttl"`
    Priority   int    `json:"priority,omitempty"` // for MX
}
```

#### 1.3 TLS 探测结果结构

```go
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

type TLSConnection struct {
    Protocol    string   `json:"protocol"`      // TLSv1.2, TLSv1.3
    CipherSuite string   `json:"cipher_suite"`
    ALPN        string   `json:"alpn,omitempty"`
    ServerName  string   `json:"server_name"`
    IsMutualTLS bool     `json:"is_mutual_tls"`
}

type CertificateInfo struct {
    Subject       CertSubject `json:"subject"`
    Issuer        CertSubject `json:"issuer"`
    SerialNumber  string      `json:"serial_number"`
    NotBefore     time.Time   `json:"not_before"`
    NotAfter      time.Time   `json:"not_after"`
    DaysRemaining int         `json:"days_remaining"`
    IsExpired     bool        `json:"is_expired"`
    IsExpiringSoon bool       `json:"is_expiring_soon"` // < 30 days
    Fingerprint   string      `json:"fingerprint_sha256"`
    DNSNames      []string    `json:"dns_names"`
    KeyAlgorithm  string      `json:"key_algorithm"`
    KeySize       int         `json:"key_size"`
}

type CertSubject struct {
    CommonName   string `json:"cn"`
    Organization string `json:"o,omitempty"`
    Country      string `json:"c,omitempty"`
}

type TLSTiming struct {
    TCPConnectMs    float64 `json:"tcp_connect_ms"`
    TLSHandshakeMs  float64 `json:"tls_handshake_ms"`
    TotalMs         float64 `json:"total_ms"`
}

type TLSSecurity struct {
    Warnings []string `json:"warnings,omitempty"`
    Grade    string   `json:"grade,omitempty"` // A, B, C, F
}
```

#### 1.4 HTTP 探测结果结构

```go
type HTTPResult struct {
    // 请求信息
    Request HTTPRequest `json:"request"`
    
    // 响应信息
    Response HTTPResponse `json:"response"`
    
    // 时间分解
    Timing HTTPTiming `json:"timing"`
    
    // 重定向链（如有）
    Redirects []HTTPRedirect `json:"redirects,omitempty"`
}

type HTTPRequest struct {
    Method  string            `json:"method"`
    URL     string            `json:"url"`
    Headers map[string]string `json:"headers,omitempty"`
}

type HTTPResponse struct {
    StatusCode      int               `json:"status_code"`
    StatusText      string            `json:"status_text"`
    Headers         map[string]string `json:"headers"`
    ContentType     string            `json:"content_type"`
    ContentLength   int64             `json:"content_length"`
    ContentEncoding string            `json:"content_encoding,omitempty"`
    Server          string            `json:"server,omitempty"`
    BodySnippet     string            `json:"body_snippet,omitempty"`
}

type HTTPTiming struct {
    DNSLookupMs       float64 `json:"dns_lookup_ms"`
    TCPConnectMs      float64 `json:"tcp_connect_ms"`
    TLSHandshakeMs    float64 `json:"tls_handshake_ms"`
    RequestSentMs     float64 `json:"request_sent_ms"`
    WaitingMs         float64 `json:"waiting_ms"`
    ContentTransferMs float64 `json:"content_transfer_ms"`
    TotalMs           float64 `json:"total_ms"`
}

type HTTPRedirect struct {
    StatusCode int    `json:"status_code"`
    Location   string `json:"location"`
}
```

#### 1.5 MTR 探测结果结构

```go
type MTRResult struct {
    // 跳点列表
    Hops []MTRHop `json:"hops"`
    
    // 汇总统计
    Summary MTRSummary `json:"summary"`
}

type MTRHop struct {
    HopNumber    int     `json:"hop_number"`
    IP           string  `json:"ip"`
    Hostname     string  `json:"hostname,omitempty"`
    PacketsSent  int     `json:"packets_sent"`
    PacketsRecv  int     `json:"packets_recv"`
    LossPercent  float64 `json:"loss_percent"`
    LatencyMs    LatencyStats `json:"latency_ms"`
    IsTimeout    bool    `json:"is_timeout"`
    IsHighLoss   bool    `json:"is_high_loss"` // > 20%
}

type LatencyStats struct {
    Min    float64 `json:"min"`
    Max    float64 `json:"max"`
    Avg    float64 `json:"avg"`
    StdDev float64 `json:"std_dev"`
}

type MTRSummary struct {
    TotalHops       int     `json:"total_hops"`
    TargetReached   bool    `json:"target_reached"`
    AvgLatencyMs    float64 `json:"avg_latency_ms"`
    OverallLossPercent float64 `json:"overall_loss_percent"`
    HighLossHops    []int   `json:"high_loss_hops,omitempty"`
}
```

#### 1.6 Diagnose 综合诊断结果结构

```go
type DiagnoseResult struct {
    // 目标信息
    Target DiagnoseTarget `json:"target"`
    
    // 各阶段探测结果
    DNS  *DNSResult  `json:"dns,omitempty"`
    TCP  []TCPResult `json:"tcp,omitempty"`  // 多 IP
    TLS  *TLSResult  `json:"tls,omitempty"`
    HTTP *HTTPResult `json:"http,omitempty"`
    MTR  *MTRResult  `json:"mtr,omitempty"`
    
    // 汇总
    Summary DiagnoseSummary `json:"summary"`
    
    // 建议
    Recommendations []string `json:"recommendations,omitempty"`
}

type DiagnoseTarget struct {
    Input    string `json:"input"`     // 用户输入
    Domain   string `json:"domain"`
    Port     int    `json:"port"`
    Protocol string `json:"protocol"`
}

type DiagnoseSummary struct {
    OverallStatus   string  `json:"overall_status"` // success, partial, failed
    TotalDurationMs float64 `json:"total_duration_ms"`
    RecommendedIP   string  `json:"recommended_ip,omitempty"`
    CertStatus      string  `json:"cert_status,omitempty"`
    Issues          []string `json:"issues,omitempty"`
}
```

### 2. MCP Server 增强

#### 2.1 参数验证

```python
class ParameterValidator:
    """参数验证器"""
    
    def validate(self, tool_name: str, arguments: dict) -> ValidationResult:
        """验证工具参数"""
        tool_config = TOOL_CONFIG_MAP.get(tool_name)
        if not tool_config:
            return ValidationResult(valid=False, error=f"Unknown tool: {tool_name}")
        
        errors = []
        for param_name, param_config in tool_config.get("parameters", {}).items():
            if param_config.get("required") and param_name not in arguments:
                errors.append(f"Missing required parameter: {param_name}")
            
            if param_name in arguments:
                value = arguments[param_name]
                # 类型检查
                expected_type = param_config.get("type")
                if not self._check_type(value, expected_type):
                    errors.append(f"Invalid type for {param_name}: expected {expected_type}")
                
                # 枚举检查
                if "enum" in param_config and value not in param_config["enum"]:
                    errors.append(f"Invalid value for {param_name}: must be one of {param_config['enum']}")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
```

#### 2.2 批量探测支持

```python
async def batch_probe(self, tool_name: str, targets: list, common_args: dict) -> list:
    """批量执行探测"""
    tasks = []
    for target in targets:
        args = {**common_args, "target": target}
        tasks.append(self._run_single_probe(tool_name, args))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        {"target": t, "result": r if not isinstance(r, Exception) else {"error": str(r)}}
        for t, r in zip(targets, results)
    ]
```

#### 2.3 审计日志

```python
class AuditLogger:
    """工具调用审计日志"""
    
    async def log_call(self, tool_name: str, arguments: dict, result: dict, duration_ms: float):
        """记录工具调用"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "tool": tool_name,
            "arguments": self._sanitize_args(arguments),
            "success": result.get("success", False),
            "duration_ms": duration_ms,
            "error": result.get("error"),
        }
        logger.info(f"Tool call: {json.dumps(log_entry)}")
```

## Data Models

### 错误码定义

| 错误码 | 含义 | 适用场景 |
|--------|------|----------|
| `DNS_TIMEOUT` | DNS 解析超时 | nslookup |
| `DNS_NXDOMAIN` | 域名不存在 | nslookup |
| `DNS_SERVFAIL` | DNS 服务器错误 | nslookup |
| `TCP_TIMEOUT` | TCP 连接超时 | tcp, tls, http |
| `TCP_REFUSED` | 连接被拒绝 | tcp, tls, http |
| `TCP_UNREACHABLE` | 目标不可达 | tcp, tls, http |
| `TLS_HANDSHAKE_FAILED` | TLS 握手失败 | tls, http |
| `TLS_CERT_EXPIRED` | 证书已过期 | tls, http |
| `TLS_CERT_INVALID` | 证书无效 | tls, http |
| `HTTP_TIMEOUT` | HTTP 请求超时 | http |
| `HTTP_ERROR` | HTTP 错误响应 | http |
| `COMMAND_NOT_FOUND` | 系统命令不存在 | ping, mtr, traceroute |
| `PERMISSION_DENIED` | 权限不足 | mtr |



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: DNS 成功结果包含必要字段

*For any* 成功的 DNS 解析结果，结果 JSON 应包含 `resolution_chain`（数组）、`resolved_ips`（数组）、`dns_server`（字符串）、`resolution_time_ms`（正数）字段，且 `resolution_chain` 中每条记录包含 `name`、`type`、`value`、`ttl` 字段。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: DNS 失败结果包含结构化错误

*For any* 失败的 DNS 解析结果，结果 JSON 应包含 `error` 对象，其中 `code` 字段为预定义错误码之一（DNS_TIMEOUT、DNS_NXDOMAIN、DNS_SERVFAIL 等），`message` 字段为非空字符串。

**Validates: Requirements 1.5**

### Property 3: TLS 结果包含完整证书和连接信息

*For any* 成功的 TLS 探测结果，结果 JSON 应包含：
- `connection` 对象：包含 `protocol`、`cipher_suite`、`is_mutual_tls` 字段
- `certificate` 对象：包含 `subject.cn`、`issuer`、`not_before`、`not_after`、`days_remaining`、`fingerprint_sha256` 字段
- `timing` 对象：包含 `tcp_connect_ms`、`tls_handshake_ms`、`total_ms` 字段

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 2.8**

### Property 4: 证书即将过期时标记警告

*For any* TLS 探测结果，当 `certificate.days_remaining < 30` 时，`certificate.is_expiring_soon` 应为 `true`，且 `security.warnings` 数组应包含过期警告信息。

**Validates: Requirements 2.9**

### Property 5: HTTP 结果包含完整响应和时间分解

*For any* 成功的 HTTP 探测结果，结果 JSON 应包含：
- `response` 对象：包含 `status_code`、`headers`、`content_type`、`content_length` 字段
- `timing` 对象：包含 `dns_lookup_ms`、`tcp_connect_ms`、`tls_handshake_ms`、`waiting_ms`、`content_transfer_ms`、`total_ms` 字段

**Validates: Requirements 3.1, 3.2, 3.4, 3.5**

### Property 6: HTTP 重定向链完整记录

*For any* 发生重定向的 HTTP 探测结果，`redirects` 数组应包含每次重定向的 `status_code` 和 `location` 字段，且数组长度等于实际重定向次数。

**Validates: Requirements 3.3, 3.6**

### Property 7: MTR 结果包含结构化跳点和汇总数据

*For any* 成功的 MTR 探测结果，结果 JSON 应包含：
- `hops` 数组：每个元素包含 `hop_number`、`ip`、`loss_percent`、`latency_ms`（含 min/max/avg/std_dev）字段
- `summary` 对象：包含 `total_hops`、`target_reached`、`avg_latency_ms`、`overall_loss_percent` 字段

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 8: MTR 高丢包跳点正确标识

*For any* MTR 探测结果中的跳点，当 `loss_percent > 20` 时，`is_high_loss` 应为 `true`；当跳点无响应时，`is_timeout` 应为 `true` 且该跳点不应被省略。

**Validates: Requirements 4.4, 4.5**

### Property 9: 所有探测结果符合统一结构

*For any* 探测结果（ping、tcp、tls、http、nslookup、mtr、traceroute、diagnose），结果 JSON 应包含 `tool`（字符串）、`success`（布尔）、`timestamp`（ISO8601 格式）、`duration_ms`（正数）、`target`（对象）字段。

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 10: 失败探测结果包含结构化错误

*For any* 失败的探测结果，结果 JSON 应包含 `error` 对象，其中 `code` 字段为预定义错误码之一，`message` 字段为非空字符串。

**Validates: Requirements 5.4**

### Property 11: MCP Server 参数验证

*For any* 缺少必填参数的工具调用，MCP Server 应返回包含 `success: false` 和明确错误信息的结果，错误信息应指明缺少的参数名称。

**Validates: Requirements 6.2**

### Property 12: MCP Server 批量探测

*For any* 批量探测请求（包含 N 个目标），MCP Server 应返回包含 N 个结果的数组，每个结果包含对应目标的探测数据或错误信息。

**Validates: Requirements 6.4**

### Property 13: diagnose 返回完整综合诊断报告

*For any* diagnose 命令执行结果，结果 JSON 应包含 `target`、`dns`、`tcp`、`summary` 字段；当目标端口为 443 时，还应包含 `tls` 字段；`summary` 应包含 `overall_status` 和 `total_duration_ms` 字段。

**Validates: Requirements 7.1, 7.2, 7.3, 7.6**

### Property 14: diagnose --skip 参数正确跳过步骤

*For any* 使用 `--skip <step>` 参数的 diagnose 命令，结果 JSON 不应包含被跳过步骤对应的字段（如 `--skip tls` 时不应有 `tls` 字段）。

**Validates: Requirements 7.4**

### Property 15: --probe-id 参数正确传递

*For any* 使用 `--probe-id <id>` 参数的探测命令，结果 JSON 应包含 `source.probe_id` 字段，其值等于传入的 id。

**Validates: Requirements 8.1**

## Error Handling

### 错误分类

1. **网络错误**：连接超时、连接拒绝、DNS 解析失败
2. **协议错误**：TLS 握手失败、HTTP 错误响应
3. **系统错误**：命令不存在、权限不足
4. **参数错误**：缺少必填参数、参数格式错误

### 错误处理策略

1. **优雅降级**：部分探测失败时，返回已成功的结果
2. **详细错误信息**：包含错误码、错误消息、可能的原因
3. **超时处理**：超时时返回部分结果（如有）
4. **重试机制**：TCP 探测支持 --retry 参数

## Testing Strategy

### 单元测试

1. **结构验证测试**：验证各探测结果的 JSON 结构符合定义
2. **错误处理测试**：验证各种错误场景返回正确的错误码
3. **参数解析测试**：验证 CLI 参数正确解析
4. **边界条件测试**：空输入、超长输入、特殊字符

### 属性测试

使用 Go 的 `testing/quick` 或 `gopter` 库进行属性测试：

1. **结构一致性属性**：所有探测结果符合统一结构
2. **字段完整性属性**：成功结果包含所有必要字段
3. **错误结构属性**：失败结果包含结构化错误信息
4. **条件逻辑属性**：证书过期警告、高丢包标识等

### 集成测试

1. **端到端测试**：MCP Server → Netprobe → 结果解析
2. **批量探测测试**：验证批量探测的并发和结果聚合
3. **超时测试**：验证超时处理和部分结果返回

### 测试配置

- 属性测试最少运行 100 次迭代
- 每个属性测试标注对应的设计属性编号
- 标签格式：`Feature: network-probe-optimization, Property N: <property_text>`


## Open WebUI 展示适配

### 问题分析

Open WebUI 只能渲染 Markdown 格式的 `message.content`，无法识别自定义的 JSON 结构。因此需要在 Graph Service 层增加一个 **Markdown 转换器**，将结构化的探测结果转换为可读的 Markdown 格式。

### 架构补充

```
┌─────────────────────────────────────────────────────────────────┐
│                        Open WebUI                               │
│                    (只渲染 Markdown)                            │
└─────────────────────────────────────────────────────────────────┘
                                ▲
                                │ Markdown (answer)
┌─────────────────────────────────────────────────────────────────┐
│                     Graph Service                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ResultToMarkdown Converter (新增)                       │   │
│  │  ├── DNS 结果 → 解析链表格 + 统计                        │   │
│  │  ├── TLS 结果 → 证书卡片 + 时间分解                      │   │
│  │  ├── HTTP 结果 → 响应摘要 + 时间条形图                   │   │
│  │  ├── MTR 结果 → 跳点表格 + 丢包标识                      │   │
│  │  └── Diagnose 结果 → 综合报告 + 建议                     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                ▲
                                │ JSON (structured)
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Server + Netprobe                       │
└─────────────────────────────────────────────────────────────────┘
```

### Markdown 转换规则

#### DNS 结果转换

```markdown
## 🔍 DNS 解析结果

**目标域名**: example.com  
**DNS 服务器**: 8.8.8.8  
**解析耗时**: 45.2ms

### 解析链路
| 步骤 | 类型 | 值 | TTL |
|------|------|-----|-----|
| 1 | CNAME | cdn.example.com | 300 |
| 2 | A | 1.2.3.4 | 60 |

**最终 IP**: 1.2.3.4
```

#### TLS 结果转换

```markdown
## 🔒 TLS 证书信息

### 证书详情
| 字段 | 值 |
|------|-----|
| 域名 (CN) | *.example.com |
| 颁发者 | DigiCert Inc |
| 有效期 | 2024-01-01 ~ 2025-01-01 |
| 剩余天数 | 180 天 ✅ |
| 指纹 (SHA256) | `abc123...` |

### 连接信息
- **协议**: TLSv1.3
- **加密套件**: TLS_AES_256_GCM_SHA384
- **双向认证**: 否

### ⏱️ 时间分解
| 阶段 | 耗时 |
|------|------|
| TCP 连接 | 35.2ms |
| TLS 握手 | 78.5ms |
| **总计** | **113.7ms** |
```

#### HTTP 结果转换

```markdown
## 🌐 HTTP 探测结果

**请求**: GET https://example.com/api  
**状态**: 200 OK ✅

### 响应信息
| 字段 | 值 |
|------|-----|
| Content-Type | application/json |
| Content-Length | 1234 bytes |
| Server | nginx/1.18.0 |
| 压缩 | gzip |

### ⏱️ 时间分解
```
DNS 解析  ██░░░░░░░░░░░░░░░░░░  12.3ms (8%)
TCP 连接  ████░░░░░░░░░░░░░░░░  35.2ms (23%)
TLS 握手  ████████░░░░░░░░░░░░  78.5ms (51%)
等待响应  ██░░░░░░░░░░░░░░░░░░  15.6ms (10%)
内容传输  ██░░░░░░░░░░░░░░░░░░  12.1ms (8%)
──────────────────────────────────
总计: 153.7ms
```
```

#### MTR 结果转换

```markdown
## 🛤️ 网络路径追踪 (MTR)

**目标**: 1.2.3.4  
**总跳数**: 12  
**平均延迟**: 45.6ms  
**整体丢包**: 2.5%

### 路径详情
| 跳数 | IP | 丢包率 | 延迟 (avg) | 状态 |
|------|-----|--------|------------|------|
| 1 | 192.168.1.1 | 0% | 1.2ms | ✅ |
| 2 | 10.0.0.1 | 0% | 5.3ms | ✅ |
| 3 | * | 100% | - | ⏱️ 超时 |
| 4 | 202.97.33.1 | 25% | 35.2ms | ⚠️ 高丢包 |
| ... | ... | ... | ... | ... |
| 12 | 1.2.3.4 | 0% | 45.6ms | ✅ 目标 |

⚠️ **注意**: 第 4 跳丢包率较高 (25%)，可能存在网络拥塞
```

#### Diagnose 综合报告转换

```markdown
## 📊 网络诊断报告

**目标**: https://example.com  
**诊断时间**: 2024-01-15 10:30:00  
**总耗时**: 2.5s

### 📋 诊断摘要
| 项目 | 状态 | 详情 |
|------|------|------|
| DNS 解析 | ✅ 成功 | 45.2ms, 解析到 1.2.3.4 |
| TCP 连接 | ✅ 成功 | 35.2ms |
| TLS 握手 | ✅ 成功 | 78.5ms, TLSv1.3 |
| HTTP 响应 | ✅ 200 OK | 153.7ms |
| 证书状态 | ✅ 有效 | 剩余 180 天 |

### 💡 建议
- ✅ 网络连接正常
- ⭐ 推荐 IP: 1.2.3.4 (连接最快)

<details>
<summary>📋 查看详细数据</summary>

[展开显示各阶段详细信息...]

</details>
```

### 实现位置

在 `graph_service/report_builder/` 目录下新增：

```
graph_service/
└── report_builder/
    ├── __init__.py
    ├── markdown_converter.py    # Markdown 转换器
    └── converters/
        ├── __init__.py
        ├── dns_converter.py
        ├── tls_converter.py
        ├── http_converter.py
        ├── mtr_converter.py
        └── diagnose_converter.py
```

### 转换器接口

```python
class MarkdownConverter:
    """将结构化探测结果转换为 Markdown"""
    
    def convert(self, tool_name: str, result: dict) -> str:
        """根据工具类型选择对应的转换器"""
        converter = self._get_converter(tool_name)
        return converter.to_markdown(result)
    
    def _get_converter(self, tool_name: str):
        converters = {
            "network.nslookup": DNSConverter(),
            "network.tls": TLSConverter(),
            "network.http": HTTPConverter(),
            "network.mtr": MTRConverter(),
            "network.diagnose": DiagnoseConverter(),
            # ping, tcp, traceroute 使用通用转换器
        }
        return converters.get(tool_name, GenericConverter())
```

### 集成点

在 `react_observe.py` 或 `final_answer_node.py` 中调用转换器：

```python
# 工具执行后
tool_result = await execute_tool(tool_name, arguments)

# 转换为 Markdown（用于 Open WebUI 显示）
markdown_output = MarkdownConverter().convert(tool_name, tool_result)

# 存储结构化数据（用于后续处理/存储）
state["tool_results"].append({
    "tool": tool_name,
    "structured": tool_result,
    "markdown": markdown_output
})
```

### Open WebUI 兼容性总结

| 功能 | Open WebUI 支持 | 实现方式 |
|------|----------------|----------|
| 表格展示 | ✅ Markdown 表格 | 转换为 `\| col \| col \|` 格式 |
| 时间条形图 | ✅ ASCII 艺术 | 使用 `█░` 字符绘制 |
| 状态图标 | ✅ Emoji | ✅❌⚠️⏱️⭐ |
| 折叠内容 | ✅ `<details>` | 原始 JSON 放入折叠块 |
| 代码块 | ✅ 语法高亮 | JSON 数据展示 |
| 引用块 | ✅ `>` 语法 | 重要信息高亮 |

**结论**：通过 Markdown 转换器，所有探测结果都能在 Open WebUI 中以可读的格式展示，同时保留结构化数据供后续处理。
