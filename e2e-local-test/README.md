# End-to-end local test

This is to run the end-to-end SLATE global controller with trace file. E2E means including trace parsing, initializing all data structures (endpoints, placement, etc.), running curve fitting for latency of each traffic class, running optimizer with them, and output the routing result.

```bash
python global_controller.py <trace_file>
```

for example,
```bash
python global_controller.py onlineboutique-trace.csv
```