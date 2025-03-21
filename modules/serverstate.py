from enum import Enum


# Define server states for better status tracking
class ServerState(Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRASHED = "CRASHED"
