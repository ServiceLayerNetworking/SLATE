# WASM/Controller API

This document describes the interaction between the WASM plugin and the global controller.

## WASM Request Lifecycle

`POST /proxyLoad`

Request Headers:
- `x-slate-clusterid`: The cluster/node ID that the request is being sent from. This is given to the WASM plugin from an environment
variable set in the Deployment.
- `x-slate-servicename`: The name of the service that the request is being sent from.
- `x-slate-podname`: The name of the pod that the request is being sent from.

Request Body Structure:
```
numRequests
method path traceId spanId parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
method path traceId spanId parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
method path traceId spanId parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
```

**gangmuk**
```
service_level_rps
endpoint_0, endpoint_1, endpoint_2
rps_endpoint_0, rps_endpoint_1, rps_endpoint_2
method path traceId spanId parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
method path traceId spanId parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
method path traceId spanId parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
```

First line is always number of requests from the current iteration, and the following lines are the requests statistics themselves.

*THE RESPONSE NEEDS TO BE THE PLAINTEXT STRUCTURE*

Response headers:
- `x-slate-ruleschanged`: Whether or not the rules have changed since the last request. 0 if not changed, 1 if changed.

Response Body Structure (JSON):
```json
{
    "changed": "0",
    "distributions": [
      {
        "matchHeaders": {
          ":method": "GET",
          ":path": "/foo"
        },
        "distribution": [
          {
            "header": "cluster1",
            "weight": 90
          },
          {
            "header": "cluster2",
            "weight": 10
          }
        ]
      }
    ]
}
```

Plaintext structure
```
:method GET,:path /foo|cluster1:90 cluster2:10
:method POST,:path /bar|cluster1:70 cluster2:30
```

- `changed` is whether or not this is a new distribution for this given service. If it is, the WASM plugin should reset its internal state and use those distributions.
- `distributions[0].matchHeaders` contains the headers that the WASM plugin should match outgoing requests against. If matched, the WASM plugin should attach the headers in `distributions[0].distribution` to the outgoing request given the weights.
