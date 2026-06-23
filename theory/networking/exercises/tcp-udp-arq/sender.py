import socket
import struct
import time

HOST = "127.0.0.1"
PORT = 9000
HEADER_SIZE = 4
TIMEOUT = 1.0  # seconds to wait for ACK before retransmit

def make_packet(seq_num: int, data: bytes) -> bytes:
    # Pack sequence number as 4-byte unsigned int (network byte order)
    header = struct.pack("!I", seq_num)
    return header + data

def parse_ack(raw: bytes) -> int:
    # ACK is just a 4-byte sequence number
    return struct.unpack("!I", raw[:HEADER_SIZE])[0]


def send_with_retry(sock: socket.socket, packet: bytes, seq_num: int) -> int:
    # Track how many times we retransmit this packet
    attempts = 0

    while True:
        sock.sendto(packet, (HOST, PORT))
        attempts += 1

        try:
            # Wait for ACK — will raise timeout if nothing arrives
            sock.settimeout(TIMEOUT)
            raw, _ = sock.recvfrom(65535)
            ack = parse_ack(raw)

            if ack == seq_num:
                # Correct ACK received
                return attempts
            # Wrong ACK — loop and retransmit
        except socket.timeout:
            # No ACK within timeout — retransmit
            print(f"[sender] timeout on seq={seq_num}, retrying...")

def run():
    messages = [f"message-{i}" for i in range(10)]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.time()

    for seq_num, msg in enumerate(messages):
        packet = make_packet(seq_num, msg.encode())
        attempts = send_with_retry(sock, packet, seq_num)
        print(f"[sender] seq={seq_num} delivered in {attempts} attempt(s)")

    elapsed = time.time() - start
    print(f"[sender] done. {len(messages)} messages in {elapsed:.3f}s")
    sock.close()


def benchmark():
    # Send 1000 messages and measure throughput
    messages = [f"message-{i:04d}" for i in range(1000)]

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    start = time.time()

    for seq_num, msg in enumerate(messages):
        packet = make_packet(seq_num, msg.encode())
        send_with_retry(sock, packet, seq_num)

    elapsed = time.time() - start
    total_bytes = sum(len(m.encode()) + HEADER_SIZE for m in messages)
    throughput = total_bytes / elapsed / 1024
    print(f"\n[benchmark] {len(messages)} msgs | {total_bytes} bytes | {elapsed:.2f}s | {throughput:.1f} KB/s")
    sock.close()


if __name__ == "__main__":
    # run()
    benchmark()
