package main

import (
	"crypto/md5"
	"encoding/binary"
	"errors"
	"fmt"
	"math/rand"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
	_ "github.com/wasilibs/nottinygc"
)

const (
	KEY_INFLIGHT_ENDPOINT_LIST = "slate_inflight_endpoint_list"
	KEY_ENDPOINT_RPS_LIST      = "slate_endpoint_rps_list"
	KEY_INFLIGHT_REQ_COUNT     = "slate_inflight_request_count"
	KEY_REQUEST_COUNT          = "slate_rps"
	KEY_LAST_RESET             = "slate_last_reset"
	KEY_RPS_THRESHOLDS         = "slate_rps_threshold"
	KEY_HASH_MOD               = "slate_hash_mod"
	KEY_TRACED_REQUESTS        = "slate_traced_requests"
	// this is in millis
	AGGREGATE_REQUEST_LATENCY = "slate_last_second_latency_avg"
	KEY_RPS_SHARED_QUEUE      = "slate_rps_shared_queue"
	KEY_RPS_SHARED_QUEUE_SIZE = "slate_rps_shared_queue_size"
	// (gangmuk): changed to 2 seconds to capture more inflights.
	TICK_PERIOD = 1000
	// nor_len     = 1000 / TICK_PERIOD
	DEFAULT_HASH_MOD = 10

	KEY_MATCH_DISTRIBUTION = "slate_match_distribution"
)

/*
todo(adiprerepa)
  lots of bloat due to the fact that we can't share data between plugins.
  to sync data, we need to use shared data, which is a pretty bloated api for a simple k/v store.
  create getorfail() and setorfail() methods to reduce the amount of code duplication.
*/

var (
	ALL_KEYS = []string{KEY_INFLIGHT_REQ_COUNT, KEY_REQUEST_COUNT, KEY_LAST_RESET, KEY_RPS_THRESHOLDS, KEY_HASH_MOD, AGGREGATE_REQUEST_LATENCY,
		KEY_TRACED_REQUESTS, KEY_MATCH_DISTRIBUTION, KEY_INFLIGHT_ENDPOINT_LIST, KEY_ENDPOINT_RPS_LIST, KEY_RPS_SHARED_QUEUE, KEY_RPS_SHARED_QUEUE_SIZE}
	cur_idx      int
	latency_list []int64
	ts_list      []int64
)

func main() {
	proxywasm.SetVMContext(&vmContext{})
	rand.Seed(time.Now().UnixNano())
	// rand.Seed(1234)

}

type vmContext struct {
	// Embed the default VM context here,
	// so that we don't need to reimplement all the methods.
	types.DefaultVMContext
}

type RpsThreshold struct {
	Threshold uint64
	// for key x-slate-remotecluster
	HeaderValue string
}

type TracedRequestStats struct {
	method       string
	path         string
	traceId      string
	spanId       string
	parentSpanId string
	startTime    int64
	endTime      int64
	bodySize     int64
	firstLoad    int64
	rps          int64
}

type EndpointStats struct {
	Inflight uint64
	Total    uint64
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

	region        string
	rpsThresholds []RpsThreshold

	startTime int64
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

// OnTick every second. Reset numRequests every tick and increment request on every http request.
func (p *pluginContext) OnTick() {
	/*
			send current RPS and receive RPS threshold
			this is called multiple times (due to the nature of the envoy threading model), so we need
		 		to make sure we only send the request count once per tick.
			check KEY_LAST_RESET (uint64 millis) to see if one of our peers already reached.
			if not, send request count and set KEY_LAST_RESET to current time.
	*/

	// TODO: OnTick is called multiple times every tick period, mutex does not solve it.
	//avg_latency := int64(calculateAverage(latency_list))
	//tail_latency := calculatePercentile(latency_list, 99)
	//proxywasm.LogCriticalf("OnTick,latency summary,avg_latency,%d,99th_latency,%d,", avg_latency, tail_latency)
	latency_list = latency_list[:0]

	data, cas, err := proxywasm.GetSharedData(KEY_LAST_RESET)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	lastReset := int64(binary.LittleEndian.Uint64(data))
	currentNanos := time.Now().UnixMilli()
	// allow for some jitter - this is bad and racy and hardcoded
	// if lastReset >= (currentNanos - (TICK_PERIOD / 2)) {
	if (TICK_PERIOD / 2) >= (currentNanos - lastReset) {
		// we've been reset. don't need to stream RPS
		return
	}
	buf := make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, uint64(currentNanos))
	if err := proxywasm.SetSharedData(KEY_LAST_RESET, buf, cas); err != nil {
		if errors.Is(err, types.ErrorStatusCasMismatch) {
			// we've been reset by another peer while we were trying to set the value.
			return
		}
	}

	// reset request count back to 0
	data, cas, err = proxywasm.GetSharedData(KEY_REQUEST_COUNT)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	reqCount := binary.LittleEndian.Uint64(data)
	//proxywasm.LogCriticalf("OnTick, reqCount: %d", reqCount)
	if TICK_PERIOD > 1000 {
		reqCount = reqCount * 1000 / TICK_PERIOD
	}
	buf = make([]byte, 8)
	// set request count back to 0
	if err := proxywasm.SetSharedData(KEY_REQUEST_COUNT, buf, cas); err != nil {
		if errors.Is(err, types.ErrorStatusCasMismatch) {
			// this should *never* happen.
			proxywasm.LogCriticalf("CAS Mismatch on RPS, failing: %v", err)
		}
		return
	}

	inflightStats := ""
	inflightStatsMap, err := GetInflightRequestStats()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get inflight request stats: %v", err)
		return
	}
	for k, v := range inflightStatsMap {
		inflightStats += strings.Join([]string{k, strconv.Itoa(int(v.Total)), strconv.Itoa(int(v.Inflight))}, ",")
		inflightStats += "|"
	}

	requestStats, err := GetTracedRequestStats()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get traced request stats: %v", err)
		return
	}
	// unbelievably shitty but what can you do if you don't have gRPC :)
	requestStatsStr := ""
	for _, stat := range requestStats {
		endpointInflightStatsBytes, _, err := proxywasm.GetSharedData(endpointInflightStatsKey(stat.traceId))
		endpointInflightStats := ""
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v endpoint inflight stats: %v", stat.traceId, err)
			endpointInflightStats = "NOT FOUND"
		} else {
			endpointInflightStats = string(endpointInflightStatsBytes)
		}
		requestStatsStr += fmt.Sprintf("%s %s %s %s %s %s %s %d %d %d %s\n", p.region, p.serviceName, stat.method, stat.path, stat.traceId, stat.spanId, stat.parentSpanId,
			stat.startTime, stat.endTime, stat.bodySize, endpointInflightStats)
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

	// print ontick results
	data, cas, err = proxywasm.GetSharedData(KEY_INFLIGHT_REQ_COUNT)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	//num_cur_inflight_req := int64(binary.LittleEndian.Uint64(data))
	//proxywasm.LogCriticalf("OnTick, num inflight request: %d", num_cur_inflight_req)

	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/proxyLoad"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
		{"x-slate-region", p.region},
	}

	reqBody := fmt.Sprintf("reqCount\n%d\n\ninflightStats\n%s\nrequestStats\n%s", reqCount, inflightStats, requestStatsStr)
	proxywasm.LogCriticalf("<OnTick>\nreqBody:\n%s", reqBody)

	proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(fmt.Sprintf("%d\n%s\n%s", reqCount, inflightStats, requestStatsStr)), make([][2]string, 0), 5000, OnTickHttpCallResponse)

}

// Override types.DefaultPluginContext.
func (p *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{contextID: contextID, pluginContext: p}
}

type httpContext struct {
	// Embed the default http context here,
	// so that we don't need to reimplement all the methods.
	types.DefaultHttpContext
	contextID     uint32
	pluginContext *pluginContext
}

func (ctx *httpContext) OnHttpRequestHeaders(int, bool) types.Action {
	// Sampling
	// if rand.Float64() > 0.1 {
	traceId, err := proxywasm.GetHttpRequestHeader("x-b3-traceid")
	if err != nil {
		return types.ActionContinue
	}

	reqMethod, err := proxywasm.GetHttpRequestHeader(":method")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get :method request header: %v", err)
		return types.ActionContinue
	}
	reqPath, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get :path request header: %v", err)
		return types.ActionContinue
	}
	reqPath = strings.Split(reqPath, "?")[0]
	reqAuthority, err := proxywasm.GetHttpRequestHeader(":authority")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get :authority request header: %v", err)
		return types.ActionContinue
	}
	dst := strings.Split(reqAuthority, ":")[0]

	// policy enforcement
	if !strings.HasPrefix(ctx.pluginContext.serviceName, dst) && !strings.HasPrefix(dst, "node") {
		// the request is originating from this sidecar to another service
		// perform routing magic
		// get endpoint distribution
		endpointDistribution, _, err := proxywasm.GetSharedData(endpointDistributionKey(dst, reqMethod, reqPath))
		//proxywasm.LogCriticalf("OnHttpRequestHeaders, endpoint distribution for %s %s: %s", reqMethod, reqPath, endpointDistribution)
		proxywasm.AddHttpRequestHeader("x-slate-routefrom", region)
		//proxywasm.LogCriticalf("OnHttpRequestHeaders, x-slate-routefrom set to %s", region)
		if err != nil {
			// no rules available yet.
			//proxywasm.LogCriticalf("No rules available for endpoint %s %s to %s", reqMethod, reqPath, dst)
			// proxywasm.LogCriticalf("Set x-slate-routeto header to local region: %s", region)
			proxywasm.AddHttpRequestHeader("x-slate-routeto", region)
		} else {
			coin := rand.Float64()
			total := 0.0
			distLines := strings.Split(string(endpointDistribution), "\n")
			for _, line := range distLines {
				lineS := strings.Split(line, " ")
				targetRegion := lineS[0]
				pct, err := strconv.ParseFloat(lineS[1], 64)
				if err != nil {
					proxywasm.LogCriticalf("Couldn't parse endpoint distribution line: %v", err)
					return types.ActionContinue
				}
				total += pct
				if coin <= total {
					// proxywasm.LogCriticalf("OnHttpRequestHeaders, coin,%f, total,%f, targetRegion,%s", coin, total, targetRegion)
					proxywasm.AddHttpRequestHeader("x-slate-routeto", targetRegion)
					proxywasm.LogCriticalf("OnHttpRequestHeaders coin success: %s%s, x-slate-routefrom, %s, x-slate-routeto set to %s (%.2f%% chance)", reqMethod, reqPath, region, targetRegion, pct*100)
					break
				}
			}
		}
		return types.ActionContinue
	}

	// bookkeeping to make sure we don't double count requests. decremented in OnHttpStreamDone
	IncrementSharedData(inboundCountKey(traceId), 1)

	// increment request count for this tick period
	IncrementSharedData(KEY_REQUEST_COUNT, 1)
	// increment total number of inflight requests
	IncrementSharedData(KEY_INFLIGHT_REQ_COUNT, 1)

	// enqueue request in endpoint queue and total rps queue
	//var endpointQueueId uint32
	//endpointQueueId, err = proxywasm.ResolveSharedQueue("", sharedQueueKey(reqMethod, reqPath))
	//if err != nil {
	//	// create queue
	//	endpointQueueId, err = proxywasm.RegisterSharedQueue(sharedQueueKey(reqMethod, reqPath))
	//	if err != nil {
	//		// we're fucked anyway
	//		proxywasm.LogCriticalf("unable to create shared queue: %v", err)
	//	}
	//	binary.LittleEndian.PutUint64(buf, uint64(0))
	//	if err := proxywasm.SetSharedData(sharedQueueSizeKey(reqMethod, reqPath), buf, 0); err != nil {
	//		proxywasm.LogCriticalf("unable to set queue size: %v", err)
	//	}
	//}
	//rpsQueueId, err := proxywasm.ResolveSharedQueue("", KEY_RPS_SHARED_QUEUE)
	//curTime := time.Now().UnixMilli()
	ctx.TimestampListAdd(reqMethod, reqPath)
	// convert cutTime to buf
	//binary.LittleEndian.PutUint64(buf, uint64(curTime))
	//if err := proxywasm.EnqueueSharedQueue(endpointQueueId, buf); err != nil {
	//	proxywasm.LogCriticalf("OnHttpRequestHeaders: unable to enqueue current time to endpoint queue %v: %v", sharedQueueKey(reqMethod, reqPath), err)
	//}
	//if err := proxywasm.EnqueueSharedQueue(rpsQueueId, buf); err != nil {
	//	proxywasm.LogCriticalf("OnHttpRequestHeaders: unable to enqueue current time to shared RPS queue: %v", err)
	//}
	//if err := proxywasm.EnqueueSharedQueue(endpointQueueId, buf); err != nil {
	//	proxywasm.LogCriticalf("OnHttpRequestHeaders: unable to enqueue current time to endpoint queue %v: %v", sharedQueueKey(reqMethod, reqPath), err)
	//}
	//if err := proxywasm.EnqueueSharedQueue(rpsQueueId, buf); err != nil {
	//	proxywasm.LogCriticalf("OnHttpRequestHeaders: unable to enqueue current time to shared RPS queue: %v", err)
	//}
	//IncrementSharedData(sharedQueueSizeKey(reqMethod, reqPath), 2)
	//IncrementSharedData(KEY_RPS_SHARED_QUEUE_SIZE, 2)

	//endpointRPS := SharedQueueGetRPS(sharedQueueKey(reqMethod, reqPath), sharedQueueSizeKey(reqMethod, reqPath))
	//totalRPS := SharedQueueGetRPS(KEY_RPS_SHARED_QUEUE, KEY_RPS_SHARED_QUEUE_SIZE)

	if tracedRequest(traceId) {
		// we need to record start and end time
		// proxywasm.LogCriticalf("tracing request: %s", traceId)
		spanId, _ := proxywasm.GetHttpRequestHeader("x-b3-spanid")
		parentSpanId, _ := proxywasm.GetHttpRequestHeader("x-b3-parentspanid")
		bSizeStr, err := proxywasm.GetHttpRequestHeader("Content-Length")
		if err != nil {
			bSizeStr = "0"
		}
		bodySize, _ := strconv.Atoi(bSizeStr)
		if err := AddTracedRequest(reqMethod, reqPath, traceId, spanId, parentSpanId, time.Now().UnixMilli(), bodySize); err != nil {
			proxywasm.LogCriticalf("unable to add traced request: %v", err)
			return types.ActionContinue
		}
		IncrementInflightCount(reqMethod, reqPath, 1)
		// save current load to shareddata
		inflightStats, err := GetInflightRequestStats()
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get inflight request stats: %v", err)
			return types.ActionContinue
		}
		saveEndpointStatsForTrace(traceId, inflightStats)
	}
	return types.ActionContinue
}

// OnHttpStreamDone is called when the stream is about to close.
// We use this to record the end time of the traced request.
// Since all responses are treated equally, regardless of whether
// they come from upstream or downstream, we need to do some clever
// bookkeeping and only record the end time for the last response.
func (ctx *httpContext) OnHttpStreamDone() {
	// get x-request-id from request headers and lookup entry time
	traceId, err := proxywasm.GetHttpRequestHeader("x-b3-traceid")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header x-b3-traceid: %v", err)
		return
	}

	// endtime should be recorded when the LAST response is received not the first response. It seems like it records the endtime on the first response.
	inbound, err := GetUint64SharedData(inboundCountKey(traceId))
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data for inboundCountKey traceId %v load: %v", traceId, err)
		return
	}

	reqAuth, err := proxywasm.GetHttpRequestHeader(":authority")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header :authority : %v", err)
		return
	}
	dst := strings.Split(reqAuth, ":")[0]

	if !strings.HasPrefix(ctx.pluginContext.serviceName, dst) && !strings.HasPrefix(dst, "node") {
		return
	}
	if inbound != 1 {
		// decrement and get out
		IncrementSharedData(inboundCountKey(traceId), -1)
		return
	}

	IncrementSharedData(KEY_INFLIGHT_REQ_COUNT, -1)

	reqMethod, err := proxywasm.GetHttpRequestHeader(":method")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header :method : %v", err)
		return
	}
	reqPath, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header :path : %v", err)
		return
	}
	reqPath = strings.Split(reqPath, "?")[0]
	IncrementInflightCount(reqMethod, reqPath, -1)

	currentTime := time.Now().UnixMilli()
	endTimeBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(endTimeBytes, uint64(currentTime))
	if err := proxywasm.SetSharedData(endTimeKey(traceId), endTimeBytes, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v endTime: %v %v", traceId, currentTime, err)
	}

	// proxywasm.LogCriticalf("e2e_latency, %d", lat)
}

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
	//proxywasm.LogCriticalf("received http call response, status %v body size: %d", hdrs, bodySize)
	if status >= 400 {
		proxywasm.LogCriticalf("received ERROR http call response, status %v body size: %d", hdrs, bodySize)
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
		metrics-fake-ingress@GET@/start, metrics-handler@GET@/detectAnomalies, us-west-1, us-west-1, 0.6
		metrics-fake-ingress@GET@/start, metrics-handler@GET@/detectAnomalies, us-west-1, us-east-1, 0.4
		metrics-fake-ingress@GET@/start, metrics-handler@GET@/detectAnomalies, us-east-1, us-east-1, 0.1
		metrics-fake-ingress@GET@/start, metrics-handler@GET@/detectAnomalies, us-east-1, us-west-1, 0.9
	*/
	// method@path -> region -> pct
	proxywasm.LogCriticalf("received http call response: %s", bodyLines)
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
		//endpointKey := dstSvcMethodPath[0] + "@" dstSvcMethodPath[1] + "@" + dstSvcMethodPath[2]
		if _, ok := distrs[lineSplit[1]]; !ok {
			distrs[lineSplit[1]] = map[string]string{}
		}
		distrs[lineSplit[1]][lineSplit[3]] = lineSplit[4]
	}
	proxywasm.LogCriticalf("pushed rules:\n%v", distrs)
	for methodPath, distr := range distrs {
		distStr := ""
		for region, pct := range distr {
			distStr += fmt.Sprintf("%s %s\n", region, pct)
		}
		mp := strings.Split(methodPath, "@")
		proxywasm.LogCriticalf("setting ENDPOINT DIST %v: %v", endpointDistributionKey(mp[0], mp[1], mp[2]), distStr)
		if err := proxywasm.SetSharedData(endpointDistributionKey(mp[0], mp[1], mp[2]), []byte(distStr), 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data for endpoint distribution %v: %v", methodPath, err)
		}
	}
}

func SharedQueueGetRPS(queueKey string, queueSizeKey string) uint64 {
	queueId, err := proxywasm.ResolveSharedQueue("", queueKey)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't resolve shared queue %v: %v", queueKey, err)
		return 0
	}
	timeMillisCutoff := time.Now().UnixMilli() - 1000
	var cas uint32
	queueSizeBuf, cas, err := proxywasm.GetSharedData(queueSizeKey)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data for queue size: %v", err)
		return 0
	}
	// convert queueSize to int
	queueSize := binary.LittleEndian.Uint64(queueSizeBuf)
	//proxywasm.LogCriticalf("queueSize: %v", queueSize)
	for queueSize > 0 {
		buf, err := proxywasm.DequeueSharedQueue(queueId)
		queueSize--
		queueSizeBuf = make([]byte, 8)
		binary.LittleEndian.PutUint64(queueSizeBuf, queueSize)
		//proxywasm.LogCriticalf("[DEQUE EVENT] set queue size to %v", queueSize)
		if err := proxywasm.SetSharedData(queueSizeKey, queueSizeBuf, cas); err != nil {
			if errors.Is(err, types.ErrorStatusCasMismatch) {
				// try again
				queueSizeBuf, cas, _ = proxywasm.GetSharedData(queueSizeKey)
				queueSize = binary.LittleEndian.Uint64(queueSizeBuf)
				queueSize--
				binary.LittleEndian.PutUint64(queueSizeBuf, queueSize)
				if err := proxywasm.SetSharedData(queueSizeKey, queueSizeBuf, cas); err != nil {
					proxywasm.LogCriticalf("WE'RE FUCKED EITHER WAY: unable to set queue size: %v", err)
				}
			}
			proxywasm.LogCriticalf("unable to set queue size: %v", err)
		}
		if err != nil {
			proxywasm.LogCriticalf("Couldn't dequeue shared queue: %v", err)
			return queueSize
		}
		reqTimestamp := int64(binary.LittleEndian.Uint64(buf))
		//proxywasm.LogCriticalf("reqTimestamp: %v, cutoff %v", reqTimestamp, timeMillisCutoff)
		queueSizeBuf, cas, _ = proxywasm.GetSharedData(queueSizeKey)
		queueSize = binary.LittleEndian.Uint64(queueSizeBuf)
		if reqTimestamp > timeMillisCutoff {
			// we're done
			break
		}
	}
	// set queue size
	queueSizeBuf = make([]byte, 8)
	binary.LittleEndian.PutUint64(queueSizeBuf, queueSize)
	//proxywasm.LogCriticalf("set queue size to %v", queueSize)
	if err := proxywasm.SetSharedData(queueSizeKey, queueSizeBuf, cas); err != nil {
		queueSizeBuf, _, _ = proxywasm.GetSharedData(queueSizeKey)
		queueSize2 := binary.LittleEndian.Uint64(queueSizeBuf)
		proxywasm.LogCriticalf("[CAS MISMATCH] tried to set %v but queue size is %v", queueSize, queueSize2)
		//proxywasm.LogCriticalf("unable to set queue size: %v", err)
	}
	return queueSize
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
		proxywasm.LogCriticalf("unable to set shared data: %v", err)
		if errors.Is(err, types.ErrorStatusCasMismatch) {
			IncrementSharedData(key, amount)
		}
	}
}

func GetUint64SharedDataOrZero(key string) uint64 {
	data, _, err := proxywasm.GetSharedData(key)
	if err != nil {
		return 0
	}
	if len(data) == 0 {
		return 0
	}
	return binary.LittleEndian.Uint64(data)
}

func GetUint64SharedData(key string) (uint64, error) {
	data, _, err := proxywasm.GetSharedData(key)
	if err != nil {
		return 0, err
	}
	if len(data) == 0 {
		return 0, nil
	}
	return binary.LittleEndian.Uint64(data), nil
}

// ParseThresholds parses the thresholds from the controller into a slice of RpsThresholds.
// Expects thresholds in the following form:
// <RPS> <header value>
// <RPS_2> <header value 2>
// ...
// <RPS_i> <header value i>
//
// where RPS_i-1 > RPS_i
func ParseThresholds(rawThresh string) (thresholds []RpsThreshold) {
	for _, thresh := range strings.Split(rawThresh, "\n") {
		rpsToHeaderRaw := strings.Split(thresh, " ")
		if len(rpsToHeaderRaw) != 2 {
			continue
		}
		rps, err := strconv.Atoi(rpsToHeaderRaw[0])
		if err != nil {
			continue
		}
		header := rpsToHeaderRaw[1]
		thresholds = append(thresholds, RpsThreshold{Threshold: uint64(rps), HeaderValue: header})
	}
	return
}

// AddTracedRequest adds a traceId to the set of traceIds we are tracking (this is collected every Tick and sent
// to the controller), and set attributes in shared data about the traceId.
func AddTracedRequest(method, path, traceId, spanId, parentSpanId string, startTime int64, bodySize int) error {
	// add traceId to the set of requests we are tracing.
	tracedRequestsRaw, cas, err := proxywasm.GetSharedData(KEY_TRACED_REQUESTS)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for traced requests: %v", err)
		return err
	}
	var tracedRequests string
	if len(tracedRequestsRaw) == 0 {
		tracedRequests = traceId
	} else {
		tracedRequests = string(tracedRequestsRaw) + " " + traceId
	}
	if err := proxywasm.SetSharedData(KEY_TRACED_REQUESTS, []byte(tracedRequests), cas); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traced requests: %v", err)
		return err
	}
	// set method, path, spanId, parentSpanId, and startTime for this traceId
	if err := proxywasm.SetSharedData(methodKey(traceId), []byte(method), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v method: %v %v", traceId, method, err)
		return err
	}

	if err := proxywasm.SetSharedData(pathKey(traceId), []byte(path), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v path: %v %v", traceId, path, err)
		return err
	}

	//proxywasm.LogCriticalf("spanId: %v parentSpanId: %v startTime: %v", spanId, parentSpanId, startTime)
	if err := proxywasm.SetSharedData(spanIdKey(traceId), []byte(spanId), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v spanId: %v %v", traceId, spanId, err)
		return err
	}

	// possible if this is the root
	if parentSpanId != "" {
		if err := proxywasm.SetSharedData(parentSpanIdKey(traceId), []byte(parentSpanId), 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data for traceId %v parentSpanId: %v %v", traceId, parentSpanId, err)
			return err
		}
	}
	startTimeBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(startTimeBytes, uint64(startTime))
	if err := proxywasm.SetSharedData(startTimeKey(traceId), startTimeBytes, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v startTime: %v %v", traceId, startTime, err)
		return err
	}

	bodySizeBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(bodySizeBytes, uint64(bodySize))
	if err := proxywasm.SetSharedData(bodySizeKey(traceId), bodySizeBytes, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v bodySize: %v %v", traceId, bodySize, err)
	}

	// Adding load to shareddata when we receive the request
	data, cas, err := proxywasm.GetSharedData(KEY_INFLIGHT_REQ_COUNT)               // Get the current load
	if err := proxywasm.SetSharedData(firstLoadKey(traceId), data, 0); err != nil { // Set the trace with the current load
		proxywasm.LogCriticalf("unable to set shared data for traceId %v load: %v", traceId, err)
		return err
	}
	return nil
}

// GetTracedRequestStats returns a slice of TracedRequestStats for all traced requests.
// It skips requests that have not completed.
func GetTracedRequestStats() ([]TracedRequestStats, error) {
	tracedRequestsRaw, _, err := proxywasm.GetSharedData(KEY_TRACED_REQUESTS)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for traced requests: %v", err)
		return nil, err
	}
	// proxywasm.LogCriticalf("tracedRequestsRaw: %v", string(tracedRequestsRaw))
	if len(tracedRequestsRaw) == 0 || errors.Is(err, types.ErrorStatusNotFound) || emptyBytes(tracedRequestsRaw) {
		// no requests traced
		return make([]TracedRequestStats, 0), nil
	}
	var tracedRequestStats []TracedRequestStats
	tracedRequests := strings.Split(string(tracedRequestsRaw), " ")
	for _, traceId := range tracedRequests {
		if emptyBytes([]byte(traceId)) {
			continue
		}
		spanIdBytes, _, err := proxywasm.GetSharedData(spanIdKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v spanId: %v", traceId, err)
			return nil, err
		}
		spanId := string(spanIdBytes)
		parentSpanIdBytes, _, err := proxywasm.GetSharedData(parentSpanIdKey(traceId))
		parentSpanId := ""
		if err == nil {
			parentSpanId = string(parentSpanIdBytes)
		}

		methodBytes, _, err := proxywasm.GetSharedData(methodKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v method: %v", traceId, err)
			return nil, err
		}
		method := string(methodBytes)
		pathBytes, _, err := proxywasm.GetSharedData(pathKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v path: %v", traceId, err)
			return nil, err
		}
		path := string(pathBytes)

		startTimeBytes, _, err := proxywasm.GetSharedData(startTimeKey(traceId))
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v startTime: %v", traceId, err)
			return nil, err
		}
		startTime := int64(binary.LittleEndian.Uint64(startTimeBytes))
		endTimeBytes, _, err := proxywasm.GetSharedData(endTimeKey(traceId))
		if err != nil {
			// request hasn't completed yet, so just disregard.
			continue
		}
		var bodySize int64
		bodySizeBytes, _, err := proxywasm.GetSharedData(bodySizeKey(traceId))
		if err != nil {
			// if we have an end time but no body size, set 0 to body, req just had headers
			bodySize = 0
		} else {
			bodySize = int64(binary.LittleEndian.Uint64(bodySizeBytes))
		}
		endTime := int64(binary.LittleEndian.Uint64(endTimeBytes))

		// (gangmuk)
		firstLoadBytes, _, err := proxywasm.GetSharedData(firstLoadKey(traceId)) // Get stored load of this traceid
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v  from firstLoadKey: %v", traceId, err)
			return nil, err
		}
		first_load := int64(binary.LittleEndian.Uint64(firstLoadBytes)) // should it be int or int64?

		rpsBytes, _, err := proxywasm.GetSharedData(KEY_REQUEST_COUNT) // Get stored load of this traceid
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v from KEY_REQUEST_COUNT: %v", traceId, err)
			return nil, err
		}
		rps_ := int64(binary.LittleEndian.Uint64(rpsBytes)) // to int

		tracedRequestStats = append(tracedRequestStats, TracedRequestStats{
			method:       method,
			path:         path,
			traceId:      traceId,
			spanId:       spanId,
			parentSpanId: parentSpanId,
			startTime:    startTime,
			endTime:      endTime,
			bodySize:     bodySize,
			firstLoad:    first_load,
			rps:          rps_,
		})
	}
	return tracedRequestStats, nil
}

func saveEndpointStatsForTrace(traceId string, stats map[string]EndpointStats) {
	str := ""
	for k, v := range stats {
		str += fmt.Sprintf("%s,%d,%d", k, v.Total, v.Inflight) + "|"
	}
	if err := proxywasm.SetSharedData(endpointInflightStatsKey(traceId), []byte(str), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v endpointInflightStats: %v %v", traceId, str, err)
	}
}

func GetInflightRequestStats() (map[string]EndpointStats, error) {
	inflightEndpoints, _, err := proxywasm.GetSharedData(KEY_ENDPOINT_RPS_LIST)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for inflight request stats: %v", err)
		return nil, err
	}
	if len(inflightEndpoints) == 0 || errors.Is(err, types.ErrorStatusNotFound) || emptyBytes(inflightEndpoints) {
		// no requests traced
		return make(map[string]EndpointStats), nil
	}
	inflightRequestStats := make(map[string]EndpointStats)
	inflightEndpointsList := strings.Split(string(inflightEndpoints), ",")
	for _, endpoint := range inflightEndpointsList {
		if emptyBytes([]byte(endpoint)) {
			continue
		}
		method := strings.Split(endpoint, "@")[0]
		path := strings.Split(endpoint, "@")[1]
		inflightRequestStats[endpoint] = EndpointStats{
			Inflight: GetUint64SharedDataOrZero(inflightCountKey(method, path)),
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
	if len(rpsEndpoints) == 0 || errors.Is(err, types.ErrorStatusNotFound) || emptyBytes(rpsEndpoints) {
		// no requests traced
		return inflightRequestStats, nil
	}
	rpsEndpointsList := strings.Split(string(rpsEndpoints), ",")
	for _, endpoint := range rpsEndpointsList {
		if emptyBytes([]byte(endpoint)) {
			continue
		}
		method := strings.Split(endpoint, "@")[0]
		path := strings.Split(endpoint, "@")[1]
		proxywasm.LogDebugf("method: %s, path: %s", method, path)
		if val, ok := inflightRequestStats[endpoint]; ok {
			//val.Total = GetUint64SharedDataOrZero(endpointCountKey(method, path))
			//val.Total = SharedQueueGetRPS(sharedQueueKey(method, path), sharedQueueSizeKey(method, path))
			val.Total = TimestampListGetRPS(method, path)
			//val.Total = 0
			inflightRequestStats[endpoint] = val
		} else {
			inflightRequestStats[endpoint] = EndpointStats{
				//Total: GetUint64SharedDataOrZero(endpointCountKey(method, path)),
				//Total: SharedQueueGetRPS(sharedQueueKey(method, path), sharedQueueSizeKey(method, path)),
				//Total: 0,
				Total: TimestampListGetRPS(method, path),
			}
		}
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for endpoint %v inflight request stats: %v", endpoint, err)
		}
	}

	return inflightRequestStats, nil
}

func IncrementInflightCount(method string, path string, amount int) {
	// the lists themselves contain endpoints in the form METHOD PATH, so when we read from the list,
	// we have to split on space to get method and path, and then we can get the inflight/rps by using the
	// inflightCountKey and endpointCountKey functions. This is to correlate the inflight count with the
	// endpoint count.
	//proxywasm.LogCriticalf("adding %d to inflight count for %s %s", amount, method, path)
	AddToSharedDataList(KEY_INFLIGHT_ENDPOINT_LIST, endpointListKey(method, path))
	AddToSharedDataList(KEY_ENDPOINT_RPS_LIST, endpointListKey(method, path))
	IncrementSharedData(inflightCountKey(method, path), int64(amount))
	if amount > 0 {
		IncrementSharedData(endpointCountKey(method, path), int64(amount))
	}

	//if newAmt, _ := GetUint64SharedData(inflightCountKey(method, path)); newAmt == uint64(0) {
	//	// remove from list
	//	newList := make([]string, 0)
	//	for _, endpoint := range endpointList {
	//		if endpoint != inflightCountKey(method, path) {
	//			newList = append(newList, endpoint)
	//		}
	//	}
	//	newListBytes := []byte(strings.Join(newList, ","))
	//	if err := proxywasm.SetSharedData(KEY_INFLIGHT_ENDPOINT_LIST, newListBytes, cas); err != nil {
	//		proxywasm.LogCriticalf("unable to set shared data: %v", err)
	//		return
	//	}
	//}
}

func ResetEndpointCounts() {
	// get list of endpoints
	endpointListBytes, cas, err := proxywasm.GetSharedData(KEY_ENDPOINT_RPS_LIST)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for endpoint rps list: %v", err)
		return
	}
	if len(endpointListBytes) == 0 || errors.Is(err, types.ErrorStatusNotFound) || emptyBytes(endpointListBytes) {
		// no requests traced
		return
	}
	endpointList := strings.Split(string(endpointListBytes), ",")
	// reset counts
	for _, endpoint := range endpointList {
		if emptyBytes([]byte(endpoint)) {
			continue
		}
		method := strings.Split(endpoint, "@")[0]
		path := strings.Split(endpoint, "@")[1]
		// reset endpoint count
		if err := proxywasm.SetSharedData(endpointCountKey(method, path), make([]byte, 8), 0); err != nil {
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

// AddToSharedDataList adds a value to a list stored in shared data at the given key, if it is not already in the list.
// The list is stored as a comma separated string.
func AddToSharedDataList(key string, value string) {
	listBytes, cas, err := proxywasm.GetSharedData(key)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	list := strings.Split(string(listBytes), ",")
	containsValue := false
	for _, v := range list {
		if v == value {
			containsValue = true
		}
	}
	if !containsValue {
		newListBytes := []byte(strings.Join(append(list, value), ","))
		if err := proxywasm.SetSharedData(key, newListBytes, cas); err != nil {
			proxywasm.LogCriticalf("unable to set shared data: %v", err)
			return
		}
	}
}

func IncrementTimestampListSize(method string, path string, amount int64) {
	queueSize, cas, err := proxywasm.GetSharedData(sharedQueueSizeKey(method, path))
	if err != nil {
		// nothing there, just set to 1
		queueSizeBuf := make([]byte, 8)
		binary.LittleEndian.PutUint64(queueSizeBuf, 1)
		if err := proxywasm.SetSharedData(sharedQueueSizeKey(method, path), queueSizeBuf, cas); err != nil {
			// try again
			IncrementTimestampListSize(method, path, amount)
		}
		return
	}
	// set queue size
	queueSizeBuf := make([]byte, 8)
	binary.LittleEndian.PutUint64(queueSizeBuf, binary.LittleEndian.Uint64(queueSize)+uint64(amount))
	if err := proxywasm.SetSharedData(sharedQueueSizeKey(method, path), queueSizeBuf, cas); err != nil {
		IncrementTimestampListSize(method, path, amount)
	}
}

func (h *httpContext) GetTime() uint32 {
	// get current time in milliseconds since the last day
	diff := time.Now().UnixMilli() - h.pluginContext.startTime
	return uint32(diff)
}

/*
TimestampListAdd adds a new timestamp to the end of the list for the given method and path.
The list is stored as a comma-separated string of timestamps.
*/
func (h *httpContext) TimestampListAdd(method string, path string) {
	// get list of timestamps
	t := h.GetTime()
	/*
			todo aditya:
			 this is an expensive load (14kb), and we are doing it on every request. This is likely what is causing
			 the bottleneck.
			 Is there a way we can cache this?
			 We have to write current time to the list anyway...so we would need to read the list to make sure evictions
			  happen...right?
			 Could we possibly use int32 or int16 instead of int64 for the timestamps? 4bytes/2bytes vs 8 bytes, so we can
			  store 3500/7000 requests with the same buffer.
			 UnixMilli returns int64, but that's time since epoch, so can we use the last 32/16 bits of that? We still want
		      millisecond precision.
	*/
	timestampListBytes, cas, err := proxywasm.GetSharedData(sharedQueueKey(method, path))
	if err != nil {
		// nothing there, just set to the current time
		// 4 bytes per request, so we can store 1750 requests in 7000 bytes
		newListBytes := make([]byte, 7000)
		binary.LittleEndian.PutUint64(newListBytes, uint64(t))
		if err := proxywasm.SetSharedData(sharedQueueKey(method, path), newListBytes, cas); err != nil {
			h.TimestampListAdd(method, path)
			return
		}
		// set write pos
		writePos := make([]byte, 8)
		binary.LittleEndian.PutUint32(writePos, 4)
		if err := proxywasm.SetSharedData(timestampListWritePosKey(method, path), writePos, 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data for timestamp write pos: %v", err)
		}

		return
	}
	// get write position
	timestampPos, writeCas, err := proxywasm.GetSharedData(timestampListWritePosKey(method, path))
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data for timestamp write pos: %v", err)
		return
	}
	writePos := binary.LittleEndian.Uint64(timestampPos)
	// if we're at the end of the list, we need to rotate list
	if writePos+4 > uint64(len(timestampListBytes)) {
		proxywasm.LogCriticalf("[REACHED CAPACITY, ROTATING]")
		// rotation magic
		readPosBytes, readCas, err := proxywasm.GetSharedData(timestampListReadPosKey(method, path))
		if err != nil {
			proxywasm.LogCriticalf("[ROTATION MAGIC] Couldn't get shared data for timestamp read pos: %v", err)
			return
		}
		readPos := binary.LittleEndian.Uint64(readPosBytes)
		// copy readPos to writePos to the beginning of the list
		bytesRemaining := len(timestampListBytes) - int(readPos)
		copy(timestampListBytes, timestampListBytes[readPos:])
		// set readPos to 0
		readPosBytes = make([]byte, 8)
		binary.LittleEndian.PutUint64(readPosBytes, 0)
		if err := proxywasm.SetSharedData(timestampListReadPosKey(method, path), readPosBytes, readCas); err != nil {
			proxywasm.LogCriticalf("[ROTATION MAGIC] unable to set shared data for timestamp read pos: %v", err)
			// try again
			//if err := proxywasm.SetSharedData(timestampListReadPosKey(method, path), readPosBytes, 0); err != nil {
			//	proxywasm.LogCriticalf("[ROTATION MAGIC] unable to set shared data for timestamp read pos: %v", err)
			//	return
			//}
			return
		}
		// set writePos to the end of the segment we just rotated
		writePos = uint64(bytesRemaining)
		// set writePos
		writePosBytes := make([]byte, 8)
		binary.LittleEndian.PutUint64(writePosBytes, writePos)
		if err := proxywasm.SetSharedData(timestampListWritePosKey(method, path), writePosBytes, writeCas); err != nil {
			proxywasm.LogCriticalf("[ROTATION MAGIC] unable to set shared data for timestamp write pos: %v", err)
			// try again
			//if err := proxywasm.SetSharedData(timestampListWritePosKey(method, path), writePosBytes, 0); err != nil {
			//	return
			//}

		}
	}
	// add new timestamp
	if writePos >= uint64(len(timestampListBytes)) {
		proxywasm.LogCriticalf("writePos: %v, len: %v", writePos, len(timestampListBytes))
		// just fuck off and dont write anything until all threads sync
		return
	}
	binary.LittleEndian.PutUint32(timestampListBytes[writePos:], t)

	if err := proxywasm.SetSharedData(sharedQueueKey(method, path), timestampListBytes, cas); err != nil {
		h.TimestampListAdd(method, path)
		return
	}
	// change write position *after* writing new bytes was success
	IncrementSharedData(timestampListWritePosKey(method, path), 4)

	// evict old entries while we're at it
	timeMillisCutoff := h.GetTime() - 1000
	// get timestamp read position
	readPosBytes, cas2, err := proxywasm.GetSharedData(timestampListReadPosKey(method, path))
	if err != nil {
		// set read pos to 0
		readPosBytes = make([]byte, 8)
		binary.LittleEndian.PutUint64(readPosBytes, 0)
		if err := proxywasm.SetSharedData(timestampListReadPosKey(method, path), readPosBytes, 0); err != nil {
			return
		}
	}
	readPos := binary.LittleEndian.Uint64(readPosBytes)
	for readPos < uint64(len(timestampListBytes)) {
		if binary.LittleEndian.Uint32(timestampListBytes[readPos:]) < timeMillisCutoff {
			readPos += 4
		} else {
			break
		}
	}
	// set read pos
	readPosBytes = make([]byte, 8)
	binary.LittleEndian.PutUint64(readPosBytes, readPos)
	if err := proxywasm.SetSharedData(timestampListReadPosKey(method, path), readPosBytes, cas2); err != nil {
		return
	}
}

/*
TimestampListGetRPS will evict entries older than 1 second for the given method and path.
It will also return the current RPS, which is just the length of the data/queue.

The data is a comma-separated string of timestamps. we add new timestamps to the end (.append),
and evict from the front (to simulate efficiency of a queue).

The "queue size" is then updated to reflect the new size of the queue. This is returned.
*/
func TimestampListGetRPS(method string, path string) uint64 {
	// get list of timestamps
	readPosBytes, _, err := proxywasm.GetSharedData(timestampListReadPosKey(method, path))
	if err != nil {
		return 0
	}
	readPos := binary.LittleEndian.Uint64(readPosBytes)
	writePosBytes, _, err := proxywasm.GetSharedData(timestampListWritePosKey(method, path))
	if err != nil {
		return 0
	}
	writePos := binary.LittleEndian.Uint64(writePosBytes)
	queueSize := writePos - readPos
	return queueSize / 4
	/*
		timestampListBytes, _, err := proxywasm.GetSharedData(sharedQueueKey(method, path))
		if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
			proxywasm.LogCriticalf("Couldn't get shared data for timestamp list: %v", err)
			return 0
		}
		if errors.Is(err, types.ErrorStatusNotFound) {
			// just return 0
			return 0
		}
		timeMillisCutoff := time.Now().UnixMilli() - 1000

		// get write pos
		writePosBytes, _, err := proxywasm.GetSharedData(timestampListWritePosKey(method, path))
		writePos := binary.LittleEndian.Uint64(writePosBytes)

		// get timestamp read position
		readPosBytes, cas2, err := proxywasm.GetSharedData(timestampListReadPosKey(method, path))
		if err != nil {
			// set read pos to 0
			readPosBytes = make([]byte, 8)
			binary.LittleEndian.PutUint64(readPosBytes, 0)
			if err := proxywasm.SetSharedData(timestampListReadPosKey(method, path), readPosBytes, 0); err != nil {
				return 0
			}
		}
		readPos := binary.LittleEndian.Uint64(readPosBytes)
		for readPos < uint64(len(timestampListBytes)) {
			if binary.LittleEndian.Uint64(timestampListBytes[readPos:]) < uint64(timeMillisCutoff) {
				readPos += 8
			} else {
				break
			}
		}
		// set read pos
		readPosBytes = make([]byte, 8)
		binary.LittleEndian.PutUint64(readPosBytes, readPos)
		if err := proxywasm.SetSharedData(timestampListReadPosKey(method, path), readPosBytes, cas2); err != nil {
			//proxywasm.LogCriticalf("CAS MISMATCH: trying again")
			return TimestampListGetRPS(method, path)
		}
		validRequests := (writePos - readPos) / 8
		return validRequests
	*/
}

func inboundCountKey(traceId string) string {
	return traceId + "-inbound-request-count"
}

func spanIdKey(traceId string) string {
	return traceId + "-s"
}

func parentSpanIdKey(traceId string) string {
	return traceId + "-p"
}

func startTimeKey(traceId string) string {
	return traceId + "-startTime"
}

func endTimeKey(traceId string) string {
	return traceId + "-endTime"
}

func bodySizeKey(traceId string) string {
	return traceId + "-bodySize"
}

func firstLoadKey(traceId string) string {
	return traceId + "-firstLoad"
}

func methodKey(traceId string) string {
	return traceId + "-method"
}

func pathKey(traceId string) string {
	return traceId + "-path"
}

func emptyBytes(b []byte) bool {
	for _, v := range b {
		if v != 0 {
			return false
		}
	}
	return true
}

func endpointListKey(method string, path string) string {
	return method + "@" + path
}

func inflightCountKey(method string, path string) string {
	return "inflight/" + method + "-" + path
}

func endpointCountKey(method string, path string) string {
	return "endpointRPS/" + method + "-" + path
}

func endpointInflightStatsKey(traceId string) string {
	return traceId + "-endpointInflightStats"
}

func endpointDistributionKey(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-distribution"
}

func sharedQueueKey(method, path string) string {
	return method + "@" + path
}

func sharedQueueSizeKey(method, path string) string {
	return method + "@" + path + "-queuesize"
}

func timestampListWritePosKey(method, path string) string {
	return method + "@" + path + "-writepos"
}

func timestampListReadPosKey(method, path string) string {
	return method + "@" + path + "-readpos"
}

// (gangmuk): need to double check to confirm it is correct.
func tracedRequest(traceId string) bool {
	// use md5 for speed
	hash := md5Hash(traceId)
	_, _, err := proxywasm.GetSharedData(KEY_HASH_MOD)
	var mod uint32
	if err != nil {
		mod = DEFAULT_HASH_MOD
	} else {
		//mod = binary.LittleEndian.Uint32(modBytes)
		mod = DEFAULT_HASH_MOD

	}
	return hash%int(mod) == 0
}

func md5Hash(s string) int {
	h := md5.New()
	h.Write([]byte(s))
	return int(binary.LittleEndian.Uint64(h.Sum(nil)))
}

func calculatePercentile(data []int64, percentile float64) int64 {
	if len(data) == 0 {
		return 0
	}
	sort.Slice(data, func(i, j int) bool {
		return data[i] < data[j]
	})
	k := int(float64(len(data)) * percentile / 100.0)
	value := data[k]
	fmt.Printf("%dth percentile: %d\n", percentile, value)
	return value
}

func calculateAverage(data []int64) float64 {
	if len(data) == 0 {
		return 0.0
	}

	var sum int64
	for _, num := range data {
		sum += num
	}

	average := float64(sum) / float64(len(data))
	return average
}