import socket
import time

HOST = "127.0.0.1"
PORT = 8081
REQUESTS = 50


def send_request(sock: socket.socket, keep_alive: bool) -> str:
    connection_header = "keep-alive" if keep_alive else "close"
    request = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {HOST}:{PORT}\r\n"
        f"Connection: {connection_header}\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode())

    # Read until we find end of headers + body
    raw = b""
    while True:
        chunk = sock.recv(1024)
        if not chunk:
            break
        raw += chunk
        if b"\r\n\r\n" in raw:
            # Parse Content-Length to know when body ends
            headers, body = raw.split(b"\r\n\r\n", 1)
            for line in headers.split(b"\r\n"):
                if line.lower().startswith(b"content-length"):
                    length = int(line.split(b": ")[1])
                    if len(body) >= length:
                        return raw.decode()


def benchmark_no_keepalive() -> float:
    # Open a new TCP connection for every single request
    start = time.time()
    for _ in range(REQUESTS):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
        send_request(sock, keep_alive=False)
        sock.close()
    return time.time() - start


def benchmark_keepalive() -> float:
    # Reuse one TCP connection for all requests
    start = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    for _ in range(REQUESTS):
        send_request(sock, keep_alive=True)
    sock.close()
    return time.time() - start


if __name__ == "__main__":
    print(f"Benchmarking {REQUESTS} requests to {HOST}:{PORT}\n")

    t1 = benchmark_no_keepalive()
    print(f"No keep-alive: {t1:.3f}s  ({REQUESTS/t1:.1f} req/s)")

    t2 = benchmark_keepalive()
    print(f"Keep-alive:    {t2:.3f}s  ({REQUESTS/t2:.1f} req/s)")

    print(f"\nSpeedup: {t1/t2:.1f}x faster with keep-alive")
