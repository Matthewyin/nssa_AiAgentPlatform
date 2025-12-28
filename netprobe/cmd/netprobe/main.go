package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	"netprobe/pkg/probe"
)

// Global configuration
var (
	outputFormat string // json or json-pretty
	probeID      string // probe source identifier
	probeIP      string // probe source IP (optional)
	probeLocation string // probe source location (optional, from env)
	probeISP     string // probe source ISP (optional, from env)
)

func init() {
	// Read probe metadata from environment variables
	probeLocation = os.Getenv("NETPROBE_LOCATION")
	probeISP = os.Getenv("NETPROBE_ISP")
	probeIP = os.Getenv("NETPROBE_IP")
}

// parseGlobalFlags extracts global flags from args and returns remaining args
func parseGlobalFlags(args []string) []string {
	remaining := []string{}
	i := 0
	for i < len(args) {
		switch args[i] {
		case "--output-format":
			if i+1 < len(args) {
				outputFormat = args[i+1]
				i += 2
			} else {
				i++
			}
		case "--probe-id":
			if i+1 < len(args) {
				probeID = args[i+1]
				i += 2
			} else {
				i++
			}
		default:
			// Check for --output-format=value or --probe-id=value format
			if strings.HasPrefix(args[i], "--output-format=") {
				outputFormat = strings.TrimPrefix(args[i], "--output-format=")
				i++
			} else if strings.HasPrefix(args[i], "--probe-id=") {
				probeID = strings.TrimPrefix(args[i], "--probe-id=")
				i++
			} else {
				remaining = append(remaining, args[i])
				i++
			}
		}
	}
	
	// Set default output format
	if outputFormat == "" {
		outputFormat = "json"
	}
	
	return remaining
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, usage())
		os.Exit(1)
	}

	// Parse global flags first
	allArgs := parseGlobalFlags(os.Args[1:])
	
	if len(allArgs) < 1 {
		fmt.Fprintln(os.Stderr, usage())
		os.Exit(1)
	}

	cmd := allArgs[0]
	args := allArgs[1:]

	var res probe.Result
	var err error

	switch cmd {
	case "ping":
		fs := flag.NewFlagSet("ping", flag.ExitOnError)
		target := fs.String("target", "", "target host or ip")
		count := fs.Int("count", 4, "ping count")
		timeout := fs.Int("timeout", 10, "timeout seconds")
		_ = fs.Parse(args)
		if *target == "" {
			err = fmt.Errorf("target is required")
			break
		}
		res = probe.Ping(probe.PingOptions{
			Target:     *target,
			Count:      *count,
			TimeoutSec: *timeout,
			Tool:       "network.ping",
		})

	case "trace", "traceroute":
		fs := flag.NewFlagSet("trace", flag.ExitOnError)
		target := fs.String("target", "", "target host or ip")
		maxHops := fs.Int("max-hops", 30, "max hops")
		timeout := fs.Int("timeout", 60, "timeout seconds")
		_ = fs.Parse(args)
		if *target == "" {
			err = fmt.Errorf("target is required")
			break
		}
		res = probe.Traceroute(probe.TraceOptions{
			Target:     *target,
			MaxHops:    *maxHops,
			TimeoutSec: *timeout,
			Tool:       "network.traceroute",
		})

	case "mtr":
		fs := flag.NewFlagSet("mtr", flag.ExitOnError)
		target := fs.String("target", "", "target host or ip")
		count := fs.Int("count", 10, "probe count")
		reportCycles := fs.Int("report-cycles", 10, "report cycles")
		timeout := fs.Int("timeout", 60, "timeout seconds")
		_ = fs.Parse(args)
		if *target == "" {
			err = fmt.Errorf("target is required")
			break
		}
		// 使用新版 MtrEnhanced 返回 UnifiedResult 结构
		unifiedRes := probe.MtrEnhanced(probe.MtrOptions{
			Target:       *target,
			Count:        *count,
			ReportCycles: *reportCycles,
			TimeoutSec:   *timeout,
			Tool:         "network.mtr",
		})
		// Set source info if probe-id is set
		if probeID != "" {
			unifiedRes.SetSource(probeID, probeIP, probeLocation, probeISP)
		}
		printUnifiedJSON(unifiedRes)
		return

	case "nslookup":
		fs := flag.NewFlagSet("nslookup", flag.ExitOnError)
		target := fs.String("target", "", "domain to query")
		recordType := fs.String("record-type", "A", "DNS record type")
		timeout := fs.Int("timeout", 10, "timeout seconds")
		unified := fs.Bool("unified", true, "use unified output format (default: true)")
		_ = fs.Parse(args)
		if *target == "" {
			err = fmt.Errorf("target is required")
			break
		}
		if *unified {
			// Use new unified output format
			unifiedRes := probe.NslookupUnified(probe.NslookupOptions{
				Target:     *target,
				RecordType: *recordType,
				TimeoutSec: *timeout,
				Tool:       "network.nslookup",
			})
			// Set source info if probe-id is set
			if probeID != "" {
				unifiedRes.SetSource(probeID, probeIP, probeLocation, probeISP)
			}
			printUnifiedJSON(unifiedRes)
			return
		}
		res = probe.Nslookup(probe.NslookupOptions{
			Target:     *target,
			RecordType: *recordType,
			TimeoutSec: *timeout,
			Tool:       "network.nslookup",
		})

	case "tcp":
		fs := flag.NewFlagSet("tcp", flag.ExitOnError)
		host := fs.String("host", "", "target host")
		port := fs.Int("port", 0, "target port")
		timeout := fs.Int("timeout", 10, "timeout seconds")
		retry := fs.Int("retry", 0, "retry times")
		_ = fs.Parse(args)
		if *host == "" || *port == 0 {
			err = fmt.Errorf("host and port are required")
			break
		}
		res = probe.TCPProbe(probe.TCPOptions{
			Host:       *host,
			Port:       *port,
			TimeoutSec: *timeout,
			Retry:      *retry,
			Tool:       "network.tcp",
		})

	case "tls":
		fs := flag.NewFlagSet("tls", flag.ExitOnError)
		host := fs.String("host", "", "target host")
		port := fs.Int("port", 443, "target port")
		serverName := fs.String("server-name", "", "server name for SNI")
		timeout := fs.Int("timeout", 10, "timeout seconds")
		insecure := fs.Bool("insecure", false, "skip certificate verification")
		caCert := fs.String("ca-cert", "", "CA certificate path")
		clientCert := fs.String("client-cert", "", "client certificate path")
		clientKey := fs.String("client-key", "", "client key path")
		unified := fs.Bool("unified", true, "use unified output format (default: true)")
		_ = fs.Parse(args)
		if *host == "" || *port == 0 {
			err = fmt.Errorf("host and port are required")
			break
		}
		if *unified {
			// Use new unified output format
			unifiedRes := probe.TLSProbeUnified(probe.TLSOptions{
				Host:       *host,
				Port:       *port,
				ServerName: *serverName,
				TimeoutSec: *timeout,
				Insecure:   *insecure,
				CACert:     *caCert,
				ClientCert: *clientCert,
				ClientKey:  *clientKey,
				Tool:       "network.tls",
			})
			// Set source info if probe-id is set
			if probeID != "" {
				unifiedRes.SetSource(probeID, probeIP, probeLocation, probeISP)
			}
			printUnifiedJSON(unifiedRes)
			return
		}
		res = probe.TLSProbe(probe.TLSOptions{
			Host:       *host,
			Port:       *port,
			ServerName: *serverName,
			TimeoutSec: *timeout,
			Insecure:   *insecure,
			CACert:     *caCert,
			ClientCert: *clientCert,
			ClientKey:  *clientKey,
			Tool:       "network.tls",
		})

	case "http":
		fs := flag.NewFlagSet("http", flag.ExitOnError)
		url := fs.String("url", "", "target url")
		method := fs.String("method", "GET", "http method")
		timeout := fs.Int("timeout", 15, "timeout seconds")
		expectStatus := fs.Int("expect-status", 0, "expected status code")
		expectContains := fs.String("expect-contains", "", "expected substring in body")
		body := fs.String("body", "", "request body")
		headersJSON := fs.String("headers", "", "headers as JSON object, e.g. {\"User-Agent\":\"netprobe\"}")
		headerKVs := multiString{}
		fs.Var(&headerKVs, "header", "single header in 'Key: Value' format (can repeat)")
		_ = fs.Parse(args)
		if *url == "" {
			err = fmt.Errorf("url is required")
			break
		}
		headers := map[string]string{}
		if *headersJSON != "" {
			if json.Unmarshal([]byte(*headersJSON), &headers) != nil {
				err = fmt.Errorf("invalid headers json")
				break
			}
		}
		for _, h := range headerKVs {
			parts := strings.SplitN(h, ":", 2)
			if len(parts) == 2 {
				headers[strings.TrimSpace(parts[0])] = strings.TrimSpace(parts[1])
			}
		}
		res = probe.HTTPProbe(probe.HTTPOptions{
			URL:            *url,
			Method:         *method,
			Headers:        headers,
			Body:           *body,
			TimeoutSec:     *timeout,
			ExpectStatus:   *expectStatus,
			ExpectContains: *expectContains,
			Tool:           "network.http",
		})

	case "diagnose":
		fs := flag.NewFlagSet("diagnose", flag.ExitOnError)
		target := fs.String("target", "", "target domain, IP, or URL")
		port := fs.Int("port", 443, "target port")
		timeout := fs.Int("timeout", 30, "timeout seconds")
		skipSteps := fs.String("skip", "", "comma-separated steps to skip: dns,tcp,tls,http,mtr")
		parallel := fs.Bool("parallel", false, "probe multiple IPs in parallel")
		includeHTTP := fs.Bool("http", false, "include HTTP probe")
		includeMTR := fs.Bool("mtr", false, "include MTR probe")
		_ = fs.Parse(args)
		if *target == "" {
			err = fmt.Errorf("target is required")
			break
		}
		// Parse skip steps
		var skipList []string
		if *skipSteps != "" {
			skipList = strings.Split(*skipSteps, ",")
			for i := range skipList {
				skipList[i] = strings.TrimSpace(skipList[i])
			}
		}
		// Execute diagnose
		unifiedRes := probe.Diagnose(probe.DiagnoseOptions{
			Target:      *target,
			Port:        *port,
			TimeoutSec:  *timeout,
			Skip:        skipList,
			Parallel:    *parallel,
			IncludeHTTP: *includeHTTP,
			IncludeMTR:  *includeMTR,
			Tool:        "network.diagnose",
		})
		// Set source info if probe-id is set
		if probeID != "" {
			unifiedRes.SetSource(probeID, probeIP, probeLocation, probeISP)
		}
		printUnifiedJSON(unifiedRes)
		return

	default:
		err = fmt.Errorf("unknown subcommand: %s", cmd)
	}

	if err != nil {
		res = probe.Result{
			Success: false,
			Tool:    "network." + cmd,
			Error:   err.Error(),
		}
	}

	printJSON(res)
}

type multiString []string

func (m *multiString) String() string {
	return strings.Join(*m, ",")
}
func (m *multiString) Set(val string) error {
	*m = append(*m, val)
	return nil
}

func printJSON(res probe.Result) {
	// Add source info if probe-id is set
	if probeID != "" {
		if res.Details == nil {
			res.Details = make(map[string]any)
		}
		source := map[string]string{
			"probe_id": probeID,
		}
		if probeIP != "" {
			source["ip"] = probeIP
		}
		if probeLocation != "" {
			source["location"] = probeLocation
		}
		if probeISP != "" {
			source["isp"] = probeISP
		}
		res.Details["source"] = source
	}

	var data []byte
	var err error
	
	switch outputFormat {
	case "json-pretty":
		data, err = json.MarshalIndent(res, "", "  ")
	case "json":
		fallthrough
	default:
		data, err = json.Marshal(res)
	}
	
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal result failed: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(string(data))
}

// printUnifiedJSON prints a UnifiedResult as JSON
func printUnifiedJSON(res *probe.UnifiedResult) {
	var data []byte
	var err error
	
	switch outputFormat {
	case "json-pretty":
		data, err = json.MarshalIndent(res, "", "  ")
	case "json":
		fallthrough
	default:
		data, err = json.Marshal(res)
	}
	
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal result failed: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(string(data))
}

func usage() string {
	return `netprobe <subcommand> [global-options] [options]

global options:
  --output-format <format>   Output format: json (default) or json-pretty
  --probe-id <id>            Probe source identifier

environment variables:
  NETPROBE_LOCATION          Probe source location
  NETPROBE_ISP               Probe source ISP
  NETPROBE_IP                Probe source IP

subcommands:
  ping         --target <host> [--count 4] [--timeout 10]
  trace        --target <host> [--max-hops 30] [--timeout 60]
  mtr          --target <host> [--count 10] [--report-cycles 10] [--timeout 60]
  nslookup     --target <domain> [--record-type A] [--timeout 10] [--unified true]
  tcp          --host <host> --port <port> [--timeout 10] [--retry 0]
  tls          --host <host> [--port 443] [--server-name <sni>] [--timeout 10] [--insecure] [--ca-cert path] [--client-cert path --client-key path] [--unified true]
  http         --url <url> [--method GET] [--timeout 15] [--expect-status <code>] [--expect-contains <str>] [--body <data>] [--headers <json>] [--header "K: V"]
  diagnose     --target <domain|url> [--port 443] [--timeout 30] [--skip dns,tcp,tls,http,mtr] [--parallel] [--http] [--mtr]

examples:
  netprobe ping --target example.com
  netprobe --output-format json-pretty ping --target example.com
  netprobe --probe-id probe-beijing-01 tcp --host example.com --port 443
  netprobe --output-format json-pretty nslookup --target example.com --record-type A
  netprobe diagnose --target example.com --port 443
  netprobe diagnose --target https://example.com --http --parallel
  netprobe diagnose --target example.com --skip tls,http
`
}
