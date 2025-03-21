import logging
import os
import subprocess
import time
import threading
import re

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

    console = Console()

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

        log.info("checking for server_template...")
        server_template = os.path.join(steamcmd, "server_template")

        if (
            os.path.isdir(server_template) is not True
            or len(os.listdir(server_template)) == 0
        ):
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
                "[yellow]Downloading server template...", total=100
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

    log.info("steamcmd setup complete")
