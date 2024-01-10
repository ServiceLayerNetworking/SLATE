# Global controller

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

## Other data structure for optimizer
```python
cg_key of A,GET,/ = "A.GET./read.B.GET./read"
cg_key = "A.POST./write.C.POST./write"
bfs_callgraph and append svc_name, method, url

ep_str_callgraph_table[cg_key][parent_ep_str] = list of child_ep_str

sp_callgraph_table[cg_key][parent_span] = list of child_span

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