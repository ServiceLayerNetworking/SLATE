from flask import Flask, request
import logging
from threading import Lock
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import optimizer as opt

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

"""
2
f85116460cc0c607a484d0521e62fb19 7c30eb0e856124df a484d0521e62fb19 1694378625363 1694378625365
4ef8ed533389d8c9ace91fc1931ca0cd 48fb12993023f618 ace91fc1931ca0cd 1694378625363 1694378625365

<Num requests>
<Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time>

Root svc will have no parent span id
"""

complete_traces = {}
traces = {}
svc_to_rps = {}
cluster_to_cid = {"us-west": 0, "us-east": 1}
stats_mutex = Lock()
stats_arr = []
# in form of [cluster_id][dest cluster] = pct
# to be applied by cluster controller
cluster_pcts = {}



class Span:
    def __init__(self, svc_name, cluster_id, trace_id, my_span_id, parent_span_id, start, end, load, call_size):
        self.svc_name = svc_name #
        self.my_span_id = my_span_id #
        self.trace_id = trace_id
        self.start = start #
        self.end = end #
        self.parent_span_id = parent_span_id #
        self.load = load #
        self.call_size = call_size ####
        self.cluster_id = cluster_id
        self.xt = 0
        self.rt = self.end - self.start

    def __str__(self):
        return f"{self.svc_name} ({self.my_span_id}) took {self.end - self.start} ms, parent {self.parent_span_id}"

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
    num_req = int(lines[0])
    for i in range(1, len(lines)):
        line = lines[i]
        ss = line.split(" ")
        if len(ss) < 6:
            continue
        trace_id = ss[0]
        my_span_id = ss[1]
        # can be empty
        parent_span_id = ss[2]
        start = int(ss[3])
        end = int(ss[4])
        call_size = int(ss[5])
        spans.append(Span(service, cluster_to_cid[cluster], trace_id, my_span_id, parent_span_id, start, end, num_req, call_size))
    return spans


# Runs every few seconds
def optimizer_entrypoint():
    # with stats_mutex:
    # for k, v in traces.items():
    #     for trace_id, spans in v.items():
    #         app.logger.info(f"Trace {trace_id} has {len(spans)} spans:")
    #         for svc_name, span in spans.items():
    #             app.logger.info(f"\t{span}")

        # todo this should be ingressgateway. hardcoding for now
        # cluster_1_num_req = svc_to_rps["us-west"]["productpage-v1"]
        # cluster_2_num_req = svc_to_rps["us-east"]["productpage-v1"]
        cluster_1_num_req = 100
        cluster_2_num_req = 1000
        reqs = {0: cluster_1_num_req, 1: cluster_2_num_req}
        num_requests = [cluster_1_num_req, cluster_2_num_req]
        # assert len(num_requests) == len(traces)
        percentage_df = opt.run_optimizer(complete_traces.copy(), num_requests)
        if percentage_df is None:
            # we don't know what ot do to stick to local routing
            if 0 not in cluster_pcts:
                cluster_pcts[0] = {1: "0.0"}
            if 1 not in cluster_pcts:
                cluster_pcts[1] = {0: "0.0"}
            app.logger.info(f"RESET PERCENTAGE RULES: {cluster_pcts}")
            return
        app.logger.info(f"PERCENTAGE RULES: {percentage_df}")
        igw_rows = percentage_df[percentage_df['src'] == "ingress_gw"]
        total_reqs = 0
        for idx, row in igw_rows.iterrows():
            total_reqs += int(row['flow'])
            src_cluster = int(row['src_cid'])
            dst_cluster = int(row['dst_cid'])
            if src_cluster not in cluster_pcts:
                cluster_pcts[src_cluster] = {}
            if src_cluster != dst_cluster:
                # flow to another cluster
                pct = int(row['flow']) / reqs[src_cluster]
                cluster_pcts[src_cluster][dst_cluster] = str(pct)
        app.logger.info(f"CLUSTER PERCENTAGE RULES: {cluster_pcts}");
        # traces.clear()

# TODO
def retrain_service_models():
    pass

@app.route("/clusterLoad", methods=["POST"])
def proxy_load():
    body = request.get_json(force=True)
    cluster = body["clusterId"]
    pod = body["podName"]
    svc_name = body["serviceName"]
    stats = body["body"]
    app.logger.info(f"Received stats from {cluster} {pod} {svc_name}")
    if cluster not in svc_to_rps:
        svc_to_rps[cluster] = {}
    svc_to_rps[cluster][svc_name] = int(stats.split("\n")[0])
    spans = parse_stats_into_spans(stats, cluster, svc_name)
    with stats_mutex:
        for span in spans:
            if span.cluster_id not in traces:
                traces[span.cluster_id] = {}
            if span.trace_id not in traces[span.cluster_id]:
                traces[span.cluster_id][span.trace_id] = {}
            traces[span.cluster_id][span.trace_id][span.svc_name] = span
            if len(traces[span.cluster_id][span.trace_id]) == 4:
                span_exists = []
                ignore_cur = False
                for svc_name, span in traces[span.cluster_id][span.trace_id].items():
                    if span.my_span_id in span_exists:
                        ignore_cur = True
                        break
                    span_exists.append(span.my_span_id)
                if ignore_cur:
                    continue
                if span.cluster_id not in complete_traces:
                    complete_traces[span.cluster_id] = {}
                if span.trace_id not in complete_traces[span.cluster_id]:
                    complete_traces[span.cluster_id][span.trace_id] = {}
                complete_traces[span.cluster_id][span.trace_id] = traces[span.cluster_id][span.trace_id].copy()
# cid -> trace id -> svc_name -> span
    stats_arr.append(f"{cluster} {pod} {svc_name} {stats}\n")

    # print(f"Received proxy load for {cluster} {pod} {svc_name}\n{stats}")
    if cluster_to_cid[cluster] in cluster_pcts:
        return cluster_pcts[cluster_to_cid[cluster]]
    return ""


if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=5)
    # scheduler.add_job(func=retrain_service_models, trigger="interval", seconds=10)
    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=8080)
