package main

import (
	"crypto/md5"
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
)

const (
	KEY_REQUEST_COUNT   = "slate_request_count"
	KEY_LAST_RESET      = "slate_last_reset"
	KEY_RPS_THRESHOLDS  = "slate_rps_threshold"
	KEY_HASH_MOD        = "slate_hash_mod"
	KEY_TRACED_REQUESTS = "slate_traced_requests"
	// this is in millis
	AGGREGATE_REQUEST_LATENCY = "slate_last_second_latency_avg"
	/////////////////////////////////////////
	// (gangmuk): changed to 2 seconds to capture more inflights.
	TICK_PERIOD = 2000
	/////////////////////////////////////////
	DEFAULT_HASH_MOD                = 1
	SLATE_REMOTE_CLUSTER_HEADER_KEY = "x-slate-remotecluster"
)

/*
todo(adiprerepa)
  lots of bloat due to the fact that we can't share data between plugins.
  to sync data, we need to use shared data, which is a pretty bloated api for a simple k/v store.
  create getorfail() and setorfail() methods to reduce the amount of code duplication.
*/

var (
	ALL_KEYS = []string{KEY_REQUEST_COUNT, KEY_LAST_RESET, KEY_RPS_THRESHOLDS, KEY_HASH_MOD, AGGREGATE_REQUEST_LATENCY,
		KEY_TRACED_REQUESTS}
	TOGGLE = 0 // (gangmuk): toggle in OnTick function to halve the times of clearing the KEY_REQUEST_COUNT.
)

func main() {
	proxywasm.SetVMContext(&vmContext{})
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
	traceId      string
	spanId       string
	parentSpanId string
	startTime    int64
	endTime      int64
	bodySize     int64
	firstLoad    int64
	lastLoad     int64
	avgLoad      int64
}

// Override types.DefaultVMContext.
func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	return &pluginContext{}
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
	return true
}

type pluginContext struct {
	types.DefaultPluginContext

	podName       string
	serviceName   string
	clusterId     string
	metaClusterId string
	rpsThresholds []RpsThreshold
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	if err := proxywasm.SetTickPeriodMilliSeconds(TICK_PERIOD); err != nil {
		proxywasm.LogCriticalf("unable to set tick period: %v", err)
		return types.OnPluginStartStatusFailed
	}
	service := os.Getenv("ISTIO_META_WORKLOAD_NAME")
	if service == "" {
		service = "SLATE_UNKNOWN_SVC"
	}
	pod := os.Getenv("HOSTNAME")
	if pod == "" {
		pod = "SLATE_UNKNOWN_POD"
	}
	meta_cid := os.Getenv("ISTIO_META_CLUSTER_ID")
	if meta_cid == "" {
		meta_cid = "META_CLUSTER_ID_UNKNOWN"
	}
	cid := os.Getenv("CLUSTER_ID")
	if cid == "" {
		cid = "CLUSTER_ID_UNKNOWN"
	}
	p.clusterId = cid
	p.metaClusterId = meta_cid
	p.podName = pod
	p.serviceName = service
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
	data, cas, err := proxywasm.GetSharedData(KEY_LAST_RESET)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	lastReset := int64(binary.LittleEndian.Uint64(data))
	currentNanos := time.Now().UnixMilli()
	// allow for some jitter - this is bad and racy and hardcoded
	if lastReset >= (currentNanos - (TICK_PERIOD / 2)) {
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

	buf = make([]byte, 8)
	///////////////////////////////////////////////
	// set request count back to 0
	// proxywasm.LogCriticalf("Current TOGGLE %d", TOGGLE)
	// if TOGGLE == 0 {

	// ** (gangmuk): this is wrong **
	// if err := proxywasm.SetSharedData(KEY_REQUEST_COUNT, buf, cas); err != nil {
	// 	if errors.Is(err, types.ErrorStatusCasMismatch) {
	// 		// this should *never* happen.
	// 		proxywasm.LogCriticalf("CAS Mismatch on RPS, failing: %v", err)
	// 	}
	// 	return
	// }
	//

	// proxywasm.LogCriticalf("TOGGLE(%d) == 0. CLEAR REQUEST_COUNT(load)!!", TOGGLE)
	// }
	// TOGGLE = (TOGGLE + 1) % 2
	///////////////////////////////////////////////
	requestStats, err := GetTracedRequestStats()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get traced request stats: %v", err)
		return
	}
	// unbelievably shitty but what can you do if you don't have gRPC :)
	requestStatsStr := ""
	for _, stat := range requestStats {
		requestStatsStr += fmt.Sprintf("%s %s %s %d %d %d %d %d %d\n", stat.traceId, stat.spanId, stat.parentSpanId,
			stat.startTime, stat.endTime, stat.bodySize, stat.firstLoad, stat.lastLoad, stat.avgLoad)
	}

	// reset stats
	if err := proxywasm.SetSharedData(KEY_TRACED_REQUESTS, make([]byte, 8), 0); err != nil {
		proxywasm.LogCriticalf("Couldn't reset traced requests: %v", err)
	}

	// print ontick results
	data, cas, err = proxywasm.GetSharedData(KEY_REQUEST_COUNT)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	reqCount := binary.LittleEndian.Uint64(data)
	// proxywasm.LogCriticalf("OnTick, request count: %d, traced stats: %s", reqCount, requestStatsStr)
	proxywasm.LogCriticalf("OnTick, request count: %d", reqCount)

	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/proxyLoad"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
	}

	proxywasm.LogCriticalf("Sending load to %s", p.metaClusterId)
	if p.metaClusterId == "kind-us-west" {
		proxywasm.DispatchHttpCall("outbound|8080|west|slate-controller.default.svc.cluster.local", controllerHeaders,
			[]byte(fmt.Sprintf("%d\n%s", reqCount, requestStatsStr)), make([][2]string, 0), 5000, OnTickHttpCallResponse)
	} else if p.metaClusterId == "kind-us-east" {
		proxywasm.DispatchHttpCall("outbound|8080|east|slate-controller.default.svc.cluster.local", controllerHeaders,
			[]byte(fmt.Sprintf("%d\n%s", reqCount, requestStatsStr)), make([][2]string, 0), 5000, OnTickHttpCallResponse)
	} else {
		proxywasm.DispatchHttpCall("outbound|8080||slate-controller.default.svc.cluster.local", controllerHeaders,
			[]byte(fmt.Sprintf("%d\n%s", reqCount, requestStatsStr)), make([][2]string, 0), 5000, OnTickHttpCallResponse)
	}
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
	traceId, err := proxywasm.GetHttpRequestHeader("x-b3-traceid")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header: %v", err)
		return types.ActionContinue
	}
	// bookkeeping to make sure we don't double count requests. decremented in OnHttpStreamDone
	IncrementSharedData(inboundCountKey(traceId), 1)
	inbound, err := GetUint64SharedData(inboundCountKey((traceId)))
	proxywasm.LogCriticalf("OnHttpRequestHeaders, increment inbound, trace_id,%v, inbound,%d", traceId, inbound)

	_, _, err = proxywasm.GetSharedData(traceId)
	if err == nil {
		// we've been set, get out
		fmt.Printf("OnhttpRequestHeaders, traceId: %v, we've been set, get out", traceId)
		return types.ActionContinue
	}

	// we haven't been set, set us. this can be anything.
	buf := make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, uint64(time.Now().UnixMilli()))
	if err := proxywasm.SetSharedData(traceId, buf, 0); err != nil {
		proxywasm.LogCriticalf("Couldn't set shared data: %v", err)
		return types.ActionContinue
	}

	// increment request count
	// (gangmuk): it is load
	IncrementSharedData(KEY_REQUEST_COUNT, 1) // There is one load variable shared by all requests in this wasm, but each request will save the snapshot of the load when the request arrives in this wasm. So different requests will have different loads but there is one load in this wasm at a time t.

	if tracedRequest(traceId) {
		// we need to record start and end time
		// proxywasm.LogCriticalf("tracing request: %s", traceId)
		spanId, _ := proxywasm.GetHttpRequestHeader("x-b3-spanid")
		parentSpanId, _ := proxywasm.GetHttpRequestHeader("x-b3-parentspanid")
		if err := AddTracedRequest(traceId, spanId, parentSpanId, time.Now().UnixMilli()); err != nil {
			proxywasm.LogCriticalf("unable to add traced request: %v", err)
			return types.ActionContinue
		}
	}

	// todo(adiprerepa) enforce controller policy by adding headers to route to remote cluster

	return types.ActionContinue
}

// bodySize will be used as call size (request size)
func (ctx *httpContext) OnHttpRequestBody(bodySize int, endOfStream bool) types.Action {
	traceId, err := proxywasm.GetHttpRequestHeader("x-b3-traceid")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header: %v", err)
		return types.ActionContinue
	}
	proxywasm.LogCriticalf("OnHttpRequestBody, bodysize, %d", bodySize)

	bodySizeBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(bodySizeBytes, uint64(bodySize))
	if err := proxywasm.SetSharedData(bodySizeKey(traceId), bodySizeBytes, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v bodySize: %v %v", traceId, bodySize, err)
	}
	return types.ActionContinue
}

/*
todo adiprerepa add call size
*/

// OnHttpStreamDone is called when the stream is about to close.
// We use this to record the end time of the traced request.
// Since all responses are treated equally, regardless of whether
// they come from upstream or downstream, we need to do some clever
// bookkeeping and only record the end time for the last response.
// ///////////////////////////////////////////////////
// (gangmuk): when is it called? on every response?
// ///////////////////////////////////////////////////
func (ctx *httpContext) OnHttpStreamDone() {
	// get x-request-id from request headers and lookup entry time
	traceId, err := proxywasm.GetHttpRequestHeader("x-b3-traceid")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header: %v", err)
		return
	}
	// TODO(gangmuk): Is it correct?
	// endtime should be recorded when the LAST response is received not the first response. It seems like it records the endtime on the first response.
	inbound, err := GetUint64SharedData(inboundCountKey(traceId))
	proxywasm.LogCriticalf("OnHttpStreamDone, trace_id,%v, inbound,%d", traceId, inbound)
	if inbound != 1 {
		// decrement and get out
		IncrementSharedData(inboundCountKey(traceId), -1)
		inbound_after_decr, _ := GetUint64SharedData(inboundCountKey(traceId))
		proxywasm.LogCriticalf("OnHttpStreamDone, decrement inbound, trace_id,%v, inbound,%d", traceId, inbound_after_decr)
		return
	}

	//////////////////////////////////////////////////////////////////////////////////////
	// (gangmuk): Instead of setting the KEY_REQUEST_COUNT(load) to zero in OnTick function, decrement it when each request is completed.

	load_0, err := GetUint64SharedData(firstLoadKey((traceId)))
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data for firstLoadKey traceId %v load: %v", traceId, err)
		return
	}

	load_1, err := GetUint64SharedData(KEY_REQUEST_COUNT)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data for firstLoadKey traceId %v load: %v", traceId, err)
		return
	}

	// loadBytes_1, _, err := proxywasm.GetSharedData(KEY_REQUEST_COUNT)
	// load_1 := int64(binary.LittleEndian.Uint64(loadBytes_1)) // current load in wasm
	avg_load := (load_0 + load_1) / 2
	proxywasm.LogCriticalf("OnHttpStreamDone, This is THE LAST response! load_0,%d, load_1,%d, avg_load,%d", load_0, load_1, avg_load)

	buf := make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, uint64(load_1))
	if err := proxywasm.SetSharedData(lastLoadKey(traceId), buf, 0); err != nil { // Set the trace with the current load
		proxywasm.LogCriticalf("unable to set shared data lastLoadKey for traceId %v load: %v", traceId, err)
		return
	}
	buf = make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, uint64(avg_load))
	if err := proxywasm.SetSharedData(avgLoadKey(traceId), buf, 0); err != nil { // Set the trace with the current load
		proxywasm.LogCriticalf("unable to set shared data avgLoadKey for traceId %v load: %v", traceId, err)
		return
	}
	IncrementSharedData(KEY_REQUEST_COUNT, -1)
	//////////////////////////////////////////////////////////////////////////////////////

	currentTime := time.Now().UnixMilli()
	endTimeBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(endTimeBytes, uint64(currentTime))
	if err := proxywasm.SetSharedData(endTimeKey(traceId), endTimeBytes, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v endTime: %v %v", traceId, currentTime, err)
	}
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
	// todo log on error status code
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
	if status >= 400 {
		proxywasm.LogCriticalf("received ERROR http call response body: %s", string(respBody))
	}
	//proxywasm.LogCriticalf("setting rps thresholds: %s", string(respBody))
	// set thresholds
	if err := proxywasm.SetSharedData(KEY_RPS_THRESHOLDS, respBody, 0); err != nil {
		proxywasm.LogCriticalf("Couldn't set shared data for rps thresholds: %v", err)
		return
	}
}

// IncrementSharedData increments the value of the shared data at the given key. The data is
// stored as a little endian uint64. if the key doesn't exist, it is created with the value 1.
func IncrementSharedData(key string, amount int) {
	data, cas, err := proxywasm.GetSharedData(key)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
	}
	var val uint64
	if len(data) == 0 {
		val = uint64(amount)
	} else {
		// hopefully we don't overflow...
		val = uint64(int(binary.LittleEndian.Uint64(data)) + amount)
	}
	buf := make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, val)
	if err := proxywasm.SetSharedData(key, buf, cas); err != nil {
		proxywasm.LogCriticalf("unable to set shared data: %v", err)
	}
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
func AddTracedRequest(traceId, spanId, parentSpanId string, startTime int64) error {
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
	// set spanId, parentSpanId, and startTime for this traceId
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
	//////////////////////////////////////////////////////////////////////////////////
	// (gangmuk): Per-request load logging
	// Adding load to shareddata when we receive the request
	data, cas, err := proxywasm.GetSharedData(KEY_REQUEST_COUNT)                    // Get the current load
	if err := proxywasm.SetSharedData(firstLoadKey(traceId), data, 0); err != nil { // Set the trace with the current load
		proxywasm.LogCriticalf("unable to set shared data for traceId %v load: %v", traceId, err)
		return err
	}
	//////////////////////////////////////////////////////////////////////////////////
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
		if err != nil {
			// this is okay. could be root.
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v parentSpanId: %v", traceId, err)
		} else {
			parentSpanId = string(parentSpanIdBytes)
		}
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
		lastLoadBytes, _, err := proxywasm.GetSharedData(lastLoadKey(traceId)) // Get stored load of this traceid
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v  from lastLoadKey: %v", traceId, err)
			return nil, err
		}
		avgLoadBytes, _, err := proxywasm.GetSharedData(avgLoadKey(traceId)) // Get stored load of this traceid
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get shared data for traceId %v from avgLoadKey: %v", traceId, err)
			return nil, err
		}
		first_load := int64(binary.LittleEndian.Uint64(firstLoadBytes)) // to int
		last_load := int64(binary.LittleEndian.Uint64(lastLoadBytes))   // to int
		avg_load := int64(binary.LittleEndian.Uint64(avgLoadBytes))     // to int

		tracedRequestStats = append(tracedRequestStats, TracedRequestStats{
			traceId:      traceId,
			spanId:       spanId,
			parentSpanId: parentSpanId,
			startTime:    startTime,
			endTime:      endTime,
			bodySize:     bodySize,
			firstLoad:    first_load, // newly added per-request level load field
			lastLoad:     last_load,  // newly added per-request level load field
			avgLoad:      avg_load,   // newly added per-request level load field
		})
	}
	return tracedRequestStats, nil
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

func avgLoadKey(traceId string) string {
	return traceId + "-avgLoad"
}

func lastLoadKey(traceId string) string {
	return traceId + "-lastLoad"
}

func emptyBytes(b []byte) bool {
	for _, v := range b {
		if v != 0 {
			return false
		}
	}
	return true
}

// (gangmuk): need to double check to confirm it is correct.
func tracedRequest(traceId string) bool {
	// use md5 for speed
	hash := md5Hash(traceId)
	modBytes, _, err := proxywasm.GetSharedData(KEY_HASH_MOD)
	var mod uint32
	if err != nil {
		mod = DEFAULT_HASH_MOD
	} else {
		mod = binary.LittleEndian.Uint32(modBytes)
	}
	return hash%int(mod) == 0
}

func md5Hash(s string) int {
	h := md5.New()
	h.Write([]byte(s))
	return int(binary.LittleEndian.Uint64(h.Sum(nil)))
}
