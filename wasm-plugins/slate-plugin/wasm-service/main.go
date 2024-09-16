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

	startTime                int64
	hillclimbingEnabled      bool
	initialHillclimbStepSize int
	hillclimbIntervalSeconds uint64
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

func hillclimbEnabled() bool {
	data, _, err := proxywasm.GetSharedData(shared.KEY_HILLCLIMBING_ENABLED)
	if err != nil || string(data) != "true" {
		return false
	}
	return true
}

func (p *pluginContext) hillclimbEnabled() bool {
	data, _, err := proxywasm.GetSharedData(shared.KEY_HILLCLIMBING_ENABLED)
	if err != nil || string(data) != "true" {
		return false
	}
	if !p.hillclimbingEnabled {
		p.hillclimbingEnabled = true
		data, _, err = proxywasm.GetSharedData(shared.KEY_HILLCLIMB_INITIAL_STEPSIZE)
		dataStr := string(data)
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get hillclimb step size: %v", err)
			p.initialHillclimbStepSize = 2
		} else {
			p.initialHillclimbStepSize, err = strconv.Atoi(dataStr)
			if err != nil {
				proxywasm.LogCriticalf("Couldn't convert hillclimb step size to int: %v", err)
				p.initialHillclimbStepSize = 2
			}
		}
		data, _, err = proxywasm.GetSharedData(shared.KEY_HILLCLIMB_INTERVAL)
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get hillclimb interval: %v", err)
			p.hillclimbIntervalSeconds = 15
		} else {
			s, err := strconv.Atoi(string(data))
			if err != nil {
				proxywasm.LogCriticalf("Couldn't convert hillclimb interval to int: %v", err)
				p.hillclimbIntervalSeconds = 15
			} else {
				p.hillclimbIntervalSeconds = uint64(s)
			}
		}
	}
	return true
}

// OnTick reports load to the controller every TICK_PERIOD milliseconds.
func (p *pluginContext) OnTick() {

	//every 5 ticks, perform the hill climbing algorithm and adjust the outbound ratios.
	if p.hillclimbEnabled() {
		ticks := shared.GetUint64SharedDataOrZero(KEY_NUM_TICKS)
		if ticks%p.hillclimbIntervalSeconds == 0 {
			proxywasm.LogCriticalf("logadi-hillclimb")
			oldDist, newDist, avgLatency, regionToLatency := p.PerformHillClimb()
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
		IncrementSharedData(KEY_NUM_TICKS, 1)
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
	proxywasm.LogCriticalf("<OnTick> reqBody:\n%s", reqBody)

	proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(fmt.Sprintf("%d\n%s\n%s", totalRps, inflightStats, requestStatsStr)), make([][2]string, 0), 5000, OnTickHttpCallResponse)

}

func HillclimbHttpResponseHandler(numHeaders, bodySize, numTrailers int) {
	// todo receive validation that direction is correct from global controller
}

// callback for OnTick() http call response
func OnTickHttpCallResponse(numHeaders, bodySize, numTrailers int) {
	// receive RPS thresholds, set shared data accordingly
	hdrs, err := proxywasm.GetHttpCallResponseHeaders()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get http call response headers: %v", err)
		return
	}
	var status int
	status = 200
	for _, hdr := range hdrs {
		if hdr[0] == ":status" {
			status, err = strconv.Atoi(hdr[1])
			if err != nil {
				proxywasm.LogCriticalf("Couldn't parse :status header: %v", err)
				return
			}
		}
	}

	if status >= 400 {
		proxywasm.LogCriticalf("received ERROR http call response, status %v body size: %d", hdrs, bodySize)
	} else {
		proxywasm.LogCriticalf("received SUCCESS http call response, status %v body size: %d", hdrs, bodySize)
	}
	if bodySize == 0 {
		return
	}

	respBody, err := proxywasm.GetHttpCallResponseBody(0, bodySize)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get http call response body: %v", err)
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
		if rules, _, err := proxywasm.GetSharedData(shared.LastRecvRulesKey(mp[0], mp[1], mp[2])); err != nil || !hillclimbEnabled() || (hillclimbEnabled() && !rulesSimilar(string(rules), distStr)) {
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
				if err := proxywasm.SetSharedData(KEY_CURRENTLY_HILLCLIMBING, []byte(shared.EndpointDistributionKey(mp[0], mp[1], mp[2])), 0); err != nil {
					proxywasm.LogCriticalf("unable to set shared data for hillclimb %v: %v", shared.EndpointDistributionKey(mp[0], mp[1], mp[2]), err)
				}
			}
		} else {
			// rules exist AND we are hillclimbing AND and the rules are similar
			// if we recieved the same rules as lastRecvRulesKey, don't set endpointDistributionKey because we might be hillclimbing
			proxywasm.LogCriticalf("rules already exist for %v and are similar to recieved, skipping", methodPath)
			continue
		}
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
func (p *pluginContext) PerformHillClimb() (oldDist, newDist string, avgLatency LatencyStat, regionToLatency map[string]LatencyStat) {
	endpointToClimb, _, err := proxywasm.GetSharedData(KEY_CURRENTLY_HILLCLIMBING)
	if err != nil || string(endpointToClimb) == "NOT" {
		// nothing to hillclimb
		proxywasm.LogCriticalf("Nothing to hillclimb yet...")
		return
	}
	regions := []string{"us-west-1", "us-east-1"} // todo get regions from distribution
	svcMethodPath := strings.Split(string(endpointToClimb)[:len(endpointToClimb)-13], "@")
	svc, method, path := svcMethodPath[0], svcMethodPath[1], svcMethodPath[2]
	distribution, cas, err := proxywasm.GetSharedData(string(endpointToClimb))
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get endpoint distribution while trying to hillclimb: %v", err)
		return
	}
	proxywasm.LogCriticalf("Hillclimbing for %v, current distribution is %v", string(endpointToClimb), string(distribution))
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
	proxywasm.LogCriticalf("dividing %v by %v", curAvgLatencyTotalMs, curAvgLatencyTotalRequests)
	curAvgLatency := curAvgLatencyTotalMs / curAvgLatencyTotalRequests
	curAvgLatencyStat := LatencyStat{
		LatencyAvg: int(curAvgLatency),
		TotalReqs:  int(curAvgLatencyTotalRequests),
	}
	lastAvgLatency, err := shared.GetUint64SharedData(shared.PrevOutboundLatencyRunningAvgKey(svc, method, path))
	if err != nil {
		proxywasm.LogCriticalf("last average latency not present, starting first iteration of the algorithm...")
		// set last average latency to current average latency
		buf := make([]byte, 8)
		binary.LittleEndian.PutUint64(buf, curAvgLatency)
		if err := proxywasm.SetSharedData(shared.PrevOutboundLatencyRunningAvgKey(svc, method, path), buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't set last average latency: %v", err)
			return
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
		// set step size and direction, and change ratios
		// direction = 1 means offload more away from the current region
		// direction = 0 means keep more traffic in this region
		// step size is in percent * 100
		// direction is 1 for increase, 0 for decrease
		// initial step size is 10, direction is 1
		stepSize, direction := p.initialHillclimbStepSize, 1
		binary.LittleEndian.PutUint64(buf, uint64(stepSize))
		if err := proxywasm.SetSharedData(KEY_HILLCLIMB_STEPSIZE, buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't set step size: %v", err)
			return
		}
		binary.LittleEndian.PutUint64(buf, uint64(direction))
		if err := proxywasm.SetSharedData(KEY_HILLCLIMB_DIRECTION, buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't set direction: %v", err)
			return
		}
		// alter the distribution with the step size and direction
		// we need to parse the distribution and adjust the percentages
		newDistr := p.AdjustDistribution(stepSize, direction, string(distribution))
		if err := proxywasm.SetSharedData(string(endpointToClimb), []byte(newDistr), cas); err != nil {
			proxywasm.LogCriticalf("Couldn't set new distribution: %v", err)
			return
		} else {
			proxywasm.LogCriticalf("(First iteration) Adjusted distribution from\n%v\nto\n%v\n", string(distribution), newDistr)
		}
		return string(distribution), newDistr, curAvgLatencyStat, regionToLatency
	}
	proxywasm.LogCriticalf("Last average latency: %v, current average latency: %v (%v samples)", lastAvgLatency, curAvgLatency, curAvgLatencyTotalRequests)
	// set last average latency to current average latency
	buf = make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, curAvgLatency)
	if err := proxywasm.SetSharedData(shared.PrevOutboundLatencyRunningAvgKey(svc, method, path), buf, 0); err != nil {
		proxywasm.LogCriticalf("Couldn't set last average latency: %v", err)
		return
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
	stepSize, err := shared.GetUint64SharedData(KEY_HILLCLIMB_STEPSIZE)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get step size: %v", err)
		return
	}
	directionUint, err := shared.GetUint64SharedData(KEY_HILLCLIMB_DIRECTION)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get direction: %v", err)
		return
	}
	var direction int
	if directionUint == 0 {
		direction = -1
	} else {
		direction = 1
	}

	// if the current latency is less than the last latency, we keep the direction and adjust the
	// distribution by the step size.
	// if the current latency is greater than the last latency, we reverse the direction and adjust the
	// distribution by half the last step size.
	// if the current latency is close to the last latency, we complete the hill climb.
	//diff := curAvgLatency - lastAvgLatency
	//latencyThresh := 5
	//if math.Abs(float64(diff)) < float64(latencyThresh) {
	//	// we've completed the hill climb
	//	proxywasm.LogCriticalf("Completed hill climb for %v (old latency %v, new latency %v)", string(endpointToClimb), lastAvgLatency, curAvgLatency)
	//	// reset the hill climb
	//	if err := proxywasm.SetSharedData(KEY_CURRENTLY_HILLCLIMBING, []byte("NOT"), 0); err != nil {
	//		proxywasm.LogCriticalf("Couldn't reset hill climb: %v", err)
	//		return
	//	}
	//	return
	//}

	if curAvgLatency < lastAvgLatency {
		// keep direction
		newDistr := p.AdjustDistribution(int(stepSize), int(direction), string(distribution))
		if err := proxywasm.SetSharedData(string(endpointToClimb), []byte(newDistr), cas); err != nil {
			proxywasm.LogCriticalf("Couldn't set new distribution: %v", err)
			return
		} else {
			proxywasm.LogCriticalf("(keeping direction %v, stepsize %v) Adjusted distribution from\n%v\nto\n%v\n", direction, stepSize, string(distribution), newDistr)
		}
		return string(distribution), newDistr, curAvgLatencyStat, regionToLatency
	} else {
		// reverse direction
		//var newStep int
		//if stepSize <= 3 {
		//	newStep = 5
		//} else {
		//	newStep = int(stepSize / 2)
		//}
		newStep := stepSize // test to see if we oscillate
		newDirection := int(direction * -1)
		proxywasm.LogCriticalf("changing step size from %v to %v, direction from %v to %v", stepSize, newStep, direction, newDirection)
		newDistr := p.AdjustDistribution(int(newStep), newDirection, string(distribution))
		if err := proxywasm.SetSharedData(string(endpointToClimb), []byte(newDistr), cas); err != nil {
			proxywasm.LogCriticalf("Couldn't set new distribution: %v", err)
			return
		} else {
			proxywasm.LogCriticalf("(reversing direction) Adjusted distribution from\n%v\nto\n%v\n", string(distribution), newDistr)
		}
		// set new step size and direction
		buf := make([]byte, 8)
		binary.LittleEndian.PutUint64(buf, uint64(newStep))
		if err := proxywasm.SetSharedData(KEY_HILLCLIMB_STEPSIZE, buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't set new step size: %v", err)
			return
		}
		if newDirection == -1 {
			newDirection = 0
		}
		binary.LittleEndian.PutUint64(buf, uint64(newDirection))
		if err := proxywasm.SetSharedData(KEY_HILLCLIMB_DIRECTION, buf, 0); err != nil {
			proxywasm.LogCriticalf("Couldn't set new direction: %v", err)
			return
		}
		return string(distribution), newDistr, curAvgLatencyStat, regionToLatency
	}
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

func saveEndpointStatsForTrace(traceId string, stats map[string]shared.EndpointStats) {
	str := ""
	for k, v := range stats {
		str += fmt.Sprintf("%s,%d,%d", k, v.Total, v.Inflight) + "|"
	}
	if err := proxywasm.SetSharedData(shared.EndpointInflightStatsKey(traceId), []byte(str), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v endpointInflightStats: %v %v", traceId, str, err)
	}
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
