package main

import (
	"encoding/binary"
	"errors"
	"fmt"
	"github.com/adiprerepa/SLATE/slate-plugin/shared"
	"math"
	"math/rand"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
	_ "github.com/wasilibs/nottinygc"
)

// These keys are global keys that are used to store shared data between all instances of the plugin.
// a lot of these keys are not used.
const (
	KEY_INFLIGHT_ENDPOINT_LIST = "slate_inflight_endpoint_list"
	KEY_ENDPOINT_RPS_LIST      = "slate_endpoint_rps_list"
	KEY_INFLIGHT_REQ_COUNT     = "slate_inflight_request_count"
	KEY_RPS_THRESHOLDS         = "slate_rps_threshold"
	KEY_HASH_MOD               = "slate_hash_mod"
	KEY_TRACED_REQUESTS        = "slate_traced_requests"
	// this is in millis
	AGGREGATE_REQUEST_LATENCY = "slate_last_second_latency_avg"
	KEY_RPS_SHARED_QUEUE      = "slate_rps_shared_queue"
	KEY_RPS_SHARED_QUEUE_SIZE = "slate_rps_shared_queue_size"

	// this is the reporting period in millis
	TICK_PERIOD = 1000

	// Hash mod for frequency of request tracing.
	DEFAULT_HASH_MOD = 10
	KEY_NUM_TICKS    = "slate_key_num_ticks"

	KEY_MATCH_DISTRIBUTION     = "slate_match_distribution"
	KEY_CURRENTLY_HILLCLIMBING = "slate_currently_hillclimbing"
	KEY_HILLCLIMB_DIRECTION    = "slate_hillclimb_direction"
	KEY_HILLCLIMB_STEPSIZE     = "slate_hillclimb_stepsize"
)

var (
	ALL_KEYS = []string{KEY_INFLIGHT_REQ_COUNT, shared.KEY_REQUEST_COUNT, KEY_RPS_THRESHOLDS, KEY_HASH_MOD, AGGREGATE_REQUEST_LATENCY,
		KEY_TRACED_REQUESTS, KEY_MATCH_DISTRIBUTION, KEY_INFLIGHT_ENDPOINT_LIST, KEY_ENDPOINT_RPS_LIST, KEY_RPS_SHARED_QUEUE, KEY_RPS_SHARED_QUEUE_SIZE}
	cur_idx      int
	latency_list []int64
	ts_list      []int64
)

func main() {
	proxywasm.SetVMContext(&vmContext{})
	rand.Seed(time.Now().UnixNano())
}

type vmContext struct {
	// Embed the default VM context here,
	// so that we don't need to reimplement all the methods.
	types.DefaultVMContext
}

// Override types.DefaultVMContext.
func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{
		startTime: time.Now().UnixMilli(),
	}
}

func (*vmContext) OnVMStart(vmConfigurationSize int) types.OnVMStartStatus {
	// set all keys to 0
	for _, key := range ALL_KEYS {
		if err := proxywasm.SetSharedData(key, make([]byte, 8), 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data: %v", err)
		}
	}
	// set default hash mod
	buf := make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, uint64(DEFAULT_HASH_MOD))
	if err := proxywasm.SetSharedData(KEY_HASH_MOD, buf, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data: %v", err)
	}
	if _, err := proxywasm.RegisterSharedQueue(KEY_RPS_SHARED_QUEUE); err != nil {
		proxywasm.LogCriticalf("unable to register shared queue: %v", err)
	}
	return true
}

var region string
var serviceName string

type pluginContext struct {
	types.DefaultPluginContext

	podName          string
	serviceName      string
	svcWithoutRegion string

	region string

	startTime                     int64
	currentlyHillclimbingEndpoint string
	hillclimbingEnabled           bool
	currentHillclimbStepSize      int
	currentHillclimbDirection     int
	hillclimbIntervalSeconds      uint64
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	if err := proxywasm.SetTickPeriodMilliSeconds(TICK_PERIOD); err != nil {
		proxywasm.LogCriticalf("unable to set tick period: %v", err)
		return types.OnPluginStartStatusFailed
	}
	svc := os.Getenv("ISTIO_META_WORKLOAD_NAME")
	if svc == "" {
		svc = "SLATE_UNKNOWN_SVC"
	}
	pod := os.Getenv("HOSTNAME")
	if pod == "" {
		pod = "SLATE_UNKNOWN_POD"
	}
	regionName := os.Getenv("ISTIO_META_REGION")
	if regionName == "" {
		regionName = "SLATE_UNKNOWN_REGION"
	}
	p.podName = pod
	p.serviceName = svc
	p.region = regionName
	region = regionName
	serviceName = svc
	return types.OnPluginStartStatusOK
}

// OnTick reports load to the controller every TICK_PERIOD milliseconds.
func (p *pluginContext) OnTick() {

	if p.hillclimbingEnabled && p.hillclimbIntervalSeconds != 0 && uint64(time.Now().Unix())%p.hillclimbIntervalSeconds == 0 {
		p.RequestHillclimbPolicy()
	}

	totalRps := shared.GetUint64SharedDataOrZero(shared.KEY_REQUEST_COUNT)
	if err := proxywasm.SetSharedData(shared.KEY_REQUEST_COUNT, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset request count: %v", err)
	}

	// get the current per-endpoint load conditions
	inflightStats := ""
	inflightStatsMap, err := GetInflightRequestStats()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get inflight request stats: %v", err)
		return
	}

	for k, _ := range inflightStatsMap {
		//for k, v := range inflightStatsMap {
		//inflightStats += strings.Join([]string{k, strconv.Itoa(int(v.Total)), strconv.Itoa(int(v.Inflight))}, ",")
		inflightStats += strings.Join([]string{k, strconv.Itoa(int(totalRps)), strconv.Itoa(int(totalRps))}, ",")
		inflightStats += "|"
	}

	// get the per-request load conditions and latencies
	requestStats, err := GetTracedRequestStats()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get traced request stats: %v", err)
		return
	}
	requestStatsStr := ""
	for _, stat := range requestStats {
		endpointInflightStatsBytes, _, err := proxywasm.GetSharedData(shared.EndpointInflightStatsKey(stat.TraceId))
		endpointInflightStats := ""
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v endpoint inflight stats: %v", stat.TraceId, err)
			endpointInflightStats = "NOT FOUND"
		} else {
			endpointInflightStats = string(endpointInflightStatsBytes)
		}
		requestStatsStr += fmt.Sprintf("%s %s %s %s %s %s %s %d %d %d %s\n", p.region, p.serviceName, stat.Method, stat.Path, stat.TraceId, stat.SpanId, stat.ParentSpanId,
			stat.StartTime, stat.EndTime, stat.BodySize, endpointInflightStats)
	}

	// reset stats
	noId := shared.GetUint64SharedDataOrZero(shared.KEY_NO_TRACEID)
	if err := proxywasm.SetSharedData(shared.KEY_NO_TRACEID, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset no traceid: %v", err)
	}
	if err := proxywasm.SetSharedData(KEY_TRACED_REQUESTS, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset traced requests: %v", err)
	}
	ResetEndpointCounts()
	if err := proxywasm.SetSharedData(KEY_INFLIGHT_ENDPOINT_LIST, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset inflight endpoint list: %v", err)
	}
	if err := proxywasm.SetSharedData(KEY_ENDPOINT_RPS_LIST, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset endpoint rps list: %v", err)
	}

	//data, cas, err = proxywasm.GetSharedData(KEY_INFLIGHT_REQ_COUNT)
	//if err != nil {
	//	proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
	//	return
	//}

	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/proxyLoad"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
		{"x-slate-region", p.region},
	}

	// first %d was reqcount

	reqBody := fmt.Sprintf("reqCount\n%d\n\ninflightStats\n%s\nrequestStats\n%s", 0, inflightStats, requestStatsStr)
	proxywasm.LogCriticalf("<OnTick (noid %v)> reqBody:\n%s", noId, reqBody)

	proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(fmt.Sprintf("%d\n%s\n%s", totalRps, inflightStats, requestStatsStr)), make([][2]string, 0), 5000, p.OnTickHttpCallResponse)

	p.ReportHillclimbingLatency()
}

func (p *pluginContext) ReportHillclimbingLatency() {
	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/hillclimbingLatency"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
		{"x-slate-region", p.region},
	}

	if p.currentlyHillclimbingEndpoint == "" || p.currentlyHillclimbingEndpoint == "WAIT" {
		// nothing to hillclimb
		proxywasm.LogCriticalf("[ReportHillclimbingLatency] no endpoint to hillclimb")
		controllerHeaders = append(controllerHeaders, [2]string{"x-slate-need-hillclimbing", "true"})
	} else {
		proxywasm.LogCriticalf("[ReportHillclimbingLatency] endpoint to hillclimb: %v", p.currentlyHillclimbingEndpoint)
		svcMethodPath := strings.Split(string(p.currentlyHillclimbingEndpoint)[:len(p.currentlyHillclimbingEndpoint)-13], "@")
		svc, method, path := svcMethodPath[0], svcMethodPath[1], svcMethodPath[2]
		totalLatency := shared.GetUint64SharedDataOrZero(shared.PerSecondLatencyKey(svc, method, path))
		totalReqs := shared.GetUint64SharedDataOrZero(shared.PerSecondLatencyTotalRequestsKey(svc, method, path))
		// reset the total latency and total requests
		nv := 0
		buf := make([]byte, 8)
		binary.LittleEndian.PutUint64(buf, uint64(nv))
		if err := proxywasm.SetSharedData(shared.PerSecondLatencyKey(svc, method, path), buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't reset total latency: %v", err)
		}
		if err := proxywasm.SetSharedData(shared.PerSecondLatencyTotalRequestsKey(svc, method, path), buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't reset total requests: %v", err)
		}
		avgLatency := 0
		if totalReqs != 0 {
			avgLatency = int(totalLatency / totalReqs)
		}
		controllerHeaders = append(controllerHeaders, [2]string{"x-slate-avg-latency", strconv.Itoa(avgLatency)})
		controllerHeaders = append(controllerHeaders, [2]string{"x-slate-total-reqs", strconv.Itoa(int(totalReqs))})
		controllerHeaders = append(controllerHeaders, [2]string{"x-slate-cur-hillclimbing", string(p.currentlyHillclimbingEndpoint)})
	}
	proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(""), make([][2]string, 0), 5000, p.HillclimbLatencyHttpResponseHandler)
}

func (p *pluginContext) RequestHillclimbPolicy() {
	proxywasm.LogCriticalf("requesting hillclimb policy")
	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/hillclimbingPolicy"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
		{"x-slate-region", p.region},
	}

	proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(""), make([][2]string, 0), 5000, p.OnHillclimbPolicyResponse)
}

func HillclimbHttpResponseHandler(numHeaders, bodySize, numTrailers int) {
	// todo should we do anything with the response?
}

func (p *pluginContext) HillclimbLatencyHttpResponseHandler(numHeaders, bodySize, numTrailers int) {
	respBody, err := parseHttpResponse("HillclimbLatencyHttpResponseHandler", numHeaders, bodySize, numTrailers)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't parse http call response: %v", err)
		return
	}
	// set the currently hillclimbing endpoint
	// we set the hillclimbing endpoint from the resposne of this latency handler because the clusters that
	// don't get rules (just fallback to local routing) will not pick a hillclimbing endpoint, so we need to
	// globally synchronize it here.
	// basically, "I need to know which class of data to report so you can make the right decisions".

	// todo: we will also sent other hillclimbing parameters here (step size, interval, etc)
	// Expected response
	/*

		Restart of slate-controller will contain new hillclimbing policy
		Enabled/Disabled
		Initial step size
		Interval
		Cur hillclimbing endpoint OR "WAIT"

		Example:
		Enabled
		2
		30
		metrics-handler@GET@/detectAnomalies@us-west-1
	*/

	lines := strings.Split(respBody, "\n")
	if len(lines) != 4 {
		proxywasm.LogCriticalf("Invalid response from hillclimbing latency handler: %s", respBody)
		return
	}
	enabled := lines[0]
	stepSize, err := strconv.Atoi(lines[1])
	if err != nil {
		proxywasm.LogCriticalf("Couldn't parse step size: %v", err)
		return
	}
	interval, err := strconv.Atoi(lines[2])
	if err != nil {
		proxywasm.LogCriticalf("Couldn't parse interval: %v", err)
		return
	}
	curHillclimbingEndpoint := lines[3]
	p.hillclimbingEnabled = enabled == "Enabled"
	p.currentHillclimbStepSize = stepSize
	p.hillclimbIntervalSeconds = uint64(interval)
	p.currentlyHillclimbingEndpoint = curHillclimbingEndpoint
}

func (p *pluginContext) OnHillclimbPolicyResponse(numHeaders, bodySize, numTrailers int) {
	respBody, err := parseHttpResponse("OnHillclimbPolicyResponse", numHeaders, bodySize, numTrailers)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't parse http call response: %v", err)
		return
	}
	// on the first call, this won't mean anything, and PerformHillClimb will ignore.
	correctDirection := false
	trimmed := strings.TrimSpace(respBody)
	if trimmed == "true" {
		correctDirection = true
	} else if trimmed == "false" {
		correctDirection = false
	} else {
		proxywasm.LogCriticalf("not hillclimbing, unknown policy response (%v)", trimmed)
		return
	}

	proxywasm.LogCriticalf("logadi-hillclimb")
	oldDist, newDist, avgLatency, regionToLatency := p.PerformHillClimb(correctDirection)
	oldDistNoNewlines, newDistNoNewlines := strings.ReplaceAll(oldDist, "\n", " "), strings.ReplaceAll(newDist, "\n", " ")
	outboundRps := avgLatency.TotalReqs / int(p.hillclimbIntervalSeconds)
	inboundRps := shared.GetUint64SharedDataOrZero(shared.KEY_HILLCLIMB_INBOUNDRPS) / p.hillclimbIntervalSeconds
	if err := proxywasm.SetSharedData(shared.KEY_HILLCLIMB_INBOUNDRPS, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset inbound rps: %v", err)
	}
	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/hillclimbingReport"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
		{"x-slate-region", p.region},
		{"x-slate-old-dist", oldDistNoNewlines},
		{"x-slate-new-dist", newDistNoNewlines},
		{"x-slate-avg-latency", strconv.Itoa(avgLatency.LatencyAvg)},
		{"x-slate-outbound-rps", strconv.Itoa(outboundRps)},
		{"x-slate-inbound-rps", strconv.Itoa(int(inboundRps))},
	}
	for r, latency := range regionToLatency {
		controllerHeaders = append(controllerHeaders, [2]string{fmt.Sprintf("x-slate-%v-latency", r), strconv.Itoa(latency.LatencyAvg)})
		controllerHeaders = append(controllerHeaders, [2]string{fmt.Sprintf("x-slate-%v-outboundreqs", r), strconv.Itoa(latency.TotalReqs)})
	}
	proxywasm.LogCriticalf("hillclimbing headers: %v", controllerHeaders)
	if _, err := proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(""), make([][2]string, 0), 5000, HillclimbHttpResponseHandler); err != nil {
		proxywasm.LogCriticalf("Couldn't dispatch hillclimbing http call: %v", err)
	}
}

// callback for OnTick() http call response
func (p *pluginContext) OnTickHttpCallResponse(numHeaders, bodySize, numTrailers int) {
	// receive RPS thresholds, set shared data accordingly
	respBody, err := parseHttpResponse("OnTick", numHeaders, bodySize, numTrailers)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't parse http call response: %v", err)
		return
	}
	bodyLines := strings.Split(string(respBody), "\n")
	/*
		Example response body:
			metrics-fake-ingress@GET@/start, metrics-handler@GET@/detectAnomalies, us-west-1, us-west-1, 0.6
			metrics-fake-ingress@GET@/start, metrics-handler@GET@/detectAnomalies, us-west-1, us-east-1, 0.4
			metrics-fake-ingress@GET@/start, metrics-handler@GET@/detectAnomalies, us-east-1, us-east-1, 0.1
			metrics-fake-ingress@GET@/start, metrics-handler@GET@/detectAnomalies, us-east-1, us-west-1, 0.9
	*/
	proxywasm.LogCriticalf("received http call response: %s", bodyLines)
	// dst_svc@method@path -> region -> pct
	distrs := map[string]map[string]string{}
	for _, line := range bodyLines {
		if line == "" {
			continue
		}
		lineSplit := strings.Split(line, ",")
		if len(lineSplit) != 5 {
			proxywasm.LogCriticalf("received invalid http call response, line: %s", line)
			continue
		}
		for i, lineItem := range lineSplit {
			lineSplit[i] = strings.TrimSpace(lineItem)
		}
		if lineSplit[2] != region {
			// disclude
			continue
		}
		srcSvcMethodPath := strings.Split(lineSplit[0], "@")
		if len(srcSvcMethodPath) != 3 {
			proxywasm.LogCriticalf("received invalid http call response, line: %s", line)
			continue
		}
		dstSvcMethodPath := strings.Split(lineSplit[1], "@")
		if len(dstSvcMethodPath) != 3 {
			proxywasm.LogCriticalf("received invalid http call response, line: %s", line)
			continue
		}
		// assume we only get responses for our service
		if !strings.HasPrefix(serviceName, srcSvcMethodPath[0]) {
			// disclude
			continue
		}
		if _, ok := distrs[lineSplit[1]]; !ok {
			distrs[lineSplit[1]] = map[string]string{}
		}
		parsedPct, err := strconv.ParseFloat(lineSplit[4], 64)
		if err != nil {
			proxywasm.LogCriticalf("Couldn't parse percentage in rules from global controller: %v", err)
			continue
		}
		// round to 2 decimal places
		distrs[lineSplit[1]][lineSplit[3]] = fmt.Sprintf("%.2f", parsedPct)

	}

	for methodPath, distr := range distrs {
		distStr := ""
		for region, pct := range distr {
			distStr += fmt.Sprintf("%s %s\n", region, pct)
		}
		mp := strings.Split(methodPath, "@")
		proxywasm.LogCriticalf("setting outbound request distribution %v: %v", shared.EndpointDistributionKey(mp[0],
			mp[1], mp[2]), distStr)

		// if lastRecvRulesKey exists and is the same, don't reset as we might be hillclimbing
		if rules, _, err := proxywasm.GetSharedData(shared.LastRecvRulesKey(mp[0], mp[1], mp[2])); err != nil || !p.hillclimbingEnabled || (p.hillclimbingEnabled && !rulesSimilar(string(rules), distStr)) {
			// whe reset the rules when either:
			// - no rules exist yet
			// - we are not hillclimbing (purely enforcement mode)
			// - we are hillclimbing and the rules are different
			// no rules exist, set new rules and set lastRecvRulesKey
			proxywasm.LogCriticalf("dissimilar rules found, setting lastRecvRulesKey %v: %v", shared.EndpointDistributionKey(mp[0], mp[1], mp[2]), distStr)
			if err := proxywasm.SetSharedData(shared.EndpointDistributionKey(mp[0], mp[1], mp[2]), []byte(distStr), 0); err != nil {
				proxywasm.LogCriticalf("unable to set shared data for endpoint distribution %v: %v", methodPath, err)
			}
			if err := proxywasm.SetSharedData(shared.LastRecvRulesKey(mp[0], mp[1], mp[2]), []byte(distStr), 0); err != nil {
				proxywasm.LogCriticalf("unable to set lastRecvRulesKey for endpoint distribution %v: %v", methodPath, err)
			}
			// if we only have one rule (as in us-west,us-west,1.0), we cant hill climb because we dont know the alternatives
			if len(distr) > 1 {
				// start hillclimbing
				p.currentlyHillclimbingEndpoint = shared.EndpointDistributionKey(mp[0], mp[1], mp[2])
			}
		} else {
			// rules exist AND we are hillclimbing AND and the rules are similar
			// if we recieved the same rules as lastRecvRulesKey, don't set endpointDistributionKey because we might be hillclimbing
			proxywasm.LogCriticalf("rules already exist for %v and are similar to recieved, skipping", methodPath)
			continue
		}
	}
}

func parseHttpResponse(callContext string, numHdrs, bodySize, numTrailers int) (string, error) {
	hdrs, err := proxywasm.GetHttpCallResponseHeaders()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get http call response headers for %v: %v", callContext, err)
		return "", err
	}
	var status int
	status = 200
	for _, hdr := range hdrs {
		if hdr[0] == ":status" {
			status, err = strconv.Atoi(hdr[1])
			if err != nil {
				proxywasm.LogCriticalf("Couldn't parse :status header for %v: %v", callContext, err)
				return "", err
			}
		}
	}

	if status >= 400 {
		proxywasm.LogCriticalf("received ERROR %v http call response, status %v body size: %d", callContext, hdrs, bodySize)
		return "", errors.New("received error http call response")
	}
	if bodySize == 0 {
		return "", nil
	}

	respBody, err := proxywasm.GetHttpCallResponseBody(0, bodySize)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get http call response body for %v: %v", callContext, err)
		return "", err
	} else {
		return string(respBody), nil
	}
}

// if the percentages of t
func rulesSimilar(current, received string) bool {
	currentLines := strings.Split(current, "\n")
	receivedLines := strings.Split(received, "\n")
	if len(currentLines) == 0 || len(receivedLines) == 0 {
		return false
	}
	regionPct := strings.Split(currentLines[0], " ")
	if len(regionPct) != 2 {
		return false
	}
	region := regionPct[0]
	currentPct, err := strconv.ParseFloat(regionPct[1], 64)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't parse current distribution: %v", err)
		return false
	}
	for _, line := range receivedLines {
		lineSplit := strings.Split(line, " ")
		if len(lineSplit) != 2 {
			return false
		}
		if lineSplit[0] == region {
			receivedPct, err := strconv.ParseFloat(lineSplit[1], 64)
			if err != nil {
				proxywasm.LogCriticalf("Couldn't parse received distribution: %v", err)
				return false
			}
			return math.Abs(currentPct-receivedPct) < 0.07
		}
	}
	proxywasm.LogCriticalf("Couldn't find region %v in received distribution", region)
	return false
}

type LatencyStat struct {
	LatencyAvg int
	TotalReqs  int
}

// PerformHillClimb performs the hill climbing algorithm to adjust the outbound request distribution.
func (p *pluginContext) PerformHillClimb(correctDirection bool) (oldDist, newDist string, avgLatency LatencyStat, regionToLatency map[string]LatencyStat) {
	if p.currentlyHillclimbingEndpoint == "" || p.currentlyHillclimbingEndpoint == "WAIT" {
		// nothing to hillclimb
		proxywasm.LogCriticalf("Nothing to hillclimb yet...")
		return
	} else {
		proxywasm.LogCriticalf("Hillclimbing for %v, correctDirection: %v", p.currentlyHillclimbingEndpoint, correctDirection)
	}
	regions := []string{"us-west-1", "us-east-1"} // todo get regions from distribution
	svcMethodPath := strings.Split(p.currentlyHillclimbingEndpoint[:len(p.currentlyHillclimbingEndpoint)-13], "@")
	svc, method, path := svcMethodPath[0], svcMethodPath[1], svcMethodPath[2]
	distribution, cas, err := proxywasm.GetSharedData(p.currentlyHillclimbingEndpoint)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get endpoint distribution while trying to hillclimb: %v", err)
		return
	}
	proxywasm.LogCriticalf("Hillclimbing for %v, current distribution is %v", string(p.currentlyHillclimbingEndpoint), string(distribution))
	curAvgLatencyTotalMs, err := shared.GetUint64SharedData(shared.OutboundLatencyRunningAvgKey(svc, method, path))
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get current average latency while trying to hillclimb: %v", err)
		return
	}
	curAvgLatencyTotalRequests, err := shared.GetUint64SharedData(shared.OutboundLatencyTotalRequestsKey(svc, method, path))
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get total requests while trying to hillclimb: %v", err)
		curAvgLatencyTotalRequests = 0
		return
	}
	if curAvgLatencyTotalRequests == 0 {
		proxywasm.LogCriticalf("No requests yet, skipping hillclimb...")
		return
	}
	regionToLatency = make(map[string]LatencyStat)
	for _, r := range regions {
		regionLatency, err := shared.GetUint64SharedData(shared.RegionOutboundLatencyRunningAvgKey(svc, method, path, r))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get region average latency while trying to hillclimb: %v", err)
			return
		}
		regionRequests, err := shared.GetUint64SharedData(shared.RegionOutboundLatencyTotalRequestsKey(svc, method, path, r))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get region total requests while trying to hillclimb: %v", err)
			return
		}
		if regionRequests == 0 {
			proxywasm.LogCriticalf("No requests yet for region %v, setting 1...", r)
			regionRequests = 1
		}
		regionToLatency[r] = LatencyStat{
			LatencyAvg: int(regionLatency / regionRequests),
			TotalReqs:  int(regionRequests),
		}
	}
	buf := make([]byte, 8)
	for _, r := range regions {
		// set 0 latency and 0 requests for each region
		if err := proxywasm.SetSharedData(shared.RegionOutboundLatencyTotalRequestsKey(svc, method, path, r), buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't reset current average latency for region %v: %v", r, err)
		}
		if err := proxywasm.SetSharedData(shared.RegionOutboundLatencyRunningAvgKey(svc, method, path, r), buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't reset total requests for region %v: %v", r, err)
		}
	}
	curAvgLatency := curAvgLatencyTotalMs / curAvgLatencyTotalRequests
	curAvgLatencyStat := LatencyStat{
		LatencyAvg: int(curAvgLatency),
		TotalReqs:  int(curAvgLatencyTotalRequests),
	}
	// set the current average latency to 0
	buf = make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, 0)
	if err := proxywasm.SetSharedData(shared.OutboundLatencyRunningAvgKey(svc, method, path), buf, 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset current average latency: %v", err)
		return
	}
	// set num requests to 0
	if err := proxywasm.SetSharedData(shared.OutboundLatencyTotalRequestsKey(svc, method, path), buf, 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset total requests: %v", err)
		return
	}
	// we have a previous average latency, we can now perform the hill climbing algorithm
	// we need to get the step size and direction
	stepSize := p.currentHillclimbStepSize
	direction := p.currentHillclimbDirection

	// if the current latency is less than the last latency, we keep the direction and adjust the
	// distribution by the step size.
	// if the current latency is greater than the last latency, we reverse the direction and adjust the
	// distribution by half the last step size.
	// if the current latency is close to the last latency, we complete the hill climb.

	// correctDirection = curAvgLatency < lastAvgLatency from global controller POV
	// todo dynamic step size
	if !correctDirection {
		// keep direction
		p.currentHillclimbDirection = direction * -1
	}
	proxywasm.LogCriticalf("changing step size from %v to %v, direction from %v to %v", stepSize, p.currentHillclimbStepSize, direction, p.currentHillclimbDirection)
	newDistr := p.AdjustDistribution(p.currentHillclimbStepSize, p.currentHillclimbDirection, string(distribution))
	if err := proxywasm.SetSharedData(p.currentlyHillclimbingEndpoint, []byte(newDistr), cas); err != nil {
		proxywasm.LogCriticalf("Couldn't set new distribution: %v", err)
		return
	} else {
		proxywasm.LogCriticalf("(keeping direction %v, stepsize %v) Adjusted distribution from\n%v\nto\n%v\n", direction, stepSize, string(distribution), newDistr)
	}
	return string(distribution), newDistr, curAvgLatencyStat, regionToLatency
}

func (p *pluginContext) AdjustDistribution(stepSize, direction int, distribution string) string {
	distrLines := strings.Split(distribution, "\n")
	newDistr := ""
	for _, line := range distrLines {
		lineS := strings.Split(line, " ")
		if len(lineS) != 2 {
			continue
		}
		region := lineS[0]
		pctFloat, err := strconv.ParseFloat(lineS[1], 64)
		proxywasm.LogCriticalf("region: %v, pct: %f", region, pctFloat)
		pct := int(math.Round(pctFloat * 100))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't parse distribution line: %v", err)
			return ""
		}
		if region == p.region {
			// local region, direction = 1 means offload more (overall percent decreases)
			// direction = -1 means keep more local (overall percent increases)
			proxywasm.LogCriticalf("adjusting pct for %v (currently %v)", region, pct)
			pct -= stepSize * direction
		} else {
			// remote region, direction = 1 means offload more (overall percent increases)
			// direction = -1 means keep more remote (overall percent decreases)
			proxywasm.LogCriticalf("adjusting pct for %v (currently %v)", region, pct)
			pct += stepSize * direction
		}
		if pct < 0 {
			proxywasm.LogCriticalf("offload pct to %v is < 0, resetting to 0", region)
			pct = 0
		}
		if pct > 100 {
			proxywasm.LogCriticalf("offload pct to %v is > 1, resetting to 1", region)
			pct = 100
		}
		proxywasm.LogCriticalf("new pct for %v: %v", region, pct)
		newDistr += fmt.Sprintf("%s %f\n", region, float64(pct)/100)
	}
	proxywasm.LogCriticalf("new distribution: %v", newDistr)
	return newDistr
}

// IncrementSharedData increments the value of the shared data at the given key. The data is
// stored as a little endian uint64. if the key doesn't exist, it is created with the value 1.
func IncrementSharedData(key string, amount int64) {
	data, cas, err := proxywasm.GetSharedData(key)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
	}
	var val int64
	if len(data) == 0 {
		val = amount
	} else {
		// hopefully we don't overflow...
		if int64(binary.LittleEndian.Uint64(data)) != 0 || amount > 0 {
			val = int64(binary.LittleEndian.Uint64(data)) + amount
		} else {
			val = int64(binary.LittleEndian.Uint64(data))
		}
	}
	buf := make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, uint64(val))
	if err := proxywasm.SetSharedData(key, buf, cas); err != nil {
		IncrementSharedData(key, amount)

	}
}

// GetTracedRequestStats returns a slice of TracedRequestStats for all traced requests.
// It skips requests that have not completed.
func GetTracedRequestStats() ([]shared.TracedRequestStats, error) {
	tracedRequestsRaw, _, err := proxywasm.GetSharedData(KEY_TRACED_REQUESTS)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for traced requests: %v", err)
		return nil, err
	}
	if len(tracedRequestsRaw) == 0 || errors.Is(err, types.ErrorStatusNotFound) || shared.EmptyBytes(tracedRequestsRaw) {
		// no requests traced
		return make([]shared.TracedRequestStats, 0), nil
	}
	var tracedRequestStats []shared.TracedRequestStats
	tracedRequests := strings.Split(string(tracedRequestsRaw), " ")
	for _, traceId := range tracedRequests {
		if shared.EmptyBytes([]byte(traceId)) {
			continue
		}
		spanIdBytes, _, err := proxywasm.GetSharedData(shared.SpanIdKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v spanId: %v", traceId, err)
			return nil, err
		}
		spanId := string(spanIdBytes)
		parentSpanIdBytes, _, err := proxywasm.GetSharedData(shared.ParentSpanIdKey(traceId))
		parentSpanId := ""
		if err == nil {
			parentSpanId = string(parentSpanIdBytes)
		}

		methodBytes, _, err := proxywasm.GetSharedData(shared.MethodKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v method: %v", traceId, err)
			return nil, err
		}
		method := string(methodBytes)
		pathBytes, _, err := proxywasm.GetSharedData(shared.PathKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v path: %v", traceId, err)
			return nil, err
		}
		path := string(pathBytes)

		startTimeBytes, _, err := proxywasm.GetSharedData(shared.StartTimeKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v startTime: %v", traceId, err)
			return nil, err
		}
		startTime := int64(binary.LittleEndian.Uint64(startTimeBytes))
		endTimeBytes, _, err := proxywasm.GetSharedData(shared.EndTimeKey(traceId))
		if err != nil {
			// request hasn't completed yet, so just disregard.
			continue
		}
		var bodySize int64
		bodySizeBytes, _, err := proxywasm.GetSharedData(shared.BodySizeKey(traceId))
		if err != nil {
			// if we have an end time but no body size, set 0 to body, req just had headers
			bodySize = 0
		} else {
			bodySize = int64(binary.LittleEndian.Uint64(bodySizeBytes))
		}
		endTime := int64(binary.LittleEndian.Uint64(endTimeBytes))

		tracedRequestStats = append(tracedRequestStats, shared.TracedRequestStats{
			Method:       method,
			Path:         path,
			TraceId:      traceId,
			SpanId:       spanId,
			ParentSpanId: parentSpanId,
			StartTime:    startTime,
			EndTime:      endTime,
			BodySize:     bodySize,
		})
	}
	return tracedRequestStats, nil
}

// Get the current load conditions of all traced requests.
func GetInflightRequestStats() (map[string]shared.EndpointStats, error) {
	inflightEndpoints, _, err := proxywasm.GetSharedData(KEY_ENDPOINT_RPS_LIST)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for inflight request stats: %v", err)
		return nil, err
	}
	if len(inflightEndpoints) == 0 || errors.Is(err, types.ErrorStatusNotFound) || shared.EmptyBytes(inflightEndpoints) {
		// no requests traced
		return make(map[string]shared.EndpointStats), nil
	}
	inflightRequestStats := make(map[string]shared.EndpointStats)
	inflightEndpointsList := strings.Split(string(inflightEndpoints), ",")
	for _, endpoint := range inflightEndpointsList {
		if shared.EmptyBytes([]byte(endpoint)) {
			continue
		}
		method := strings.Split(endpoint, "@")[0]
		path := strings.Split(endpoint, "@")[1]
		inflightRequestStats[endpoint] = shared.EndpointStats{
			Inflight: shared.GetUint64SharedDataOrZero(shared.InflightCountKey(method, path)),
		}
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for endpoint %v inflight request stats: %v", endpoint, err)
		}
	}

	rpsEndpoints, _, err := proxywasm.GetSharedData(KEY_ENDPOINT_RPS_LIST)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for rps request stats: %v", err)
		return nil, err
	}
	if len(rpsEndpoints) == 0 || errors.Is(err, types.ErrorStatusNotFound) || shared.EmptyBytes(rpsEndpoints) {
		// no requests traced
		return inflightRequestStats, nil
	}
	rpsEndpointsList := strings.Split(string(rpsEndpoints), ",")
	for _, endpoint := range rpsEndpointsList {
		if shared.EmptyBytes([]byte(endpoint)) {
			continue
		}
		method := strings.Split(endpoint, "@")[0]
		path := strings.Split(endpoint, "@")[1]
		proxywasm.LogDebugf("method: %s, path: %s", method, path)
		if val, ok := inflightRequestStats[endpoint]; ok {
			val.Total = TimestampListGetRPS(method, path)
			inflightRequestStats[endpoint] = val
		} else {
			inflightRequestStats[endpoint] = shared.EndpointStats{
				Total: TimestampListGetRPS(method, path),
			}
		}
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for endpoint %v inflight request stats: %v", endpoint, err)
		}
	}

	return inflightRequestStats, nil
}

// ResetEndpointCounts : reset everything.
func ResetEndpointCounts() {
	// get list of endpoints
	endpointListBytes, cas, err := proxywasm.GetSharedData(KEY_ENDPOINT_RPS_LIST)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for endpoint rps list: %v", err)
		return
	}
	if len(endpointListBytes) == 0 || errors.Is(err, types.ErrorStatusNotFound) || shared.EmptyBytes(endpointListBytes) {
		// no requests traced
		return
	}
	endpointList := strings.Split(string(endpointListBytes), ",")
	// reset counts
	for _, endpoint := range endpointList {
		if shared.EmptyBytes([]byte(endpoint)) {
			continue
		}
		method := strings.Split(endpoint, "@")[0]
		path := strings.Split(endpoint, "@")[1]
		// reset endpoint count
		if err := proxywasm.SetSharedData(shared.EndpointCountKey(method, path), make([]byte, 8), 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data: %v", err)
			return
		}
	}
	// reset list
	if err := proxywasm.SetSharedData(KEY_ENDPOINT_RPS_LIST, make([]byte, 8), cas); err != nil {
		proxywasm.LogCriticalf("unable to set shared data: %v", err)
		return
	}
}

/*
TimestampListGetRPS will get the number of requests in the last second for the given method and path.
It can do this cheaply it just needs to get the read and write positions of the list, and then calculate
the number of requests in the last second.

The data is a comma-separated string of timestamps. we add new timestamps to the end (.append),
and evict from the front (to simulate efficiency of a queue).

The "queue size" is then updated to reflect the new size of the queue. This is returned.
*/
func TimestampListGetRPS(method string, path string) uint64 {
	// get list of timestamps
	readPosBytes, _, err := proxywasm.GetSharedData(shared.TimestampListReadPosKey(method, path))
	if err != nil {
		return 0
	}
	readPos := binary.LittleEndian.Uint64(readPosBytes)
	writePosBytes, _, err := proxywasm.GetSharedData(shared.TimestampListWritePosKey(method, path))
	if err != nil {
		return 0
	}
	writePos := binary.LittleEndian.Uint64(writePosBytes)
	queueSize := writePos - readPos
	return queueSize / 4
}
