import os
import subprocess
import asyncio
import logging
import toml

from subprocess import Popen, PIPE
from shutil import copyfile, copytree
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
        f"-servermod={server_mods}" if server_mods else "",
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


def validate_workshop_mods(username, server_configs, app_path):
    steamcmd_path = os.path.join(app_path, "steamcmd")
    mod_templates_path = os.path.join(
        steamcmd_path, "steamapps", "workshop", "content", "221100"
    )

    mod_array = []

    # load client mods from each server.toml and parse out dupes & empty entries
    meta = []
    client_mod_list = list(
        filter(
            None, [config["server"]["info"]["client_mods"] for config in server_configs]
        )
    )
    if client_mod_list:
        client_mod_list = [
            mod_list.replace("@", "").split(";") for mod_list in client_mod_list
        ]
        for mod_list in client_mod_list:
            for mod in mod_list:
                if mod.isdigit() and len(mod) == 10:
                    meta.append(mod)
        client_mod_list = list(dict.fromkeys(meta))  # remvoe dupes
    log.debug(f"client_mod_list: {client_mod_list}")

    meta = []
    # load server mods from each server.toml and parse out dupes
    server_mod_list = list(
        filter(
            None, [config["server"]["info"]["server_mods"] for config in server_configs]
        )
    )
    log.debug(f"server_mod_list: {server_mod_list}")
    if server_mod_list:
        server_mod_list = [
            mod_list.replace("@", "").split(";") for mod_list in server_mod_list
        ]
        for mod_list in server_mod_list:
            for mod in mod_list:
                if mod.isdigit() and len(mod) == 10:
                    meta.append(mod)
        server_mod_list = list(dict.fromkeys(meta))  # remove dupes

    mod_array = client_mod_list + server_mod_list

    # exempt already installed mods
    if os.path.exists(mod_templates_path):
        # existing_mods = next(os.walk(mod_templates_path))[1]
        existing_mods = [
            d
            for d in os.listdir(mod_templates_path)
            if os.path.isdir(os.path.join(mod_templates_path, d))
        ]
        log.debug(f"existing_mods: {existing_mods}")
        mod_list = list(set(mod_array) - set(existing_mods))

    log.debug(f"mod_list: {mod_list}")

    workshop_list = ""

    # create arg for mod downloads, only download valid mod ids
    for mod in mod_list:
        log.debug(f"mod: {mod}")
        if mod.isdigit() and len(mod) == 10:
            workshop_list += f" +workshop_download_item 221100 {mod}"
    workshop_list = workshop_list.strip()  # cleaup extra whitespace
    log.debug(f"workshop_list: {workshop_list}")
    log.debug(f"mod_array: {mod_array}")

    # if there are valid mods to download, download them
    if workshop_list:
        # create symlinks from default location to project directory
        default_workshop_path = os.path.expanduser(
            os.path.join(
                "~",
                ".local",
                "share",
                "Steam",
                "steamapps",
                "workshop",
                "content",
                "221100",
            )
        )

        # Run steamcmd to download the mods (they'll go to default location)
        subprocess.run(
            [
                "./steamcmd.sh",
                f"+login {username}",
            ]
            + workshop_list.split()
            + ["+quit"],
            shell=False,
            cwd=steamcmd_path,
        )

        # ensure target directory exists
        os.makedirs(mod_templates_path, exist_ok=True)

        # create symlinks for each downloaded mod
        for mod_id in mod_list:
            default_mod_path = os.path.join(default_workshop_path, mod_id)
            target_mod_path = os.path.join(mod_templates_path, mod_id)

            if os.path.exists(default_mod_path) and not os.path.exists(target_mod_path):
                os.symlink(default_mod_path, target_mod_path)
                log.info(
                    f"Created symlink for mod {mod_id} from {default_mod_path} to {target_mod_path}"
                )

        print()  # steamcmd doesnt print newline when finished downloading..........

    else:
        log.info("no new mods to download")

    name = ""
    mod_dict = {}

    # get mod name from meta.cpp and apply it to workshop.cfg
    log.debug("this is the part")
    for mod in mod_array:
        log.debug(f"mod: {mod}")

        meta_path = os.path.join(mod_templates_path, mod, "meta.cpp")

        if os.path.exists(meta_path):
            with open(meta_path) as cpp:
                lines = cpp.read().splitlines()

            log.debug(f"lines: {lines}")

            for line in lines:
                if "name" in line:
                    log.debug(f"line: {line}")
                    name = (
                        line.replace('"', "")
                        .replace(";", "")
                        .replace("name =", "")
                        .strip()
                    )
                    log.debug(f"name: {name}")

        else:
            log.warning(f"mod {mod} not found in {mod_templates_path}")
            name = "Not Found"

        mod_dict[mod] = name

    return mod_dict


def import_mods(app_path, instance, client_mods, server_mods, mod_dict):
    # copy files from steamcmd to server root
    client = client_mods.replace("@", "").split(";")
    server = server_mods.replace("@", "").split(";")

    def copy_and_rename(mod):
        instance_path = os.path.join(app_path, "servers", instance)
        try:
            if (
                os.path.exists(os.path.join(instance_path, f"@{mod_dict[mod]}"))
                is not True
            ):
                copytree(
                    os.path.join(
                        app_path,
                        "steamcmd",
                        "steamapps",
                        "workshop",
                        "content",
                        "221100",
                        mod,
                    ),
                    os.path.join(app_path, "servers", instance, f"@{mod_dict[mod]}"),
                )
        except KeyError:
            pass

    for mod in client:
        copy_and_rename(mod)

    for mod in server:
        copy_and_rename(mod)

    log.debug(f"client: {client}")
    log.debug(f"server: {server}")

    # replace ids with modnames in args
    for index, mod in enumerate(client):
        try:
            client[index] = mod_dict[mod]
        except KeyError:
            pass

    client_mods = f"@{';@'.join(client)}" if client_mods else ""

    for index, mod in enumerate(server):
        try:
            server[index] = mod_dict[mod]
        except KeyError:
            pass

    server_mods = f"@{';@'.join(server)}" if server_mods else ""

    log.debug(f"client: {client}")
    log.debug(f"server: {server}")
    log.debug(f"client_mods: {client_mods}")
    log.debug(f"server_mods: {server_mods}")

    return client_mods, server_mods


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

    else:
        log.warning("no instances in dman.toml")
        return

    mod_dict = validate_workshop_mods(username, server_configs, app_path)
    log.debug(f"mod_dict: {mod_dict}")

    # this is where we store server information and the actual processes
    servers = {}
    processes = []

    # initiate configurations with server.tomls
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

        if client_mods or server_mods:
            client_mods, server_mods = import_mods(
                app_path, instance, client_mods, server_mods, mod_dict
            )
            with open(
                os.path.join(
                    app_path,
                    "servers",
                    instance,
                    "server.toml",
                ),
                "w",
            ) as f:
                server_config["server"]["info"]["client_mods"] = client_mods
                server_config["server"]["info"]["server_mods"] = server_mods
                toml.dump(server_config, f)

    for arg in servers.values():
        processes.append(start_server(arg[0], arg[1], arg[2], arg[3], arg[4]))

    server_instances = await asyncio.gather(*processes)
    log.debug(server_instances)

    # while True:
    await asyncio.sleep(420)


asyncio.run(main())
