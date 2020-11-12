import socket
import ssl
import sys
import curses
import re

state = {
    "current_hname": "",
    "current_url": "",
    "sock": None,
    "ssock": None,
    "context": ssl.create_default_context(),
    "logger": print,
    "render_body": []
}

state["context"].check_hostname = False
state["context"].verify_mode = ssl.CERT_NONE


def validate_url(url):
    if (re.match(r"((gemini:\/\/)?[a-zA-Z0-9\-]+\.[a-zA-Z0-9])?\/?[^\/\t\n\ \r]+(\/?[^\/\/\n\ \r\t]+)*\/?", url)):
        if ("gemini://" not in url):
            if (re.match(r"[a-zA-Z0-9\-]+\.[a-zA-Z].*", url)):
                return "gemini://" + url + "/"
            else:
                if (url[0].isalnum()):
                    url = state["current_url"] + url
                    if not url.endswith("/"):
                        url += "/"
                    return url
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


def gemini_get_document(url, port):
    url = validate_url(url)
    state["current_url"] = url
    log("attempting to get", url)
    hostname = get_hostname(url)
    if state["current_hname"] != hostname:
        state["sock"] = socket.create_connection((hostname, port))
        state["ssock"] = state["context"].wrap_socket(
            state["sock"], server_hostname=hostname)
        log("Connected to", hostname, "over", state["ssock"].version())
    else:
        pass
    state["current_hname"] = hostname
    state["ssock"].sendall(get_encoded(url))
    fp = state["ssock"].makefile("rb")
    header = fp.readline()
    header = header.decode("UTF-8").strip().split()
    status = header[0]
    meta = header[1]
    response_body = None
    if (status.startswith("2")):
        response_body = fp.read().decode("UTF-8").strip().split("\n")
        fp.close()
    elif (status.startswith("3")):
        fp.close()
        log("redirected to", meta)
        return gemini_get_document(meta, 1965)

    return {
        "status": status,
        "meta": meta,
        "body": response_body
    }


if len(sys.argv) == 1:
    url = input("Enter hostname / URL: ")
else:
    url = sys.argv[1]

a = gemini_get_document(url, 1965)

print(get_hostname(url), "returned code", a["status"])
print(validate_url("users/"))
print("MIME type of body was", a["meta"]) if a["status"] == "20" else ""
if (a["body"]):
    for i in a["body"]:
        line = i
        state["render_body"].append(i.replace("\\n", "\n"))
    for i in state["render_body"]:
        print(i)