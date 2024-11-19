import pandas as pd
import os
import graphviz
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)

def visualize_request_flow(fn, counter, plot_first_hop_only=False, include_legend=True, routing_rule=None):
    df = pd.read_csv(fn)
    if counter > 0:
        df = df[df['counter'] == counter]
    # display(df)
    grouped_df = df.groupby(['counter','src_svc', 'dst_svc', 'src_cid', 'dst_cid']).agg({'flow': 'sum', 'total': 'max'}).reset_index()
    grouped_df['weight'] = grouped_df['flow'] / grouped_df['total']
    # display(grouped_df)

    node_color_dict = {
        "XXXX": "gray",
        "-1": "#FFBF00",
        "us-west-1": "#FFBF00",
        "us-east-1": "#ff6375",
        "us-south-1": "#bbfbfc",
        "us-central-1": "#c8ffbf"
    }

    g_ = graphviz.Digraph()
    node_pw = "1.4"
    node_fs = "16"
    node_width = "0.6"
    
    edge_pw = "1.0"
    edge_fs = "14"
    edge_arrowsize = "1.2"
    edge_minlen = "1.2"
    
    font_name = "times bold italic"
    cluster_list = list()

    # Edge colors for request types
    legend_dict = {
        "singlecore": "blue",
        "multicore": "red"
    }

    change_node_label = {"sslate-ingress": "IngressGW", "frontend": "Frontend"}

    # Drop duplicates based on relevant columns
    df = df.drop_duplicates(subset=["src_svc", "dst_svc", "src_cid", "dst_cid", "flow", "total", "weight"], keep='last')
    for index, row in df.iterrows():
        src_cid = row["src_cid"]
        dst_cid = row["dst_cid"]
        src_svc = row["src_svc"].split("-")[-1]
        dst_svc = row["dst_svc"].split("-")[-1]
        src_endpoint = row["src_endpoint"]
        dst_endpoint = row["dst_endpoint"]
        cluster_list.extend([src_cid, dst_cid])
        
        ''' When you only want to plot the first hop routing '''
        if plot_first_hop_only:
            if dst_endpoint not in legend_dict:
                continue
        
        # Determine edge style
        if src_svc == "SOURCE":
            edge_style = 'filled'
        elif src_cid == dst_cid:
            edge_style = 'filled'
        else:
            edge_style = 'dashed'
        
        # Extract request type from src_endpoint (assuming it's consistent)
        try:
            request_type = src_endpoint.split('/')[-1]
        except IndexError:
            request_type = "unknown"
        
        # Assign edge color based on request type
        edge_color = legend_dict.get(request_type, "black")
        
        # Modify edge label to include request type
        if src_svc == "SOURCE":
            edge_label = f'{round(row["flow"],1)}\n{request_type}'
        elif int(row["flow"]) > 0:
            edge_label = f'{round(row["flow"],1)}({int(round(row["weight"], 2)*100)}%)\n{request_type}'
        else:
            edge_label = f'{int(round(row["weight"], 2)*100)}%\n{request_type}'
        
        try:
            src_node_color = node_color_dict.get(src_cid, "black")
            dst_node_color = node_color_dict.get(dst_cid, "black")
            src_node_name = src_svc + str(src_cid)
            dst_node_name = dst_svc + str(dst_cid)
            
            # Modify node labels to include region
            src_node_label = f"{src_svc}\n{src_cid}"
            dst_node_label = f"{dst_svc}\n{dst_cid}"
            
            ## PLOT SOURCE OR NOT
            if "SOURCE" in src_node_label:
                src_node_label = "SOURCE"
                dst_node_label = f"GW\n{dst_cid}"
                
            if "ingress" in src_node_label:
                src_node_label = f"GW\n{src_cid}"
                dst_node_label = f"FR\n{dst_cid}"
            if "frontend" in src_node_label:
                src_node_label = f"FR\n{src_cid}"
            if "service" in src_node_label:
                src_node_label = f"{src_node_label[:2].upper()}\n{src_cid}"
            if "service" in dst_node_label:
                dst_node_label = f"{dst_node_label[:2].upper()}\n{dst_cid}"
            
            # Add nodes to the graph
            g_.node(
                name=src_node_name, 
                label=src_node_label, 
                shape='circle', 
                style='filled', 
                fillcolor=src_node_color, 
                penwidth=node_pw, 
                fontsize=node_fs, 
                fontname=font_name, 
                fixedsize="True", 
                width=node_width
            )
            g_.node(
                name=dst_node_name, 
                label=dst_node_label, 
                shape='circle', 
                style='filled', 
                fillcolor=dst_node_color, 
                penwidth=node_pw, 
                fontsize=node_fs, 
                fontname=font_name, 
                fixedsize="True", 
                width=node_width
            )
            
            # Add edge to the graph with updated label and color
            g_.edge(
                src_node_name, 
                dst_node_name, 
                label=edge_label, 
                penwidth=edge_pw, 
                style=edge_style, 
                fontsize=edge_fs, 
                fontcolor=edge_color, 
                color=edge_color, 
                arrowsize=edge_arrowsize, 
                minlen=edge_minlen
            )
        except Exception as e:
            print(f"Error: {e}")
            print(f"Error row: {row}")
        
    # Adding a legend
    if include_legend:
        with g_.subgraph(name='cluster_legend') as c:
            c.attr(label='Legend')
            legend_fontsize = '10'
            # Create legend for regions
            regions = set(cluster_list)
            for region in regions:
                if region == "XXXX":
                    continue
                c.node(
                    f"legend_region_{region}", 
                    label=region, 
                    shape='circle', 
                    style='filled', 
                    fillcolor=node_color_dict.get(region, "black"), 
                    fontsize=legend_fontsize, 
                    fixedsize='true', 
                    width='0.3', 
                    height='0.3'
                )
            # Create legend for request types
            legend_counter = 0
            for req_type, color in legend_dict.items():
                src = f'legend_src_{legend_counter}'
                dst = f'legend_dst_{legend_counter}'
                c.node(src, label='', style='invisible')
                c.node(dst, label='', style='invisible')
                c.edge(
                    src, 
                    dst, 
                    label=req_type, 
                    color=color, 
                    fontsize=legend_fontsize
                )
                legend_counter += 1

    return g_

def run(input_file):
    counter = -1
    g_ = visualize_request_flow(input_file, counter, plot_first_hop_only=False, include_legend=True)
    pwd = os.getcwd()
    output_file = f"{pwd}/{input_file.split('.')[0]}"
    print(f"** Saved routing visualization: {output_file}.pdf")
    g_.render(output_file)
    g_

import sys
if __name__ == "__main__":
    input_file = sys.argv[1]
    run(input_file)
