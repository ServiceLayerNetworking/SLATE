# How to use scalability test

The purpose of this directory is to test the scalability of the SLATE optimizer with different application topologies and cluster network topologies.

The scalability will depend on many variables
- number of clusters
- application topology, depth and width(fanout)
- total number of traffic classes
- the model of the latency function used in the optimizer (1 degree linear regression, 2 degree polynomial regression, mm1 model, etc.)
- maybe more

<!-- There are two different ways to run standalone optimizer. -->
One is fully configurable. You can define any application topology and any cluster network topology you want, etc.
<!-- The other is to run with trace file. It will run read trace file, fitting latency functions to run optimizer. -->

## Run with configured app and clusters

```bash
python global_controller.py 4 2 4 3 1
```

global_controller.py
- num_cluster = int(sys.argv[1])
- num_callgraph = int(sys.argv[2])
- depth = int(sys.argv[3])
- fanout = int(sys.argv[4])
- degree_ = int(sys.argv[5])

<!-- or

THIS IS NOT COMPLETED YET. DON'T USE IT.
```bash
python run_optimizer.py
``` -->
