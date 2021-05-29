#!/usr/bin/env python
from __future__ import annotations

import socket
import ssl
import argparse
import re
import os
import getpass
import urllib.parse
import json
import typing

GEMINI_PORT = 1965
REDIRECT_LOOP_THRESHOLD = 5

logger: typing.Callable | None = print
debug_logger: typing.Callable | None

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

class Browser:
    def __init__(self, config):
        self.current_host = ""
        self.current_url = ""
        self.sock = None
        self.ssock = None

        self.context = ssl.create_default_context()
        self.context.check_hostname = False
        self.context.verify_mode = ssl.CERT_NONE

        self.current_links = []
        self.last_load_was_redirect = False
        self.redirect_count = 0
        self.history = []
        self.current_history_idx = 0

        if ("wrap_text" in config):
            self.wrap_text = config["wrap_text"]
        else:
            self.wrap_text = False
            
        self.wrap_width = 0
        if (self.wrap_text and "wrap_width" in config):
            self.wrap_width = config["wrap_width"]
        
        self.cert_path = config["cert_path"]
        if (os.path.isfile(self.cert_path)):
            self.enable_cert()
    
    def _get_gemini_document(self, url, port = GEMINI_PORT):
        """
        Gets a document via the Gemini protocol.
        """
        self.current_url = url
        log_info("attempting to get", url)
        hostname = get_hostname(url)
        self.sock = socket.create_connection((hostname, port))
        self.ssock = self.context.wrap_socket(
            self.sock, server_hostname=hostname
        )
        log_info("Connected to", hostname, "over", self.ssock.version())
        self.current_host = hostname
        set_term_title(hostname)

        self.ssock.sendall(get_encoded(url))

        with self.ssock.makefile("rb") as fp:
            header = fp.readline()
            header = header.decode("UTF-8").strip().split()
            status = header[0]
            charset = "UTF-8"
            for item in header:
                if item.lower().startswith("charset="):
                    charset = item.split("=", maxsplit=1)[1].replace(";", "")
            meta = " ".join(header[1:])
            response_body = fp.read()
            if response_body:
                response_body = response_body.decode(charset)
                response_body = response_body.split("\n")
            fp.close()
        return {
            "status": status,
            "meta": meta,
            "body": response_body
        }
    
    def _get_render_body(self, file):
        cols, _ = os.get_terminal_size()
        if (self.wrap_text and self.wrap_width):
            cols = min(cols, self.wrap_width)
        final = []
        is_toggle_line = lambda _line: _line.startswith(hlt["italic"] + hlt["unfocus_color"] + "```") or _line.startswith("```")
        in_pf_block = False
        for line in file:
            if line.startswith("```"):
                line = "%s%s%s%s" % (hlt["italic"], hlt["unfocus_color"], line, hlt["reset"])
                in_pf_block = not in_pf_block
            elif line.startswith("#"):
                if not in_pf_block:
                    line = "%s%s%s%s" % (hlt["bold"], hlt["header_color"], line, hlt["reset"])
                    final += fmt(line, cols)
            elif line.startswith("=>"):
                if not in_pf_block:
                    link = get_link_from_line(line, self)
                    self.current_links.append(link)
                    line = link["render_line"]
                    final += fmt(line, cols)
            elif line.startswith(">"):
                line[0] = "|"
            else:
                if in_pf_block:
                    if not is_toggle_line(line):
                        if len(line) > cols:
                            sliced = slice_line(line, cols - 1)
                            final.append("%s%s%s>%s" % (sliced[0], hlt["error_color"], hlt["bold"], hlt["reset"]))
                        else:
                            final.append(line)
                    else:
                        final += fmt(line, cols)
                else:
                    final += fmt(line, cols)
        return final

    def _page(self, lines):
        cols, rows = os.get_terminal_size()
        if (self.wrap_text and self.wrap_width):
            cols = min(cols, self.wrap_width)
        screenfuls = slice_line(lines, rows - 1)
        for count, screenful in enumerate(screenfuls):
            for line in screenful:
                print(line)
            if (count + 1) == len(screenfuls):
                continue
            else:
                cmd = get_user_input(f"{hlt['bold']}Enter to continue reading, Ctrl-C to stop, or (URL/Num): {hlt['reset']}")
                if cmd == "":
                    pass
                elif cmd == -1:
                    print("\r" + (" "*cols) + "\r", end='')
                    break
                else:
                    isURL = False
                    _type = get_input_type(cmd)
                    if _type == 0: # plaintext URL
                        isURL = True
                        pass
                    elif _type == 1: # number
                        cmd = get_number_url(cmd, self)
                        if cmd != -1:
                            isURL = True
                            
                    elif _type == 2:
                        pass
                    if isURL:
                        cmd = validate_url(cmd, self.current_host, self.current_url, True)
                        if cmd:
                            self.navigate(cmd["final"])
                        else:
                            log_error("Invalid URL.")
                        
                        break
                print("\033[1A\r" + (" "*cols) + "\r", end='')
    
    def _render(self, file):
        lines = self._get_render_body(file)
        self._page(lines)

    def navigate(self, url):
        self.history.append(url)
        self.current_links = []
        resp = self._get_gemini_document(url)

        status = resp["status"]
        meta = resp["meta"]

        if len(status) < 2:
            log_error("Server returned invalid status code.")
            return

        if status.startswith("1"):
            log_info("Server at", self.current_host, "requested input")
            _url = url if url[-1] != '/' else url[:len(url) - 1] # remove trailing /
            result = _url + "?" + get_1x_input(status, meta)
            self.navigate(result)
        
        elif status.startswith("2"):
            self.last_load_was_redirect = False
            self._render(resp["body"])
        
        elif status.startswith("3"):
            log_info("redirected to", meta)

            if self.redirect_count > 5:
                log_info("Redirect cycle detected.")
                self.redirect_count = 0
                return

            url = meta
            self.redirect_count += 1

            if not self.last_load_was_redirect:
                self.redirect_count = 1
            
            self.last_load_was_redirect = True
            rurl = validate_url(meta, self.current_host, self.current_url)
            
            if (not rurl) or rurl["scheme"] != "gemini":
                log_info("Site attempted to redirect us to a non-gemini protocol. Stopping.")
                return
            else:
                self.navigate(rurl["final"])
        
        elif status.startswith("4") or status.startswith("5"):
            log_error("Server returned code 4x/5x (TEMPORARY/PERMANENT FAILURE), info:", meta)
        
        elif status.startswith("6"):
            log_error("Server requires you to be authenticated.\nPlease set a valid cert path in config.json and restart leo.")
        else:
            log_error("Server returned invalid status code.")
    
    def reload(self):
        self.navigate(self.current_url)
    
    def back(self):
        print(self.history)
        if len(self.history) <= 1:
            return
        self.history.pop()
        self.navigate(self.history.pop())
    
    def enable_cert(self):
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.load_verify_locations(self.cert_path)

        

def log(*argv):
    log_debug(*argv)
    if logger:
        logger(*argv)

def log_info(*argv):
    if logger:
        logger(hlt["bold"] + hlt["info_color"], end='')
        logger(*argv)
        logger(hlt["reset"], end='')

def log_error(*argv):
    log_debug(*argv)
    if logger:
        logger(hlt["bold"], hlt["error_color"], sep='', end='')
        logger(*argv)
        logger(hlt["reset"], end='')

def log_debug(*argv):
    if debug_logger:
        # pylint: disable=C0321
        debug_logger(*argv)

def set_term_title(s: str):
    print(hlt["set_title"]%s, end='')

def validate_url(url: str, host: str, current: str, internal=False):
    if "://" not in url:
        if internal and re.match(r"^([^\W_]+)(\.([^\W_]+))+", url):
            return {
                "final": "gemini://" + url,
                "scheme": "gemini"
            }
        base = host
        if "gemini://" not in base:
            base = "https://" + base
        if base == "":
            raise ValueError("Relative URL parsed with no valid hostname")
        if url.startswith("/"):
            url = urllib.parse.urljoin(base, url).replace("https", "gemini")
        else:
            current_copy = current.replace("gemini", "https")
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

def get_link_from_line(line, browser: Browser):
    link_parts = line.strip().split(maxsplit=2)
    del link_parts[0] # remove the =>
    if len(link_parts) < 1:
        return {
            "url": browser.current_url,
            "text": "INVALID LINK",
            "render_line": "%s%s [%s]%s" % (hlt["error_color"], hlt["bold"], "INVALID LINK", hlt["reset"]),
        }
    if link_parts[0]:
        if len(link_parts) == 1:
            link_parts.append(link_parts[0])
    _text = "".join(link_parts[1:])
    scheme = ""
    validated = validate_url(link_parts[0], browser.current_host, browser.current_url)
    if validated["scheme"] != "gemini":
        scheme = "%s%s [%s]%s" % (hlt["error_color"], hlt["bold"], validated["scheme"], hlt["reset"])
    return {
        "url": validated["final"],
        "text": _text,
         # print links in bold, underlined.
         "render_line": "%s%s%s%d%s%s %s" % (hlt["bold"], hlt["underline"], hlt["link_color"], len(browser.current_links), hlt["reset"], scheme, _text)
    }

def slice_line(line, length):
    sliced = [line[i:i + length] for i in range(0, len(line), length)]
    return sliced

def fmt(line, width):
    if line.strip() == "":
        return [""]
    final = []
    copy = line
    words = []
    length = 0
    copy = copy.split(' ')
    if copy[0] == line:
        copy = line.split('-')
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
    return final

def get_1x_input(status, meta):
    prompt = meta
    sensitive = True if status[1] == "1" else False
    if sensitive:
        inp = getpass.getpass(prompt + "> ")
    else:
        print(prompt, end='> ')
        inp = input()
    return inp

def get_user_input(prompt):
    a = None
    try:
        a = input(prompt)
    except (EOFError, KeyboardInterrupt):
        a = -1 # User terminated input
    return a

def quit():
    print("\n", hlt["bold"], hlt["info_color"], "Exiting...", hlt["reset"], sep='')
    exit(0)

def print_help():
    print(hlt["info_color"], hlt['bold'], "*** Commands ***", hlt["reset"], sep='')
    for (key, val) in command_impls.items():
        if ("help" in val):
            print(f"\t{hlt['bold']}{key}{hlt['reset']}:\t{val['help']}")


def get_input_type(url):
    split = url.split(" ")
    if (split[0] not in command_impls.keys()) and not re.match(r'\d+', url.strip()):
        return 0 # not a command, not a link no., must be a url
    elif re.match(r'\d+', url.strip()):
        return 1 # this is a link number
    else:
        return 2 # this is a command

def get_number_url(n, browser: Browser):
    try:
        link = browser.current_links[int(n)]
        _url = link["url"]
        if urllib.parse.urlparse(_url).scheme != "gemini":
            log_info("Sorry, leo does not support that scheme yet.")
            return -1 # -1 means that you should keep the old url
        else:
            return _url
    except IndexError:
        log_error("invalid link number specified")
        return -1

if __name__ == "__main__":
    url = ""
    old_url = ""

    parser = argparse.ArgumentParser(prog='leo', description="Command-line Gemini browser.")
    parser.add_argument("--url", required=False, type=str, help='Initial URL to navigate to. If left blank and no homepage is set, you will be prompted.')
    parser.add_argument("--config", required=False, type=str, help='Config file location. If left blank, will look for a file named config.json in the current working directory.')
    args = parser.parse_args()

    config = {
        "wrap_text": False,
        "wrap_width": 0,
        "homepage": "",
        "cert_path": ""
    }

    config_path = ""

    if args.config:
        if (os.path.isfile(args.config)):
            config_path = args.config
            config = json.loads(open(args.config).read())
    else:
        path = (os.path.realpath(__file__))
        parts = path.split('/')
        del parts[-1]
        path = f"{'/'.join(parts)}/config.json"
        if os.path.isfile(path):
            config_path = path
            config = json.loads(open(path).read())
    if config_path != "":
        log_info(f"Loaded config from {config_path}")

    browser = Browser(config)

    command_impls = {
        "exit": {
            "fn": quit,
            "help": "Exits leo."
        },
        "quit": {
            "fn": quit,
            "help": "Exits leo."
        },
        "reload": {
            "fn": browser.reload,
            "help": "Reloads the current page."
        },
        "back": {
            "fn": browser.back,
            "help": "Goes back a page."
        },
        "help": {
            "fn": print_help,
        },
    }

    if "homepage" in config and config["homepage"] != "":
        url = config["homepage"] # takes precedence over prompting
    
    if (args.url):
        url = args.url # always takes precedence over config file
    else:
        try:
            url = input("(URL): ") # never takes precedence
        except (KeyboardInterrupt, EOFError):
            quit()

    while True:
        if url == "":
            url = get_user_input("(URL/Num): ")
            continue
        if url == -1:
            quit()
        else:
            _type = get_input_type(url)
            if _type == 0: # text url
                _url = validate_url(url, browser.current_host, browser.current_url, True)
                if not _url:
                    log_error("Invalid URL specified.")
                    url = get_user_input("(URL/Num): ")
                    continue
                else:
                    url = _url["final"]
            elif _type == 1: # number
                url = get_number_url(url, browser)
                if url == -1:
                    url = old_url
            elif _type == 2: # command
                split = url.split(" ")
                command_impls[url]["fn"]()
                pass

            if _type == 0 or _type == 1:
                browser.navigate(url)
        
        old_url = url
        url = get_user_input("(URL/Num): ")