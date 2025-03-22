from subprocess import check_output


def get_console_size():
    console_size = check_output(["stty", "size"]).decode("utf-8").split()
    h = int(console_size[0])
    w = int(console_size[1])

    return w, h


def print_center(text, beginning="\n", end=""):
    whitespace = (get_console_size()[0] // 2 - ((len(text) - 1) // 2)) - 1
    print(f"{beginning}{' ' * whitespace}{text}", end=end, flush=True)
