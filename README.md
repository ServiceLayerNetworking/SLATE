# SLATE: Service Layer Traffic Engineering

adiprerepa, gangmuk

This repository houses all the components of *Service Layer Traffic Engineering (SLATE)*, a system that globally optimizes the flow of requests for end-to-end application latency and cost deployed in multi-cluster (multi- zone/region/continent)

To find multi-cluster survey result, ```multicluster survey reult.pdf``` in the home directory of this repo.

There are three major components:
- Global controller: `/global-controller`
- Data plane: `/slate-plugin`
- Cluster controller: `/cluster-controller` (optional)


## WASM Note as of 9/7/2023
The way this wasm plugin works is kind of stupid. It uses the `OnTick()` callback provided by the ABI to send
real time stats to the cluster controller, and receives the new route recommendations. However, Envoy is run across
multiple worker threads, each of which host this VM. This means that the `OnTick()` callback is called multiple times,
and we currently have a racy way to ensure that only one of the threads actually sends the stats to the cluster controller.

I'm pretty stupid for not realizing *WASM SERVICES* existed, as singleton VMs that run on the main thread. This would
mean a lot of the overhead of making HTTP requests every second would be gone from the datapath (kind of), and we wouldn't 
have to do all sorts of racy stuff to ensure that only one of the threads sends the stats.

Long term, I think the architecture of this system should consist of two WASM plugins: one that is an HTTP WASM Filter
that collects RPS info/other metrics and enforces controller recommendations, and one that is a WASM Service that acts as
a stats sink and receives controller recommendations. The plugins would communicate through shared memory or the shared
message queues.

However, for the purposes of an IstioCon demo, the current architecture (while stupid) will have to do.
