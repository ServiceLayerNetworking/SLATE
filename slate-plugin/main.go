package main

import (
	"encoding/binary"
	"errors"
	"fmt"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	KEY_REQUEST_COUNT  = "slate_request_count"
	KEY_LAST_RESET     = "slate_last_reset"
	KEY_RPS_THRESHOLDS = "slate_rps_threshold"
	// this is in millis
	AGGREGATE_REQUEST_LATENCY       = "slate_last_second_latency_avg"
	TICK_PERIOD                     = 1000
	SLATE_REMOTE_CLUSTER_HEADER_KEY = "x-slate-remotecluster"
)

var (
	ALL_KEYS = []string{KEY_REQUEST_COUNT, KEY_LAST_RESET, KEY_RPS_THRESHOLDS, AGGREGATE_REQUEST_LATENCY}
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
	return true
}

type pluginContext struct {
	types.DefaultPluginContext

	podName     string
	serviceName string

	rpsThresholds []RpsThreshold
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	if err := proxywasm.SetTickPeriodMilliSeconds(TICK_PERIOD); err != nil {
		proxywasm.LogCriticalf("unable to set tick period: %v", err)
		return types.OnPluginStartStatusFailed
	}
	service := os.Getenv("WORKLOAD_NAME")
	if service == "" {
		service = "SLATE_UNKNOWN_SVC"
	}
	pod := os.Getenv("HOSTNAME")
	if pod == "" {
		pod = "SLATE_UNKNOWN_POD"
	}
	p.podName = pod
	p.serviceName = service
	return types.OnPluginStartStatusOK
}

// OnTick every second. Reset numRequests every tick and increment request on every http request.
func (p *pluginContext) OnTick() {
	/*
			send current RPS and recieve RPS threshold
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

	data, cas, err = proxywasm.GetSharedData(KEY_REQUEST_COUNT)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	reqCount := binary.LittleEndian.Uint64(data)
	buf = make([]byte, 8)
	// set request count back to 0
	if err := proxywasm.SetSharedData(KEY_REQUEST_COUNT, buf, cas); err != nil {
		if errors.Is(err, types.ErrorStatusCasMismatch) {
			// this should *never* happen.
			proxywasm.LogCriticalf("CAS Mismatch on RPS, failing: %v", err)
		}
		return
	}

	data, _, err = proxywasm.GetSharedData(AGGREGATE_REQUEST_LATENCY)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	latencyAggregate := binary.LittleEndian.Uint64(data)
	// reset latency avg
	if err := proxywasm.SetSharedData(AGGREGATE_REQUEST_LATENCY, buf, 0); err != nil {
		proxywasm.LogCriticalf("Couldn't set shared data for latency avg: %v", err)
		return
	}

	var latencyAvg uint64
	if reqCount != 0 {
		latencyAvg = latencyAggregate / reqCount
	} else {
		latencyAvg = 0
	}

	// print ontick results
	proxywasm.LogCriticalf("request count: %d, latency avg: %d", reqCount, latencyAvg)
	controllerHeaders := [][2]string{
		{":method", "POST"},
		{":path", "/proxyLoad"},
		{":authority", "slate-controller.default.svc.cluster.local"},
		{"x-slate-podname", p.podName},
		{"x-slate-servicename", p.serviceName},
	}
	proxywasm.DispatchHttpCall("outbound|8000||slate-controller.default.svc.cluster.local", controllerHeaders,
		[]byte(fmt.Sprintf("%d %d", reqCount, latencyAvg)), make([][2]string, 0), 5000, OnTickHttpCallResponse)
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

	// increment request count
	data, cas, err := proxywasm.GetSharedData(KEY_REQUEST_COUNT)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return types.ActionContinue
	}
	buf := make([]byte, 8)
	reqCount := binary.LittleEndian.Uint64(data) + 1
	binary.LittleEndian.PutUint64(buf, reqCount)
	if err := proxywasm.SetSharedData(KEY_REQUEST_COUNT, buf, cas); err != nil {
		if !errors.Is(err, types.ErrorStatusCasMismatch) {
			proxywasm.LogCriticalf("unable to set shared data: %v", err)
		}
	}

	// set time we received this x-request-id
	reqId, err := proxywasm.GetHttpRequestHeader("x-request-id")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header: %v", err)
		return types.ActionContinue
	}
	currentMillis := time.Now().UnixMilli()
	buf = make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, uint64(currentMillis))
	if err := proxywasm.SetSharedData(reqId, buf, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for x-request-id: %v", err)
		return types.ActionContinue
	}

	// todo(adiprerepa): check if we've exceeded the threshold and set headers accordingly
	//   right now, we can just do this linearly: if reqCount > threshold, set header. this resets every tick.
	//   the downside is requests will not be evenly "distributed" - 0->thresh requests go to one pod, thresh->thresh2 go
	//   to another, but sequentially, not uniformly.

	data, _, err = proxywasm.GetSharedData(KEY_RPS_THRESHOLDS)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return types.ActionContinue
	}
	// assume sorted - IN REVERSE ORDER
	thresholds := ParseThresholds(string(data))

	// maybe we don't need to get this twice.
	data, _, err = proxywasm.GetSharedData(KEY_REQUEST_COUNT)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return types.ActionContinue
	}
	reqCount = binary.LittleEndian.Uint64(data)

	for _, thresh := range thresholds {
		if reqCount > thresh.Threshold {
			// set header
			proxywasm.LogCriticalf("exceeded thresh %d, setting request header to %s", thresh.Threshold, thresh.HeaderValue)
			if err := proxywasm.AddHttpRequestHeader(SLATE_REMOTE_CLUSTER_HEADER_KEY, thresh.HeaderValue); err != nil {
				proxywasm.LogCriticalf("Couldn't set request header SLATE_REMOTE_CLUSTER_HEADER_KEY: %v", err)
				return types.ActionContinue
			}
		}
	}
	return types.ActionContinue
}

/*
map x-request-id to start time in millis.
when we get the response headers, we can calculate the duration of the request.
*/
func (ctx *httpContext) OnHttpStreamDone() {
	// get x-request-id from request headers and lookup entry time
	reqId, err := proxywasm.GetHttpRequestHeader("x-request-id")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header: %v", err)
		return
	}
	data, _, err := proxywasm.GetSharedData(reqId)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	startTime := int64(binary.LittleEndian.Uint64(data))
	currentTime := time.Now().UnixMilli()
	requestDuration := uint64(currentTime - startTime)
	//proxywasm.LogCriticalf("request duration: %d", requestDuration)

	data, _, err = proxywasm.GetSharedData(AGGREGATE_REQUEST_LATENCY)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	agLatency := binary.LittleEndian.Uint64(data) + requestDuration
	buf := make([]byte, 8)
	binary.LittleEndian.PutUint64(buf, agLatency)
	if err := proxywasm.SetSharedData(AGGREGATE_REQUEST_LATENCY, buf, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data: %v", err)
		return
	}

}

func OnTickHttpCallResponse(numHeaders, bodySize, numTrailers int) {
	// receive RPS thresholds, set shared data accordingly
	hdrs, err := proxywasm.GetHttpCallResponseHeaders()
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get http call response headers: %v", err)
		return
	}
	proxywasm.LogCriticalf("received http call response, status %v body size: %d", hdrs, bodySize)
	if bodySize == 0 {
		return
	}
	respBody, err := proxywasm.GetHttpCallResponseBody(0, bodySize)
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get http call response body: %v", err)
		return
	}
	proxywasm.LogCriticalf("setting rps thresholds: %s", string(respBody))
	// set thresholds
	if err := proxywasm.SetSharedData(KEY_RPS_THRESHOLDS, respBody, 0); err != nil {
		proxywasm.LogCriticalf("Couldn't set shared data for rps thresholds: %v", err)
		return
	}
}

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
