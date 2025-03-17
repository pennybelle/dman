from subprocess import check_output


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


logo_width = 33
border_width = 1
logo_whitespace = (w // 2 - (logo_width // 2)) - (border_width * 2)


logo = rf"""
█{"█" * logo_whitespace}██████████████████████████████████{"█" * logo_whitespace}█
█{"█" * logo_whitespace}████  ████████████████████████████{"█" * logo_whitespace}█
█{"█" * logo_whitespace}████  ████████████████████████████{"█" * logo_whitespace}█
█{"█" * logo_whitespace}████  ████████████████████████████{"█" * logo_whitespace}█
█{"█" * logo_whitespace}████  ███  █  █ █████   ████  █ ██{"█" * logo_whitespace}█
█{"█" * logo_whitespace}██    ███        ███  █  ███     █{"█" * logo_whitespace}█
█{"█" * logo_whitespace}█  █  ███  █  █  ██████  ███  █  █{"█" * logo_whitespace}█
█{"█" * logo_whitespace}█  █  ███  █  █  ████    ███  █  █{"█" * logo_whitespace}█
█{"█" * logo_whitespace}█  █  ███  █  █  ███  █  ███  █  █{"█" * logo_whitespace}█
█{"█" * logo_whitespace}██    ███  █  █  ████    ███  █  █{"█" * logo_whitespace}█
█{"█" * logo_whitespace}██████████████████████████████████{"█" * logo_whitespace}█
"""


def title_screen():
    print(logo)


#     print(rf"""┏{"━" * (w - 2)}┓
# ┃{logo_whitespace}██████╗ ███╗   ███╗ █████╗ ███╗   ██╗{logo_whitespace} ┃
# ┃{logo_whitespace}██╔══██╗████╗ ████║██╔══██╗████╗  ██║{logo_whitespace} ┃
# ┃{logo_whitespace}██║  ██║██╔████╔██║███████║██╔██╗ ██║{logo_whitespace} ┃
# ┃{logo_whitespace}██║  ██║██║╚██╔╝██║██╔══██║██║╚██╗██║{logo_whitespace} ┃
# ┃{logo_whitespace}██████╔╝██║ ╚═╝ ██║██║  ██║██║ ╚████║{logo_whitespace} ┃
# ┃{logo_whitespace}╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝{logo_whitespace} ┃
# ┗{"━" * (w - 2)}┛""")


# title_screen()


def main_menu():
    pass
