# TCP / UDP

Ngày học: 2026-06-23

---

## 1. Khái niệm

### Vấn đề cần giải quyết

Internet truyền dữ liệu dưới dạng các **gói tin (packet)** — những mảnh nhỏ đi qua các router một cách độc lập. Nếu không có tầng transport, bạn phải tự xử lý:
- Packet đến không đúng thứ tự
- Packet bị mất giữa đường
- Receiver bị ngập vì sender gửi quá nhanh
- Không biết đầu kia còn sống không

TCP và UDP là hai câu trả lời khác nhau cho câu hỏi: *"Làm thế nào để xây dựng giao tiếp trên nền một mạng vốn không đáng tin?"*

### Tại sao lại có hai protocol?

Đây là sự đánh đổi cốt lõi xuất hiện khắp nơi trong distributed systems: **độ tin cậy vs độ trễ**.

- **TCP** chọn độ tin cậy. Đảm bảo giao hàng, thứ tự, và tính toàn vẹn — nhưng phải trả giá bằng overhead (handshake, ACK, retransmit).
- **UDP** chọn tốc độ. Bắn gói tin xong quên luôn — ứng dụng tự quyết định xử lý mất mát thế nào.

Ứng dụng thực tế:

| Protocol | Dùng bởi |
|----------|---------|
| TCP | HTTP, HTTPS, database, SSH, email (SMTP/IMAP) |
| UDP | DNS, video streaming, game online, VoIP, QUIC (HTTP/3) |

---

## 2. TCP — Transmission Control Protocol

### Đặc điểm cốt lõi

- **Hướng kết nối (connection-oriented):** phải thiết lập kết nối trước khi gửi dữ liệu (3-way handshake)
- **Giao hàng đáng tin (reliable delivery):** packet mất được phát hiện và gửi lại
- **Có thứ tự (ordered):** byte đến theo đúng thứ tự gửi
- **Flow control:** ngăn sender làm ngập receiver
- **Congestion control:** ngăn sender làm ngập mạng

### Bắt tay 3 bước (3-Way Handshake)

```
Client                      Server
  |                            |
  |------- SYN (seq=x) ------> |   "Tôi muốn kết nối, seq của tôi bắt đầu từ x"
  |                            |
  | <----- SYN-ACK (seq=y,    |   "OK, seq của tôi là y, tôi nhận được x của bạn"
  |         ack=x+1) ---------|
  |                            |
  |------- ACK (ack=y+1) ----> |   "Nhận rồi, kết nối mở"
  |                            |
  |====== DỮ LIỆU LƯU THÔNG ==|
```

Tại sao cần 3 bước chứ không phải 2? Vì cả hai phía đều phải chứng minh được rằng mình có thể **gửi VÀ nhận**. Với 2 bước, server không biết SYN-ACK của mình có tới client không.

### Đóng kết nối (4-Way Teardown)

```
Client                      Server
  |                            |
  |------- FIN --------------> |   "Tôi gửi xong rồi"
  | <----- ACK --------------- |   "Nhận được"
  | <----- FIN --------------- |   "Tôi cũng gửi xong"
  |------- ACK --------------> |   "Nhận được, đóng kết nối"
```

Client vào trạng thái `TIME_WAIT` (2 × MSL, thường 60 giây) trước khi đóng hẳn — đảm bảo ACK cuối đến được server nếu bị mất.

### Sequence Number và ACK

Mỗi byte có một sequence number. Receiver gửi ACK báo "tôi nhận đủ đến byte N, gửi tiếp từ N+1." Cơ chế này cho phép:
- Giao hàng đúng thứ tự (buffer packet lộn xộn, deliver theo thứ tự)
- Retransmit (phát hiện ACK bị thiếu qua timeout hoặc duplicate ACK)

### Flow Control — Sliding Window

Receiver quảng bá một **receive window** (rwnd) — bao nhiêu byte nó có thể buffer ngay lúc này. Sender không được có quá `rwnd` byte in-flight (đã gửi nhưng chưa được ACK). Nếu buffer receiver đầy, nó set rwnd=0, tạm dừng sender.

```
Sender                         Receiver
  |                               |
  | [đã gửi & ACK'd] [in-flight]->| rwnd = 64KB
  |                [có thể gửi thêm]
```

### Congestion Control

Flow control lo cho buffer của receiver. Congestion control lo cho **năng lực của mạng** — các router ở giữa bị drop packet vì quá tải.

TCP suy ra tắc nghẽn từ việc mất packet. Các thuật toán chính:

**Slow Start (Khởi động chậm):**
- Bắt đầu với cwnd (congestion window) = 1 MSS
- Double cwnd mỗi RTT cho đến khi đạt ssthresh hoặc mất packet
- Tăng theo hàm mũ

**Congestion Avoidance (Tránh tắc nghẽn):**
- Khi cwnd > ssthresh, tăng 1 MSS mỗi RTT (tuyến tính)

**Khi mất packet (timeout):**
- ssthresh = cwnd / 2
- cwnd = 1 (slow start lại từ đầu)

**Khi mất packet (3 duplicate ACK — Fast Retransmit):**
- ssthresh = cwnd / 2
- cwnd = ssthresh (bỏ qua slow start, nhảy thẳng vào congestion avoidance)

```
cwnd
 ^
 |     /
 |    /
 |   / (slow start, tăng mũ)
 |--/-------- ssthresh
 | /  (congestion avoidance, tuyến tính)
 |/
 +----------------------------> time
```

Thực tế: Linux dùng **CUBIC** (mặc định) hoặc **BBR** (của Google). BBR không phản ứng với mất packet — nó mô hình hóa trực tiếp băng thông của bottleneck.

---

## 3. UDP — User Datagram Protocol

### Đặc điểm cốt lõi

- **Không cần kết nối (connectionless):** không handshake, cứ gửi thôi
- **Không đáng tin (unreliable):** không retransmit, không ACK
- **Không có thứ tự:** packet có thể đến theo bất kỳ thứ tự nào
- **Không có flow/congestion control:** sender có thể làm ngập receiver

### UDP cho bạn những gì

Một lớp mỏng bọc ngoài IP, chỉ thêm:
- Port nguồn / đích (để demultiplex — phân biệt các ứng dụng)
- Độ dài
- Checksum (tùy chọn)

Chỉ vậy thôi. Không state, không overhead, không máy móc quản lý kết nối.

### Khi nào UDP thắng

**Nhạy cảm với độ trễ, chịu được mất mát:**
- Video call: một frame bị drop còn hơn frame cũ tới muộn
- Game: dữ liệu vị trí cũ không dùng được; cần cái mới nhất, nhanh nhất
- DNS: một request/response — handshake của TCP tốn hơn cả query

**Ứng dụng tự implement độ tin cậy:**
- QUIC (HTTP/3) dùng UDP nhưng tự implement connection, retransmit, congestion control ở tầng application — có thêm tự do đổi mới mà không cần thay đổi kernel OS

**Multicast/broadcast:**
- UDP hỗ trợ một-nhiều; TCP chỉ điểm-điểm

---

## 4. So sánh TCP vs UDP

| Thuộc tính | TCP | UDP |
|----------|-----|-----|
| Kết nối | Có (3-way handshake) | Không |
| Độ tin cậy | Đảm bảo | Best-effort |
| Thứ tự | Có | Không |
| Flow control | Có (rwnd) | Không |
| Congestion control | Có (cwnd) | Không |
| Overhead mỗi packet | Cao (header 20B + state) | Thấp (header 8B) |
| Độ trễ | Cao hơn | Thấp hơn |
| Dùng cho | File, web, database | Video, DNS, game |

---

## 5. Đánh đổi và tình huống lỗi

### TCP Head-of-Line Blocking (HOL Blocking)

Nếu packet N bị mất, các packet N+1, N+2, ... bị buffer ở receiver và không được chuyển lên ứng dụng cho đến khi N đến. Đây là hệ quả tất yếu của cơ chế ordering của TCP.

**Tác động:** Trong HTTP/1.1, một response chậm chặn cả connection. HTTP/2 multiplexes nhiều request trên một TCP connection nhưng vẫn chịu HOL blocking ở tầng TCP. HTTP/3 (QUIC over UDP) giải quyết bằng cách implement retransmission theo từng stream.

### Overhead state của TCP

Mỗi TCP connection cần state ở cả hai đầu (sequence number, buffer, timer). Server với 100k kết nối đồng thời phải duy trì 100k state machine. Đây là lý do tích lũy `TIME_WAIT` có thể cạn kiệt port trên server lưu lượng cao.

### UDP Amplification Attack

UDP không có kết nối, nên client có thể giả mạo source IP và gửi request nhỏ đến server — server trả về response lớn đến nạn nhân. DNS amplification là ví dụ điển hình (request 30B → response 3000B). TCP ngăn điều này vì IP giả mạo không bao giờ hoàn thành SYN-ACK.

### Elephant Flows

Các TCP flow tồn tại lâu, băng thông cao (backup database, chuyển file lớn) có thể "chiếm sóng" các flow nhỏ hơn bằng cách chiếm congestion window. ECMP routing và chính sách QoS xử lý vấn đề này ở tầng infrastructure.

---

## 6. Góc độ phỏng vấn

### Câu hỏi thường gặp

**Q: Tại sao HTTP dùng TCP mà không dùng UDP?**
HTTP được thiết kế để truyền tài liệu đáng tin — bạn cần từng byte của HTML/CSS/JS. Gửi lại packet bị mất chấp nhận được; giao nội dung bị hỏng thì không.

**Q: Tại sao DNS dùng UDP?**
Query/response của DNS vừa trong một packet (thường < 512 byte). UDP tránh được ~1.5 RTT overhead của TCP handshake. DNS fallback sang TCP cho response lớn (zone transfer, DNSSEC).

**Q: Chuyện gì xảy ra khi một TCP segment bị mất?**
Receiver gửi duplicate ACK cho byte cuối nhận được. Sau 3 duplicate ACK, sender fast-retransmit segment bị thiếu mà không chờ timeout. Nếu timeout xảy ra trước, sender cũng retransmit và reset congestion window.

**Q: TCP ngăn sender nhanh làm ngập receiver chậm như thế nào?**
Receive window (rwnd): receiver báo cho sender biết capacity buffer của mình. Sender không được có quá rwnd byte in-flight.

**Q: Flow control khác congestion control ở chỗ nào?**
Flow control là end-to-end: ngăn làm ngập *buffer của receiver*. Congestion control nhận biết mạng: ngăn làm ngập *các router ở giữa*. Cả hai đều giới hạn lượng data in-flight nhưng kiểm soát độc lập.

### Điều interviewer cấp Senior kỳ vọng

- Giải thích được *tại sao* 3-way handshake cần 3 bước chứ không phải 2
- Giải thích HOL blocking và QUIC/HTTP3 giải quyết thế nào
- Biết congestion control phản ứng với loss, BBR phản ứng với bandwidth
- Hiểu TIME_WAIT tồn tại vì sao và điều gì xảy ra nếu tắt nó
- Kết nối đặc điểm UDP với quyết định thiết kế thực tế

### Lỗi hay mắc

- Nhầm flow control (rwnd) với congestion control (cwnd)
- Nói "TCP đảm bảo giao hàng" mà không nói thêm "trong phạm vi một kết nối" — nếu kết nối đứt, data in-flight vẫn mất
- Quên rằng checksum UDP là tùy chọn trong IPv4
- Không biết QUIC chạy trên UDP

---

## 7. Bài tập thực hành

### Bài tập implement

Xây dựng một lớp UDP đáng tin đơn giản bằng Python:

```python
# Mục tiêu: implement Stop-and-Wait ARQ trên UDP
# - sender gửi packet kèm sequence number
# - receiver ACK lại
# - nếu không nhận ACK trong timeout, sender retransmit
# - implement trong ~100 dòng để hiểu TCP làm gì cho bạn
```

Milestone 1: Gửi/nhận cơ bản với sequence number
Milestone 2: Timeout và retransmit
Milestone 3: Đo throughput so với raw UDP và TCP

### Bài tập system design

Thiết kế backend cho game multiplayer real-time. Bạn dùng transport layer nào và tại sao? Xử lý thế nào với:
- Packet di chuyển của người chơi bị mất
- Thứ tự các nước đi từ nhiều người chơi
- Server reconciliation trạng thái game

### Câu hỏi follow-up

1. Bạn đang xây dựng app video call. Một user mạng xấu mất 10% packet. Việc chọn TCP hay UDP ảnh hưởng chất lượng cuộc gọi thế nào?
2. Tại sao connection pool của database có thể dùng TCP keepalive? Nó giải quyết vấn đề gì?
3. HTTP/3 dùng QUIC trên UDP. QUIC tự implement lại những gì mà TCP đã cung cấp?

---

## Tóm tắt

TCP = máy móc đảm bảo độ tin cậy được build sẵn trong OS. Trả giá bằng độ trễ, HOL blocking, và chi phí thiết lập kết nối. Lựa chọn đúng khi bạn cần từng byte.

UDP = tốc độ tối giản. Bạn được port và checksum; mọi thứ còn lại là việc của bạn. Đúng cho ứng dụng nhạy cảm với độ trễ, chịu được mất mát, hoặc khi muốn tự build độ tin cậy theo cách riêng.

Bài học sâu hơn: các tính năng của TCP không miễn phí. Mỗi khi dùng TCP, bạn đang trả tiền cho ordering, retransmission, flow control, và congestion control — dù có cần chúng hay không. Hiểu *những tính năng đó tốn bao nhiêu* mới cho phép bạn thiết kế hệ thống biết chọn đúng công cụ.
