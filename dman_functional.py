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
# import asyncio
# import shlex
# from os import path, makedirs
from subprocess import Popen, PIPE

# import pwd
# username = pwd.getpwuid(os.getuid())[0]
# dman_path = os.path.join("/", "home", username, "Documents", "GitHub", "dman")
# steamcmd = os.path.join(dman_path, "app", "steamcmd")
# servers = os.path.join(dman_path, "app", "servers")

steamcmd = os.path.join(os.getcwd(), "app", "steamcmd")
servers = os.path.join(os.getcwd(), "app", "servers")
username = None


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


def install_steamcmd():
    print("checking for steamcmd...")
    if os.path.isdir(steamcmd) is not True:
        print("no steamcmd found, installing...", end="", flush=True)
        os.makedirs(steamcmd)
        command(f'cd {steamcmd} && curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -')
        print("done")
        print("steamcmd installed")
    else:
        print("steamcmd found")


def check_server(server_name):
    print(f"looking for server instance {server_name}")
    instance_path = os.path.join(servers, server_name)
    if os.path.isdir(instance_path) is not True:
        print("no server by that name, creating...")
        # os.makedirs(instance_path)
        if username is None:
            username = input("enter your steam username: ")
        subprocess.run([f'{os.path.join(steamcmd, "steamcmd.sh")}', f"+force_install_dir {instance_path}", f"+login {username}", "+app_update 223350", "+quit"], shell=False)
        print(f"server instance {server_name} has been created")
        # print(server)
    else:
        print(f"server instance {server_name} has been found")


def run_server(server_name):
    instance_path = os.path.join(servers, server_name)
    subprocess.run([
        os.path.join(instance_path, "DayZServer"), 
        f'-config={os.path.join(instance_path, "serverDZ.cfg")}', 
        "-port=2301", 
        f'-BEpath={os.path.join(instance_path, "battleye")}', 
        f'-profiles={os.path.join(instance_path, "profiles")}', 
        "-dologs", 
        "-adminlog", 
        "-netlog", 
        "-freezecheck"
    ], cwd=instance_path)

    # print(server.pid)

    # command(f"cd {instance_path} && ./DayZServer -config={os.path.join(instance_path, "serverDZ.cfg")} -port=2301 -BEpath={os.path.join(instance_path, "battleye")} -profiles={os.path.join(instance_path, "profiles")} -dologs -adminlog -netlog -freezecheck")


async def start_server(instance_path, port):
    args = [
        os.path.join(instance_path, "DayZServer"),
        f'-config={os.path.join(instance_path, "serverDZ.cfg")}',
        f'-port={port}',
        f'-BEpath={os.path.join(instance_path, "battleye")}',
        f'-profiles={os.path.join(instance_path, "profiles")}',
        "-dologs",
        "-adminlog",
        "-netlog",
        "-freezecheck"
    ]

    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=instance_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Store PID and process object
    server_info = {
        'pid': process.pid,
        'process': process,
        'port': port
    }

    # Start monitoring task
    asyncio.create_task(monitor_process(process))

    return server_info


async def monitor_process(process):
    try:
        stdout, stderr = await process.communicate()
        if stdout:
            print(f'Server output: {stdout.decode()}')
        if stderr:
            print(f'Server error: {stderr.decode()}')
    except Exception as e:
        print(f'Monitoring failed: {e}')
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()


async def main():
    install_steamcmd()

    # print(os.getcwd())
    # run_server("pennybelle")

    instances = ["pennybelle1", "pennybelle2"]
    for instance in instances:
        check_server(instance)

    tasks = []
    for id, instance in enumerate(instances):
        instance_path = os.path.join(servers, instance)
        port = 2303 + id
        tasks.append(start_server(instance_path, port))

    server_instances = await asyncio.gather(*tasks)
    await asyncio.sleep(300)


asyncio.run(main())