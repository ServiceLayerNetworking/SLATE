from flask import Flask, request
import logging
from threading import Lock
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import optimizer as opt ## NOTE: COMMENT OUT when you run optimizer in standalone
import config as cfg
import span as sp
import time_stitching as tst
import pandas as pd

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
werklog = logging.getLogger('werkzeug')
werklog.setLevel(logging.DEBUG)

"""
<Num requests>
<Method> <URL> <Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time> <bodySize> <firstLoad> <lastLoad> <avgLoad> <rps>
<Method> <URL> <Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time> <bodySize> <firstLoad> <lastLoad> <avgLoad> <rps>
<Method> <URL> <Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time> <bodySize> <firstLoad> <lastLoad> <avgLoad> <rps>
<Method> <URL> <Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time> <bodySize> <firstLoad> <lastLoad> <avgLoad> <rps>
...

NOTE: Root svc will have no parent span id
NOTE: Make sure you turn on the child_span.parent_span_id = parent_span.span_id
"""

complete_traces = {}
all_traces = {}
prerecorded_trace = {}
svc_to_rps = {}
callgraph_aware_load = {}
'''
cluster_to_cid and cid_to_cluster should be deprecated
cluster_id is given as a number. e.g., 0, 1, 2, ...
'''
# cluster_to_cid = {"us-west": 0, "us-east": 1}
# cid_to_cluster = {0: "us-west", 1: "us-east"}
stats_mutex = Lock()
# stats_arr = []
# TODO: It is currently dealing with ingress gateway only.
# cluster_pcts[cluster_id][dest cluster] = pct
cluster_pcts = {} 
prof_start = {0: False, 1: False}
counter = dict()
for cid in range(cfg.NUM_CLUSTER):
    counter[cid] = 0 # = {0:0, 1:0} # {cid:counter, ...}
load_bucket = dict()
'''
- num_bucket: 10
- bucket_size: 5
1. calculate key
    key: int(load/bucket_size)
    e.g., 47/5 = 9
          6/5 = 1
          15/5 = 3
          200/5 = 40
2. increment load_bucket by 1 for the key since we observe one more data point.
    load_bucket[0(cid)][9] += 1
3. If all keys in load bucket collect more than MIN_DATA_IN_BUCKET data point, then we consider profiling is done.
'''
num_bucket = 10
bucket_size = 5
MIN_DATA_IN_BUCKET = 5
for cid in range(cfg.NUM_CLUSTER):
    load_bucket[cid] = dict()
    for i in range(num_bucket):
        load_bucket[cid][i] = 0
prof_done = {0:False, 1:False} # {cid: prof_done_flag, ...}

"""
This function will parse the stats string into a list of spans.
"""
def parse_stats_into_spans(stats, cluster_id, service):
    spans = []
    lines = stats.split("\n")
    for i in range(1, len(lines)):
        line = lines[i]
        ss = line.split(" ")
        ## NOTE: THIS SHOUD BE UPDATED WHEN member fields in span class is updated.
        if len(ss) != 12:
            app.logger.info(f"{cfg.log_prefix} parse_stats_into_spans, len(ss) != 12, {len(ss)}")
            assert False
            continue
        method = ss[0]
        url_path = ss[1]
        trace_id = ss[2]
        my_span_id = ss[3]
        parent_span_id = ss[4]
        start = int(ss[5])
        end = int(ss[6])
        call_size = int(ss[7])
        first_load = int(ss[8])
        last_load = int(ss[9])
        avg_load = int(ss[10])
        rps = int(ss[11])
        spans.append(sp.Span(method, url, service, cluster_id, trace_id, my_span_id, parent_span_id, start, end, first_load, last_load, avg_load, rps, call_size))
    if len(spans) > 0:
        app.logger.info(f"{cfg.log_prefix} ==================================")
        for span in spans:
            app.logger.info(f"{cfg.log_prefix} parse_stats_into_spans: {span}")
        app.logger.info(f"{cfg.log_prefix} ==================================")
    return spans


def print_routing_rule(pct_df):
    app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: ********************")
    app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: ** Routing rule")
    app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: ** west->west: {int(float(pct_df[0][0])*100)}%")
    app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: ** west->east: {int(float(pct_df[0][1])*100)}%")
    app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: ** east->east: {int(float(pct_df[1][1])*100)}%")
    app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: ** east->west: {int(float(pct_df[1][0])*100)}%")
    app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: ********************")


def print_load_bucket():
    app.logger.info(f"{cfg.log_prefix} print_load_bucket")
    for cid in load_bucket:
        app.logger.info(f"{cfg.log_prefix} =======================================================")
        for bucket, num_observ in load_bucket[cid].items():
            app.logger.info(f"{cfg.log_prefix} cluster,{cid}, bucket,{bucket}, num_observ,{num_observ}")
        app.logger.info(f"{cfg.log_prefix} =======================================================")
        


def is_load_bucket_filled(cid):
    for i in range(num_bucket):
        if load_bucket[cid][i] < MIN_DATA_IN_BUCKET:
            app.logger.info(f"{cfg.log_prefix} Not filled, cluster,{cid}, bucket:{i}, num:{load_bucket[cid][i]}, min_len:{MIN_DATA_IN_BUCKET}")
            app.logger.info(f"{cfg.log_prefix} is_load_bucket_filled, RETURNS FALSE, Cluster {cid}")
            return False
        else:
            app.logger.info(f"{cfg.log_prefix} cluster,{cid}, bucket:{i} is filled, num,{load_bucket[cid][i]}, min_len,{MIN_DATA_IN_BUCKET}")
    app.logger.info(f"{cfg.log_prefix} is_load_bucket_filled, All buckets are filled. Cluster {cid}, RETURN TRUE")
    return True


# This function can be async
def check_and_move_to_complete_trace():
    for cid in all_traces:
        for tid in all_traces[cid]:
            single_trace = all_traces[cid][tid]
            if is_this_trace_complete(single_trace) == True:
                ########################################################
                ## Weird behavior: In some traces, all spans have the same span id which is productpage's span id.
                ## For now, to filter out them following code exists.
                ## If the traces were good, it is redundant code.
                span_exists = []
                ignore_cur = False
                for span in single_trace:
                    if span.my_span_id in span_exists:
                        ignore_cur = True
                        break
                    span_exists.append(span.my_span_id)
                    if ignore_cur:
                        app.logger.debug(f"{cfg.log_prefix} span exist, ignore_cur, cid,{span.cluster_id}, tid,{span.trace_id}, span_id,{span.my_span_id}")
                        continue
                    if span.cluster_id not in complete_traces:
                        complete_traces[span.cluster_id] = {}
                    if span.trace_id not in complete_traces[span.cluster_id]:
                        complete_traces[span.cluster_id][span.trace_id] = {}
                    complete_traces[span.cluster_id][span.trace_id] = all_traces[span.cluster_id][span.trace_id].copy()


## Deprecated
# def prof_phase():
#     with stats_mutex:
#         for cid in range(cfg.NUM_CLUSTER):
#             if prof_start[cid]:
#                 prof_percentage = int((counter[cid]/PROF_DURATION)*100)
#                 if prof_percentage > 100:
#                     prof_percentage = 100
#                 else:
#                     #app.logger.info(f"{cfg.log_prefix} OPTIMIZER, Cluster {cid}, Profiling phase: {prof_percentage}%")
#                     app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: Cluster {cid}, Profiling: {prof_percentage}%")
#                 if cid in complete_traces:
#                     app.logger.info(f"{cfg.log_prefix} prof_phase, Cluster {cid}, NUM_COMPLETE_TRACE: {len(complete_traces[cid])}")
#                 else:
#                     app.logger.info(f"{cfg.log_prefix} prof_phase, Cluster {cid}, NUM_COMPLETE_TRACE: 0")
#                 if cid in all_traces:
#                     app.logger.info(f"{cfg.log_prefix} prof_phase, Cluster {cid}, NUM_ALL_TRACE: {len(all_traces[cid])}")
#                 else:
#                     app.logger.info(f"{cfg.log_prefix} prof_phase, Cluster {cid}, NUM_ALL_TRACE: 0")
#                 ## TODO:
#                 if (counter[cid] >= PROF_DURATION) and (cid in complete_traces):
#                     prof_done[cid] = True ## Toggle profiling done flag!
#                     # print_load_bucket()
#                     # if is_load_bucket_filled(cid):
#                     app.logger.debug(f"{cfg.log_prefix} prof_phase, Cluster {cid} Profiling already DONE")
#                 counter[cid] += 1
                
                
def print_trace():
    with stats_mutex:
        if cid in all_traces:
            app.logger.info(f"{cfg.log_prefix} ================ CLUSTER {cid} PRINT ALL TRACE START ==================")
            app.logger.info(f"{cfg.log_prefix} len(all_traces[{cid}]), {len(all_traces[cid])}")
            for tid, single_trace in all_traces[cid].items():
                for span in single_trace:
                    app.logger.info(f"{cfg.log_prefix} {span}")
            app.logger.info(f"{cfg.log_prefix} ================ CLUSTER {cid} PRINT ALL TRACE DONE ==================")
        
        if cid in complete_traces:
            app.logger.info(f"{cfg.log_prefix} ================ CLUSTER {cid} PRINT COMPLETE TRACE START ==================")
            app.logger.info(f"{cfg.log_prefix} len(complete_traces[{cid}]), {len(complete_traces[cid])}")
            for tid, single_trace in complete_traces[cid].items():
                for span in single_trace:
                    app.logger.info(f"{cfg.log_prefix} {span}")
            app.logger.info(f"{cfg.log_prefix} ================ CLUSTER {cid} PRINT COMPLETE TRACE DONE ==================")


def garbage_collection():
    app.logger.info(f"{cfg.log_prefix} Start Garbage collection")
    app.logger.info(f"{cfg.log_prefix} Clearing complete_traces, all_traces...")
    all_traces.clear()
    # complete_traces.clear()
    # stats_arr.clear()
    app.logger.info(f"{cfg.log_prefix} Done with Garbage collection")


'''
local routing example
cluster_pcts[0] = {0: "1.0", 1: "0.0"}
cluster_pcts[1] = {0: "0.0", 1: "1.0"}
'''
def local_routing_rule():
    cluster_pcts_ = dict()
    for cid in range(cfg.NUM_CLUSTER):
        cluster_pcts_[cid] = {}
        for dst_cid in range(cfg.NUM_CLUSTER):
            if dst_cid == cid:
                cluster_pcts_[cid][dst_cid] = "1.0"
            else:
                cluster_pcts_[cid][dst_cid] = "0.0"
    return cluster_pcts_


def is_prof_done():
    for cid in prof_done:
        if prof_done[cid] == False:
            return False
    return True


def optimizer_entrypoint():
    # with stats_mutex:
    app.logger.info(f"\n\n{cfg.log_prefix} optimizer_entrypoint function is called.")
    if is_prof_done() == False:
        print_routing_rule(cluster_pcts)
        return cluster_pcts
    else:
        app.logger.info(f"\n\n{cfg.log_prefix} Run Optimizer, number of complete traces")
        for cid in range(cfg.NUM_CLUSTER):
            app.logger.info(f"cluster {cid}: {len(complete_traces[cid])}")
        cluster_0_num_req = svc_to_rps["us-west"][INGRESS_GW]
        cluster_1_num_req = svc_to_rps["us-east"][INGRESS_GW]
        num_requests = [cluster_0_num_req, cluster_1_num_req]
        app.logger.info(f"\n{cfg.log_prefix} OPTIMIZER: NUM_REQUESTS: us-west:{num_requests[0]}, us-east:{num_requests[1]}")
        if cluster_0_num_req == 0 and cluster_1_num_req == 0:
            app.logger.info(f"{cfg.log_prefix} NO LOAD. Rollback to local routing and Skip Optimizer")
            cluster_pcts = local_routing_rule()
        else:
            for i in range(len(num_requests)):
                if num_requests[i] < 0:
                    app.logger.warning(f"{cfg.log_prefix} cluster,{i}, num_request < 0, ({num_requests[i]}), reset to zero.")
                    num_requests[i] = 0
            app.logger.info(f"{cfg.log_prefix} MODE: {cfg.MODE}")
            if cfg.MODE == "LOCAL_ROUTING":
                cluster_pcts = local_routing_rule()
            elif cfg.MODE == "PROFILE":
                traces, df = tst.stitch_time(complete_traces)
                df.to_csv(f"{cfg.OUTPUT_DIR}/traces.csv")
                list_of_callgraph, callgraph_table = tst.traces_to_callgraph(complete_traces)
                tst.file_write_callgraph_table(callgraph_table)
                tst.print_callgraph_table(callgraph_table)
            elif cfg.MODE == "SLATE":
                app.logger.info(f"{cfg.log_prefix} SLATE_ON")
                ## NOTE: It should be executed only once
                placement = tst.get_placement(complete_traces)
                list_of_callgraph, callgraph_table = tst.traces_to_callgraph(complete_traces)
                pre_recorded_trace = sp.file_to_trace("/app/sampled_both_trace.txt")
                percentage_df, desc = opt.run_optimizer(pre_recorded_trace, callgraph_aware_load, placement, callgraph_table)
                if percentage_df == None: # If optimizer failed, use local routing or stick to the previous routing rule.
                    cluster_pcts = local_routing_rule()
                    app.logger.info(f"{cfg.log_prefix} OPTIMIZER, FAIL, {desc}")
                    app.logger.info(f"{cfg.log_prefix} OPTIMIZER, ROLLBACK TO LOCAL ROUTING: {cluster_pcts}")
                else:
                    ## NOTE: Translated optimizer output into callgraph-aware routing rules.
                    ingress_gw_df = percentage_df[percentage_df['src']=='ingress_gw']
                    for src_cid in range(cfg.NUM_CLUSTER):
                        for dst_cid in range(cfg.NUM_CLUSTER):
                            row = ingress_gw_df[(ingress_gw_df['src_cid']==src_cid) & (ingress_gw_df['dst_cid']==dst_cid)]
                            if len(row) == 1:
                                cluster_pcts[src_cid][dst_cid] = str(round(row['weight'].tolist()[0], 2))
                            elif len(row) == 0:
                                # empty means no routing from this src to this dst
                                cluster_pcts[src_cid][dst_cid] = str(0)
                            else:
                                # It should not happen
                                app.logger.info(f"{cfg.log_prefix} [ERROR] length of row can't be greater than 1.")
                                app.logger.info(f"{cfg.log_prefix} row: {row}")
                                assert len(row) <= 1
                    ################################################################
        print_routing_rule(cluster_pcts)
        return cluster_pcts


def span_existed(traces_, span_):
    if (span_.cluster_id in traces_) and (span_.trace_id in traces_[span_.cluster_id]):
            for span in traces_[span_.cluster_id][span_.trace_id]:
                if sp.are_they_same_service_spans(span_, span):
                    app.logger.info(f"{cfg.log_prefix} span already exists in all_trace {span.trace_id[:8]}, {span.my_span_id}, {span.svc_name}")
                    return True
    return False


def add_span_to_traces(traces_, span_):
    if span_.cluster_id not in traces_:
        traces_[span_.cluster_id] = {}
    if span_.trace_id not in traces_[span_.cluster_id]:
        traces_[span_.cluster_id][span_.trace_id] = {}
    traces_[span_.cluster_id][span_.trace_id].append(span_)
    return traces_[span_.cluster_id][span_.trace_id]


def is_this_trace_complete(single_trace):
    # TODO: Must be changed for other applications.
    if len(single_trace) == 4: 
        return True
    return False

        
@app.route("/clusterLoad", methods=["POST"])
def proxy_load():
    body = request.get_json(force=True)
    cluster_id = body["clusterId"]
    pod = body["podName"]
    svc_name = body["serviceName"]
    stats = body["body"]
    if cluster_id not in svc_to_rps:
        svc_to_rps[cluster_id] = {}
    num_inflight_req = int(stats.split("\n")[0])
    if num_inflight_req > 1000000000:
        app.logger.info(f"{cfg.log_prefix} num_inflight_req,{num_inflight_req}")
        assert False
    svc_to_rps[cluster_id][svc_name] = num_inflight_req
    
    
    # if prof_done[cluster_id] == False:
    spans = parse_stats_into_spans(stats, cluster_id, svc_name)
    
    user_request = f'{spans[0].svc_name},{spans[0].method},{spans[0].url}'
    if cluster_id not in callgraph_aware_load:
        callgraph_aware_load[cluster_id] = dict()
    callgraph_aware_load[cluster_id][user_request] = num_inflight_req
    print(f'callgraph_aware_load[{cluster_id}][{user_request}]: {callgraph_aware_load[cluster_id][user_request]}')
    
    if len(spans) > 0 and spans[0].load > 0:
        if prof_start[cluster_id] == False:
            prof_start[cluster_id] = True
            app.logger.info(f"{cfg.log_prefix} OPTIMIZER,  The FIRST proxy load for cluster  {spans[0].cluster_id} Start profiling for cluster.")
    with stats_mutex:
        for span in spans:
            if span_existed(all_traces, span) == False:
                added_trace = add_span_to_traces(all_traces, span) # NOTE: added_trace could be incomplete trace.
    # stats_arr.append(f"{cluster} {pod} {svc_name} {stats}\n")
    for cid in range(cfg.NUM_CLUSTER):
        if cid not in cluster_pcts:
            cluster_pcts[cid] = {}
    if prof_done[cluster_id] == False:
        cluster_pcts = local_routing_rule()
        
    assert cluster_id in cluster_pcts
    # app.logger.info(f"{cfg.log_prefix} Pushing down routing rules to data planes: {cluster_pcts}")
    return cluster_pcts[cluster_id]
    

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=4)
    # scheduler.add_job(func=prof_phase, trigger="interval", seconds=1)
    scheduler.add_job(func=garbage_collection, trigger="interval", seconds=600)
    # scheduler.add_job(func=print_trace, trigger="interval", seconds=10) ## uncomment it if you want trace log print
    scheduler.add_job(func=check_and_move_to_complete_trace, trigger="interval", seconds=10) ## uncomment it if you want trace log print
    # scheduler.add_job(func=retrain_service_models, trigger="interval", seconds=10)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    app.run(host='0.0.0.0', port=8080)
