#!/usr/bin/env python
from __future__ import annotations
from pathlib import Path

import argparse
import getpass
import json
import os
import pprint
import re
import site
import socket
import ssl
import sys
import typing
import urllib.parse

DEFAULT_CONFIG = {
    "wrap_text": False,
    "wrap_width": 0,
    "homepage": "",
    "cert_path": ""
}

GEMINI_PORT = 1965
REDIRECT_LOOP_THRESHOLD = 5

logger: typing.Callable | None = print
debug_logger: typing.Callable | None = None

hlt = {
    "reset": "\033[0m",
    "italic": "\033[3m",
    "bold": "\033[1m",
    "underline": "\033[4m",
    "error_color": "\033[38;5;1m",
    "info_color": "\033[38;5;3m",
    "header_color": "\033[38;5;119m",
    "link_color": "\033[38;5;13m",
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

        self.current_resp = []
        self.current_body = []

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
            appended = False
            if line.startswith("```"):
                line = hlt['italic'] + hlt['unfocus_color'] + line + hlt['reset']
                in_pf_block = not in_pf_block
                final += fmt(line, cols)
                appended = True
            if line.startswith("#"):
                if not in_pf_block:
                    line = f"{hlt['bold']}{hlt['header_color']}{line}{hlt['reset']}"
                    final += fmt(line, cols)
                    appended = True
            if line.startswith("=>"):
                if not in_pf_block:
                    link = get_link_from_line(line, self)
                    self.current_links.append(link)
                    line = link["render_line"]
                    final += fmt(line, cols)
                    appended = True
            if line.startswith(">"):
                if not in_pf_block:
                    line = "|" + line[1:]
                    final.append(line)
                    appended = True
            if in_pf_block:
                if not is_toggle_line(line):
                    if len(line) > cols:
                        sliced = slice_line(line, cols - 1)
                        line = f'{sliced[0]}{hlt["error_color"]}{hlt["bold"]}>{hlt["reset"]}'
                    else:
                        pass
                    final.append(line)
                appended = True
            if not appended:
                final += fmt(line, cols)
        self.current_body = [x for x in final]
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
                try:
                    cmd = get_user_input(f"{hlt['bold']}{hlt['unfocus_color']}Enter to continue reading, Ctrl-C to stop, or (URL/Num): {hlt['reset']}")
                except:
                    print(f'\r{" " * cols}\r', end='')
                    break
                if cmd == "":
                    pass
                else:
                    _type = get_input_type(cmd)
                    if _type == 0 or _type == 1:
                        if _type == 1:
                            try:
                                cmd = get_number_url(cmd, self)
                            except:
                                continue
                        cmd = validate_url(cmd, self.current_host, self.current_url, True)
                        self.navigate(cmd["final"])
                        break
                print(f'\033[1A\r{" " * cols}\r', end='')
    
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
            self.current_resp = resp["body"]
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
    
    def reload(self, args:list, browser:Browser):
        if 'hard' in args:
            self.navigate(self.current_url)
        else:
            self._page(self.current_body)
    
    def inspect(self, args: list, browser:Browser):
        pprint.pprint(self.current_resp)
    
    def back(self, args:list, browser:Browser):
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
        logger("ERROR:", *argv)
        logger(hlt["reset"], end='')

def log_debug(*argv):
    if debug_logger is not None:
        # pylint: disable=E1102
        debug_logger(*argv)

def set_term_title(s: str):
    print(hlt["set_title"]%s, end='')

def validate_url(url: str, host: str, current: str, internal=False):
    if internal:
        if (re.match(r'^\w*$', url)):
            return None
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
    link_parts = line[2:].strip().split(maxsplit=1)
    if len(link_parts) < 1:
        return {
            "url": browser.current_url,
            "text": "INVALID LINK",
            "render_line": f'{hlt["error_color"]}{hlt["bold"]}[INVALID LINK]{hlt["reset"]}'
        }
    if link_parts[0]:
        if len(link_parts) == 1:
            link_parts.append(link_parts[0])
    _text = "".join(link_parts[1:])
    scheme = ""
    validated = validate_url(link_parts[0], browser.current_host, browser.current_url)
    if validated["scheme"] != "gemini":
        scheme = f'{hlt["error_color"]}{hlt["bold"]} [{validated["scheme"]}]{hlt["reset"]}'
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

def print_formatted(str, end = '\n'):
    cols, _ = os.get_terminal_size()
    msg = fmt(str, cols - 4)
    final = "\n".join(msg) # +1 for \n and +1 to get to the end of the string
    print(final, end=end)

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
        raise EOFError
    return a

def quit(args:list, browser:Browser):
    # pylint: disable=unused-argument
    print("\n", hlt["bold"], hlt["info_color"], "Exiting...", hlt["reset"], sep='')
    exit(0)



def print_help(args:list, browser:Browser):
    # pylint: disable=unused-argument
    print(hlt["info_color"], hlt['bold'], "*** Commands ***", hlt["reset"], sep='')
    longest = len(sorted(command_impls.keys(), key=lambda a:len(a), reverse=True)[0])
    indent = '    '
    for (key, val) in command_impls.items():
        if ("help" in val):
            padded = key.ljust(longest, ' ')
            print_formatted(f"{indent}{hlt['bold']}{padded}{hlt['reset']}:  {val['help']}", '\n')

def get_input_type(url):
    split = url.split(" ")
    if (split[0] not in command_impls.keys()) and not re.match(r'\d+', url.strip()):
        return 0 # not a command, not a link no., must be a url
    elif re.match(r'\d+', url.strip()):
        return 1 # this is a link number
    else:
        return 2 # this is a command

def get_number_url(n, browser: Browser, internal=False):
    try:
        link = browser.current_links[int(n)]
        _url = link["url"]
        if urllib.parse.urlparse(_url).scheme != "gemini":
            if not internal:
                log_info("Sorry, leo does not support that scheme yet.")
                raise ValueError
            else:
                return _url
        else:
            return _url
    except (IndexError, ValueError):
        log_error("invalid link number specified:", str(n))
        raise ValueError

def can_write(path):
    if path == "":
        raise ValueError
    if os.path.isfile(path):
        raise FileExistsError
    if os.path.isdir(path):
        raise IsADirectoryError
    parent = os.path.dirname(path)
    if "/" in path and not os.path.isdir(parent):
        raise NotADirectoryError
    if os.path.isfile(path) and not os.access(path, os.W_OK):
        raise PermissionError
    return True

def saveurl(args: list, browser: Browser):
    if (len(args)) <= 1:
        log_error("You must specify a filename.")
        return
    mode = "w"
    path = args[1].strip()
    if re.match(r"^\d+$", path):
        print_formatted(f"You entered a number for the filename. Are you sure you want to save under the name '{path}'?", ' ')
        try:
            inp = input("(y / n) ").lower().strip()
        except:
            return
        if (inp == "y"):
            pass
        else:
            return

    args = args[2:]
    lines = []
    if args == []: # no numbers specified
            lines.append(browser.current_url) # write the current url
    else: # numbers specified
        for arg in args:
            try:
                _url = get_number_url(arg, browser)
                lines.append(_url)
            except:
                log_error(f"Invalid link number specified: {arg}")
    try:
        can_write(path)
    except ValueError:
        log_error("Filename was empty.")
        return
    except FileExistsError:
        inp = input(hlt["bold"] + "File exists. (O)verwrite/ (A)ppend / (C)ancel " + hlt["reset"]) # prompt
        inp = inp.lower().strip()
        modes = {"o": "w", "a": "a"}
        if inp in modes:
            mode = modes[inp]
        else: # any other input mode
            log_info("Cancelled.")
            return
    except IsADirectoryError:
        log_error("Supplied path is a directory.")
        return
    except PermissionError:
        log_error(f"Cannot write to {path}: Insufficient permissions")
        return
    except NotADirectoryError:
        parent = os.path.dirname(path)
        log_error(f"Cannot write to {parent}: No such directory")
        return
    with open(path, mode) as fp:
        try:
            fp.writelines(map(lambda a: a + "\n", lines))
            log_info("Saved files successfully.")
        except:
            log_error("Could not save files.")

def printurl(args:list, browser:Browser):
    if (len(args)) == 1:
        log_info("Current URL:", browser.current_url)
        return
    for arg in args[1:]:
        try:
            _url = get_number_url(int(arg), browser, True)
            log_info("URL of %d is %s" % (int(arg), _url))
        except ValueError:
            log_error("invalid link number specified")

def load_default_config():
    config_file_location = os.path.join(get_config_path(), "config.json")
    if os.path.isfile(config_file_location):
        try:
            fp = open(config_file_location, "r")
            _config = json.loads(fp.read())
            fp.close()
            return _config
        except:
            log_error(f"Error reading config from {config_file_location}")
            quit(None, None)
    return None


def get_config_path(silent=True):
    xdg_dir = os.getenv("XDG_CONFIG_HOME")
    if not xdg_dir:
        if not silent:
            log_info("XDG_CONFIG_HOME not found: falling back to ~/.config/leo")
        home = os.getenv("HOME")
        cfg_location = os.path.join(home, ".config/", "leo")
    else:
        cfg_location = os.path.join(xdg_dir, "leo")
    return cfg_location

def create_config(cfg):
    cfg_location = get_config_path(False)
    try:
        Path(cfg_location).mkdir(parents=True, exist_ok=True) # create path if it doesn't exist.
        with open(os.path.join(cfg_location, "config.json"), "w") as fp:
            fp.write(json.dumps(cfg, sort_keys=True, indent=4))
        log_info(f"Stored config in {cfg_location}.")
        quit(None, None)
    except PermissionError:
        log_error(f"Could not write config to {cfg_location}: permission denied")
        quit(None, None)

def handle_args(args):
    if args.copy_config:
        create_config(DEFAULT_CONFIG)
        quit(None, None)
    
    if args.print_config:
        print(json.dumps(DEFAULT_CONFIG, indent=4, sort_keys=True))
        exit(0)

if __name__ == "__main__":
    url = ""
    old_url = ""

    parser = argparse.ArgumentParser(prog='leo', description="Command-line Gemini browser.")
    parser.add_argument("--url", required=False, type=str, help='Initial URL to navigate to. If left blank and no homepage is set, you will be prompted.')
    parser.add_argument("--config", required=False, type=str, help='Temporary config file location. If left blank, leo will load the default config.')
    parser.add_argument("--copy-config", required=False, action="store_true", help='Copy the default config file to either XDG_CONFIG_HOME (if set) or ~/.config/leo/ (Will be created if it does not exist).')
    parser.add_argument("--print-config", required=False, action="store_true", help='Print out the default config.')
    args = parser.parse_args()
    handle_args(args)

    config = DEFAULT_CONFIG
    defaults = False

    _config = load_default_config()
    if (_config):
        config = _config
    if args.config:
        if (os.path.isfile(args.config)):
            fp = open(args.config)
            config = json.loads(fp.read())
            fp.close()
            log_info(f"Loaded config from {args.config}")
    else:
        if (_config):
            config_file_location = os.path.join(get_config_path(), "config.json")
            log_info(f"Loaded config from {config_file_location}")
        else:
            log_error("Config not found: falling back to defaults.")
            defaults = True

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
            "help": "Redisplays the current page. Type `reload hard` to redownload the page."
        },
        "back": {
            "fn": browser.back,
            "help": "Goes back a page."
        },
        "help": {
            "fn": print_help,
        },

        "printurl": {
            "fn": printurl,
            "help": "(Usage: printurl [n1] [n2] ...) Print the URL of the links with numbers n1, n2, and so on. If no number is specified, prints the current URL."
        },

        "saveurl": {
            "fn": saveurl,
            "help": "(Usage: saveurl FILENAME [n1] [n2] ...) Save the URLs of the links with numbers n1, n2, and so on to a file in the current working directory called FILENAME. If no number is specified, it saves the current URL."
        },

        "inspect": {
            "fn": browser.inspect,
            "help": "Displays the raw gemtext of the current page."
        }
    }

    if defaults:
        print_help(None, None)

    if "homepage" in config and config["homepage"] != "":
        url = config["homepage"] # takes precedence over prompting
    
    if (args.url):
        url = args.url # always takes precedence over config file

    while True:
        old_url = url
        try:
            url = get_user_input("(URL/Num): ")
            if url == "":
                continue
        except EOFError:
            quit(None, None)
        except ValueError:
            continue
        _type = get_input_type(url)
        if _type == 0: # text url
            _url = validate_url(url, browser.current_host, browser.current_url, True)
            if _url is not None:
                url = _url["final"]
            else:
                url = None
        elif _type == 1: # number
            try:
                url = get_number_url(url, browser)
            except:
                url = None
        elif _type == 2: # command
            split = url.split(" ")
            command_impls[split[0]]["fn"](split, browser)

        if (_type == 0 or _type == 1) and url is not None:
            browser.navigate(url)
        elif _type == 0 and url is None:
            log_error("Invalid url specifed.")