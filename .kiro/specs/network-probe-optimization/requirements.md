# Requirements Document

## Introduction

本文档定义了网络探测工具（netprobe）和 MCP Server 的优化需求。目标是增强探测能力、改进输出结构、提升可观测性，为后续的数据持久化和前端展示奠定基础。

## Glossary

- **Netprobe**: 使用 Go 编写的网络探测 CLI 工具，提供 ping、traceroute、mtr、nslookup、tcp、tls、http 等探测能力
- **MCP_Server**: Model Context Protocol 服务器，作为 LLM Agent 与 netprobe 之间的桥梁
- **Probe_Result**: 探测结果的统一 JSON 结构
- **Timing_Breakdown**: 请求各阶段的耗时分解（DNS、TCP、TLS、等待、传输等）
- **Certificate_Info**: TLS 证书的详细信息结构
- **Hop**: MTR/Traceroute 中的单个网络跳点

## Requirements

### Requirement 1: 增强 DNS 解析输出

**User Story:** As a 运维工程师, I want to 获取完整的 DNS 解析链路信息, so that I can 诊断 CNAME 递归、TTL 配置和 DNS 服务器问题。

#### Acceptance Criteria

1. WHEN 执行 nslookup 探测, THE Netprobe SHALL 返回完整的解析链路（包括所有 CNAME 跳转）
2. WHEN DNS 解析成功, THE Netprobe SHALL 返回每条记录的 TTL 值
3. WHEN DNS 解析成功, THE Netprobe SHALL 返回使用的 DNS 服务器地址
4. WHEN DNS 解析成功, THE Netprobe SHALL 返回解析耗时（毫秒）
5. IF DNS 解析失败, THEN THE Netprobe SHALL 返回具体的错误类型（超时、NXDOMAIN、SERVFAIL 等）

### Requirement 2: 增强 TLS 探测输出

**User Story:** As a 安全工程师, I want to 获取详细的 TLS 握手和证书信息, so that I can 评估服务的安全配置和证书状态。

#### Acceptance Criteria

1. WHEN 执行 TLS 探测, THE Netprobe SHALL 返回证书的完整主题信息（CN、O、OU、C 等）
2. WHEN 执行 TLS 探测, THE Netprobe SHALL 返回证书的颁发者信息
3. WHEN 执行 TLS 探测, THE Netprobe SHALL 返回证书的有效期和剩余天数
4. WHEN 执行 TLS 探测, THE Netprobe SHALL 返回证书的 SHA256 指纹
5. WHEN 执行 TLS 探测, THE Netprobe SHALL 返回支持的 TLS 协议版本列表
6. WHEN 执行 TLS 探测, THE Netprobe SHALL 返回协商使用的加密套件
7. WHEN 执行 TLS 探测, THE Netprobe SHALL 返回 TCP 连接和 TLS 握手的分段耗时
8. WHEN 执行 TLS 探测, THE Netprobe SHALL 检测并返回是否为双向 TLS（mTLS）
9. IF 证书即将过期（30天内）, THEN THE Netprobe SHALL 在结果中标记警告

### Requirement 3: 增强 HTTP 探测输出

**User Story:** As a 开发工程师, I want to 获取 HTTP 请求的详细时间分解, so that I can 定位性能瓶颈。

#### Acceptance Criteria

1. WHEN 执行 HTTP 探测, THE Netprobe SHALL 返回完整的时间分解（DNS、TCP、TLS、等待、传输）
2. WHEN 执行 HTTP 探测, THE Netprobe SHALL 返回响应头的关键字段（Content-Type、Server、Cache-Control 等）
3. WHEN 执行 HTTP 探测, THE Netprobe SHALL 返回重定向链路（如有）
4. WHEN 执行 HTTP 探测, THE Netprobe SHALL 返回最终 URL（重定向后）
5. WHEN 执行 HTTP 探测, THE Netprobe SHALL 返回响应体大小和压缩方式
6. IF HTTP 请求发生重定向, THEN THE Netprobe SHALL 记录每次重定向的状态码和目标 URL

### Requirement 4: 增强 MTR 输出结构

**User Story:** As a 网络工程师, I want to 获取结构化的 MTR 路径数据, so that I can 分析网络路径质量和定位丢包节点。

#### Acceptance Criteria

1. WHEN 执行 MTR 探测, THE Netprobe SHALL 返回每跳的结构化数据（跳数、IP、主机名、丢包率、延迟统计）
2. WHEN 执行 MTR 探测, THE Netprobe SHALL 返回每跳的最小/最大/平均/标准差延迟
3. WHEN 执行 MTR 探测, THE Netprobe SHALL 返回汇总统计（总跳数、平均延迟、整体丢包率）
4. WHEN 执行 MTR 探测, THE Netprobe SHALL 标识丢包率超过阈值（20%）的跳点
5. IF 某跳无响应, THEN THE Netprobe SHALL 在结果中标记为超时而非省略

### Requirement 5: 统一输出结构

**User Story:** As a 平台开发者, I want to 所有探测工具使用统一的输出结构, so that I can 简化数据处理和存储逻辑。

#### Acceptance Criteria

1. THE Netprobe SHALL 为所有探测类型使用统一的顶层 JSON 结构
2. THE Netprobe SHALL 在每个结果中包含 tool、success、timestamp、duration_ms 字段
3. THE Netprobe SHALL 在每个结果中包含 target 信息（域名/IP/URL）
4. WHEN 探测失败, THE Netprobe SHALL 返回结构化的错误信息（error_code、error_message）
5. THE Netprobe SHALL 支持 --output-format 参数选择输出格式（json、json-pretty）

### Requirement 6: MCP Server 增强

**User Story:** As a Agent 开发者, I want to MCP Server 提供更丰富的工具元数据, so that I can 让 LLM 更好地理解和使用工具。

#### Acceptance Criteria

1. WHEN 列出工具时, THE MCP_Server SHALL 返回每个工具的详细参数说明和示例
2. WHEN 调用工具时, THE MCP_Server SHALL 验证必填参数并返回友好的错误提示
3. WHEN 工具执行超时, THE MCP_Server SHALL 返回部分结果（如有）和超时信息
4. THE MCP_Server SHALL 支持批量探测（同一工具对多个目标）
5. THE MCP_Server SHALL 记录每次工具调用的耗时和结果摘要（用于审计）

### Requirement 7: 新增综合诊断命令

**User Story:** As a 运维工程师, I want to 一键执行完整的网络诊断, so that I can 快速获取目标的全面连通性报告。

#### Acceptance Criteria

1. THE Netprobe SHALL 提供 diagnose 子命令，接受域名或 URL 作为输入
2. WHEN 执行 diagnose, THE Netprobe SHALL 自动执行 DNS → TCP → TLS → HTTP 探测链
3. WHEN 执行 diagnose, THE Netprobe SHALL 返回包含所有探测结果的综合报告
4. THE Netprobe SHALL 支持 --skip 参数跳过特定探测步骤
5. THE Netprobe SHALL 支持 --parallel 参数并行执行多 IP 探测
6. WHEN 诊断完成, THE Netprobe SHALL 生成诊断结论和建议

### Requirement 8: 探测源信息

**User Story:** As a 运维工程师, I want to 在探测结果中包含探测源信息, so that I can 区分不同探测点的结果。

#### Acceptance Criteria

1. THE Netprobe SHALL 支持 --probe-id 参数标识探测源
2. WHEN 执行探测, THE Netprobe SHALL 在结果中包含本机出口 IP（可选）
3. THE Netprobe SHALL 支持从环境变量读取探测源元数据（位置、ISP 等）
