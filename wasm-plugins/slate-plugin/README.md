# SLATE Data Plane

The SLATE Data Plane is implemented as an HTTP filter, abiding by the [proxy-wasm](https://github.com/proxy-wasm/spec) interface. It's main functions are:
1) Load and latency collection & reporting
2) Routing rule enforcement

To better understand this code, you must understand [Envoy's Threading Model](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/intro/threading_model), and how [Filters/WASM work](https://github.com/tetratelabs/proxy-wasm-go-sdk/blob/main/doc/OVERVIEW.md) (see some nice examples [here](https://github.com/tetratelabs/proxy-wasm-go-sdk/)).

From now on: Slate Data Plane: slate-proxy.

## Load/Latency collection

For every *inbound* request processed by slate-proxy, we want to record the load (RPS) at the time that request arrived (which is just the number of requests in the last second), along with the processing time of that request. This helps train the model in the global controller. Load means load of *every endpoint*.

We heavily utilized the shared data interface, so each thread can have an up-to-date view of load conditions. To know what the load of each request type, we keep a *per-endpoint rotating shared queue* which is stored as a bytearray in the proxy shared memory. When a request enters slate-proxy, the time of its arrival is added to the queue, and all entries which are older than 1 second before the current time are evicted.

Because we are memory constrained and want to reduce the number of transfers from proxy shared memory to thread-local memory in the request path, this shared queue logic is heavily optimized. Reading the length of this queue (to understand load conditions) is simply two reads to variables representing the start and end positions of the queue in memory, and doing some arithmetic to get queue size (see `TimestampListGetRPS`). The much more complicated logic of adding an entry to this queue is in `TimestampListAdd`, where a new load time is added and all old entries are evicted, updating the queue read and write positions. This logic includes rotating this shared queue if reaching the end of the memory region, and all sorts of race condition handling. It seems to work under high load, so I wouldn't recommend changing it unless you know what you are doing.

## Load reporting

Every `TICK_PERIOD`, an HTTP call is made from whichever thread claims the network mutex (essentially updating the `KEY_LAST_RESET`). This is done in a custom format (see `gangmuk_api.md`). Tinygo does not allow for protobuf and JSON serialization/deserialization, hence the custom format. This call has a timeout of 5s, and is made to the `slate-controller` cluster (automatically populated by Istio). The return of this call is handled by the callback `OnTickHttpCallResponse`, in which new routing rules are sent and persisted in shared memory. 

## Routing Rule enforcement

For every *outbound* request (to another service), slate-proxy checks for the routing rules pertaining to that request in the shared memory. If the rules exist (they exist as a distribution of regions -> percentages), slate-proxy draws from this distribution. Based on the results of this draw, it sets the `x-slate-routeto` header, which controls which cluster the outbound request is then routed to.


