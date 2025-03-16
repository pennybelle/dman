import os
import subprocess
import logging
import shutil
import time
import threading
import socket
import struct
import toml
from queue import Queue
from subprocess import Popen, PIPE
from shutil import copyfile, copytree
from sys import exit

# Assuming your __logger__.py is in the same directory
from __logger__ import setup_logger

log = logging.getLogger(__name__)
setup_logger(level=10, stream_logs=True)


# install steamcmd if needed
def check_steamcmd(steamcmd):
    link = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
    log.info("checking for steamcmd...")
    if os.path.isdir(steamcmd) is not True:
        log.info("not found, installing...(this could take a while)")
        os.makedirs(steamcmd)
        Popen(
            f'cd {steamcmd} && curl -sqL "{link}" | tar zxvf -',
            shell=True,
            stdout=PIPE,
            stderr=PIPE,
        ).communicate()


# initiate servers directory and return list of sub-directories
def check_servers(servers_path):
    # ensure servers path exists
    if not os.path.exists(servers_path):
        os.makedirs(servers_path, exist_ok=True)
        log.info(f"created servers directory at {servers_path}")

    # initialize existing instances
    try:
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
def validate_server_files(username, app_path, server_name):
    log.info(f"initializing instance {server_name}...")
    instance_path = os.path.join(app_path, "servers", server_name)

    needs_config_edit = False

    if os.path.isdir(instance_path) is not True or len(os.listdir(instance_path)) == 0:
        log.info("creating instance...")
        subprocess.run(
            [
                f"{os.path.join(app_path, 'steamcmd', 'steamcmd.sh')}",
                f"+force_install_dir {instance_path}",
                f"+login {username}",
                "+app_update 223350",
                "+quit",
            ],
            shell=False,
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


# Function to read process output
def read_output(process, instance_name, output_queue):
    while True:
        if process.poll() is not None:
            # Process has terminated
            log.info(
                f"Server {instance_name} process terminated with code {process.returncode}"
            )
            break

        # Read stdout
        line = process.stdout.readline()
        if line:
            output_queue.put((instance_name, "stdout", line.decode().strip()))

        # Read stderr
        line = process.stderr.readline()
        if line:
            output_queue.put((instance_name, "stderr", line.decode().strip()))

        # Prevent CPU hogging
        time.sleep(0.1)


# Function to process output from the queue
def process_output(output_queue):
    while True:
        try:
            instance_name, stream, line = output_queue.get(timeout=1)
            if stream == "stdout":
                log.info(f"[{instance_name}] {line}")
            else:
                log.warning(f"[{instance_name}] ERROR: {line}")
            output_queue.task_done()
        except Exception:
            # No output available or queue is empty
            time.sleep(0.1)


# start instance with threading
def start_server(
    app_path, instance, port, client_mods, server_mods, logs, output_queue
):
    instance_path = os.path.join(app_path, "servers", instance)

    # Build command arguments, filtering out empty ones
    args = [os.path.join(instance_path, "DayZServer")]

    # Add basic arguments
    args.extend(["-autoinit", "-steamquery"])

    # Add config path
    args.append(f"-config={os.path.join(instance_path, 'serverDZ.cfg')}")

    # Make sure we specify both main port and steam query port (port+1)
    args.append(f"-port={port}")
    # args.append(f"-steamQueryPort={steam_query_port}")  # Add explicit query port

    # Add other paths
    args.append(f"-BEpath={os.path.join(instance_path, 'battleye')}")
    args.append(f"-profiles={os.path.join(instance_path, 'profiles')}")

    # Add mods if specified
    if client_mods:
        args.append(f"-mod={client_mods}")

    if server_mods:
        args.append(f"-servermod={server_mods}")

    # Add logs and freezecheck
    if logs:
        args.append(logs)

    args.append("-freezecheck")

    log.debug(f"Starting server {instance} with command: {' '.join(args)}")

    # Start the process with stdout and stderr piping
    process = subprocess.Popen(
        args,
        cwd=instance_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,  # Line buffered
        universal_newlines=False,  # Keep as bytes for binary output
    )

    # Create a thread to read the output
    output_thread = threading.Thread(
        target=read_output, args=(process, instance, output_queue), daemon=True
    )
    output_thread.start()

    return {
        "instance": instance,
        "process": process,
        "pid": process.pid,
        "port": port,
        "thread": output_thread,
    }


# monitor instance
async def monitor_process(process):
    try:
        stdout, stderr = await process.communicate()
        if stdout:
            log.info(f"Server output: {stdout.decode()}")
        if stderr:
            log.info(f"Server error: {stderr.decode()}")
    except Exception as e:
        log.info(f"Monitoring failed: {e}")
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()


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
                    log.warning(f"Error reading meta.cpp for mod {mod_id}: {e}")

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
            log.warning("Could not find Steam workshop content directory")
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
                    f"{username}",
                    "+workshop_download_item",
                    "221100",
                    f"{mod_id}",
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
                        f"Error downloading mod {mod_id}: {process.stderr.decode('utf-8')}"
                    )
                else:
                    log.info(f"Successfully downloaded mod {mod_id}")

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
                        log.warning(f"Failed to create symlink for mod {mod_id}: {e}")

            except subprocess.TimeoutExpired:
                log.error(f"Timeout while downloading mod {mod_id}")
            except Exception as e:
                log.error(f"Error processing mod {mod_id}: {e}")
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
                log.warning(f"Failed to parse meta.cpp for mod {mod_id}: {e}")

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


class A2SQueryException(Exception):
    """Exception raised for errors in the A2S query."""

    pass

    def a2s_info_query(ip, port, timeout=5.0):
        """
        Performs a Source Engine A2S_INFO query to check if a server is visible.

        Args:
            ip: Server IP address
            port: steam query port
            timeout: Query timeout in seconds

        Returns:
            dict: Server information if visible, None otherwise
        """
        # A2S_INFO request packet
        request = b"\xff\xff\xff\xffTSource Engine Query\x00"

        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)

            # Send request
            sock.sendto(request, (ip, port))

            # Receive response
            response = sock.recv(4096)

            # Check for split packet (common for Source servers)
            if response[0:4] == b"\xff\xff\xff\xff":
                # Simple packet, continue processing
                response = response[4:]
            elif response[0:4] == b"\xfe\xff\xff\xff":
                # Split packet, not handling these for simplicity
                # More complex handling would reassemble multi-packet responses
                raise A2SQueryException("Split packet responses not supported")
            else:
                raise A2SQueryException("Invalid response header")

            # Parse response
            if response[0] != 0x49:  # 'I' response header
                raise A2SQueryException(f"Invalid response type: {response[0]}")

            # Extract server information
            protocol = response[1]

            # Extract server name (null-terminated string)
            name_end = response.find(b"\x00", 2)
            if name_end == -1:
                raise A2SQueryException("Malformed response - cannot find server name")
            name = response[2:name_end].decode("utf-8", errors="replace")

            # Extract map name
            map_start = name_end + 1
            map_end = response.find(b"\x00", map_start)
            if map_end == -1:
                raise A2SQueryException("Malformed response - cannot find map name")
            map_name = response[map_start:map_end].decode("utf-8", errors="replace")

            # Extract game directory
            dir_start = map_end + 1
            dir_end = response.find(b"\x00", dir_start)
            if dir_end == -1:
                raise A2SQueryException(
                    "Malformed response - cannot find game directory"
                )
            game_dir = response[dir_start:dir_end].decode("utf-8", errors="replace")

            # Extract game description
            desc_start = dir_end + 1
            desc_end = response.find(b"\x00", desc_start)
            if desc_end == -1:
                raise A2SQueryException(
                    "Malformed response - cannot find game description"
                )
            description = response[desc_start:desc_end].decode(
                "utf-8", errors="replace"
            )

            # Move to the bytes after description
            current_pos = desc_end + 1

            # Get remaining info - app ID and player info
            # Note: This assumes the response format hasn't changed, which can happen
            if len(response) >= current_pos + 6:
                app_id = struct.unpack("<H", response[current_pos : current_pos + 2])[0]
                current_pos += 2

                players = response[current_pos]
                current_pos += 1

                max_players = response[current_pos]
                current_pos += 1

                bots = response[current_pos]
                current_pos += 1

                server_type = chr(response[current_pos])
                current_pos += 1

                # Parse environment and visibility
                if current_pos < len(response):
                    environment = chr(response[current_pos])
                    current_pos += 1
                else:
                    environment = "?"

                if current_pos < len(response):
                    visibility = response[current_pos]
                    current_pos += 1
                else:
                    visibility = -1

                # Additional fields like VAC status may be available but not parsed here

            server_info = {
                "protocol": protocol,
                "name": name,
                "map": map_name,
                "directory": game_dir,
                "description": description,
                "app_id": app_id if "app_id" in locals() else None,
                "players": players if "players" in locals() else None,
                "max_players": max_players if "max_players" in locals() else None,
                "bots": bots if "bots" in locals() else None,
                "server_type": server_type if "server_type" in locals() else None,
                "environment": environment if "environment" in locals() else None,
                "visibility": visibility if "visibility" in locals() else None,
                "response": True,
            }

            return server_info

        except socket.timeout:
            return {"response": False, "reason": "Timeout"}
        except socket.error as e:
            return {"response": False, "reason": f"Socket error: {e}"}
        except A2SQueryException as e:
            return {"response": False, "reason": str(e)}
        except Exception as e:
            return {"response": False, "reason": f"Unknown error: {e}"}
        finally:
            try:
                sock.close()
            except Exception:
                pass


def check_server_visibility(servers, retry_count=3, retry_delay=5):
    """
    Checks visibility of all running DayZ servers.

    Args:
        servers: Dictionary of server information
        retry_count: Number of times to retry failed checks
        retry_delay: Delay between retries in seconds

    Returns:
        Dict of server names with visibility status
    """
    results = {}

    log.info("Checking server visibility...")

    for instance, server_info in servers.items():
        port = int(
            server_info.get(server_info["port"], server_info["steam_query_port"])
        )
        ip = "127.0.0.1"  # Assuming local server, use actual IP for remote servers
        # ip = public_ip.get()

        log.info(f"Checking server {instance} at {ip}:{port}")

        # Try multiple times in case of initial issues
        for attempt in range(retry_count):
            query_result = A2SQueryException.a2s_info_query(ip, port)

            if query_result.get("response") is True:
                # Server is visible
                results[instance] = {
                    "visible": True,
                    "name": query_result.get("name", "Unknown"),
                    "players": query_result.get("players", "?"),
                    "max_players": query_result.get("max_players", "?"),
                    "port": port,
                }
                log.info(
                    f"✓ Server {instance} is visible as '{query_result.get('name')}' with {query_result.get('players', '?')}/{query_result.get('max_players', '?')} players"
                )
                break
            else:
                if attempt < retry_count - 1:
                    log.warning(
                        f"× Server {instance} check failed ({query_result.get('reason')}), retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                else:
                    # All retries failed
                    results[instance] = {
                        "visible": False,
                        "reason": query_result.get("reason", "Unknown error"),
                        "port": port,
                    }
                    log.error(
                        f"× Server {instance} is NOT VISIBLE: {query_result.get('reason', 'Unknown error')}"
                    )

    return results


# lets go
def main():
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
    steamcmd_path = os.path.join(app_path, "steamcmd")

    # grab username from dman config
    user_info = dman_config["user"]["info"]
    username = user_info["steam_username"]

    # grab server instances from dman config
    instance_info = dman_config["servers"]["list"]
    log.debug(f"instance_info: {instance_info}")

    if username == "STEAM_USERNAME":
        log.info("replace STEAM_USERNAME in dman.toml")
        return

    # ensure steamcmd is installed
    check_steamcmd(steamcmd_path)

    # ensure servers directory is initiated
    check_servers(servers_path)

    # initialize instances to be run using dman config
    instances = [key for key in instance_info.keys()]
    active_instances = [
        key for key in instance_info.keys() if instance_info[key] is True
    ]
    log.debug(f"active_instances: {active_instances}")

    # confirm instance integrity and extract configurations
    instances_needing_edits = []
    if len(instances) > 0:
        server_configs = []
        for instance in instances:
            instance_name, needs_edit = validate_server_files(
                username, app_path, instance
            )
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
        log.warning(
            f"The following instances need configuration: {', '.join(instances_needing_edits)}"
        )
        log.warning(
            "Please edit their server.toml files before running the script again."
        )
        exit()

    try:
        mod_dict = validate_workshop_mods(username, server_configs, app_path)
        log.debug(f"mod_dict: {mod_dict}")
    except Exception as e:
        log.error(f"Error validating workshop mods: {e}")
        mod_dict = {}  # Use empty dict if validation fails

    # Create output queue and start output processing thread
    output_queue = Queue()
    output_processor = threading.Thread(
        target=process_output, args=(output_queue,), daemon=True
    )
    output_processor.start()

    # this is where we store server information and the actual processes
    servers = {}
    server_processes = []

    # Make sure each server has a unique port pair (main port and query port)
    used_ports = set()

    # initiate configurations with server.tomls
    for instance in active_instances:
        # Find the corresponding server config
        instance_index = instances.index(instance)
        server_config = server_configs[instance_index]

        server_info = server_config["server"]["info"]
        port = server_info["port"]

        # Make sure ports don't conflict
        if port in used_ports:
            log.warning(
                f"Port conflict detected for {instance} on port {port}, please adjust in server.toml"
            )
            exit()

        # Mark ports as used
        used_ports.add(int(port))

        client_mods = server_info["client_mods"]
        server_mods = server_info["server_mods"]
        logs = server_info["logs"]

        # Process and update mods
        if client_mods or server_mods:
            try:
                updated_client_mods, updated_server_mods = import_mods(
                    app_path, instance, client_mods, server_mods, mod_dict
                )

                # Update the server_config in memory
                server_config["server"]["info"]["client_mods"] = updated_client_mods
                server_config["server"]["info"]["server_mods"] = updated_server_mods

                # Update the config file
                with open(
                    os.path.join(app_path, "servers", instance, "server.toml"), "w"
                ) as f:
                    toml.dump(server_config, f)

                # Use updated mod strings
                client_mods = updated_client_mods
                server_mods = updated_server_mods
            except Exception as e:
                log.error(f"Error importing mods for {instance}: {e}")

        # Store server info
        servers[instance] = {
            "app_path": app_path,
            "instance": instance,
            "port": port,
            "client_mods": client_mods,
            "server_mods": server_mods,
            "logs": logs,
        }

    log.debug(f"Prepared servers: {servers}")

    # for calculating wait timer
    mod_total = 0

    # Start all server processes
    for instance, args in servers.items():
        try:
            log.info(f"Starting server {instance} on port {args['port']}...")

            # Enforce a short delay between server starts to reduce resource contention
            if server_processes:  # If we've already started at least one server
                time.sleep(5)  # Wait 5 seconds between server starts

            process_info = start_server(
                args["app_path"],
                args["instance"],
                args["port"],
                args["client_mods"],
                args["server_mods"],
                args["logs"],
                output_queue,
            )

            server_processes.append(process_info)
            log.info(f"Server {instance} started with PID {process_info['pid']}")

            mod_total += len(args["client_mods"].replace("@", "").split(";")) + len(
                args["server_mods"].replace("@", "").split(";")
            )

        except Exception as e:
            log.error(f"Failed to start server {instance}: {e}")

    # Allow servers some time to initialize fully before checking visibility
    # wait time is dependent on mod total because more mods = longer server load time
    wait_time = 60 * (mod_total // 20) if mod_total > 0 else 60
    log.debug(f"mod_total: {mod_total}")
    log.info(f"Waiting {wait_time} seconds for servers to fully initialize...")
    time.sleep(wait_time)

    # Monitor processes
    try:
        while True:
            all_alive = True
            for server_info in server_processes:
                instance = server_info["instance"]
                process = server_info["process"]

                # Check if process is still running
                if process.poll() is not None:
                    log.warning(
                        f"Server {instance} (PID {server_info['pid']}) has terminated with code {process.returncode}"
                    )
                    all_alive = False

                    # Optionally restart the server here if needed
                    # For now, just log the termination

            if not all_alive:
                log.warning("One or more servers have terminated")
                # Option 1: Break the loop and exit when any server terminates
                # break

                # Option 2: Continue running remaining servers
                # pass

                # For this example, we'll continue running

            # Sleep to prevent CPU hogging
            time.sleep(30)

    except KeyboardInterrupt:
        log.info("Shutdown requested...")

        # Attempt graceful shutdown of all servers
        for server_info in server_processes:
            instance = server_info["instance"]
            process = server_info["process"]

            if process.poll() is None:  # If process is still running
                log.info(f"Terminating server {instance} (PID {server_info['pid']})...")
                try:
                    process.terminate()
                    # Wait up to 10 seconds for graceful termination
                    for _ in range(10):
                        if process.poll() is not None:
                            break
                        time.sleep(1)

                    # Force kill if still running
                    if process.poll() is None:
                        log.warning(
                            f"Server {instance} did not terminate gracefully, killing..."
                        )
                        process.kill()
                except Exception as e:
                    log.error(f"Error shutting down server {instance}: {e}")

        log.info("All servers stopped")

    # Return exit code
    return 0


if __name__ == "__main__":
    main()
