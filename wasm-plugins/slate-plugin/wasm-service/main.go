package main

import (
	"encoding/binary"
	"errors"
	"fmt"
	"github.com/adiprerepa/SLATE/slate-plugin/shared"
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
	KEY_INFLIGHT_REQ_COUNT     = "slate_inflight_request_count"
	KEY_RPS_THRESHOLDS         = "slate_rps_threshold"
	KEY_HASH_MOD               = "slate_hash_mod"
	// this is in millis
	AGGREGATE_REQUEST_LATENCY = "slate_last_second_latency_avg"
	KEY_RPS_SHARED_QUEUE      = "slate_rps_shared_queue"
	KEY_RPS_SHARED_QUEUE_SIZE = "slate_rps_shared_queue_size"

	// this is the reporting period in millis
	TICK_PERIOD              = 1000
	HILLCLIMB_LATENCY_PERIOD = 3000

	// Hash mod for frequency of request tracing.
	DEFAULT_HASH_MOD = 1000000
	KEY_NUM_TICKS    = "slate_key_num_ticks"

	KEY_MATCH_DISTRIBUTION = "slate_match_distribution"
)

var (
	ALL_KEYS = []string{KEY_INFLIGHT_REQ_COUNT, shared.KEY_REQUEST_COUNT, KEY_RPS_THRESHOLDS, KEY_HASH_MOD, AGGREGATE_REQUEST_LATENCY,
		shared.KEY_TRACED_REQUESTS, KEY_MATCH_DISTRIBUTION, KEY_INFLIGHT_ENDPOINT_LIST, shared.KEY_ENDPOINT_RPS_LIST, KEY_RPS_SHARED_QUEUE, KEY_RPS_SHARED_QUEUE_SIZE}
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

	tickPeriod                 int64
	hillclimbLatencyTickPeriod int64

	region string

	startTime int64
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {

	tickPeriod := os.Getenv("TICK_PERIOD_SECONDS")
	tps := int64(1)
	if tickPeriod != "" {
		tmp, _ := strconv.Atoi(tickPeriod)
		tps = int64(tmp)
	}
	p.tickPeriod = tps
	htps := int64(2)
	hillclimbLatencyTickPeriod := os.Getenv("HILLCLIMB_LATENCY_PERIOD_SECONDS")
	if hillclimbLatencyTickPeriod != "" {
		tmp, _ := strconv.Atoi(hillclimbLatencyTickPeriod)
		htps = int64(tmp)
	}
	p.hillclimbLatencyTickPeriod = htps
	if err := proxywasm.SetTickPeriodMilliSeconds(1000); err != nil {
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

	if time.Now().Unix()%p.hillclimbLatencyTickPeriod == 0 {
		p.ReportHillclimbingLatency()
	}

	totalRps := shared.GetUint64SharedDataOrZero(shared.KEY_REQUEST_COUNT)
	if err := proxywasm.SetSharedData(shared.KEY_REQUEST_COUNT, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset request count: %v", err)
	}

	// get the current per-endpoint load conditions
	inflightStats := ""
	inflightStatsMap, err := shared.GetEndpointLoadConditions()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get inflight request stats: %v", err)
		return
	}

	for k, v := range inflightStatsMap {
		//for k, v := range inflightStatsMap {
		inflightStats += strings.Join([]string{k, strconv.Itoa(int(v.Total)), strconv.Itoa(int(v.Inflight))}, ",")
		//inflightStats += strings.Join([]string{k, strconv.Itoa(int(totalRps)), strconv.Itoa(int(totalRps))}, ",")
		inflightStats += "|"
	}

	var requestStats []shared.TracedRequestStats
	var skipped int
	if time.Now().Unix()%p.tickPeriod == 0 {
		requestStats, skipped, err = GetTracedRequestStats()
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get traced request stats: %v", err)
			return
		}
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

	if time.Now().Unix()%p.tickPeriod == 0 {
		if err := proxywasm.SetSharedData(shared.KEY_TRACED_REQUESTS, make([]byte, 8), 0); err != nil {
			proxywasm.LogCriticalf("Couldn't reset traced requests: %v", err)
		}
		ResetEndpointCounts()
	}
	if err := proxywasm.SetSharedData(shared.KEY_ENDPOINT_RPS_LIST, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset endpoint rps list: %v", err)
	}

	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/proxyLoad"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
		{"x-slate-region", p.region},
	}

	reqBody := fmt.Sprintf("reqCount\n%d\n\ninflightStats\n%s\nrequestStats\n%s", 0, inflightStats, requestStatsStr)
	proxywasm.LogCriticalf("<OnTick (noid %v, skipped %v)> reqBody:\n%s", noId, skipped, reqBody)

	proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(fmt.Sprintf("%d\n%s\n%s", totalRps, inflightStats, requestStatsStr)), make([][2]string, 0), 5000, p.OnTickHttpCallResponse)
}

// ReportHillclimbingLatency will report the average latency of all (1) inbound requests and (2) outbound requests (by region).
// The inbound requests are used in the global controller, and the outbound request latencies are used for visibility.
func (p *pluginContext) ReportHillclimbingLatency() {
	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/hillclimbingLatency"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
		{"x-slate-region", p.region},
	}

	outboundEndpointsStr, _, err := proxywasm.GetSharedData(shared.KEY_OUTBOUND_ENDPOINT_LIST)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for outbound endpoints: %v", err)
		return
	}
	proxywasm.SetSharedData(shared.KEY_OUTBOUND_ENDPOINT_LIST, make([]byte, 8), 0)
	hasOutbound, hasInbound := true, true
	if len(outboundEndpointsStr) == 0 || errors.Is(err, types.ErrorStatusNotFound) || shared.EmptyBytes(outboundEndpointsStr) {
		hasOutbound = false
	}
	inboundEndpointsStr, _, err := proxywasm.GetSharedData(shared.KEY_INBOUND_ENDPOINT_LIST)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for inbound endpoints: %v", err)
		return
	}
	if len(inboundEndpointsStr) == 0 || errors.Is(err, types.ErrorStatusNotFound) || shared.EmptyBytes(inboundEndpointsStr) {
		hasInbound = false
	}
	proxywasm.SetSharedData(shared.KEY_INBOUND_ENDPOINT_LIST, make([]byte, 8), 0)
	reqBody := ""
	if hasOutbound {
		reqBody += "outbound\n"
		outboundEndpoints := strings.Split(string(outboundEndpointsStr), ",")
		for _, endpoint := range outboundEndpoints {
			if shared.EmptyBytes([]byte(endpoint)) {
				continue
			}
			mp := strings.Split(endpoint, "@")
			if len(mp) != 3 {
				continue
			}
			svc, method, path := mp[0], mp[1], mp[2]
			totalLatency := shared.GetUint64SharedDataOrZero(shared.OutboundLatencyRunningAvgKey(svc, method, path))
			totalReqs := shared.GetUint64SharedDataOrZero(shared.OutboundLatencyTotalRequestsKey(svc, method, path))
			// reset the total latency and total requests
			nv := 0
			buf := make([]byte, 8)
			binary.LittleEndian.PutUint64(buf, uint64(nv))
			if err := proxywasm.SetSharedData(shared.OutboundLatencyRunningAvgKey(svc, method, path), buf, 0); err != nil {
				proxywasm.LogCriticalf("Couldn't reset total latency: %v", err)
			}
			if err := proxywasm.SetSharedData(shared.OutboundLatencyTotalRequestsKey(svc, method, path), buf, 0); err != nil {
				proxywasm.LogCriticalf("Couldn't reset total requests: %v", err)
			}
			avgLatency := 0
			if totalReqs != 0 {
				avgLatency = int(totalLatency / totalReqs)
			}
			reqBody += fmt.Sprintf("%s %s %s %d %d\n", svc, method, path, avgLatency, totalReqs)
		}
	}
	if hasInbound {
		reqBody += "inbound\n"
		inboundEndpoints := strings.Split(string(inboundEndpointsStr), ",")
		for _, endpoint := range inboundEndpoints {
			if shared.EmptyBytes([]byte(endpoint)) {
				continue
			}
			mp := strings.Split(endpoint, "@")
			if len(mp) != 2 {
				continue
			}
			method, path := mp[0], mp[1]
			totalLatency := shared.GetUint64SharedDataOrZero(shared.InboundLatencyRunningAvgKey(method, path))
			totalReqs := shared.GetUint64SharedDataOrZero(shared.InboundLatencyTotalRequestsKey(method, path))
			totalM2Bytes, _, err := proxywasm.GetSharedData(shared.InboundLatencyM2Key(method, path))
			totalM2 := "0"
			if err == nil {
				totalM2 = string(totalM2Bytes)
			}

			// reset the total latency and total requests
			nv := 0
			buf := make([]byte, 8)
			binary.LittleEndian.PutUint64(buf, uint64(nv))
			if err := proxywasm.SetSharedData(shared.InboundLatencyRunningAvgKey(method, path), buf, 0); err != nil {
				proxywasm.LogCriticalf("Couldn't reset total latency: %v", err)
			}
			if err := proxywasm.SetSharedData(shared.InboundLatencyTotalRequestsKey(method, path), buf, 0); err != nil {
				proxywasm.LogCriticalf("Couldn't reset total requests: %v", err)
			}
			if err := proxywasm.SetSharedData(shared.InboundLatencyM2Key(method, path), []byte("0"), 0); err != nil {
				proxywasm.LogCriticalf("Couldn't reset total requests: %v", err)
			}
			avgLatency := 0
			if totalReqs != 0 {
				avgLatency = int(totalLatency / totalReqs)
			}
			reqBody += fmt.Sprintf("%s %s %d %d %s\n", method, path, avgLatency, totalReqs, totalM2)
		}
		reqBody += "inboundLatencies\n\n"
		//for _, endpoint := range inboundEndpoints {
		//	if shared.EmptyBytes([]byte(endpoint)) {
		//		continue
		//	}
		//	mp := strings.Split(endpoint, "@")
		//	if len(mp) != 2 {
		//		continue
		//	}
		//	method, path := mp[0], mp[1]
		//	latencyListBytes, _, err := proxywasm.GetSharedData(shared.InboundLatencyListKey(method, path))
		//	if err != nil {
		//		proxywasm.LogCriticalf("Couldn't get shared data for inbound latency list: %v", err)
		//		continue
		//	}
		//	if err := proxywasm.SetSharedData(shared.InboundLatencyListKey(method, path), make([]byte, 8), 0); err != nil {
		//		proxywasm.LogCriticalf("Couldn't reset inbound latency list: %v", err)
		//	}
		//	latencyList := strings.TrimSpace(string(latencyListBytes))
		//	reqBody += fmt.Sprintf("%s %s %s\n", method, path, latencyList)
		//}
	}

	proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(reqBody), make([][2]string, 0), 5000, p.HillclimbLatencyHttpResponseHandler)
}

func (p *pluginContext) HillclimbLatencyHttpResponseHandler(numHeaders, bodySize, numTrailers int) {
	respBody, err := parseHttpResponse("HillclimbLatency", numHeaders, bodySize, numTrailers)
	if err != nil {
		proxywasm.LogCriticalf("[HillclimbLatency] Couldn't parse http call response: %v", err)
		return
	}
	proxywasm.LogCriticalf("[HillclimbLatency] received http call response: %s", respBody)
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

		if err := proxywasm.SetSharedData(shared.EndpointDistributionKey(mp[0], mp[1], mp[2]), []byte(distStr), 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data for endpoint distribution %v: %v", methodPath, err)
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

// GetTracedRequestStats returns a slice of TracedRequestStats for all traced requests.
// It skips requests that have not completed.
func GetTracedRequestStats() ([]shared.TracedRequestStats, int, error) {
	tracedRequestsRaw, _, err := proxywasm.GetSharedData(shared.KEY_TRACED_REQUESTS)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for traced requests: %v", err)
		return nil, 0, err
	}
	if len(tracedRequestsRaw) == 0 || errors.Is(err, types.ErrorStatusNotFound) || shared.EmptyBytes(tracedRequestsRaw) {
		// no requests traced
		return make([]shared.TracedRequestStats, 0), 0, nil
	}
	var tracedRequestStats []shared.TracedRequestStats
	tracedRequests := strings.Split(string(tracedRequestsRaw), " ")
	skipped := 0
	for _, traceId := range tracedRequests {
		if shared.EmptyBytes([]byte(traceId)) {
			continue
		}
		spanIdBytes, _, err := proxywasm.GetSharedData(shared.SpanIdKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v spanId: %v", traceId, err)
			skipped++
			continue
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
			skipped++
			continue
		}
		method := string(methodBytes)
		pathBytes, _, err := proxywasm.GetSharedData(shared.PathKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v path: %v", traceId, err)
			skipped++
			continue
		}
		path := string(pathBytes)

		startTimeBytes, _, err := proxywasm.GetSharedData(shared.StartTimeKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v startTime: %v", traceId, err)
			skipped++
			continue
		}
		startTime := int64(binary.LittleEndian.Uint64(startTimeBytes))
		endTimeBytes, _, err := proxywasm.GetSharedData(shared.EndTimeKey(traceId))
		if err != nil {
			// request hasn't completed yet, so just disregard.
			skipped++
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
	return tracedRequestStats, skipped, nil
}

// ResetEndpointCounts : reset everything.
func ResetEndpointCounts() {
	// get list of endpoints
	endpointListBytes, cas, err := proxywasm.GetSharedData(shared.KEY_ENDPOINT_RPS_LIST)
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
	if err := proxywasm.SetSharedData(shared.KEY_ENDPOINT_RPS_LIST, make([]byte, 8), cas); err != nil {
		proxywasm.LogCriticalf("unable to set shared data: %v", err)
		return
	}
}
