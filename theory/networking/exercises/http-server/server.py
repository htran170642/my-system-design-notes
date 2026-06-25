import socket
import threading

HOST = "127.0.0.1"
PORT = 8081


def parse_request(raw: str) -> tuple[str, str, dict]:
    lines = raw.split("\r\n")

    # First line: "GET /path HTTP/1.1"
    method, path, _ = lines[0].split(" ")

    # Remaining lines: "Header-Name: value"
    headers = {}
    for line in lines[1:]:
        if ": " in line:
            key, value = line.split(": ", 1)
            headers[key.lower()] = value

    return method, path, headers

def make_response(status: int, body: str) -> bytes:
    status_text = {200: "OK", 404: "Not Found"}[status]
    body_bytes = body.encode()

    # HTTP response format: status line + headers + blank line + body
    response = (
        f"HTTP/1.1 {status} {status_text}\r\n"
        f"Content-Type: text/plain\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
    )
    return response.encode() + body_bytes


def handle_client(conn: socket.socket, addr: tuple):
    print(f"[server] connection from {addr}")

    while True:
        # Receive data until we have the full headers
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = conn.recv(1024)
            if not chunk:
                # Client closed connection
                break
            raw += chunk

        if not raw:
            break

        method, path, headers = parse_request(raw.decode())
        print(f"[server] {method} {path} {raw}")

        if path == "/":
            response = make_response(200, "Hello from raw HTTP server!")
        else:
            response = make_response(404, "Not Found")

        conn.sendall(response)

        # Close if client requests it
        if headers.get("connection") == "close":
            break

    conn.close()
    print(f"[server] connection closed {addr}")


def run():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow reuse of address immediately after restart
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[server] listening on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        # Each client runs on its own thread
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.daemon = True
        thread.start()

if __name__ == "__main__":
    run()
