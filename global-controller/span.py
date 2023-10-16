class Span:
    def __init__(self, svc_name, cluster_id, trace_id, my_span_id, parent_span_id, st, et, first_load, last_load, avg_load, rps, cs):
        self.svc_name = svc_name
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
            # print(et)
            # print(st)
            # print(type(et))
            # print(type(st))
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
        self.ct = 0 # critical time
        # self.cpt = list() # critical path time
        self.child_spans = list()
        self.critical_child_spans = list()
        self.call_size = cs
        self.depth = 0 # ingress gw's depth: 0, frontend's depth: 1
    
    def unfold(self):
        unfold_dict = {k:v for k, v in self.__dict__.items() if not (k.startswith('__') and k.endswith('__'))}
        return unfold_dict
    
    def __str__(self):
        return f"SPAN,{self.trace_id},{self.svc_name},{self.cluster_id},{self.my_span_id},{self.parent_span_id},{self.load},{self.last_load},{self.avg_load},{self.st},{self.et},{self.rt},{self.call_size}"
    
    # def __str__(self):
    #     return f"SPAN tid,{self.trace_id[:8]}, {self.svc_name}, cid,{self.cluster_id}, span,{self.my_span_id}, parent_span,{self.parent_span_id}, load,{self.load}"
