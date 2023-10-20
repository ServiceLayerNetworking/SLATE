from flask import Flask, request
import logging
from threading import Lock
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import optimizer as opt ## NOTE: COMMENT OUT when you run optimizer in standalone
from config import *
import span as sp

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
werklog = logging.getLogger('werkzeug')
werklog.setLevel(logging.ERROR)

"""
2
f85116460cc0c607a484d0521e62fb19 7c30eb0e856124df a484d0521e62fb19 1694378625363 1694378625365
4ef8ed533389d8c9ace91fc1931ca0cd 48fb12993023f618 ace91fc1931ca0cd 1694378625363 1694378625365

<Num requests>
<Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time>

Root svc will have no parent span id
"""

complete_traces = {}
all_traces = {}
prerecorded_trace = {}
svc_to_rps = {}
cluster_to_cid = {"us-west": 0, "us-east": 1}
stats_mutex = Lock()
stats_arr = []
# in form of [cluster_id][dest cluster] = pct
# to be applied by cluster controller
cluster_pcts = {} # TODO: It is currently dealing with ingress gateway only.

prof_start = {0: False, 1: False}
counter = dict()
for cid in range(NUM_CLUSTER):
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
for cid in range(NUM_CLUSTER):
    load_bucket[cid] = dict()
    for i in range(num_bucket):
        load_bucket[cid][i] = 0
prof_done = {0:False, 1:False} # {cid: prof_done_flag, ...}

# TODO: It is currently Hardcoded

'''
Span class in global controlelr is deprecated.
Use Span class in time_stitching.py for compatibility.
'''
# class Span:
#     def __init__(self, svc_name, cluster_id, trace_id, my_span_id, parent_span_id, start, end, load, call_size):
#         self.svc_name = svc_name #
#         self.my_span_id = my_span_id #
#         self.trace_id = trace_id
#         self.start = start #
#         self.end = end #
#         self.parent_span_id = parent_span_id #
#         self.load = load #
#         self.call_size = call_size ####
#         self.cluster_id = cluster_id
#         self.xt = 0
#         self.rt = self.end - self.start

#     def __str__(self):
#         return f"{self.svc_name} ({self.my_span_id}) took {self.end - self.start} ms, parent {self.parent_span_id}"

"""
parse_stats_into_spans will parse the stats string into a list of spans.
stats is in the format of:
<Num requests>
<Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time> <Call Size>

Root svc will have no parent span id
If the span doesn't make sense, just ignore it.
"""
def parse_stats_into_spans(stats, cluster, service):
    spans = []
    lines = stats.split("\n")
    # num_req = int(lines[0]) # (gangmuk): deprecated
    # for l_ in lines:
    #     app.logger.info(f"{log_prefix} parse_stats_into_spans, {l_}")
    # app.logger.info(f"{log_prefix}")
    for i in range(1, len(lines)):
        line = lines[i]
        ss = line.split(" ")
        # app.logger.info(f"{log_prefix} ss: {ss}")
        if len(ss) != 10: ## NOTE: THIS SHOUD BE UPDATED WHEN member fields in span class is updated.
            continue
        trace_id = ss[0]
        my_span_id = ss[1]
        # can be empty
        parent_span_id = ss[2]
        start = int(ss[3])
        end = int(ss[4])
        call_size = int(ss[5])
        first_load = int(ss[6]) # (gangmuk): new
        last_load = int(ss[7]) # (gangmuk): new
        avg_load = int(ss[8]) # (gangmuk): new
        rps = int(ss[9]) # (gangmuk): new
        spans.append(sp.Span(service, cluster_to_cid[cluster], trace_id, my_span_id, parent_span_id, start, end, first_load, last_load, avg_load, rps, call_size))
    # if len(spans) > 0:
    #     app.logger.info(f"{log_prefix} ==================================")
    #     for span in spans:
    #         app.logger.info(f"{log_prefix} parse_stats_into_spans: {span}")
    #     app.logger.info(f"{log_prefix} ==================================")
    return spans


def print_load_bucket():
    app.logger.info(f"{log_prefix} print_load_bucket")
    for cid in load_bucket:
        app.logger.info(f"{log_prefix} =======================================================")
        for bucket, num_observ in load_bucket[cid].items():
            app.logger.info(f"{log_prefix} cluster,{cid}, bucket,{bucket}, num_observ,{num_observ}")
        app.logger.info(f"{log_prefix} =======================================================")
        


def is_load_bucket_filled(cid):
    for i in range(num_bucket):
        if load_bucket[cid][i] < MIN_DATA_IN_BUCKET:
            app.logger.info(f"{log_prefix} Not filled, cluster,{cid}, bucket:{i}, num:{load_bucket[cid][i]}, min_len:{MIN_DATA_IN_BUCKET}")
            app.logger.info(f"{log_prefix} is_load_bucket_filled, RETURNS FALSE, Cluster {cid}")
            return False
        else:
            app.logger.info(f"{log_prefix} cluster,{cid}, bucket:{i} is filled, num,{load_bucket[cid][i]}, min_len,{MIN_DATA_IN_BUCKET}")
    app.logger.info(f"{log_prefix} is_load_bucket_filled, All buckets are filled. Cluster {cid}, RETURN TRUE")
    return True


# def move_to_complete_trace():
#     for cid in all_traces:
#         for tid, single_trace in all_traces[cid].items():
#             if len(single_trace) == 4: # NOTE: hardcoded.
#                 ########################################################
#                 ## Weird behavior: In some traces, all spans have the same span id which is productpage's span id.
#                 ## For now, to filter out them following code exists.
#                 ## If the traces were good, it is redundant code.
#                 span_exists = []
#                 ignore_cur = False
#                 for svc, span in single_trace.items():
#                     if span.my_span_id in span_exists:
#                         ignore_cur = True
#                         break
#                     span_exists.append(span.my_span_id)
#                 if ignore_cur:
#                     app.logger.debug(f"{log_prefix} span exist, ignore_cur, cid,{span.cluster_id}, tid,{span.trace_id}, span_id,{span.my_span_id}")
#                     continue
#                 ########################################################
#                 if span.cluster_id not in complete_traces:
#                     complete_traces[span.cluster_id] = {}
#                 if span.trace_id not in complete_traces[span.cluster_id]:
#                     complete_traces[span.cluster_id][span.trace_id] = {}
#                 complete_traces[span.cluster_id][span.trace_id] = all_traces[span.cluster_id][span.trace_id].copy()
#                 del all_traces[span.cluster_id][span.trace_id]
#                 try:
#                     bucket_key = int(span.load/bucket_size)
#                     if bucket_key not in load_bucket[span.cluster_id]:
#                         app.logger.info(f"{log_prefix} New load bucket key:{bucket_key}, load:{span.load}")
#                         load_bucket[span.cluster_id][bucket_key] = 0
#                     load_bucket[span.cluster_id][bucket_key] += 1
#                 except Exception as e:
#                     app.logger.error(f"{log_prefix} {e}")


def prof_phase():
    with stats_mutex:
        for cid in range(NUM_CLUSTER):
            if prof_start[cid]:
                #####################################################################
                ## This is purely for print. You can comment them out.
                # if cid in all_traces:
                #     app.logger.info(f"{log_prefix} ==================================")
                #     app.logger.info(f"{log_prefix} len(all_traces[{cid}]), {len(all_traces[cid])}")
                #     for tid, single_trace in all_traces[cid].items():
                #         for svc, span in single_trace.items():
                #             app.logger.info(f"{log_prefix} prof_phase/all_traces: {span}")
                #         app.logger.info(f"{log_prefix}")
                #     app.logger.info(f"{log_prefix} ==================================")
                # else:
                #     app.logger.info(f"{log_prefix} len(all_traces[{cid}]), EMPTY!")
                # if cid in complete_traces:
                #     app.logger.info(f"{log_prefix} ==================================")
                #     app.logger.info(f"{log_prefix} len(complete_traces[{cid}]), {len(complete_traces[cid])}")
                #     for tid, single_trace in complete_traces[cid].items():
                #         app.logger.info(f"{log_prefix} prof_phase/complete_traces: tid, {tid[:8]}")
                #         # for svc, span in single_trace.items():
                #         #     app.logger.info(f"{log_prefix} prof_phase/complete_traces: {span}")
                #         # app.logger.info(f"{log_prefix}")
                #     app.logger.info(f"{log_prefix} ==================================")
                # else:
                #     app.logger.info(f"{log_prefix} len(complete_traces[{cid}]), EMPTY!")
                #####################################################################
                prof_percentage = int((counter[cid]/PROF_DURATION)*100)
                if prof_percentage > 100:
                    prof_percentage = 100
                else:
                    app.logger.info(f"{log_prefix} OPTIMIZER, Cluster {cid}, Profiling phase: {prof_percentage}%")
                    # app.logger.info(f"{log_prefix} OPTIMIZER, Cluster {cid}, Profiling phase: {prof_percentage}% (elapsed seconds: {counter[cid]} / required seconds: {PROF_DURATION}")
                if cid in complete_traces:
                    app.logger.info(f"{log_prefix} prof_phase, Cluster {cid}, NUM_COMPLETE_TRACE: {len(complete_traces[cid])}")
                else:
                    app.logger.info(f"{log_prefix} prof_phase, Cluster {cid}, NUM_COMPLETE_TRACE: 0")
                if cid in all_traces:
                    app.logger.info(f"{log_prefix} prof_phase, Cluster {cid}, NUM_ALL_TRACE: {len(all_traces[cid])}")
                else:
                    app.logger.info(f"{log_prefix} prof_phase, Cluster {cid}, NUM_ALL_TRACE: 0")
                ## TODO:
                if (counter[cid] >= PROF_DURATION) and (cid in complete_traces): # and (len(complete_traces[cid]) > MIN_NUM_TRACE):
                    prof_done[cid] = True ## Toggle profiling done flag!
                    # print_load_bucket()
                    # if is_load_bucket_filled(cid):
                    app.logger.debug(f"{log_prefix} prof_phase, Cluster {cid} Profiling already DONE")
                counter[cid] += 1
                
                
def print_trace():
    if PRINT_TRACE:
        for cid in prof_done:
            if prof_done[cid]:
                with stats_mutex:
                    if cid in all_traces:
                        app.logger.info(f"{log_prefix} ================ CLUSTER {cid} PRINT ALL TRACE START ==================")
                        app.logger.info(f"{log_prefix} len(all_traces[{cid}]), {len(all_traces[cid])}")
                        # for tid, single_trace in all_traces[cid].items():
                        #     for svc, span in single_trace.items():
                        #         app.logger.info(f"{log_prefix} {span}")
                        app.logger.info(f"{log_prefix} ================ CLUSTER {cid} PRINT ALL TRACE DONE ==================")
                    
                    if cid in complete_traces:
                        app.logger.info(f"{log_prefix} ================ CLUSTER {cid} PRINT COMPLETE TRACE START ==================")
                        app.logger.info(f"{log_prefix} len(complete_traces[{cid}]), {len(complete_traces[cid])}")
                        for tid, single_trace in complete_traces[cid].items():
                            for svc, span in single_trace.items():
                                app.logger.info(f"{log_prefix} {span}")
                        app.logger.info(f"{log_prefix} ================ CLUSTER {cid} PRINT COMPLETE TRACE DONE ==================")


def garbage_collection():
    app.logger.info(f"{log_prefix} Start Garbage collection")
    app.logger.info(f"{log_prefix} Clearing complete_traces, all_traces, stats_arr...")
    # complete_traces.clear()
    all_traces.clear()
    stats_arr.clear()
    app.logger.info(f"{log_prefix} Done with Garbage collection")


# Runs every few seconds
def optimizer_entrypoint():
    # with stats_mutex:
    # for k, v in all_traces.items():
    #     for trace_id, spans in v.items():
    #         app.logger.info(f"{log_prefix} Trace {trace_id} has {len(spans)} spans:")
    #         for svc_name, span in spans.items():
    #             app.logger.info(f"{log_prefix} \t{span}")
        app.logger.info(f"\n\n{log_prefix} optimizer_entrypoint function is called.")

        ###################################
        # if prof_done[0]:
        if prof_done[0] and prof_done[1]:
        ###################################
            app.logger.info(f"\n\n{log_prefix} Run Optimizer, number of complete traces (cluster 0: {len(complete_traces[0])}, cluster 1: {len(complete_traces[1])})\n")
            
            # TODO: this should be ingressgateway. hardcoding for now
            
            # Next tick load == Current tick load
            app.logger.info(f"{log_prefix} CONFIG: ACTUAL_LOAD")
            cluster_0_num_req = svc_to_rps["us-west"]["productpage-v1"]
            cluster_1_num_req = svc_to_rps["us-east"]["productpage-v1"]
            app.logger.info(f"{log_prefix} LOAD, cluster 0: {cluster_0_num_req}")
            app.logger.info(f"{log_prefix} LOAD, cluster 1: {cluster_0_num_req}")
            num_requests = [cluster_0_num_req, cluster_1_num_req]
            app.logger.info(f"{log_prefix} OPTIMIZER, NUM_REQUESTS: {num_requests}")
            if cluster_0_num_req == 0 and cluster_1_num_req == 0:
                app.logger.info(f"{log_prefix} NO LOAD. Skip Optimizer")
                cluster_pcts[0] = {0: "1.0", 1: "0.0"}
                cluster_pcts[1] = {0: "0.0", 1: "1.0"}
                app.logger.info(f"{log_prefix} OPTIMIZER, OUTPUT: {cluster_pcts}\n")
                return cluster_pcts
            for i in range(len(num_requests)):
                if num_requests[i] < 0:
                    app.logger.warning(f"{log_prefix} cluster,{i}, num_request < 0, ({num_requests[i]}), reset to zero.")
                    num_requests[i] = 0
                    
            ############################################################################
            ## NOTE: copy() function could be expensive if complete_trace is large
            if SLATE_ON:
                app.logger.info(f"{log_prefix} SLATE_ON")
                # if USE_MODEL_DIRECTLY:
                #     percentage_df = opt.run_optimizer(raw_traces=None, trace_file=None, NUM_REQUESTS=num_requests, models=MODEL_DICT)
                if USE_TRACE_FILE:
                    percentage_df, desc = opt.run_optimizer(raw_traces=None, trace_file=TRACE_FILE_PATH, NUM_REQUESTS=num_requests, model_parameter=None)
                elif USE_PRERECORDED_TRACE:
                    percentage_df, desc = opt.run_optimizer(pre_recorded_trace, trace_file=None, NUM_REQUESTS=num_requests, model_parameter=None)
                else:
                    percentage_df, desc = opt.run_optimizer(complete_traces.copy(), trace_file=None, NUM_REQUESTS=num_requests, model_parameter=None)
            else:
                percentage_df, desc = opt.run_optimizer(raw_traces=None, trace_file=None, NUM_REQUESTS=num_requests, model_parameter=None)
                app.logger.info(f"{log_prefix} SLATE_OFF")
                percentage_df = None
            ############################################################################
            
            app.logger.debug(f"{log_prefix} PERCENTAGE RULES: {percentage_df}")
            if percentage_df is None:
                # we don't know what to do to stick to local routing
                app.logger.info(f"{log_prefix} OPTIMIZER, FAIL, {desc}")
                app.logger.info(f"{log_prefix} OPTIMIZER, ROLLBACK TO LOCAL ROUTING: {cluster_pcts}")
                cluster_pcts[0] = {0: "1.0", 1: "0.0"}
                cluster_pcts[1] = {0: "0.0", 1: "1.0"}
                app.logger.info(f"{log_prefix} OPTIMIZER, OUTPUT: {cluster_pcts}\n")
                return cluster_pcts
            
            else:
                ingress_gw_df = percentage_df[percentage_df['src']=='ingress_gw']
                for src_cid in range(NUM_CLUSTER):
                    for dst_cid in range(NUM_CLUSTER):
                        row = ingress_gw_df[(ingress_gw_df['src_cid']==src_cid) & (ingress_gw_df['dst_cid']==dst_cid)]
                        if len(row) == 1:
                            cluster_pcts[src_cid][dst_cid] = str(round(row['weight'].tolist()[0], 2))
                        elif len(row) == 0:
                            # empty means no routing from this src to this dst
                            cluster_pcts[src_cid][dst_cid] = str(0)
                        else:
                            # It should not happen
                            app.logger.info(f"{log_prefix} [ERROR] length of row can't be greater than 1.")
                            app.logger.info(f"{log_prefix} row: {row}")
                            assert len(row) <= 1
            app.logger.info(f"{log_prefix} OPTIMIZER, OUTPUT: {cluster_pcts}\n")
            # all_traces.clear()
            return cluster_pcts
        else:
            # app.logger.info(f"{log_prefix} prof is NOT done yet. still needs to collect more traces...")
            return
        
def span_existed(span_):
    if (span_.cluster_id in all_traces) \
        and (span_.trace_id in all_traces[span_.cluster_id]) \
        and (span_.svc_name in all_traces[span_.cluster_id][span_.trace_id]) \
        and (span_.my_span_id == all_traces[span_.cluster_id][span_.trace_id][span_.svc_name].my_span_id):
            return True
    return False
        
        
# TODO
def retrain_service_models():
    pass


@app.route("/clusterLoad", methods=["POST"])
def proxy_load():
    # cluster_pcts[0] = dict()
    # cluster_pcts[1] = dict()
    # cluster_pcts[0][0] = "1.0"
    # cluster_pcts[0][1] = "0.0"
    # cluster_pcts[1][1] = "1.0"
    # cluster_pcts[1][0] = "0.0"
    # return cluster_pcts
    
    body = request.get_json(force=True)
    cluster = body["clusterId"]
    pod = body["podName"]
    svc_name = body["serviceName"]
    stats = body["body"]
    # app.logger.info(f"{log_prefix} Received stats from {cluster} {pod} {svc_name}")
    if cluster not in svc_to_rps:
        svc_to_rps[cluster] = {}
    num_inflight_req = int(stats.split("\n")[0])
    if num_inflight_req > 1000000000:
        app.logger.info(f"{log_prefix} num_inflight_req,{num_inflight_req}")
        assert False
    svc_to_rps[cluster][svc_name] = num_inflight_req
    
    ## Keep collecting traces
    ################################################
    # if prof_done[cluster_to_cid[cluster]] == False:
    if True:
    ################################################
        spans = parse_stats_into_spans(stats, cluster, svc_name)
        # if len(spans) > 0 and spans[0].load > 0:
        if prof_start[cluster_to_cid[cluster]] == True or (len(spans) > 0 and spans[0].load):
            if prof_start[cluster_to_cid[cluster]] == False:
                prof_start[cluster_to_cid[cluster]] = True
                app.logger.info(f"{log_prefix} The FIRST proxy load for cluster {cluster}, {spans[0].cluster_id}.")
                app.logger.info(f"{log_prefix} OPTIMIZER, Start profiling for cluster {cluster}, {spans[0].cluster_id}.")
            else:
                app.logger.debug(f"{log_prefix} Profiling for Cluster {cluster} already started.")
        else:
            app.logger.debug(f"{log_prefix} cluster {cluster}, {cluster_to_cid[cluster]} still have NOT received any proxy load. Hold off starting profiling.")
        with stats_mutex:
            for span in spans:
                if span.cluster_id not in all_traces:
                    all_traces[span.cluster_id] = {}
                if span.trace_id not in all_traces[span.cluster_id]:
                    all_traces[span.cluster_id][span.trace_id] = {}
                ## Skip spans that were already collected.
                # cid, tid, svc, span
                if span_existed(span):
                    app.logger.info(f"{log_prefix} span already exists in all_trace, skip this span. {span.trace_id[:8]}, {span.my_span_id}, {span.svc_name}")
                    continue    
                all_traces[span.cluster_id][span.trace_id][span.svc_name] = span
                ##############################################################################
                ## (gangmuk): It should be moved to a separate async function later.
                if len(all_traces[span.cluster_id][span.trace_id]) == 4: # NOTE: hardcoded.
                    span_exists = []
                    ignore_cur = False
                    for svc_name, span in all_traces[span.cluster_id][span.trace_id].items():
                        if span.my_span_id in span_exists:
                            ignore_cur = True
                            break
                        span_exists.append(span.my_span_id)
                    if ignore_cur:
                        app.logger.debug(f"{log_prefix} span exist, ignore_cur, {span.svc_name} cid,{cluster_to_cid[cluster]}, tid,{span.trace_id}, span_id,{span.my_span_id}")
                        continue
                    if span.cluster_id not in complete_traces:
                        complete_traces[span.cluster_id] = {}
                    if span.trace_id not in complete_traces[span.cluster_id]:
                        complete_traces[span.cluster_id][span.trace_id] = {}
                    complete_traces[span.cluster_id][span.trace_id] = all_traces[span.cluster_id][span.trace_id].copy()
                    # del all_traces[span.cluster_id][span.trace_id]
                    try:
                        bucket_key = int(span.load/bucket_size)
                        if bucket_key not in load_bucket[span.cluster_id]:
                            app.logger.info(f"{log_prefix} New load bucket cid:{span.cluster_id}, bucket key:{bucket_key}, load:{span.load}")
                            load_bucket[span.cluster_id][bucket_key] = 0
                        load_bucket[span.cluster_id][bucket_key] += 1
                    except Exception as e:
                        app.logger.error(f"{log_prefix} {e}")
                ##############################################################################
                    
        # cid -> trace id -> svc_name -> span
        stats_arr.append(f"{cluster} {pod} {svc_name} {stats}\n")
        # app.logger.info(f"{log_prefix} Profiling was done. No more trace will be collected anymore.")
        for cid in range(2):
            if cid not in cluster_pcts:
                cluster_pcts[cid] = {}
        # Since this is still profiling phase, it does not have enough traces.
        # Set local routing rule
        
    if prof_done[cluster_to_cid[cluster]] == False:
        # Need more traces. Do local routing for now.
        # app.logger.info(f"{log_prefix} Cluster Percentage for {cluster} is NOT computed yet...")
        cluster_pcts[0][0] = "1.0"
        cluster_pcts[0][1] = "0.0"
        cluster_pcts[1][1] = "1.0"
        cluster_pcts[1][0] = "0.0"
        # cluster_pcts[0][0] = "0.5"
        # cluster_pcts[0][1] = "0.5"
        # cluster_pcts[1][1] = "0.5"
        # cluster_pcts[1][0] = "0.5"
    else:
        # Profiling is DONE.
        app.logger.debug(f"{log_prefix} Profiling was already done.")
        
    # if cluster_to_cid[cluster] in cluster_pcts:
    assert cluster_to_cid[cluster] in cluster_pcts
    # app.logger.info(f"{log_prefix} PUSHING DOWN CLUSTER PERCENTAGE RULES TO VS: {cluster_pcts}")
    return cluster_pcts[cluster_to_cid[cluster]]
    

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=4)
    scheduler.add_job(func=prof_phase, trigger="interval", seconds=1)
    scheduler.add_job(func=garbage_collection, trigger="interval", seconds=600)
    scheduler.add_job(func=print_trace, trigger="interval", seconds=10) ## uncomment it if you want trace log print
        
        
    # scheduler.add_job(func=retrain_service_models, trigger="interval", seconds=10)
    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=8080)
