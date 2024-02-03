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