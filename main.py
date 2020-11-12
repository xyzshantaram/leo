import socket
import ssl
import sys
import re

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
    "unfocus_color": "\033[38;5;8m"
}

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
        state["debug_logger"](*args)

global GEMINI_PORT
GEMINI_PORT = 1965

state["context"].check_hostname = False
state["context"].verify_mode = ssl.CERT_NONE

def validate_url(url):
    if (re.match(r"(((http([s])?:\/\/)|(gemini:\/\/))?[a-zA-Z0-9\-]+\.[a-zA-Z0-9])?\/?[^\/\t\n\ \r]+(\/?[^\/\/\n\ \r\t]+)*\/?", url)):
        if ("gemini://" not in url):
            if (url.startswith("http")):
                log_info("while parsing url", url, ":")
                log_debug("HTTP is not supported yet, sorry")
                return state["current_url"]
            if (re.match(r"[a-zA-Z0-9\-]+\.[a-zA-Z].*", url) and not url.endswith(".gmi")):
                return "gemini://" + url + "/"
            else:
                if (url[0].isalnum()):
                    url = state["current_url"] + "/" + url
                    """if not url.endswith("/"):
                        url += "/" """
                    return url
                elif url.startswith("/"):
                    url = validate_url(state["current_hname"] + "/" + url)
        else:
            return url
    else:
        if (url == "/"):
            return validate_url(state["current_hname"])
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
    url = validate_url(url)
    state["current_url"] = url
    log_info("attempting to get", url)
    hostname = get_hostname(url)
    state["sock"] = socket.create_connection((hostname, port))
    state["ssock"] = state["context"].wrap_socket(
        state["sock"], server_hostname=hostname)
    log_info("Connected to", hostname, "over", state["ssock"].version())
    state["current_hname"] = hostname
    state["ssock"].sendall(get_encoded(url))
    fp = state["ssock"].makefile("rb")
    header = fp.readline()
    header = header.decode("UTF-8").strip().split()
    status = header[0]
    meta = " ".join(header[1:])
    response_body = fp.read()
    fp.close()
    if (status.startswith("2")):
        response_body = response_body.decode("UTF-8").split("\n")
        fp.close()
    elif (status.startswith("3")):
        log_info("redirected to", meta)
        return gemini_get_document(meta, GEMINI_PORT)
    elif (status.startswith("5") or status.startswith("4")):
        log_error("Server returned code 41/51, metadata:", meta)
    return {
        "status": status,
        "meta": meta,
        "body": response_body
    }

def render(url):
    resp = gemini_get_document(url, GEMINI_PORT)
    log_info("GET", url, "returned code", resp["status"])
    log_info("MIME type of body was", resp["meta"]) if resp["status"] == "20" else ""
    if (resp["body"]):
        in_pf_block = False
        for i in range(len(resp["body"])):
            line = resp["body"][i]
            if (line.startswith("```")):
                line = hlt["italic"] + hlt["unfocus_color"] + line[3:] + hlt["reset"]
                """ line = line[:3] """
                in_pf_block = not in_pf_block
            if line.startswith("#"):
                if not in_pf_block:
                    line = hlt["bold"] + hlt["header_color"] + line + hlt["reset"]
            if line.startswith("=>"):
                if not in_pf_block:
                    link_parts = line.split()
                    link_parts = link_parts[1:]
                    if (link_parts[0]):
                        if not (link_parts[1]):
                            link_parts.append(link_parts[0]) # duplicate the URL if there is no pretty text
                        state["current_links"].append({
                            "url": validate_url(link_parts[0]),
                            "text": " ".join(link_parts[1:]),
                        })
                        line = line.replace(link_parts[0], hlt["bold"] + hlt["underline"] + hlt["link_color"] + str(len(state["current_links"]) - 1) + hlt["reset"])
            state["render_body"].append(line.replace("\\n", "\n"))
        for i in state["render_body"]:
            print(i)


if len(sys.argv) == 1:
    url = input("(URL): ")
else:
    url = sys.argv[1]

while True:
    if (url not in ["exit", "quit", "q", "e"]):
        state["render_body"] = []
        state["current_links"] = []
        render(url)
    url = input("(URL/Num: ")
    try:
        link = state["current_links"][int(url)]
        url = link["url"]
    except ValueError:
        pass

