import socket
import struct
import random

HOST = "127.0.0.1"
PORT = 9000
HEADER_SIZE = 4

def parse_packet(raw: bytes) -> tuple[int, bytes]:
    seq_num = struct.unpack("!I", raw[:HEADER_SIZE])[0]
    data = raw[HEADER_SIZE:]
    return seq_num, data

def make_ack(seq_num: int) -> bytes:
    return struct.pack("!I", seq_num)

def run():
    # Tạo UDP socket và bind vào địa chỉ lắng nghe
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    print(f"[receiver] listening on {HOST}:{PORT}")

    # Seq number tiếp theo mà receiver mong đợi
    expected_seq = 0

    while True:
        # Nhận packet từ sender (tối đa 65535 bytes)
        raw, addr = sock.recvfrom(65535)
        seq_num, data = parse_packet(raw)

        # if seq_num == expected_seq:
        #     # Đúng thứ tự — xử lý và ACK
        #     print(f"[receiver] got seq={seq_num} data={data.decode()!r}")
        #     sock.sendto(make_ack(seq_num), addr)
        #     expected_seq += 1
        # else:
        #     # Sai thứ tự hoặc duplicate — bỏ qua, ACK lại seq cuối hợp lệ
        #     print(f"[receiver] unexpected seq={seq_num}, expected={expected_seq}, discard")
        #     sock.sendto(make_ack(expected_seq - 1), addr)

        if seq_num == expected_seq:
            # Randomly drop 30% of ACKs to simulate packet loss
            # if random.random() < 0.3:
            #     print(f"[receiver] dropping ACK for seq={seq_num} (simulated loss)")
            #     continue
            print(f"[receiver] got seq={seq_num} data={data.decode()!r}")
            sock.sendto(make_ack(seq_num), addr)
            expected_seq += 1
        else:
            print(f"[receiver] unexpected seq={seq_num}, expected={expected_seq}, discard")
            sock.sendto(make_ack(expected_seq - 1), addr)

if __name__ == "__main__":
    run()

