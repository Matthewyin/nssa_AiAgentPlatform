# Implementation Plan: Network Probe Optimization

## Overview

本实现计划将网络探测工具（netprobe）和 MCP Server 的优化分为多个阶段：首先统一数据结构，然后逐步增强各探测命令，最后实现 Markdown 转换器和综合诊断命令。

## Tasks

- [x] 1. 统一结果结构和基础设施
  - [x] 1.1 定义统一的 Go 数据结构
    - 在 `netprobe/pkg/probe/types.go` 中定义 `UnifiedResult`、`TargetInfo`、`SourceInfo`、`ErrorInfo` 结构
    - 定义错误码常量（DNS_TIMEOUT、TCP_REFUSED 等）
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x] 1.2 编写属性测试：统一结构验证
    - **Property 9: 所有探测结果符合统一结构**
    - **Validates: Requirements 5.1, 5.2, 5.3**
  - [x] 1.3 添加 --output-format 和 --probe-id 参数支持
    - 修改 `netprobe/cmd/netprobe/main.go` 添加全局参数
    - _Requirements: 5.5, 8.1_

- [x] 2. 增强 DNS 解析 (nslookup)
  - [x] 2.1 定义 DNS 结果数据结构
    - 在 `types.go` 中定义 `DNSResult`、`DNSRecord` 结构
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 2.2 重构 nslookup.go 实现
    - 使用 Go 标准库 `net` 包实现完整解析链路追踪
    - 返回 TTL、DNS 服务器、解析耗时
    - 实现结构化错误返回（NXDOMAIN、SERVFAIL 等）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [x] 2.3 编写属性测试：DNS 结果验证
    - **Property 1: DNS 成功结果包含必要字段**
    - **Property 2: DNS 失败结果包含结构化错误**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

- [x] 3. 增强 TLS 探测
  - [x] 3.1 定义 TLS 结果数据结构
    - 在 `types.go` 中定义 `TLSResult`、`TLSConnection`、`CertificateInfo`、`TLSTiming`、`TLSSecurity` 结构
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_
  - [x] 3.2 重构 tls.go 实现
    - 提取完整证书信息（主题、颁发者、有效期、指纹）
    - 分离 TCP 连接和 TLS 握手耗时
    - 检测 mTLS 配置
    - 实现证书过期警告（< 30 天）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 2.8, 2.9_
  - [x] 3.3 编写属性测试：TLS 结果验证
    - **Property 3: TLS 结果包含完整证书和连接信息**
    - **Property 4: 证书即将过期时标记警告**
    - **Validates: Requirements 2.1-2.9**

- [x] 4. Checkpoint - 确保基础探测测试通过
  - 运行所有测试，确保 DNS 和 TLS 增强功能正常
  - 如有问题，询问用户

- [x] 5. 增强 HTTP 探测
  - [x] 5.1 定义 HTTP 结果数据结构
    - 在 `types.go` 中定义 `HTTPResult`、`HTTPRequest`、`HTTPResponse`、`HTTPTiming`、`HTTPRedirect` 结构
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [x] 5.2 重构 http.go 实现
    - 完善时间分解（已有基础，需规范化输出）
    - 实现重定向链路追踪
    - 提取关键响应头
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [x] 5.3 编写属性测试：HTTP 结果验证
    - **Property 5: HTTP 结果包含完整响应和时间分解**
    - **Property 6: HTTP 重定向链完整记录**
    - **Validates: Requirements 3.1-3.6**

- [x] 6. 增强 MTR 探测
  - [x] 6.1 定义 MTR 结果数据结构
    - 在 `types.go` 中定义 `MTRResult`、`MTRHop`、`LatencyStats`、`MTRSummary` 结构
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 6.2 重构 mtr.go 实现
    - 解析 mtr 输出为结构化跳点数据
    - 计算每跳延迟统计（min/max/avg/std_dev）
    - 标识高丢包跳点和超时跳点
    - 生成汇总统计
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [x] 6.3 编写属性测试：MTR 结果验证
    - **Property 7: MTR 结果包含结构化跳点和汇总数据**
    - **Property 8: MTR 高丢包跳点正确标识**
    - **Validates: Requirements 4.1-4.5**

- [x] 7. Checkpoint - 确保所有探测增强测试通过
  - 运行所有测试，确保 HTTP 和 MTR 增强功能正常
  - 如有问题，询问用户

- [x] 8. 实现 diagnose 综合诊断命令
  - [x] 8.1 定义 Diagnose 结果数据结构
    - 在 `types.go` 中定义 `DiagnoseResult`、`DiagnoseTarget`、`DiagnoseSummary` 结构
    - _Requirements: 7.1, 7.2, 7.3, 7.6_
  - [x] 8.2 实现 diagnose 子命令
    - 新建 `netprobe/pkg/probe/diagnose.go`
    - 实现 DNS → TCP → TLS → HTTP 探测链
    - 支持 --skip 参数跳过特定步骤
    - 支持 --parallel 参数并行多 IP 探测
    - 生成诊断结论和建议
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
  - [x] 8.3 在 main.go 中注册 diagnose 命令
    - 添加命令行参数解析
    - _Requirements: 7.1_
  - [x] 8.4 编写属性测试：diagnose 结果验证
    - **Property 13: diagnose 返回完整综合诊断报告**
    - **Property 14: diagnose --skip 参数正确跳过步骤**
    - **Validates: Requirements 7.1-7.6**

- [x] 9. MCP Server 增强
  - [x] 9.1 实现参数验证器
    - 在 `mcp_servers/network_mcp/` 中新建 `validator.py`
    - 验证必填参数、类型、枚举值
    - 返回友好的错误提示
    - _Requirements: 6.2_
  - [x] 9.2 实现批量探测支持
    - 修改 `server.py` 支持 targets 数组参数
    - 并发执行探测并聚合结果
    - _Requirements: 6.4_
  - [x] 9.3 实现审计日志
    - 记录每次工具调用的耗时和结果摘要
    - _Requirements: 6.5_
  - [x] 9.4 更新 tools_config.yaml
    - 添加 diagnose 工具配置
    - 更新现有工具的参数说明
    - _Requirements: 6.1_
  - [x] 9.5 编写属性测试：MCP Server 验证
    - **Property 11: MCP Server 参数验证**
    - **Property 12: MCP Server 批量探测**
    - **Validates: Requirements 6.2, 6.4**

- [x] 10. Checkpoint - 确保 MCP Server 增强测试通过
  - 运行所有测试，确保 MCP Server 增强功能正常
  - 如有问题，询问用户

- [x] 11. 实现 Markdown 转换器
  - [x] 11.1 创建转换器基础结构
    - 新建 `graph_service/report_builder/` 目录
    - 创建 `markdown_converter.py` 基类
    - _Requirements: Open WebUI 适配_
  - [x] 11.2 实现 DNS 结果转换器
    - 创建 `converters/dns_converter.py`
    - 转换为解析链表格 + 统计信息
    - _Requirements: Open WebUI 适配_
  - [x] 11.3 实现 TLS 结果转换器
    - 创建 `converters/tls_converter.py`
    - 转换为证书卡片 + 时间分解表格
    - _Requirements: Open WebUI 适配_
  - [x] 11.4 实现 HTTP 结果转换器
    - 创建 `converters/http_converter.py`
    - 转换为响应摘要 + ASCII 时间条形图
    - _Requirements: Open WebUI 适配_
  - [x] 11.5 实现 MTR 结果转换器
    - 创建 `converters/mtr_converter.py`
    - 转换为跳点表格 + 丢包/超时标识
    - _Requirements: Open WebUI 适配_
  - [x] 11.6 实现 Diagnose 结果转换器
    - 创建 `converters/diagnose_converter.py`
    - 转换为综合报告 + 建议 + 折叠详情
    - _Requirements: Open WebUI 适配_
  - [x] 11.7 编写单元测试：Markdown 转换器
    - 验证各转换器输出格式正确
    - 验证 Emoji 和表格格式

- [x] 12. 集成 Markdown 转换器到 Graph Service
  - [x] 12.1 修改 react_observe.py
    - 在工具执行后调用 Markdown 转换器
    - 同时保存结构化数据和 Markdown 输出
    - _Requirements: Open WebUI 适配_
  - [x] 12.2 修改 final_answer_node.py
    - 将 Markdown 输出整合到最终回答中
    - _Requirements: Open WebUI 适配_

- [x] 13. Final Checkpoint - 端到端测试
  - 运行完整的端到端测试
  - 验证 Open WebUI 中的显示效果
  - 如有问题，询问用户

## Notes

- 所有任务都必须完成，包括属性测试
- 每个 Checkpoint 确保增量验证，避免问题累积
- Go 代码修改后需要重新编译 netprobe
- Python 代码修改后需要重启 MCP Server
- 属性测试使用 Go 的 `testing/quick` 或 `gopter` 库
