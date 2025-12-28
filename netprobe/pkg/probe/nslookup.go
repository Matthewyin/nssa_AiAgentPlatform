package probe

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os/exec"
	"strings"
	"time"
)

// NslookupUnified 执行 DNS 解析并返回统一结构的结果
// 使用 Go 标准库 net 包实现完整解析链路追踪
func NslookupUnified(opts NslookupOptions) *UnifiedResult {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.nslookup"
	}
	if opts.RecordType == "" {
		opts.RecordType = "A"
	}

	// 创建统一结果结构
	target := TargetInfo{
		Domain:   opts.Target,
		Protocol: "dns",
	}
	result := NewUnifiedResult(toolName, target)

	// 执行 DNS 解析
	startTime := time.Now()
	dnsResult, err := performDNSLookup(opts)
	durationMs := float64(time.Since(startTime).Microseconds()) / 1000.0

	if err != nil {
		// 设置结构化错误
		errorCode, errorMsg := classifyDNSError(err)
		result.SetError(errorCode, errorMsg, map[string]any{
			"original_error": err.Error(),
			"query_type":     strings.ToUpper(opts.RecordType),
		})
		result.DurationMs = durationMs
		return result
	}

	// 设置成功结果
	result.SetSuccess(durationMs, dnsResult)
	return result
}

// performDNSLookup 执行实际的 DNS 解析
func performDNSLookup(opts NslookupOptions) (*DNSResult, error) {
	timeoutSec := opts.TimeoutSec
	if timeoutSec <= 0 {
		timeoutSec = 10
	}

	resolver := &net.Resolver{
		PreferGo: true,
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSec)*time.Second)
	defer cancel()

	recordType := strings.ToUpper(opts.RecordType)
	dnsResult := &DNSResult{
		QueryType:       recordType,
		ResolutionChain: []DNSRecord{},
		ResolvedIPs:     []string{},
		DNSServer:       getSystemDNSServer(),
	}

	startTime := time.Now()

	// 首先尝试获取 CNAME 链路
	cnameChain, err := resolveCNAMEChain(ctx, resolver, opts.Target)
	if err == nil && len(cnameChain) > 0 {
		dnsResult.ResolutionChain = append(dnsResult.ResolutionChain, cnameChain...)
	}

	// 根据记录类型执行解析
	switch recordType {
	case "A":
		err = resolveARecords(ctx, resolver, opts.Target, dnsResult)
	case "AAAA":
		err = resolveAAAARecords(ctx, resolver, opts.Target, dnsResult)
	case "MX":
		err = resolveMXRecords(ctx, resolver, opts.Target, dnsResult)
	case "NS":
		err = resolveNSRecords(ctx, resolver, opts.Target, dnsResult)
	case "TXT":
		err = resolveTXTRecords(ctx, resolver, opts.Target, dnsResult)
	case "CNAME":
		err = resolveCNAMERecord(ctx, resolver, opts.Target, dnsResult)
	default:
		// 默认解析 A 记录
		err = resolveARecords(ctx, resolver, opts.Target, dnsResult)
	}

	dnsResult.ResolutionTimeMs = float64(time.Since(startTime).Microseconds()) / 1000.0

	if err != nil {
		return nil, err
	}

	return dnsResult, nil
}

// resolveCNAMEChain 解析 CNAME 链路
func resolveCNAMEChain(ctx context.Context, resolver *net.Resolver, target string) ([]DNSRecord, error) {
	var chain []DNSRecord
	currentTarget := target
	visited := make(map[string]bool)

	for i := 0; i < 10; i++ { // 最多追踪 10 层 CNAME
		if visited[currentTarget] {
			break // 避免循环
		}
		visited[currentTarget] = true

		cname, err := resolver.LookupCNAME(ctx, currentTarget)
		if err != nil {
			break
		}

		// 去掉末尾的点
		cname = strings.TrimSuffix(cname, ".")

		// 如果 CNAME 和当前目标相同，说明没有 CNAME 记录
		if cname == currentTarget || cname == currentTarget+"." {
			break
		}

		chain = append(chain, DNSRecord{
			Name:  currentTarget,
			Type:  "CNAME",
			Value: cname,
			TTL:   0, // Go 标准库不提供 TTL，设为 0
		})

		currentTarget = cname
	}

	return chain, nil
}

// resolveARecords 解析 A 记录
func resolveARecords(ctx context.Context, resolver *net.Resolver, target string, result *DNSResult) error {
	ips, err := resolver.LookupIP(ctx, "ip4", target)
	if err != nil {
		return err
	}

	for _, ip := range ips {
		ipStr := ip.String()
		result.ResolvedIPs = append(result.ResolvedIPs, ipStr)
		result.ResolutionChain = append(result.ResolutionChain, DNSRecord{
			Name:  target,
			Type:  "A",
			Value: ipStr,
			TTL:   0, // Go 标准库不提供 TTL
		})
	}

	return nil
}

// resolveAAAARecords 解析 AAAA 记录
func resolveAAAARecords(ctx context.Context, resolver *net.Resolver, target string, result *DNSResult) error {
	ips, err := resolver.LookupIP(ctx, "ip6", target)
	if err != nil {
		return err
	}

	for _, ip := range ips {
		ipStr := ip.String()
		result.ResolvedIPs = append(result.ResolvedIPs, ipStr)
		result.ResolutionChain = append(result.ResolutionChain, DNSRecord{
			Name:  target,
			Type:  "AAAA",
			Value: ipStr,
			TTL:   0,
		})
	}

	return nil
}

// resolveMXRecords 解析 MX 记录
func resolveMXRecords(ctx context.Context, resolver *net.Resolver, target string, result *DNSResult) error {
	records, err := resolver.LookupMX(ctx, target)
	if err != nil {
		return err
	}

	for _, r := range records {
		host := strings.TrimSuffix(r.Host, ".")
		result.ResolutionChain = append(result.ResolutionChain, DNSRecord{
			Name:     target,
			Type:     "MX",
			Value:    host,
			TTL:      0,
			Priority: int(r.Pref),
		})
	}

	return nil
}

// resolveNSRecords 解析 NS 记录
func resolveNSRecords(ctx context.Context, resolver *net.Resolver, target string, result *DNSResult) error {
	records, err := resolver.LookupNS(ctx, target)
	if err != nil {
		return err
	}

	for _, r := range records {
		host := strings.TrimSuffix(r.Host, ".")
		result.ResolutionChain = append(result.ResolutionChain, DNSRecord{
			Name:  target,
			Type:  "NS",
			Value: host,
			TTL:   0,
		})
	}

	return nil
}

// resolveTXTRecords 解析 TXT 记录
func resolveTXTRecords(ctx context.Context, resolver *net.Resolver, target string, result *DNSResult) error {
	records, err := resolver.LookupTXT(ctx, target)
	if err != nil {
		return err
	}

	for _, txt := range records {
		result.ResolutionChain = append(result.ResolutionChain, DNSRecord{
			Name:  target,
			Type:  "TXT",
			Value: txt,
			TTL:   0,
		})
	}

	return nil
}

// resolveCNAMERecord 解析 CNAME 记录
func resolveCNAMERecord(ctx context.Context, resolver *net.Resolver, target string, result *DNSResult) error {
	cname, err := resolver.LookupCNAME(ctx, target)
	if err != nil {
		return err
	}

	cname = strings.TrimSuffix(cname, ".")
	result.ResolutionChain = append(result.ResolutionChain, DNSRecord{
		Name:  target,
		Type:  "CNAME",
		Value: cname,
		TTL:   0,
	})

	return nil
}

// getSystemDNSServer 获取系统 DNS 服务器地址
func getSystemDNSServer() string {
	// 尝试从 /etc/resolv.conf 读取
	// 这是一个简化实现，实际可能需要更复杂的逻辑
	return "system-default"
}

// classifyDNSError 将 DNS 错误分类为预定义错误码
func classifyDNSError(err error) (string, string) {
	if err == nil {
		return "", ""
	}

	errStr := err.Error()

	// 检查是否为 DNS 错误
	if dnsErr, ok := err.(*net.DNSError); ok {
		if dnsErr.IsTimeout {
			return ErrDNSTimeout, fmt.Sprintf("DNS 解析超时: %s", dnsErr.Name)
		}
		if dnsErr.IsNotFound {
			return ErrDNSNXDomain, fmt.Sprintf("域名不存在: %s", dnsErr.Name)
		}
		if dnsErr.IsTemporary {
			return ErrDNSServFail, fmt.Sprintf("DNS 服务器临时错误: %s", dnsErr.Name)
		}
	}

	// 基于错误消息进行分类
	errLower := strings.ToLower(errStr)
	switch {
	case strings.Contains(errLower, "timeout") || strings.Contains(errLower, "timed out"):
		return ErrDNSTimeout, fmt.Sprintf("DNS 解析超时: %s", errStr)
	case strings.Contains(errLower, "no such host") || strings.Contains(errLower, "nxdomain"):
		return ErrDNSNXDomain, fmt.Sprintf("域名不存在: %s", errStr)
	case strings.Contains(errLower, "server failure") || strings.Contains(errLower, "servfail"):
		return ErrDNSServFail, fmt.Sprintf("DNS 服务器错误: %s", errStr)
	case strings.Contains(errLower, "refused"):
		return ErrDNSRefused, fmt.Sprintf("DNS 查询被拒绝: %s", errStr)
	case strings.Contains(errLower, "no answer") || strings.Contains(errLower, "no records"):
		return ErrDNSNoAnswer, fmt.Sprintf("DNS 无应答: %s", errStr)
	default:
		return ErrDNSServFail, fmt.Sprintf("DNS 解析失败: %s", errStr)
	}
}

// ============================================================================
// Legacy Functions - 保留旧函数以保持兼容性
// ============================================================================

// Nslookup 执行 DNS 解析 (旧版本，保持兼容性)
// Deprecated: 请使用 NslookupUnified 替代
func Nslookup(opts NslookupOptions) Result {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.nslookup"
	}
	if opts.RecordType == "" {
		opts.RecordType = "A"
	}

	args := []string{}
	if opts.RecordType != "" && strings.ToUpper(opts.RecordType) != "A" {
		args = append(args, "-type="+opts.RecordType)
	}
	args = append(args, opts.Target)

	cmdResult, err := RunCommand(opts.TimeoutSec, "nslookup", args...)

	result := Result{
		Tool:       toolName,
		Target:     opts.Target,
		RecordType: strings.ToUpper(opts.RecordType),
		RawOutput:  "",
		Summary:    map[string]any{},
	}

	if cmdResult != nil {
		result.RawOutput = TrimOutput(cmdResult.Stdout, 8000)
	}

	if err == nil {
		result.Success = true
		return result
	}

	// nslookup 不存在时，尝试标准库解析
	if _, ok := err.(*exec.Error); ok {
		stdResult, stdErr := fallbackDNSLookup(result.RecordType, opts.Target, opts.TimeoutSec)
		if stdErr != nil {
			result.Error = stdErr.Error()
			return result
		}
		// fallback 结果放到 raw_output 里
		buf, _ := json.MarshalIndent(stdResult, "", "  ")
		result.RawOutput = string(buf)
		result.Success = true
		return result
	}

	result.Error = err.Error()
	return result
}

func fallbackDNSLookup(recordType, target string, timeoutSec int) (map[string]any, error) {
	if timeoutSec <= 0 {
		timeoutSec = 10
	}
	resolver := &net.Resolver{
		PreferGo: true,
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSec)*time.Second)
	defer cancel()

	recordType = strings.ToUpper(recordType)
	switch recordType {
	case "A":
		ips, err := resolver.LookupHost(ctx, target)
		if err != nil {
			return nil, err
		}
		return map[string]any{"A": ips}, nil
	case "AAAA":
		ips, err := resolver.LookupIP(ctx, "ip6", target)
		if err != nil {
			return nil, err
		}
		var list []string
		for _, ip := range ips {
			list = append(list, ip.String())
		}
		return map[string]any{"AAAA": list}, nil
	case "MX":
		records, err := resolver.LookupMX(ctx, target)
		if err != nil {
			return nil, err
		}
		var list []map[string]any
		for _, r := range records {
			list = append(list, map[string]any{"host": r.Host, "pref": r.Pref})
		}
		return map[string]any{"MX": list}, nil
	case "NS":
		records, err := resolver.LookupNS(ctx, target)
		if err != nil {
			return nil, err
		}
		var list []string
		for _, r := range records {
			list = append(list, r.Host)
		}
		return map[string]any{"NS": list}, nil
	case "TXT":
		txts, err := resolver.LookupTXT(ctx, target)
		if err != nil {
			return nil, err
		}
		return map[string]any{"TXT": txts}, nil
	case "CNAME":
		cname, err := resolver.LookupCNAME(ctx, target)
		if err != nil {
			return nil, err
		}
		return map[string]any{"CNAME": cname}, nil
	default:
		ips, err := resolver.LookupHost(ctx, target)
		if err != nil {
			return nil, err
		}
		return map[string]any{"A": ips}, nil
	}
}
