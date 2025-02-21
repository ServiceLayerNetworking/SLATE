\ Model RequestRouting
\ LP format - for model browsing. Use MPS format to capture full model detail.
Minimize
  0 load_for_compute_edge2[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')]
   + 0 load_for_compute_edge2[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')]
   + 0 load_for_compute_edge2[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')]
   + 0 load_for_compute_edge2[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')]
   + 0 load_for_compute_edge2[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')]
   + 0 load_for_compute_edge2[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')]
   + 0 load_for_compute_edge2[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')]
   + 0 load_for_compute_edge2[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')]
   + 0 network_egress_cost[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_east_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_west_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_east_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_west_1#start')]
   + 0 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_east_1#start')]
   + 0 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_west_1#start')]
   + 0 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_east_1#start')]
   + 0 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_west_1#start')]
   + [
   2 compute_latency[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')] * load_for_compute_edge[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')]
   + 2 compute_latency[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')] * load_for_compute_edge[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')]
   + 2 compute_latency[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')] * load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')]
   + 2 compute_latency[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')] * load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')]
   + 2 compute_latency[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')] * load_for_compute_edge[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')]
   + 2 compute_latency[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')] * load_for_compute_edge[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')]
   + 2 compute_latency[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')] * load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')]
   + 2 compute_latency[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')] * load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')]
   + 2 network_latency[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')] * load_for_network_edge[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')]
   + 2 network_latency[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')] * load_for_network_edge[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')]
   + 2 network_latency[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')] * load_for_network_edge[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')]
   + 2 network_latency[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')] * load_for_network_edge[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')]
   + 2 network_latency[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_east_1#start')] * load_for_network_edge[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_east_1#start')]
   + 2 network_latency[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_west_1#start')] * load_for_network_edge[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_west_1#start')]
   + 2 network_latency[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_east_1#start')] * load_for_network_edge[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_east_1#start')]
   + 2 network_latency[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_west_1#start')] * load_for_network_edge[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_west_1#start')]
   + 2 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_east_1#start')] * load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_east_1#start')]
   + 2 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_west_1#start')] * load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_west_1#start')]
   + 2 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_east_1#start')] * load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_east_1#start')]
   + 2 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_west_1#start')] * load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_west_1#start')]
   ] / 2 
Subject To
 normalized_load_('corecontrast@POST@/multicore#us-east-1#start',_'corecontrast@POST@/multicore#us-east-1#end'):
   - load_for_compute_edge[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')]
   - 4 load_for_compute_edge[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')]
   + normalized_load_for_compute_edge[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')]
   = 0
 normalized_load_('corecontrast@POST@/singlecore#us-east-1#start',_'corecontrast@POST@/singlecore#us-east-1#end'):
   - 0.25 load_for_compute_edge[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')]
   - load_for_compute_edge[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')]
   + normalized_load_for_compute_edge[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')]
   = 0
 normalized_load_('sslateingress@POST@/singlecore#us-east-1#start',_'sslateingress@POST@/singlecore#us-east-1#end'):
   - load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')]
   - load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')]
   + normalized_load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')]
   = 0
 normalized_load_('sslateingress@POST@/multicore#us-east-1#start',_'sslateingress@POST@/multicore#us-east-1#end'):
   - load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')]
   - load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')]
   + normalized_load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')]
   = 0
 normalized_load_('corecontrast@POST@/multicore#us-west-1#start',_'corecontrast@POST@/multicore#us-west-1#end'):
   - load_for_compute_edge[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')]
   - 4 load_for_compute_edge[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')]
   + normalized_load_for_compute_edge[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')]
   = 0
 normalized_load_('corecontrast@POST@/singlecore#us-west-1#start',_'corecontrast@POST@/singlecore#us-west-1#end'):
   - 0.25 load_for_compute_edge[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')]
   - load_for_compute_edge[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')]
   + normalized_load_for_compute_edge[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')]
   = 0
 normalized_load_('sslateingress@POST@/singlecore#us-west-1#start',_'sslateingress@POST@/singlecore#us-west-1#end'):
   - load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')]
   - load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')]
   + normalized_load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')]
   = 0
 normalized_load_('sslateingress@POST@/multicore#us-west-1#start',_'sslateingress@POST@/multicore#us-west-1#end'):
   - load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')]
   - load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')]
   + normalized_load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')]
   = 0
 cluster_us-east-1_load_in_sslateingress@POST@/singlecore:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_east_1#start')]
   = 25
 cluster_us-west-1_load_in_sslateingress@POST@/singlecore:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_west_1#start')]
   = 600
 cluster_us-east-1_load_in_sslateingress@POST@/multicore:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_east_1#start')]
   = 700
 cluster_us-west-1_load_in_sslateingress@POST@/multicore:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_west_1#start')]
   = 400
 source:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_east_1#start')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_west_1#start')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_east_1#start')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_west_1#start')]
   = 1725
 flow_conservation-start_node-corecontrast@POST@/multicore:
   - load_for_compute_edge[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')]
   + load_for_network_edge[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_east_1#start')]
   + load_for_network_edge[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_east_1#start')]
   = 0
 flow_conservation-start_node-corecontrast@POST@/singlecore:
   - load_for_compute_edge[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')]
   + load_for_network_edge[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')]
   + load_for_network_edge[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')]
   = 0
 flow_conservation-start_node-sslateingress@POST@/singlecore:
   - load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_east_1#start')]
   = 0
 flow_conservation-start_node-sslateingress@POST@/multicore:
   - load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_east_1#start')]
   = 0
 flow_conservation-start_node-corecontrast@POST@/multicore:
   - load_for_compute_edge[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')]
   + load_for_network_edge[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_west_1#start')]
   + load_for_network_edge[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_west_1#start')]
   = 0
 flow_conservation-start_node-corecontrast@POST@/singlecore:
   - load_for_compute_edge[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')]
   + load_for_network_edge[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')]
   + load_for_network_edge[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')]
   = 0
 flow_conservation-start_node-sslateingress@POST@/singlecore:
   - load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_west_1#start')]
   = 0
 flow_conservation-start_node-sslateingress@POST@/multicore:
   - load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_west_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-16a6e1be:
   load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')]
   - load_for_network_edge[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')]
   - load_for_network_edge[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-16a6e1be:
   load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')]
   - load_for_network_edge[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')]
   - load_for_network_edge[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-953f0033:
   load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')]
   - load_for_network_edge[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_east_1#start')]
   - load_for_network_edge[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_west_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-953f0033:
   load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')]
   - load_for_network_edge[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_east_1#start')]
   - load_for_network_edge[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_west_1#start')]
   = 0
 latency_function_('corecontrast@POST@/multicore#us-east-1#start',_'corecontrast@POST@/multicore#us-east-1#end'):
   compute_latency[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')]
   + [
   - 1.57851e-05 normalized_load_for_compute_edge[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')] ^2
   ] = 1.924014069403059
 latency_function_('corecontrast@POST@/singlecore#us-east-1#start',_'corecontrast@POST@/singlecore#us-east-1#end'):
   compute_latency[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')]
   + [
   - 0.0010205703179596 normalized_load_for_compute_edge[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')] ^2
   ] = 1
 latency_function_('sslateingress@POST@/singlecore#us-east-1#start',_'sslateingress@POST@/singlecore#us-east-1#end'):
   compute_latency[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')]
   + [
   - 3.69049e-06 normalized_load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')] ^2
   ] = 2.307072443509285
 latency_function_('sslateingress@POST@/multicore#us-east-1#start',_'sslateingress@POST@/multicore#us-east-1#end'):
   compute_latency[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')]
   + [
   - 2.92483e-06 normalized_load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')] ^2
   ] = 1.5162914348461
 latency_function_('corecontrast@POST@/multicore#us-west-1#start',_'corecontrast@POST@/multicore#us-west-1#end'):
   compute_latency[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')]
   + [
   - 1.57851e-05 normalized_load_for_compute_edge[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')] ^2
   ] = 1.924014069403059
 latency_function_('corecontrast@POST@/singlecore#us-west-1#start',_'corecontrast@POST@/singlecore#us-west-1#end'):
   compute_latency[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')]
   + [
   - 0.0010205703179596 normalized_load_for_compute_edge[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')] ^2
   ] = 1
 latency_function_('sslateingress@POST@/singlecore#us-west-1#start',_'sslateingress@POST@/singlecore#us-west-1#end'):
   compute_latency[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')]
   + [
   - 3.69049e-06 normalized_load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')] ^2
   ] = 2.307072443509285
 latency_function_('sslateingress@POST@/multicore#us-west-1#start',_'sslateingress@POST@/multicore#us-west-1#end'):
   compute_latency[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')]
   + [
   - 2.92483e-06 normalized_load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')] ^2
   ] = 1.5162914348461
Bounds
 load_for_compute_edge[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')] <= 100000
 load_for_compute_edge[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')] <= 100000
 load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')] <= 100000
 load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')] <= 100000
 load_for_compute_edge[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')] <= 100000
 load_for_compute_edge[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')] <= 100000
 load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')] <= 100000
 load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('corecontrast@POST@/multicore#us_east_1#start',_'corecontrast@POST@/multicore#us_east_1#end')] <= 100000
 normalized_load_for_compute_edge[('corecontrast@POST@/singlecore#us_east_1#start',_'corecontrast@POST@/singlecore#us_east_1#end')] <= 100000
 normalized_load_for_compute_edge[('sslateingress@POST@/singlecore#us_east_1#start',_'sslateingress@POST@/singlecore#us_east_1#end')] <= 100000
 normalized_load_for_compute_edge[('sslateingress@POST@/multicore#us_east_1#start',_'sslateingress@POST@/multicore#us_east_1#end')] <= 100000
 normalized_load_for_compute_edge[('corecontrast@POST@/multicore#us_west_1#start',_'corecontrast@POST@/multicore#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('corecontrast@POST@/singlecore#us_west_1#start',_'corecontrast@POST@/singlecore#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('sslateingress@POST@/singlecore#us_west_1#start',_'sslateingress@POST@/singlecore#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('sslateingress@POST@/multicore#us_west_1#start',_'sslateingress@POST@/multicore#us_west_1#end')] <= 100000
 network_latency[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')] = 0
 network_latency[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')] = 66
 network_latency[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')] = 66
 network_latency[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')] = 0
 network_latency[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_east_1#start')] = 0
 network_latency[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_west_1#start')] = 66
 network_latency[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_east_1#start')] = 66
 network_latency[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_west_1#start')] = 0
 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_east_1#start')] = 0
 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_west_1#start')] = 0
 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_east_1#start')] = 0
 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_west_1#start')] = 0
 network_egress_cost[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')] = 0
 network_egress_cost[('sslateingress@POST@/singlecore#us_east_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')] = 0.1
 network_egress_cost[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_east_1#start')] = 0.1
 network_egress_cost[('sslateingress@POST@/singlecore#us_west_1#end',_'corecontrast@POST@/singlecore#us_west_1#start')] = 0
 network_egress_cost[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_east_1#start')] = 0
 network_egress_cost[('sslateingress@POST@/multicore#us_east_1#end',_'corecontrast@POST@/multicore#us_west_1#start')] = 0.1
 network_egress_cost[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_east_1#start')] = 0.1
 network_egress_cost[('sslateingress@POST@/multicore#us_west_1#end',_'corecontrast@POST@/multicore#us_west_1#start')] = 0
 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_east_1#start')] = 0
 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/singlecore#us_west_1#start')] = 0
 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_east_1#start')] = 0
 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/multicore#us_west_1#start')] = 0
End
