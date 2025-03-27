import logging
import os
import subprocess
import time
import threading
import re
import shutil
import json

from modules.format import print_center

from shutil import copytree, ignore_patterns
from subprocess import check_output
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

log = logging.getLogger(__name__)

console = Console()


def get_console_size():
    console_size = check_output(["stty", "size"]).decode("utf-8").split()
    h = int(console_size[0])
    w = int(console_size[1])

    return w, h


def check_steamcmd(app_path, username, password):
    link = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
    log.info("checking for steamcmd...")
    steamcmd = os.path.join(app_path, "steamcmd")

    # Get terminal width
    w, h = get_console_size()
    terminal_width = w

    # Calculate bar width based on terminal width
    # Subtract space for other columns (spinner, text, percentage, time)
    bar_width = terminal_width - 50  # Adjust this value as needed

    if not os.path.isdir(steamcmd):
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=bar_width),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,  # Ensure the progress bar expands to fill available space
        ) as progress:
            log.info("SteamCMD not found, installing...")
            os.makedirs(steamcmd, exist_ok=True)

            # Create a task for the SteamCMD download
            download_task = progress.add_task(
                "[green]Downloading SteamCMD...", total=100
            )

            # Download and extract SteamCMD
            download_cmd = f'cd {steamcmd} && curl -sqL "{link}" | tar zxvf -'

            # Create a flag to track if the process is still running
            process_running = True

            # Use Popen to get real-time output
            process = subprocess.Popen(
                download_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Function to gradually update progress
            def update_download_progress():
                step = 0
                while process_running and step < 99:
                    if process.poll() is not None:  # Process finished
                        break
                    time.sleep(0.1)
                    step = min(step + 1, 99)  # Cap at 99%
                    progress.update(download_task, completed=step)

            # Start progress updater in a thread
            progress_thread = threading.Thread(
                target=update_download_progress, daemon=True
            )
            progress_thread.start()

            # Wait for process to complete
            stdout, stderr = process.communicate()

            # Process is no longer running
            process_running = False

            # Wait for the thread to pick up the change
            time.sleep(0.2)

            # Ensure progress is at 100%
            progress.update(
                download_task,
                completed=100,
                description="[green]SteamCMD download complete",
            )

            # Log output to file
            if stdout:
                for line in stdout.splitlines():
                    log.debug(f"SteamCMD download output: {line}")

            if stderr:
                for line in stderr.splitlines():
                    log.error(f"SteamCMD download error: {line}")

            if process.returncode != 0:
                log.error(
                    f"Failed to download SteamCMD with return code: {process.returncode}"
                )
                raise RuntimeError("SteamCMD download failed")

            # Verify steamcmd.sh exists
            steamcmd_sh = os.path.join(steamcmd, "steamcmd.sh")
            if not os.path.exists(steamcmd_sh):
                log.error(f"steamcmd.sh not found at {steamcmd_sh} after extraction")
                raise FileNotFoundError(f"steamcmd.sh not found at {steamcmd_sh}")

        # print("Done")

    steamcmd = os.path.join(app_path, "steamcmd")
    server_template = os.path.join(steamcmd, "server_template")
    if (
        os.path.isdir(server_template) is not True
        or len(os.listdir(server_template)) == 0
    ):
        # print("Initializing server template...", end="", flush=True)
        log.info("checking for server_template...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=bar_width),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,  # Ensure the progress bar expands to fill available space
        ) as progress:
            log.info(
                "Server template not found, installing (this will take a while)..."
            )
            # os.makedirs(server_template, exist_ok=True)

            steamcmd_sh = os.path.join(steamcmd, "steamcmd.sh")
            if not os.path.exists(steamcmd_sh):
                log.error(f"steamcmd.sh not found at {steamcmd_sh}")
                raise FileNotFoundError(f"steamcmd.sh not found at {steamcmd_sh}")

            # Create a task for the server template installation
            template_task = progress.add_task(
                "[yellow]Downloading server template (takes a while)...",
                total=100,
            )

            # Process running flag
            process_running = True

            # Run steamcmd with correct arguments using Popen for real-time output
            process = subprocess.Popen(
                [
                    steamcmd_sh,
                    f"+force_install_dir {server_template}",
                    f"+login {username} {password}",
                    "+app_update 223350",
                    "+quit",
                ],
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Regex to extract progress percentage from SteamCMD output
            progress_pattern = re.compile(r"Update state \(0x\d+\) (\d+)%.*")

            # Current progress percentage
            current_progress = 0

            # Function to parse output and update progress
            def update_template_progress():
                nonlocal current_progress
                for line in iter(process.stdout.readline, ""):
                    if not process_running:
                        break

                    match = progress_pattern.search(line)
                    if match:
                        percent = int(match.group(1))
                        current_progress = percent
                        progress.update(template_task, completed=percent)
                    log.debug(f"SteamCMD install output: {line.strip()}")

                # Process stderr
                for line in iter(process.stderr.readline, ""):
                    if not process_running:
                        break
                    log.error(f"SteamCMD install error: {line.strip()}")

            # Start progress updater in a thread
            progress_thread = threading.Thread(
                target=update_template_progress, daemon=True
            )
            progress_thread.start()

            # Wait for process to complete
            process.wait()

            # Mark process as completed
            process_running = False

            # Small delay to let the thread catch up
            time.sleep(0.2)

            # Ensure progress is at 100%
            progress.update(
                template_task,
                completed=100,
                description="[yellow]Server template installation complete",
            )

            if process.returncode != 0:
                log.error(
                    f"Failed to install server template with return code: {process.returncode}"
                )
                raise RuntimeError("Server template installation failed")
            # print("Done")

            # install necessary default battleye rcon cfg
            with open(
                os.path.join(server_template, "battleye", "BEServer_x64.cfg"), "w"
            ) as cfg:
                cfg_contents = "RConPassword RCON_PASSWORD\n"
                cfg_contents += "RestrictRCon 0\n"
                cfg_contents += "RConPort 2303"
                cfg.write(cfg_contents)

    log.info("steamcmd setup complete")


def update_servers(app_path, username, password):
    steamcmd = os.path.join(app_path, "steamcmd")
    # console = Console()

    # print(servers)

    # Get terminal width
    w, h = get_console_size()
    terminal_width = w

    # Calculate bar width based on terminal width
    # Subtract space for other columns (spinner, text, percentage, time)
    bar_width = terminal_width - 50  # Adjust this value as needed

    # for server in servers:
    server_template_path = os.path.join(app_path, "steamcmd", "server_template")
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=bar_width),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        expand=True,  # Ensure the progress bar expands to fill available space
    ) as progress:
        log.info("Server template not found, installing (this will take a while)...")
        # os.makedirs(server_template, exist_ok=True)

        steamcmd_sh = os.path.join(steamcmd, "steamcmd.sh")
        if not os.path.exists(steamcmd_sh):
            log.error(f"steamcmd.sh not found at {steamcmd_sh}")
            raise FileNotFoundError(f"steamcmd.sh not found at {steamcmd_sh}")

        # Create a task for the server template installation
        template_task = progress.add_task(
            "[yellow]Updating Servers...",
            total=100,
        )

        # Process running flag
        process_running = True

        # Run steamcmd with correct arguments using Popen for real-time output
        process = subprocess.Popen(
            [
                steamcmd_sh,
                f"+force_install_dir {server_template_path}",
                f"+login {username} {password}",
                "+app_update 223350",
                "+quit",
            ],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Regex to extract progress percentage from SteamCMD output
        progress_pattern = re.compile(r"Update state \(0x\d+\) (\d+)%.*")

        # Current progress percentage
        current_progress = 0

        # Function to parse output and update progress
        def update_template_progress():
            nonlocal current_progress
            for line in iter(process.stdout.readline, ""):
                if not process_running:
                    break

                match = progress_pattern.search(line)
                if match:
                    percent = int(match.group(1))
                    current_progress = percent
                    progress.update(template_task, completed=percent)
                log.debug(f"SteamCMD install output: {line.strip()}")

            # Process stderr
            for line in iter(process.stderr.readline, ""):
                if not process_running:
                    break
                log.error(f"SteamCMD install error: {line.strip()}")

        # Start progress updater in a thread
        progress_thread = threading.Thread(target=update_template_progress, daemon=True)
        progress_thread.start()

        # Wait for process to complete
        process.wait()

        instances = [
            d
            for d in os.listdir(os.path.join(app_path, "servers"))
            if os.path.isdir(os.path.join(app_path, "servers", d))
        ]

        # Mark process as completed
        process_running = False

        # Small delay to let the thread catch up
        time.sleep(0.2)

        for server in instances:
            server_path = os.path.join(app_path, "servers", server)
            if server_path:
                copytree(
                    src=server_template_path,
                    dst=server_path,
                    ignore=ignore_patterns(
                        "*.xml",
                        "*.cfg",
                        "*.json",
                        "*.map",
                        "*.c",
                        "*.db",
                        "*.bin",
                        "*.001",
                        "*.002",
                        "*.txt",
                    ),
                    dirs_exist_ok=True,
                )

        # Ensure progress is at 100%
        progress.update(
            template_task,
            completed=100,
            description="[yellow]Server template installation complete",
        )

        if process.returncode != 0:
            log.error(
                f"Failed to install server template with return code: {process.returncode}"
            )
            raise RuntimeError("Server template installation failed")


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
    # print to CLI UI, center text
    print_center("Validating mods...")

    # print("\nValidating mods...", end="", flush=True)

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
                    log.warning(f"error reading meta.cpp for mod {mod_id}: {e}")

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
            log.warning("could not find Steam workshop content directory")
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
                    username,
                    "+workshop_download_item",
                    "221100",
                    mod_id,
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
                        f"error downloading mod {mod_id}: {process.stderr.decode('utf-8')}"
                    )
                else:
                    log.info(f"successfully downloaded mod {mod_id}")

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
                        log.warning(f"failed to create symlink for mod {mod_id}: {e}")

            except subprocess.TimeoutExpired:
                log.error(f"timeout while downloading mod {mod_id}")
            except Exception as e:
                log.error(f"error processing mod {mod_id}: {e}")
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
                log.warning(f"failed to parse meta.cpp for mod {mod_id}: {e}")

        workshop_mods_by_id[mod_id] = name
        workshop_mods_by_name[name] = mod_id
        known_mod_names[name] = mod_id

    print("Done\n")

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

    # Ensure all file operations are complete
    # Wait for any potential file operations to complete
    time.sleep(3)

    # create updated mod strings
    client_mods = f"@{';@'.join(processed_client)}" if processed_client else ""
    server_mods = f"@{';@'.join(processed_server)}" if processed_server else ""

    log.debug(f"updated client mods: {client_mods}")
    log.debug(f"updated server mods: {server_mods}")

    return client_mods, server_mods


def check_and_update_mods(
    username, password, server_configs, app_path, force_check=False
):
    """
    Check if workshop mods have updates available and download them if needed.

    Args:
        username (str): Steam username
        server_configs (list): List of server configuration dictionaries
        app_path (str): Base application path
        force_check (bool): Force update check even if last check was recent

    Returns:
        dict: Dictionary of updated mods (mod_id -> mod_name)
    """
    log.info("Checking for mod updates...")

    # Path setup
    steamcmd_path = os.path.join(app_path, "steamcmd")
    mod_templates_path = os.path.join(
        steamcmd_path, "steamapps", "workshop", "content", "221100"
    )
    os.makedirs(mod_templates_path, exist_ok=True)

    # Path to store mod update metadata
    update_metadata_path = os.path.join(app_path, "mod_update_metadata.json")

    # Load existing metadata
    update_metadata = {}
    if os.path.exists(update_metadata_path):
        try:
            with open(update_metadata_path, "r") as f:
                update_metadata = json.load(f)
        except Exception as e:
            log.warning(f"Failed to load mod update metadata: {e}")

    # Get current time
    current_time = time.time()

    # Check if we've checked recently (within last 6 hours) and not forcing check
    last_check_time = update_metadata.get("last_check_time", 0)
    if not force_check and current_time - last_check_time < 21600:  # 6 hours in seconds
        log.info(
            f"Skipping mod update check - last check was {(current_time - last_check_time) / 3600:.1f} hours ago"
        )
        return {}

    # Parse mod IDs from configs (same as in validate_workshop_mods)
    all_mod_ids = set()
    all_mod_names = set()
    known_mod_names = {}

    # Dictionary to store mod details
    workshop_mods_by_id = {}

    # First, build mapping from existing mods
    if os.path.exists(mod_templates_path):
        existing_mod_ids = [
            d
            for d in os.listdir(mod_templates_path)
            if os.path.isdir(os.path.join(mod_templates_path, d))
        ]

        # Get names for existing mods
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
            known_mod_names[name] = mod_id

    # Extract mod IDs and names from configs
    for config in server_configs:
        # Process client mods
        client_mods = config["server"]["info"]["client_mods"]
        process_mod_string(client_mods, all_mod_ids, all_mod_names, known_mod_names)

        # Process server mods
        server_mods = config["server"]["info"]["server_mods"]
        process_mod_string(server_mods, all_mod_ids, all_mod_names, known_mod_names)

    # Get current workshop mod details
    workshop_details = update_metadata.get("workshop_details", {})

    # Get Steam API access for update checking
    workshop_details_updated = False
    mods_to_update = set()

    # Get default workshop path
    default_workshop_path = find_steam_workshop_path("221100", app_path)
    if not default_workshop_path:
        default_workshop_path = mod_templates_path

    # Console width for progress bar
    w, h = get_console_size()
    terminal_width = w
    bar_width = terminal_width - 50
    console = Console()

    # Initialize progress bar for update checking
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=bar_width),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        expand=True,
    ) as progress:
        check_task = progress.add_task(
            "[cyan]Checking for mod updates...", total=len(all_mod_ids)
        )

        # Use SteamCMD to query workshop item details for each mod
        for i, mod_id in enumerate(all_mod_ids):
            if not mod_id.isdigit() or len(mod_id) != 10:
                continue

            progress.update(
                check_task, description=f"[cyan]Checking mod {mod_id}...", completed=i
            )
            log.debug(f"checking mod {mod_id}...")

            # Check if mod exists in the workshop directory
            mod_path = os.path.join(mod_templates_path, mod_id)
            if not os.path.exists(mod_path):
                # Mod doesn't exist locally, needs download
                mods_to_update.add(mod_id)
                continue

            # Get last modified time of the mod directory
            try:
                local_mod_time = os.path.getmtime(mod_path)

                # Get saved update details if available
                mod_details = workshop_details.get(mod_id, {})
                stored_update_time = mod_details.get("update_time", 0)

                # Check if we need to query Steam for updates (once per day per mod)
                need_query = (
                    current_time - mod_details.get("last_query_time", 0) > 86400
                )  # 24 hours

                if need_query:
                    # Use steamcmd to query workshop item details
                    try:
                        cmd = [
                            "./steamcmd.sh",
                            "+login",
                            username,
                            password,
                            "+workshop_item_info",
                            "221100",
                            mod_id,
                            "+quit",
                        ]

                        # Run with timeout
                        process = subprocess.run(
                            cmd,
                            shell=False,
                            cwd=steamcmd_path,
                            timeout=60,  # 1 minute timeout per query
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )

                        # Parse the output to find the last updated time
                        update_time = 0
                        for line in process.stdout.splitlines():
                            if (
                                "timetouched" in line.lower()
                                or "time_updated" in line.lower()
                            ):
                                parts = line.split(":", 1)
                                if len(parts) == 2:
                                    try:
                                        update_time = int(parts[1].strip())
                                        break
                                    except ValueError:
                                        pass

                        # Update the metadata
                        if update_time > 0:
                            mod_details["update_time"] = update_time
                            mod_details["last_query_time"] = current_time
                            workshop_details[mod_id] = mod_details
                            workshop_details_updated = True

                            # Check if update is needed
                            if update_time > local_mod_time:
                                log.info(f"Update available for mod {mod_id}")
                                mods_to_update.add(mod_id)

                    except subprocess.TimeoutExpired:
                        log.warning(f"Timeout while querying mod {mod_id}")
                    except Exception as e:
                        log.warning(f"Error querying mod {mod_id}: {e}")

                # Check based on stored update time if query wasn't done
                elif stored_update_time > local_mod_time:
                    log.info(f"Update needed for mod {mod_id} based on stored metadata")
                    mods_to_update.add(mod_id)

            except Exception as e:
                log.warning(f"Error checking mod {mod_id} for updates: {e}")

        # Update progress to complete
        progress.update(
            check_task,
            completed=len(all_mod_ids),
            description="[cyan]Mod update check complete",
        )

    # Update metadata with latest check time
    update_metadata["last_check_time"] = current_time
    update_metadata["workshop_details"] = workshop_details

    # Save the metadata
    try:
        with open(update_metadata_path, "w") as f:
            json.dump(update_metadata, f)
    except Exception as e:
        log.warning(f"Failed to save mod update metadata: {e}")

    # If there are mods to update, download them
    updated_mods = {}
    if mods_to_update:
        log.info(f"Updating {len(mods_to_update)} mods...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold yellow]{task.description}"),
            BarColumn(bar_width=bar_width),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        ) as progress:
            update_task = progress.add_task(
                f"[yellow]Updating {len(mods_to_update)} mods...",
                total=len(mods_to_update),
            )

            # Download each mod that needs updating
            for i, mod_id in enumerate(mods_to_update):
                try:
                    mod_name = workshop_mods_by_id.get(mod_id, mod_id)
                    progress.update(
                        update_task,
                        description=f"[yellow]Updating mod {mod_name} ({mod_id})...",
                        completed=i,
                    )

                    # Create command for workshop download
                    cmd = [
                        "./steamcmd.sh",
                        "+login",
                        username,
                        password,
                        "+workshop_download_item",
                        "221100",
                        mod_id,
                        "+quit",
                    ]

                    # Process running flag for progress tracking
                    process_running = True

                    # Run steamcmd with correct arguments using Popen for real-time output
                    process = subprocess.Popen(
                        cmd,
                        shell=False,
                        cwd=steamcmd_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        universal_newlines=True,
                    )

                    # Regex to extract progress percentage from SteamCMD output
                    progress_pattern = re.compile(r"Update state \(0x\d+\) (\d+)%.*")

                    # Current progress percentage
                    current_progress = 0
                    download_sub_task = progress.add_task(
                        f"[green]Downloading {mod_name}...", total=100
                    )

                    # Function to parse output and update progress
                    def update_download_progress():
                        nonlocal current_progress
                        for line in iter(process.stdout.readline, ""):
                            if not process_running:
                                break

                            match = progress_pattern.search(line)
                            if match:
                                percent = int(match.group(1))
                                current_progress = percent
                                progress.update(download_sub_task, completed=percent)
                            log.debug(f"SteamCMD download output: {line.strip()}")

                        # Process stderr
                        for line in iter(process.stderr.readline, ""):
                            if not process_running:
                                break
                            log.error(f"SteamCMD download error: {line.strip()}")

                    # Start progress updater in a thread
                    progress_thread = threading.Thread(
                        target=update_download_progress, daemon=True
                    )
                    progress_thread.start()

                    # Wait for process to complete
                    process.wait()

                    # Mark process as completed
                    process_running = False

                    # Small delay to let the thread catch up
                    time.sleep(0.2)

                    # Ensure progress is at 100%
                    progress.update(
                        download_sub_task,
                        completed=100,
                        description=f"[green]Download complete: {mod_name}",
                    )

                    if process.returncode != 0:
                        log.error(
                            f"Failed to download mod {mod_id} with return code: {process.returncode}"
                        )
                    else:
                        log.info(f"Successfully updated mod {mod_id}")

                        # create symlink for the downloaded mod if needed
                        default_mod_path = os.path.join(default_workshop_path, mod_id)
                        target_mod_path = os.path.join(mod_templates_path, mod_id)

                        if (
                            os.path.exists(default_mod_path)
                            and default_mod_path != target_mod_path
                        ):
                            # Remove existing symlink if it exists
                            if os.path.exists(target_mod_path):
                                if os.path.islink(target_mod_path):
                                    os.unlink(target_mod_path)
                                else:
                                    shutil.rmtree(target_mod_path)

                            try:
                                os.symlink(default_mod_path, target_mod_path)
                                log.info(
                                    f"Created symlink for mod {mod_id} from {default_mod_path} to {target_mod_path}"
                                )
                            except Exception as e:
                                log.warning(
                                    f"Failed to create symlink for mod {mod_id}: {e}"
                                )

                        # Read updated mod name from meta.cpp
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
                                log.warning(
                                    f"Error reading meta.cpp for mod {mod_id}: {e}"
                                )

                        # Store the updated mod
                        workshop_mods_by_id[mod_id] = name
                        updated_mods[mod_id] = name

                except subprocess.TimeoutExpired:
                    log.error(f"Timeout while updating mod {mod_id}")
                except Exception as e:
                    log.error(f"Error updating mod {mod_id}: {e}")

                # Remove the download subtask
                progress.remove_task(download_sub_task)

            # Update progress to complete
            progress.update(
                update_task,
                completed=len(mods_to_update),
                description="[yellow]Mod updates complete",
            )

    else:
        log.info("All mods are up to date")

    # If any mods were updated, we need to update the servers
    if updated_mods:
        # Handle server side updates here or call other functions as needed
        log.info(f"Updated {len(updated_mods)} mods: {list(updated_mods.values())}")

        # You might want to copy the updated mods to server directories here
        # or call your existing import_mods function for each server instance

    return updated_mods
