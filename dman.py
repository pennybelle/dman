import os
import subprocess
import asyncio
import toml
import logging

from subprocess import Popen, PIPE
from shutil import copyfile
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
    log.info("checking for steamcmd...")
    if os.path.isdir(steamcmd) is not True:
        log.info("not found, installing...(this could take a while)")
        os.makedirs(steamcmd)
        Popen(
            f'cd {steamcmd} && curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -',
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

        log.warning("edit the server's server.toml before proceeding")
        exit()

    return server_name


def run_server(servers, server_name):
    instance_path = os.path.join(servers, server_name)
    subprocess.run(
        [
            os.path.join(instance_path, "DayZServer"),
            f"-config={os.path.join(instance_path, 'serverDZ.cfg')}",
            "-port=2301",
            f"-BEpath={os.path.join(instance_path, 'battleye')}",
            f"-profiles={os.path.join(instance_path, 'profiles')}",
            "-dologs",
            "-adminlog",
            "-netlog",
            "-freezecheck",
        ],
        cwd=instance_path,
    )


async def start_server(instance_path, port, client_mods, server_mods, logs):
    args = [
        os.path.join(instance_path, "DayZServer"),
        f"-config={os.path.join(instance_path, 'serverDZ.cfg')}",
        f"-port={port}",
        f"-BEpath={os.path.join(instance_path, 'battleye')}",
        f"-profiles={os.path.join(instance_path, 'profiles')}",
        f"-mod={client_mods}" if client_mods else "",
        server_mods,
        " " + logs,
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


# def create_instance(username, steamcmd_path, servers_path, name):
#     os.makedirs(os.path.join(servers_path, name), exist_ok=True)
#     check_server(username, steamcmd_path, servers_path, name)


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
    if len(instances) > 0:
        server_configs = [
            toml.load(
                os.path.join(
                    app_path,
                    "servers",
                    validate_server_files(username, app_path, instance),
                    "server.toml",
                )
            )
            for instance in instances
        ]
        log.debug(f"server_configs: {server_configs}")

    # this is where we store server information and the actual processes
    servers = {}
    processes = []

    #
    for id, instance in enumerate(active_instances):
        server_config = server_configs[id]

        server_info = server_config["server"]["info"]
        port = server_info["port"]
        # webhook = server_info["discord_webhook"]
        client_mods = server_info["client_mods"]
        server_mods = server_info["server_mods"]
        logs = server_info["logs"]

        instance_path = os.path.join(app_path, "servers", instance)
        servers[instance] = [instance_path, port, client_mods, server_mods, logs]

    log.debug(f"servers: {servers}")
    # start_servers = log.info()

    for arg in servers.values():
        processes.append(start_server(arg[0], arg[1], arg[2], arg[3], arg[4]))

    server_instances = await asyncio.gather(*processes)
    log.debug(server_instances)

    # while True:
    await asyncio.sleep(300)


asyncio.run(main())
