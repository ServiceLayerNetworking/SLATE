def file_to_trace(TRACE_PATH):
    df = pd.read_csv(TRACE_PATH)
    traces = dict()
    for index, row in df.iterrows():
        if row["cluster_id"] not in traces:
            traces[row["cluster_id"]] = dict()
        if row["trace_id"] not in traces[row["cluster_id"]]:
            traces[row["cluster_id"]][row["trace_id"]] = dict()
        span = Span(row["method"], row["url"], row["svc_name"], row["cluster_id"], row["trace_id"], row["my_span_id"], row["parent_span_id"], row["st"], row["et"], row["load"], row["last_load"], row["avg_load"], row["rps"], row["call_size"], ct=row["ct"])
        traces[row["cluster_id"]][row["trace_id"]].append(span)
    return traces

def parse_num_cluster(trace_file):
    df = pd.read_csv(trace_file)
    return len(df["cluster_id"].unique())


def are_they_same_endpoint(span1, span2):
    if span1.svc_name == span2.svc_name and span1.method == span2.method and span1.method == span2.method:
        return True
    return False


def are_they_same_service_spans(span1, span2):
    if span1.svc_name == span2.svc_name:
        return True
    return False


class Span:
    def __init__(self, method, url, svc_name, cluster_id, trace_id, my_span_id, parent_span_id, st, et, first_load, last_load, avg_load, rps, cs, ct=0):
        self.method = method
        self.url = url
        self.svc_name = svc_name
        self.endpoint = f"{self.svc_name},{self.method},{self.url}"
        self.my_span_id = my_span_id
        self.parent_span_id = parent_span_id
        self.trace_id = trace_id
        self.cluster_id = cluster_id
        self.load = first_load
        self.last_load = last_load
        self.avg_load = avg_load
        self.rps = rps
        self.st = st
        self.et = et
        try:
            self.rt = et - st
        except Exception as error:
            print(f"et: {et}")
            print(f"st: {st}")
            print(error)
            exit()
        if self.rt < 0:
            print(f"class Span, negative response time, {self.rt}")
            assert False
        self.xt = 0 # exclusive time
        self.ct = ct # critical time
        # self.cpt = list() # critical path time
        self.child_spans = list()
        self.critical_child_spans = list()
        self.call_size = cs
        self.depth = 0 # ingress gw's depth: 0, frontend's depth: 1
        
    
    def unfold(self):
        unfold_dict = {k:v for k, v in self.__dict__.items() if not (k.startswith('__') and k.endswith('__'))}
        return unfold_dict
    
    def __str__(self):
        return f"SPAN,{self.trace_id},{self.method},{self.url},{self.svc_name},{self.cluster_id},{self.my_span_id},{self.parent_span_id},{self.load},{self.last_load},{self.avg_load},{self.rps},{self.st},{self.et},{self.rt},{self.call_size}"