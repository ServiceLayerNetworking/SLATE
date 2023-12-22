
### What we need is 
- number of requests per callgraph
- defining callgraph_key
- mapping callgraph_key -> callgraph
- call graph is not same as trace. Hence, we need trace-to-callgraph function.


### What is callgraph?
- Callgraph is a combination of service topology and method,url of services in the topology
- If service topology and method and url of all services of two different traces(request) are the same, then they are considered to have the same category.
service topology
  - { A: [B, C], B: [D], C: [], D: [] }
      
method and url of services
  - { A: {method: "GET", url: "/product/123"}, B: {method: "GET", url: "/reviews"}, C: {method: "POST", url: "/details/456"}, D: {method: "GET", url: "/ratings"} }

### Change traces data structure in the global controller
Current traces data structure:
    traces[cluster_id][trace_id][service_name] = span

==>

New traces data structure:
    traces[cluster_id][trace_id] = [span_A, span_B, span_C, span_D]
    why do we need this data structure?
    because span_* will be added individually but not at once,
    call graph can be constructed when all spans are collected.
    Hence, first we append spans as they arrive at the global controller and transform complete traces only to call graph.
    What about latency? cg should be classified instantly to count the number requests for each call graph.


### Span data structure
existing span data structure += method and url of the service

### endpoint data structure
```python
endpoint = {"service": "productpage", \
            "method": "GET", \
            "url": "/productpage/login"}
```

### Call graph data structure
A->B, A->C, B->D
```python
callgraph = {A_span: [B_span, C_span], B_span:[D_span], C_span:[], D_span:[]}
```

If two call graphs have the same list of the endpoints

### Trace to Call graph
```python
def trace_to_callgraph(single_trace):
    key = ""
    callgraph = dict()
    for parent_svc, parent_span in single_trace_.items():
        callgraph[parent_span] = list()
        for child_svc, child_span in single_trace_.items():
            if child_span.parent_span_id == parent_span.my_span_id:
                callgraph[parent_span].append(child_span)
        callgraph[parent_span].sort() # for unique callgraph key
    return callgraph

def get_key_of_callgraph(cg):
    root_span = find_root_span(cg)
    cg_key = list()
    for parent_span in cg:
        cg_key.append(parent_span.svc_name)
        cg_key.append(parent_span.method)
        cg_key.append(parent_span.url)
        for child_span in cg[parent_span]:
            cg_key.append(child_span.svc_name)
            cg_key.append(child_span.method)
            cg_key.append(child_span.url)
    return cg_key

```

### Call graph table

endpoint: "svc_name,method,url"
```
endpoint_0 -> endpoint_1
endpoint_1 -> endpoint_2, endpoint_3
endpoint_3 -> endpoint_4
```

bfs the callgraph and append svc_name,method,url of each span
callgraph_key: "endpoint_0,endpoint_1,endpoint_2,endpoint_3,endpoint_4"

```python
callgraph_table = {callgraph_A_key: callgrah_A, callgraph_B_key: callgrap_B}
```

### endpoint_level_load
if the ingress_gateway endpoint is unique for every callgraph, then cg_key can be replaced with the ingress endpoint.
```python
per_cluster_endpoint_level_load = { cid_0: {"ingress_gw": {"endpoint_0": 66, ...}, "productpage": {"endpoint_4": 45, ...}}, cid_1: {"ingress_gw": {"endpoint_0": 33, ...}, "productpage": {"endpoint_4": 22, ...}} }
```
ASSUMPTION: A endpoint at the ingress gw can be used as a unique to classify the call graphs.
per cluster per endpoint ingress gw load will look like
```python
per_cluster_endpoint_level_load[cid][ingress_gw_svc_name][wanted_endpoint]
```

How should the load be normalize? by what?
- For service level load, normalize the loads in each service **by load ingress gateway**
- For endpoint level load, normalize the loads in each endpoint **by unique endpoint at the ingress gateway**
  - It is assuming that two different call graphs always have different ingress gateway endpoint.
  - It is not true in real world case. It becomes the problem of how requests should be classfied.
    - cache_setting, premium user, ...

```python
service_level_request_weight_in_out = {"productpage": 1, "details": 0.7, "reviews": 0.6, "ratings": 0.5}
endpoint_level_request_weight_in_out = {cg_key_A: {"endpoint_0": 1, "endpoint_1": 0.5, ... }, cg_key_B: {"endpoint_0": 1, "endpoint_1": 0.8, ... }}
```
Why endpoint_level_request_weight_in_out is not just 1:1 ratio. This is because the notion of call graph in our system could be coarse.

### Trace/Request classification
```python
cg_list = list()
for single_trace in complete_traces:
    cg = trace_to_callgraph(single_trace)
    cg_list.append(cg)
    cg_key = get_key_of_callgraph(cg)
    if cg_key not in callgraph_table:
        callgraph_table[cg_key] = cg
    if cg_key not in num_requests:
        num_requests[cg_key] = 0
    else:
        num_requests[cg_key] += 1
```