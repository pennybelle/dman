import os
import subprocess
import asyncio
import logging
import shutil
import time
import toml

from subprocess import Popen, PIPE
from shutil import copyfile, copytree, copy2
from sys import exit
from __logger__ import setup_logger

log = logging.getLogger(__name__)
setup_logger(level=10, stream_logs=True)
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


# start instance
async def start_server(instance_path, port, client_mods, server_mods, logs):
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

    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=instance_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Store PID and process object
    server_info = {"pid": process.pid, "process": process, "port": port}

    # Start monitoring task
    asyncio.create_task(monitor_process(process))

    return server_info


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
    mod_dict = {}

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

            mod_dict[mod_id] = name
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

    log.debug(f"mods to download: {mods_to_download}")

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
                    f"+login",
                    f"{username}",
                    f"+workshop_download_item",
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

        mod_dict[mod_id] = name
        known_mod_names[name] = mod_id

    return mod_dict


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
def import_mods(app_path, instance, client_mods, server_mods, mod_dict):
    """
    copy mods to server directories and update config strings
    with mod names instead of IDs
    """
    # create reverse lookup from mod name to mod ID
    name_to_id = {name: mod_id for mod_id, name in mod_dict.items()}

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
            if mod in mod_dict:
                mod_name = mod_dict[mod]
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

    mod_dict = validate_workshop_mods(username, server_configs, app_path)
    log.debug(f"mod_dict: {mod_dict}")

    try:
        mod_dict = validate_workshop_mods(username, server_configs, app_path)
        log.debug(f"mod_dict: {mod_dict}")
    except Exception as e:
        log.error(f"Error validating workshop mods: {e}")
        mod_dict = {}  # Use empty dict if validation fails

    # this is where we store server information and the actual processes
    servers = {}
    processes = []

    # # initiate configurations with server.tomls
    # for id, instance in enumerate(active_instances):
    #     server_config = server_configs[id]

    #     server_info = server_config["server"]["info"]
    #     port = server_info["port"]
    #     # webhook = server_info["discord_webhook"]
    #     client_mods = server_info["client_mods"]
    #     server_mods = server_info["server_mods"]
    #     logs = server_info["logs"]

    #     instance_path = os.path.join(app_path, "servers", instance)
    #     servers[instance] = {
    #         "instance_path": instance_path,
    #         "port": port,
    #         "client_mods": client_mods,
    #         "server_mods": server_mods,
    #         "logs": logs,
    #     }

    #     if client_mods or server_mods:
    #         client_mods, server_mods = import_mods(
    #             app_path, instance, client_mods, server_mods, mod_dict
    #         )
    #         with open(
    #             os.path.join(
    #                 app_path,
    #                 "servers",
    #                 instance,
    #                 "server.toml",
    #             ),
    #             "w",
    #         ) as f:
    #             server_config["server"]["info"]["client_mods"] = client_mods
    #             server_config["server"]["info"]["server_mods"] = server_mods
    #             toml.dump(server_config, f)

    # initiate configurations with server.tomls
    for id, instance in enumerate(active_instances):
        # Find the corresponding server config
        # This assumes active_instances is a subset of instances
        instance_index = instances.index(instance)
        server_config = server_configs[instance_index]

        server_info = server_config["server"]["info"]
        port = server_info["port"]
        client_mods = server_info["client_mods"]
        server_mods = server_info["server_mods"]
        logs = server_info["logs"]

        instance_path = os.path.join(app_path, "servers", instance)

        # First collect all the server information
        servers[instance] = {
            "instance_path": instance_path,
            "port": port,
            "client_mods": client_mods,
            "server_mods": server_mods,
            "logs": logs,
        }

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

    # Prepare the server processes
    for instance, arg in servers.items():
        processes.append(
            start_server(
                arg["instance_path"],
                arg["port"],
                arg["client_mods"],
                arg["server_mods"],
                arg["logs"],
            )
        )

    server_instances = await asyncio.gather(*processes)
    log.debug(server_instances)

    while True:
        await asyncio.sleep(60)


asyncio.run(main())
