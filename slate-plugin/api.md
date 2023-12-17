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
traceId spanId, parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
traceId spanId, parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
traceId spanId, parentSpanId startTime endTime bodySize firstLoad lastLoad avgLoad rps
```
First line is always number of requests from the current iteration, and the following lines are the requests statistics themselves.

Response Body Structure:
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

- `changed` is whether or not this is a new distribution for this given service. If it is, the WASM plugin should reset its internal state and use those distributions.
- `distributions[0].matchHeaders` contains the headers that the WASM plugin should match outgoing requests against. If matched, the WASM plugin should attach the headers in `distributions[0].distribution` to the outgoing request given the weights.

