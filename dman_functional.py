# fn_install_dayz(){
# 	if [ ! -f "${SERVER_ROOT}/steamcmd/steamcmd.sh" ]; then
# 		mkdir ${SERVER_ROOT}/steamcmd &> /dev/null
# 		curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxf - -C steamcmd
# 		printf "[ ${yellow}STEAM${default} ] Steamcmd installed\n"
# 	else
# 		printf "[ ${lightblue}STEAM${default} ] Steamcmd already installed\n"
# 	fi
# 	if [ ! -f "${SERVER_ROOT}/serverfiles/DayZServer" ]; then
# 		mkdir ${SERVER_ROOT}/serverfiles &> /dev/null
# 		mkdir ${SERVER_ROOT}/serverprofile &> /dev/null
# 		printf "[ ${yellow}DayZ${default} ] Downloading DayZ Server-Files!\n"
# 		fn_runvalidate_dayz
# 	else
# 		printf "[ ${lightblue}DayZ${default} ] The Server is already installed.\n"
# 		fn_opt_usage
# 	fi
# }

import os
import subprocess
import asyncio
import toml

# import asyncio
# import shlex
# from os import path, makedirs
from subprocess import Popen, PIPE
from shutil import copyfile

# import pwd
# username = pwd.getpwuid(os.getuid())[0]
# dman_path = os.path.join("/", "home", username, "Documents", "GitHub", "dman")
# steamcmd = os.path.join(dman_path, "app", "steamcmd")
# servers = os.path.join(dman_path, "app", "servers")


# used for downloading steamcmd
def command(input):
    output = Popen(
        input,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    output = output.communicate()

    return output


# def split_args(command):
#     return shlex.split(command)


def install_steamcmd(steamcmd):
    print("checking for steamcmd...", end="", flush=True)
    if os.path.isdir(steamcmd) is not True:
        print("not found, installing...", end="", flush=True)
        os.makedirs(steamcmd)
        command(
            f'cd {steamcmd} && curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -'
        )
    print("done")


def check_server(username, app_path, server_name):
    print(f"initializing instance {server_name}...", end="", flush=True)
    instance_path = os.path.join(app_path, "servers", server_name)

    if os.path.isdir(instance_path) is not True or len(os.listdir(instance_path)) == 0:
        print("not found, creating...", end="", flush=True)
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

        print("created")

    else:
        print("done")

    # make default toml
    if os.path.exists(os.path.join(instance_path, "dman.toml")) is not True:
        copyfile(
            os.path.join(os.getcwd(), "resources", "server_default_config.toml"),
            os.path.join(instance_path, "dman.toml"),
        )

    return server_name


def check_config(path):
    pass


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

    # print(server.pid)

    # command(f"cd {instance_path} && ./DayZServer -config={os.path.join(instance_path, "serverDZ.cfg")} -port=2301 -BEpath={os.path.join(instance_path, "battleye")} -profiles={os.path.join(instance_path, "profiles")} -dologs -adminlog -netlog -freezecheck")


async def start_server(instance_path, port, client_mods, server_mods, logs):
    args = [
        os.path.join(instance_path, "DayZServer"),
        f"-config={os.path.join(instance_path, 'serverDZ.cfg')}",
        f"-port={port}",
        f"-BEpath={os.path.join(instance_path, 'battleye')}",
        f"-profiles={os.path.join(instance_path, 'profiles')}",
        client_mods,
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
            print(f"Server output: {stdout.decode()}")
        if stderr:
            print(f"Server error: {stderr.decode()}")
    except Exception as e:
        print(f"Monitoring failed: {e}")
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()


def create_instance(username, steamcmd_path, servers_path, name):
    os.makedirs(os.path.join(servers_path, name), exist_ok=True)
    check_server(username, steamcmd_path, servers_path, name)


async def main():
    # steamcmd = os.path.join(os.getcwd(), "app", "steamcmd")
    # servers = os.path.join(os.getcwd(), "app", "servers")

    # print(os.getcwd())
    # run_server("pennybelle")

    dman_config_path = os.path.join(os.getcwd(), "dman.toml")
    default_dman_config_path = os.path.join(
        os.getcwd(), "resources", "dman_default_config.toml"
    )

    if os.path.exists(dman_config_path) is not True:
        copyfile(default_dman_config_path, dman_config_path)

    dman_config = toml.load(dman_config_path)

    # dman_info = dman_config["dman"]["info"]
    dman_path = os.getcwd()
    app_path = os.path.join(dman_path, "app")
    servers_path = os.path.join(app_path, "servers")

    user_info = dman_config["user"]["info"]
    username = user_info["steam_username"]

    if username == "STEAM_USERNAME":
        print("replace STEAM_USERNAME in dman.toml")

    install_steamcmd(os.path.join(app_path, "steamcmd"))

    # config_name = 'dman.toml'
    # dman_path = '~/dman'
    # steamcmd_path = '~/dman/steamcmd'

    # initialize existing instances
    instances = next(os.walk(servers_path))[1]
    print(instances)

    # instances = ["pennybelle1", "pennybelle2"]
    # for instance in instances:
    #     check_server(instance)

    # confirm instance integrity and extract configurations
    server_configs = [
        toml.load(
            os.path.join(
                app_path,
                "servers",
                check_server(username, app_path, instance),
                "dman.toml",
            )
        )
        for instance in instances
    ]
    print(server_configs)

    tasks = []
    for id, instance in enumerate(instances):
        server_config = server_configs[id]

        server_info = server_config["server"]["info"]
        # name = server_info["name"]
        port = server_info["port"]
        # webhook = server_info["discord_webhook"]
        client_mods = server_info["client_mods"]
        server_mods = server_info["server_mods"]
        logs = server_info["logs"]

        instance_path = os.path.join(app_path, "servers", instance)
        # port = 2303 + id
        tasks.append(start_server(instance_path, port, client_mods, server_mods, logs))

    server_instances = await asyncio.gather(*tasks)
    await asyncio.sleep(600)


asyncio.run(main())
