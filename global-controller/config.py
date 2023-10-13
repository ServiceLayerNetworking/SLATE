log_prefix="[SLATE]"


###############
## Optimizer ##
###############
OUTPUT_DIR = "./optimizer_output/"
VERBOSITY=1
DELIMITER="#"
OUTPUT_WRITE=False
DISPLAY=False
GRAPHVIZ=True
INGRESS_GW_NAME = "ingress_gw"
# ENTRANCE = tst.FRONTEND_svc
ENTRANCE = INGRESS_GW_NAME
PRODUCTPAGE_ONLY = False
if PRODUCTPAGE_ONLY:
    assert ENTRANCE == INGRESS_GW_NAME
SAME_COMPUTE_TIME = False
LOAD_IN = True
ALL_PRODUCTPAGE=False
REAL_DATA=True
REGRESSOR_DEGREE = 1 # 1: linear, >2: polynomial
APP_NAME = "bookinfo"

INTRA_CLUTER_RTT = 1
INTER_CLUSTER_RTT = 40
# DOLLAR_PER_MS: value of latency
DOLLAR_PER_MS = 0.00001
# DOLLAR_PER_MS = 0.001
# DOLLAR_PER_MS = 1

#################
## Time stitch ##
#################
