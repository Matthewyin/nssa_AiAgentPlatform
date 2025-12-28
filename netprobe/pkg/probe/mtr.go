package probe

import (
	"fmt"
	"math"
	"os/exec"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// MtrEnhanced 执行增强版 MTR 探测，返回统一结果结构
func MtrEnhanced(opts MtrOptions) *UnifiedResult {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.mtr"
	}
	if opts.Count <= 0 {
		opts.Count = 10
	}
	if opts.ReportCycles <= 0 {
		opts.ReportCycles = opts.Count
	}

	// 创建统一结果结构
	target := TargetInfo{
		Domain: opts.Target,
	}
	result := NewUnifiedResult(toolName, target)

	// 构建 mtr 命令参数
	// -r: report mode (非交互式)
	// -w: wide report (显示完整主机名)
	// -c: 探测次数
	// -n: 不解析主机名（加快速度，我们后续可以选择性解析）
	args := []string{
		"-r",
		"-w",
		"-c", fmt.Sprintf("%d", opts.ReportCycles),
		opts.Target,
	}

	cmdName := "mtr"
	cmdArgs := args
	if runtime.GOOS != "windows" {
		// macOS 需要 sudo 权限运行 mtr
		cmdName = "sudo"
		cmdArgs = append([]string{"-n", "/opt/homebrew/sbin/mtr"}, args...)
	}

	startTime := time.Now()
	cmdResult, err := RunCommand(opts.TimeoutSec, cmdName, cmdArgs...)
	durationMs := float64(time.Since(startTime).Microseconds()) / 1000.0

	// 保存原始输出用于调试
	if cmdResult != nil {
		result.RawOutput = TrimOutput(cmdResult.Stdout, 8000)
	}

	// 处理命令执行错误
	if err != nil {
		if _, ok := err.(*exec.Error); ok {
			result.SetError(ErrCommandNotFound, "mtr command not found (install mtr or grant permissions)", nil)
		} else {
			result.SetError(ErrInternalError, err.Error(), nil)
		}
		result.DurationMs = durationMs
		return result
	}

	// 解析 MTR 输出
	mtrResult := parseMTROutput(cmdResult.Stdout, opts.ReportCycles)

	// 设置成功结果
	result.SetSuccess(durationMs, mtrResult)

	return result
}

// parseMTROutput 解析 mtr 命令输出为结构化数据
func parseMTROutput(output string, reportCycles int) *MTRResult {
	mtrResult := &MTRResult{
		Hops: []MTRHop{},
		Summary: MTRSummary{
			HighLossHops: []int{},
			TimeoutHops:  []int{},
		},
	}

	lines := strings.Split(output, "\n")

	// MTR 报告格式示例 (mtr -r -w):
	// Start: 2024-01-15T10:30:00+0800
	//                                  My traceroute  [v0.95]
	// hostname                         Loss%   Snt   Last   Avg  Best  Wrst StDev
	//  1.|-- 192.168.1.1               0.0%    10    1.2   1.5   1.0   2.3   0.4
	//  2.|-- 10.0.0.1                  0.0%    10    5.3   5.8   4.2   8.1   1.2
	//  3.|-- ???                      100.0%    10    0.0   0.0   0.0   0.0   0.0
	//  4.|-- 202.97.33.1              25.0%    10   35.2  38.5  32.1  45.6   4.3

	// 正则表达式匹配 MTR 输出行
	// 格式: hop.|-- host/IP  Loss%  Snt  Last  Avg  Best  Wrst  StDev
	hopRegex := regexp.MustCompile(`^\s*(\d+)\.\|--\s+(\S+)\s+(\d+\.?\d*)%\s+(\d+)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)`)

	// 备用正则：简化格式（某些版本的 mtr）
	// 格式: hop. host/IP  Loss%  Snt  Last  Avg  Best  Wrst  StDev
	hopRegexAlt := regexp.MustCompile(`^\s*(\d+)\.\s+(\S+)\s+(\d+\.?\d*)%\s+(\d+)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)\s+(\d+\.?\d*)`)

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		// 尝试匹配标准格式
		matches := hopRegex.FindStringSubmatch(line)
		if matches == nil {
			// 尝试备用格式
			matches = hopRegexAlt.FindStringSubmatch(line)
		}

		if matches != nil && len(matches) >= 10 {
			hop := parseHopFromMatches(matches, reportCycles)
			mtrResult.Hops = append(mtrResult.Hops, hop)

			// 记录高丢包和超时跳点
			if hop.IsHighLoss {
				mtrResult.Summary.HighLossHops = append(mtrResult.Summary.HighLossHops, hop.HopNumber)
			}
			if hop.IsTimeout {
				mtrResult.Summary.TimeoutHops = append(mtrResult.Summary.TimeoutHops, hop.HopNumber)
			}
		}
	}

	// 生成汇总统计
	mtrResult.Summary.TotalHops = len(mtrResult.Hops)

	if len(mtrResult.Hops) > 0 {
		lastHop := mtrResult.Hops[len(mtrResult.Hops)-1]
		mtrResult.Summary.TargetReached = !lastHop.IsTimeout && lastHop.LossPercent < 100
		mtrResult.Summary.AvgLatencyMs = lastHop.LatencyMs.Avg
		mtrResult.Summary.OverallLossPercent = lastHop.LossPercent
	}

	return mtrResult
}

// parseHopFromMatches 从正则匹配结果解析单跳信息
func parseHopFromMatches(matches []string, reportCycles int) MTRHop {
	hopNumber, _ := strconv.Atoi(matches[1])
	host := matches[2]
	lossPercent, _ := strconv.ParseFloat(matches[3], 64)
	packetsSent, _ := strconv.Atoi(matches[4])
	last, _ := strconv.ParseFloat(matches[5], 64)
	avg, _ := strconv.ParseFloat(matches[6], 64)
	best, _ := strconv.ParseFloat(matches[7], 64)
	worst, _ := strconv.ParseFloat(matches[8], 64)
	stdDev, _ := strconv.ParseFloat(matches[9], 64)

	// 计算接收的包数
	packetsRecv := int(math.Round(float64(packetsSent) * (100 - lossPercent) / 100))

	// 判断是否超时（??? 或 100% 丢包）
	isTimeout := host == "???" || lossPercent >= 100

	// 判断是否高丢包（> 20%）
	isHighLoss := lossPercent > HighLossThreshold && !isTimeout

	// 处理 IP 和主机名
	ip := host
	hostname := ""
	if host == "???" {
		ip = ""
	} else if !isIPAddress(host) {
		// 如果不是 IP 地址，则认为是主机名
		hostname = host
		ip = "" // 需要额外解析
	}

	return MTRHop{
		HopNumber:   hopNumber,
		IP:          ip,
		Hostname:    hostname,
		PacketsSent: packetsSent,
		PacketsRecv: packetsRecv,
		LossPercent: lossPercent,
		LatencyMs: LatencyStats{
			Min:    best,
			Max:    worst,
			Avg:    avg,
			StdDev: stdDev,
			Last:   last,
		},
		IsTimeout:  isTimeout,
		IsHighLoss: isHighLoss,
	}
}

// isIPAddress 简单判断字符串是否为 IP 地址
func isIPAddress(s string) bool {
	// 简单检查：包含点且不包含字母（除了十六进制）
	if strings.Contains(s, ".") {
		// IPv4 检查
		parts := strings.Split(s, ".")
		if len(parts) == 4 {
			for _, part := range parts {
				if _, err := strconv.Atoi(part); err != nil {
					return false
				}
			}
			return true
		}
	}
	// IPv6 检查
	if strings.Contains(s, ":") {
		return true
	}
	return false
}

// Mtr 保留原有函数以保持向后兼容
// Deprecated: 请使用 MtrEnhanced 替代
func Mtr(opts MtrOptions) Result {
	toolName := opts.Tool
	if toolName == "" {
		toolName = "network.mtr"
	}
	if opts.Count <= 0 {
		opts.Count = 10
	}
	if opts.ReportCycles <= 0 {
		opts.ReportCycles = opts.Count
	}

	args := []string{
		"-r",
		"-c", fmt.Sprintf("%d", opts.ReportCycles),
		"-n",
		opts.Target,
	}

	cmdName := "mtr"
	cmdArgs := args
	if runtime.GOOS != "windows" {
		cmdName = "sudo"
		cmdArgs = append([]string{"-n", "/opt/homebrew/sbin/mtr"}, args...)
	}

	cmdResult, err := RunCommand(opts.TimeoutSec, cmdName, cmdArgs...)

	result := Result{
		Tool:         toolName,
		Target:       opts.Target,
		Count:        opts.Count,
		ReportCycles: opts.ReportCycles,
		RawOutput:    "",
		Summary:      map[string]any{},
	}

	if cmdResult != nil {
		raw := TrimOutput(cmdResult.Stdout, 8000)
		if strings.Contains(raw, "\n") {
			result.RawOutput = strings.Split(raw, "\n")
		} else {
			result.RawOutput = raw
		}
		result.Summary["duration_ms"] = cmdResult.Duration.Milliseconds()
	}

	if cmdResult != nil {
		hops := extractHops(cmdResult.Stdout)
		result.Summary["hops"] = hops
		result.Summary["total_hops"] = len(hops)
	}

	if err == nil {
		result.Success = true
		return result
	}

	if _, ok := err.(*exec.Error); ok {
		result.Error = "mtr command not found (install mtr or grant permissions)"
		return result
	}

	result.Error = err.Error()
	return result
}

func extractHops(output string) []map[string]string {
	var hops []map[string]string
	lines := strings.Split(output, "\n")
	re := regexp.MustCompile(`^\s*(\d+)\.\s+(\S+)\s+(\S+)%\s+`)
	for _, line := range lines {
		m := re.FindStringSubmatch(line)
		if len(m) >= 4 {
			hop := map[string]string{
				"hop":          m[1],
				"host":         m[2],
				"loss_percent": m[3],
			}
			hops = append(hops, hop)
		}
	}
	return hops
}
