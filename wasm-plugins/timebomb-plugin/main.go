package main

import (
	"encoding/binary"
	"strconv"
	"time"
	"strings"
	"os"

	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
)

const (
	KEY_INFLIGHT_REQUESTS = "inflight_requests"
)


func main() {
	proxywasm.SetVMContext(&vmContext{})

}

type vmContext struct {
	// Embed the default VM context here,
	// so that we don't need to reimplement all the methods.
	types.DefaultVMContext
}

func (*vmContext) OnVMStart(vmConfigurationSize int) types.OnVMStartStatus {
	// set initial value for inflight requests
	proxywasm.SetSharedData(KEY_INFLIGHT_REQUESTS, make([]byte, 8), 0)
	return types.OnVMStartStatusOK
}

// Override types.DefaultVMContext.
func (*vmContext) NewPluginContext(contextID uint32) types.PluginContext {
	svc := os.Getenv("ISTIO_META_WORKLOAD_NAME")
	if svc == "" {
		svc = "SLATE_UNKNOWN_SVC"
	}
	return &pluginContext{
		contextID: contextID,
		queue: make(RequestPriorityQueue, 0),
		inflightCapacity: 1,
		serviceName: svc,
	}
}

type pluginContext struct {
	// Embed the default plugin context here,
	// so that we don't need to reimplement all the methods.
	types.DefaultPluginContext
	contextID uint32
	serviceName string

	inflightCapacity uint64
	queue RequestPriorityQueue
}

// Override types.DefaultPluginContext.
func (ctx *pluginContext) OnPluginStart(pluginConfigurationSize int) types.OnPluginStartStatus {
	return types.OnPluginStartStatusOK
}

// Override types.DefaultPluginContext.
func (ctx *pluginContext) NewHttpContext(contextID uint32) types.HttpContext {
	return &httpContext{
		contextID: contextID,
		pluginCtx: ctx,
	}
}

type httpContext struct {
	// Embed the default http context here,
	// so that we don't need to reimplement all the methods.
	types.DefaultHttpContext
	contextID uint32
	pluginCtx *pluginContext
}

// Override types.DefaultHttpContext.
func (ctx *httpContext) OnHttpRequestHeaders(numHeaders int, endOfStream bool) types.Action {
	reqAuthority, err := proxywasm.GetHttpRequestHeader(":authority")
	if err != nil {
		proxywasm.LogCriticalf("Couldn't get :authority request header: %v", err)
		return types.ActionContinue
	}
	dst := strings.Split(reqAuthority, ":")[0]
	if !strings.HasPrefix(ctx.pluginCtx.serviceName, dst) && !strings.HasPrefix(dst, "172") {
		return types.ActionContinue
	}

	// if we reach inflight capacity, insert request (keyed by current time minus request start time) into heap
	reqStartTimeBytes, err := proxywasm.GetHttpRequestHeader("x-slate-start")
	if err != nil {
		proxywasm.LogCriticalf("failed to get request start time: %v", err)
		return types.ActionContinue
	}
	// in unix millis
	reqStartTime, err := strconv.ParseUint(string(reqStartTimeBytes), 10, 64)
	if err != nil {
		proxywasm.LogCriticalf("failed to parse request start time: %v", err)
		return types.ActionContinue
	}
	inflightBytes, cas, err := proxywasm.GetSharedData(KEY_INFLIGHT_REQUESTS)
	if err != nil {
		proxywasm.LogCriticalf("failed to get shared data: %v", err)
		return types.ActionContinue
	}
	inflight := binary.LittleEndian.Uint64(inflightBytes)
	if inflight >= ctx.pluginCtx.inflightCapacity {
		// pause request
		prio := uint64(time.Now().UnixMicro() - int64(reqStartTime))
		// if testing just queue
		// prio := uint64(time.Now().UnixMilli())
		proxywasm.LogCriticalf("pausing request with contextID=%v, priority=%v", ctx.contextID, prio)
		ctx.pluginCtx.queue.Push(&PausedRequest{
			value: ctx.contextID,
			priority: prio,
		})
		return types.ActionPause
	} else {
		// inflight capacity not reached, increment inflight and continue
		proxywasm.LogCriticalf("inflight capacity not reached, increment inflight")
		inflight++
		binary.LittleEndian.PutUint64(inflightBytes, inflight)
		if err := proxywasm.SetSharedData(KEY_INFLIGHT_REQUESTS, inflightBytes, cas); err != nil {
			// inflight was updated, redo
			return ctx.OnHttpRequestHeaders(numHeaders, endOfStream)
		}
		proxywasm.LogCriticalf("incremented inflight to %v, httpCtx: %v", inflight, ctx.contextID)
		return types.ActionContinue
	
	}
}

func (ctx *httpContext) OnHttpResponseHeaders(numHeaders int, endOfStream bool) types.Action {
	if server, err := proxywasm.GetHttpResponseHeader("server"); err == nil && server == "istio-envoy" {
		// proxywasm.LogCriticalf("ignoring response from envoy")
		return types.ActionContinue
	}

	proxywasm.LogCriticalf("OnRespHeaders, httpCtx: %v, queue size: %v", ctx.contextID, len(ctx.pluginCtx.queue))
	// For deciding which paused request to resume, we can use a max heap keyed on request flight time.
	if len(ctx.pluginCtx.queue) > 0 {
		item := ctx.pluginCtx.queue.Pop().(*PausedRequest)
		proxywasm.LogCriticalf("resume request with contextID=%v, prio=%v", item.value, item.priority)
		proxywasm.SetEffectiveContext(item.value)
		// todo do we have to modify inflight count here? There's no difference if we just trade a response for a request.
		// basically, does this end up calling OnHttpRequestHeaders again? if not, we don't need to do anything/
		proxywasm.ResumeHttpRequest()
	} else {
		// decrement inflight count
		proxywasm.LogCriticalf("decrement inflight")
		inflightBytes, cas, err := proxywasm.GetSharedData(KEY_INFLIGHT_REQUESTS)
		if err != nil {
			proxywasm.LogCriticalf("failed to get shared data: %v", err)
			return types.ActionContinue
		}
		inflight := binary.LittleEndian.Uint64(inflightBytes)
		inflight--
		binary.LittleEndian.PutUint64(inflightBytes, inflight)
		if err := proxywasm.SetSharedData(KEY_INFLIGHT_REQUESTS, inflightBytes, cas); err != nil {
			// inflight was updated, redo
			return ctx.OnHttpResponseHeaders(numHeaders, endOfStream)
		}
	}
	return types.ActionContinue
}
