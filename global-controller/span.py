# import pandas as pd
import config as cfg
import logging
logging.config.dictConfig(cfg.LOGGING_CONFIG)

# def pre_recorded_trace_object(TRACE_PATH):
#     df = pd.read_csv(TRACE_PATH)
#     traces = dict()
#     for index, row in df.iterrows():
#         if row["cluster_id"] not in traces:
#             traces[row["cluster_id"]] = dict()
#         if row["trace_id"] not in traces[row["cluster_id"]]:
#             traces[row["cluster_id"]][row["trace_id"]] = dict()
#         span = Span(row["method"], row["url"], row["svc_name"], row["cluster_id"], row["trace_id"], row["span_id"], row["parent_span_id"], row["st"], row["et"], row["num_inflight"], row["rps"], row["call_size"], ct=row["ct"])
#         traces[row["cluster_id"]][row["trace_id"]].append(span)
#     return traces

# def parse_num_cluster(trace_file):
#     df = pd.read_csv(trace_file)
#     return len(df["cluster_id"].unique())

def are_they_same_endpoint(span1, span2):
    if span1.svc_name == span2.svc_name and span1.method == span2.method and span1.method == span2.method:
        return True
    return False


def are_they_same_service_spans(span1, span2):
    if span1.svc_name == span2.svc_name:
        return True
    return False

class Endpoint:
    def __init__(self, svc_name, method, url):
        self.svc_name = svc_name
        self.method = method
        self.url = url
        
    def __eq__(self, other):
        if isinstance(other, Endpoint):
            # Customize the comparison logic based on your requirements
            return (self.svc_name == other.svc_name) and (self.method == other.method) and (self.url == other.url)
        return False
    
    def __hash__(self):
        # Combine hash values of attributes to create a unique hash for the object
        return hash((self.svc_name, self.method, self.url))
    
    def __str__(self):
        return f"{self.svc_name}{cfg.ep_del}{self.method}{cfg.ep_del}{self.url}"


class Span:
    def __init__(self, method="METHOD", url="URL", svc_name="SVC", cluster_id="CID",\
        trace_id="TRACE_ID", span_id="SPAN_ID", parent_span_id="PARENT_SPAN_ID", \
        st=-1, et=-1, xt=0, callsize=-1, \
        rps_dict={}, num_inflight_dict={}, \
        reported_time=0, rps=-100, load_bucket=-1):
        logger = logging.getLogger(__name__)
        self.method = method
        self.url = url
        self.svc_name = svc_name
        self.endpoint = Endpoint(self.svc_name, self.method, self.url)
        self.endpoint_str = str(Endpoint(self.svc_name, self.method, self.url))
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.trace_id = trace_id
        self.cluster_id = cluster_id
        self.rps_dict = rps_dict
        self.num_inflight_dict = num_inflight_dict
        self.st = st
        self.et = et
        self.rt = et - st
        self.xt = xt
        if self.rt < 0:
            logger.error(f"ERROR: class Span, negative response time, {self.rt}")
            logger.error(self.__str__())
            assert False
        if self.xt < 0:
            logger.error(f"ERROR: class Span, negative exclusive time, {self.xt}")
            assert False
        self.xt = 0 # exclusive time
        self.ct = 0 # critical time
        # self.cpt = list() # critical path time
        self.child_spans = list()
        self.critical_child_spans = list()
        self.call_size = callsize
        self.depth = 0 # ingress gw's depth: 0, frontend's depth: 1
        self.time = reported_time
        if rps < 0:
            logger.error(f"rps({rps}) cannot be negative")
            assert False
        self.rps = rps
        self.load_bucket = load_bucket
    
    
    def get_class(self):
        return self.endpoint
    
    def unfold(self):
        unfold_dict = {k:v for k, v in self.__dict__.items() if not (k.startswith('__') and k.endswith('__'))}
        return unfold_dict
    
    # def get_colunm_name(self):
    #     colname = "cluster_id,trace_id,span_id,parent_span_id,svc_name,method,url,st,et,rt,xt,ct,call_size"
    #     for endpoint in self.num_inflight_dict:
    #         colname += f",num_inflight_{endpoint}"
    #     for endpoint in self.rps_dict:
    #         colname += f",rps_{endpoint}"
    #     return colname
    
    def to_dict(self):
        temp = dict()
        temp["cluster_id"] = self.cluster_id
        temp["trace_id"] = self.trace_id
        temp["span_id"] = self.span_id
        temp["parent_span_id"] = self.parent_span_id
        temp["svc_name"] = self.svc_name
        temp["method"] = self.method
        temp["endpoint_str"] = self.endpoint_str
        temp["url"] = self.url
        temp["st"] = self.st
        temp["et"] = self.et
        temp["rt"] = self.rt
        temp["xt"] = self.xt
        temp["ct"] = self.ct
        temp["call_size"] = self.call_size
        temp["inflight_dict"] = self.num_inflight_dict
        temp["rps_dict"] = self.rps_dict
        return temp
        
    def __str__(self):
        temp = f"{self.cluster_id},{self.svc_name},{self.method},{self.url},{self.trace_id},{self.span_id},{self.parent_span_id},{self.st},{self.et},{self.rt},{self.xt},{self.ct},{self.call_size},"
        for endpoint in self.num_inflight_dict:
            temp += f"{endpoint}:{self.num_inflight_dict[endpoint]}|"
        temp += ","
        for endpoint in self.rps_dict:
            temp += f"{endpoint}:{self.rps_dict[endpoint]}|"
        return temp

# This is not Span class function
def get_columns(self):
    return "cluster_id,svc_name,method,url,trace_id,span_id,parent_span_id,st,et,rt,xt,ct,call_size,inflight_dict,rps_dict"