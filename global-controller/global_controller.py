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

traces = {}
svc_to_rps = {}

stats_mutex = Lock()
stats_arr = []
# in form of [cluster_id][dest cluster] = pct
# to be applied by cluster controller
cluster_pcts = {}



class Span:
    def __init__(self, svc, cluster_id, trace_id, span_id, parent_span_id, start, end, cur_load, call_size):
        self.svc = svc
        self.span_id = span_id
        self.trace_id = trace_id
        self.start = start
        self.end = end
        self.parent_span_id = parent_span_id
        self.cur_load = cur_load
        self.call_size = call_size
        self.cluster_id = cluster_id

    def __str__(self):
        return f"{self.svc} ({self.span_id}) took {self.end - self.start} ms, parent {self.parent_span_id}"

"""
parse_stats_into_spans will parse the stats string into a list of spans.
stats is in the format of:
<Num requests>
<Trace Id> <Span Id> <Parent Span Id> <Start Time> <End Time> <Call Size>

Root svc will have no parent span id
If the span doesn't make sense, just ignore it.
"""
def parse_stats_into_spans(stats, cluster_id, service):
    spans = []
    lines = stats.split("\n")
    num_req = int(lines[0])
    for i in range(1, len(lines)):
        line = lines[i]
        ss = line.split(" ")
        if len(ss) < 6:
            continue
        trace_id = ss[0]
        span_id = ss[1]
        # can be empty
        parent_span_id = ss[2]
        start = int(ss[3])
        end = int(ss[4])
        call_size = int(ss[5])
        spans.append(Span(service, cluster_id, trace_id, span_id, parent_span_id, start, end, num_req, call_size))
    return spans


# Runs every few seconds
def optimizer_entrypoint():
    with stats_mutex:
        for k, v in traces.items():
            for trace_id, spans in v.items():
                app.logger.info(f"Trace {trace_id} has {len(spans)} spans:")
                for svc, span in spans.items():
                    app.logger.info(f"\t{span}")
        # todo this should be ingressgateway. hardcoding for now
        cluster_1_num_req = svc_to_rps["us-west"]["productpage-v1"]
        cluster_2_num_req = svc_to_rps["us-east"]["productpage-v1"]
        reqs = {"us-west": cluster_1_num_req, "us-east": cluster_2_num_req}
        num_requests = [cluster_1_num_req, cluster_2_num_req]
        # assert len(num_requests) == len(traces)
        percentage_df = opt.run_optimizer(traces, num_requests)
        igw_rows = percentage_df.iloc[percentage_df['src'] == "ingress_gw"]
        total_reqs = 0
        for idx, row in igw_rows.iterrows():
            total_reqs += int(row['flow'])
            src_cluster = row['src_cid']
            dst_cluster = row['dst_cid']
            if src_cluster not in cluster_pcts:
                cluster_pcts[src_cluster] = {}
            if src_cluster != dst_cluster:
                # flow to another cluster
                pct = int(row['flow']) / reqs[src_cluster]
                cluster_pcts[src_cluster][dst_cluster] = pct
        app.logger.info(cluster_pcts)
        traces.clear()

# TODO
def retrain_service_models():
    pass

@app.route("/clusterLoad", methods=["POST"])
def proxy_load():
    body = request.get_json(force=True)
    cluster = body["clusterId"]
    pod = body["podName"]
    svc = body["serviceName"]
    stats = body["body"]
    # if svc == "productpage-v1":
    #     num_req = stats.split("\n")[0]
    #     sum = 0
    #     num_p = 0
    #     for s in stats.split("\n")[1:]:
    #
    #         ss = s.split(" ")
    #         if len(ss) >= 3:
    #             start = int(ss[-3])
    #             end = int(ss[-2])
    #             sum += (end - start)
    #             num_p += 1
    #
    #     if num_p > 0:
    #         app.logger.info(f"{num_req} requests, avg latency {sum/num_p} ms")
    if cluster not in svc_to_rps:
        svc_to_rps[cluster] = {}
    svc_to_rps[cluster][svc] = int(stats.split("\n")[0])
    spans = parse_stats_into_spans(stats, cluster, svc)
    with stats_mutex:
        for span in spans:
            if span.cluster_id not in traces:
                traces[span.cluster_id] = {}
            if span.trace_id not in traces[span.cluster_id]:
                traces[span.cluster_id][span.trace_id] = {}
            traces[span.cluster_id][span.trace_id][span.svc] = span

    stats_arr.append(f"{cluster} {pod} {svc} {stats}\n")

    # print(f"Received proxy load for {cluster} {pod} {svc}\n{stats}")
    return cluster_pcts[cluster]


if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=optimizer_entrypoint, trigger="interval", seconds=3)
    scheduler.add_job(func=retrain_service_models, trigger="interval", seconds=10)
    scheduler.start()

    atexit.register(lambda: scheduler.shutdown())

    app.run(host='0.0.0.0', port=8080)
