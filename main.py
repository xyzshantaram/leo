#!/usr/bin/env python

import socket
import ssl
import sys
import re
import os
import getpass

# TODO error handling
# TODO split into files

global GEMINI_PORT
GEMINI_PORT = 1965

global WRAP_TEXT
WRAP_TEXT = False

global WRAP_MARGIN
WRAP_MARGIN = 3

global PROMPT_MSG
PROMPT_MSG = "<Press Enter to continue>"

def getch():
    import termios
    import sys, tty
    def _getch():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch
    return _getch()

state = {
    "current_hname": "",
    "current_url": "",
    "sock": None,
    "ssock": None,
    "context": ssl.create_default_context(),
    "logger": print,
    "debug_logger": None,
    "render_body": [],
    "current_links": []
}

hlt = {
    "bold": "\033[1m",
    "underline": "\033[4m",
    "error_color": "\033[38;5;1m",
    "info_color": "\033[38;5;3m",
    "header_color": "\033[38;5;119m",
    "link_color": "\033[38;5;13m",
    "reset": "\033[0m",
    "italic": "\033[3m",
    "unfocus_color": "\033[38;5;8m",
    "set_title": "\033]0;%s\a"
}

hlt_vals = list(hlt.values())

def log(*argv):
    log_debug(*argv)
    if (state["logger"]):
        state["logger"](*argv)

def log_info(*argv):
    if (state["logger"]):
        state["logger"](hlt["bold"] + hlt["info_color"], end='')
        state["logger"](*argv)
        state["logger"](hlt["reset"], end='')

def log_error(*argv):
    log_debug(*argv)
    if (state["logger"]):
        state["logger"](hlt["bold"] + hlt["error_color"], end='')
        state["logger"](*argv)
        state["logger"](hlt["reset"], end='')

def log_debug(*argv):
    if (state["debug_logger"]):
        state["debug_logger"](*argv)

def set_term_title(s):
    print(hlt["set_title"]%s, end='')

def validate_url(url, echo = False):
    rval = None
    if (re.match(r"(((http([s])?:\/\/)|(gemini:\/\/)|(gopher:\/\/))?[a-zA-Z0-9\-]+\.[a-zA-Z0-9])?\/?[^\/\t\n\ \r]+(\/?[^\/\/\n\ \r\t]+)*\/?", url)):
        if ("gemini://" not in url):
            if (url.startswith("http") or url.startswith("https")):
                if echo:
                    log_error("HTTP(s) is unsupported.")
                rval = state["current_url"]
            elif (re.match(r"[a-zA-Z0-9\-]+\.[a-zA-Z].*", url) and not url.endswith(".gmi")):
                rval = "gemini://" + url + "/"
            else:
                if url.startswith("/"):
                    url = validate_url(state["current_hname"] + url)
                    rval = url
        else:
            rval = url
    else:
        if (url == "/"):
            return validate_url(state["current_hname"])
    if (rval):
        p, *u = rval.split("://")
        return p + "://" + "".join(u).replace("//", "/")
    else:
        return None

def get_hostname(url):
    ret = re.findall(
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]", url)[0]
    if not (ret.endswith("/")):
        return ret
    else:
        return ret[:len(ret) - 1]


def get_encoded(s):
    return ((s + "\r\n").encode("UTF-8"))

def gemini_get_document(url, port = GEMINI_PORT):
    state["current_url"] = url
    log_info("attempting to get", url)

    hostname = get_hostname(url)
    state["sock"] = socket.create_connection((hostname, port))
    state["ssock"] = state["context"].wrap_socket(
        state["sock"], server_hostname=hostname
    )
    log_info("Connected to", hostname, "over", state["ssock"].version())
    state["current_hname"] = hostname
    set_term_title(state["current_hname"])

    state["ssock"].sendall(get_encoded(url))

    fp = state["ssock"].makefile("rb")
    header = fp.readline()
    header = header.decode("UTF-8").strip().split()
    log_info(header)
    status = header[0]
    meta = " ".join(header[1:])
    response_body = fp.read()
    if (response_body):
        response_body = response_body.decode("UTF-8").split("\n")
    fp.close()
    return {
        "status": status,
        "meta": meta,
        "body": response_body
    }

def get_document_ez(url):
    resp = gemini_get_document(url, GEMINI_PORT)
    log_info("GET", url, "returned code", resp["status"])
    log_info("MIME type of body was", resp["meta"]) if resp["status"] == "20" else ""
    return resp

def get_link_from_line(line):
    link_parts = line.strip().split()
    link_parts = link_parts[1:]
    if (link_parts[0]):
        if (len(link_parts) == 1):
            link_parts.append(link_parts[0])
        return {
            "url": validate_url(link_parts[0]),
            "text": " ".join(link_parts[1:]),
            "render_line": hlt["bold"] # print links in bold, underlined, 
                + hlt["underline"] + hlt["link_color"]
                + str(len(state["current_links"]))
                + hlt["reset"] + " "
                + " ".join(link_parts[1:])
        }

def slice_line(line, length):
    sliced = [line[i:i + length] for i in range(0, len(line), length)]
    return sliced

def fmt(line, width):
    final = []
    copy = line
    words = []
    length = 0
    copy = copy.split(' ')
    for i in copy:
        hl_len = 0
        for j in hlt:
            if hlt[j] in i:
                hl_len += len(hlt[j])
        length -= hl_len
        if length + len(i) + 1 <= width + hl_len:
            words.append(i)
            length += len(i) + 1
        else:
            final.append(" ".join(words))
            words = [i]
            length = len(i)
    final.append(" ".join(words))
    print("\n".join(final))

def render(file):
    cols, rows = os.get_terminal_size()
    state["render_body"] = []
    in_pf_block = False
    for line in file:
        if (line.startswith("```")):
            line = line.strip()
            line = hlt["italic"] + hlt["unfocus_color"] + line + hlt["reset"]
            in_pf_block = not in_pf_block
        if line.startswith("#"):
            if not in_pf_block:
                line = hlt["bold"] + hlt["header_color"] + line + hlt["reset"]
        if line.startswith("=>"):
            if not in_pf_block:
                link = get_link_from_line(line)
                state["current_links"].append(link)
                line = link["render_line"]
        state["render_body"].append(line.replace("\\n", "\n"))

    if (WRAP_TEXT and WRAP_MARGIN and type(WRAP_MARGIN) == int):
        cols -= WRAP_MARGIN
    
    in_pf_block = False
    screenfuls = slice_line(state["render_body"], rows - 1)
    for count, screenful in enumerate(screenfuls):
        for line in screenful:
            is_toggle_line = lambda _line: _line.startswith(hlt["italic"] + hlt["unfocus_color"] + "```") or _line.startswith("```")
            if is_toggle_line(line):
                in_pf_block = not in_pf_block
                if in_pf_block:
                    fmt(line.replace("```", ""), cols)
                    print(hlt["reset"])
                else:
                    continue
            if in_pf_block:
                if not is_toggle_line(line):
                    if (len(line) > cols):
                        sliced = slice_line(line, cols - 1)
                        print(sliced[0] + hlt["error_color"] + hlt["bold"] + ">" + hlt["reset"])
            else:
                fmt(line, cols)
        if (count + 1 == len(screenfuls)):
            continue
        else:
            ch = getch()
            if (ch == 'q' or ord(ch) == 4):
                break
            # print("\033[1A\r" + (" "*cols) + "\r", end='')

def get_input(prompt, meta):
    sensitive = True if meta[1] == "1" else False
    if sensitive:
        inp = getpass.getpass(prompt + "> ")
    else:
        print(prompt, end='> ')
        inp = input()
    return inp

if len(sys.argv) == 1:
    try:
        url = input("(URL): ")
    except (KeyboardInterrupt, EOFError):
        quit()
else:
    url = sys.argv[1]

if len(sys.argv) > 1:
    if ("-cert" in sys.argv):
        if (sys.argv[sys.argv.index("-cert") + 1]):
            state["context"] = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            state["context"].load_verify_locations(sys.argv[sys.argv.index("-cert") + 1])

state["context"].check_hostname = False
state["context"].verify_mode = ssl.CERT_NONE

command_list = ["exit", "quit", "back", "forward", "reload"]

def quit():
    log_info("\nexiting...")
    exit(0)

def reload():
    get_and_display(state["current_url"])

def get_and_display(url):
    url = validate_url(url)
    if not url:
        log_error("Invalid URL specified.")
        return
    state["current_links"] = []
    resp = get_document_ez(url)

    status = resp["status"]
    meta = resp["meta"]

    if (status.startswith("3")):
        log_info("redirected to", meta)
        url = meta
        get_and_display(meta)
    
    elif (status.startswith("5") or status.startswith("4")):
        log_error("Server returned code 4x/5x, info:", meta)

    elif (status.startswith("1")):
        log_info("Server at", state["current_hname"], "requested input")
        resp = get_document_ez(url + "?" + get_input(status, meta))
    
    elif (status.startswith("6")):
        log_error("Server requires you to be authenticated.\n\
            Please start leo with the -cert option with the path to a valid SSL cert passed in as an argument.")

    else:
        render(resp["body"])


command_impls = {
    "exit": quit,
    "quit": quit,
    "reload": reload,
}

if __name__ == "__main__":
    while True:
        split = url.split(" ")
        if (split[0] not in command_list):
            get_and_display(url)
            old_url = url

            try:
                url = input("(URL/Num): ")
            except (KeyboardInterrupt, EOFError):
                quit()
            try:
                link = state["current_links"][int(url)]
                url = link["url"]
            except ValueError:
                pass
            except IndexError:
                log_error("invalid link number specified")
                url = old_url
        else:
            command_impls[url]()
