import socket
import ssl
import sys

def validate_url(url):
    if ("gemini://" not in url):
        return "gemini://" + url
    else:
        return url

def get_encoded(s):
    return ((s + "\r\n").encode("UTF-8"))

if len(sys.argv) == 1:
    hostname, port = input("Enter hostname and port (colon-separated): ").split(":")
    port = int(port)
else:
    hostname, port = sys.argv[1].split(":")
    port = int(port)

context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

def gemini_get_document(url, port, logger):
    sock = socket.create_connection((hostname, port))
    ssock = context.wrap_socket(sock, server_hostname=hostname)
    if logger:
        logger("Connected to", hostname, "over", ssock.version())
    ssock.sendall(get_encoded(validate_url(hostname)))
    fp = ssock.makefile("rb")
    header = fp.readline()
    header = header.decode("UTF-8").strip()
    status, mime = header.split()
    response_body = fp.read().decode("UTF-8").strip().split("\n")
    
    return {
        "status": status,
        "mime": mime,
        "body": response_body
    }

a = gemini_get_document(hostname, port, print)
print(hostname, "returned code", a["status"])
print("MIME type of body was", a["mime"]) if a["status"] == "20" else ""
if (a["body"]):
    for i in a["body"]:
        print(i.replace("\\n", "\n"))
