# Inspired by haywardgg's DayZ_Server_Manager
# https://github.com/haywardgg/DayZ_Server_Manager

import os, toml, cv2

from os import path, join
from subprocess import Popen, PIPE

default = r"\e[0m]"
red = r"\e[31m"
green = r"\e[32m"
yellow = r"\e[33m"
lightyellow = r"\e[93m"
blue = r"\e[34m"
lightblue = r"\e[94m"
magenta = r"\e[35m"
cyan = r"\e[36m"
# carriage return & erase to end of line
creeol = r"\r\033[K"

# SERVER_CONFIG = "config.py"

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


class Config:
    def __init__(self, config_path):
        try:
            server_configs = toml.load(config_path)

            self.server_info = server_configs["server"]
            self.name = self.server_info["name"]
            self.port = self.server_info["port"]
            self.webhook = self.server_info["discord_webhook"]
            self.client_mods = self.server_info["client_mods"]
            self.server_mods = self.server_info["server_mods"]

        except Exception as e:
            print(f"DEBUG - Error: {e}")
            self.server_info = None
            self.name = None
            self.port = None
            self.webhook = None
            self.client_mods = None
            self.server_mods = None



class Server(Config):
    def __init__(self, logs=False):
        self.config_file_name = "dman.toml"
        self.server_list_path = join("~", "dman", "servers")
        self.server_root_path = join(self.server_list_path, self.name)
        self.config_file_path = join(self.server_root_path, self.config_file_name)
        self.be_path = f'-BEpath={self.server_root_path}/battleye/'
        self.profiles_path = f'-profiles={self.server_root_path}/profiles/'
        self.logs = logs

        if logs:
            self.logs = '-dologs -adminlog -netlog'
        
        self.settings = Config(self.config_file_path)


    def default_server_config(self):
        default_config_path = join("~", "dman", "resources", "server_default_config.toml")
        try:
            with open(default_config_path, "r") as default_config:
                return default_config
        except FileNotFoundError:
            print("Default server config not found???")


    def check_server_files(self):
        # Check if the server root path exists
        if path.exists(self.server_root_path) is not True:
            os.makedirs(self.server_root_path)


    def check_config(self):
        # If config file doesn't exist, create it
        self.check_server_files()
        if path.exists(self.config_file_path) is not True:
            with open(self.config_file_path, "w") as f:
                f.write(self.default_server_config())
        
        # Populate server config vars with toml values
        self.settings = Config(self.config_file_path)



class SteamCMD():
    def __init__(
            self, 
            steam_username, 
            dman_config=join("~", "dman", "dman_config.toml")
        ):
        self.steam_login = steam_username
        self.dman_config = dman_config

        self.appid = 223350
        self.dayz_id = 221100
        self.dman_path = join("~", "dman")
        self.server_list_path = join(self.dman_path, "servers")
        self.steamcmd = join(self.dman_path, "steamcmd")


    def check_steamcmd(self):
        # Check if the steamcmd path exists
        if path.exists(self.steamcmd) is not True:
            # os.makedirs(self.steamcmd_path) # no dummy you need to curl the steamcmd source files
            command(f'cd {self.dman_path} && curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -')


    def create_new_server(self, server):
        command(f'{join(self.steamcmd, "steamcmd.sh")} +force_install_dir {join(self.server_list_path, server)} +login {self.steam_login} +app_update 223350 +quit')



class Manager(SteamCMD, Server):
    def __init__(self):
        self.resources_path = join("~", "dman", "resources")
        self.servers = next(os.walk(self.server_list_path))
        # self.servers = [x[0] for x in os.walk(self.server_list_path)]
        print(f"DEBUG - Servers: {self.servers}")


    def default_server_config(self):
        default_config_path = join(self.resources_path, "server_default_config.toml")
        try:
            with open(default_config_path, "r") as default_config:
                return default_config

        except FileNotFoundError:
            print("Default server config not found???")


    def default_dman_config(self):
        default_config_path = join(self.resources_path, "dman_default_config.toml")
        try:
            with open(default_config_path, "r") as default_config:
                return default_config

        except FileNotFoundError:
            print("Default server config not found???")


    def check_dman_config(self):
        # Check if the dman config exists
        if path.exists(self.dman_config):
            return
        
        os.makedirs(self.dman_path)
        with open(self.dman_config, "w") as f:
            f.write(self.default_dman_config())


    def start_server(self, server_name):
        server = Server
        server_script = join(SteamCMD.server_list_path, server_name)
        config = f'-config={join(SteamCMD.server_list_path, "serverDZ.cfg")}'

        process = command(f'{server_script} {config} {server.port} {server.be_path} {server.profiles_path} {server.logs} -freezecheck')


    def stop_server(self, server):
        pass # TODO kick all players, wait 3m, stop server



def main():
    dman = Manager
    dman.check_dman_config()

    server_list = dman.servers

    if server_list:
        print("Servers:")
        for server in server_list:
            print(f"\t- {server}\n")

    else:
        print(f"No servers in {dman.server_list_path}")
        # TODO allow deploy new server instance with default values
    
    print(
        """Options:"""
        """\n\tu - Start server (Up)"""
        """\n\td - Stop server (Down)"""
    )

    while True:
        k = cv2.waitKey(1) & 0xFF
            # press 'q' to exit
        if k == ord('q'):
            break
        elif k == ord('b'):
            # change a variable / do something ...
            pass
        elif k == ord('k'):
            # change a variable / do something ...
            pass



# main()