class Span:
    def __init__(self, svc_name, cluster_id, trace_id, my_span_id, parent_span_id, st, et, load, cs):
        self.svc_name = svc_name
        self.my_span_id = my_span_id
        self.parent_span_id = parent_span_id
        self.trace_id = trace_id
        self.cluster_id = cluster_id
        self.load = load
        self.st = st
        self.et = et
        self.rt = et - st
        if self.rt < 0:
            print(f"class Span, negative response time, {self.rt}")
            assert False
        self.xt = 0
        self.cpt = list() # critical path time
        self.child_spans = list()
        self.critical_child_spans = list()
        self.critical_time = 0
        self.call_size = cs
        self.depth = 0 # ingress gw's depth: 0, frontend's depth: 1
    
    def __str__(self):
        return f"SPAN,{self.trace_id},{self.svc_name},{self.cluster_id},{self.my_span_id},{self.parent_span_id},{self.load},{self.st},{self.et},{self.rt},{self.call_size}"
    
    # def __str__(self):
    #     return f"SPAN tid,{self.trace_id[:8]}, {self.svc_name}, cid,{self.cluster_id}, span,{self.my_span_id}, parent_span,{self.parent_span_id}, load,{self.load}"
        
