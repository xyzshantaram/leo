#!/usr/bin/env python

import socket
import ssl
import sys
import re
import os
import getpass
import urllib.parse

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

global REDIRECT_LOOP_THRESHOLD
REDIRECT_LOOP_THRESHOLD = 5

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
    "current_links": [],
    "last_load_was_redirect": False,
    "redirect_count": 0,
    "inp_buffer": ""
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

def validate_url(url):
    if "://" not in url:
        if re.match(r"([^\W_]+)(\.([^\W_]+))+", url):
            return {
                "final": "gemini://" + url,
                "scheme": "gemini"

            }
        base = state["current_hname"]
        if "gemini://" not in base:
            base = "https://" + base
        if base == "":
            raise ValueError("Relative URL parsed with no valid hostname")
        if (url.startswith("/")):
            url = urllib.parse.urljoin(base, url).replace("https", "gemini")
        else:
            current_copy = state["current_url"].replace("gemini", "https")
            url = urllib.parse.urljoin(current_copy, url)
            url = url.replace("https", "gemini")
    parsed_url = urllib.parse.urlparse(url)
    return {
        "final": parsed_url.geturl(),
        "scheme": parsed_url.scheme
    }

def get_hostname(url):
    ret = urllib.parse.urlparse(url).netloc
    return ret


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
    charset = "UTF-8"
    for item in header:
        if item.lower().startswith("charset="):
            charset = item.split("=", maxsplit=1)[1].replace(";", "")
    meta = " ".join(header[1:])
    response_body = fp.read()
    if (response_body):
        response_body = response_body.decode(charset)
        response_body = response_body.split("\n")
    fp.close()
    return {
        "status": status,
        "meta": meta,
        "body": response_body
    }

def get_document_ez(url):
    resp = gemini_get_document(url, GEMINI_PORT)
    """ log_info("GET", url, "returned code", resp["status"])
    log_info("MIME type of body was", resp["meta"]) if resp["status"] == "20" else "" """
    return resp

def get_link_from_line(line):
    link_parts = line.strip().split(maxsplit=2)
    link_parts = link_parts[1:] # remove =>
    if (len(link_parts) < 1):
        return {
            "url": state["current_url"],
            "text": "INVALID LINK",
            "render_line": "%s%s[%s]%s" % (hlt["error_color"], hlt["bold"], "INVALID LINK", hlt["reset"]),
        }
    if (link_parts[0]):
        if (len(link_parts) == 1):
            link_parts.append(link_parts[0])
    _text = "".join(link_parts[1:])
    text = " "
    validated = validate_url(link_parts[0])
    if (validated["scheme"] != "gemini"):
        text = "%s%s[%s]%s %s" % (hlt["error_color"], hlt["bold"], validated["scheme"], hlt["reset"], _text)
    return {
        "url": validated["final"],
        "text": _text,
         # print links in bold, underlined.
        "render_line": hlt["bold"]
            + hlt["underline"] + hlt["link_color"]
            + str(len(state["current_links"]))
            + hlt["reset"] + text + " "
            + _text
    }

def slice_line(line, length):
    sliced = [line[i:i + length] for i in range(0, len(line), length)]
    return sliced

def fmt(line, width):
    if (line.strip() == ""):
        return
    final = []
    copy = line
    words = []
    length = 0
    copy = copy.split(' ')
    if (copy[0] == line):
        copy = copy.split('-')
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
                    print(hlt["reset"], end='')
                else:
                    print()
                    continue
            if in_pf_block:
                if not is_toggle_line(line):
                    if (len(line) > cols):
                        sliced = slice_line(line, cols - 1)
                        print(sliced[0] + hlt["error_color"] + hlt["bold"] + ">" + hlt["reset"])
                    else:
                        print(line)
            else:
                fmt(line, cols)
        if (count + 1 == len(screenfuls)):
            continue
        else:
            ch = getch()
            if (ch == 'q' or ord(ch) == 4):
                break
            # print("\033[1A\r" + (" "*cols) + "\r", end='')

def get_input(status, meta):
    prompt = meta
    sensitive = True if status[1] == "1" else False
    if sensitive:
        inp = getpass.getpass(prompt + "> ")
    else:
        print(prompt, end='> ')
        inp = input()
    return inp

state["context"].check_hostname = False
state["context"].verify_mode = ssl.CERT_NONE

command_list = ["exit", "quit", "back", "forward", "reload"]

def quit():
    log_info("\nexiting...")
    exit(0)

def reload():
    get_and_display(state["current_url"])

def get_and_display(url):
    state["current_links"] = []
    resp = get_document_ez(url)

    status = resp["status"]
    meta = resp["meta"]

    if (len(status) < 2):
        log_error("Server returned invalid status code.")
        return

    if (status.startswith("1")):
        log_info("Server at", state["current_hname"], "requested input")
        _url = url if url[-1] != '/' else url[:len(url) - 1]
        result = _url + "?" + get_input(status, meta)
        get_and_display(result)
    
    elif (status.startswith("2")):
        state["last_load_was_redirect"] = False
        render(resp["body"])

    elif (status.startswith("3")):
        log_info("redirected to", meta)
        if state["redirect_count"] > 5:
            log_info("Redirect cycle detected.")
            state["redirect_count"] = 0
            return
        url = meta
        state["redirect_count"] += 1
        if not state["last_load_was_redirect"]:
            state["redirect_count"] = 1

        state["last_load_was_redirect"] = True
        rurl = validate_url(meta)
        if (rurl["scheme"] != "gemini"):
            log_info("Site attempted to redirect us to a non-gemini protocol. Stopping.")
            return
        else:
            get_and_display(rurl["final"])
        
    elif  status.startswith("4") or status.startswith("5"):
        log_error("Server returned code 4x/5x, info:", meta)
    
    elif (status.startswith("6")):
        log_error("Server requires you to be authenticated.\n\
            Please start leo with the -cert option with the path to a valid SSL cert passed in as an argument.")

    else:
        log_error("Server returned invalid status code.")


command_impls = {
    "exit": quit,
    "quit": quit,
    "reload": reload,
}

if __name__ == "__main__":
    url = ""
    old_url = ""
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
    while True:
        command = False
        split = url.split(" ")

        if (split[0] not in command_list) and not re.match(r'\d+', url.strip()):
            pass
        elif re.match(r'\d+', url.strip()):
            try:
                link = state["current_links"][int(url)]
                _url = link["url"]
                if (urllib.parse.urlparse(_url).scheme != "gemini"):
                    log_info("Gemini does not support that scheme yet.")
                    url = old_url
                else:
                    url = _url
            except ValueError:
                pass
            except IndexError:
                log_error("invalid link number specified")
                url = old_url
                continue
        else:
            command = True
            command_impls[url]()

        if url and not command:
            url = validate_url(url)["final"]
            if not url:
                log_error("Invalid URL specified.")
            else:
                get_and_display(url.strip())

        try:
            old_url = url
            url = input("(URL/Num): ")
        except (KeyboardInterrupt, EOFError):
            quit()