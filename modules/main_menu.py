from os import system, name
from subprocess import check_output
from rich.console import Console
from rich.table import Table
from rich.panel import Panel


def cls():
    system("cls" if name == "nt" else "clear")


def get_console_size():
    # gather raw output from console
    # console_width = check_output(["stty", "size"], stdout=PIPE)
    # format raw data into int
    # console_width = int(console_width.communicate().decode())

    console_size = check_output(["stty", "size"]).decode("utf-8").split()
    h = int(console_size[0])
    w = int(console_size[1])

    return w, h


#     print(rf"""┏{"━" * (w - 2)}┓
# ┃{logo_whitespace}██████╗ ███╗   ███╗ █████╗ ███╗   ██╗{logo_whitespace} ┃
# ┃{logo_whitespace}██╔══██╗████╗ ████║██╔══██╗████╗  ██║{logo_whitespace} ┃
# ┃{logo_whitespace}██║  ██║██╔████╔██║███████║██╔██╗ ██║{logo_whitespace} ┃
# ┃{logo_whitespace}██║  ██║██║╚██╔╝██║██╔══██║██║╚██╗██║{logo_whitespace} ┃
# ┃{logo_whitespace}██████╔╝██║ ╚═╝ ██║██║  ██║██║ ╚████║{logo_whitespace} ┃
# ┃{logo_whitespace}╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝{logo_whitespace} ┃
# ┗{"━" * (w - 2)}┛""")


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
{"█" * logo_whitespace}██████████████████████████████████{"█" * logo_whitespace}
"""
    console = Console(width=w)
    cls()
    console.print(logo)


def main_menu(server_states):
    title_screen()

    # Get console size
    w, h = get_console_size()

    # Create console with the width of the terminal
    console = Console(width=w)

    # Create a table that will fill the console width
    table = Table(
        title="Server Instances",
        show_header=True,
        header_style="bold cyan",
        expand=True,
        width=w,
    )

    # Calculate relative column widths based on console width
    server_width = int(w * 0.25)  # 25% of width
    state_width = int(w * 0.15)  # 15% of width
    players_width = int(w * 0.15)  # 15% of width
    pid_width = int(w * 0.2)  # 20% of width
    port_width = int(w * 0.15)  # 15% of width

    # Add columns with specified widths
    table.add_column("Server", style="dim", width=server_width, no_wrap=True)
    table.add_column("State", style="", width=state_width, no_wrap=True)
    table.add_column("Players", justify="right", width=players_width, no_wrap=True)
    table.add_column("PID", justify="right", width=pid_width, no_wrap=True)
    table.add_column("Port", justify="right", width=port_width, no_wrap=True)

    # Add rows
    for server, data in list(server_states.items()):
        pid = data["pid"]
        port = data["port"]
        players = data["players"]
        state = data["state"]

        # Conditional styling based on state
        state_text = str(state).replace("ServerState.", "")
        state_style = "green" if state_text == "RUNNING" else "red"

        table.add_row(
            server,
            f"[{state_style}]{state_text}[/{state_style}]",
            str(players),
            str(pid),
            str(port),
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
