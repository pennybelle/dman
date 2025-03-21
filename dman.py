# this script/program is a WIP and the code isnt great
# but i plan to put a lot into this and i'll learn as i go
# please consider contributing to the project by opening a PR

# my goal is to have a CLI-only menu-based program that can be scaled
# to maange and run as many servers as your hardware can handle.
# i have 4 years of experience dealing with dayz's weirdness and im hoping
# to use that experience to make other people's lives a bit easier

import os
import re
import struct
import socket
import threading
import subprocess
import asyncio
import logging
import shutil
import time
import datetime
import toml


from subprocess import Popen, PIPE, check_output
from shutil import copyfile, copytree
from sys import exit
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from __logger__ import setup_logger
from modules.main_menu import main_menu, title_screen
from modules.constants_classes import (
    ServerState,
    SERVERDATA_AUTH,
    SERVERDATA_AUTH_RESPONSE,
    SERVERDATA_EXECCOMMAND,
    # SERVERDATA_RESPONSE_VALUE,
)

log = logging.getLogger(__name__)
setup_logger(level=10, stream_logs=False)

log.info("######################## STARTING FROM THE TOP ########################")

## LEVELS ##
# 10: DEBUG
# 20: INFO
# 30: WARNING
# 40: ERROR
# 50: CRITICAL

# log.debug("This is a debug log")
# log.info("This is an info log")
# log.warning("This is a warn log")
# log.critical("This is a criticallog")


# Dictionary to track server states
server_states = {}
# cached_states = {}


def get_console_size():
    # gather raw output from console
    # console_width = check_output(["stty", "size"], stdout=PIPE)
    # format raw data into int
    # console_width = int(console_width.communicate().decode())

    console_size = check_output(["stty", "size"]).decode("utf-8").split()
    h = int(console_size[0])
    w = int(console_size[1])

    return w, h


class RCONClient:
    """Simple RCON client implementation for DayZ servers"""

    def __init__(self, port, password, host="127.0.0.1"):
        self.host = host
        self.port = port
        self.password = password
        self.socket = None
        self.authenticated = False
        self.request_id = 0

    async def connect(self):
        """Connect to the RCON server"""
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)  # 10 second timeout
            self.socket.connect((self.host, self.port))
            log.info(f"Connected to RCON at {self.host}:{self.port}")

            # Authenticate
            result = await self.authenticate()
            if not result:
                log.error("RCON authentication failed")
                self.socket.close()
                return False

            self.authenticated = True
            return True
        except Exception as e:
            log.error(f"RCON connection error: {e}")
            if self.socket:
                self.socket.close()
            return False

    async def authenticate(self):
        """Authenticate with the RCON server using the provided password"""
        if not self.socket:
            return False

        self.request_id += 1
        request_id = self.request_id

        # Send auth packet
        packet = self._build_packet(request_id, SERVERDATA_AUTH, self.password)
        self.socket.send(packet)

        # Receive response
        response = await self._receive_response()

        # Check if authentication was successful
        if (
            response
            and response.get("type") == SERVERDATA_AUTH_RESPONSE
            and response.get("id") == request_id
        ):
            log.info("RCON authentication successful")
            return True
        else:
            log.error("RCON authentication failed")
            return False

    async def send_command(self, command):
        """Send a command to the RCON server and get the response"""
        if not self.socket or not self.authenticated:
            log.error("RCON not connected or not authenticated")
            return None

        self.request_id += 1
        request_id = self.request_id

        # Send command packet
        packet = self._build_packet(request_id, SERVERDATA_EXECCOMMAND, command)
        self.socket.send(packet)

        # Receive response
        response = await self._receive_response()

        if response and response.get("id") == request_id:
            return response.get("body", "")
        return None

    async def _receive_response(self):
        """Receive and parse RCON response packet"""
        try:
            # First get the packet size
            size_data = self.socket.recv(4)
            if not size_data:
                return None

            size = struct.unpack("<I", size_data)[0]

            # Now get the actual packet
            packet_data = b""
            remaining = size
            while remaining > 0:
                chunk = self.socket.recv(remaining)
                if not chunk:
                    break
                packet_data += chunk
                remaining -= len(chunk)

            # Parse the packet
            if (
                len(packet_data) >= 8
            ):  # Minimum packet size (id + type + empty string + null terminator)
                response_id = struct.unpack("<I", packet_data[0:4])[0]
                response_type = struct.unpack("<I", packet_data[4:8])[0]

                # Extract the response body (null-terminated string)
                body = ""
                if len(packet_data) > 8:
                    body = packet_data[8:-2].decode("utf-8", errors="replace")

                return {"id": response_id, "type": response_type, "body": body}
        except Exception as e:
            log.error(f"Error receiving RCON response: {e}")

        return None

    def _build_packet(self, request_id, packet_type, body):
        """Build an RCON packet"""
        # Convert body to bytes if it's a string
        if isinstance(body, str):
            body = body.encode("utf-8")

        # Add null terminators
        body = body + b"\x00\x00"

        # Calculate packet size (excluding the size field itself)
        size = 4 + 4 + len(body)  # id + type + body with null terminators

        # Build the packet
        packet = struct.pack("<I", size)  # Size
        packet += struct.pack("<I", request_id)  # Request ID
        packet += struct.pack("<I", packet_type)  # Packet Type
        packet += body  # Body with null terminators

        return packet

    def close(self):
        """Close the RCON connection"""
        if self.socket:
            try:
                self.socket.close()
                log.info("RCON connection closed")
            except Exception as e:
                log.error(f"Error closing RCON connection: {e}")
            finally:
                self.socket = None
                self.authenticated = False


def check_steamcmd(app_path, username, password):
    link = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
    log.info("checking for steamcmd...")
    steamcmd = os.path.join(app_path, "steamcmd")

    # Get terminal width
    w, h = get_console_size()
    terminal_width = w

    # Calculate bar width based on terminal width
    # Subtract space for other columns (spinner, text, percentage, time)
    bar_width = terminal_width - 50  # Adjust this value as needed

    console = Console()

    if not os.path.isdir(steamcmd):
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=bar_width),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,  # Ensure the progress bar expands to fill available space
        ) as progress:
            log.info("SteamCMD not found, installing...")
            os.makedirs(steamcmd, exist_ok=True)

            # Create a task for the SteamCMD download
            download_task = progress.add_task(
                "[green]Downloading SteamCMD...", total=100
            )

            # Download and extract SteamCMD
            download_cmd = f'cd {steamcmd} && curl -sqL "{link}" | tar zxvf -'

            # Create a flag to track if the process is still running
            process_running = True

            # Use Popen to get real-time output
            process = subprocess.Popen(
                download_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Function to gradually update progress
            def update_download_progress():
                step = 0
                while process_running and step < 99:
                    if process.poll() is not None:  # Process finished
                        break
                    time.sleep(0.1)
                    step = min(step + 1, 99)  # Cap at 99%
                    progress.update(download_task, completed=step)

            # Start progress updater in a thread
            progress_thread = threading.Thread(
                target=update_download_progress, daemon=True
            )
            progress_thread.start()

            # Wait for process to complete
            stdout, stderr = process.communicate()

            # Process is no longer running
            process_running = False

            # Wait for the thread to pick up the change
            time.sleep(0.2)

            # Ensure progress is at 100%
            progress.update(
                download_task,
                completed=100,
                description="[green]SteamCMD download complete",
            )

            # Log output to file
            if stdout:
                for line in stdout.splitlines():
                    log.debug(f"SteamCMD download output: {line}")

            if stderr:
                for line in stderr.splitlines():
                    log.error(f"SteamCMD download error: {line}")

            if process.returncode != 0:
                log.error(
                    f"Failed to download SteamCMD with return code: {process.returncode}"
                )
                raise RuntimeError("SteamCMD download failed")

            # Verify steamcmd.sh exists
            steamcmd_sh = os.path.join(steamcmd, "steamcmd.sh")
            if not os.path.exists(steamcmd_sh):
                log.error(f"steamcmd.sh not found at {steamcmd_sh} after extraction")
                raise FileNotFoundError(f"steamcmd.sh not found at {steamcmd_sh}")

        log.info("checking for server_template...")
        server_template = os.path.join(steamcmd, "server_template")

        if (
            os.path.isdir(server_template) is not True
            or len(os.listdir(server_template)) == 0
        ):
            log.info(
                "Server template not found, installing (this will take a while)..."
            )
            # os.makedirs(server_template, exist_ok=True)

            steamcmd_sh = os.path.join(steamcmd, "steamcmd.sh")
            if not os.path.exists(steamcmd_sh):
                log.error(f"steamcmd.sh not found at {steamcmd_sh}")
                raise FileNotFoundError(f"steamcmd.sh not found at {steamcmd_sh}")

            # Create a task for the server template installation
            template_task = progress.add_task(
                "[yellow]Downloading server template...", total=100
            )

            # Process running flag
            process_running = True

            # Run steamcmd with correct arguments using Popen for real-time output
            process = subprocess.Popen(
                [
                    steamcmd_sh,
                    f"+force_install_dir {server_template}",
                    f"+login {username} {password}",
                    "+app_update 223350",
                    "+quit",
                ],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Regex to extract progress percentage from SteamCMD output
            progress_pattern = re.compile(r"Update state \(0x\d+\) (\d+)%.*")

            # Current progress percentage
            current_progress = 0

            # Function to parse output and update progress
            def update_template_progress():
                nonlocal current_progress
                for line in iter(process.stdout.readline, ""):
                    if not process_running:
                        break

                    match = progress_pattern.search(line)
                    if match:
                        percent = int(match.group(1))
                        current_progress = percent
                        progress.update(template_task, completed=percent)
                    log.debug(f"SteamCMD install output: {line.strip()}")

                # Process stderr
                for line in iter(process.stderr.readline, ""):
                    if not process_running:
                        break
                    log.error(f"SteamCMD install error: {line.strip()}")

            # Start progress updater in a thread
            progress_thread = threading.Thread(
                target=update_template_progress, daemon=True
            )
            progress_thread.start()

            # Wait for process to complete
            process.wait()

            # Mark process as completed
            process_running = False

            # Small delay to let the thread catch up
            time.sleep(0.2)

            # Ensure progress is at 100%
            progress.update(
                template_task,
                completed=100,
                description="[yellow]Server template installation complete",
            )

            if process.returncode != 0:
                log.error(
                    f"Failed to install server template with return code: {process.returncode}"
                )
                raise RuntimeError("Server template installation failed")

    log.info("steamcmd setup complete")


# initiate servers directory and return list of sub-directories
def check_servers(servers_path):
    # ensure servers path exists
    if not os.path.exists(servers_path):
        os.makedirs(servers_path, exist_ok=True)
        log.info(f"created servers directory at {servers_path}")

    # initialize existing instances
    try:
        # instances = next(os.walk(servers_path))
        instances = [
            d
            for d in os.listdir(servers_path)
            if os.path.isdir(os.path.join(servers_path, d))
        ]

    except StopIteration:
        # handle the case where the directory doesn't exist or is empty
        log.info(f"no instances found in {servers_path}")
        instances = []  # default empty result

    return instances


#  initiate server files and default config if needed
def validate_server_files(app_path, server_name):
    log.info(f"initializing instance {server_name}...")
    instance_path = os.path.join(app_path, "servers", server_name)

    needs_config_edit = False

    if os.path.isdir(instance_path) is not True or len(os.listdir(instance_path)) == 0:
        log.info("creating instance...")
        copytree(
            os.path.join(app_path, "steamcmd", "server_template"),
            instance_path,
        )

    # make default toml
    if (
        instance_path
        and os.path.exists(os.path.join(instance_path, "server.toml")) is not True
    ):
        copyfile(
            os.path.join(os.getcwd(), "resources", "server_default_config.toml"),
            os.path.join(instance_path, "server.toml"),
        )

        needs_config_edit = True
        log.warning(f"edit the server's server.toml for {server_name} before starting")

    return server_name, needs_config_edit


async def kick_all_and_restart(
    instance_name,
    rcon_port,
    rcon_password,
    host="127.0.0.1",
    restart_delay=60,
):
    """
    Kick all players and restart a DayZ server using RCON

    Args:
        instance_name: Name of the server instance
        host: RCON host address (default 127.0.0.1)
        rcon_port: RCON port (default is game port + 1)
        rcon_password: RCON password
        restart_delay: Delay in seconds before server restart (default 60)

    Returns:
        bool: True if successful, False otherwise
    """
    if not rcon_password:
        log.error(f"[{instance_name}] No RCON password provided")
        return False

    # Get the server info from server_states
    if instance_name not in server_states:
        log.error(f"[{instance_name}] Server instance not found in server_states")
        return False

    # server = server_states[instance_name]
    # game_port = server.get("rcon_port")

    # # If no RCON port specified, use game port + 1 (DayZ default)
    # if not rcon_port and game_port:
    #     rcon_port = game_port + 1

    if not rcon_port:
        log.error(f"[{instance_name}] Could not determine RCON port")
        return False

    log.info(
        f"[{instance_name}] Starting kick all and restart procedure via RCON on port {rcon_port}"
    )

    # Create RCON client
    rcon = RCONClient(port=rcon_port, password=rcon_password, host=host)

    try:
        # Connect to RCON
        connected = await rcon.connect()
        if not connected:
            log.error(f"[{instance_name}] Failed to connect to RCON")
            return False

        # Announce server restart
        message = f"SERVER RESTART IN {restart_delay} SECONDS. YOU WILL BE KICKED."
        log.info(f"[{instance_name}] Broadcasting restart message: {message}")
        await rcon.send_command(f'say -1 "{message}"')

        # Get list of players
        log.info(f"[{instance_name}] Getting player list")
        players_response = await rcon.send_command("players")

        if not players_response:
            log.warning(
                f"[{instance_name}] Could not get player list, assuming no players"
            )
            players = []
        else:
            # Parse player list
            players = []
            # Typical format:
            # Players on server:
            # [#] [ID] [Name]
            # 0   12   PlayerName

            lines = players_response.strip().split("\n")
            if len(lines) > 2:  # Header lines + at least one player
                for i in range(2, len(lines)):
                    parts = lines[i].strip().split()
                    if len(parts) >= 3:
                        try:
                            player_id = int(parts[1])
                            player_name = " ".join(parts[2:])
                            players.append((player_id, player_name))
                        except (ValueError, IndexError):
                            log.warning(
                                f"[{instance_name}] Could not parse player line: {lines[i]}"
                            )

        # If players found, kick them all
        if players:
            log.info(f"[{instance_name}] Kicking {len(players)} players")
            for player_id, player_name in players:
                kick_message = (
                    "Server is restarting. Please reconnect in a few minutes."
                )
                log.info(
                    f"[{instance_name}] Kicking player {player_name} (ID: {player_id})"
                )

                kick_response = await rcon.send_command(
                    f'kick {player_id} "{kick_message}"'
                )
                log.debug(f"[{instance_name}] Kick response: {kick_response}")

                # Small delay between kicks to avoid overloading the server
                await asyncio.sleep(0.5)
        else:
            log.info(f"[{instance_name}] No players to kick")

        # Wait for the specified delay before restart
        log.info(f"[{instance_name}] Waiting {restart_delay} seconds before restart")
        for i in range(restart_delay, 0, -10):
            if i <= 30:  # More frequent updates in the last 30 seconds
                step = 5
            else:
                step = 10

            # Announce time remaining if more than one step left
            if i > step:
                await rcon.send_command(f'say -1 "SERVER RESTARTING IN {i} SECONDS"')
                log.info(f"[{instance_name}] Restart in {i} seconds")
                await asyncio.sleep(step)

        # Final announcement
        await rcon.send_command('say -1 "SERVER RESTARTING NOW"')
        log.info(f"[{instance_name}] Executing restart command")

        # Send restart command
        restart_response = await rcon.send_command("#shutdown")
        log.info(f"[{instance_name}] Restart response: {restart_response}")

        # Close RCON connection
        rcon.close()

        # Update server state
        if instance_name in server_states:
            server_states[instance_name]["state"] = ServerState.STOPPED
            server_states[instance_name]["events"].append(
                {
                    "timestamp": datetime.datetime.now(),
                    "state": ServerState.STOPPED.value,
                    "message": "Server restarted via RCON",
                }
            )

        log.info(f"[{instance_name}] Kick all and restart completed successfully")
        return True

    except Exception as e:
        log.error(f"[{instance_name}] Error during kick all and restart: {e}")
        if rcon:
            rcon.close()
        return False


# Example function to start the restart process for a specific server
async def schedule_server_restart(
    app_path, instance_name, restart_delay=60, warning_time=300
):
    """
    Schedule a server restart with warnings

    Args:
        instance_name: Name of the server instance
        restart_delay: Time in seconds to wait between kicking players and restart (default 60)
        warning_time: Time in seconds to warn players before kicking begins (default 300, 5 minutes)
    """
    if instance_name not in server_states:
        log.error(f"Cannot restart unknown server: {instance_name}")
        return

    # Get server config to find RCON password
    server_config_path = os.path.join(app_path, "servers", instance_name, "server.toml")

    try:
        server_config = toml.load(server_config_path)
        rcon_port = server_config.get("server", {}).get("rcon", {}).get("port")
        rcon_password = server_config.get("server", {}).get("rcon", {}).get("password")

        if not rcon_password:
            log.error(
                f"[{instance_name}] No RCON password found in server configuration"
            )
            return

        # Send warning messages at intervals
        rcon = RCONClient(host="127.0.0.1", port=rcon_port, password=rcon_password)

        connected = await rcon.connect()
        if not connected:
            log.error(f"[{instance_name}] Failed to connect to RCON for warnings")
            return

        # Warnings at various intervals
        warning_intervals = [warning_time, 180, 120, 60, 30]

        for interval in warning_intervals:
            if interval <= warning_time:
                minutes = interval // 60
                message = (
                    f"SERVER RESTART IN {minutes} MINUTE{'S' if minutes > 1 else ''}"
                )
                log.info(f"[{instance_name}] Warning: {message}")
                await rcon.send_command(f'say -1 "{message}"')

                # Wait until next warning interval
                next_index = warning_intervals.index(interval) + 1
                if next_index < len(warning_intervals):
                    wait_time = interval - warning_intervals[next_index]
                    await asyncio.sleep(wait_time)
                else:
                    # Last warning, wait until restart
                    await asyncio.sleep(interval - restart_delay)

        rcon.close()

        # Execute kick all and restart
        success = await kick_all_and_restart(
            rcon_port=rcon_port,
            rcon_password=rcon_password,
            instance_name=instance_name,
            restart_delay=restart_delay,
        )

        if not success:
            log.error(f"[{instance_name}] Failed to restart server via RCON")

    except Exception as e:
        log.error(f"[{instance_name}] Error scheduling restart: {e}")


# Enhanced monitor process function
async def monitor_process(process, instance_name=None, port=None):
    """
    Monitor a server process with enhanced logging capabilities.
    Captures stdout and stderr in real-time and logs with appropriate levels.
    Tracks server state transitions and important events.

    Args:
        process: The asyncio subprocess object
        instance_name: Name of the server instance
        port: Port the server is running on
    """
    server_id = instance_name or f"pid-{process.pid}"
    log.info(f"[{server_id}] Server monitoring started on PID {process.pid}")

    # Set initial state
    server_states[server_id] = {
        "state": ServerState.STARTING,
        "pid": process.pid,
        "port": port,
        "start_time": datetime.datetime.now(),
        "last_update": datetime.datetime.now(),
        "players": 0,
        "events": [],
    }

    # Create a function to update and log state changes
    def update_state(new_state, message=None):
        old_state = server_states[server_id]["state"]
        if old_state != new_state:
            state_msg = (
                f"[{server_id}] State changed: {old_state.value} → {new_state.value}"
            )
            if message:
                state_msg += f" ({message})"

            if new_state == ServerState.ERROR or new_state == ServerState.CRASHED:
                log.error(state_msg)
            elif new_state == ServerState.WARNING:
                log.warning(state_msg)
            else:
                log.info(state_msg)

        server_states[server_id]["state"] = new_state
        server_states[server_id]["last_update"] = datetime.datetime.now()

        if message:
            server_states[server_id]["events"].append(
                {
                    "timestamp": datetime.datetime.now(),
                    "state": new_state.value,
                    "message": message,
                }
            )

    # Regular expressions for parsing important server messages
    startup_patterns = [
        (
            re.compile(r"Waiting for connection\.\.\."),
            ServerState.RUNNING,
            "Server ready for connections",
        ),
        (
            re.compile(r"DayZ Console version"),
            ServerState.RUNNING,
            "Server ready for connections",
        ),
        (re.compile(r'Player [^"]+ connected'), None, "Player connected"),
        (re.compile(r'Player [^"]+ disconnected'), None, "Player disconnected"),
        (
            re.compile(r"ERROR|CRITICAL|FATAL"),
            ServerState.ERROR,
            "Server error detected",
        ),
        # (re.compile(r"WARNING"), ServerState.WARNING, "Server warning"),
        (
            re.compile(r"Connection with host timed out"),
            ServerState.WARNING,
            "Connection timeout",
        ),
        (re.compile(r"No space left on device"), ServerState.ERROR, "Disk space issue"),
        (
            re.compile(r"Segmentation fault|Aborted|Killed"),
            ServerState.CRASHED,
            "Server crash detected",
        ),
    ]

    # Function to analyze log lines and update state accordingly
    def process_log_line(line, error=False):
        line_type = "ERROR" if error else "INFO"
        log_prefix = f"[{server_id}][{line_type}]"

        # Count players if possible (simplified example)
        if "connected" in line and "Player" in line:
            if "Player" in line and "connected" in line and "dis" not in line:
                server_states[server_id]["players"] += 1
            elif "Player" in line and "disconnected" in line:
                server_states[server_id]["players"] = max(
                    0, server_states[server_id]["players"] - 1
                )

        # Process line with regex patterns
        for pattern, state, message in startup_patterns:
            if pattern.search(line):
                if state:
                    update_state(state, message)
                log.info(f"{log_prefix} {message}: {line.strip()}")
                return

        # Default logging based on line type
        if error:
            log.error(f"{log_prefix} {line.strip()}")
        else:
            # Only log meaningful output lines to avoid spam
            if line.strip() and not line.strip().startswith(
                ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")
            ):
                log.debug(f"{log_prefix} {line.strip()}")

    try:
        # Set up async readers for stdout and stderr
        stdout_reader = asyncio.create_task(
            read_stream(process.stdout, lambda line: process_log_line(line))
        )
        stderr_reader = asyncio.create_task(
            read_stream(process.stderr, lambda line: process_log_line(line, True))
        )

        # Create periodic status reporting task
        status_reporter = asyncio.create_task(periodic_status_report(server_id))

        # Wait for process to complete
        return_code = await process.wait()

        # Cancel stream readers and status reporter
        stdout_reader.cancel()
        stderr_reader.cancel()
        status_reporter.cancel()

        # Handle process termination
        if return_code != 0:
            update_state(
                ServerState.CRASHED, f"Server terminated with code {return_code}"
            )
        else:
            update_state(ServerState.STOPPED, "Server stopped gracefully")

        log.info(
            f"[{server_id}] Server process terminated with return code {return_code}"
        )

        # Final status report
        report_server_status(server_id, final=True)

    except asyncio.CancelledError:
        update_state(ServerState.STOPPED, "Monitor task cancelled")
        log.info(f"[{server_id}] Monitoring cancelled")
        raise
    except Exception as e:
        update_state(ServerState.ERROR, f"Monitoring error: {str(e)}")
        log.error(f"[{server_id}] Monitoring failed: {e}")
    finally:
        # Ensure process is terminated if still running
        if server_states[server_id]["state"] not in [
            ServerState.STOPPED,
            ServerState.CRASHED,
        ]:
            if process.returncode is None:
                log.info(f"[{server_id}] Terminating server process")
                try:
                    process.terminate()
                    await asyncio.wait_for(await process.wait(), timeout=5.0)
                    update_state(ServerState.STOPPED, "Server terminated by monitor")
                except asyncio.TimeoutError:
                    log.warning(
                        f"[{server_id}] Server didn't terminate gracefully, killing"
                    )
                    process.kill()
                    update_state(ServerState.STOPPED, "Server killed by monitor")


# Helper function to read stream data line by line
async def read_stream(stream, callback):
    """Read lines from an asyncio stream and process them with the callback"""
    while True:
        line = await stream.readline()
        if not line:
            break
        try:
            decoded_line = line.decode("utf-8", errors="replace")
            callback(decoded_line)
        except Exception as e:
            log.error(f"Error processing stream line: {e}")


# Periodic status reporting function
async def periodic_status_report(server_id):
    """Report server status periodically"""
    try:
        while True:
            await asyncio.sleep(300)  # Report every 5 minutes
            report_server_status(server_id)
    except asyncio.CancelledError:
        pass


# Function to generate and log server status reports
def report_server_status(server_id, final=False):
    """Generate a status report for the specified server"""
    if server_id not in server_states:
        log.warning(f"Cannot report status for unknown server: {server_id}")
        return

    server = server_states[server_id]
    uptime = datetime.datetime.now() - server["start_time"]
    hours, remainder = divmod(uptime.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)

    status_type = "FINAL STATUS" if final else "STATUS UPDATE"

    log.info(f"[{server_id}] {status_type} REPORT:")
    log.info(f"[{server_id}] State: {server['state'].value}")
    log.info(f"[{server_id}] PID: {server['pid']}, Port: {server['port']}")
    log.info(f"[{server_id}] Uptime: {int(hours)}h {int(minutes)}m {int(seconds)}s")
    log.info(f"[{server_id}] Current Players: {server['players']}")

    # Report recent events (last 5 or all if final report)
    events_to_show = server["events"] if final else server["events"][-5:]
    if events_to_show:
        log.info(f"[{server_id}] Recent events:")
        for event in events_to_show:
            timestamp = event["timestamp"].strftime("%H:%M:%S")
            log.info(
                f"[{server_id}]   {timestamp} [{event['state']}] {event['message']}"
            )


# Update the start_server function to pass instance name to monitor_process
async def start_server(app_path, instance, port, client_mods, server_mods, logs):
    instance_path = os.path.join(app_path, "servers", instance)

    log.info(f"[{instance}] Starting server on port {port}")
    if client_mods:
        log.debug(f"[{instance}] Client mods: {client_mods}")
    if server_mods:
        log.debug(f"[{instance}] Server mods: {server_mods}")

    args = [
        os.path.join(instance_path, "DayZServer"),
        "-autoinit",
        "-steamquery",
        f"-config={os.path.join(instance_path, 'serverDZ.cfg')}",
        f"-port={port}",
        f"-BEpath={os.path.join(instance_path, 'battleye')}",
        f"-profiles={os.path.join(instance_path, 'profiles')}",
        f"-mod={client_mods}" if client_mods else "",
        f"-servermod={server_mods}" if server_mods else "",
        " " + logs,
        "-freezecheck",
    ]

    # Log complete command for debugging
    log.debug(f"[{instance}] Launch command: {' '.join(args)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=instance_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        log.info(f"[{instance}] Server process started with PID {process.pid}")

        # Store PID and process object
        server_info = {
            "instance": instance,
            "pid": process.pid,
            "process": process,
            "port": port,
        }

        # Start enhanced monitoring task with instance name
        asyncio.create_task(monitor_process(process, instance, port))

        return server_info
    except Exception as e:
        log.error(f"[{instance}] Failed to start server: {e}")
        raise


# find Steam path if it's not in expected location
def find_steam_workshop_path(app_id, app_path):
    """
    Find the Steam workshop content directory for a specific app_id.
    Returns the full path to the workshop content directory or None if not found.
    """
    # Common Steam installation locations
    possible_paths = [
        # Linux paths
        os.path.expanduser("~/.local/share/Steam/steamapps/workshop/content/"),
        os.path.expanduser("~/Steam/steamapps/workshop/content/"),
        os.path.expanduser("~/.steam/steam/steamapps/workshop/content/"),
        os.path.expanduser("~/.steam/root/steamapps/workshop/content/"),
        # Add more paths if needed for different distributions or configurations
    ]

    # Check if any of the paths contain the app_id directory
    for base_path in possible_paths:
        full_path = os.path.join(base_path, app_id)
        if os.path.exists(full_path) and os.path.isdir(full_path):
            log.debug(f"Found Steam workshop content directory at: {full_path}")
            return full_path

    # If steamcmd has been run, we might be able to find the path from its config
    home_dir = os.path.expanduser("~")
    registry_path = os.path.join(home_dir, ".steam", "registry.vdf")
    if os.path.exists(registry_path):
        try:
            with open(registry_path, "r") as f:
                content = f.read()
                # Simple parsing to find installation path
                for line in content.split("\n"):
                    if "BaseInstallFolder" in line or "SteamPath" in line:
                        # Extract path from quotes
                        path_match = line.split('"')
                        if len(path_match) >= 4:
                            steam_path = path_match[3].replace("\\\\", "/")
                            workshop_path = os.path.join(
                                steam_path, "steamapps", "workshop", "content", app_id
                            )
                            if os.path.exists(workshop_path):
                                log.debug(
                                    f"Found Steam workshop content directory from registry: {workshop_path}"
                                )
                                return workshop_path
        except Exception as e:
            log.warning(f"Failed to parse Steam registry file: {e}")

    # Try to find using steamcmd
    try:
        result = subprocess.run(
            ["./steamcmd.sh", "+quit"],
            shell=False,
            cwd=os.path.join(app_path, "steamcmd"),
            capture_output=True,
            text=True,
        )
        for line in result.stdout.split("\n"):
            if "Steam API initialized" in line:
                log_parts = line.split(" - ")
                if len(log_parts) > 1:
                    steam_path = log_parts[1].strip()
                    workshop_path = os.path.join(
                        steam_path, "steamapps", "workshop", "content", app_id
                    )
                    if os.path.exists(workshop_path):
                        log.debug(
                            f"Found Steam workshop content directory from steamcmd: {workshop_path}"
                        )
                        return workshop_path
    except Exception as e:
        log.warning(f"Failed to run steamcmd to find Steam path: {e}")

    log.warning("Could not find Steam workshop content directory")
    return None


# ensure mod installation in workshop and server root
def validate_workshop_mods(username, server_configs, app_path):
    steamcmd_path = os.path.join(app_path, "steamcmd")
    mod_templates_path = os.path.join(
        steamcmd_path, "steamapps", "workshop", "content", "221100"
    )
    os.makedirs(mod_templates_path, exist_ok=True)

    # dictionary to store mod_id -> mod_name mappings
    workshop_mods_by_id = {}
    workshop_mods_by_name = {}

    # dictionary to track mod names that we already know
    known_mod_names = {}

    # first, build a mapping of existing mods in workshop directory
    if os.path.exists(mod_templates_path):
        existing_mod_ids = [
            d
            for d in os.listdir(mod_templates_path)
            if os.path.isdir(os.path.join(mod_templates_path, d))
        ]

        # get names for existing mods
        for mod_id in existing_mod_ids:
            meta_path = os.path.join(mod_templates_path, mod_id, "meta.cpp")
            name = mod_id

            if os.path.exists(meta_path):
                try:
                    with open(meta_path) as cpp:
                        lines = cpp.read().splitlines()

                    for line in lines:
                        if "name" in line:
                            name = (
                                line.replace('"', "")
                                .replace(";", "")
                                .replace("name =", "")
                                .strip()
                            )
                            break
                except Exception as e:
                    log.warning(f"error reading meta.cpp for mod {mod_id}: {e}")

            workshop_mods_by_id[mod_id] = name
            workshop_mods_by_name[name] = mod_id
            known_mod_names[name] = mod_id

    # parse both mod IDs and mod names from configs
    all_mod_ids = set()
    all_mod_names = set()

    for config in server_configs:
        # process client mods
        if (
            "client_mods" in config["server"]["info"]
            and config["server"]["info"]["client_mods"]
        ):
            client_mods = config["server"]["info"]["client_mods"]
            process_mod_string(client_mods, all_mod_ids, all_mod_names, known_mod_names)

        # process server mods
        if (
            "server_mods" in config["server"]["info"]
            and config["server"]["info"]["server_mods"]
        ):
            server_mods = config["server"]["info"]["server_mods"]
            process_mod_string(server_mods, all_mod_ids, all_mod_names, known_mod_names)

    log.debug(f"all mod IDs: {all_mod_ids}")
    log.debug(f"all mod names: {all_mod_names}")

    # determine which mods need to be downloaded (only IDs can be downloaded)
    mods_to_download = set()
    for mod_id in all_mod_ids:
        # only consider valid mod IDs (10 digit numbers)
        if mod_id.isdigit() and len(mod_id) == 10:
            # check if it's already in the workshop directory
            if not os.path.exists(os.path.join(mod_templates_path, mod_id)):
                mods_to_download.add(mod_id)

    log.debug(f"mods to download: {list(mods_to_download)}")

    # download missing mods one at a time with timeout protection
    if mods_to_download:
        # Find Steam workshop content directory
        default_workshop_path = find_steam_workshop_path("221100", app_path)
        if not default_workshop_path:
            log.warning("could not find Steam workshop content directory")
            # Fallback to the path in the project directory
            default_workshop_path = mod_templates_path

        log.info(f"using Steam workshop content directory: {default_workshop_path}")

        # Process mods one at a time to prevent hanging
        for mod_id in mods_to_download:
            try:
                log.info(f"Downloading mod {mod_id}...")

                # Create a command list for better security and control
                cmd = [
                    "./steamcmd.sh",
                    "+login",
                    username,
                    "+workshop_download_item",
                    "221100",
                    mod_id,
                    "+quit",
                ]

                # Run with timeout
                process = subprocess.run(
                    cmd,
                    shell=False,
                    cwd=steamcmd_path,
                    timeout=300,  # 5 minute timeout per mod
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                if process.returncode != 0:
                    log.warning(
                        f"error downloading mod {mod_id}: {process.stderr.decode('utf-8')}"
                    )
                else:
                    log.info(f"successfully downloaded mod {mod_id}")

                # create symlink for the downloaded mod
                default_mod_path = os.path.join(default_workshop_path, mod_id)
                target_mod_path = os.path.join(mod_templates_path, mod_id)

                if os.path.exists(default_mod_path) and not os.path.exists(
                    target_mod_path
                ):
                    try:
                        os.symlink(default_mod_path, target_mod_path)
                        log.info(
                            f"created symlink for mod {mod_id} from {default_mod_path} to {target_mod_path}"
                        )
                    except Exception as e:
                        log.warning(f"failed to create symlink for mod {mod_id}: {e}")

            except subprocess.TimeoutExpired:
                log.error(f"timeout while downloading mod {mod_id}")
            except Exception as e:
                log.error(f"error processing mod {mod_id}: {e}")
    else:
        log.info("no new mods to download")

    # Update mod_dict with names for newly downloaded mods
    for mod_id in mods_to_download:
        meta_path = os.path.join(mod_templates_path, mod_id, "meta.cpp")
        name = mod_id  # Default to using the ID as the name

        if os.path.exists(meta_path):
            try:
                with open(meta_path) as cpp:
                    lines = cpp.read().splitlines()

                for line in lines:
                    if "name" in line:
                        name = (
                            line.replace('"', "")
                            .replace(";", "")
                            .replace("name =", "")
                            .strip()
                        )
                        break
            except Exception as e:
                log.warning(f"failed to parse meta.cpp for mod {mod_id}: {e}")

        workshop_mods_by_id[mod_id] = name
        workshop_mods_by_name[name] = mod_id
        known_mod_names[name] = mod_id

    return workshop_mods_by_id


# parse mod string to extract ids and names
def process_mod_string(mod_string, all_mod_ids, all_mod_names, known_mod_names):
    """helper function to parse mod strings and extract IDs and names"""
    if not mod_string:
        return

    mods = mod_string.replace("@", "").split(";")
    for mod in mods:
        if not mod:
            continue

        if mod.isdigit() and len(mod) == 10:
            # this is a mod ID
            all_mod_ids.add(mod)
        else:
            # this is a mod name
            all_mod_names.add(mod)
            # check if we know the ID for this name
            if mod in known_mod_names:
                all_mod_ids.add(known_mod_names[mod])


# copy mods to server directories and update configs
def import_mods(app_path, instance, client_mods, server_mods, workshop_mods_by_id):
    """
    copy mods to server directories and update config strings
    with mod names instead of IDs
    """
    # create reverse lookup from mod name to mod ID
    name_to_id = {name: mod_id for mod_id, name in workshop_mods_by_id.items()}

    instance_path = os.path.join(app_path, "servers", instance)

    # ensure server keys directory exists
    keys_dir = os.path.join(instance_path, "keys")
    os.makedirs(keys_dir, exist_ok=True)

    # parse client and server mod strings
    client = client_mods.replace("@", "").split(";") if client_mods else []
    server = server_mods.replace("@", "").split(";") if server_mods else []

    # filter out empty items
    client = [mod for mod in client if mod]
    server = [mod for mod in server if mod]

    log.debug(f"client mods before processing: {client}")
    log.debug(f"server mods before processing: {server}")

    # process all mods (both client and server)
    processed_client = []
    processed_server = []

    def process_and_copy_mod(mod):
        """process a single mod (ID or name) and copy to server if needed"""
        mod_id = None
        mod_name = None

        # determine if this is a mod ID or name
        if mod.isdigit() and len(mod) == 10:
            # it's a mod ID, get its name
            mod_id = mod
            if mod in workshop_mods_by_id:
                mod_name = workshop_mods_by_id[mod]
            else:
                log.warning(f"unknown mod ID: {mod}")
                return mod  # return original if we don't know what it is
        else:
            # it's a mod name, try to find its ID
            mod_name = mod
            if mod in name_to_id:
                mod_id = name_to_id[mod]
            else:
                log.warning(f"unknown mod name: {mod}")
                return mod  # return original if we don't know what it is

        # at this point we should have both mod_id and mod_name
        if not mod_id or not mod_name:
            return mod

        # check if mod exists in server directory
        server_mod_path = os.path.join(instance_path, f"@{mod_name}")
        workshop_mod_path = os.path.join(
            app_path, "steamcmd", "steamapps", "workshop", "content", "221100", mod_id
        )

        needs_copy = False

        # determine if mod needs copying
        if not os.path.exists(server_mod_path):
            # mod doesn't exist in server directory
            needs_copy = True
        elif os.path.exists(workshop_mod_path):
            # both exist, check if workshop version is newer
            try:
                workshop_time = os.path.getmtime(workshop_mod_path)
                server_time = os.path.getmtime(server_mod_path)
                if workshop_time > server_time:
                    needs_copy = True
            except Exception as e:
                log.warning(f"error comparing mod timestamps: {e}")

        # guard clause
        if not needs_copy:
            return mod_name

        if not os.path.exists(workshop_mod_path):
            log.warning(f"Workshop mod path does not exist: {workshop_mod_path}")
            return mod_name

        # copy mod if needed
        log.info(f"copying mod {mod_name} from workshop to server")

        # remove existing mod directory if it exists
        if os.path.exists(server_mod_path):
            try:
                shutil.rmtree(server_mod_path)
            except Exception as e:
                log.error(f"error removing existing mod directory: {e}")

        # copy mod directory
        try:
            copytree(workshop_mod_path, server_mod_path)

            # check for keys directory with any capitalization
            keys_dir_found = False
            for sub_dir in os.listdir(server_mod_path):
                if (
                    sub_dir.lower() == "keys" or sub_dir.lower() == "key"
                ) and os.path.isdir(os.path.join(server_mod_path, sub_dir)):
                    keys_src = os.path.join(server_mod_path, sub_dir)
                    keys_dir_found = True

                    log.debug(f"copying keys from {keys_src} to {keys_dir}")
                    for key_file in os.listdir(keys_src):
                        if key_file.lower().endswith(".bikey"):
                            try:
                                shutil.copy2(
                                    os.path.join(keys_src, key_file),
                                    os.path.join(keys_dir, key_file),
                                )
                                log.debug(f"copied key file: {key_file}")
                            except Exception as e:
                                log.error(f"error copying key file {key_file}: {e}")

            if not keys_dir_found:
                log.debug(f"no keys directory found in mod: {mod_name}")
        except Exception as e:
            log.error(f"error copying mod {mod_name}: {e}")

        return mod_name

    # Process all client mods
    for mod in client:
        processed_name = process_and_copy_mod(mod)
        if processed_name:
            processed_client.append(processed_name)

    # Process all server mods
    for mod in server:
        processed_name = process_and_copy_mod(mod)
        if processed_name:
            processed_server.append(processed_name)

    # Add a sync point here - ensure all file operations are complete
    # Wait for any potential file operations to complete
    time.sleep(3)  # Increased from 2 to 3 seconds for safety

    # create updated mod strings
    client_mods = f"@{';@'.join(processed_client)}" if processed_client else ""
    server_mods = f"@{';@'.join(processed_server)}" if processed_server else ""

    log.debug(f"updated client mods: {client_mods}")
    log.debug(f"updated server mods: {server_mods}")

    return client_mods, server_mods


# lets go
async def main():
    title_screen()
    print("Initializing...", end="", flush=True)

    # initialize pathing
    dman_config_path = os.path.join(os.getcwd(), "dman.toml")
    default_dman_config_path = os.path.join(
        os.getcwd(), "resources", "dman_default_config.toml"
    )

    # ensure dman config
    if os.path.exists(dman_config_path) is not True:
        copyfile(default_dman_config_path, dman_config_path)

    # load dman config
    dman_config = toml.load(dman_config_path)

    # initialize app paths
    dman_path = os.getcwd()
    app_path = os.path.join(dman_path, "app")
    servers_path = os.path.join(app_path, "servers")
    # steamcmd_path = os.path.join(app_path, "steamcmd")

    # grab username from dman config
    user_info = dman_config["user"]["info"]
    username = user_info["steam_username"]
    password = user_info["steam_password"]

    # grab server instances from dman config
    instance_info = dman_config["servers"]["list"]
    log.debug(f"instance_info: {instance_info}")

    if username == "STEAM_USERNAME":
        log.info("replace STEAM_USERNAME in dman.toml")
        print(
            "Please change STEAM_USERNAME & STEAM_PASSWORD in dman.toml to start using dman!"
        )
        return

    if password == "STEAM_PASSWORD":
        log.info("replace STEAM_PASSWORD in dman.toml")
        print("Please change STEAM_PASSWORD in dman.toml to start using dman!")
        return

    # ensure steamcmd is installed
    check_steamcmd(app_path, username, password)

    # ensure servers directory is initiated
    check_servers(servers_path)

    # # initialize instances to be run using dman config
    instance_keys = [key for key in instance_info.keys()]
    active_instances = [
        key for key in instance_info.keys() if instance_info[key] is True
    ]
    inactive_instances = [
        key for key in instance_info.keys() if instance_info[key] is not True
    ]
    log.debug(f"active_instances: {active_instances}")

    # confirm instance integrity and extract configurations
    instances_needing_edits = []
    if instance_info:
        server_configs = []
        for instance in instance_keys:
            instance_name, needs_edit = validate_server_files(app_path, instance)
            if needs_edit:
                instances_needing_edits.append(instance_name)

            # Load configs for existing instances
            config_path = os.path.join(
                app_path, "servers", instance_name, "server.toml"
            )
            if os.path.exists(config_path):
                server_configs.append(toml.load(config_path))

        log.debug(f"server_configs: {server_configs}")
    else:
        log.warning("no instances in dman.toml")
        return

    # Exit if any instances need configuration
    if instances_needing_edits:
        print(
            f"The following instances need configuration: {', '.join(instances_needing_edits)}"
        )
        print("Please edit their server.toml files before running the script again.")
        await asyncio.sleep(5)
        return

    # mod_dict = validate_workshop_mods(username, server_configs, app_path)
    # log.debug(f"mod_dict: {mod_dict}")

    try:
        mod_dict = validate_workshop_mods(username, server_configs, app_path)
        log.debug(f"mod_dict: {mod_dict}")
    except Exception as e:
        log.error(f"Error validating workshop mods: {e}")
        mod_dict = {}  # Use empty dict if validation fails

    # this is where we store server information and the actual processes
    servers = {}
    processes = []

    # initiate configurations with server.tomls
    for instance in instance_keys:
        # Find the corresponding server config
        # This assumes active_instances is a subset of instances
        instance_index = instance_keys.index(instance)
        server_config = server_configs[instance_index]

        server_info = server_config["server"]["info"]
        port = server_info["port"]
        client_mods = server_info["client_mods"]
        server_mods = server_info["server_mods"]
        logs = server_info["logs"]

        rcon_info = server_config["server"]["rcon"]
        rcon_port = rcon_info["port"]
        rcon_pass = rcon_info["password"]

        # First collect all the server information
        servers[instance] = {
            "is_active": instance_info[instance],
            "app_path": app_path,
            "instance": instance,
            "port": port,
            "rcon_port": rcon_port,
            "rcon_pass": rcon_pass,
            "client_mods": client_mods,
            "server_mods": server_mods,
            "logs": logs,
        }

        # Set initial state
        server_states[instance] = {
            "state": ServerState.STOPPED,
            "pid": "N/A",
            "port": port,
            "start_time": datetime.datetime.now(),
            "last_update": datetime.datetime.now(),
            "players": "N/A",
            "events": [],
        }

        # # Update server state to default
        # server_states[instance]["state"] = ServerState.STOPPED
        # server_states[instance]["events"].append(
        #     {
        #         "timestamp": datetime.datetime.now(),
        #         "state": ServerState.STOPPED.value,
        #         "message": "Server not active",
        #     }
        # )

        # Process and update mods separately
        if client_mods or server_mods:
            updated_client_mods, updated_server_mods = import_mods(
                app_path, instance, client_mods, server_mods, mod_dict
            )

            # Update the server_config in memory
            server_config["server"]["info"]["client_mods"] = updated_client_mods
            server_config["server"]["info"]["server_mods"] = updated_server_mods

            # Update the config file
            with open(
                os.path.join(app_path, "servers", instance, "server.toml"),
                "w",
            ) as f:
                toml.dump(server_config, f)

            # Update the servers dictionary with new mod values
            servers[instance]["client_mods"] = updated_client_mods
            servers[instance]["server_mods"] = updated_server_mods

    log.debug(f"servers: {servers}")

    print("Done")
    if active_instances:
        print("Starting servers...", end="", flush=True)

    else:
        print("No active instances, enable them in dman.toml :3")

    # Prepare the server processes
    for instance, data in servers.items():
        # print(servers)
        if data["is_active"]:
            log.debug(f"Starting server {instance}")
            processes.append(
                start_server(
                    data["app_path"],
                    data["instance"],
                    data["port"],
                    data["client_mods"],
                    data["server_mods"],
                    data["logs"],
                )
            )

    # Start servers
    server_instances = await asyncio.gather(*processes)

    # Print server info
    log.info(f"All enabled servers started. Summary: {server_instances}")
    if active_instances:
        print("Done")
        await asyncio.sleep(3)
        # cached_menu = main_menu(server_states)
        # cached_states = server_states.copy()
        # main_menu(server_states)

    # Before the main loop
    cached_states = {}
    for server, data in server_states.items():
        cached_states[server] = {"state": data["state"], "players": data["players"]}
    main_menu(server_states)  # Show initial state

    # print("Servers running:")
    # for server in server_instances:
    #     log.info(
    #         f"Instance: {server['instance']}, PID: {server['pid']}, Port: {server['port']}"
    #     )
    #     print(f" - {server['instance']}")

    # Set up restart scheduling
    scheduling_tasks = []
    for server in server_instances:
        scheduling_tasks.append(
            await schedule_server_restart(
                app_path=app_path,
                instance_name=server["instance"],
                restart_delay=180,
                warning_time=1800,
            )
        )

    # Main monitoring loop - we'll return the server_instances so they can be cleaned up
    try:
        while True:
            running_servers = [instance for instance in active_instances]
            stopped_servers = [instance for instance in inactive_instances]
            await asyncio.sleep(1)

            # Check for crashed servers
            for server_id, state in list(server_states.items()):
                if state["state"] == ServerState.CRASHED:
                    log.warning(
                        f"[{server_id}] Server detected as crashed, consider implementing auto-restart"
                    )
                    if server_id not in stopped_servers:
                        stopped_servers.append(server_id)

                    if server_id in running_servers:
                        running_servers.remove(server_id)

                elif server_id not in running_servers:
                    running_servers.append(server_id)

                    if server_id in stopped_servers:
                        stopped_servers.remove(server_id)

            # print(server_states)
            # print(cached_states)

            # for server, data in server_states.items():
            #     if server in cached_states and (
            #         data["state"] != cached_states[server]["state"]
            #         or data["players"] != cached_states[server]["players"]
            #     ):
            #         main_menu(server_states)
            #         cached_states = server_states.copy()
            #         break  # prevent multiple menu refreshes in one cycle

            needs_update = False
            for server, data in server_states.items():
                # Check if server is new or if state/players have changed
                if (
                    server not in cached_states
                    or data["state"] != cached_states[server]["state"]
                    or data["players"] != cached_states[server]["players"]
                ):
                    needs_update = True
                    break

            # Also check for removed servers
            for server in list(cached_states.keys()):
                if server not in server_states:
                    needs_update = True
                    break

            if needs_update:
                main_menu(server_states)
                # Update cached values
                cached_states = {}
                for server, data in server_states.items():
                    cached_states[server] = {
                        "state": data["state"],
                        "players": data["players"],
                    }

    finally:
        # This will run when the task is cancelled
        return server_instances


async def shutdown_servers(server_instances):
    """Gracefully shut down all server instances"""
    if not server_instances:
        return

    log.info("Shutdown requested. Stopping all servers...")
    print("losing dman...")

    # Send terminate signal to all servers
    for server in server_instances:
        instance = server["instance"]
        process = server["process"]
        if process and process.returncode is None:
            log.info(f"[{instance}] Sending terminate signal...")
            process.terminate()

    # Wait for servers to stop gracefully
    log.info("Waiting for servers to stop gracefully...")
    await asyncio.sleep(10)

    # Force kill any remaining processes
    for server in server_instances:
        process = server["process"]
        if process and process.returncode is None:
            log.warning(
                f"[{server['instance']}] Server still running, force killing..."
            )
            process.kill()

    # Wait for all processes to fully terminate
    for server in server_instances:
        process = server["process"]
        if process:
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                log.warning(
                    f"[{server['instance']}] Process didn't terminate within timeout"
                )

    log.info("Server manager shutting down")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    server_instances = None
    main_task = None

    try:
        # Run the main task
        main_task = loop.create_task(main())
        server_instances = loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        # This runs when Ctrl+C is pressed
        log.info("Keyboard interrupt detected")
        if main_task and not main_task.done():
            # Cancel the main task if it's still running
            main_task.cancel()
            try:
                # Try to get the server instances if available
                server_instances = loop.run_until_complete(main_task)
            except asyncio.CancelledError:
                # This is expected when cancelling the task
                pass
    finally:
        # Run the shutdown procedure if we have server instances
        if server_instances:
            try:
                loop.run_until_complete(shutdown_servers(server_instances))
            except Exception as e:
                log.error(f"Error during shutdown: {e}")

        # Close all running event loop tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        # Allow cancelled tasks to complete with a timeout
        if pending:
            try:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            except asyncio.CancelledError:
                pass

        # Close the event loop
        loop.close()
