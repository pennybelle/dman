from os import system, name
from subprocess import check_output


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


w, h = get_console_size()
# print(w, h)


logo_width = len("██████████████████████████████████") - 1
border_width = 1
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


def title_screen():
    cls()
    print(logo)


# title_screen()


#     print(rf"""┏{"━" * (w - 2)}┓
# ┃{logo_whitespace}██████╗ ███╗   ███╗ █████╗ ███╗   ██╗{logo_whitespace} ┃
# ┃{logo_whitespace}██╔══██╗████╗ ████║██╔══██╗████╗  ██║{logo_whitespace} ┃
# ┃{logo_whitespace}██║  ██║██╔████╔██║███████║██╔██╗ ██║{logo_whitespace} ┃
# ┃{logo_whitespace}██║  ██║██║╚██╔╝██║██╔══██║██║╚██╗██║{logo_whitespace} ┃
# ┃{logo_whitespace}██████╔╝██║ ╚═╝ ██║██║  ██║██║ ╚████║{logo_whitespace} ┃
# ┃{logo_whitespace}╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝{logo_whitespace} ┃
# ┗{"━" * (w - 2)}┛""")


def main_menu(running_servers, stopped_servers):
    title_screen()
    if running_servers:
        print("Servers running:")
        for server in running_servers:
            print(f" - {server}")

    else:
        print("No active instances, enable them in dman.toml :3")

    if stopped_servers:
        print("Servers stopped:")
        for server in stopped_servers:
            print(f" - {server}")
