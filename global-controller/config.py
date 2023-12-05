import datetime

log_prefix="[SLATE]"

#######################
## Global controller ##
#######################
PRINT_TRACE=False
NUM_CLUSTER = 2
ACTUAL_LOAD=True
SLATE_ON=1
REAL_DATA=True
USE_PRERECORDED_TRACE=1
USE_TRACE_FILE=0
USE_MODEL_DIRECTLY=0
# if USE_MODEL_DIRECTLY:
#     MODEL_DICT = {"productpage-v1": {"slope:":154,  "intercetp":130}, \
#                       "ratings-v1": {"slope" :0.0,  "intercetp":1.3}, \
#                       "details-v1": {"slope" :0.0,  "intercetp":6.2}, \
#                       "reviews-v3": {"slope" :0.3,  "intercetp":5.0}, \
#                       "ingress_gw": {"slope" :0.0,  "intercetp":0.0} }
# else:  
#     TRACE_FILE_PATH=None
#     # PROF_DURATION = 40 # in seconds, hey
#     PROF_DURATION = 350 # in seconds, wrk2 (30*20)*7 =350
MIN_NUM_TRACE = 30


###############
## Optimizer ##
###############
VERBOSITY=1
DELIMITER="#"
OUTPUT_WRITE=True
cur_time = datetime.datetime.now().strftime("%Y%m%d_%H:%M:%S")
OUTPUT_DIR="./optimizer_output/"+cur_time
DISPLAY=True
PLOT=False
GRAPHVIZ=True

INGRESS_GW_NAME="ingress_gw"
# ENTRANCE = tst.FRONTEND_svc
ENTRANCE=INGRESS_GW_NAME
SAME_COMPUTE_TIME=False
LOAD_IN=True
ALL_PRODUCTPAGE=False
REGRESSOR_DEGREE=1 # 1: linear, >2: polynomial
APP_NAME="bookinfo"

INTRA_CLUTER_RTT=1
INTER_CLUSTER_RTT=10
INTER_CLUSTER_EGRESS_COST=1
# DOLLAR_PER_MS: value of latency
# DOLLAR_PER_MS = 0.00001
# DOLLAR_PER_MS=0.001
DOLLAR_PER_MS = 1

#################
## Time stitch ##
#################

