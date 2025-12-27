package probe

import (
	"fmt"
	"os/exec"
	"regexp"
	"runtime"
	"strings"
)

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
