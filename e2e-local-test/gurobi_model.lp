\ Model RequestRouting
\ LP format - for model browsing. Use MPS format to capture full model detail.
Minimize
  0 load_for_compute_edge2[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')]
   + 0 load_for_compute_edge2[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')]
   + 0 load_for_compute_edge2[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   + 0 load_for_compute_edge2[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   + 0 load_for_compute_edge2[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')]
   + 0 load_for_compute_edge2[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')]
   + 0 load_for_compute_edge2[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')]
   + 0 load_for_compute_edge2[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')]
   + 0 load_for_compute_edge2[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')]
   + 0 load_for_compute_edge2[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   + 0 load_for_compute_edge2[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')]
   + 0 load_for_compute_edge2[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')]
   + 0 load_for_compute_edge2[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')]
   + 0 load_for_compute_edge2[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')]
   + 0 load_for_compute_edge2[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   + 0 load_for_compute_edge2[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   + 0 load_for_compute_edge2[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')]
   + 0 load_for_compute_edge2[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')]
   + 0 load_for_compute_edge2[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')]
   + 0 load_for_compute_edge2[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')]
   + 0 load_for_compute_edge2[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')]
   + 0 load_for_compute_edge2[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   + 0 load_for_compute_edge2[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')]
   + 0 load_for_compute_edge2[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')]
   + 0 network_egress_cost[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_west_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_central_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_west_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')]
   + 0 network_egress_cost[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')]
   + 0 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')]
   + 0 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')]
   + 0 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_west_1#start')]
   + 0 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_central_1#start')]
   + 0 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_west_1#start')]
   + 0 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_central_1#start')]
   + [
   2 compute_latency[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')] * load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')]
   + 2 compute_latency[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')] * load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')]
   + 2 compute_latency[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')] * load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   + 2 compute_latency[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')] * load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   + 2 compute_latency[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')] * load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')]
   + 2 compute_latency[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')] * load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')]
   + 2 compute_latency[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')] * load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')]
   + 2 compute_latency[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')] * load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')]
   + 2 compute_latency[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')] * load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')]
   + 2 compute_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')] * load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   + 2 compute_latency[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')] * load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')]
   + 2 compute_latency[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')] * load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')]
   + 2 compute_latency[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')] * load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')]
   + 2 compute_latency[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')] * load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')]
   + 2 compute_latency[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')] * load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   + 2 compute_latency[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')] * load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   + 2 compute_latency[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')] * load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')]
   + 2 compute_latency[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')] * load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')]
   + 2 compute_latency[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')] * load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')]
   + 2 compute_latency[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')] * load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')]
   + 2 compute_latency[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')] * load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')]
   + 2 compute_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')] * load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   + 2 compute_latency[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')] * load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')]
   + 2 compute_latency[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')] * load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')]
   + 2 network_latency[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_west_1#start')] * load_for_network_edge[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_west_1#start')]
   + 2 network_latency[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_central_1#start')] * load_for_network_edge[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_central_1#start')]
   + 2 network_latency[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_west_1#start')] * load_for_network_edge[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_west_1#start')]
   + 2 network_latency[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_central_1#start')] * load_for_network_edge[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')]
   + 2 network_latency[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')] * load_for_network_edge[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')]
   + 2 network_latency[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')] * load_for_network_edge[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')]
   + 2 network_latency[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')] * load_for_network_edge[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')]
   + 2 network_latency[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')] * load_for_network_edge[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')]
   + 2 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')] * load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')]
   + 2 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')] * load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')]
   + 2 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_west_1#start')] * load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_west_1#start')]
   + 2 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_central_1#start')] * load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_central_1#start')]
   + 2 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_west_1#start')] * load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_west_1#start')]
   + 2 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_central_1#start')] * load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_central_1#start')]
   ] / 2 
Subject To
 normalized_load_('sslateingress@POST@/cart/checkout#us-central-1#start',_'sslateingress@POST@/cart/checkout#us-central-1#end'):
   - load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')]
   - load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')]
   + normalized_load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')]
   = 0
 normalized_load_('sslateingress@POST@/cart#us-central-1#start',_'sslateingress@POST@/cart#us-central-1#end'):
   - load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')]
   - load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')]
   + normalized_load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')]
   = 0
 normalized_load_('frontend@POST@/cart#us-central-1#start',_'frontend@POST@/cart#us-central-1#end'):
   - load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   - 0.7142857142857143 load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   + normalized_load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   = 0
 normalized_load_('frontend@POST@/cart/checkout#us-central-1#start',_'frontend@POST@/cart/checkout#us-central-1#end'):
   - 1.4 load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   - load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   + normalized_load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   = 0
 normalized_load_('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us-central-1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us-central-1#end'):
   - load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')]
   + normalized_load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')]
   = 0
 normalized_load_('cartservice@POST@/hipstershop.CartService/AddItem#us-central-1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us-central-1#end'):
   - load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')]
   - 0.7027406886858749 load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')]
   + normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')]
   = 0
 normalized_load_('cartservice@POST@/hipstershop.CartService/GetCart#us-central-1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us-central-1#end'):
   - 1.423 load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')]
   - load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')]
   + normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')]
   = 0
 normalized_load_('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us-central-1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us-central-1#end'):
   - load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')]
   + normalized_load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')]
   = 0
 normalized_load_('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us-central-1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us-central-1#end'):
   - load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')]
   + normalized_load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')]
   = 0
 normalized_load_('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us-central-1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us-central-1#end'):
   - load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   + normalized_load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   = 0
 normalized_load_('paymentservice@POST@/hipstershop.PaymentService/Charge#us-central-1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us-central-1#end'):
   - load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')]
   + normalized_load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')]
   = 0
 normalized_load_('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us-central-1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us-central-1#end'):
   - load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')]
   + normalized_load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')]
   = 0
 normalized_load_('sslateingress@POST@/cart/checkout#us-west-1#start',_'sslateingress@POST@/cart/checkout#us-west-1#end'):
   - load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')]
   - load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')]
   + normalized_load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')]
   = 0
 normalized_load_('sslateingress@POST@/cart#us-west-1#start',_'sslateingress@POST@/cart#us-west-1#end'):
   - load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')]
   - load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')]
   + normalized_load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')]
   = 0
 normalized_load_('frontend@POST@/cart#us-west-1#start',_'frontend@POST@/cart#us-west-1#end'):
   - load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   - 0.7142857142857143 load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   + normalized_load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   = 0
 normalized_load_('frontend@POST@/cart/checkout#us-west-1#start',_'frontend@POST@/cart/checkout#us-west-1#end'):
   - 1.4 load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   - load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   + normalized_load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   = 0
 normalized_load_('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us-west-1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us-west-1#end'):
   - load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')]
   + normalized_load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')]
   = 0
 normalized_load_('cartservice@POST@/hipstershop.CartService/AddItem#us-west-1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us-west-1#end'):
   - load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')]
   - 0.7027406886858749 load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')]
   + normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')]
   = 0
 normalized_load_('cartservice@POST@/hipstershop.CartService/GetCart#us-west-1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us-west-1#end'):
   - 1.423 load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')]
   - load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')]
   + normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')]
   = 0
 normalized_load_('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us-west-1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us-west-1#end'):
   - load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')]
   + normalized_load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')]
   = 0
 normalized_load_('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us-west-1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us-west-1#end'):
   - load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')]
   + normalized_load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')]
   = 0
 normalized_load_('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us-west-1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us-west-1#end'):
   - load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   + normalized_load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   = 0
 normalized_load_('paymentservice@POST@/hipstershop.PaymentService/Charge#us-west-1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us-west-1#end'):
   - load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')]
   + normalized_load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')]
   = 0
 normalized_load_('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us-west-1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us-west-1#end'):
   - load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')]
   + normalized_load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')]
   = 0
 cluster_us-central-1_load_in_sslateingress@POST@/cart:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_central_1#start')]
   = 150
 cluster_us-west-1_load_in_sslateingress@POST@/cart:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_west_1#start')]
   = 150
 cluster_us-central-1_load_in_sslateingress@POST@/cart/checkout:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_central_1#start')]
   = 200
 cluster_us-west-1_load_in_sslateingress@POST@/cart/checkout:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_west_1#start')]
   = 400
 source:
   load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_west_1#start')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_central_1#start')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_west_1#start')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_central_1#start')]
   = 900
 flow_conservation-start_node-sslateingress@POST@/cart/checkout:
   - load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_central_1#start')]
   = 0
 flow_conservation-start_node-sslateingress@POST@/cart:
   - load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_central_1#start')]
   = 0
 flow_conservation-start_node-frontend@POST@/cart:
   - load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   + load_for_network_edge[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_central_1#start')]
   + load_for_network_edge[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_central_1#start')]
   = 0
 flow_conservation-start_node-frontend@POST@/cart/checkout:
   - load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   + load_for_network_edge[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')]
   + load_for_network_edge[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')]
   = 0
 flow_conservation-start_node-productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct:
   - load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')]
   + load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')]
   + load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')]
   = 0
 flow_conservation-start_node-cartservice@POST@/hipstershop.CartService/AddItem:
   - load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')]
   + load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')]
   + load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')]
   = 0
 flow_conservation-start_node-cartservice@POST@/hipstershop.CartService/GetCart:
   - load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')]
   = 0
 flow_conservation-start_node-emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation:
   - load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')]
   = 0
 flow_conservation-start_node-recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations:
   - load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')]
   = 0
 flow_conservation-start_node-checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder:
   - load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')]
   = 0
 flow_conservation-start_node-paymentservice@POST@/hipstershop.PaymentService/Charge:
   - load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')]
   = 0
 flow_conservation-start_node-currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies:
   - load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')]
   = 0
 flow_conservation-start_node-sslateingress@POST@/cart/checkout:
   - load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_west_1#start')]
   = 0
 flow_conservation-start_node-sslateingress@POST@/cart:
   - load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')]
   + load_for_network_edge[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_west_1#start')]
   = 0
 flow_conservation-start_node-frontend@POST@/cart:
   - load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   + load_for_network_edge[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_west_1#start')]
   + load_for_network_edge[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_west_1#start')]
   = 0
 flow_conservation-start_node-frontend@POST@/cart/checkout:
   - load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   + load_for_network_edge[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')]
   + load_for_network_edge[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')]
   = 0
 flow_conservation-start_node-productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct:
   - load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')]
   + load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')]
   + load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')]
   = 0
 flow_conservation-start_node-cartservice@POST@/hipstershop.CartService/AddItem:
   - load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')]
   + load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')]
   + load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')]
   = 0
 flow_conservation-start_node-cartservice@POST@/hipstershop.CartService/GetCart:
   - load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')]
   = 0
 flow_conservation-start_node-emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation:
   - load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')]
   = 0
 flow_conservation-start_node-recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations:
   - load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')]
   = 0
 flow_conservation-start_node-checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder:
   - load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')]
   = 0
 flow_conservation-start_node-paymentservice@POST@/hipstershop.PaymentService/Charge:
   - load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')]
   + load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')]
   = 0
 flow_conservation-start_node-currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies:
   - load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')]
   + load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-b292c3dd:
   load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')]
   - load_for_network_edge[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_west_1#start')]
   - load_for_network_edge[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-b292c3dd:
   load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')]
   - load_for_network_edge[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_west_1#start')]
   - load_for_network_edge[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-b292c3dd:
   load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   - load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-b292c3dd:
   load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   - load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-b292c3dd:
   load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   - load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-b292c3dd:
   load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   - load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')]
   - load_for_network_edge[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')]
   - load_for_network_edge[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')]
   - load_for_network_edge[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')]
   - load_for_network_edge[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')]
   - load_for_network_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')]
   = 0
 flow_conservation-nonleaf_endnode-c5f11459:
   load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')]
   - load_for_network_edge[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')]
   = 0
 latency_function_('sslateingress@POST@/cart/checkout#us-central-1#start',_'sslateingress@POST@/cart/checkout#us-central-1#end'):
   compute_latency[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')]
   + [
   - 9.32311e-06 normalized_load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')] ^2
   ] = 1.622480578628564
 latency_function_('sslateingress@POST@/cart#us-central-1#start',_'sslateingress@POST@/cart#us-central-1#end'):
   compute_latency[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')]
   + [
   - 1.91897e-06 normalized_load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')] ^2
   ] = 1.639923485812918
 latency_function_('frontend@POST@/cart#us-central-1#start',_'frontend@POST@/cart#us-central-1#end'):
   compute_latency[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')]
   + [
   - 2.46585e-06 normalized_load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')] ^2
   ] = 0.6910597027495876
 latency_function_('frontend@POST@/cart/checkout#us-central-1#start',_'frontend@POST@/cart/checkout#us-central-1#end'):
   compute_latency[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')]
   + [
   - 0.000156891 normalized_load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')] ^2
   ] = 1
 latency_function_('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us-central-1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us-central-1#end'):
   compute_latency[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')]
   + [
   - 1.55298e-07 normalized_load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')] ^2
   ] = 0.8767966096508572
 latency_function_('cartservice@POST@/hipstershop.CartService/AddItem#us-central-1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us-central-1#end'):
   compute_latency[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')]
   + [
   - 8.25696e-07 normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')] ^2
   ] = 1.368473797558095
 latency_function_('cartservice@POST@/hipstershop.CartService/GetCart#us-central-1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us-central-1#end'):
   compute_latency[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')]
   + [
   - 9.27183e-06 normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')] ^2
   ] = 0.5015571668249245
 latency_function_('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us-central-1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us-central-1#end'):
   compute_latency[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')]
   + [
   - 7.14276e-06 normalized_load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')] ^2
   ] = 0.4405435686721614
 latency_function_('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us-central-1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us-central-1#end'):
   compute_latency[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')]
   + [
   - 4.12164e-05 normalized_load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')] ^2
   ] = 1
 latency_function_('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us-central-1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us-central-1#end'):
   compute_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')]
   + [
   - 1.9178427411229999e-04 normalized_load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')] ^2
   ] = 1
 latency_function_('paymentservice@POST@/hipstershop.PaymentService/Charge#us-central-1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us-central-1#end'):
   compute_latency[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')]
   + [
   - 3.73038e-06 normalized_load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')] ^2
   ] = 0.8099851884675366
 latency_function_('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us-central-1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us-central-1#end'):
   compute_latency[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')]
   + [
   - 9.74485e-06 normalized_load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')] ^2
   ] = 1
 latency_function_('sslateingress@POST@/cart/checkout#us-west-1#start',_'sslateingress@POST@/cart/checkout#us-west-1#end'):
   compute_latency[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')]
   + [
   - 9.32311e-06 normalized_load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')] ^2
   ] = 1.622480578628564
 latency_function_('sslateingress@POST@/cart#us-west-1#start',_'sslateingress@POST@/cart#us-west-1#end'):
   compute_latency[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')]
   + [
   - 1.91897e-06 normalized_load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')] ^2
   ] = 1.639923485812918
 latency_function_('frontend@POST@/cart#us-west-1#start',_'frontend@POST@/cart#us-west-1#end'):
   compute_latency[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')]
   + [
   - 2.46585e-06 normalized_load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')] ^2
   ] = 0.6910597027495876
 latency_function_('frontend@POST@/cart/checkout#us-west-1#start',_'frontend@POST@/cart/checkout#us-west-1#end'):
   compute_latency[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')]
   + [
   - 0.000156891 normalized_load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')] ^2
   ] = 1
 latency_function_('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us-west-1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us-west-1#end'):
   compute_latency[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')]
   + [
   - 1.55298e-07 normalized_load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')] ^2
   ] = 0.8767966096508572
 latency_function_('cartservice@POST@/hipstershop.CartService/AddItem#us-west-1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us-west-1#end'):
   compute_latency[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')]
   + [
   - 8.25696e-07 normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')] ^2
   ] = 1.368473797558095
 latency_function_('cartservice@POST@/hipstershop.CartService/GetCart#us-west-1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us-west-1#end'):
   compute_latency[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')]
   + [
   - 9.27183e-06 normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')] ^2
   ] = 0.5015571668249245
 latency_function_('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us-west-1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us-west-1#end'):
   compute_latency[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')]
   + [
   - 7.14276e-06 normalized_load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')] ^2
   ] = 0.4405435686721614
 latency_function_('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us-west-1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us-west-1#end'):
   compute_latency[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')]
   + [
   - 4.12164e-05 normalized_load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')] ^2
   ] = 1
 latency_function_('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us-west-1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us-west-1#end'):
   compute_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')]
   + [
   - 1.9178427411229999e-04 normalized_load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')] ^2
   ] = 1
 latency_function_('paymentservice@POST@/hipstershop.PaymentService/Charge#us-west-1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us-west-1#end'):
   compute_latency[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')]
   + [
   - 3.73038e-06 normalized_load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')] ^2
   ] = 0.8099851884675366
 latency_function_('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us-west-1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us-west-1#end'):
   compute_latency[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')]
   + [
   - 9.74485e-06 normalized_load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')] ^2
   ] = 1
Bounds
 load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')] <= 100000
 load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')] <= 100000
 load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')] <= 100000
 load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')] <= 100000
 load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')] <= 100000
 load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')] <= 100000
 load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')] <= 100000
 load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')] <= 100000
 load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')] <= 100000
 load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')] <= 100000
 load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')] <= 100000
 load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')] <= 100000
 load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')] <= 100000
 load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')] <= 100000
 load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')] <= 100000
 load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')] <= 100000
 load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')] <= 100000
 load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')] <= 100000
 load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')] <= 100000
 load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')] <= 100000
 load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')] <= 100000
 load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')] <= 100000
 load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')] <= 100000
 load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_central_1#start',_'sslateingress@POST@/cart/checkout#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('sslateingress@POST@/cart#us_central_1#start',_'sslateingress@POST@/cart#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('frontend@POST@/cart#us_central_1#start',_'frontend@POST@/cart#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('frontend@POST@/cart/checkout#us_central_1#start',_'frontend@POST@/cart/checkout#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#end')] <= 100000
 normalized_load_for_compute_edge[('sslateingress@POST@/cart/checkout#us_west_1#start',_'sslateingress@POST@/cart/checkout#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('sslateingress@POST@/cart#us_west_1#start',_'sslateingress@POST@/cart#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('frontend@POST@/cart#us_west_1#start',_'frontend@POST@/cart#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('frontend@POST@/cart/checkout#us_west_1#start',_'frontend@POST@/cart/checkout#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#end')] <= 100000
 normalized_load_for_compute_edge[('currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#end')] <= 100000
 network_latency[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_west_1#start')] = 0
 network_latency[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_central_1#start')] = 30
 network_latency[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_west_1#start')] = 30
 network_latency[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_central_1#start')] = 0
 network_latency[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')] = 0
 network_latency[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')] = 30
 network_latency[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')] = 30
 network_latency[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')] = 0
 network_latency[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')] = 0
 network_latency[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')] = 30
 network_latency[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')] = 30
 network_latency[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')] = 0
 network_latency[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')] = 0
 network_latency[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')] = 30
 network_latency[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')] = 30
 network_latency[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')] = 0
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')] = 0
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')] = 30
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')] = 30
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')] = 0
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')] = 0
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')] = 30
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')] = 30
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')] = 0
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')] = 0
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')] = 30
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')] = 30
 network_latency[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')] = 0
 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')] = 0
 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')] = 30
 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')] = 30
 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')] = 0
 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')] = 0
 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')] = 30
 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')] = 30
 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')] = 0
 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')] = 0
 network_latency[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')] = 30
 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')] = 30
 network_latency[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')] = 0
 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_west_1#start')] = 0
 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_central_1#start')] = 0
 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_west_1#start')] = 0
 network_latency[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_central_1#start')] = 0
 network_egress_cost[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_west_1#start')] = 0
 network_egress_cost[('sslateingress@POST@/cart#us_west_1#end',_'frontend@POST@/cart#us_central_1#start')] = 2000
 network_egress_cost[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_west_1#start')] = 2000
 network_egress_cost[('sslateingress@POST@/cart#us_central_1#end',_'frontend@POST@/cart#us_central_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')] = 5.2
 network_egress_cost[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_west_1#start')] = 5.2
 network_egress_cost[('frontend@POST@/cart#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/AddItem#us_central_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart#us_west_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')] = 1246.87
 network_egress_cost[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_west_1#start')] = 1246.87
 network_egress_cost[('frontend@POST@/cart#us_central_1#end',_'productcatalogservice@POST@/hipstershop.ProductCatalogService/GetProduct#us_central_1#start')] = 0
 network_egress_cost[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')] = 0
 network_egress_cost[('sslateingress@POST@/cart/checkout#us_west_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')] = 2000
 network_egress_cost[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_west_1#start')] = 2000
 network_egress_cost[('sslateingress@POST@/cart/checkout#us_central_1#end',_'frontend@POST@/cart/checkout#us_central_1#start')] = 0
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')] = 0
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')] = 54.83
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_west_1#start')] = 54.83
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'cartservice@POST@/hipstershop.CartService/GetCart#us_central_1#start')] = 0
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')] = 0
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')] = 60.32
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_west_1#start')] = 60.32
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'emailservice@POST@/hipstershop.EmailService/SendOrderConfirmation#us_central_1#start')] = 0
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')] = 0
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')] = 10.55
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_west_1#start')] = 10.55
 network_egress_cost[('checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#end',_'paymentservice@POST@/hipstershop.PaymentService/Charge#us_central_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')] = 18.32
 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_west_1#start')] = 18.32
 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'checkoutservice@POST@/hipstershop.CheckoutService/PlaceOrder#us_central_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')] = 1024
 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_west_1#start')] = 1024
 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'currencyservice@POST@/hipstershop.CurrencyService/GetSupportedCurrencies#us_central_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')] = 0
 network_egress_cost[('frontend@POST@/cart/checkout#us_west_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')] = 54.42
 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_west_1#start')] = 54.42
 network_egress_cost[('frontend@POST@/cart/checkout#us_central_1#end',_'recommendationservice@POST@/hipstershop.RecommendationService/ListRecommendations#us_central_1#start')] = 0
 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_west_1#start')] = 0
 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/cart#us_central_1#start')] = 0
 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_west_1#start')] = 0
 network_egress_cost[('SOURCE#XXXX#end',_'sslateingress@POST@/cart/checkout#us_central_1#start')] = 0
End
