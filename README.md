# [SLATE: Service Layer Traffic Engineering](https://servicelayernetworking.github.io/slate.html)

This repository houses all the components of *Service Layer Traffic Engineering (SLATE)*, a system that globally optimizes the flow of requests for end-to-end application latency and cost deployed in multi-region enviroments.

[*See the NSDI '26 Paper*](https://www.usenix.org/conference/nsdi26/presentation/lim) 🚀🚀🚀🚀🚀

[*See the HotNets '24 Paper*](https://conferences.sigcomm.org/hotnets/2024/papers/hotnets24-107.pdf) 🚀🚀🚀🚀🚀


To find the multi-cluster survey results, go to ```multicluster survey result.pdf``` in the home directory of this repo.

There are three major components:
- Global controller: `/global-controller`
- Data plane: `/wasm-plugins/slate-plugin`
- Cluster controller: `/cluster-controller` (optional)

![SLATE Architecture](docs/slate_arch.jpg)

This system is tested on Istio.

The workflow is as such:
- The data plane in every region collects realtime metrics about current load (RPS) and experienced latency of those requests.
- The global controller builds a load to latency model for each service over time. When feasible, it uses this model in a Mixed-Integer Linear Program and solves for optimal request flow, minimizing latency. This solution is expressed as rules that are pushed to the data plane.
- The data plane enforces these rules.


```
@inproceedings {316074,
author = {Gangmuk Lim and Aditya Prerepa and Brighten Godfrey and Radhika Mittal},
title = {{SLATE}: Service Layer Traffic Engineering},
booktitle = {23rd USENIX Symposium on Networked Systems Design and Implementation (NSDI 26)},
year = {2026},
isbn = {978-1-939133-54-0},
address = {Renton, WA},
pages = {1895--1918},
url = {https://www.usenix.org/conference/nsdi26/presentation/lim},
publisher = {USENIX Association},
month = may
}
```

```
@inproceedings{lim2024opportunities,
  title={Opportunities and Challenges in Service Layer Traffic Engineering},
  author={Lim, Gangmuk and Prerepa, Aditya and Godfrey, Brighten and Mittal, Radhika},
  booktitle={Proceedings of the 23rd ACM Workshop on Hot Topics in Networks},
  pages={352--359},
  year={2024}
}
```


