package shared

import (
	"encoding/binary"
	"errors"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
	"strings"
)

const (
	KEY_HILLCLIMBING_ENABLED       = "hillclimbing_enabled"
	KEY_REQUEST_COUNT              = "slate_rps"
	KEY_HILLCLIMB_INITIAL_STEPSIZE = "initial_hillclimbing_stepsize"
	KEY_HILLCLIMB_INTERVAL         = "hillclimbing_interval"
	KEY_HILLCLIMB_INBOUNDRPS       = "hillclimbing_inboundrps"
)

// TracedRequestStats is a struct that holds information about a traced request.
// This is what is reported to the controller.
type TracedRequestStats struct {
	Method       string
	Path         string
	TraceId      string
	SpanId       string
	ParentSpanId string
	StartTime    int64
	EndTime      int64
	BodySize     int64
}

// Statistic for a given endpoint.
type EndpointStats struct {
	Inflight uint64
	Total    uint64
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

func InboundCountKey(traceId string) string {
	return traceId + "-inbound-request-count"
}

func SpanIdKey(traceId string) string {
	return traceId + "-s"
}

func ParentSpanIdKey(traceId string) string {
	return traceId + "-p"
}

func StartTimeKey(traceId string) string {
	return traceId + "-startTime"
}

func EndTimeKey(traceId string) string {
	return traceId + "-endTime"
}

func BodySizeKey(traceId string) string {
	return traceId + "-bodySize"
}

func FirstLoadKey(traceId string) string {
	return traceId + "-firstLoad"
}

func MethodKey(traceId string) string {
	return traceId + "-method"
}

func PathKey(traceId string) string {
	return traceId + "-path"
}

func EmptyBytes(b []byte) bool {
	for _, v := range b {
		if v != 0 {
			return false
		}
	}
	return true
}

func EndpointListKey(method string, path string) string {
	return method + "@" + path
}

func InflightCountKey(method string, path string) string {
	return "inflight/" + method + "-" + path
}

func EndpointCountKey(method string, path string) string {
	return "endpointRPS/" + method + "-" + path
}

func EndpointInflightStatsKey(traceId string) string {
	return traceId + "-endpointInflightStats"
}

func EndpointDistributionKey(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-distribution"
}

func LastRecvRulesKey(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-lastrecv"
}

func SharedQueueKey(method, path string) string {
	return method + "@" + path
}

func SharedQueueSizeKey(method, path string) string {
	return method + "@" + path + "-queuesize"
}

func TimestampListWritePosKey(method, path string) string {
	return method + "@" + path + "-writepos"
}

func TimestampListReadPosKey(method, path string) string {
	return method + "@" + path + "-readpos"
}

func PrevOutboundLatencyRunningAvgKey(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-prev-outbound-latency"
}

func OutboundLatencyRunningAvgKey(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-outbound-latency"
}

func OutboundLatencyTotalRequestsKey(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-outbound-latency-totalrequests"
}
func RegionOutboundLatencyRunningAvgKey(svc, method, path, region string) string {
	return svc + "@" + method + "@" + path + "@" + region + "-outbound-latency"
}

func RegionOutboundLatencyTotalRequestsKey(svc, method, path, region string) string {
	return svc + "@" + method + "@" + path + "@" + region + "-outbound-latency-totalrequests"
}
