import config as cfg
import span as sp

def parse_stats_into_spans(body, cluster_id, service):
    '''
    reqCount,2
    inflightStats:GET@/recommendations,4,0|POST@/reservation,2,0|GET@/hotels,2,0|

    requestStats,
    us-west-1 frontend-us-west-1 GET /recommendations 9c3974644c103e1604faad5a17aff4f5 04faad5a17aff4f5  1704869734566 1704869734572 0 GET@/hotels,0,1|POST@/reservation,2,0|GET@/recommendations,2,1|
    '''
    spans = []
    lines = body.split("\n")
    service_level_rps = int(lines[0])
    inflightStats = lines[1]
    requestStats = lines[4:]
    print('='*30)
    print(f'service_level_rps: {service_level_rps}')
    print()
    print('='*30)
    print(f'inflightStats: {inflightStats}')
    print()
    print('='*30)
    print(f'requestStats: {requestStats}')
    
    # for i in range(len(requestStats)):
    for span_stat in requestStats:
        '''
        ['us-west-1', 'frontend-us-west-1', 'GET', '/recommendations', '9c3974644c103e1604faad5a17aff4f5', '04faad5a17aff4f5', '1704869734566', '1704869734572', '0', 'GET@/hotels,0,1|POST@/reservation,2,0|GET@/recommendations,2,1|']
        '''
        ss = span_stat.split(" ")
        print(f"ss: {ss}")
        print(f"len(ss): {len(ss)}")
        ## NOTE: THIS SHOUD BE UPDATED WHEN member fields in span class is updated.
        # if len(ss) != 12:
        #     print(f"{cfg.log_prefix} parse_stats_into_spans, len(ss) != 12, {len(ss)}")
        #     assert False
        region = ss[0]
        serviceName = ss[1]
        method = ss[2]
        path = ss[3]
        traceId = ss[4]
        spanId = ss[5]
        parentSpanId = ss[6]
        startTime = int(ss[7])
        endTime = int(ss[8])
        bodySize = int(ss[9])
        # 'GET@/hotels,0,1|POST@/reservation,2,0|GET@/recommendations,2,1|'
        endpointInflightStats = ss[10].split("|")
        if endpointInflightStats[-1] == "":
            endpointInflightStats = endpointInflightStats[:-1]
        rps_dict = dict()
        inflight_dict = dict()
        for ep_load in endpointInflightStats:
            method_and_path = ep_load.split(",")[0]
            method = method_and_path.split("@")[0]
            path = method_and_path.split("@")[1]
            endpoint = sp.Endpoint(svc_name=serviceName, method=method, url=path)
            rps = ep_load.split(",")[1]
            inflight = ep_load.split(",")[2]
            rps_dict[str(endpoint)] = rps
            inflight_dict[str(endpoint)] = inflight
        spans.append(sp.Span(method, path, serviceName, region, traceId, spanId, parentSpanId, startTime, endTime, bodySize, rps_dict=rps_dict, num_inflight_dict=inflight_dict))
    if len(spans) > 0:
        print(f"{cfg.log_prefix} ==================================")
        for span in spans:
            print(f"{span}")
        print(f"{cfg.log_prefix} ==================================")
    return spans

region="us-west-1"
svc="frontend"
body = '2\nGET@/recommendations,4,0|POST@/reservation,2,0|GET@/hotels,2,0\n\nrequestStats,\nus-west-1 frontend-us-west-1 GET /recommendations 9c3974644c103e16 04faad5a17aff4f5 04faad5a17aff4f5 1704869734566 1704869734572 0 GET@/hotels,0,1|POST@/reservation,2,0|GET@/recommendations,2,1|\nus-west-1 frontend-us-west-1 POST /reservation 9c3974644c103e16 04faad5a17aff4f5 04faad5a17aff4f5 1704869734566 1704869734572 0 GET@/hotels,0,1|POST@/reservation,2,0|GET@/recommendations,2,1|'
print(body)
parse_stats_into_spans(body, region, svc)