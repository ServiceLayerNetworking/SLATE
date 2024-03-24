import datetime
import os

def get_cur_time():
    return datetime.datetime.now().strftime("%Y%m%d_%H:%M:%S")


############
## LOGGER ##
############
# log_prefix="[SLATE]"
log_prefix=""

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            # 'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'format': '%(name)s - %(funcName)s(line:%(lineno)d) - %(message)s',
        },
    },
    'handlers': {
        'default': {
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
        },
        'error_file': {  # New handler for error level logs
            'level': 'ERROR',
            'formatter': 'standard',
            'class': 'logging.FileHandler',
            'filename': 'error.log',  # File to log errors
            'mode': 'a',  # Append mode
        },
    },
    'loggers': {
        '': {  # root logger
            'handlers': ['default', 'error_file'],
            'level': 'INFO',
            'propagate': True
        },
        'gurobipy.gurobipy': {  # specifically targeting the gurobipy.gurobipy logger
            'handlers': ['default'],  # It's optional in this case since we're only adjusting the level
            'level': 'CRITICAL',  # Set to 'CRITICAL' to suppress all lower severity logs
            'propagate': False  # Prevents the log messages from being propagated to ancestor loggers
        }
    }
}

#######################
## Global controller ##
#######################
PRINT_TRACE=False
NUM_CLUSTER = 2 # NOTE: hardcoded
MODE="PROFILE" # PROFILE, SLATE, LOCAL_ROUTING
between_ep = "|" # svc@method@url|svc@method@url
ep_del = "@" # svc@method@url

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

# intra_CLUSTER_NETWORK_LATENCY=0.5 # oneway
# INTER_CLUSTER_NETWORK_LATENCY=20 # oneway
INTER_CLUSTER_EGRESS_COST=1
# DOLLAR_PER_MS: value of latency
# DOLLAR_PER_MS = 0.00001
# DOLLAR_PER_MS=0.001
DOLLAR_PER_MS = 0.001

#################
## Time stitch ##
#################

