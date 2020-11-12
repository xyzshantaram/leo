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
    "render_body": [],
    "current_links": []
}

global GEMINI_PORT
GEMINI_PORT = 1965

state["context"].check_hostname = False
state["context"].verify_mode = ssl.CERT_NONE

def validate_url(url):
    if (re.match(r"(((http([s])?:\/\/)|(gemini:\/\/))?[a-zA-Z0-9\-]+\.[a-zA-Z0-9])?\/?[^\/\t\n\ \r]+(\/?[^\/\/\n\ \r\t]+)*\/?", url)):
        if ("gemini://" not in url):
            if (url.startswith("http")):
                log("HTTP is not supported yet, sorry")
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


def log(*argv):
    if (state["logger"]):
        state["logger"](*argv)


def gemini_get_document(url, port = GEMINI_PORT):
    url = validate_url(url)
    state["current_url"] = url
    log("attempting to get", url)
    hostname = get_hostname(url)
    state["sock"] = socket.create_connection((hostname, port))
    state["ssock"] = state["context"].wrap_socket(
        state["sock"], server_hostname=hostname)
    log("Connected to", hostname, "over", state["ssock"].version())
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
        response_body = response_body.decode("UTF-8").strip().split("\n")
        fp.close()
    elif (status.startswith("3")):
        log("redirected to", meta)
        return gemini_get_document(meta, GEMINI_PORT)
    elif (status.startswith("5") or status.startswith("4")):
        log("Server returned code 41/51, metadata:", meta)
    return {
        "status": status,
        "meta": meta,
        "body": response_body
    }

def render(url):
    resp = gemini_get_document(url, GEMINI_PORT)
    print("GET", "returned code", resp["status"])
    print("MIME type of body was", resp["meta"]) if resp["status"] == "20" else ""
    if (resp["body"]):
        for i in range(len(resp["body"])):
            line = resp["body"][i]
            if line.startswith("=>"):
                link_parts = line.split()
                link_parts = link_parts[1:]
                if (link_parts[0]):
                    if not (link_parts[1]):
                        link_parts.append(link_parts[0]) # duplicate the URL if there is no pretty text
                    state["current_links"].append({
                        "url": validate_url(link_parts[0]),
                        "text": " ".join(link_parts[1:]),
                    })
                    line = line.replace(link_parts[0], str(len(state["current_links"]) - 1))
            state["render_body"].append(line.replace("\\n", "\n"))
        for i in state["render_body"]:
            print(i)


if len(sys.argv) == 1:
    url = input("Enter hostname / URL: ")
else:
    url = sys.argv[1]

while True:
    if (url not in ["exit", "quit", "q", "e"]):
        state["render_body"] = []
        state["current_links"] = []
        render(url)
    url = input()
    try:
        link = state["current_links"][int(url)]
        url = link["url"]
    except ValueError:
        pass

