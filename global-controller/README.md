
# Docker error
```bash
ERROR: permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Get "http://%2Fvar%2Frun%2Fdocker.sock/_ping": dial unix /var/run/docker.sock: connect: permission denied
permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: Post "http://%2Fvar%2Frun%2Fdocker.sock/v1.24/images/ghcr.io/adiprerepa/slate-controller-py/push?tag=latest": dial unix /var/run/docker.sock: connect: permission denied
```
Run
```bash
sudo chmod 666 /var/run/docker.sock
```

# Global controller

Global controller has two modes. One is `profile` and the other is `runtime`.

In `profile` mode
- `write_trace_str_to_file`
- `handleproxyload`

In `runtime` mode
- `training_phase`
- `optimizer_entrypoint`
- `handleproxyload`

## `read_config_file`
function reads `env.txt` files. It is invoked every 5 seconds regardless of the mode.
If you want to change the mode, use `./set_env.sh [profile|runtime]`

## `handleProxyLoad` endpoint 
It is triggered by every wasm in every sidecar pod for every ontick period (check `SLATE/slate-plugin/main.go` `TICK_PERIOD` variable)
- parsed `inflightStats` is empty string. Init all `endpoint_level_rps` and `endpoint_level_inflight` to 0.
- Set `endpoint_level_rps` and `endpoint_level_inflight` for the given `region`, `svc`, `ep`
`endpoint_level_rps` and `endpoint_level_inflight` will be used by optimizer

**If it is `profile` mode**
1. Parse received spans into `Span` object
2. Append parsed `Span` objects into `trace_str_list` object
3. Set `csv_string` to empty string
   - In profile mode, it does not run optimizer. Hence, routing rule is always local routing.
**NOTE**: svc name will truncate region name after `"-us-"` in it. (region is given separately in `x-slate-region` header)

**If it is `runtime` mode**
Check `percentage_df` variable (`percentage_df` is set by `run_optimizer`)
If `percentage_df` is empty, in other words routing rule is not optimized by optimizer
- Set `csv_string` = "" (local routing)

If `percentage_df` is not empty,
1. Filter proxy's `svc` and `region` in `src_svc` and `src_cid` in `percentage_df`
2. Put them into `csv_string` which is 
3. Return csv_string to proxy

Example `csv_string` for `metrics-fake-ingress-us-west-1` wasm
(The columns means `src_endpoint`, `src_region`, `dst_region`, `routing weight`)
```txt
metrics-fake-ingress-us-west-1@GET@/start, us-west-1, us-west-1, 0.6
metrics-fake-ingress-us-west-1@GET@/start, us-west-1, us-east-1, 0.4
metrics-fake-ingress-us-west-1@POST@/start, us-west-1, us-west-1, 0.9
metrics-fake-ingress-us-west-1@POST@/start, us-west-1, us-east-1, 0.1
```

## `write_trace_str_to_file` (profile mode only)
write `trace_str_list` into `trace_string.csv` file


## `training_phase` (runtime mode only)
This function will be effectively executed only once.
If it has not trained,
1. Read trace_string.csv file
2. Convert it into `traces` data structure (all_traces[cid][tid]: list of spans)
3. Filter complete traces only based on the length of each traces (e.g., metrics-app needs 3 spans in one trace,)
   - **NOTE**: Error-prone code. different request could have different lengths of spans in one trace
4. Time stitch traces
5. Parse traces object to get data structure
6. Init `endpoint_level_rps`, `endpoint_level_inflight` to 0
7. Fit linear regression model
Example coef_dict output
```

```

## `optimizer_entrypoint` (runtime mode only)
Run `run_optimizer`
Set `percentage_df`

Format of `percentage_df`
```csv
index_col,src_svc,dst_svc,src_endpoint,dst_endpoint,src_cid,dst_cid,flow,total,weight
"('metrics-handler@GET@/detectAnomalies', 'us-west-1', 'metrics-processing@POST@/detectAnomalies')",metrics-handler,metrics-processing,metrics-handler@GET@/detectAnomalies,metrics-processing@POST@/detectAnomalies,us-west-1,us-west-1,35,49,0.7142857142857143
"('metrics-handler@GET@/detectAnomalies', 'us-west-1', 'metrics-processing@POST@/detectAnomalies')",metrics-handler,metrics-processing,metrics-handler@GET@/detectAnomalies,metrics-processing@POST@/detectAnomalies,us-west-1,us-east-1,14,49,0.2857142857142857
"('metrics-fake-ingress@GET@/start', 'us-west-1', 'metrics-handler@GET@/detectAnomalies')",metrics-fake-ingress,metrics-handler,metrics-fake-ingress@GET@/start,metrics-handler@GET@/detectAnomalies,us-west-1,us-west-1,48,48,1.0
"('SOURCE', 'XXXX', 'metrics-fake-ingress@GET@/start')",SOURCE,metrics-fake-ingress,SOURCE,metrics-fake-ingress@GET@/start,XXXX,us-west-1,48,48,1.0
```

### Notes
`endpoint_level_rps[region][svc]` and `endpoint_level_inflight[region][svc]` is initialized both in `handleProxyLoad` and in `training_phase`.

---

## From trace_string.csv to stitched_traces

1. trace_string.csv 
   - -> each line will be parsed into one span object (it does not have valid exclusive time)
   - **process**: convert each line to span and put them in a flat list which is list_of_span
2. list_of_span
   - **process**: convert them into trace object which is the nested dictionary
3. complete_traces
   - It looks like
      ```python
      complete_traces[cluster_id][trace_id] = list of span objects from the same trace id
      ```
   - Note that still the spans in complete_traces do not have exclusive time
   - **process**: stitch_time
4. stitched_traces
   - stitched_traces is the same data structure as complete_traces but now it has exclusive time
   - It is ready to be used to train the linear regression model

## Data structures

```python
cg_key of A,GET,/ = "A.GET./read.B.GET./read"
cg_key = "A.POST./write.C.POST./write"
bfs_callgraph and append svc_name, method, url

ep_str_callgraph_table[cg_key][parent_ep_str] = list of child_ep_str

request_in_out_weight[cg_key][parent_ep_str][child_ep_str] = in_/out_ ratio (in_: parent_ep_str, out_: child_ep_str)

latency_func[svc_name][endpoint] = fitted regression model

endpoint_level_inflight_req[cid][svc_name][ep] = num inflight requests

endpoint_level_rps[cid][svc_name][ep] = rps

root_node_max_rps[root_node_endpoint] = rps

all_endpoints[cid][svc_name] = endpoint

placement[cid] = svc_name

svc_to_placement[svc_name] = set of cids

endpoint_to_placement[ep] = set of cids

coef_dict
coef_dict[A][A.GET./read]: {'A.GET./read': 1, 'A.POST./write': 1, 'intercept': 0}
coef_dict[A][A.POST./write]: {'A.GET./read': 1, 'A.POST./write': 1, 'intercept': 0}
coef_dict[B][B.GET./read]: {'B.GET./read': 1, 'intercept': 0}
coef_dict[C][C.POST./write]: {'C.POST./write': 1, 'intercept': 0}
```

---

# Span
```
cluster_id,svc_name,method,url,trace_id,span_id,parent_span_id,st,et,rt,xt,ct,call_size,{endpoint_1}:{num_inflight_dict[endpoint_1]}|{endpoint_2}:{self.num_inflight_dict[endpoint_2]}|,{endpoint_1}:{rps_dict[endpoint_1]}|{endpoint_2}:{self.rps_dict[endpoint_2]}|
```

`endpoint`: `svc_name@method@url`

Example
```
us-west-1,metrics-processing,POST,/detectAnomalies,b3f278df40ad38529eaa609a92206c8c,1088b92dc567deb9,c2c3dbe904d256f3,1706486731895,1706486731896,1,0,0,50,metrics-processing@POST@/detectAnomalies:3|,metrics-processing@POST@/detectAnomalies:2|
```

---

# Callgraph

### What we need is 
- number of requests per callgraph
- defining callgraph_key
- mapping callgraph_key -> callgraph
- call graph is not same as trace. Hence, we need trace-to-callgraph function.


### What is callgraph?
Callgraph is a combination of service topology of request classes executed in each service
Example

```python
# Topology
A: [B, C]
B: [D]
C: []
D: []
```

```python
# Callgraph
{A-endpoint_1:[B-endpoint_3, C-endpoint_2], \
 B-endpoint_3:[D-endpoint_6], \
 C-endpoint_2:[], \
 D-endpoint_6:[]}
```

```python
# Callgraph
{A-req_class_1:[B-req_class_3, C-req_class_2], \
 B-req_class_3:[D-req_class_6], \
 C-req_class_2:[], \
 D-req_class_6:[]}
```


- If service topology and method and url of all services of two different traces(request) are the same, then they are considered to have the same category.
service topology
      
method and url of services
  - { A: {method: "GET", url: "/product/123"}, B: {method: "GET", url: "/reviews"}, C: {method: "POST", url: "/details/456"}, D: {method: "GET", url: "/ratings"} }

### Change traces data structure in the global controller
Current traces data structure:
    traces[cluster_id][trace_id][service_name] = span

==>

**New traces data structure:**
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