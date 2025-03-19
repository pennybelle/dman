from enum import Enum


# Define server states for better status tracking
class ServerState(Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WARNING = "WARNING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"
    CRASHED = "CRASHED"


# RCON Constants
SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0
