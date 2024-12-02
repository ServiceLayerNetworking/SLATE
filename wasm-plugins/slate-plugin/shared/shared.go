package shared

import (
	"encoding/binary"
	"errors"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm"
	"github.com/tetratelabs/proxy-wasm-go-sdk/proxywasm/types"
	"strings"
)

const (
	KEY_REQUEST_COUNT          = "slate_rps"
	KEY_HILLCLIMB_INBOUNDRPS   = "hillclimbing_inboundrps"
	KEY_NO_TRACEID             = "no_traceid"
	KEY_ENDPOINT_RPS_LIST      = "slate_endpoint_rps_list"
	KEY_OUTBOUND_ENDPOINT_LIST = "slate_outbound_endpoint_list"
	KEY_INBOUND_ENDPOINT_LIST  = "slate_inbound_endpoint_list"
	KEY_TRACED_REQUESTS        = "slate_traced_requests"
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
	readPosBytes, _, err := proxywasm.GetSharedData(TimestampListReadPosKey(method, path))
	if err != nil {
		return 0
	}
	readPos := binary.LittleEndian.Uint64(readPosBytes)
	writePosBytes, _, err := proxywasm.GetSharedData(TimestampListWritePosKey(method, path))
	if err != nil {
		return 0
	}
	writePos := binary.LittleEndian.Uint64(writePosBytes)
	queueSize := writePos - readPos
	return queueSize / 4
}

// Get the current load conditions of all traced requests.
func GetEndpointLoadConditions() (map[string]EndpointStats, error) {
	requestStats := make(map[string]EndpointStats)
	rpsEndpoints, _, err := proxywasm.GetSharedData(KEY_ENDPOINT_RPS_LIST)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data for rps request stats: %v", err)
		return nil, err
	}
	if len(rpsEndpoints) == 0 || errors.Is(err, types.ErrorStatusNotFound) || EmptyBytes(rpsEndpoints) {
		// no requests traced
		return requestStats, nil
	}
	rpsEndpointsList := strings.Split(string(rpsEndpoints), ",")
	for _, endpoint := range rpsEndpointsList {
		if EmptyBytes([]byte(endpoint)) {
			continue
		}
		mp := strings.Split(endpoint, "@")
		if len(mp) != 2 {
			continue
		}
		method := mp[0]
		path := mp[1]
		requestStats[endpoint] = EndpointStats{
			Inflight: 0,
			Total:    TimestampListGetRPS(method, path),
		}
	}

	return requestStats, nil
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

// AddToSharedDataSet adds a value to a list stored in shared data at the given key, if it is not already in the list.
// The list is stored as a comma separated string.
func AddToSharedDataSet(key string, value string) {
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

// AddToSharedDataList adds a value to a list stored in shared data at the given key.
// The list is stored as a comma separated string.
func AddToSharedDataList(key string, value string) {
	listBytes, cas, err := proxywasm.GetSharedData(key)
	if err != nil && !errors.Is(err, types.ErrorStatusNotFound) {
		proxywasm.LogCriticalf("Couldn't get shared data: %v", err)
		return
	}
	if len(listBytes) == 0 {
		listBytes = []byte(value)
	} else {
		list := string(listBytes)
		if list[len(list)-1] != ',' {
			list += ","
		}
		list += value
		listBytes = []byte(list)
	}
	if err := proxywasm.SetSharedData(key, listBytes, cas); err != nil {
		proxywasm.LogCriticalf("unable to set shared data: %v", err)
		return
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

func OutboundRequestListElementKey(dstsvc string, method string, path string) string {
	return dstsvc + "@" + method + "@" + path
}

func InboundRequestListElementKey(method string, path string) string {
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

func OutboundLatencyRunningAvgKey(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-outbound-latency"
}

func OutboundLatencyTotalRequestsKey(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-outbound-latency-totalrequests"
}

func InboundLatencyM2Key(method, path string) string {
	return method + "@" + path + "-inbound-latency-m2"
}

func OutboundLatencyM2Key(svc, method, path string) string {
	return svc + "@" + method + "@" + path + "-outbound-latency-m2"
}

func InboundLatencyListKey(method, path string) string {
	return method + "@" + path + "-inbound-latency-list"
}

func RegionOutboundLatencyRunningAvgKey(svc, method, path, region string) string {
	return svc + "@" + method + "@" + path + "@" + region + "-outbound-latency"
}

func RegionOutboundLatencyTotalRequestsKey(svc, method, path, region string) string {
	return svc + "@" + method + "@" + path + "@" + region + "-outbound-latency-totalrequests"
}

func InboundLatencyRunningAvgKey(method, path string) string {
	return method + "@" + path + "-inbound-latency"
}

func InboundLatencyTotalRequestsKey(method, path string) string {
	return method + "@" + path + "-inbound-latency-totalrequests"
}
