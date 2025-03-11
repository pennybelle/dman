# Inspired by haywardgg's DayZ_Server_Manager
# https://github.com/haywardgg/DayZ_Server_Manager

import os, toml

from os import path
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


class Dman_Config:
    def __init__(self):
        try:
            # pull server specific details from config file
            server_configs = toml.load(path.join(".", "dman.toml"))

            self.dman_info = server_configs["dman"]
            self.name = self.dman_info["config_name"]
            self.dman_path = self.dman_info["dman_location"]
            self.steamcmd_path = self.dman_info["steamcmd_path"]

            self.user_info = server_configs["user"]
            self.steam_username = self.dman_info["steam_username"]
            self.servers_path = self.dman_info["servers_path"]

        except Exception as e:
            print(f"DEBUG - Error: {e}")
            self.name = None
            self.dman_path = None
            self.steam_username = None
            self.servers_path = None



class Server_Config:
    def __init__(self, server_path):
        try:
            # pull server specific details from config file
            server_configs = toml.load(server_path)

            self.server_info = server_configs["server"]["info"]
            self.name = self.server_info["name"]
            self.port = self.server_info["port"]
            self.webhook = self.server_info["discord_webhook"]
            self.client_mods = self.server_info["client_mods"]
            self.server_mods = self.server_info["server_mods"]
            self.logs = self.server_info["logs"]

        except Exception as e:
            print(f"DEBUG - Error: {e}")
            self.server_info = None
            self.name = None
            self.port = None
            self.webhook = None
            self.client_mods = None
            self.server_mods = None
            self.logs = None



class Server(Server_Config):
    def __init__(self, server_path, name, logs=False):
        super().__init__(self, server_path, name)
        # paths used in launch script (organized for my own convenience)
        self.config_file_name = Dman_Config.name # default "dman.toml"
        self.server_root_path = path.join(Dman_Config.servers_path, self.name)
        self.config_file_path = path.join(self.server_root_path, self.config_file_name)

        # args for launch script, hardcoded since these directories shouldnt change
        self.be_path = f'-BEpath={self.server_root_path}/battleye/'
        self.profiles_path = f'-profiles={self.server_root_path}/profiles/'

        # logs are off by default
        if self.logs:
            self.logs = "-dologs -adminlog -netlog"
        
        # init server settings using dman.toml inside server root
        self.configs = Server_Config(self.config_file_path)
        self.name = self.configs.name
        self.port = self.configs.port
        self.discord_webhook = self.configs.webhook
        self.client_mods = self.configs.client_mods
        self.server_mods = self.configs.server_mods
        self.logs = self.configs.logs


    def default_config(self):
        default_config_path = path.join(Dman_Config.dman_path, "resources", "server_default_config.toml")
        try:
            with open(default_config_path, "r") as default_config:
                return default_config.read()

        except FileNotFoundError:
            print("Default server config not found???")


    def config(self):
        # Check if the dman config exists
        if path.exists(self.config_file_path) is not True:
            print(f"No config found for {self.name}, creating...", end="", flush=True)
            # os.makedirs(self.server_root_path)
            with open(self.config_file_path, "w") as f:
                f.write(self.default_config())
            print("Done")

        # Populate server config vars with toml values
        self.configs = Server_Config(self.config_file_path)


    # def default_server_config(self):
    #     default_config_path = path.join(Dman_Config.dman_path, "resources", "server_default_config.toml")
    #     try:
    #         with open(default_config_path, "r") as default_config:
    #             return default_config
    #     except FileNotFoundError:
    #         print("Default server config not found???")


    def verify_integrity(self):
        # Check if the server root path exists
        if path.exists(self.server_root_path) is not True:
            print("Server root path doesn't exist, creating...", end="", flush=True)
            os.makedirs(self.server_root_path)
            print("Done")


    # def config(self):
    #     # If config file doesn't exist, create it
    #     self.verify_integrity()
    #     if path.exists(self.config_file_path) is not True:
    #         with open(self.config_file_path, "w") as f:
    #             f.write(self.default_config())
        
    #     # Populate server config vars with toml values
    #     self.configs = Server_Config(self.config_file_path)


    def start(self, server_name):
        server = Server
        server_script = path.join(self.servers_list, server_name)
        config = f'-config={path.join(self.servers_list, "serverDZ.cfg")}'

        process = command(f'{server_script} {config} {server.port} {server.be_path} {server.profiles_path} {server.logs} -freezecheck')


    def stop(self, server):
        pass # TODO kick all players, wait 3m, stop server



class SteamCMD(Dman_Config):
    def __init__(self):
        self.appid = 223350
        self.dayz_id = 221100

        self.steam_login = Dman_Config.steam_username
        self.dman_path = Dman_Config.dman_path
        self.steamcmd_path = Dman_Config.steamcmd_path
        self.dman_config = path.join(self.dman_path, Dman_Config.name)
        self.server_list_path = Dman_Config.servers_path


    def check_steamcmd(self):
        # Check if the steamcmd path exists
        if path.exists(self.steamcmd_path) is not True:
            # os.makedirs(self.steamcmd_path) # no dummy you need to curl the steamcmd source files
            command(f'cd {self.steamcmd_path} && curl -sqL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" | tar zxvf -')


    def download_server(self, server):
        command(f'{path.join(self.steamcmd_path, "steamcmd.sh")} +force_install_dir {path.join(self.server_list_path, server)} +login {self.steam_login} +app_update 223350 +quit')



class Manager(SteamCMD, Dman_Config):
    def __init__(self, name, dman_path, server_list_path):
        super().__init__(self, name, dman_path, server_list_path)
        self.config_file_name = Dman_Config.name # default "dman.toml"
        self.dman_path = Dman_Config.dman_path
        self.config_file_path = path.join(self.dman_path, self.config_file_name)

        self.resources_path = path.join(self.dman_path, "resources")
        self.servers_list = next(os.walk(SteamCMD.server_list_path))
        self.servers_dict = {id:server for (id, server) in enumerate(self.servers_list)}
        # self.servers = [x[0] for x in os.walk(self.server_list_path)]
        print(f"DEBUG - Servers: {self.servers}")


    def default_config(self):
        default_config_path = path.join(self.resources_path, "dman_default_config.toml")
        try:
            with open(default_config_path, "r") as f:
                return f.read()

        except FileNotFoundError:
            print("Default server config not found???")


    def config(self):
        # Check if the dman config exists
        if path.exists(self.config_file_path) is not True:
            print("No config found for dman, creating...", end="", flush=True)
            # os.makedirs(self.server_root_path)
            with open(self.config_file_path, "w") as f:
                f.write(self.default_config())
            print("Done")
        
        with open(self.config_file_path, "r") as f:
            return f.read()



def main():
    # init manager to variable
    dman = Manager(SteamCMD, Dman_Config)
    # steamcmd = SteamCMD

    # creat config if it doesnt exist, return contents if it does
    # configs = steamcmd.dman_config()


    if not dman.servers_dict:
        print(f"No servers in {dman.server_list_path}")
        default_server_name = "default_server"
        print(f"Downloading new server to {dman.server_list_path}")
        dman.download_server(default_server_name) # provide server name desired
        # TODO allow deploy new server instance with default values
        dman.servers_list.append(default_server_name)

    print("Servers:")
    for id, name in dman.servers_dict.items():
        print(f"\t{id} - {name}")

    print("Starting servers")
    for id, name in dman.servers_dict.items():
        print(f"Starting server #{id} - {name}")

        try:
            Server.start(name)
        except Exception as e:
            print(f"Error - {e}")

        print(f"Server #{id} ({name}) is running!")

    # print(
    #     """Options:"""
    #     """\n\tu - Start server (Up)"""
    #     """\n\td - Stop server (Down)"""
    # )

    # while True:
    #     k = cv2.waitKey(1) & 0xFF
    #         # press 'q' to exit
    #     if k == ord('q'):
    #         break
    #     elif k == ord('b'):
    #         # change a variable / do something ...
    #         pass
    #     elif k == ord('k'):
    #         # change a variable / do something ...
    #         pass

main()