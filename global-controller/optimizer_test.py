#!/usr/bin/env python
# coding: utf-8

# In[31]:
import sys
sys.dont_write_bytecode = True

import time
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
import random
import gurobipy_pandas as gppd
from gurobi_ml import add_predictor_constr
from IPython.display import display
import config as cfg
import optimizer_header as opt_func
import time_stitching as tst
import os
from IPython.display import display
import itertools
from pprint import pprint
import span as sp
from global_controller import app

import logging
logging.config.dictConfig(cfg.LOGGING_CONFIG)

random.seed(1234)

# output_dir = "optimizer_output"

'''
For interactive run with jupyternotebook, comment out following lines "COMMENT_OUT_FOR_JUPYTER".
And adjust the indentation accordingly.
'''

# pre_recorded_trace is simply a list of spans?
'''
*********************
** Data structures **
*********************

NUM_REQUESTS = {cid_0: {"cg_1": rps, "cg_2": rps}, 
                cid_1: {"cg_1": rps, "cg_2": rps}}

cg_key = bfs_callgraph and append svc_name, method, url

ep_str_callgraph_table[cg_key][parent_ep_str] = list of child_ep_str

request_in_out_weight[cg_key][parent_ep_str][child_ep_str] = in_/out_ ratio

latency_func[svc_name][endpoint] = fitted regression model

endpoint_level_inflight_req[cid][svc_name][ep] = #inflight req

endpoint_level_rps[cid][svc_name][ep] = rps

root_node_max_rps[root_node_endpoint] = rps

all_endpoints[cid][svc_name] = set of endpoint

placement[cid] = set of svc_names

svc_to_placement[svc_name] = set of cids

endpoint_to_placement[ep] = set of cids

max_capacity_per_service[svc_name] = max_load

traffic_segmentation = True/False

objective = "avg_latency"/"end_to_end_latency"/"egress_cost"/"multi_objective"

inter_cluster_latency['us-west']['us-east'] = 20 # this is oneway latency
inter_cluster_latency['us-west']['us-central'] = 10
'''

# def run_optimizer(coef_dict, endpoint_level_inflight_req, endpoint_level_rps, placement, svc_to_placement, endpoint_to_placement, endpoint_to_cg_key, ep_str_callgraph_table, traffic_segmentation, objective, ROUTING_RULE, max_capacity_per_service, degree, inter_cluster_latency):
def run_optimizer(coef_dict, \
        endpoint_level_rps, \
        placement, \
        svc_to_placement, \
        endpoint_to_placement, \
        ep_str_callgraph_table, \
        traffic_segmentation, \
        objective, \
        ROUTING_RULE, \
        max_capacity_per_service, \
        degree, \
        inter_cluster_latency, \
        endpoint_sizes, \
        DOLLAR_PER_MS):
    logger = logging.getLogger(__name__)
    if not os.path.exists(cfg.OUTPUT_DIR):
        os.mkdir(cfg.OUTPUT_DIR)
        logger.debug(f"{cfg.log_prefix} mkdir {cfg.OUTPUT_DIR}")

    def collapse_cid_in_endpoint_level_rps(endpoint_level_rps):
        collapsed_endpoint_level_rps = dict()
        for cid in endpoint_level_rps:
            for svc_name in endpoint_level_rps[cid]:
                for ep in endpoint_level_rps[cid][svc_name]:
                    if svc_name not in collapsed_endpoint_level_rps:
                        collapsed_endpoint_level_rps[svc_name] = dict()
                    if ep not in collapsed_endpoint_level_rps[svc_name]:
                        collapsed_endpoint_level_rps[svc_name][ep] = 0
                    # try:
                    collapsed_endpoint_level_rps[svc_name][ep] += endpoint_level_rps[cid][svc_name][ep]
                    # except Exception as e:
                        # logger.info(f'collapsed_endpoint_level_rps[{svc_name}][{ep}]: {type(collapsed_endpoint_level_rps[svc_name][ep])}')
                        
                        # logger.info(f'endpoint_level_rps[{cid}][{svc_name}][{ep}]: {type(endpoint_level_rps[cid][svc_name][ep])}')
                        # logger.error(f'Exception: {e}')
        return collapsed_endpoint_level_rps
    
    collapsed_endpoint_level_rps = collapse_cid_in_endpoint_level_rps(endpoint_level_rps)
    logger.info(f'collapsed_endpoint_level_rps: {collapsed_endpoint_level_rps}')
    # This is used in flow_conservation-nonleaf_endnode constraint
    request_in_out_weight = dict()
    for cg_key in ep_str_callgraph_table:
        if cg_key not in request_in_out_weight:
            request_in_out_weight[cg_key] = dict()
        for parent_ep in ep_str_callgraph_table[cg_key]:
            if parent_ep not in request_in_out_weight[cg_key]:
                request_in_out_weight[cg_key][parent_ep] = dict()
            for child_ep in ep_str_callgraph_table[cg_key][parent_ep]:
                if child_ep not in request_in_out_weight[cg_key][parent_ep]:
                    request_in_out_weight[cg_key][parent_ep][child_ep] = dict()
                parent_svc_name = parent_ep.split(cfg.ep_del)[0]
                child_svc_name = child_ep.split(cfg.ep_del)[0]
                # TODO: request_in_out_weight[cg_key][parent_ep][child_ep] = in_/out_
                # logger.debug(f'parent_svc_name: {parent_svc_name}, parent_ep: {parent_ep}, {collapsed_endpoint_level_rps[parent_svc_name]}')
                # logger.debug(f'child_svc_name: {child_svc_name}, child_ep: {child_ep}, {collapsed_endpoint_level_rps[child_svc_name]}')                
                # in_ = collapsed_endpoint_level_rps[parent_svc_name][parent_ep]
                # out_ = collapsed_endpoint_level_rps[child_svc_name][child_ep]
                # logger.debug(f'request_in_out_weight: {request_in_out_weight[cg_key][parent_ep][child_ep]}, parent_ep: {parent_ep}, child_ep: {child_ep}, in_: {in_}, out_: {out_}')
                
                request_in_out_weight[cg_key][parent_ep][child_ep] = 1
                
    ##############################################
    # TODO: Problem: how should we the endpoint to each call graph? Otherwise, by simply using the endpoint, we are not able to find root endpoint of the call graph.
    # norm_inout_weight = dict()
    # for cg_key in request_in_out_weight:
    #     norm_inout_weight[cg_key] = opt_func.norm(request_in_out_weight[cg_key], root_endpoint[cg_key].endpoint)
    # merged_in_out_weight = opt_func.merge(request_in_out_weight, norm_inout_weight, MAX_LOAD)
    # norm_merged_in_out_weight = opt_func.norm(merged_in_out_weight, root_endpoint[cg_key].svc_name)
    ##############################################
    
    if traffic_segmentation == False:
        logger.error(f'further implementation is required for traffic_segmentation False')
        assert False
        original_NUM_REQUESTS = NUM_REQUESTS.copy()
        original_MAX_LOAD = MAX_LOAD.copy()
        original_callgraph = callgraph.copy()
        original_request_in_out_weight = request_in_out_weight.copy()
        merged_cg_key = "M"
        merged_callgraph = opt_func.merge_callgraph(callgraph)
        callgraph = dict()
        callgraph[merged_cg_key] = merged_callgraph
        request_in_out_weight = dict()
        request_in_out_weight[merged_cg_key] = merged_in_out_weight
        norm_inout_weight = dict()
        norm_inout_weight[merged_cg_key] = norm_merged_in_out_weight
        merged_NUM_REQUESTS = list()
        for num_req in NUM_REQUESTS:
            merged_NUM_REQUESTS.append({merged_cg_key: sum(num_req.values())})
        NUM_REQUESTS = list()
        NUM_REQUESTS = merged_NUM_REQUESTS
        MAX_LOAD = opt_func.get_max_load(NUM_REQUESTS)

    ## depth_dict
    ## key: cg key, value: dict of {svc: depth}
    depth_dict = dict()
    for cg_key in ep_str_callgraph_table:
        depth_dict[cg_key] = opt_func.get_depth_in_graph(ep_str_callgraph_table[cg_key])
        
    callsize_dict = dict()
    for cg_key in ep_str_callgraph_table:
        callsize_dict[cg_key] = opt_func.get_callsize_dict(ep_str_callgraph_table[cg_key], endpoint_sizes)
    
    # root_node_max_rps = opt_func.get_root_node_max_rps(root_node_rps)
    compute_arc_var_name = opt_func.create_compute_arc_var_name(endpoint_level_rps)
    opt_func.check_compute_arc_var_name(compute_arc_var_name)
    # try:
    logger.debug(f'compute_arc_var_name: {compute_arc_var_name}')
    compute_df = opt_func.create_compute_df(compute_arc_var_name, ep_str_callgraph_table, coef_dict, max_capacity_per_service)
    # except Exception as e:
        # logger.error(f'Exception: {type(e).__name__}, {e}')
        # logger.error(f'!!! ERROR !!! create_compute_df failed')
        # assert False
        # return pd.DataFrame(), f"Exception: {e}"
    compute_df.to_csv(f'compute_df.csv')
    if traffic_segmentation == False:
        original_compute_df = opt_func.create_compute_df(placement, original_callgraph, callsize_dict, original_NUM_REQUESTS, original_MAX_LOAD)

    # When using gurobi.wls license
    ## Defining objective function
    gurobi_key = open("./gurobi.wls", "r")
    options = dict()
    for line in gurobi_key:
        line = line.strip()
        # print("line: ", line)
        if line == "":
            continue
        key, value = line.split(",")
        if key == "LICENSEID":
            value = int(value)
        options[key] = value
    options['OutputFlag'] = 0
    env = gp.Env(params=options)
    gurobi_model = gp.Model('RequestRouting', env=env)

    compute_latency = dict()
    compute_load = dict()
    compute_latency = gppd.add_vars(gurobi_model, compute_df, name="compute_latency", lb="min_compute_latency")
    compute_load = gppd.add_vars(gurobi_model, compute_df, name="load_for_compute_edge", ub="max_load")
    '''
    compute_load2 = compute_load**2
    latency = compute_load2**2 + b
    latency = (compute_load**2)**2 + b
    latency = compute_load**4 + b -> this is what we want eventually. 
    This is walkaround solution because gurobi does not support more than quadratic.
    '''
    compute_load2 = gppd.add_vars(gurobi_model, compute_df, name="load_for_compute_edge2")
    for index, row in compute_df.iterrows():
        if degree == 4:
            gurobi_model.addConstr(compute_load2[index] == compute_load[index]**2, name=f'for_higher_degree-{index}')
        
    gurobi_model.update()
    constraint_file = open(f'constraint.log', 'w')
    
    '''
    Manually setting the latency function constraint
    
    coef[ep_1] = latency_function[svc_A][ep_1]["linearregression"].coef_[0]
    coef[ep_2] = latency_function[svc_A][ep_1]["linearregression"].coef_[1]
    intercept = latency_function[svc_A][ep_1]["linearregression"].intercept_
    Constraint equation:
        endpoint latency == (coef[ep_1]*scheduled_load[ep_1]) + (coef[ep_2]*scheduled_load[ep_2]) + intercept
    '''
    normalized_total_rps = dict()
    for svc_name in compute_df['svc_name'].unique():
        if svc_name not in normalized_total_rps:
            normalized_total_rps[svc_name] = 0
        svc_df = compute_df[compute_df['svc_name'] == svc_name]
        if len(svc_df) == 0:
            logger.error(f'svc_name: {svc_name} does not exist in compute_df')
            assert False
        cid_of_svc = svc_df['src_cid'].unique()
        for cid in cid_of_svc:
            svc_cid_df = svc_df[svc_df['src_cid'] == cid]
            for ep in svc_cid_df['endpoint'].unique(): # all endpoints of the svc
                arc_name = opt_func.get_compute_arc_var_name(ep, cid)
                normalized_total_rps[svc_name] += compute_load[arc_name]
        logger.debug(f'normalized_total_rps[{svc_name}]: {normalized_total_rps[svc_name]}')
        
    for index, row in compute_df.iterrows():
        lh = compute_latency[index]
        rh = 0
        # try:
        coefs = row['coef']
        logger.debug(f"target svc,endpoint: {row['svc_name']}, {row['endpoint']}")
        logger.debug(coefs)
        for dependent_ep in coefs:
            if dependent_ep != 'intercept':
                dependent_arc_name = opt_func.get_compute_arc_var_name(dependent_ep, row['src_cid'])
                logger.debug(f'dependent_arc_name: {dependent_arc_name}')
                logger.debug(f'coefs[{dependent_ep}]: {coefs[dependent_ep]}')
                logger.debug(f'dependent_arc_name: {dependent_arc_name}')
                if degree == 4:
                    # degree is 4 using compute_load2 = compute_load**2
                    rh += coefs[dependent_ep] * (compute_load2[dependent_arc_name] ** 2) 
                elif degree == 2:
                    rh += coefs[dependent_ep] * (compute_load[dependent_arc_name] ** 2) 
                else:
                    # degree is 1
                    rh += coefs[dependent_ep] * (compute_load[dependent_arc_name])
        rh += coefs['intercept']
        constraint_file.write(f"{lh}\n")
        constraint_file.write("==\n")
        constraint_file.write(f"{rh}\n")
        constraint_file.write("-"*80)
        constraint_file.write("\n")
        gurobi_model.addConstr(lh == rh, name=f'latency_function_{index}')
    gurobi_model.update()


    logger.debug(f'{svc_to_placement}')
    ## Define names of the variables for network arc in gurobi
    # endpoint_to_placement: 
    # {'A,POST,post': {0, 1}, 'A,GET,read': {0, 1}, 'B,GET,read': {0, 1}, 'C,POST,post': {0, 1}}
    network_arc_var_name = list()
    for cg_key in ep_str_callgraph_table:
        for parent_ep_str in ep_str_callgraph_table[cg_key]:
            for child_ep_str in ep_str_callgraph_table[cg_key][parent_ep_str]:
                for p_cid in endpoint_to_placement[parent_ep_str]:
                    for c_cid in endpoint_to_placement[child_ep_str]:
                        # logger.debug(f'parent_ep_str: {parent_ep_str}, p_cid: {p_cid}, child_ep_str: {child_ep_str}, c_cid: {c_cid}')
                        var_name = opt_func.get_network_arc_var_name(parent_ep_str, child_ep_str, p_cid, c_cid)
                        if var_name not in network_arc_var_name:
                            network_arc_var_name.append(var_name)

    for cg_key in ep_str_callgraph_table:
        root_node = opt_func.find_root_node(ep_str_callgraph_table[cg_key])
        for dst_cid in endpoint_to_placement[root_node]:
            logger.debug(f'root_node: {root_node}')
            logger.debug(f'dst_cid, {dst_cid}')
            var_name = opt_func.get_network_arc_var_name(opt_func.source_node_name, root_node, opt_func.NONE_CID, dst_cid)
            network_arc_var_name.append(var_name)
    
    columns=["src_endpoint", "src_cid", "dst_endpoint", "dst_cid", "min_network_time", "max_network_time", "max_load", "min_load", "min_egress_cost", "max_egress_cost"]
    network_df = pd.DataFrame(
        columns=columns,
        data={
        },
        index=network_arc_var_name
    )

    src_endpoint_list = list()
    dst_endpoint_list = list()
    src_cid_list = list()
    dst_cid_list = list()
    min_network_time_list = list()
    max_network_time_list = list()
    min_egress_cost_list = list()
    max_egress_cost_list = list()
    flattened_callsize_dict = {inner_key: value for outer_key, inner_dict in callsize_dict.items() for inner_key, value in inner_dict.items()}
    for key in flattened_callsize_dict:
        logger.info(f"flattened_callsize_dict[{key}]: {flattened_callsize_dict[key]}")
        
    for var_name in network_arc_var_name:
        if type(var_name) == tuple:
            src_endpoint = var_name[0].split(cfg.DELIMITER)[0]
            dst_endpoint = var_name[1].split(cfg.DELIMITER)[0]
            logger.debug(f"src_endpoint: {src_endpoint}, dst_endpoint: {dst_endpoint}")
            # src_cid = int(var_name[0].split(cfg.DELIMITER)[1])
            # dst_cid = int(var_name[1].split(cfg.DELIMITER)[1])
            src_cid = var_name[0].split(cfg.DELIMITER)[1]
            dst_cid = var_name[1].split(cfg.DELIMITER)[1]
        else:
            logger.error("var_name MUST be tuple datatype")
            assert False
        src_cid_list.append(src_cid)
        dst_cid_list.append(dst_cid)
        src_endpoint_list.append(src_endpoint)
        dst_endpoint_list.append(dst_endpoint)
        # min_network_time_list.append(opt_func.get_network_latency(src_cid, dst_cid)*2)
        # max_network_time_list.append(opt_func.get_network_latency(src_cid, dst_cid)*2)
        try:
            if src_cid == "XXXX" or dst_cid == "XXXX":
                min_network_time_list.append(0)
                max_network_time_list.append(0)
            else:
                min_network_time_list.append(inter_cluster_latency[src_cid][dst_cid] + inter_cluster_latency[dst_cid][src_cid])
                max_network_time_list.append(inter_cluster_latency[src_cid][dst_cid] + inter_cluster_latency[dst_cid][src_cid])
        except Exception as e:
            logger.error(f"!!! ERROR !!! inter_cluster_latency, {src_cid}, {dst_cid}, {type(e).__name__}, {e}")
            logger.error(inter_cluster_latency)
            assert False
        e_cost = opt_func.get_egress_cost(src_endpoint, src_cid, dst_endpoint, dst_cid, flattened_callsize_dict)
        if e_cost != 0:
            logger.debug(f"egress_cost: {e_cost}, from {src_cid}-{src_endpoint} to {dst_cid}-{dst_endpoint}")
        min_egress_cost_list.append(e_cost)
        max_egress_cost_list.append(e_cost)
        
    network_df["src_endpoint"] = src_endpoint_list
    network_df["dst_endpoint"] = dst_endpoint_list
    network_df["src_cid"] = src_cid_list
    network_df["dst_cid"] = dst_cid_list
    network_df["min_network_time"] = min_network_time_list
    network_df["max_network_time"] = max_network_time_list
    # for index, row in network_df.iterrows():
    #     network_df.at[index, 'max_load'] = MAX_LOAD[key]
    #     if row["src_svc"] == opt_func.source_node_name:
    #         network_df.at[index, 'max_load'] = MAX_LOAD[key]
    #     else:
    #         network_df.at[index, 'max_load'] = 0
    #     network_df.at[index, 'min_load'] = 0
    network_df["min_egress_cost"] = min_egress_cost_list
    network_df["max_egress_cost"] = max_egress_cost_list

    network_df.to_csv(f'network_df.csv')
    network_latency = dict()
    network_load = dict()
    network_egress_cost = dict()
    network_latency = gppd.add_vars(gurobi_model, network_df, name="network_latency", lb="min_network_time", ub="max_network_time")
    network_load = gppd.add_vars(gurobi_model, network_df, name="load_for_network_edge")
    network_egress_cost = gppd.add_vars(gurobi_model, network_df, name="network_egress_cost", lb="min_egress_cost", ub="max_egress_cost")
    gurobi_model.update()

    # avg_latency
    network_latency_sum = 0
    compute_latency_sum = 0
    network_latency_sum += sum(network_latency.multiply(network_load))
    compute_latency_sum += sum(compute_latency.multiply(compute_load))
    total_latency_sum = network_latency_sum + compute_latency_sum

    # egress_cost
    network_egress_cost_sum = 0
    network_egress_cost_sum += sum(network_egress_cost.multiply(network_load))
    total_egress_sum = network_egress_cost_sum
    gurobi_model.update()
    
    #############################################################
    if objective == "max_end_to_end_latency":
        svc_order = dict()
        for key in callgraph:
            assert key not in svc_order
            svc_order[key] = dict()
            root_svc_name = "ingress_gw" # NOTE: IT IS HARDCODED!!
            opt_func.get_dfs_svc_order(callgraph, key, root_svc_name, svc_order, idx=0)
        for key in svc_order:
            logger.debug(f'svc_order[{key}]: {svc_order[key]}')
        svc_to_placement = dict()
        all_combinations = dict()
        new_all_combinations = dict()
        for key in callgraph:
            svc_to_placement[key] = opt_func.svc_to_cid(svc_order[key], placement)
            logger.debug(f'svc_to_placement[{key}]: {svc_to_placement[key]}')
            all_combinations[key] = list(itertools.product(*svc_to_placement[key]))
            new_all_combinations[key] = opt_func.remove_too_many_cross_cluster_routing_path(all_combinations[key], 1)
            # for comb in new_all_combinations[key]:
            #     logger.info(f'comb: {comb}')
            #     break
        assert svc_order.keys() == new_all_combinations.keys()

        root_node = dict()
        for key in callgraph:
            root_node[key] = opt_func.find_root_node(callgraph, "A")
        logger.debug(f'root_node: {root_node}')

        unpack_list = dict()
        for key in callgraph:
            unpack_list[key] = list()
            opt_func.unpack_callgraph_in_dfs_order(callgraph, key, root_node[key], unpack_list[key])
        for key in unpack_list:
            logger.debug(f'unpack_list[{key}]: {unpack_list[key]}')
        path_dict = dict()
        for key in svc_order:
            path_dict[key] = dict()
            for comb in new_all_combinations[key]:
                # return type of create_path: list (path is a list)
                path = opt_func.create_path(svc_order[key], comb, unpack_list[key], callgraph, key)
                path_dict[key][comb] = path
        # for key in path_dict:
        #     for comb, path in path_dict[key].items():
        #         logger.debug(f'{comb} path in path_dict[{key}]')
        #         for pair in path:
        #             logger.debug(f'{pair}')
            
        possible_path = dict()
        for key in callgraph:
            possible_path[key] = dict()
            for comb in new_all_combinations[key]:
                logger.debug(f'key: {key}, comb: {comb}')
                possible_path[key][comb] = list()

        end_to_end_path_var = dict()
        for key in path_dict:
            end_to_end_path_var[key] = dict()
            for comb, path in path_dict[key].items():
                logger.debug(f'comb: {comb}')
                # end_to_end_path_var[key][comb] = gurobi_model.addVar(vtype=gp.GRB.CONTINUOUS, name=f'end_to_end_path_var_{key}_{comb}')
                end_to_end_path_var[key][comb] = 0
                for pair in path:
                    if opt_func.is_network_var(pair):
                        try:
                            # logger.debug(f'network_latency[{key}][{pair}]: {network_latency[key][pair]}')
                            # end_to_end_path_var[key][comb].append(network_latency[key][pair])
                            end_to_end_path_var[key][comb] += network_latency[key][pair]
                        except Exception as e:
                            logger.debug(f'network_latency, key: {key}, pair: {pair}')
                            logger.debug(f'Exception: {type(e).__name__}, {e}')
                            assert False
                    else:
                        try:
                            # logger.debug(f'compute_latency[{key}][{pair}]: {compute_latency[key][pair]}')
                            # end_to_end_path_var[key][comb].append(compute_latency[key][pair])
                            end_to_end_path_var[key][comb] += compute_latency[key][pair]
                            logger.debug(f'compute_latency[{key}][{pair}]: {compute_latency[key][pair]}')
                        except Exception as e:
                            logger.error(f'compute_latency[{key}][{pair}]: {compute_latency[key][pair]}')
                            logger.error(f'Exception: {type(e).__name__}, {e}')
                            assert False
        gurobi_model.update()
        # logger.debug()
        # for key in end_to_end_path_var:
        #     for comb in end_to_end_path_var[key]:
        #         logger.debug(f'key: {key}, comb: {comb}')
        #         # for var in end_to_end_path_var[key][comb]:
        #         logger.debug(f'{end_to_end_path_var[key][comb]}')
        #         logger.debug()
                
        '''
        reference: https://www.gurobi.com/documentation/current/refman/py_model_agc_max.html#pythonmethod:Model.addGenConstrMax
        # gurobi_model.addGenConstrMax(resvar=max_end_to_end_latency, vars=end_to_end_path_list, name="maxconstr")
        '''
        max_end_to_end_latency = gurobi_model.addVar(name="max_end_to_end_latency", lb=0)
        # end_to_end_path_list = list()
        for key in end_to_end_path_var:
            for comb in end_to_end_path_var[key]:
                # end_to_end_path_list.append(end_to_end_path_var[key][comb])
                gurobi_model.addConstr(end_to_end_path_var[key][comb] <= max_end_to_end_latency, name=f'maxconstr_{key}_{comb}')
                constraint_file.write(f'end_to_end_path_var[{key}][{comb}] <= max_end_to_end_latency({max_end_to_end_latency})\n')
                # logger.debug(f'end_to_end_path_var[{key}][{comb}]: {end_to_end_path_var[key][comb]}')
                # logger.debug(f'<=')
                # logger.debug(f'max_end_to_end_latency')
        gurobi_model.update()
        logger.info('max_end_to_end_latency')
        logger.info(f'{max_end_to_end_latency}\n')
    ''' end of if objective == "max_end_to_end_latency" '''
    #############################################################

    if objective == "avg_latency":
        gurobi_model.setObjective(total_latency_sum, gp.GRB.MINIMIZE)
    elif objective == "end_to_end_latency":
        gurobi_model.setObjective(max_end_to_end_latency, gp.GRB.MINIMIZE)
    elif objective == "egress_cost":
        gurobi_model.setObjective(total_egress_sum, gp.GRB.MINIMIZE)
    elif objective == "multi_objective":
        # NOTE: higher dollar per ms, more important the latency
        # DOLLAR_PER_MS: value of latency
        # lower dollar per ms, less tempting to re-route since bandwidth cost is becoming more important
        # simply speaking, when we have DOLLAR_PER_MS decreased, less offloading.
        gurobi_model.setObjective(total_latency_sum*DOLLAR_PER_MS + total_egress_sum, gp.GRB.MINIMIZE)
    else:
        logger.error("unsupported objective, ", objective)
        assert False
        
    gurobi_model.update()
    logger.debug(f"{cfg.log_prefix} model objective: {gurobi_model.getObjective()}")

    temp = dict()
    temp = pd.concat([network_load, compute_load], axis=0)
    # concat_df = pd.concat(temp, axis=0)
    # logger.debug("type(concat_df): ", type(concat_df))
    # logger.debug("concat_df.to_dict()")
    # concat_dict = concat_df.to_dict()
    # for k, v in concat_dict.items():
        # logger.debug(f"key: {k}\nvalue: {v}")
    arcs = dict()
    aggregated_load = dict()
    arcs, aggregated_load = gp.multidict(temp.to_dict())
    # if cfg.DISPLAY:
    #     logger.debug("arcs")
    #     logger.debug(f'{arcs}\n')
    #     logger.debug("aggregated_load")
    #     logger.debug(f'{aggregated_load}\n')
    #     logger.debug("aggregated_load")
    #     logger.debug(type(aggregated_load))
    #     for k, v in aggregated_load.items():
    #         logger.debug(f"key: {k}\nvalue: {v}")
    opt_func.log_timestamp("gurobi add_vars and set objective")

    for cid in endpoint_level_rps:
        for svc_name in endpoint_level_rps[cid]:
            for ep in endpoint_level_rps[cid][svc_name]:
                logger.info(f'endpoint_level_rps: {cid}, {svc_name}, {ep}, {endpoint_level_rps[cid][svc_name][ep]}')
    ## Constraint 1: SOURCE
    if cfg.LOAD_IN:
        total_coming = 0
        for cg_key in ep_str_callgraph_table:
            root_ep = opt_func.find_root_node(ep_str_callgraph_table[cg_key])
            root_ep_svc_name = root_ep.split(cfg.ep_del)[0]
            # logger.debug(f'cg_key: {cg_key}')
            for cid in placement:
                if root_ep_svc_name in placement[cid]:
                    # logger.debug(f'endpoint_level_rps[{cid}][{root_ep_svc_name}]')
                    # logger.debug(f'[{root_ep}]: {endpoint_level_rps[cid][root_ep_svc_name][root_ep]}')
                    logger.debug(f"endpoint_level_rps[{cid}]: {endpoint_level_rps[cid]}")
                    try:
                        incoming = endpoint_level_rps[cid][root_ep_svc_name][root_ep]
                    except Exception as e:
                        logger.error(f'endpoint_level_rps,{cid},{root_ep_svc_name},{root_ep}')
                        logger.error(f'Exception: {type(e).__name__}, {e}')
                        assert False
                    # incoming += endpoint_level_inflight_req[cid][root_ep_svc_name][root_ep]
                    # logger.debug(f"incoming: {incoming}")
                    total_coming += incoming
                    # ingress_gw_start_node = f'{svc}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'
                    node_name = f'{root_ep}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'
                    # logger.debug(f'node_name: {node_name}')
                    lh = gp.quicksum(aggregated_load.select('*', node_name))
                    rh = incoming
                    gurobi_model.addConstr((lh == rh), name="cluster_"+str(cid)+"_load_in_"+str(root_ep))
                    constraint_file.write(f'{lh}\n')
                    constraint_file.write("==\n")
                    constraint_file.write(f'{rh}\n')
                    constraint_file.write("-"*80)
                    constraint_file.write("\n")
                    # logger.debug(lh)
                    # logger.debug("==")
                    # logger.debug(rh)
                    # logger.debug("-"*80)
        # logger.debug("*"*80)
        # logger.debug(aggregated_load.select(opt_func.source_node_fullname, '*'))
        # logger.debug("==")
        # logger.debug(total_coming)
        gurobi_model.addConstr((gp.quicksum(aggregated_load.select(opt_func.source_node_fullname, '*')) == total_coming), name="source")
        gurobi_model.update()

    ## Constraint 2: destination
    # destination = dict()
    # destination[opt_func.destination_node_fullname] = MAX_LOAD
    # dest_keys = destination.keys()
    # leaf_services = list()
    # for parent_svc, children in callgraph.items():
    #     if len(children) == 0: # leaf service
    #         leaf_services.append(parent_svc)
    # num_leaf_services = len(leaf_services)
    # logger.debug(f"{cfg.log_prefix} num_leaf_services: {num_leaf_services}")
    # logger.debug(f"{cfg.log_prefix} leaf_services: {leaf_services}")
    # dst_flow = gurobi_model.addConstrs((gp.quicksum(aggregated_load.select('*', dst)) == destination[dst]*num_leaf_services for dst in dest_keys), name="destination")
    # for dst in dest_keys:
    #     logger.debug(aggregated_load.select('*', dst))
    # gurobi_model.update()

    ## Constraint 3: flow conservation
    # Start node in-out flow conservation
    for cid in endpoint_level_rps:
        for svc_name in endpoint_level_rps[cid]:
            for ep_str in endpoint_level_rps[cid][svc_name]:
                # start_node = f'{ep_str}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'
                start_node = opt_func.get_start_node_name(ep_str, cid)
                lh = gp.quicksum(aggregated_load.select('*', start_node))
                rh = gp.quicksum(aggregated_load.select(start_node, '*'))
                gurobi_model.addConstr((lh == rh), name="flow_conservation-start_node-"+ep_str)
                constraint_file.write(f'{lh}\n')
                constraint_file.write("==\n")
                constraint_file.write(f'{rh}\n')
                constraint_file.write("-"*80)
                constraint_file.write("\n")
                # logger.debug(lh)
                # logger.debug("==")
                # logger.debug(rh)
                # logger.debug("-"*50)
    gurobi_model.update()

    # End node in-out flow conservation
    # case 1 (leaf node to destination): incoming num requests == outgoing num request for all nodes
    # for parent_svc, children in callgraph.items():
    #     for cid in range(len(NUM_REQUESTS)):
    #         if len(children) == 0: # leaf_services:
    #             end_node = parent_svc + cfg.DELIMITER + str(cid) + cfg.DELIMITER + "end"
    #             node_flow = gurobi_model.addConstr((gp.quicksum(aggregated_load.select('*', end_node)) == gp.quicksum(aggregated_load.select(end_node, '*'))), name="flow_conservation["+end_node+"]-leaf_endnode")
    #             logger.debug("*"*50)
    #             logger.debug(aggregated_load.select('*', end_node))
    #             logger.debug('==')
    #             logger.debug(aggregated_load.select(end_node, '*'))
    #             logger.debug("-"*50)
    #             logger.debug("*"*50)

    # case 2 
    # For non-leaf node and end node, incoming to end node == sum of outgoing
    for cg_key in ep_str_callgraph_table:
        for parent_ep in ep_str_callgraph_table[cg_key]:
            children_ep = ep_str_callgraph_table[cg_key][parent_ep]
            # non-leaf node will only have child
            for parent_cid in endpoint_to_placement[parent_ep]:
                for child_ep in children_ep:
                    logger.debug(f'child_ep: {child_ep}')
                    end_node = opt_func.get_end_node_name(parent_ep, parent_cid)
                    logger.debug(f'non-leaf end_node: {end_node}')
                    outgoing_sum = 0
                    for child_cid in endpoint_to_placement[child_ep]:
                        child_start_node = opt_func.get_start_node_name(child_ep, child_cid)
                        outgoing_sum += aggregated_load.sum(end_node, child_start_node)
                    # if traffic_segmentation:
                        # lh = gp.quicksum(aggregated_load.select('*', end_node))*request_in_out_weight[cg_key][parent_svc][child_svc]
                    # else:
                    #     lh = gp.quicksum(aggregated_load.select('*', end_node))*merged_in_out_weight[parent_svc][child_svc]
                    
                    # try:
                    logger.debug(f'request_in_out_weight: {request_in_out_weight}')
                    lh = gp.quicksum(aggregated_load.select('*', end_node))*request_in_out_weight[cg_key][parent_ep][child_ep]
                    rh = outgoing_sum
                    gurobi_model.addConstr((lh == rh), name="flow_conservation-nonleaf_endnode-"+cg_key)
                    constraint_file.write(f'{lh}\n')
                    constraint_file.write("==\n")
                    constraint_file.write(f'{rh}\n')
                    constraint_file.write("-"*80)
                    constraint_file.write("\n")
                    # logger.debug(lh)
                    # logger.debug('==')
                    # logger.debug(rh)
                    # logger.debug("-"*80)
                    # except Exception as e:
                    #     logger.error(f'Error: {e}')
                    #     assert False
    gurobi_model.update()

    '''
    This constraint also seems redundant.
    The optimizer output varies with and without this constraint. The reason is assumed that there are multiple optimal solutions and how it searches the optimal solution (e.g., order of search exploration) changes with and without this constraint.
    It will be commented out anyway since it it not necessary constraint.
    '''
    ## Constraint 4: Tree topology
    # svc_to_cid = opt_func.svc_to_cid(placement)
    # logger.debug("svc_to_cid: ", svc_to_cid)
    # for key in callgraph:
    #     for svc_name in svc_to_cid:
    #         if svc_name != cfg.ENTRANCE and svc_name in callgraph[key]:
    #             incoming_sum = 0
    #             for cid in svc_to_cid[svc_name]:
    #                 start_node = opt_func.start_node_name(svc_name, cid)
    #                 incoming_sum += aggregated_load[key].sum('*', start_node)
    #             node_flow = gurobi_model.addConstr(incoming_sum == MAX_LOAD[key], name="tree_topo_conservation_"+key)
    #             if cfg.DISPLAY:
    #                 logger.debug(incoming_sum)
    #                 logger.debug('==')
    #                 logger.debug(MAX_LOAD[key])
    #                 logger.debug("-"*50)
    # gurobi_model.update()


    # # Constraint 5: max throughput of service
    # max_tput = dict()
    # for cid in range(len(NUM_REQUESTS)):
    #     for svc_name in placement[cid]:
    #         max_tput[svc_name+cfg.DELIMITER+str(cid)+cfg.DELIMITER+"start"] = MAX_LOAD
    #         max_tput[svc_name+cfg.DELIMITER+str(cid)+cfg.DELIMITER+"end"] = MAX_LOAD
    # logger.debug(f"{cfg.log_prefix} max_tput: {max_tput}")
    # max_tput_key = max_tput.keys()
    # throughput = gurobi_model.addConstrs((gp.quicksum(aggregated_load.select('*', n_)) <= max_tput[n_] for n_ in max_tput_key), name="service_capacity")
    # constraint_setup_end_time = time.time()

    opt_func.log_timestamp("gurobi add constraints and model update")
    gurobi_model.update()
    # opt_func.print_gurobi_var(gurobi_model)
    # opt_func.print_gurobi_constraint(gurobi_model)
    gurobi_model.setParam('NonConvex', 2)
    ts = time.time()
    gurobi_model.optimize()
    solver_runtime = time.time() - ts
    opt_func.log_timestamp("MODEL OPTIMIZE")

    ## Not belonging to optimizer critical path
    ts = time.time()
    varInfo = [(v.varName, v.LB, v.UB) for v in gurobi_model.getVars() ]
    df_var = pd.DataFrame(varInfo) # convert to pandas dataframe
    df_var.columns=['Variable Name','LB','UB'] # Add column headers
    num_var = len(df_var)
    constrInfo = [(c.constrName, gurobi_model.getRow(c), c.Sense, c.RHS) for c in gurobi_model.getConstrs() ]
    df_constr = pd.DataFrame(constrInfo)
    df_constr.columns=['Constraint Name','Constraint equation', 'Sense','RHS']
    num_constr = len(df_constr)
    df_var.to_csv(f'variable.csv')
    df_constr.to_csv(f'constraint.csv')
    substract_time = time.time() - ts
    opt_func.log_timestamp("get var and constraint")
    if gurobi_model.Status != GRB.OPTIMAL:
        logger.info(f"XXXXXXXXXXXXXXXXXXXXXXXXXXX")
        logger.info(f"XXXX INFEASIBLE MODEL! XXXX")
        logger.info(f"XXXXXXXXXXXXXXXXXXXXXXXXXXX")
        if cfg.DISPLAY:
            logger.debug(df_constr)
        gurobi_model.computeIIS()
        gurobi_model.write("gurobi_model.ilp")
        logger.error('\nThe following constraints and variables are in the IIS:')
        # for c in gurobi_model.getConstrs():
        #     if c.IISConstr: logger.debug(f'\t{c.constrname}: {gurobi_model.getRow(c)} {c.Sense} {c.RHS}')
        for v in gurobi_model.getVars():
            if v.IISLB: logger.error(f'\t{v.varname} ≥ {v.LB}')
            if v.IISUB: logger.error(f'\t{v.varname} ≤ {v.UB}')
        logger.info(f'FAIL: INFEASIBLE MODEL')
        return pd.DataFrame(), "reason: infeasible model"
    else:
        logger.debug(f"ooooooooooooooooooooooo")
        logger.debug(f"oooo SOLVED MODEL! oooo")
        logger.debug(f"ooooooooooooooooooooooo")
        request_flow = pd.DataFrame(columns=["From", "To", "Flow"])
        for arc in arcs:
            if aggregated_load[arc].x > 1e-6:
                temp = pd.DataFrame({"From": [arc[0]], "To": [arc[1]], "Flow": [aggregated_load[arc].x]})
                request_flow = pd.concat([request_flow, temp], ignore_index=True)
        request_flow.to_csv(f'request_flow.csv')
        logger.debug("asdf request_flow")
        logger.debug(request_flow)
        percentage_df = opt_func.translate_to_percentage(request_flow)
        percentage_df.to_csv(f'percentage_df.csv')
        logger.debug("asdf percentage_df")
        logger.debug(percentage_df)
        # opt_func.plot_callgraph_request_flow(percentage_df, network_arc_var_name)
        logger.info(f'Successful run')
        logger.warning(f"solver runtime: {solver_runtime}")
        return percentage_df, "model solved"


        '''
        Post this line, it is not a part of optimization. It analyzes latency and cost difference between traffic segmentation and non-traffic segmentation.
        '''
        
        ##
        def update_flow(cur_node, cur_node_cid, inout_weight, cg, actual_req_flow_df, p_df, NUM_REQ, key, incoming_flow):
            if cur_node == opt_func.source_node_name:
                for index, row in p_df.iterrows():
                    if row["src"] == opt_func.source_node_name:
                        new_flow = 0
                        new_flow += NUM_REQ[row['dst_cid']][key]
                        logger.debug(f'update_flow, {tup_index_to_str_index(row)},  new_flow: {new_flow}')
                        actual_req_flow_df.loc[tup_index_to_str_index(row), "flow"] += new_flow
                        update_flow(row['dst'], row['dst_cid'], inout_weight, cg, actual_req_flow_df, p_df, NUM_REQ, key, incoming_flow=new_flow)
            else:
                if len(cg[cur_node]) == 0:
                    return
                for child in cg[cur_node]:
                    for index, row in p_df.iterrows():
                        if row['src'] == cur_node and row['dst'] == child and row['src_cid'] == cur_node_cid:
                            new_flow = incoming_flow * inout_weight[row["src"]][row["dst"]]*row['weight']
                            str_index = tup_index_to_str_index(row)
                            logger.debug(f'update_flow, {str_index}, incoming_flow: {incoming_flow} new_flow: {round(new_flow, 1)}')
                            actual_req_flow_df.loc[str_index, "flow"] += new_flow
                            update_flow(row['dst'], row['dst_cid'], inout_weight, cg, actual_req_flow_df, p_df,  NUM_REQ, key, incoming_flow=new_flow)
                                        
        def update_actual_flow(inout_weight, p_df, cg, actual_req_flow_df, NUM_REQ, key):
            # root_node = opt_func.find_root_node(cg, key)
            root_node = opt_func.source_node_name
            update_flow(root_node, -1, inout_weight, cg, actual_req_flow_df, p_df, NUM_REQ, key, 0)
        for key in request_in_out_weight:
            logger.debug(f'request_in_out_weight[{key}]: {request_in_out_weight[key]}')
            logger.debug(f'norm_inout_weight[{key}]: {norm_inout_weight[key]}\n')
        logger.debug(f'merged_in_out_weight: {merged_in_out_weight}\n')
        
        def tup_index_to_str_index(row):
            return f"{row['src']}, {row['src_cid']}, {row['dst']}, {row['dst_cid']}"
        
        if traffic_segmentation == False:
            assert len(percentage_df) == 1
            for key in percentage_df:
                assert key == merged_cg_key
                new_index = list()
                for index, row in percentage_df[key].iterrows():
                    new_index.append(tup_index_to_str_index(row))
                # logger.debug(f'new_index: {new_index}')
            actual_request_flow_df = dict()
            for key in original_request_in_out_weight:
                actual_request_flow_df[key] = pd.DataFrame(columns=percentage_df[merged_cg_key].columns, index=new_index)
                for index, row in percentage_df[merged_cg_key].iterrows():
                    actual_request_flow_df[key].loc[tup_index_to_str_index(row)] = [row["src"], row["dst"], row["src_cid"], row["dst_cid"], 0, 0, row["weight"]]
                # update_actual_flow(request_in_out_weight[key], percentage_df, callgraph, key, actual_request_flow_df)
                logger.debug(original_request_in_out_weight)
                update_actual_flow(original_request_in_out_weight[key], percentage_df[merged_cg_key], original_callgraph[key], actual_request_flow_df[key], original_NUM_REQUESTS, key)
                logger.debug(f'percentage_df[{merged_cg_key}]')
                logger.debug(percentage_df[merged_cg_key])
                logger.debug(f'actual_request_flow_df[{key}]')
                logger.debug(actual_request_flow_df[key])
                
        if traffic_segmentation == True and len(request_in_out_weight) > 1:
            concat_df = pd.DataFrame()
            for key in callgraph:
                if concat_df.empty:
                    concat_df = percentage_df[key]
                    continue
                concat_df = pd.concat([concat_df, percentage_df[key]], axis=0,  ignore_index=True)
            for index, row in concat_df.iterrows():
                concat_df.loc[index, "merge_col_1"] = f"{row['src']},{row['src_cid']},{row['dst']}"
                concat_df.loc[index, "merge_col_2"] = f"{row['src']},{row['src_cid']},{row['dst']},{row['dst_cid']}"
            another_group_by_df = concat_df.groupby(['merge_col_2']).sum()
            for index, row in another_group_by_df.iterrows():
                another_group_by_df.at[index, "src"] = index.split(",")[0]
                another_group_by_df.at[index, "src_cid"] = int(index.split(",")[1].split(".")[0])
                another_group_by_df.at[index, "dst"] = index.split(",")[2]
                another_group_by_df.at[index, "dst_cid"] = int(index.split(",")[3].split(".")[0])
                another_group_by_df.at[index, "weight"] = row["flow"]/row["total"]
            logger.debug("another_group_by_df")
            logger.debug(another_group_by_df)
            
        if cfg.PLOT:
            cg_keys = callgraph.keys()
            opt_func.plot_callgraph_request_flow(percentage_df, cg_keys, workload, network_arc_var_name)
            if traffic_segmentation == False:
                cg_keys = actual_request_flow_df.keys()
                opt_func.plot_callgraph_request_flow(actual_request_flow_df, cg_keys, workload, network_arc_var_name)
            # else:
            #     opt_func.plot_callgraph_request_flow(actual_request_flow_df, cg_keys, workload, network_arc_var_name)
        if cfg.PLOT and cfg.PLOT_ALL:
            # NOTE: It plots latency function of call graph "A"
            opt_func.plot_latency_function_2d(compute_df, callgraph, "A")
            opt_func.plot_full_arc(compute_arc_var_name, network_arc_var_name, callgraph)
            # for key in callgraph:
            #     opt_func.plot_arc_var_for_callgraph(network_arc_var_name, placement, callgraph, key)
            opt_func.plot_merged_request_flow(another_group_by_df, workload, network_arc_var_name)
            for key in callgraph:
                opt_func.plot_callgraph_request_flow(percentage_df, key, workload, network_arc_var_name)
        # opt_func.print_all_gurobi_var(gurobi_model)
        lat_ret = dict()
        cost_ret = dict()
        for key in callgraph:
            lat_ret[key] = dict()
            lat_ret[key]["compute"] = 0
            lat_ret[key]["network"] = 0
            cost_ret[key] = 0
        for key in callgraph:
            assert compute_latency[key].keys().all() == compute_load[key].keys().all()
            assert network_latency[key].keys().all() == network_load[key].keys().all()
            for k, v in compute_latency[key].items():
                # logger.debug(f'compute_latency[{key}][{k}]: {round(compute_latency[key][k].getAttr("X"), 1)}')
                # logger.debug(f'compute_load[{key}][{k}]: {round(compute_load[key][k].getAttr("X"), 1)}')
                # logger.debug(f'{compute_latency[key][k].getAttr("X")*compute_load[key][k].getAttr("X")}')
                lat_ret[key]["compute"] += compute_latency[key][k].getAttr("X")*compute_load[key][k].getAttr("X")
            for k, v in network_latency[key].items():
                # logger.debug(f'network_latency[{key}][{k}]: {round(network_latency[key][k].getAttr("X"), 1)}')
                # logger.debug(f'network_load[{key}][{k}]: {round(network_load[key][k].getAttr("X"), 1)}')
                # logger.debug(f'{network_latency[key][k].getAttr("X")*network_load[key][k].getAttr("X")}')
                lat_ret[key]["network"] += network_latency[key][k].getAttr("X")*network_load[key][k].getAttr("X")
            for k, v in network_egress_cost[key].items():
                # logger.debug(f'network_egress_cost[{key}][{k}]: {round(network_egress_cost[key][k].getAttr("X"), 1)}')
                # logger.debug(f'network_load[{key}][{k}]: {round(network_load[key][k].getAttr("X"), 1)}')
                # logger.debug(f'{round(network_egress_cost[key][k].getAttr("X")*network_load[key][k].getAttr("X"), 1)}')
                cost_ret[key] += network_egress_cost[key][k].getAttr("X")*network_load[key][k].getAttr("X")
        total_lat = dict()
        sum_total_lat = dict()
        for key in lat_ret:
            total_lat[key] = 0
            for k, v in lat_ret[key].items(): # k: compute or network
                logger.debug(f"{key}: {k}: {round(v,1)}")
                total_lat[key] += v
                if k not in sum_total_lat:
                    sum_total_lat[k] = 0
                sum_total_lat[k] += v
            if MAX_LOAD[key] != 0:
                logger.debug(f"{key}: total_avg_latency: {round(total_lat[key], 1)}")
                logger.debug(f"{key}: avg_latency: {round(total_lat[key]/MAX_LOAD[key], 1)}")
            else:
                logger.debug(f"{key}: total: {total_lat[key]}, MAX_LOAD[{key}] is 0")
            logger.debug(f'{key}: total_egress_cost: {round(cost_ret[key], 1)}\n')
        all_total_e_cost = 0
        all_total_lat = 0
        for key in lat_ret:
            all_total_lat += total_lat[key]
            all_total_e_cost += cost_ret[key]
        for k in sum_total_lat:
            logger.debug(f"sum_total_lat: {k}: {round(sum_total_lat[k], 1)}")
        logger.debug(f"all_total_avg_lat: {round(all_total_lat, 1)}")
        logger.debug(f"all_avg_lat: {round(all_total_lat/sum(MAX_LOAD.values()), 1)}")
        logger.debug(f"all_total_e_cost: {round(all_total_e_cost, 1)}")
        logger.debug()
        logger.debug(f"model.objVal: {round(gurobi_model.objVal, 1)}")
        logger.debug('*'*70)
        if traffic_segmentation == False:
            act_tot_network_latency = dict()
            for key in actual_request_flow_df:
                # logger.debug(actual_request_flow_df[key])
                act_tot_network_latency[key] = 0
                for index, row in actual_request_flow_df[key].iterrows():
                    # avg_oneway_network_latency = opt_func.get_network_latency(row['src_cid'], row['dst_cid']) * row['flow']
                    avg_oneway_network_latency = inter_cluster_latency[row['src_cid']][row['dst_cid']] * row['flow']
                    avg_twoway_network_latency = avg_oneway_network_latency * 2
                    act_tot_network_latency[key] += avg_twoway_network_latency
            group_by_df = dict()
            for key in actual_request_flow_df:
                # logger.debug(actual_request_flow_df[key])
                temp_df = actual_request_flow_df[key].drop(columns=['src', 'src_cid', 'total', 'weight'])
                group_by_df[key] = temp_df.groupby(["dst", "dst_cid"]).sum()
                group_by_df[key] = group_by_df[key].reset_index()
                # logger.debug(group_by_df[key])
            act_tot_compute_avg_lat = dict()
            for key in group_by_df:
                act_tot_compute_avg_lat[key] = 0
                for index, row in group_by_df[key].iterrows():
                    data = dict()
                    data["observed_x_"+key] = [row["flow"]]
                    for key2 in group_by_df:
                        if key2 != key:
                            for index2, row2 in group_by_df[key2].iterrows():
                                if row2["dst"] == row["dst"] and row2["dst_cid"] == row["dst_cid"]:
                                    data["observed_x_"+key2] = [row2["flow"]]
                                    break
                    temp_df = pd.DataFrame(data=data)
                    # logger.debug(f'{row["dst"]}, {row["dst_cid"]}')
                    # logger.debug(temp_df)
                    idx = opt_func.get_compute_arc_var_name(row["dst"], row["dst_cid"])
                    lat_f = original_compute_df.loc[[idx]]["latency_function_"+key].tolist()[0]
                    # logger.debug(lat_f)
                    pred = lat_f.predict(temp_df)
                    # logger.debug(f'pred: {pred}')
                    act_tot_compute_avg_lat[key] += (pred[0] * group_by_df[key].loc[index, "flow"])
                    logger.debug(f'{key}, {row["dst"]}, cid, {row["dst_cid"]}: {round(pred[0] * group_by_df[key].loc[index, "flow"], 1)} = {round(pred[0], 1)} x {round(group_by_df[key].loc[index, "flow"], 1)}')
            act_tot_avg_lat = dict()
            for key in act_tot_compute_avg_lat:
                act_tot_avg_lat[key] = act_tot_compute_avg_lat[key] + act_tot_network_latency[key]
            for key in act_tot_avg_lat:
                logger.debug(f'{key}: compute: {round(act_tot_compute_avg_lat[key], 1)}')
                logger.debug(f'{key}: network: {round(act_tot_network_latency[key], 1)}')
                logger.debug(f'{key}: sum: {round(act_tot_avg_lat[key], 1)}')
                logger.debug(f'{key}: avg latency: {round(act_tot_avg_lat[key]/original_MAX_LOAD[key], 1)}')
                logger.debug(f'{key}: egress cost: ')
                logger.debug()
            logger.debug(f'sum_total_lat: compute: {round(sum(act_tot_compute_avg_lat.values()), 1)}')
            logger.debug(f'sum_total_lat: network: {round(sum(act_tot_network_latency.values()), 1)}')
            logger.debug(f'all_total_avg_lat: {round(sum(act_tot_avg_lat.values()), 1)}')
            logger.debug(f'all_avg_lat: {round(sum(act_tot_avg_lat.values())/sum(original_MAX_LOAD.values()), 1)}')
            logger.debug(f'all_total_e_cost: ')
''' END of run_optimizer function'''