import pandas as pd
import sys
from random import sample
import logging
from threading import Lock
import config as cfg
import span as sp
import time_stitching as tst
from IPython.display import display
from pprint import pprint
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.preprocessing import StandardScaler
import time
import math
import matplotlib.pyplot as plt
import sys
import numpy as np
import sys
import os
import glob
from scipy.optimize import curve_fit
import warnings
from scipy.optimize import OptimizeWarning
warnings.filterwarnings("ignore", category=OptimizeWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning, message="divide by zero encountered")


import logging
logging.config.dictConfig(cfg.LOGGING_CONFIG)

latency_func = {}
is_trained_flag = False
complete_traces = {}
all_traces = {}
prerecorded_trace = {}
svc_to_rps = {}
endpoint_level_inflight = {}
endpoint_level_rps = {}
endpoint_to_cg_key = {}
ep_str_callgraph_table = {}
sp_callgraph_table = {}
all_endpoints = {}
placement = {}
coef_dict = {}
profiling = True
trace_str = list()
# x_feature = "num_inflight_dict"
x_feature = "rps_dict"
target_y = "xt" # exclusive time
# target_y = "rt" # response time

'''
cluster_to_cid and cid_to_cluster should be deprecated
cluster_id is given as a number. e.g., 0, 1, 2, ...
'''
# cluster_to_cid = {"us-west": 0, "us-east": 1}
# cid_to_cluster = {0: "us-west", 1: "us-east"}
stats_mutex = Lock()
cluster_pcts = {}


def fit_mm1_model(data, y_col_name, svc_name, ep_str, cid, directory):
    logger = logging.getLogger(__name__)
    # y_col_name: "latency"
    # data: {endpoint_str: [rps], "latency": [latency]}
    df = pd.DataFrame(data)
    x_colnames = [x for x in df.columns if x != y_col_name] # x_columes: [endpoint_str]
    if len(x_colnames) > 1: # If there are more than one endpoint, it is an error.
        logger.error(f"ERROR: {svc_name} service has more than one endpoint")
        assert False
    x_col = x_colnames[0] # x_col: endpoint_str
    max_rps = df[x_col].max()
    use_raw_rps = True
    if use_raw_rps:
        u_ = df[x_col]  # Use raw x_col values directly
        def mm1_model(u, a, b):
            return (a / (1.05* max_rps - u)) + b
        logger.debug(f"max_rps: {max_rps}")
    else:
        # df['utilization-'+x_col] = df[x_col]
        df['utilization-'+x_col] = df[x_col]/df[x_col].max()
        u_ = df['utilization-'+x_col]
        def mm1_model(u, a, b):
            amplified_a = a * 1
            return (amplified_a) / (1.05 - u)+b
    y_ = df[y_col_name]
    if np.isinf(u_).any() or np.isnan(u_).any():
        logger.error("Infinite or NaN values found in 'u'")
    popt, _ = curve_fit(mm1_model, u_, y_, maxfev=10000)
    logger.debug(f"mm1, {ep_str} {int(popt[0])}/(max_rps - rps) + {popt[1]}")
    return {ep_str: popt[0], 'intercept': popt[1]}


def fit_polynomial_regression(data, y_colname, svc_name, ep_str, cid, directory, degree):
    logger = logging.getLogger(__name__)
    global target_y
    degree_list = [degree]
    # plt.figure()
    df = pd.DataFrame(data)
    x_colnames = [x for x in df.columns if x != y_colname]
    X = df[x_colnames]
    y = df[y_colname]
    # plt.scatter(X, y, color='red', alpha=0.1, label='Data')
    for degree in degree_list:
        X_transformed = np.hstack((X**degree, np.ones(X.shape)))
        model = LinearRegression(fit_intercept=False)
        model.fit(X_transformed, y)
        feature_names = x_colnames.copy() + ['intercept']
        logger.debug(f"svc_name,{svc_name}, model.coef_, {model.coef_}")
        coefficients = pd.Series(model.coef_, index=feature_names)
    #     X_plot = np.linspace(X.min(), X.max(), 100).reshape(-1, 1)
    #     X_plot_transformed = np.hstack((X_plot**degree, np.ones(X_plot.shape)))
    #     y_plot = model.predict(X_plot_transformed)
    #     label = f'${model.coef_[0]} \cdot x^{degree} + {model.coef_[1]}$'
    #     plt.plot(X_plot, y_plot, linewidth=1, label=label)
    #     logger.debug(f"plt.plot, degree: {degree}")
    # plt.ylim(0, 500)
    # plt.xlabel(x_feature)
    # plt.ylabel(y_colname +" ms")
    # plt.title(f'{ep_str} in {cid}')
    # plt.legend()
    # pdf_fn = f"{directory}/latency-{svc_name}-poly-{target_y}.pdf"
    # plt.savefig(pdf_fn)
    # logger.debug(f"**output: {pdf_fn}")
    # plt.show()
    # logger.debug(f"model coef coefficients, {coefficients}")
    return coefficients.to_dict()


def train_latency_function_with_trace(model, traces, directory, degree):
    logger = logging.getLogger(__name__)
    # df = tst.trace_to_df(traces)
    df = tst.trace_to_unfolded_df(traces)
    logger.debug(f'df.columns: {df.columns}')
    coef_dict = dict()
    logger.debug(f'df["cluster_id"].unique(): {df["cluster_id"].unique()}')
    for region in df["cluster_id"].unique():
        if region not in coef_dict:
            coef_dict[region] = dict()
        region_df = df[df["cluster_id"]==region]
        logger.debug(f'region_df.columns: {region_df.columns}')
        for svc_name in region_df["svc_name"].unique():
            region_svc_df = region_df[region_df["svc_name"]==svc_name]
            if svc_name not in latency_func:
                latency_func[svc_name] = dict()
            if svc_name not in coef_dict[region]:
                coef_dict[region][svc_name] = dict()
            for ep_str in region_svc_df["endpoint_str"].unique():
                if "checkoutcart" in directory:
                    if "hipstershop.CurrencyService/Convert" in ep_str or "/hipstershop.ProductCatalogService/GetProduct" in ep_str:
                        logger.error(row)
                        assert False
                ep_df = region_svc_df[region_svc_df["endpoint_str"]==ep_str]
                # Data preparation: load(X) and latency(y) 
                data = dict()
                for _, row in ep_df.iterrows():
                    flag = False
                    for endpoint_str, rps in row[x_feature].items(): # x_feature: rps_dict, endpoint_str: endpoint_str, rps: rps
                        # endpoint_str: ep_str, rps: rps
                        if endpoint_str not in data:
                            data[endpoint_str] = list()
                        if type(rps) != type(1):
                            logger.error(f"ERROR: type(rps) != type(1): {type(rps)}")
                            logger.error(f"rps: {rps}")
                            logger.error(f"row: {row}")
                            assert False
                        data[endpoint_str].append(rps)
                        flag = True
                    if flag == True:
                        if "latency" not in data:
                            data["latency"] = list()
                        if len(row[x_feature]) == 1:
                            data["latency"].append(row[target_y]) # target_y: 'xt' or 'rt'
                        else:
                            ''' 
                            It actullay occurs. I don't know how it occurs.
                            E.g., There was only one request type, checkoutcart so there must be only one endpoint in frontend but that is not true for some trace.
                            ERROR: len(row[rps_dict]) != 1: 4
                            ERROR - row[rps_dict]: {'frontend@POST@/setCurrency': 2, 'frontend@POST@/cart': 1, 'frontend@GET@/product/66VCHSJNUP': 1, 'frontend@POST@/cart/checkout': 3}
                            '''
                            logger.error(f"ERROR: len(row[{x_feature}]) != 1: {len(row[x_feature])}")
                            logger.error(f"row[{x_feature}]: {row[x_feature]}")
                            # assert False
                            continue # ignore this span. It will leave the trace incomplete and it will be cleaned up later.
                data = {key: value for key, value in data.items() if isinstance(value, list)}
                # data: {endpoint_str: [rps], "latency": [latency]}
                if model == "poly":
                    ts = time.time()
                    coef_dict[region][svc_name][ep_str] = fit_polynomial_regression(data, "latency", svc_name, ep_str, region, directory, degree)
                    logger.info(f"fit_polynomial_regression, {time.time()-ts}")
                elif model == "mm1":
                    coef_dict[region][svc_name][ep_str] = fit_mm1_model(data, "latency", svc_name, ep_str, region, directory)
                else:
                    logger.error(f"ERROR: model: {model}")
                    assert False
    return coef_dict


def trace_string_file_to_trace_data_structure(trace_string_file_path, required_num_endpoint, num_replica):
    logger = logging.getLogger(__name__)
    col = ["cluster_id","svc_name","method","path","trace_id","span_id","parent_span_id","st","et","rt","xt","ct","call_size","inflight_dict","rps_dict"]
    df = pd.read_csv(trace_string_file_path, names=col, header=None)
    logger.info(f"len(df): {len(df)}")
    df = df.loc[df['rt'] > 0]
    logger.info(f"after negative rt filter, len(df): {len(df)}")
    num_filter_rps_datapoint = 0
    list_of_span = list()
    for index, row in df.iterrows():
        if row["cluster_id"] == "SLATE_UNKNOWN_REGION" or row["svc_name"] == "consul":
            continue
        num_inflight_dict = dict()
        rps_dict = dict()
        inflight_list = row["inflight_dict"].split("|")[:-1]
        for ep_inflight in inflight_list:
            temp = ep_inflight.split(":")
            assert len(temp) == 2
            ep = temp[0]
            inflight = int(temp[1])
            num_inflight_dict[ep] = inflight
        rps_list = row["rps_dict"].split("|")[:-1]
        for ep_rps in rps_list:
            temp = ep_rps.split(":")
            assert len(temp) == 2
            ep = temp[0]
            rps = int(temp[1])
            ''' NOTE: HARDCODED, RPS FILTER'''
            if rps > 1000:
                continue
            rps_dict[ep] = rps * num_replica
        ''' NOTE: HARDCODED, RPS FILTER'''
        if rps > 1200:
            num_filter_rps_datapoint += 1
            continue
        span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], row["trace_id"], row["span_id"], row["parent_span_id"], st=float(row["st"]), et=float(row["et"]), callsize=int(row["call_size"]), rps_dict=rps_dict, num_inflight_dict=num_inflight_dict)
        list_of_span.append(span)
    logger.debug(f"-- num_filter_rps_datapoint: {num_filter_rps_datapoint}")  
    all_traces = dict()
    for span in list_of_span:
        if span.cluster_id not in all_traces:
            all_traces[span.cluster_id] = dict()
        if span.trace_id not in all_traces[span.cluster_id]:
            all_traces[span.cluster_id][span.trace_id] = list()
        all_traces[span.cluster_id][span.trace_id].append(span)
    logger.debug(f"required_num_endpoint in {cid}: {required_num_endpoint}")
    complete_traces = dict()
    for cid in all_traces:
        if cid not in complete_traces:
            complete_traces[cid] = dict()
        for tid in all_traces[cid]:
            if len(all_traces[cid][tid]) == required_num_endpoint:
                complete_traces[cid][tid] = all_traces[cid][tid]
    for cid in all_traces:
        logger.debug(f"len(all_traces[{cid}]): {len(all_traces[cid])}")
    for cid in complete_traces:
        logger.debug(f"len(complete_traces[{cid}]): {len(complete_traces[cid])}")
    return complete_traces

def trace_string_file_to_trace_data_structure_with_df(df, required_num_endpoint, num_replica):
    logger = logging.getLogger(__name__)
    logger.debug(f"len(df): {len(df)}")
    df = df.loc[df['rt'] > 0]
    logger.debug(f"after negative rt filter, len(df): {len(df)}")
    num_filter_rps_datapoint = 0
    list_of_span = list()
    excluded_traces = set()  # To track trace_ids with RPS > 6000

    for index, row in df.iterrows():
        if row["trace_id"] in excluded_traces:
            logger.debug(f"Part of invalid trace, {row['trace_id']}, {row['svc_name']}, {row['method']}, {row['path']} row")
            continue    
        
        if row["cluster_id"] == "SLATE_UNKNOWN_REGION" or row["svc_name"] == "consul":
            excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
            continue
        if "ListProducts" in row["path"]:
            logger.debug(f"asdf asdf {row}")
        if "checkoutcart" in directory:
            if "/hipstershop.CurrencyService/Convert" in row["path"] or "/hipstershop.ProductCatalogService/GetProduct" in row["path"]:
                logger.debug(f"Skip this span, {row['svc_name']}, {row['method']}, {row['path']} row")
                excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
                continue
        num_inflight_dict = dict()
        rps_dict = dict()
        inflight_list = row["inflight_dict"].split("|")[:-1]
        for ep_inflight in inflight_list:
            temp = ep_inflight.split(":")
            assert len(temp) == 2
            ep = temp[0]
            if "checkoutcart" in directory:
                if "hipstershop.CurrencyService/Convert" in ep or "/hipstershop.ProductCatalogService/GetProduct" in ep:
                    logger.debug(f"Skip inflight_dict, {ep} endpoint, {row['svc_name']}, {row['method']}, {row['path']} row")
                    excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
                    continue
            inflight = int(temp[1])
            num_inflight_dict[ep] = inflight
        rps_list = row["rps_dict"].split("|")[:-1] # sd03b@POST@/heavy:335|
        for ep_rps in rps_list:
            temp = ep_rps.split(":") # ["sd03b@POST@/heavy", "335"]
            assert len(temp) == 2
            ep = temp[0] # "sd03b@POST@/heavy"
            if "checkoutcart" in directory:
                if "hipstershop.CurrencyService/Convert" in ep or "/hipstershop.ProductCatalogService/GetProduct" in ep:
                    logger.debug(f"Skip rps_dict, {ep} endpoint, {row['svc_name']}, {row['method']}, {row['path']} row")
                    excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
                    continue
            rps = int(temp[1]) * num_replica # 335 * 3
            ''' NOTE: HARDCODED, RPS FILTER'''
            if rps > 6000:
                excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
                logger.debug(f"Skip UNREASONABLE RPS: {rps/num_replica} or {rps}, {row['trace_id']}, {row['svc_name']}, {row['method']}, {row['path']} row")
                continue
            rps_dict[ep] = rps
        # ''' NOTE: HARDCODED, RPS FILTER'''
        if rps > 6000:
            num_filter_rps_datapoint += 1
            excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
            continue
        if len(rps_dict) == 0:
            logger.error(row)
            assert False
        span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], row["trace_id"], row["span_id"], row["parent_span_id"], st=float(row["st"]), et=float(row["et"]), callsize=int(row["call_size"]), rps_dict=rps_dict, num_inflight_dict=num_inflight_dict)
        list_of_span.append(span)
    logger.debug(f"-- num_filter_rps_datapoint: {num_filter_rps_datapoint}")
    
    all_traces = dict()
    for span in list_of_span:
        if span.cluster_id not in all_traces:
            all_traces[span.cluster_id] = dict()
        if span.trace_id not in all_traces[span.cluster_id]:
            all_traces[span.cluster_id][span.trace_id] = list()
        all_traces[span.cluster_id][span.trace_id].append(span)
    logger.debug(f"required_num_endpoint: {required_num_endpoint}")
    complete_traces = dict()
    for cid in all_traces:
        if cid not in complete_traces:
            complete_traces[cid] = dict()
        for tid in all_traces[cid]:
            if len(all_traces[cid][tid]) == required_num_endpoint:
                complete_traces[cid][tid] = all_traces[cid][tid]
    return complete_traces


def merge_files(directory, postfix ,columns):
    logger = logging.getLogger(__name__)
    slatelog_files = glob.glob(os.path.join(directory, '**', f'*{postfix}'), recursive=True)
    for slate_log_file in slatelog_files:
        logger.debug(f"slate_log_file: {slate_log_file}")
    output_filename = f"merged-{postfix}"
    with open(output_filename, 'w') as outfile:
        for fname in slatelog_files:
            with open(fname) as infile:
                outfile.write(infile.read())
                logger.debug(f"Write {fname} to {output_filename}")
    return output_filename