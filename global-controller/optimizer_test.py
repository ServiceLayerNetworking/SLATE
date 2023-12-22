#!/usr/bin/env python
# coding: utf-8

# In[31]:
import sys
sys.dont_write_bytecode = True

import time
import numpy as np  
import pandas as pd
import gurobipy as gp
from gurobipy import GRB
import random
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.preprocessing import StandardScaler
from sklearn.compose import make_column_transformer
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from sklearn.metrics import r2_score
import gurobipy_pandas as gppd
from gurobi_ml import add_predictor_constr
from IPython.display import display
from global_controller import app
import time_stitching as tst
import config as cfg
import span as sp
import optimizer_header as opt_func
import os
from IPython.display import display
import itertools

random.seed(1234)

'''
For interactive run with jupyternotebook, comment out following lines "COMMENT_OUT_FOR_JUPYTER".
And adjust the indentation accordingly.
'''

# pre_recorded_trace is simply a list of spans?
def run_optimizer(pre_recorded_trace, per_endpoint_load, per_cluster_per_endpoint_load, placement, callgraph, root_endpoint):
    if not os.path.exists(cfg.OUTPUT_DIR):
        os.mkdir(cfg.OUTPUT_DIR)
        print(f"{cfg.log_prefix} mkdir {cfg.OUTPUT_DIR}")
        
    traffic_segmentation = 1
    objective_function = "avg_latency" # avg_latency, end_to_end_latency, multi_objective, egress_cost
    
    request_in_out_weight = dict() # This is used in flow_conservation-nonleaf_endnode constraint
    for cid in per_endpoint_load:
        for endpoint in per_endpoint_load[cid]:
            if endpoint not in request_in_out_weight:
                request_in_out_weight[endpoint] = dict()
            request_in_out_weight[endpoint] = per_endpoint_load[endpoint]/per_endpoint_load[root_endpoint]
    
    norm_inout_weight = dict() # NOTE: not being used anywhere. it is redundant
    for key in request_in_out_weight:
        norm_inout_weight[key] = opt_func.norm(request_in_out_weight[key])
    merged_in_out_weight = opt_func.merge(request_in_out_weight, norm_inout_weight, MAX_LOAD)
    norm_merged_in_out_weight = opt_func.norm(merged_in_out_weight)
    
    if traffic_segmentation == False:
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
        
    opt_func.print_setup()

    if len(placement) != len(NUM_REQUESTS):
        print(f'len(placement)({len(placement)}) != len(NUM_REQUESTS)({len(NUM_REQUESTS)})')
        assert False
        
    if len(callgraph) != len(request_in_out_weight):
        print(f'len(callgraph)({len(callgraph)}) != len(request_in_out_weight)({len(request_in_out_weight)})')
        assert False
            
    assert len(placement) == len(NUM_REQUESTS)

    # In[31]:

    # key: cg key, value: dict of {svc: depth}
    depth_dict = opt_func.get_depth_dict(callgraph)
    print(f'depth_dict: {depth_dict}')
    # key: (parent_svc,child_svc), value: callsize of the link (= depth+1)
    callsize_dict = opt_func.get_callsize_dict(callgraph, depth_dict)
    print(f'callsize_dict: {callsize_dict}')


    # In[31]:

    compute_df = opt_func.create_compute_df(placement, callgraph, callsize_dict, NUM_REQUESTS, MAX_LOAD)
    display(compute_df)
    if traffic_segmentation == False:
        original_compute_df = opt_func.create_compute_df(placement, original_callgraph, callsize_dict, original_NUM_REQUESTS, original_MAX_LOAD)
        # display(original_compute_df)


    # In[42]:

    gurobi_model = gp.Model('RequestRouting')

    compute_latency = dict()
    compute_load = dict()
    for key in callgraph:
        compute_latency[key] = gppd.add_vars(gurobi_model, compute_df, name="compute_latency_"+key, lb="min_compute_latency_"+key)
    for key in callgraph:
        # compute_load[key] = gppd.add_vars(gurobi_model, compute_df, name="load_for_compute_edge_"+key, lb="min_load_"+key, ub="max_load_"+key)
        compute_load[key] = gppd.add_vars(gurobi_model, compute_df, name="load_for_compute_edge_"+key)
    gurobi_model.update()


    # In[44]:


    for index, row in compute_df.iterrows():
        data = dict()
        for key in callgraph:
            data["observed_x_"+key] = compute_load[key][index]
        m_feats = pd.DataFrame(
            data=data,
            index=[index]
        )
        for key in callgraph:
            print(f'callgraph key: {key}')
            print(f'{row["svc_name"]}')
            print(f'index: {index}')
            print(f'm_feats: {m_feats}')
            print(f'{compute_latency[key][index]}')
            print(f'{row["latency_function_"+key]}')
            print()
            # (gurobi_model, regression model, x, y)
            pred_constr = add_predictor_constr(gurobi_model, row["latency_function_"+key], m_feats, compute_latency[key][index])
    gurobi_model.update()


    # In[44]:


    ## Define names of the variables for network arc in gurobi
    network_arc_var_name = opt_func.create_network_arc_var_name(placement, callgraph)
    opt_func.check_network_arc_var_name(network_arc_var_name)


    # In[36]:


    columns=["src_svc", "src_cid", "dst_svc", "dst_cid", "min_network_time", "max_network_time"]
    for key in callgraph:
        columns.append("max_load_"+key)
    for key in callgraph:
        columns.append("min_load_"+key)
    for key in callgraph:
        columns.append("min_egress_cost_"+key)
    for key in callgraph:
        columns.append("max_egress_cost_"+key)
    network_df = pd.DataFrame(
        columns=columns,
        data={
        },
        index=network_arc_var_name
    )
    if cfg.DISPLAY: display(network_df)


    # In[36]:


    src_svc_list = list()
    dst_svc_list = list()
    src_cid_list = list()
    dst_cid_list = list()
    min_network_time_list = list()
    max_network_time_list = list()
    min_egress_cost_list = list()
    max_egress_cost_list = list()
    call_size_list = list()
    for var_name in network_arc_var_name:
        # print(var_name)
        if type(var_name) == tuple:
            src_svc = var_name[0].split(cfg.DELIMITER)[0]
            dst_svc = var_name[1].split(cfg.DELIMITER)[0]
            src_cid = int(var_name[0].split(cfg.DELIMITER)[1])
            dst_cid = int(var_name[1].split(cfg.DELIMITER)[1])
        else:
            print("var_name MUST be tuple datatype")
            assert False
        src_svc_list.append(src_svc)
        dst_svc_list.append(dst_svc)
        src_cid_list.append(src_cid)
        dst_cid_list.append(dst_cid)
        n_time = opt_func.get_network_latency(src_cid, dst_cid)
        min_network_time_list.append(n_time)
        max_network_time_list.append(n_time)
        e_cost = opt_func.get_egress_cost(src_cid, src_svc, dst_svc, dst_cid, callsize_dict)
        min_egress_cost_list.append(e_cost)
        max_egress_cost_list.append(e_cost)
        
    network_df["src_svc"] = src_svc_list
    network_df["dst_svc"] = dst_svc_list
    network_df["src_cid"] = src_cid_list
    network_df["dst_cid"] = dst_cid_list
    network_df["min_network_time"] = min_network_time_list
    network_df["max_network_time"] = max_network_time_list
    for index, row in network_df.iterrows():
        for key in callgraph:
            # if this network arc is in the callgraph
            if row["src_svc"] in callgraph[key] and row["dst_svc"] in callgraph[key][row["src_svc"]]:
                network_df.at[index, 'max_load_'+key] = MAX_LOAD[key]
            else:
                if row["src_svc"] == opt_func.source_node_name:
                    network_df.at[index, 'max_load_'+key] = MAX_LOAD[key]
                else:
                    network_df.at[index, 'max_load_'+key] = 0
            network_df.at[index, 'min_load_'+key] = 0
    for key in callgraph:
        network_df["min_egress_cost_"+key] = min_egress_cost_list
        network_df["max_egress_cost_"+key] = max_egress_cost_list


    # In[44]:




    network_latency = dict()
    for key in callgraph:
        network_latency[key] = gppd.add_vars(gurobi_model, network_df, name="network_latency_"+key, lb="min_network_time", ub="max_network_time")
    network_load = dict()
    for key in callgraph:
        # network_load[key] = gppd.add_vars(gurobi_model, network_df, name="load_for_network_edge_"+key, lb="min_load_"+key, ub="max_load_"+key)
        network_load[key] = gppd.add_vars(gurobi_model, network_df, name="load_for_network_edge_"+key)

    network_egress_cost = dict()
    for key in callgraph:
        network_egress_cost[key] = gppd.add_vars(gurobi_model, network_df, name="network_egress_cost", lb="min_egress_cost_"+key, ub="max_egress_cost_"+key)
        
    gurobi_model.update()


        

    # In[44]:



    # if objective_function == "avg_latency":
    network_latency_sum = 0
    compute_latency_sum = 0
    for key in callgraph:
        network_latency_sum += sum(network_latency[key].multiply(network_load[key]))
        compute_latency_sum += sum(compute_latency[key].multiply(compute_load[key]))
    total_latency_sum = network_latency_sum + compute_latency_sum

    # if objective_function == "egress_cost":
    network_egress_cost_sum = 0
    for key in callgraph:
        network_egress_cost_sum += sum(network_egress_cost[key].multiply(network_load[key]))
    # compute_egress_cost = dict()
    # compute_egress_cost = gppd.add_vars(gurobi_model, compute_df, name="compute_egress_cost", lb="min_egress_cost", ub="max_egress_cost")
    # compute_egress_cost_sum = sum(compute_egress_cost.multiply(compute_load))
    # print("compute_egress_cost_sum")
    # print(compute_egress_cost_sum)

    ## compute edge egress cost is always 0
    # total_egress_sum = network_egress_cost_sum + compute_egress_cost_sum
    total_egress_sum = network_egress_cost_sum
    gurobi_model.update()
        
    if objective_function == "end_to_end_latency":
        svc_order = dict()
        for key in callgraph:
            assert key not in svc_order
            svc_order[key] = dict()
            opt_func.get_svc_order(callgraph, key, "ingress_gw", svc_order, idx=0)
        for key in svc_order:
            print(f'svc_order[{key}]: {svc_order[key]}')

        svc_to_placement = dict()
        all_combinations = dict()
        new_all_combinations = dict()
        for key in callgraph:
            svc_to_placement[key] = opt_func.svc_to_cid(svc_order[key], placement)
            print(f'svc_to_placement[{key}]: {svc_to_placement[key]}')
            all_combinations[key] = list(itertools.product(*svc_to_placement[key]))
            new_all_combinations[key] = opt_func.remove_too_many_cross_cluster_routing_path(all_combinations[key], 1)
            # for comb in new_all_combinations[key]:
            #     print(f'comb: {comb}')
            #     break
            
        assert svc_order.keys() == new_all_combinations.keys()

        root_node = dict()
        for key in callgraph:
            root_node[key] = opt_func.find_root_node(callgraph, "A")
        print(f'root_node: {root_node}')

        unpack_list = dict()
        for key in callgraph:
            unpack_list[key] = list()
            opt_func.unpack_callgraph(callgraph, key, root_node[key], unpack_list[key])
        for key in unpack_list:
            print(f'unpack_list[{key}]: {unpack_list[key]}')

        print()
        path_dict = dict()
        for key in svc_order:
            path_dict[key] = dict()
            for comb in new_all_combinations[key]:
                # return type of create_path: list (path is a list)
                path = opt_func.create_path(svc_order[key], comb, unpack_list[key], callgraph, key)
                path_dict[key][comb] = path

        print()
        for key in path_dict:
            for comb, path in path_dict[key].items():
                print(f'{comb} path in path_dict[{key}]')
                for pair in path:
                    print(f'{pair}')
                print()
            
        possible_path = dict()
        for key in callgraph:
            possible_path[key] = dict()
            for comb in new_all_combinations[key]:
                print(f'key: {key}, comb: {comb}')
                possible_path[key][comb] = list()

        print()
        end_to_end_path_var = dict()
        for key in path_dict:
            end_to_end_path_var[key] = dict()
            for comb, path in path_dict[key].items():
                print(f'comb: {comb}')
                # end_to_end_path_var[key][comb] = gurobi_model.addVar(vtype=gp.GRB.CONTINUOUS, name=f'end_to_end_path_var_{key}_{comb}')
                end_to_end_path_var[key][comb] = 0
                for pair in path:
                    if opt_func.is_network_var(pair):
                        try:
                            # print(f'network_latency[{key}][{pair}]: {network_latency[key][pair]}')
                            # end_to_end_path_var[key][comb].append(network_latency[key][pair])
                            end_to_end_path_var[key][comb] += network_latency[key][pair]
                        except Exception as e:
                            print(f'network_latency, key: {key}, pair: {pair}')
                            print(f'Exception: {e}')
                            assert False
                    else:
                        try:
                            # print(f'compute_latency[{key}][{pair}]: {compute_latency[key][pair]}')
                            # end_to_end_path_var[key][comb].append(compute_latency[key][pair])
                            end_to_end_path_var[key][comb] += compute_latency[key][pair]
                            print(f'compute_latency[{key}][{pair}]: {compute_latency[key][pair]}')
                        except Exception as e:
                            print(f'compute_latency[{key}][{pair}]: {compute_latency[key][pair]}')
                            print(f'Exception: {e}')
                            assert False
        gurobi_model.update()
        print()
        for key in end_to_end_path_var:
            for comb in end_to_end_path_var[key]:
                print(f'key: {key}, comb: {comb}')
                # for var in end_to_end_path_var[key][comb]:
                print(f'{end_to_end_path_var[key][comb]}')
                print()
                
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
                print(f'end_to_end_path_var[{key}][{comb}]: {end_to_end_path_var[key][comb]}')
                print(f'<=')
                print(f'max_end_to_end_latency')
        gurobi_model.update()

        print('max_end_to_end_latency')
        print(f'{max_end_to_end_latency}\n')

    # In[44]:

    print("compute_latency_sum:")
    print(f"{compute_latency_sum}\n")

    print("network_latency_sum:")
    print(f"{network_latency_sum}\n")

    print("total_latency_sum:")
    print(f"{total_latency_sum}\n")

    print('total_egress_sum')
    print(f'{total_egress_sum}\n')

    if objective_function == "avg_latency":
        gurobi_model.setObjective(total_latency_sum, gp.GRB.MINIMIZE)
    elif objective_function == "end_to_end_latency":
        gurobi_model.setObjective(max_end_to_end_latency, gp.GRB.MINIMIZE)
    elif objective_function == "egress_cost":
        gurobi_model.setObjective(total_egress_sum, gp.GRB.MINIMIZE)
    elif objective_function == "multi_objective":
        # NOTE: higher dollar per ms, more important the latency
        # DOLLAR_PER_MS: value of latency
        # lower dollar per ms, less tempting to re-route since bandwidth cost is becoming more important
        # simply speaking, when we have DOLLAR_PER_MS decreased, less offloading.
        gurobi_model.setObjective(total_latency_sum*cfg.DOLLAR_PER_MS + total_egress_sum, gp.GRB.MINIMIZE)
    else:
        print("unsupported objective, ", objective_function)
        assert False
        
    gurobi_model.update()
    print(f"{cfg.log_prefix} model objective: {gurobi_model.getObjective()}")


    # In[44]:

    temp = dict()
    for key in callgraph:
        temp[key] = pd.concat([network_load[key], compute_load[key]], axis=0)
    # concat_df = pd.concat(temp, axis=0)
    # print("type(concat_df): ", type(concat_df))
    # print("concat_df.to_dict()")
    # concat_dict = concat_df.to_dict()
    # for k, v in concat_dict.items():
        # print(f"key: {k}\nvalue: {v}")
    # print()
    arcs = dict()
    aggregated_load = dict()
    for key in callgraph:
        arcs[key], aggregated_load[key] = gp.multidict(temp[key].to_dict())
    if cfg.DISPLAY:
        # print("arcs")
        # print(f'{arcs}\n')
        # print("aggregated_load")
        # print(f'{aggregated_load}\n')
        print("aggregated_load")
        # print(type(aggregated_load))
        for key in callgraph:
            for k, v in aggregated_load[key].items():
                print(f"key: {k}\nvalue: {v}")
                print()
        
    opt_func.log_timestamp("gurobi add_vars and set objective")


    # In[45]:

        
    ## Constraint 1: SOURCE
    if cfg.LOAD_IN:
        source = dict()
        for key in callgraph:
            source[key] = dict()
            source[key][opt_func.source_node_fullname] = MAX_LOAD[key]
        for key in callgraph:
            src_keys = source[key].keys()
            src_flow = gurobi_model.addConstrs((gp.quicksum(aggregated_load[key].select(src, '*')) == source[key][src] for src in src_keys), name="source_"+key)
            for cid in placement:
                for svc in placement[cid]:
                    if opt_func.is_ingress_gw(svc, callgraph):
                        ingress_gw_start_node = f'{svc}{cfg.DELIMITER}{cid}{cfg.DELIMITER}start'
                        lh = gp.quicksum(aggregated_load[key].select('*', ingress_gw_start_node))
                        rh = NUM_REQUESTS[cid][key]
                        per_cluster_load_in = gurobi_model.addConstr((lh == rh), name="cluster_"+str(cid)+"_load_in-"+key)
                        if cfg.DISPLAY:
                            print(lh)
                            print("==")
                            print(rh)
                            print("-"*80)
        gurobi_model.update()


    # In[47]:

    ## Constraint 2: destination
    # destination = dict()
    # destination[opt_func.destination_node_fullname] = MAX_LOAD
    # dest_keys = destination.keys()
    # leaf_services = list()
    # for parent_svc, children in callgraph.items():
    #     if len(children) == 0: # leaf service
    #         leaf_services.append(parent_svc)
    # num_leaf_services = len(leaf_services)
    # app.logger.debug(f"{cfg.log_prefix} num_leaf_services: {num_leaf_services}")
    # app.logger.debug(f"{cfg.log_prefix} leaf_services: {leaf_services}")
    # dst_flow = gurobi_model.addConstrs((gp.quicksum(aggregated_load.select('*', dst)) == destination[dst]*num_leaf_services for dst in dest_keys), name="destination")
    # for dst in dest_keys:
    #     print(aggregated_load.select('*', dst))
    # gurobi_model.update()


    # In[47]:

    ## Constraint 3: flow conservation
    # Start node in-out flow conservation
    for key in callgraph:
        for svc in callgraph[key]:
            for cid in placement:
                if svc in placement[cid]:
                    start_node = svc + cfg.DELIMITER + str(cid) + cfg.DELIMITER + "start"
                    lh = gp.quicksum(aggregated_load[key].select('*', start_node))
                    rh = gp.quicksum(aggregated_load[key].select(start_node, '*'))
                    node_flow = gurobi_model.addConstr((lh == rh), name="flow_conservation-start_node-"+key)
                    # if cfg.DISPLAY:
                    print(lh)
                    print("==")
                    print(rh)
                    print("-"*50)
            
            
    # In[47]:


    # End node in-out flow conservation
    # case 1 (leaf node to destination): incoming num requests == outgoing num request for all nodes
    # for parent_svc, children in callgraph.items():
    #     for cid in range(len(NUM_REQUESTS)):
    #         if len(children) == 0: # leaf_services:
    #             end_node = parent_svc + cfg.DELIMITER + str(cid) + cfg.DELIMITER + "end"
    #             node_flow = gurobi_model.addConstr((gp.quicksum(aggregated_load.select('*', end_node)) == gp.quicksum(aggregated_load.select(end_node, '*'))), name="flow_conservation["+end_node+"]-leaf_endnode")
    #             print("*"*50)
    #             print(aggregated_load.select('*', end_node))
    #             print('==')
    #             print(aggregated_load.select(end_node, '*'))
    #             print("-"*50)
    #             print("*"*50)

    # In[47]:


    # case 2 
    # For non-leaf node and end node, incoming to end node == sum of outgoing
    for key in callgraph:
        for parent_svc, children in callgraph[key].items():
            if len(children) > 0: # non-leaf services:
                for parent_cid in placement:
                    if parent_svc in placement[parent_cid]:
                        end_node = opt_func.end_node_name(parent_svc, parent_cid)
                        for child_svc in children:
                            outgoing_sum = 0
                            # child_list = list()
                            for child_cid in placement:
                                if child_svc in placement[child_cid]:
                                    child_start_node = opt_func.start_node_name(child_svc, child_cid)
                                    # child_list.append(child_start_node)
                                    outgoing_sum += aggregated_load[key].sum(end_node, child_start_node)
                            # print(f"request_in_out_weight[{key}][{parent_svc}][{child_svc}]: {request_in_out_weight[key][parent_svc][child_svc]}")
                            
                            # if traffic_segmentation:
                                # lh = gp.quicksum(aggregated_load[key].select('*', end_node))*request_in_out_weight[key][parent_svc][child_svc]
                            if key not in aggregated_load:
                                print(f'key: {key}')
                                print(f'aggregated_load: {aggregated_load} not in aggregated_load')
                                assert False
                            if parent_svc not in request_in_out_weight[key]:
                                print(f'parent_svc: {parent_svc} not in request_in_out_weight[{key}]')
                                print(f'request_in_out_weight: {request_in_out_weight}')
                                assert False
                            if child_svc not in request_in_out_weight[key][parent_svc]:
                                print(f'child_svc: {child_svc} not in request_in_out_weight[{key}][{parent_svc}]')
                                print(f'request_in_out_weight: {request_in_out_weight}')
                                assert False
                            # else:
                            #     lh = gp.quicksum(aggregated_load[key].select('*', end_node))*merged_in_out_weight[parent_svc][child_svc]
                            lh = gp.quicksum(aggregated_load[key].select('*', end_node))*request_in_out_weight[key][parent_svc][child_svc]
                            rh = outgoing_sum
                            node_flow = gurobi_model.addConstr((lh == rh), name="flow_conservation-nonleaf_endnode-"+key)
                            # if cfg.DISPLAY:
                            # print(aggregated_load[key].select('*', end_node))
                            print(lh)
                            print('==')
                            print(rh)
                            # print(outgoing_sum)
                            print("-"*80)
    gurobi_model.update()


    # In[48]:


    '''
    This constraint also seems redundant.
    The optimizer output varies with and without this constraint. The reason is assumed that there are multiple optimal solutions and how it searches the optimal solution (e.g., order of search exploration) changes with and without this constraint.
    It will be commented out anyway since it it not necessary constraint.
    '''
    ## Constraint 4: Tree topology
    # svc_to_cid = opt_func.svc_to_cid(placement)
    # print("svc_to_cid: ", svc_to_cid)
    # for key in callgraph:
    #     for svc_name in svc_to_cid:
    #         if svc_name != cfg.ENTRANCE and svc_name in callgraph[key]:
    #             incoming_sum = 0
    #             for cid in svc_to_cid[svc_name]:
    #                 start_node = opt_func.start_node_name(svc_name, cid)
    #                 incoming_sum += aggregated_load[key].sum('*', start_node)
    #             node_flow = gurobi_model.addConstr(incoming_sum == MAX_LOAD[key], name="tree_topo_conservation_"+key)
    #             if cfg.DISPLAY:
    #                 print(incoming_sum)
    #                 print('==')
    #                 print(MAX_LOAD[key])
    #                 print("-"*50)
    # gurobi_model.update()


    # In[48]:


    # # Constraint 5: max throughput of service
    # max_tput = dict()
    # for cid in range(len(NUM_REQUESTS)):
    #     for svc_name in placement[cid]:
    #         max_tput[svc_name+cfg.DELIMITER+str(cid)+cfg.DELIMITER+"start"] = MAX_LOAD
    #         max_tput[svc_name+cfg.DELIMITER+str(cid)+cfg.DELIMITER+"end"] = MAX_LOAD
    # app.logger.info(f"{cfg.log_prefix} max_tput: {max_tput}")
    # max_tput_key = max_tput.keys()
    # throughput = gurobi_model.addConstrs((gp.quicksum(aggregated_load.select('*', n_)) <= max_tput[n_] for n_ in max_tput_key), name="service_capacity")
    # constraint_setup_end_time = time.time()



    # In[51]:

    opt_func.log_timestamp("gurobi add constraints and model update")

    ## Defining objective function
    gurobi_model.setParam('NonConvex', 2)
    solve_start_time = time.time()
    gurobi_model.update()
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
    # print("options: ", options)
    env = gp.Env(params=options)
    gp.Model(env=env)
    gurobi_model.optimize()
    solve_end_time = time.time()
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
    if cfg.OUTPUT_WRITE:
        df_var.to_csv(cfg.OUTPUT_DIR+"/variable.csv")
        df_constr.to_csv(cfg.OUTPUT_DIR+"/constraint.csv")
    with pd.option_context('display.max_colwidth', None):
        with pd.option_context('display.max_rows', None):
            print("df_var")
            display(df_var)
            print()
            print("df_constr")
            display(df_constr)
    substract_time = time.time() - ts
    opt_func.log_timestamp("get var and constraint")

    opt_func.write_arguments_to_file(NUM_REQUESTS, callgraph, depth_dict, callsize_dict, placement)


    if gurobi_model.Status != GRB.OPTIMAL:
        app.logger.info(f"{cfg.log_prefix} XXXXXXXXXXXXXXXXXXXXXXXXXXX")
        app.logger.info(f"{cfg.log_prefix} XXXX INFEASIBLE MODEL! XXXX")
        app.logger.info(f"{cfg.log_prefix} XXXXXXXXXXXXXXXXXXXXXXXXXXX")
        if cfg.DISPLAY:
            display(df_constr)
        
        gurobi_model.computeIIS()
        gurobi_model.write("gurobi_model.ilp")
        print('\nThe following constraints and variables are in the IIS:')
        # for c in gurobi_model.getConstrs():
        #     if c.IISConstr: print(f'\t{c.constrname}: {gurobi_model.getRow(c)} {c.Sense} {c.RHS}')
        for v in gurobi_model.getVars():
            if v.IISLB: print(f'\t{v.varname} ≥ {v.LB}')
            if v.IISUB: print(f'\t{v.varname} ≤ {v.UB}')
        print("OPTIMIZER, INFEASIBLE MODEL")
    else:
        app.logger.info(f"{cfg.log_prefix} ooooooooooooooooooooooo")
        app.logger.info(f"{cfg.log_prefix} oooo SOLVED MODEL! oooo")
        app.logger.info(f"{cfg.log_prefix} ooooooooooooooooooooooo")

        ## Print out the result
        optimize_end_time = time.time()
        # optimizer_runtime = round((optimize_end_time - optimizer_start_time) - substract_time, 5)
        # solve_runtime = round(solve_end_time - solve_start_time, 5)
        app.logger.error(f"{cfg.log_prefix} ** Objective function: {objective_function}")
        app.logger.error(f"{cfg.log_prefix} ** Num constraints: {num_constr}")
        app.logger.error(f"{cfg.log_prefix} ** Num variables: {num_var}")
        # app.logger.error(f"{cfg.log_prefix} ** Optimization runtime: {optimizer_runtime} ms")
        # app.logger.error(f"{cfg.log_prefix} ** model.optimize() runtime: {solve_runtime} ms")
        app.logger.error(f"{cfg.log_prefix} ** model.objVal: {gurobi_model.objVal}")
        # app.logger.error(f"{cfg.log_prefix} ** gurobi_model.objVal / total num requests: {gurobi_model.objVal/MAX_LOAD}")
        request_flow = dict()
        for key in callgraph:
            request_flow[key] = pd.DataFrame(columns=["Callgraph", "From", "To", "Flow"])
        for key in callgraph:
            for arc in arcs[key]:
                if aggregated_load[key][arc].x > 1e-6:
                    temp = pd.DataFrame({"Callgraph":key, "From": [arc[0]], "To": [arc[1]], "Flow": [aggregated_load[key][arc].x]})
                    request_flow[key] = pd.concat([request_flow[key], temp], ignore_index=True)
        if cfg.DISPLAY:
            for key in callgraph:
                display(request_flow[key])
        percentage_df = dict()
        for key in callgraph:
            percentage_df[key] = opt_func.translate_to_percentage(request_flow[key])
        for key in callgraph:
            print(f"percentage_df[{key}]")
            display(percentage_df[key])
            if percentage_df[key].empty == False:
                percentage_df[key].to_csv(f'{cfg.OUTPUT_DIR}/routing-{key}.csv')
                # opt_func.plot_callgraph_request_flow(percentage_df, key, placement, callgraph, network_arc_var_name)



        # In[52]:
        
        def update_flow(cur_node, cur_node_cid, inout_weight, cg, actual_req_flow_df, p_df, NUM_REQ, key, incoming_flow):
            if cur_node == opt_func.source_node_name:
                for index, row in p_df.iterrows():
                    if row["src"] == opt_func.source_node_name:
                        new_flow = 0
                        new_flow += NUM_REQ[row['dst_cid']][key]
                        print(f'update_flow, {tup_index_to_str_index(row)},  new_flow: {new_flow}')
                        # print()
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
                            
                            print(f'update_flow, {str_index}, incoming_flow: {incoming_flow} new_flow: {round(new_flow, 1)}')
                            # print()
                            actual_req_flow_df.loc[str_index, "flow"] += new_flow
                            update_flow(row['dst'], row['dst_cid'], inout_weight, cg, actual_req_flow_df, p_df,  NUM_REQ, key, incoming_flow=new_flow)
                                
                                
        def update_actual_flow(inout_weight, p_df, cg, actual_req_flow_df, NUM_REQ, key):
            # root_node = opt_func.find_root_node(cg, key)
            root_node = opt_func.source_node_name
            update_flow(root_node, -1, inout_weight, cg, actual_req_flow_df, p_df, NUM_REQ, key, 0)
        
        for key in request_in_out_weight:
            print(f'request_in_out_weight[{key}]: {request_in_out_weight[key]}')
            print(f'norm_inout_weight[{key}]: {norm_inout_weight[key]}')
            print()
        print(f'merged_in_out_weight: {merged_in_out_weight}')
        print()
        
        def tup_index_to_str_index(row):
            return f"{row['src']}, {row['src_cid']}, {row['dst']}, {row['dst_cid']}"
        
        if traffic_segmentation == False:
            assert len(percentage_df) == 1
            for key in percentage_df:
                assert key == merged_cg_key
                new_index = list()
                for index, row in percentage_df[key].iterrows():
                    new_index.append(tup_index_to_str_index(row))
                # print(f'new_index: {new_index}')
            actual_request_flow_df = dict()
            for key in original_request_in_out_weight:
                actual_request_flow_df[key] = pd.DataFrame(columns=percentage_df[merged_cg_key].columns, index=new_index)
                for index, row in percentage_df[merged_cg_key].iterrows():
                    actual_request_flow_df[key].loc[tup_index_to_str_index(row)] = [row["src"], row["dst"], row["src_cid"], row["dst_cid"], 0, 0, row["weight"]]
                    
                # update_actual_flow(request_in_out_weight[key], percentage_df, callgraph, key, actual_request_flow_df)
                print(original_request_in_out_weight)
                update_actual_flow(original_request_in_out_weight[key], percentage_df[merged_cg_key], original_callgraph[key], actual_request_flow_df[key], original_NUM_REQUESTS, key)
                
                print(f'percentage_df[{merged_cg_key}]')
                display(percentage_df[merged_cg_key])
                print(f'actual_request_flow_df[{key}]')
                display(actual_request_flow_df[key])
        

        # In[52]:

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
            print("another_group_by_df")
            display(another_group_by_df)
            
        # for key in callgraph:
        #     opt_func.plot_callgraph_request_flow(percentage_df, [key], network_arc_var_name)
        if cfg.PLOT:
            # if traffic_segmentation == True:
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
        
        
        # In[52]:
        
        
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
                # print(f'compute_latency[{key}][{k}]: {round(compute_latency[key][k].getAttr("X"), 1)}')
                # print(f'compute_load[{key}][{k}]: {round(compute_load[key][k].getAttr("X"), 1)}')
                # print(f'{compute_latency[key][k].getAttr("X")*compute_load[key][k].getAttr("X")}')
                lat_ret[key]["compute"] += compute_latency[key][k].getAttr("X")*compute_load[key][k].getAttr("X")
                
            for k, v in network_latency[key].items():
                # print(f'network_latency[{key}][{k}]: {round(network_latency[key][k].getAttr("X"), 1)}')
                # print(f'network_load[{key}][{k}]: {round(network_load[key][k].getAttr("X"), 1)}')
                # print(f'{network_latency[key][k].getAttr("X")*network_load[key][k].getAttr("X")}')
                lat_ret[key]["network"] += network_latency[key][k].getAttr("X")*network_load[key][k].getAttr("X")
                
            for k, v in network_egress_cost[key].items():
                # print(f'network_egress_cost[{key}][{k}]: {round(network_egress_cost[key][k].getAttr("X"), 1)}')
                # print(f'network_load[{key}][{k}]: {round(network_load[key][k].getAttr("X"), 1)}')
                # print(f'{round(network_egress_cost[key][k].getAttr("X")*network_load[key][k].getAttr("X"), 1)}')
                cost_ret[key] += network_egress_cost[key][k].getAttr("X")*network_load[key][k].getAttr("X")
        total_lat = dict()
        sum_total_lat = dict()
        for key in lat_ret:
            total_lat[key] = 0
            for k, v in lat_ret[key].items(): # k: compute or network
                print(f"{key}: {k}: {round(v,1)}")
                total_lat[key] += v
                if k not in sum_total_lat:
                    sum_total_lat[k] = 0
                sum_total_lat[k] += v
            if MAX_LOAD[key] != 0:
                print(f"{key}: total_avg_latency: {round(total_lat[key], 1)}")
                print(f"{key}: avg_latency: {round(total_lat[key]/MAX_LOAD[key], 1)}")
            else:
                print(f"{key}: total: {total_lat[key]}, MAX_LOAD[{key}] is 0")
            print(f'{key}: total_egress_cost: {round(cost_ret[key], 1)}')
            print()
            
        all_total_e_cost = 0
        all_total_lat = 0
        for key in lat_ret:
            all_total_lat += total_lat[key]
            all_total_e_cost += cost_ret[key]
        for k in sum_total_lat:
            print(f"sum_total_lat: {k}: {round(sum_total_lat[k], 1)}")
        print(f"all_total_avg_lat: {round(all_total_lat, 1)}")
        print(f"all_avg_lat: {round(all_total_lat/sum(MAX_LOAD.values()), 1)}")
        print(f"all_total_e_cost: {round(all_total_e_cost, 1)}")
        print()
        
        print(f"model.objVal: {round(gurobi_model.objVal, 1)}")
        print('*'*70)
        
        
        # In[52]:
        
        
        if traffic_segmentation == False:
            act_tot_network_latency = dict()
            for key in actual_request_flow_df:
                # display(actual_request_flow_df[key])
                act_tot_network_latency[key] = 0
                for index, row in actual_request_flow_df[key].iterrows():
                    act_tot_network_latency[key] += opt_func.get_network_latency(row['src_cid'], row['dst_cid']) * row['flow']
            
            group_by_df = dict()
            for key in actual_request_flow_df:
                # display(actual_request_flow_df[key])
                temp_df = actual_request_flow_df[key].drop(columns=['src', 'src_cid', 'total', 'weight'])
                group_by_df[key] = temp_df.groupby(["dst", "dst_cid"]).sum()
                group_by_df[key] = group_by_df[key].reset_index()
                # display(group_by_df[key])
                
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
                    # print(f'{row["dst"]}, {row["dst_cid"]}')
                    # display(temp_df)
                    idx = opt_func.get_compute_arc_var_name(row["dst"], row["dst_cid"])
                    lat_f = original_compute_df.loc[[idx]]["latency_function_"+key].tolist()[0]
                    # print(lat_f)
                    pred = lat_f.predict(temp_df)
                    # print(f'pred: {pred}')
                    act_tot_compute_avg_lat[key] += (pred[0] * group_by_df[key].loc[index, "flow"])
                    print(f'{key}, {row["dst"]}, cid, {row["dst_cid"]}: {round(pred[0] * group_by_df[key].loc[index, "flow"], 1)} = {round(pred[0], 1)} x {round(group_by_df[key].loc[index, "flow"], 1)}')
            act_tot_avg_lat = dict()
            for key in act_tot_compute_avg_lat:
                act_tot_avg_lat[key] = act_tot_compute_avg_lat[key] + act_tot_network_latency[key]
            for key in act_tot_avg_lat:
                print(f'{key}: compute: {round(act_tot_compute_avg_lat[key], 1)}')
                print(f'{key}: network: {round(act_tot_network_latency[key], 1)}')
                print(f'{key}: sum: {round(act_tot_avg_lat[key], 1)}')
                print(f'{key}: avg latency: {round(act_tot_avg_lat[key]/original_MAX_LOAD[key], 1)}')
                print(f'{key}: egress cost: ')
                print()
            print(f'sum_total_lat: compute: {round(sum(act_tot_compute_avg_lat.values()), 1)}')
            print(f'sum_total_lat: network: {round(sum(act_tot_network_latency.values()), 1)}')
            print(f'all_total_avg_lat: {round(sum(act_tot_avg_lat.values()), 1)}')
            print(f'all_avg_lat: {round(sum(act_tot_avg_lat.values())/sum(original_MAX_LOAD.values()), 1)}')
            print(f'all_total_e_cost: ')
        
    
''' END of run_optimizer function'''


# In[52]:


# total_list = list()
# for index, row in concat_df.iterrows():
#     total = group_by_sum.loc[[index]]["flow"].tolist()[0]
#     total_list.append(total)
# concat_df["total"] = total_list
# weight_list = list()
# for index, row in concat_df.iterrows():
#     try:
#         weight_list.append(row['flow']/row['total'])
#     except Exception as e:
#         weight_list.append(0)
# concat_df["weight"] = weight_list
# display(concat_df)


# %%
