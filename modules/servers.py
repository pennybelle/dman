import logging
import os
import asyncio
import datetime
import re

from modules.serverstate import ServerState

from shutil import copyfile, copytree

log = logging.getLogger(__name__)


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


# Enhanced monitor process function
async def monitor_process(server_states, process, instance_name=None, port=None):
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
        status_reporter = asyncio.create_task(
            periodic_status_report(server_states, server_id)
        )

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
async def periodic_status_report(server_states, server_id):
    """Report server status periodically"""
    try:
        while True:
            await asyncio.sleep(300)  # Report every 5 minutes
            report_server_status(server_states, server_id)
    except asyncio.CancelledError:
        pass


# Function to generate and log server status reports
def report_server_status(server_states, server_id, final=False):
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
async def start_server(
    server_states, app_path, instance, port, client_mods, server_mods, logs
):
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
        asyncio.create_task(monitor_process(server_states, process, instance, port))

        return server_info
    except Exception as e:
        log.error(f"[{instance}] Failed to start server: {e}")
        raise
