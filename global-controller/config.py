log_prefix="[SLATE]"


###############
## Optimizer ##
###############
OUTPUT_DIR = "./optimizer_output/"
VERBOSITY=1
DELIMITER="#"
OUTPUT_WRITE=False
DISPLAY=False
GRAPHVIZ=False
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

intra_cluster_network_rtt = 1
inter_cluster_network_rtt = 40


#################
## Time stitch ##
#################
