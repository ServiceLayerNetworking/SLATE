import pandas as pd
import os
import graphviz

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)

def visualize_request_flow(fn, counter, plot_first_hop_only=False, include_legend=True):
    df = pd.read_csv(fn)
    if counter > 0:
        df = df[df['counter'] == counter]
    
    grouped_df = df.groupby(['src_svc', 'dst_svc', 'src_endpoint', 'dst_endpoint', 'src_cid', 'dst_cid']).agg({
        'flow': 'sum', 'total': 'max', 'weight': 'mean'
    }).reset_index()

    # Map request types and colors
    request_color_map = {
        'addtocart': 'blue',
        'checkout': 'darkred'
    }
    grouped_df['src_endpoint'] = grouped_df['src_endpoint'].replace({
        'sslateingress@POST@/cart': 'addtocart',
        'sslateingress@POST@/cart/checkout': 'checkout',
        'frontend@POST@/cart': 'addtocart',
        'frontend@POST@/cart/checkout': 'checkout',
    })
    grouped_df['dst_endpoint'] = grouped_df['dst_endpoint'].replace({
        'frontend@POST@/cart': 'addtocart',
        'frontend@POST@/cart/checkout': 'checkout',
    })

    node_color_dict = {
        "us-west-1": "#FFBF00",
        "us-east-1": "#ff6375",
        "us-central-1": "#c8ffbf",
        "us-south-1": "#bbfbfc",
        "XXXX": "gray",
    }

    g_ = graphviz.Digraph(format='pdf')
    g_.attr('graph', rankdir='LR')
    g_.attr('node', shape='circle', style='filled', fontname='Arial')

    for _, row in grouped_df.iterrows():
        src_node = f'{row["src_svc"]}\n{row["src_cid"]}'
        dst_node = f'{row["dst_svc"]}\n{row["dst_cid"]}'

        src_color = node_color_dict.get(row['src_cid'], 'white')
        dst_color = node_color_dict.get(row['dst_cid'], 'white')

        g_.node(src_node, fillcolor=src_color)
        g_.node(dst_node, fillcolor=dst_color)

        # Label includes the request type, flow, and percentage weight
        edge_label = f'{row["src_endpoint"]} ({int(row["flow"])}, {int(row["weight"] * 100)}%)'
        edge_color = request_color_map.get(row['src_endpoint'], 'black')
        edge_style = 'dotted' if row['src_cid'] != row['dst_cid'] else 'solid'

        # Thicker edges
        edge_penwidth = '3.0'

        g_.edge(
            src_node,
            dst_node,
            label=edge_label,
            color=edge_color,
            style=edge_style,
            penwidth=edge_penwidth
        )

    if include_legend:
        with g_.subgraph(name='cluster_legend') as legend:
            legend.attr(label='Legend')
            for cid, color in node_color_dict.items():
                legend.node(cid, label=cid, style='filled', fillcolor=color)

            # Add legend for request colors
            for req_type, color in request_color_map.items():
                legend.node(req_type, label=req_type, style='filled', fillcolor=color)

    return g_

def run(input_file):
    counter = -1
    graph = visualize_request_flow(input_file, counter, plot_first_hop_only=False, include_legend=True)
    output_file = os.path.splitext(input_file)[0]
    graph.render(output_file, cleanup=True)
    print(f"Routing visualization saved as: {output_file}.pdf")

if __name__ == "__main__":
    import sys
    input_file = sys.argv[1]
    run(input_file)
