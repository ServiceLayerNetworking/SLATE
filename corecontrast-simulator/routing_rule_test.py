import math
from collections import defaultdict

# Define a class for Compute Edges
class ComputeEdge:
    def __init__(self, start, end, constant, k, node):
        """
        Initialize a ComputeEdge.

        Parameters:
        - start (str): Start node identifier.
        - end (str): End node identifier.
        - constant (float): Constant component of latency.
        - k (float): Coefficient for squared normalized load.
        - node (str): The node to which this edge is connected.
        """
        self.start = start
        self.end = end
        self.constant = constant  # Constant component of latency
        self.k = k                # Coefficient for squared normalized load
        self.node = node          # Associated node for normalized load

    def compute_latency(self, normalized_load):
        """
        Compute the latency for this compute edge based on the normalized load.

        Formula:
            compute_latency = constant + k * (normalized_load)^2

        Parameters:
        - normalized_load (float): The normalized load for the associated node.

        Returns:
        - latency (float): Calculated latency for this edge.
        """
        latency = self.constant + self.k * (normalized_load ** 2)
        return latency

# Define a class for Network Edges
class NetworkEdge:
    def __init__(self, start, end, network_latency):
        """
        Initialize a NetworkEdge.

        Parameters:
        - start (str): Start node identifier.
        - end (str): End node identifier.
        - network_latency (float): Fixed network latency.
        """
        self.start = start
        self.end = end
        self.network_latency = network_latency  # Fixed network latency

# Initialize Compute Edges based on the LP constraints
compute_edges = [
    ComputeEdge(
        'corecontrast@POST@/singlecore#us_east_1#start',
        'corecontrast@POST@/singlecore#us_east_1#end',
        constant=1,
        k=0.078340559948566,
        node='corecontrast@POST@/singlecore#us_east_1#start'
    ),
    ComputeEdge(
        'corecontrast@POST@/multicore#us_east_1#start',
        'corecontrast@POST@/multicore#us_east_1#end',
        constant=1,
        k=0.0015913631904008,
        node='corecontrast@POST@/multicore#us_east_1#start'
    ),
    ComputeEdge(
        'sslateingress@POST@/multicore#us_east_1#start',
        'sslateingress@POST@/multicore#us_east_1#end',
        constant=3.115396051809149,
        k=0.00000185459,
        node='sslateingress@POST@/multicore#us_east_1#start'
    ),
    ComputeEdge(
        'sslateingress@POST@/singlecore#us_east_1#start',
        'sslateingress@POST@/singlecore#us_east_1#end',
        constant=1.82261443113976,
        k=0.000177601,
        node='sslateingress@POST@/singlecore#us_east_1#start'
    ),
    ComputeEdge(
        'corecontrast@POST@/singlecore#us_west_1#start',
        'corecontrast@POST@/singlecore#us_west_1#end',
        constant=1,
        k=0.078340559948566,
        node='corecontrast@POST@/singlecore#us_west_1#start'
    ),
    ComputeEdge(
        'corecontrast@POST@/multicore#us_west_1#start',
        'corecontrast@POST@/multicore#us_west_1#end',
        constant=1,
        k=0.0015913631904008,
        node='corecontrast@POST@/multicore#us_west_1#start'
    ),
    ComputeEdge(
        'sslateingress@POST@/multicore#us_west_1#start',
        'sslateingress@POST@/multicore#us_west_1#end',
        constant=3.115396051809149,
        k=0.00000185459,
        node='sslateingress@POST@/multicore#us_west_1#start'
    ),
    ComputeEdge(
        'sslateingress@POST@/singlecore#us_west_1#start',
        'sslateingress@POST@/singlecore#us_west_1#end',
        constant=1.82261443113976,
        k=0.000177601,
        node='sslateingress@POST@/singlecore#us_west_1#start'
    ),
    # Additional Compute Edges between us-west-1 and us-east-1 for /singlecore and /multicore with load 0
    ComputeEdge(
        'corecontrast@POST@/singlecore#us_west_1#start',
        'corecontrast@POST@/singlecore#us_east_1#end',
        constant=1,
        k=0.078340559948566,
        node='corecontrast@POST@/singlecore#us_west_1#start'
    ),
    ComputeEdge(
        'corecontrast@POST@/singlecore#us_east_1#start',
        'corecontrast@POST@/singlecore#us_west_1#end',
        constant=1,
        k=0.078340559948566,
        node='corecontrast@POST@/singlecore#us_east_1#start'
    ),
    ComputeEdge(
        'corecontrast@POST@/multicore#us_west_1#start',
        'corecontrast@POST@/multicore#us_east_1#end',
        constant=1,
        k=0.0015913631904008,
        node='corecontrast@POST@/multicore#us_west_1#start'
    ),
    ComputeEdge(
        'corecontrast@POST@/multicore#us_east_1#start',
        'corecontrast@POST@/multicore#us_west_1#end',
        constant=1,
        k=0.0015913631904008,
        node='corecontrast@POST@/multicore#us_east_1#start'
    )
]

# Initialize Network Edges based on the LP bounds
network_edges = [
    NetworkEdge(
        'sslateingress@POST@/singlecore#us_west_1#end',
        'corecontrast@POST@/singlecore#us_west_1#start',
        network_latency=0
    ),
    NetworkEdge(
        'sslateingress@POST@/singlecore#us_west_1#end',
        'corecontrast@POST@/singlecore#us_east_1#start',
        network_latency=66
    ),
    NetworkEdge(
        'sslateingress@POST@/singlecore#us_east_1#end',
        'corecontrast@POST@/singlecore#us_west_1#start',
        network_latency=66
    ),
    NetworkEdge(
        'sslateingress@POST@/singlecore#us_east_1#end',
        'corecontrast@POST@/singlecore#us_east_1#start',
        network_latency=0
    ),
    NetworkEdge(
        'sslateingress@POST@/multicore#us_west_1#end',
        'corecontrast@POST@/multicore#us_west_1#start',
        network_latency=0
    ),
    NetworkEdge(
        'sslateingress@POST@/multicore#us_west_1#end',
        'corecontrast@POST@/multicore#us_east_1#start',
        network_latency=66
    ),
    NetworkEdge(
        'sslateingress@POST@/multicore#us_east_1#end',
        'corecontrast@POST@/multicore#us_west_1#start',
        network_latency=66
    ),
    NetworkEdge(
        'sslateingress@POST@/multicore#us_east_1#end',
        'corecontrast@POST@/multicore#us_east_1#start',
        network_latency=0
    ),
    NetworkEdge(
        'SOURCE#XXXX#end',
        'sslateingress@POST@/singlecore#us_west_1#start',
        network_latency=0
    ),
    NetworkEdge(
        'SOURCE#XXXX#end',
        'sslateingress@POST@/singlecore#us_east_1#start',
        network_latency=0
    ),
    NetworkEdge(
        'SOURCE#XXXX#end',
        'sslateingress@POST@/multicore#us_west_1#start',
        network_latency=0
    ),
    NetworkEdge(
        'SOURCE#XXXX#end',
        'sslateingress@POST@/multicore#us_east_1#start',
        network_latency=0
    ),
]

# Define the routing rules (loads on compute and network edges)
# Loads are set based on the LP constraints
# routing_rules = {
#     'compute_loads': {
#         ('sslateingress@POST@/multicore#us_east_1#start', 'sslateingress@POST@/multicore#us_east_1#end'): 200,
#         ('sslateingress@POST@/singlecore#us_east_1#start', 'sslateingress@POST@/singlecore#us_east_1#end'): 50,
#         ('sslateingress@POST@/multicore#us_west_1#start', 'sslateingress@POST@/multicore#us_west_1#end'): 200,
#         ('sslateingress@POST@/singlecore#us_west_1#start', 'sslateingress@POST@/singlecore#us_west_1#end'): 50,

#         ('corecontrast@POST@/singlecore#us_east_1#start', 'corecontrast@POST@/singlecore#us_east_1#end'): 100,
#         ('corecontrast@POST@/multicore#us_east_1#start', 'corecontrast@POST@/multicore#us_east_1#end'): 0,
#         ('corecontrast@POST@/singlecore#us_west_1#start', 'corecontrast@POST@/singlecore#us_west_1#end'): 0,
#         ('corecontrast@POST@/multicore#us_west_1#start', 'corecontrast@POST@/multicore#us_west_1#end'): 400,
#     },
#     'network_loads': {
#         ('sslateingress@POST@/singlecore#us_west_1#end', 'corecontrast@POST@/singlecore#us_west_1#start'): 0,
#         ('sslateingress@POST@/singlecore#us_west_1#end', 'corecontrast@POST@/singlecore#us_east_1#start'): 50,
#         ('sslateingress@POST@/singlecore#us_east_1#end', 'corecontrast@POST@/singlecore#us_west_1#start'): 0,
#         ('sslateingress@POST@/singlecore#us_east_1#end', 'corecontrast@POST@/singlecore#us_east_1#start'): 50,
#         ('sslateingress@POST@/multicore#us_west_1#end', 'corecontrast@POST@/multicore#us_west_1#start'): 200,
#         ('sslateingress@POST@/multicore#us_west_1#end', 'corecontrast@POST@/multicore#us_east_1#start'): 0,
#         ('sslateingress@POST@/multicore#us_east_1#end', 'corecontrast@POST@/multicore#us_west_1#start'): 200,
#         ('sslateingress@POST@/multicore#us_east_1#end', 'corecontrast@POST@/multicore#us_east_1#start'): 0,
#         ('SOURCE#XXXX#end', 'sslateingress@POST@/singlecore#us_west_1#start'): 50,
#         ('SOURCE#XXXX#end', 'sslateingress@POST@/singlecore#us_east_1#start'): 50,
#         ('SOURCE#XXXX#end', 'sslateingress@POST@/multicore#us_west_1#start'): 200,
#         ('SOURCE#XXXX#end', 'sslateingress@POST@/multicore#us_east_1#start'): 200,
#     }
# }

routing_rules = {
    'compute_loads': {
        ('sslateingress@POST@/multicore#us_east_1#start', 'sslateingress@POST@/multicore#us_east_1#end'): 200,
        ('sslateingress@POST@/singlecore#us_east_1#start', 'sslateingress@POST@/singlecore#us_east_1#end'): 50,
        ('sslateingress@POST@/multicore#us_west_1#start', 'sslateingress@POST@/multicore#us_west_1#end'): 200,
        ('sslateingress@POST@/singlecore#us_west_1#start', 'sslateingress@POST@/singlecore#us_west_1#end'): 50,

        ('corecontrast@POST@/singlecore#us_east_1#start', 'corecontrast@POST@/singlecore#us_east_1#end'): 100,
        ('corecontrast@POST@/multicore#us_east_1#start', 'corecontrast@POST@/multicore#us_east_1#end'): 57,
        ('corecontrast@POST@/singlecore#us_west_1#start', 'corecontrast@POST@/singlecore#us_west_1#end'): 0,
        ('corecontrast@POST@/multicore#us_west_1#start', 'corecontrast@POST@/multicore#us_west_1#end'): 344,
    },
    'network_loads': {
        ('sslateingress@POST@/singlecore#us_west_1#end', 'corecontrast@POST@/singlecore#us_west_1#start'): 0,
        ('sslateingress@POST@/singlecore#us_west_1#end', 'corecontrast@POST@/singlecore#us_east_1#start'): 50,
        ('sslateingress@POST@/singlecore#us_east_1#end', 'corecontrast@POST@/singlecore#us_west_1#start'): 0,
        ('sslateingress@POST@/singlecore#us_east_1#end', 'corecontrast@POST@/singlecore#us_east_1#start'): 50,
        ('sslateingress@POST@/multicore#us_west_1#end', 'corecontrast@POST@/multicore#us_west_1#start'): 200,
        ('sslateingress@POST@/multicore#us_west_1#end', 'corecontrast@POST@/multicore#us_east_1#start'): 0,
        ('sslateingress@POST@/multicore#us_east_1#end', 'corecontrast@POST@/multicore#us_west_1#start'): 144,
        ('sslateingress@POST@/multicore#us_east_1#end', 'corecontrast@POST@/multicore#us_east_1#start'): 57,
        ('SOURCE#XXXX#end', 'sslateingress@POST@/singlecore#us_west_1#start'): 50,
        ('SOURCE#XXXX#end', 'sslateingress@POST@/singlecore#us_east_1#start'): 50,
        ('SOURCE#XXXX#end', 'sslateingress@POST@/multicore#us_west_1#start'): 200,
        ('SOURCE#XXXX#end', 'sslateingress@POST@/multicore#us_east_1#start'): 200,
    }
}

def calculate_normalized_loads(compute_edges, routing_rules):
    """
    Calculate the normalized load for each node based on the sum of compute loads.

    Parameters:
    - compute_edges (list of ComputeEdge): List of compute edges.
    - routing_rules (dict): Dictionary containing 'compute_loads'.

    Returns:
    - normalized_loads (dict): Dictionary mapping node identifiers to their normalized loads.
    """
    normalized_loads = defaultdict(float)

    compute_loads = routing_rules['compute_loads']
    for edge in compute_loads:
        for e in compute_loads:
            s1 = edge[1].split("@")[0]
            r1 = edge[1].split("#")[1]
            s2 = e[1].split("@")[0]
            r2 = e[1].split("#")[1]
            if s1 == s2 and r1 == r2:
                normalized_loads[edge[0]] += compute_loads.get((e[0], e[1]), 0)
    
        

    return normalized_loads

def calculate_total_latency(compute_edges, network_edges, routing_rules):
    """
    Calculate the total latency based on the compute and network edges and their respective loads.

    Parameters:
    - compute_edges (list of ComputeEdge): List of compute edges.
    - network_edges (list of NetworkEdge): List of network edges.
    - routing_rules (dict): Dictionary containing 'compute_loads' and 'network_loads'.

    Returns:
    - total_latency (float): The calculated total latency.
    """
    total_latency = 0.0

    # Calculate normalized loads
    normalized_loads = calculate_normalized_loads(compute_edges, routing_rules)
    
    print("=== Normalized Loads Per Node ===\n")
    for node, n_load in normalized_loads.items():
        print(f"Node: {node}")
        print(f"  Normalized Load: {n_load}\n")

    # Calculate latency for compute edges
    print("=== Compute Edge Latencies ===\n")
    for edge in compute_edges:
        load = routing_rules['compute_loads'].get((edge.start, edge.end), 0)
        normalized_load = normalized_loads.get(edge.node, 0)
        latency = edge.compute_latency(normalized_load)
        contribution = latency * load
        total_latency += contribution
        if contribution > 0:
            print(f"Compute Edge: {edge.start} -> {edge.end}")
            print(f"  Load: {load}")
            print(f"  Associated Node: {edge.node}")
            print(f"  Normalized Load for Node: {normalized_load}")
            print(f"  Compute Latency: {latency:.6f}")
            print(f"  Contribution to Total Latency: {load} * ({edge.k} * {normalized_load}^2 + {edge.constant}) = {contribution:.6f}\n")

    # Calculate latency for network edges
    print("=== Network Edge Latencies ===\n")
    for edge in network_edges:
        load = routing_rules['network_loads'].get((edge.start, edge.end), 0)
        latency = edge.network_latency
        contribution = latency * load
        total_latency += contribution
        if contribution > 0:
            print(f"Network Edge: {edge.start} -> {edge.end}")
            print(f"  Load: {load}")
            print(f"  Network Latency: {latency}")
            print(f"  Contribution to Total Latency: {contribution}\n")

    return total_latency

def main():
    total_latency = calculate_total_latency(compute_edges, network_edges, routing_rules)
    print(f"Total Latency: {total_latency:.6f}")

if __name__ == "__main__":
    main()
