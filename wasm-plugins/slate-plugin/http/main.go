package main

import (
	"crypto/md5"
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
	KEY_LAST_RESET             = "slate_last_reset"
	KEY_RPS_THRESHOLDS         = "slate_rps_threshold"
	KEY_HASH_MOD               = "slate_hash_mod"
	KEY_TRACED_REQUESTS        = "slate_traced_requests"
	// this is in millis
	AGGREGATE_REQUEST_LATENCY = "slate_last_second_latency_avg"
	KEY_RPS_SHARED_QUEUE      = "slate_rps_shared_queue"
	KEY_RPS_SHARED_QUEUE_SIZE = "slate_rps_shared_queue_size"

	// Hash mod for frequency of request tracing.
	DEFAULT_HASH_MOD = 10000000

	KEY_MATCH_DISTRIBUTION = "slate_match_distribution"
)

var (
	ALL_KEYS = []string{KEY_INFLIGHT_REQ_COUNT, KEY_LAST_RESET, KEY_RPS_THRESHOLDS, KEY_HASH_MOD, AGGREGATE_REQUEST_LATENCY,
		KEY_TRACED_REQUESTS, KEY_MATCH_DISTRIBUTION, KEY_INFLIGHT_ENDPOINT_LIST, shared.KEY_ENDPOINT_RPS_LIST, KEY_RPS_SHARED_QUEUE, KEY_RPS_SHARED_QUEUE_SIZE}
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

	tracingHashMod int
	region         string

	startTime int64
}

func (p *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
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
	tracingHashMod := os.Getenv("TRACING_HASH_MOD")
	if tracingHashMod != "" {
		tmp, _ := strconv.Atoi(tracingHashMod)
		p.tracingHashMod = tmp
	} else {
		p.tracingHashMod = DEFAULT_HASH_MOD
	}
	p.podName = pod
	p.serviceName = svc
	p.region = regionName
	region = regionName
	serviceName = svc
	return types.OnPluginStartStatusOK
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
	traceId, err := proxywasm.GetHttpRequestHeader("X-B3-TraceId")
	if err != nil {
		shared.IncrementSharedData(shared.KEY_NO_TRACEID, 1)
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

	// policy enforcement for outbound requests
	if !strings.HasPrefix(ctx.pluginContext.serviceName, dst) && !strings.HasPrefix(dst, "node") {
		// add request start time
		if err := proxywasm.AddHttpRequestHeader("x-slate-start-outbound", fmt.Sprintf("%d", time.Now().UnixMilli())); err != nil {
			proxywasm.LogCriticalf("Couldn't add request header x-slate-start-outbound: %v", err)
		}
		// the request is originating from this sidecar to another service, perform routing magic
		// get endpoint distribution
		endpointDistribution, _, err := proxywasm.GetSharedData(shared.EndpointDistributionKey(dst, reqMethod, reqPath))
		if err != nil {
			// no rules available yet.
			if err := proxywasm.AddHttpRequestHeader("x-slate-routeto", region); err != nil {
				proxywasm.LogCriticalf("Couldn't add request header x-slate-routeto [1]: %v", err)
			}
		} else {
			// draw from distribution
			coin := rand.Float64()
			total := 0.0
			distLines := strings.Split(string(endpointDistribution), "\n")
			for _, line := range distLines {
				lineS := strings.Split(line, " ")
				if len(lineS) != 2 {
					return types.ActionContinue
				}
				targetRegion := lineS[0]
				pct, err := strconv.ParseFloat(lineS[1], 64)
				if err != nil {
					proxywasm.LogCriticalf("Couldn't parse endpoint distribution line: %v", err)
					return types.ActionContinue
				}
				total += pct
				if coin <= total {
					if err := proxywasm.AddHttpRequestHeader("x-slate-routeto", targetRegion); err != nil {
						proxywasm.LogCriticalf("Couldn't add request header x-slate-routeto [2]: %v", err)
					}
					break
				}
			}
		}
		return types.ActionContinue
	}

	if err := proxywasm.AddHttpRequestHeader("x-slate-start-inbound", fmt.Sprintf("%d", time.Now().UnixMilli())); err != nil {
		proxywasm.LogCriticalf("Couldn't add request header x-slate-start-inbound: %v", err)
	}
	shared.IncrementSharedData(shared.KEY_REQUEST_COUNT, 1)
	shared.IncrementSharedData(shared.KEY_HILLCLIMB_INBOUNDRPS, 1)
	shared.AddToSharedDataSet(shared.KEY_ENDPOINT_RPS_LIST, shared.EndpointListKey(reqMethod, reqPath))
	// add the new request to our queue
	ctx.TimestampListAdd(reqMethod, reqPath)

	// if this is a traced request, we need to record load conditions and request details
	if ctx.tracedRequest(traceId) {
		spanId, _ := proxywasm.GetHttpRequestHeader("X-B3-SpanId")
		parentSpanId, _ := proxywasm.GetHttpRequestHeader("X-B3-ParentSpanId")
		bSizeStr, err := proxywasm.GetHttpRequestHeader("Content-Length")
		if err != nil {
			bSizeStr = "0"
		}
		bodySize, _ := strconv.Atoi(bSizeStr)
		// save various request attributes that we will end up reporting in OnTick()
		if err := AddTracedRequest(reqMethod, reqPath, traceId, spanId, parentSpanId, time.Now().UnixMilli(), bodySize, 4); err != nil {
			proxywasm.LogCriticalf("unable to add traced request: %v", err)
			return types.ActionContinue
		}
		// save current load conditions for this request
		endpointStats, err := shared.GetEndpointLoadConditions()
		if err != nil {
			proxywasm.LogCriticalf("Couldn't get inflight request stats: %v", err)
			return types.ActionContinue
		}
		saveEndpointStatsForTrace(traceId, endpointStats)
	}
	return types.ActionContinue
}

func (ctx *httpContext) OnHttpResponseHeaders(int, bool) types.Action {
	end := time.Now().UnixMilli()
	if d, err := proxywasm.GetHttpResponseHeader("x-slate-end"); err != nil || string(d) == "" {
		// this is the first response, record the end time
		proxywasm.AddHttpResponseHeader("x-slate-end", fmt.Sprintf("%d", end))
	} else {
		proxywasm.ReplaceHttpResponseHeader("x-slate-end", fmt.Sprintf("%d", end))
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
	traceId, err := proxywasm.GetHttpRequestHeader("X-B3-TraceId")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get request header x-b3-traceid: %v", err)
		return
	}

	reqMethod, err := proxywasm.GetHttpRequestHeader(":method")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get :method request header: %v", err)
	}
	reqPath, err := proxywasm.GetHttpRequestHeader(":path")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get :path request header: %v", err)
	}
	reqPath = strings.Split(reqPath, "?")[0]
	reqAuthority, err := proxywasm.GetHttpRequestHeader(":authority")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get :authority request header: %v", err)
	}
	dst := strings.Split(reqAuthority, ":")[0]

	// endTime is populated in OnHttpResponseHeaders
	// x-slate-end is set in OnHttpResponseHeaders, and shortly after OnHttpResponseHeaders this function is called,
	// where we get that value. It is first set in the upstream envoy OnResponseHeaders, then the upstream envoy OnStreamDone
	// uses the value, and then the downstream envoy OnResponseHeaders overwrites it, and then the downstream envoy OnStreamDone
	// uses it.
	endTimeStr, err := proxywasm.GetHttpResponseHeader("x-slate-end")
	if err != nil {
		//reqHdrs, _ := proxywasm.GetHttpRequestHeaders()
		//proxywasm.LogCriticalf("Couldn't get x-slate-end (when inbound response should have it) : %v\nreqHdrs: %v", err, reqHdrs)
		endTimeStr = fmt.Sprintf("%d", time.Now().UnixMilli())
	}
	endTime, err := strconv.ParseInt(endTimeStr, 10, 64)
	// this was an outbound request/response
	// measure running average for latency for outbound requests
	if !strings.HasPrefix(ctx.pluginContext.serviceName, dst) && !strings.HasPrefix(dst, "node") {
		processedRegion, err := proxywasm.GetHttpRequestHeader("x-slate-routeto")
		if err != nil {
			processedRegion = ctx.pluginContext.region
		}
		shared.AddToSharedDataSet(shared.KEY_OUTBOUND_ENDPOINT_LIST, shared.OutboundRequestListElementKey(dst, reqMethod, reqPath))
		startStr, err := proxywasm.GetHttpRequestHeader("x-slate-start-outbound")
		if err != nil {
			return
		}
		start, err := strconv.ParseInt(startStr, 10, 64)
		latencyMs := endTime - start
		addOutboundLatency(dst, reqMethod, reqPath, processedRegion, latencyMs, 5)
		return
	} else {
		// this was an inbound request/response.
		// measure inbound latency.
		shared.AddToSharedDataSet(shared.KEY_INBOUND_ENDPOINT_LIST, shared.InboundRequestListElementKey(reqMethod, reqPath))
		startStr, err := proxywasm.GetHttpRequestHeader("x-slate-start-inbound")
		if err != nil {
			return
		}
		start, err := strconv.ParseInt(startStr, 10, 64)
		latencyMs := endTime - start
		addInboundLatency(reqMethod, reqPath, latencyMs, 5)
	}

	// record end time
	endTimeBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(endTimeBytes, uint64(endTime))
	if err := proxywasm.SetSharedData(shared.EndTimeKey(traceId), endTimeBytes, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v endTime: %v %v", traceId, endTime, err)
	}
}

func addOutboundLatency(svc, method, path, region string, latencyMs int64, retries int) {
	// get the old average and variance
	outboundLatencyAvgKey := shared.OutboundLatencyRunningAvgKey(svc, method, path)
	outboundLatencyTotal := shared.OutboundLatencyTotalRequestsKey(svc, method, path)
	// set the new average and variance
	shared.IncrementSharedData(outboundLatencyAvgKey, latencyMs)
	shared.IncrementSharedData(outboundLatencyTotal, 1)

	// increment region latency
	regionLatencyAvgKey := shared.RegionOutboundLatencyRunningAvgKey(svc, method, path, region)
	regionLatencyTotal := shared.RegionOutboundLatencyTotalRequestsKey(svc, method, path, region)
	shared.IncrementSharedData(regionLatencyAvgKey, latencyMs)
	shared.IncrementSharedData(regionLatencyTotal, 1)
}

func addInboundLatency(method, path string, latencyMs int64, retries int) {
	inboundLatencyAvgKey := shared.InboundLatencyRunningAvgKey(method, path)
	inboundLatencyTotal := shared.InboundLatencyTotalRequestsKey(method, path)

	oldLatencyTotal := shared.GetUint64SharedDataOrZero(inboundLatencyAvgKey)
	oldTotalRequests := shared.GetUint64SharedDataOrZero(inboundLatencyTotal)
	m2Key := shared.InboundLatencyM2Key(method, path)
	if oldTotalRequests == 0 {
		newM2 := 0.0
		// Set the initial M2
		newM2Str := fmt.Sprintf("%f", newM2)
		if err := proxywasm.SetSharedData(m2Key, []byte(newM2Str), 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data for traceId %v m2: %v %v", m2Key, newM2Str, err)
		}
		shared.IncrementSharedData(inboundLatencyAvgKey, latencyMs)
		shared.IncrementSharedData(inboundLatencyTotal, 1)
		return
	}
	oldAvg := float64(oldLatencyTotal) / float64(oldTotalRequests)
	oldDiff := float64(latencyMs) - oldAvg
	newAvg := (float64(oldTotalRequests)*oldAvg + float64(latencyMs)) / float64(oldTotalRequests+1)
	newDiff := float64(latencyMs) - newAvg
	oldM2Bytes, cas, err := proxywasm.GetSharedData(m2Key)
	oldM2 := "0"
	if err == nil {
		oldM2 = string(oldM2Bytes)
	}
	oldM2Float, _ := strconv.ParseFloat(oldM2, 64)
	newM2 := oldM2Float + oldDiff*newDiff
	// set new m2 as string
	newM2Str := fmt.Sprintf("%f", newM2)
	if err := proxywasm.SetSharedData(m2Key, []byte(newM2Str), cas); err != nil {
		if retries == 0 {
			proxywasm.LogCriticalf("unable to set shared data for traceId %v m2: %v %v", m2Key, newM2Str, err)
			return
		}
		addInboundLatency(method, path, latencyMs, retries-1)
	}

	shared.IncrementSharedData(inboundLatencyAvgKey, latencyMs)
	shared.IncrementSharedData(inboundLatencyTotal, 1)
	//shared.AddToSharedDataList(shared.InboundLatencyListKey(method, path), fmt.Sprintf("%d", latencyMs))
}

// AddTracedRequest adds a traceId to the set of traceIds we are tracking (this is collected every Tick and sent
// to the controller), and set attributes in shared data about the traceId.
func AddTracedRequest(method, path, traceId, spanId, parentSpanId string, startTime int64, bodySize int, retries int) error {
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
		if retries == 0 {
			proxywasm.LogCriticalf("unable to set shared data for traced requests (and out of retries): %v", err)
			return err
		}
		return AddTracedRequest(method, path, traceId, spanId, parentSpanId, startTime, bodySize, retries-1)
	}
	// set method, path, spanId, parentSpanId, and startTime for this traceId
	if err := proxywasm.SetSharedData(shared.MethodKey(traceId), []byte(method), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v method: %v %v", traceId, method, err)
		return err
	}

	if err := proxywasm.SetSharedData(shared.PathKey(traceId), []byte(path), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v path: %v %v", traceId, path, err)
		return err
	}

	//proxywasm.LogCriticalf("spanId: %v parentSpanId: %v startTime: %v", spanId, parentSpanId, startTime)
	if err := proxywasm.SetSharedData(shared.SpanIdKey(traceId), []byte(spanId), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v spanId: %v %v", traceId, spanId, err)
		return err
	}

	// possible if this is the root
	if parentSpanId != "" {
		if err := proxywasm.SetSharedData(shared.ParentSpanIdKey(traceId), []byte(parentSpanId), 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data for traceId %v parentSpanId: %v %v", traceId, parentSpanId, err)
			return err
		}
	}
	startTimeBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(startTimeBytes, uint64(startTime))
	if err := proxywasm.SetSharedData(shared.StartTimeKey(traceId), startTimeBytes, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v startTime: %v %v", traceId, startTime, err)
		return err
	}

	bodySizeBytes := make([]byte, 8)
	binary.LittleEndian.PutUint64(bodySizeBytes, uint64(bodySize))
	if err := proxywasm.SetSharedData(shared.BodySizeKey(traceId), bodySizeBytes, 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v bodySize: %v %v", traceId, bodySize, err)
	}
	return nil
}

func saveEndpointStatsForTrace(traceId string, stats map[string]shared.EndpointStats) {
	if traceId == "" || len(stats) == 0 {
		return
	}
	str := ""
	for k, v := range stats {
		str += fmt.Sprintf("%s,%d,%d", k, v.Total, 0) + "|"
	}
	if err := proxywasm.SetSharedData(shared.EndpointInflightStatsKey(traceId), []byte(str), 0); err != nil {
		proxywasm.LogCriticalf("unable to set shared data for traceId %v endpointInflightStats: %v %v", traceId, str, err)
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
It also evicts timestamps older than the given time.

The general idea is to have a fixed size buffer of timestamps, and we rotate the buffer when we reach the end.
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
	timestampListBytes, cas, err := proxywasm.GetSharedData(shared.SharedQueueKey(method, path))
	if err != nil {
		// nothing there, just set to the current time
		// 4 bytes per request, so we can store 1750 requests in 7000 bytes
		newListBytes := make([]byte, 7000)
		binary.LittleEndian.PutUint32(newListBytes, t)
		if err := proxywasm.SetSharedData(shared.SharedQueueKey(method, path), newListBytes, cas); err != nil {
			h.TimestampListAdd(method, path)
			return
		}
		// set write pos
		writePos := make([]byte, 8)
		binary.LittleEndian.PutUint32(writePos, 4)
		if err := proxywasm.SetSharedData(shared.TimestampListWritePosKey(method, path), writePos, 0); err != nil {
			proxywasm.LogCriticalf("unable to set shared data for timestamp write pos: %v", err)
		}

		return
	}
	// get write position
	timestampPos, writeCas, err := proxywasm.GetSharedData(shared.TimestampListWritePosKey(method, path))
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get shared data for timestamp write pos: %v", err)
		return
	}
	writePos := binary.LittleEndian.Uint64(timestampPos)
	// if we're at the end of the list, we need to rotate list
	if writePos+4 > uint64(len(timestampListBytes)) {
		proxywasm.LogCriticalf("[REACHED CAPACITY, ROTATING]")
		// rotation magic
		readPosBytes, readCas, err := proxywasm.GetSharedData(shared.TimestampListReadPosKey(method, path))
		if err != nil {
			proxywasm.LogCriticalf("[ROTATION MAGIC] Couldn't get shared data for timestamp read pos: %v", err)
			return
		}
		readPos := binary.LittleEndian.Uint64(readPosBytes)
		if readPos == 0 {
			// either (1) requests are coming in so fast that none have been evicted yet, or (2) another thread`1
			// already rotated the list
			return
		}

		// copy readPos to writePos to the beginning of the list
		bytesRemaining := len(timestampListBytes) - int(readPos)
		copy(timestampListBytes, timestampListBytes[readPos:])
		// potential problem with setting readPos and writePos separately is that if anothe thread is writing to the list,
		// it could overwrite the new writePos before we set it.
		// set readPos to 0
		readPosBytes = make([]byte, 8)
		binary.LittleEndian.PutUint64(readPosBytes, 0)
		if err := proxywasm.SetSharedData(shared.TimestampListReadPosKey(method, path), readPosBytes, readCas); err != nil {
			proxywasm.LogCriticalf("[ROTATION MAGIC] unable to set shared data for timestamp read pos: %v", err)
			return
		}
		// set writePos to the end of the segment we just rotated
		writePos = uint64(bytesRemaining)
		// set writePos
		writePosBytes := make([]byte, 8)
		binary.LittleEndian.PutUint64(writePosBytes, writePos)
		if err := proxywasm.SetSharedData(shared.TimestampListWritePosKey(method, path), writePosBytes, writeCas); err != nil {
			proxywasm.LogCriticalf("[ROTATION MAGIC] unable to set shared data for timestamp write pos: %v", err)
		}
	}
	// add new timestamp
	if writePos >= uint64(len(timestampListBytes)) {
		proxywasm.LogCriticalf("writePos: %v, len: %v", writePos, len(timestampListBytes))
		// just fuck off and dont write anything until all threads sync
		return
	}
	binary.LittleEndian.PutUint32(timestampListBytes[writePos:], t)

	if err := proxywasm.SetSharedData(shared.SharedQueueKey(method, path), timestampListBytes, cas); err != nil {
		h.TimestampListAdd(method, path)
		return
	}
	// change write position *after* writing new bytes was success
	shared.IncrementSharedData(shared.TimestampListWritePosKey(method, path), 4)

	// evict old entries while we're at it
	timeMillisCutoff := h.GetTime() - 1000
	// get timestamp read position
	readPosBytes, cas2, err := proxywasm.GetSharedData(shared.TimestampListReadPosKey(method, path))
	if err != nil {
		// set read pos to 0
		readPosBytes = make([]byte, 8)
		binary.LittleEndian.PutUint64(readPosBytes, 0)
		if err := proxywasm.SetSharedData(shared.TimestampListReadPosKey(method, path), readPosBytes, 0); err != nil {
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
	if err := proxywasm.SetSharedData(shared.TimestampListReadPosKey(method, path), readPosBytes, cas2); err != nil {
		return
	}
}

func (h *httpContext) tracedRequest(traceId string) bool {
	// use md5 for speed
	hash := md5Hash(traceId)
	return hash%h.pluginContext.tracingHashMod == 0
}

func md5Hash(s string) int {
	h := md5.New()
	h.Write([]byte(s))
	return int(binary.LittleEndian.Uint64(h.Sum(nil)))
}
