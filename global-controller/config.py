import pandas as pd
import span as sp

log_prefix="[SLATE]"

#######################
## Global controller ##
#######################
PRINT_TRACE=False
NUM_CLUSTER = 2
ACTUAL_LOAD=True
SLATE_ON=1
USE_PRERECORDED_TRACE=1
USE_TRACE_FILE=0
USE_MODEL_DIRECTLY=0
if USE_PRERECORDED_TRACE:
    TRACE_PATH="/app/sampled_both_trace.txt"
    df = pd.read_csv(TRACE_PATH)
    pre_recorded_trace = sp.df_to_trace(df)
    PROF_DURATION = 10 # in seconds
elif USE_TRACE_FILE:
    # TRACE_FILE_PATH="/app/new_trace.txt"
    # TRACE_FILE_PATH="/app/trace-west_only-avg_load.csv"
    TRACE_FILE_PATH="/app/wrk_prof_log2_west.txt"
    PROF_DURATION = 10 # in seconds
elif USE_MODEL_DIRECTLY:
    MODEL_DICT = {"productpage-v1": {"slope:":154,  "intercetp":130}, \
                      "ratings-v1": {"slope" :0.0,  "intercetp":1.3}, \
                      "details-v1": {"slope" :0.0,  "intercetp":6.2}, \
                      "reviews-v3": {"slope" :0.3,  "intercetp":5.0}, \
                      "ingress_gw": {"slope" :0.0,  "intercetp":0.0} }
else:  
    TRACE_FILE_PATH=None
    # PROF_DURATION = 40 # in seconds, hey
    PROF_DURATION = 350 # in seconds, wrk2 (30*20)*7 =350
MIN_NUM_TRACE = 30


###############
## Optimizer ##
###############
OUTPUT_DIR="./optimizer_output/"
VERBOSITY=1
DELIMITER="#"
OUTPUT_WRITE=False
DISPLAY=False
PLOT=False
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

