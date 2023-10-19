log_prefix="[SLATE]"


#######################
## Global controller ##
#######################
PRINT_TRACE=True
NUM_CLUSTER = 2
ACTUAL_LOAD=True
SLATE_ON=1
USE_TRACE_FILE=0
if USE_TRACE_FILE:
    # TRACE_FILE_PATH="/app/new_trace.txt"
    TRACE_FILE_PATH="/app/trace-west_only-avg_load.csv"
    PROF_DURATION = 5 # in seconds
else:
    TRACE_FILE_PATH=None
    # PROF_DURATION = 40 # in seconds, hey
    PROF_DURATION = 300 # in seconds, wrk2
MIN_NUM_TRACE = 30


###############
## Optimizer ##
###############
OUTPUT_DIR="./optimizer_output/"
VERBOSITY=1
DELIMITER="#"
OUTPUT_WRITE=False
DISPLAY=False
GRAPHVIZ=False
INGRESS_GW_NAME="ingress_gw"
# ENTRANCE = tst.FRONTEND_svc
ENTRANCE=INGRESS_GW_NAME
PRODUCTPAGE_ONLY=False
if PRODUCTPAGE_ONLY:
    assert ENTRANCE == INGRESS_GW_NAME
SAME_COMPUTE_TIME=False
LOAD_IN=True
ALL_PRODUCTPAGE=False
REAL_DATA=True
REGRESSOR_DEGREE=1 # 1: linear, >2: polynomial
APP_NAME="bookinfo"

INTRA_CLUTER_RTT=1
INTER_CLUSTER_RTT=40
# DOLLAR_PER_MS: value of latency
# DOLLAR_PER_MS = 0.00001
DOLLAR_PER_MS=0.001
# DOLLAR_PER_MS = 1

#################
## Time stitch ##
#################
