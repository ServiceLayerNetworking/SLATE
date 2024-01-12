import datetime
import os

def get_cur_time():
    return datetime.datetime.now().strftime("%Y%m%d_%H:%M:%S")

log_prefix="[SLATE]"

#######################
## Global controller ##
#######################
PRINT_TRACE=False
NUM_CLUSTER = 2 # NOTE: hardcoded
MODE="PROFILE" # PROFILE, SLATE, LOCAL_ROUTING


###############
## Optimizer ##
###############
VERBOSITY=1
DELIMITER="#"
OUTPUT_WRITE=False
FAKE_DATA=True
init_time = get_cur_time()
OUTPUT_DIR="./optimizer_output/"+init_time
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
DISPLAY=True
PLOT=True
PLOT_ALL=False
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
DOLLAR_PER_MS = 0.001

#################
## Time stitch ##
#################

