import logging

from os import system, name
from subprocess import check_output
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.box import SIMPLE


log = logging.getLogger(__name__)


def get_console_size():
    # gather raw output from console
    # console_width = check_output(["stty", "size"], stdout=PIPE)
    # format raw data into int
    # console_width = int(console_width.communicate().decode())

    console_size = check_output(["stty", "size"]).decode("utf-8").split()
    h = int(console_size[0])
    w = int(console_size[1])

    return w, h


def title_screen():
    w, h = get_console_size()
    logo_width = len("██████████████████████████████████") - 1
    # border_width = 1
    logo_whitespace = (w // 2 - (logo_width // 2)) - 1
    logo = rf"""{"█" * logo_whitespace}██████████████████████████████████{"█" * logo_whitespace}
{"█" * logo_whitespace}████  ████████████████████████████{"█" * logo_whitespace}
{"█" * logo_whitespace}████  ████████████████████████████{"█" * logo_whitespace}
{"█" * logo_whitespace}████  ████████████████████████████{"█" * logo_whitespace}
{"█" * logo_whitespace}████  ███  █  █ █████   ████  █ ██{"█" * logo_whitespace}
{"█" * logo_whitespace}██    ███        ███  █  ███     █{"█" * logo_whitespace}
{"█" * logo_whitespace}█  █  ███  █  █  ██████  ███  █  █{"█" * logo_whitespace}
{"█" * logo_whitespace}█  █  ███  █  █  ████    ███  █  █{"█" * logo_whitespace}
{"█" * logo_whitespace}█  █  ███  █  █  ███  █  ███  █  █{"█" * logo_whitespace}
{"█" * logo_whitespace}██    ███  █  █  ████    ███  █  █{"█" * logo_whitespace}
{"█" * logo_whitespace}██████████████████████████████████{"█" * logo_whitespace}
{"█" * logo_whitespace}█                                █{"█" * logo_whitespace}
{"█" * logo_whitespace}█    open source dayz manager    █{"█" * logo_whitespace}
{"█" * logo_whitespace}█                                █{"█" * logo_whitespace}
{"█" * logo_whitespace}██████████████████████████████████{"█" * logo_whitespace}"""
    console = Console(width=w)
    system("cls" if name == "nt" else "clear")
    console.print(logo)

    return console, w


def main_menu(server_states):
    console, w = title_screen()

    # Create a table that will fill the console width
    table = Table(
        # title="Server Instances",
        show_header=True,
        header_style="white bold",
        expand=True,
        width=w,
        box=SIMPLE,
    )

    # Calculate relative column widths based on console width
    server_width = int(w * 0.30)  # 30% of width
    state_width = int(w * 0.20)  # 15% of width
    players_width = int(w * 0.10)  # 15% of width
    pid_width = int(w * 0.15)  # 15% of width
    port_width = int(w * 0.15)  # 15% of width

    # Add columns with specified widths
    table.add_column("Server", style="", width=server_width, no_wrap=True)
    table.add_column(
        "PID", style="white", justify="right", width=pid_width, no_wrap=True
    )
    table.add_column(
        "Port", style="rgb(90,205,255)", justify="right", width=port_width, no_wrap=True
    )
    table.add_column(
        "Players",
        style="rgb(90,205,255)",
        justify="right",
        width=players_width,
        no_wrap=True,
    )
    table.add_column(
        "State", style="", justify="right", width=state_width, no_wrap=True
    )

    # Add rows
    for server, data in list(server_states.items()):
        pid = data["pid"]
        port = data["port"]
        players = data["players"]
        state = data["state"]

        # Conditional styling based on state
        state_text = str(state).replace("ServerState.", "")
        if state_text == "STARTING":
            state_style = "yellow"
            server_style = "rgb(255,161,229)"
        elif state_text == "RUNNING":
            state_style = "green"
            server_style = "rgb(255,161,229)"
        elif state_text == "STOPPED":
            state_style = "rgb(176,176,176)"
            server_style = "rgb(176,176,176)"
        elif state_text == "WARNING":
            server_style = "rgb(255,161,229)"
            state_style = "red"
        elif state_text == "ERROR":
            state_style = "red"
            server_style = "rgb(255,161,229)"
        elif state_text == "CRASHED":
            state_style = "red"
            server_style = "rgb(176,176,176)"
        else:
            state_style = "rgb(176,176,176)"
            server_style = "rgb(176,176,176)"

        table.add_row(
            f"[{server_style}]{server}[/{server_style}]",
            str(pid),
            str(port),
            str(players),
            f"[{state_style}]{state_text}[/{state_style}]",
        )

    # Print the table
    console.print(table)

    # Optional: Add a message if no servers are present
    if not server_states:
        console.print(
            Panel(
                "No active instances, enable them in dman.toml :3",
                style="yellow",
                expand=False,
                width=w,
            )
        )
