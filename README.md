# SLATE: Service Layer Traffic Engineering

adiprerepa, gangmuk

This repository houses all the components of *Service Layer Traffic Engineering (SLATE)*, a system that globally optimizes the flow of requests for end-to-end application latency and cost deployed in multi-region enviroments.

To find the multi-cluster survey results, go to ```multicluster survey reult.pdf``` in the home directory of this repo.

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

## Results

We benchmark on three applications: [Hotel Reservation](https://github.com/delimitrou/DeathStarBench/blob/master/hotelReservation), [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo), and [Alibaba](https://github.com/alibaba/clusterdata).

HotelReservation:


![Hotel](docs/even_wrk-routing_rules_cdf/even_wrk-routing_rules_cdf_page-0001.jpg)


Online Boutique:


![Online](docs/uneven_wrk-routing_rules_cdf-1/uneven_wrk-routing_rules_cdf%20(1)_page-0001.jpg)


Alibaba:


![Alibaba](docs/uneven_wrk-routing_rules_cdf/uneven_wrk-routing_rules_cdf_page-0001.jpg)
