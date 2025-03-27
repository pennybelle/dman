import os
import pwd
import asyncio
import logging
import datetime
import toml

from subprocess import check_output
from shutil import copyfile
from os import system, name
from rich.console import Console

from modules.format import print_center
from modules.main_menu import main_menu, title_screen
from modules.serverstate import ServerState
from modules.rconclient import schedule_server_restart
from modules.steamcmd import (
    check_steamcmd,
    # update_servers,
    validate_workshop_mods,
    import_mods,
    check_and_update_mods,
)
from modules.servers import check_servers, validate_server_files, start_server
# from modules.update_servers import update_servers

log = logging.getLogger(__name__)

console = Console()

# Dictionary to track server states
server_states = {}


# check if user is logged in as root
def is_root():
    if pwd.getpwuid(os.getuid())[0] == "root":
        return True
    else:
        return False


# lets go
async def main():
    # title_screen()

    # cant run this script as root
    if is_root():
        print("\nYou cannot run dman as root, sorry!\n")
        return

    # print to CLI UI, center text
    print_center("Initializing steamcmd...")

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
    # check_server_template(app_path, username, password)

    # ensure servers directory is initiated
    check_servers(servers_path)

    # # update servers to latest version
    # update_servers(app_path, username, password)

    # # initialize instances to be run using dman config
    instance_keys = [key for key in instance_info.keys()]
    active_instances = [
        key for key in instance_info.keys() if instance_info[key] is True
    ]
    inactive_instances = [
        key for key in instance_info.keys() if instance_info[key] is not True
    ]
    log.debug(f"active_instances: {active_instances}")
    print("Done\n")

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

        # print()  # add newline in ui
        # check_and_update_mods(
        #     username, password, server_configs, app_path, force_check=True
        # )

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

    if not active_instances:
        print("No active instances, enable them in dman.toml :3")
        return

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

        # rcon_info = server_config["server"]["rcon"]
        # ensure battleye configos.path.join(
        default_be_config_path = os.path.join(
            os.getcwd(),
            "app",
            "steamcmd",
            "server_template",
            "battleye",
            "BEServer_x64.cfg",
        )
        be_config_path = os.path.join(
            app_path, "servers", instance, "battleye", "BEServer_x64.cfg"
        )

        if os.path.exists(be_config_path) is not True:
            copyfile(default_be_config_path, be_config_path)

        # gather rcon info from be config
        with open(be_config_path, "r") as cfg:
            cfg_contents = cfg.readlines()
            rcon_pass = cfg_contents[0].replace("RConPassword", "").strip()
            rcon_port = int(cfg_contents[2].replace("RConPort", "").strip())

        is_active = instance_info[instance]

        # First collect all the server information
        servers[instance] = {
            "is_active": is_active,
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
            "pid": "",
            "port": port if is_active else "",
            "start_time": datetime.datetime.now(),
            "last_update": datetime.datetime.now(),
            "players": "",
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

    # Prepare the server processes
    for instance, data in servers.items():
        # print(servers)
        if data["is_active"]:
            log.debug(f"Starting server {instance}")
            processes.append(
                start_server(
                    server_states,
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
    await asyncio.sleep(2)

    # Before the main loop
    cached_states = {}
    for server, data in server_states.items():
        cached_states[server] = {"state": data["state"], "players": data["players"]}
    main_menu(server_states)  # Show initial state

    # Set up restart scheduling
    scheduling_tasks = []
    for server in server_instances:
        scheduling_tasks.append(
            await schedule_server_restart(
                server_states,
                app_path=app_path,
                instance_name=server["instance"],
                restart_delay=180,
                warning_time=1800,
            )
        )

    def get_console_size():
        # gather raw output from console
        # console_width = check_output(["stty", "size"], stdout=PIPE)
        # format raw data into int
        # console_width = int(console_width.communicate().decode())

        console_size = check_output(["stty", "size"]).decode("utf-8").split()
        h = int(console_size[0])
        w = int(console_size[1])

        return w, h

    cached_res = list(get_console_size())

    # Main monitoring loop - we'll return the server_instances so they can be cleaned up
    try:
        while True:
            running_servers = [instance for instance in active_instances]
            stopped_servers = [instance for instance in inactive_instances]
            await asyncio.sleep(0.1)  # update CLI UI every tenth of a second

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
                    break  # Also check for removed servers

            # w, h = list(get_console_size())
            # for dimension in cached_res:
            res = list(get_console_size())
            # print(res, cached_res)
            # await asyncio.sleep(1)
            if res != cached_res:
                needs_update = True
                cached_res = res
            # else:
            #     needs_update = False

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
    system("cls" if name == "nt" else "clear")
    print_center("Closing dman...", beginning="\n")

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
