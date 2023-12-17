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

---

# external api and internal api

 In a microservices architecture, the method or URL of an HTTP request might be changed as it passes through different microservices for various reasons such as abstraction, encapsulation, and optimization. Here are some examples:

### API Gateway Transformation:

- An API Gateway might transform the URL to route requests to different microservices based on a path or header. For instance:
  - Original Request: `GET /api/orders/123`
  - Transformed Request: `GET /internal/orders-service/orders/123`

### Internal Routing and Composition:

- Requests might go through multiple microservices, each responsible for a specific part of the functionality. The URL or method might change at each stage. For example:
  - Original Request: `GET /products/456`
  - Microservice A: `GET /internal/product-service/products/456`
  - Microservice B: `POST /internal/inventory-service/check-availability`

### Service Mesh Routing:

- In a service mesh, sidecar proxies might change the URL or method based on routing rules. For instance:
  - Original Request: `PUT /api/update-user`
  - Routed through Service Mesh: `PUT /internal/user-service/update-user`

### Versioning:

- Different versions of a microservice might expose APIs with different paths to maintain backward compatibility:
  - Original Request: `GET /api/v1/resource`
  - Routed to v2 of the service: `GET /internal/service-v2/resource`

### Security and Authentication:

- The URL or method might change to include security-related information as requests pass through microservices:
  - Original Request: `GET /api/sensitive-data`
  - Routed through Auth Service: `GET /internal/auth-service/verify-and-retrieve/sensitive-data`

### Dynamic Routing Based on Load:

- Requests might be dynamically routed to different microservices based on load or other runtime conditions:
  - Original Request: `GET /api/data`
  - Routed dynamically: `GET /internal/data-service-instance-2/data`

### Content Transformation:

- Microservices might expect different content types, leading to the transformation of the request body:
  - Original Request: `POST /api/process-data` with JSON body
  - Routed to another service: `POST /internal/data-processor/process` with XML body

### Proxying to Legacy Systems:

- Requests might be routed through microservices acting as proxies to legacy systems with different interfaces:
  - Original Request: `GET /api/new-feature`
  - Routed through Proxy: `GET /internal/legacy-proxy-service/legacy-feature`

