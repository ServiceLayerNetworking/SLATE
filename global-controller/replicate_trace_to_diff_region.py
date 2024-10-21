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

logger = logging.getLogger(__name__)

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
    plt.figure()
    df = pd.DataFrame(data)
    x_colnames = [x for x in df.columns if x != y_col_name]
    # for x_col in x_colnames:
    if len(x_colnames) > 1:
        print(f"ERROR: {svc_name} service has more than one endpoint")
        print(f"Fit the function each endpoint separately")
        assert False
    x_col = x_colnames[0]
    df['utilization-'+x_col] = df[x_col]
    df['utilization-'+x_col] = df['utilization-'+x_col] / df['utilization-'+x_col].max()
    u_ = df['utilization-'+x_col]
    y_ = df[y_col_name]
    print(f"len(u): {len(u_)}, len(y_): {len(y_)}")
    if np.isinf(u_).any() or np.isnan(u_).any():
        print("Infinite or NaN values found in 'u'")
    # plt.scatter(u_, y_, color='blue', alpha=0.1, label='Data')
    max_rps = df[x_col].max()
    print(f"max_rps: {max_rps}")
    norm_u_ = u_*max_rps
    plt.scatter(norm_u_, y_, color='red', alpha=0.1, label='Data')
    constant = 1.08
    def mm1_model(u, a, b):
        amplified_a = a * 1
        return (amplified_a) / (1*constant - u)+b
    popt, pcov = curve_fit(mm1_model, u_, y_, maxfev=10000)
    print(f"popt = {popt}")
    # u_plot = np.linspace(min(u_), max(u_)*constant * 0.99, 100)  # Avoid division by zero at u=1
    u_plot = np.linspace(min(u_), max(u_)*constant, 100)  # Avoid division by zero at u=1
    y_plot = mm1_model(u_plot, *popt)
    # print(f"u_plot: {u_plot}")
    # print(f"y_plot: {y_plot}")
    norm_u_plot = u_plot*max_rps
    #plt.plot(norm_u_plot, y_plot, 'r-', label=f'MM1 Fit: $\\frac{{a}}{{c-u}}+b$,a={popt[0]}, c={u_.max()*constant}, b={popt[1]}')
    plt.plot(norm_u_plot, y_plot, 'r-', label=f'MM1 Fit: $\\frac{{a}}{{c-u}}+b$\n$a={popt[0]:.2f}, c={(u_.max()*constant):.2f}, b={popt[1]:.2f}$')
    # plt.plot(u_plot, y_plot, 'r-', label=f'MM1 Fit: $\\frac{{a}}{{1-u}}$, a={popt[0]:.2f}')
    plt.ylim(0, 500)
    plt.xlabel('Utilization (u_)')
    plt.ylabel(y_col_name + " ms")
    plt.title(f'{ep_str} in {cid}')
    plt.legend()
    plt.ylim(0, max(y_)*1.1)
    pdf_fn = f"{directory}/latency-{svc_name}-mm1-{target_y}.pdf"
    plt.savefig(pdf_fn)
    plt.show()
    # Output the model parameters and where the plot was saved
    print(f"Model parameters: a = {popt}")
    print(f"Output plot saved as: {pdf_fn}")
    # Return model parameters as a dictionary if needed
    return {'a': popt[0]}



def fit_polynomial_regression(data, y_col_name, svc_name, ep_str, cid, directory, degree):
    global target_y
    degree_list = [degree]
    plt.figure()
    df = pd.DataFrame(data)
    x_colnames = [x for x in df.columns if x != y_col_name]
    X = df[x_colnames]
    y = df[y_col_name]
    plt.scatter(X, y, color='red', alpha=0.1, label='Data')
    for degree in degree_list:
        X_transformed = np.hstack((X**degree, np.ones(X.shape)))
        model = LinearRegression(fit_intercept=False)
        model.fit(X_transformed, y)
        feature_names = x_colnames.copy() + ['intercept']
        print(f"svc_name,{svc_name}, model.coef_, {model.coef_}")
        coefficients = pd.Series(model.coef_, index=feature_names)
    #     X_plot = np.linspace(X.min(), X.max(), 100).reshape(-1, 1)
    #     X_plot_transformed = np.hstack((X_plot**degree, np.ones(X_plot.shape)))
    #     y_plot = model.predict(X_plot_transformed)
    #     label = f'${model.coef_[0]} \cdot x^{degree} + {model.coef_[1]}$'
    #     plt.plot(X_plot, y_plot, linewidth=1, label=label)
    #     print(f"plt.plot, degree: {degree}")
    # plt.ylim(0, 500)
    # plt.xlabel(x_feature)
    # plt.ylabel(y_col_name +" ms")
    # plt.title(f'{ep_str} in {cid}')
    # plt.legend()
    # pdf_fn = f"{directory}/latency-{svc_name}-poly-{target_y}.pdf"
    # plt.savefig(pdf_fn)
    # print(f"**output: {pdf_fn}")
    # plt.show()
    # print(f"model coef coefficients, {coefficients}")
    return coefficients.to_dict()


def train_latency_function_with_trace(model, traces, directory, degree):
    # df = tst.trace_to_df(traces)
    df = tst.trace_to_unfolded_df(traces)
    logger.info(f'df.columns: {df.columns}')
    coef_dict = dict()
    logger.info(f'df["cluster_id"].unique(): {df["cluster_id"].unique()}')
    for cid in df["cluster_id"].unique():
        cid_df = df[df["cluster_id"]==cid]
        logger.info(f'cid_df.columns: {cid_df.columns}')
        for svc_name in cid_df["svc_name"].unique():
            cid_svc_df = cid_df[cid_df["svc_name"]==svc_name]
            if svc_name not in latency_func:
                latency_func[svc_name] = dict()
            if svc_name not in coef_dict:
                coef_dict[svc_name] = dict()
            for ep_str in cid_svc_df["endpoint_str"].unique():
                if "checkoutcart" in directory:
                    if "hipstershop.CurrencyService/Convert" in ep_str or "/hipstershop.ProductCatalogService/GetProduct" in ep_str:
                        print(row)
                        assert False
                ep_df = cid_svc_df[cid_svc_df["endpoint_str"]==ep_str]
                # Data preparation: load(X) and latency(y) 
                data = dict()
                for index, row in ep_df.iterrows():
                    flag = False
                    for key, val in row[x_feature].items(): # x_feature: rps_dict
                        # key: ep_str, val: rps
                        if key not in data:
                            data[key] = list()
                        data[key].append(val)
                        flag = True
                    if flag == True:
                        if "latency" not in data:
                            data["latency"] = list()
                            
                        if len(row[x_feature]) == 1:
                            data["latency"].append(row[target_y])
                            # if xt:
                            #     data["latency"].append(row["xt"])
                            # else:
                            #     data["latency"].append(row["rt"])
                        else:
                            print(f"ERROR: len(row[{x_feature}]) != 1: {len(row[x_feature])}")
                            print(f"row[{x_feature}]: {row[x_feature]}")
                            print(f"{row['svc_name'], row['endpoint_str'], row['trace_id'], row['span_id']}")
                            assert False
                data = {key: value for key, value in data.items() if isinstance(value, list)}  # Ensure all values are lists
                # try:
                #     df = pd.DataFrame(data)
                # except ValueError as e:
                #     lengths = {key: len(value) for key, value in data.items()}
                #     print(f"data: {data}")
                #     print(f"lengths: {lengths}")  # This will show you the length of the array for each column
                #     print("Data length mismatch:", e)
                #     # Optional: Log the lengths for debugging
                #     assert False
                if model == "poly":
                    coef_dict[svc_name][ep_str] = fit_polynomial_regression(data, "latency", svc_name, ep_str, cid, directory, degree)
                elif model == "mm1":
                    coef_dict[svc_name][ep_str] = fit_mm1_model(data, "latency", svc_name, ep_str, cid, directory)
                else:
                    print(f"ERROR: model: {model}")
                    assert False
    return coef_dict


def trace_string_file_to_trace_data_structure(trace_string_file_path, required_num_endpoint, num_replica):
    col = ["cluster_id","svc_name","method","path","trace_id","span_id","parent_span_id","st","et","rt","xt","ct","call_size","inflight_dict","rps_dict"]
    df = pd.read_csv(trace_string_file_path, names=col, header=None)
    print(f"len(df): {len(df)}")
    df = df.loc[df['rt'] > 0]
    print(f"after negative rt filter, len(df): {len(df)}")
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
    print(f"-- num_filter_rps_datapoint: {num_filter_rps_datapoint}")  
    all_traces = dict()
    for span in list_of_span:
        if span.cluster_id not in all_traces:
            all_traces[span.cluster_id] = dict()
        if span.trace_id not in all_traces[span.cluster_id]:
            all_traces[span.cluster_id][span.trace_id] = list()
        all_traces[span.cluster_id][span.trace_id].append(span)
    print(f"required_num_endpoint in {cid}: {required_num_endpoint}")
    complete_traces = dict()
    for cid in all_traces:
        if cid not in complete_traces:
            complete_traces[cid] = dict()
        for tid in all_traces[cid]:
            if len(all_traces[cid][tid]) == required_num_endpoint:
                complete_traces[cid][tid] = all_traces[cid][tid]
    for cid in all_traces:
        print(f"len(all_traces[{cid}]): {len(all_traces[cid])}")
    for cid in complete_traces:
        print(f"len(complete_traces[{cid}]): {len(complete_traces[cid])}")
    return complete_traces

def trace_string_file_to_trace_data_structure_with_df(df, required_num_endpoint, num_replica):
    print(f"len(df): {len(df)}")
    df = df.loc[df['rt'] > 0]
    print(f"after negative rt filter, len(df): {len(df)}")
    num_filter_rps_datapoint = 0
    list_of_span = list()
    excluded_traces = set()  # To track trace_ids with RPS > 6000

    for index, row in df.iterrows():
        if row["trace_id"] in excluded_traces:
            print(f"Part of invalid trace, {row['trace_id']}, {row['svc_name']}, {row['method']}, {row['path']} row")
            continue    
        
        if row["cluster_id"] == "SLATE_UNKNOWN_REGION" or row["svc_name"] == "consul":
            excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
            continue
        if "ListProducts" in row["path"]:
            print(f"asdf asdf {row}")
        if "checkoutcart" in directory:
            if "/hipstershop.CurrencyService/Convert" in row["path"] or "/hipstershop.ProductCatalogService/GetProduct" in row["path"]:
                print(f"Skip this span, {row['svc_name']}, {row['method']}, {row['path']} row")
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
                    print(f"Skip inflight_dict, {ep} endpoint, {row['svc_name']}, {row['method']}, {row['path']} row")
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
                    print(f"Skip rps_dict, {ep} endpoint, {row['svc_name']}, {row['method']}, {row['path']} row")
                    excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
                    continue
            rps = int(temp[1]) * num_replica # 335 * 3
            ''' NOTE: HARDCODED, RPS FILTER'''
            if rps > 6000:
                excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
                print(f"Skip UNREASONABLE RPS: {rps/num_replica} or {rps}, {row['trace_id']}, {row['svc_name']}, {row['method']}, {row['path']} row")
                continue
            rps_dict[ep] = rps
        # ''' NOTE: HARDCODED, RPS FILTER'''
        if rps > 6000:
            num_filter_rps_datapoint += 1
            excluded_traces.add(row["trace_id"])  # Mark the trace_id for exclusion
            continue
        if len(rps_dict) == 0:
            print(row)
            assert False
        span = sp.Span(row["method"], row["path"], row["svc_name"], row["cluster_id"], row["trace_id"], row["span_id"], row["parent_span_id"], st=float(row["st"]), et=float(row["et"]), callsize=int(row["call_size"]), rps_dict=rps_dict, num_inflight_dict=num_inflight_dict)
        list_of_span.append(span)
    print(f"-- num_filter_rps_datapoint: {num_filter_rps_datapoint}")
    
    all_traces = dict()
    for span in list_of_span:
        if span.cluster_id not in all_traces:
            all_traces[span.cluster_id] = dict()
        if span.trace_id not in all_traces[span.cluster_id]:
            all_traces[span.cluster_id][span.trace_id] = list()
        all_traces[span.cluster_id][span.trace_id].append(span)
    print(f"required_num_endpoint: {required_num_endpoint}")
    complete_traces = dict()
    for cid in all_traces:
        if cid not in complete_traces:
            complete_traces[cid] = dict()
        for tid in all_traces[cid]:
            if len(all_traces[cid][tid]) == required_num_endpoint:
                complete_traces[cid][tid] = all_traces[cid][tid]
    return complete_traces


def merge_files(directory, postfix ,columns):
    slatelog_files = glob.glob(os.path.join(directory, '**', f'*{postfix}'), recursive=True)
    for slate_log_file in slatelog_files:
        print(f"slate_log_file: {slate_log_file}")
    output_filename = f"merged-{postfix}"
    with open(output_filename, 'w') as outfile:
        for fname in slatelog_files:
            with open(fname) as infile:
                outfile.write(infile.read())
                print(f"Write {fname} to {output_filename}")
    return output_filename


# if __name__ == "__main__":
#     if len(sys.argv) < 4:
#         print("Usage: python3 replicate.py <directory> <required_num_endpoint> <num_replica> <sample_ratio>")
#         sys.exit(1)
#     directory = sys.argv[1]
#     subdir = directory.split('/')[-1]
#     if subdir == "":
#         subdir = directory.split('/')[-2]
#     print(f"subdir: {subdir}")
#     required_num_endpoint = int(sys.argv[2])
#     num_replica = int(sys.argv[3])
#     sample_ratio = float(sys.argv[4])
    
#     columns = ["cluster_id","svc_name","method","path","trace_id","span_id","parent_span_id","st","et","rt","xt","ct","call_size","inflight_dict","rps_dict"]
    
#     merged_trace_file_name = merge_files(directory, "trace.slatelog", columns)
#     print(f"* Output, merged_trace_file_name: {merged_trace_file_name}")
#     # merged_trace_file_name = "mergedtrace.slatelog"
#     ts = time.time()
#     # line_index_to_remove = 797046
#     # line_index_to_remove = 229902
#     # with open(merged_trace_file_name, 'r') as file:
#     #     lines = file.readlines()  # Read all lines into a list
#     #     if len(lines) > line_index_to_remove:
#     #         if 0 <= line_index_to_remove < len(lines):
#     #             removed_line = lines.pop(line_index_to_remove)
#     #             print(f"Removed line {line_index_to_remove}")
#     #         with open(merged_trace_file_name, 'w') as file:
#     #             file.writelines(lines)  # Write the updated list of lines
#     #             print(f"Output, removed line {removed_line}")
        
#     df = pd.read_csv(merged_trace_file_name, header=None, names=columns, on_bad_lines='skip')
#     df['endpoint'] = df['svc_name'] + "@" + df['method'] + "@" + df['path']
    
#     df = df[df["rt"] > 0]
#     # df['rps'] = df['rps_dict'].apply(lambda x: int(x.split(':')[1]))
#     # df = df[df['rps'] <= 6000]
    
#     ss = df["svc_name"].unique()
#     pp = df["endpoint"].unique()
#     print(f"svc len(service): {len(ss)}, {ss}")
#     print(f"endpoint len(endpoint): {len(pp)}, {pp}")
    
#     trace_id = df['trace_id'].unique().tolist()
#     sample_size = int(len(trace_id) * sample_ratio)
#     sampled_trace_id = sample(trace_id, sample_size)
    
#     sampled_df = df[df['trace_id'].isin(sampled_trace_id)]
#     sampled_df.to_csv("sampled_df.csv")
#     print("Output sampled_df.csv")
    
#     trace_span_counts = sampled_df.groupby('trace_id').size()
#     print(f"trace_span_counts: {trace_span_counts}")
#     print(f"max(trace_span_counts): {max(trace_span_counts)}")
#     trace_ids_with_four_spans = trace_span_counts[trace_span_counts == required_num_endpoint].index
#     filtered_df = sampled_df[sampled_df['trace_id'].isin(trace_ids_with_four_spans)]
#     filtered_df.to_csv("filtered_df.csv")
#     print(f"len(filtered_df): {len(filtered_df)}")
#     print("Output filtered_df.csv")
#     service_list = filtered_df['svc_name'].unique().tolist()
#     endpoint_list = filtered_df['endpoint'].unique().tolist()
#     print(f"service_list: {service_list}")
#     print(f"len(service_list): {len(service_list)}")
#     print(f"endpoint_list: {endpoint_list}")
#     print(f"len(endpoint_list): {len(endpoint_list)}")
    
#     complete_traces = trace_string_file_to_trace_data_structure_with_df(filtered_df, required_num_endpoint, num_replica)
#     for cid in complete_traces:
#         print(f"len(complete_traces[{cid}]): {len(complete_traces[cid])}")
        
#     # complete_traces_df = tst.trace_to_df(complete_traces)
#     # complete_traces_df.to_csv("complete_traces_df.csv")
#     # print("Output complete_traces_df.csv")
    
#     stitched_traces = tst.stitch_time(complete_traces)
#     for cid in stitched_traces:
#         print(f"len(stitched_traces[{cid}]): {len(stitched_traces[cid])}")
    
#     stitched_df = tst.trace_to_df(stitched_traces)
#     stitched_df.to_csv(f"stitched_df-{subdir}.csv")
#     print(f"Output stitched_df-{subdir}.csv")

#     degree = 2 # NOTE
#     poly_coef_dict = train_latency_function_with_trace("poly", stitched_traces, directory, degree)
#     print("-"*80)
#     multiplied_by_one_fn = f"{directory}/poly-coef_multiplied_by_one-{subdir}.csv"
#     with open(multiplied_by_one_fn, "w") as f:
#         for svc_name in poly_coef_dict:
#             for ep_str in poly_coef_dict[svc_name]:
#                 for feature in poly_coef_dict[svc_name][ep_str]:
#                     print(f'poly_coef_dict,{svc_name},{ep_str},{feature},{poly_coef_dict[svc_name][ep_str][feature]}')
#                     f.write(f'{svc_name},{ep_str},{feature},{poly_coef_dict[svc_name][ep_str][feature]}\n')
#     print("-"*80)
#     print(f"Output: {multiplied_by_one_fn}")
    
#     mm1_coef_dict = train_latency_function_with_trace("mm1", stitched_traces, directory, degree=None)
#     print("-"*80)
#     multiplied_by_one_fn = f"{directory}/mm1-coef_multiplied_by_one-{subdir}.csv"
#     with open(multiplied_by_one_fn, "w") as f:
#         for svc_name in mm1_coef_dict:
#             for ep_str in mm1_coef_dict[svc_name]:
#                 for feature in mm1_coef_dict[svc_name][ep_str]:
#                     print(f'mm1_coef_dict,{svc_name},{ep_str},{feature},{mm1_coef_dict[svc_name][ep_str][feature]}')
#                     f.write(f'{svc_name},{ep_str},{feature},{mm1_coef_dict[svc_name][ep_str][feature]}\n')
#     print("-"*80)
#     print(f"Output: {multiplied_by_one_fn}")
    
#     print("num all trace ", len(df['trace_id'].unique()))
#     print("num sampled trace", len(sampled_df['trace_id'].unique()))
#     print("num filtered trace", len(filtered_df['trace_id'].unique()))
#     print("num stitched trace", len(stitched_df['trace_id'].unique()))
    
    
#     ''' Define how you want to replicate '''
#     new_cluster_dict = dict()
#     # replicated_cluster_list = ["us-east-1", "us-central-1", "us-south-1"]
#     replicated_cluster_list = ["us-east-1"]
#     for cluster in replicated_cluster_list:
#         new_cluster_dict[cluster] = service_list
#     new_df_dict = dict()
#     for nc in new_cluster_dict:
#         copy_df = stitched_df.copy() # copy orignal trace log df
#         copy_df['cluster_id'] = nc # set 'cluster_id' column to a new cluster name
#         copy_df = copy_df[copy_df['svc_name'].isin(new_cluster_dict[nc])] # filter out services that you don't want to replicate
#         new_df_dict[nc] = copy_df.copy()
#         print(f"Replicated {nc}")
#     df_all = stitched_df.copy()
#     for cluster_id, new_df in new_df_dict.items():
#         df_all = pd.concat([df_all, new_df])
#     df_all.sort_values(by=['cluster_id', 'trace_id'], inplace=True)
    
#     output_fn = "replicated-"
#     for nc in new_cluster_dict:
#         cluster_id_first_ch = nc.split('-')[1][0]
#         output_fn += f"{cluster_id_first_ch}-"
#     output_fn += "trace.csv"
#     output_path = directory + output_fn
#     df_all.to_csv(output_path, index=False, header=False)
#     print("Output file written: ", output_path)
