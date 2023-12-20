
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
```python
callgraph_table: {callgraph_A_key: callgrah_A, callgraph_B_key: callgrap_B}
num_requests = {callgraph_A_key: 10, callgraph_B_key: 200}
```

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