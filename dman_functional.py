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

from os import path, makedirs
from subprocess import Popen, PIPE

steamcmd = path.join("app", "steamcmd")
servers = path.join("app", "servers")


# run any command (pipe or not)
def command(input):
    output = Popen(
        input,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    output = str(output.communicate()[0])
    output = output[2 : len(output) - 3]

    return output


def install_steamcmd():
    print("Checking for steamcmd...")
    if path.isdir(steamcmd) is not True:
        print("No steamcmd found, installing...", end="", flush=True)
        makedirs(steamcmd)
        command(f'cd {steamcmd} && curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -')
        print("Done")
        print("Steamcmd installed")
    else:
        print("Steamcmd found")


def create_instance(name, username):
    print("Creating new server instance")
    instance_path = path.join("app", "servers", name)
    if path.isdir(instance_path) is not True:
        makedirs(instance_path)
        command(f"{path.join(steamcmd, "steamcmd.sh")} +force_install_dir {path.join(servers, name)} +login {username} +app_update 223350 +quit")


def main():
    install_steamcmd()




main()