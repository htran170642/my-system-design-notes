# HTTP / HTTPS / HTTP2 / HTTP3

Ngày học: 2026-06-23

---

## 1. Khái niệm

### HTTP giải quyết vấn đề gì

TCP cho bạn một byte stream đáng tin giữa hai đầu. Nhưng byte stream không có cấu trúc — bạn không biết một message kết thúc ở đâu, data có định dạng gì, hay đầu kia phải làm gì với nó.

HTTP là **application-layer protocol** thêm cấu trúc lên trên TCP:
- Mô hình request/response
- Methods (GET, POST, PUT, DELETE...)
- Headers (metadata về message)
- Status codes (chuyện gì đã xảy ra)
- Content negotiation (body có định dạng gì)

### Timeline tiến hóa

```
HTTP/0.9 (1991) → chỉ GET, không có header
HTTP/1.0 (1996) → headers, status codes, methods — nhưng mỗi request mở TCP mới
HTTP/1.1 (1997) → persistent connection, pipelining, Host header — vẫn HOL blocking
HTTP/2  (2015)  → binary framing, multiplexing, nén header, server push
HTTP/3  (2022)  → QUIC (UDP), loại bỏ TCP HOL blocking
```

Mỗi phiên bản giải quyết bottleneck mà phiên bản trước tạo ra.

---

## 2. HTTP/1.1

### Persistent Connection

HTTP/1.0 mở TCP connection mới cho mỗi request (3-way handshake overhead × mỗi request). HTTP/1.1 mặc định dùng `Connection: keep-alive` — tái sử dụng cùng một TCP connection cho nhiều request.

```
HTTP/1.0:
  [TCP handshake] GET /a → response [TCP close]
  [TCP handshake] GET /b → response [TCP close]

HTTP/1.1:
  [TCP handshake]
  GET /a → response
  GET /b → response
  GET /c → response
  [TCP close]
```

### Pipelining (và tại sao nó thất bại)

HTTP/1.1 thêm pipelining — gửi nhiều request mà không chờ response từng cái. Nhưng response phải trả về **đúng thứ tự** (HOL blocking ở tầng HTTP). Nếu request A chậm, B và C phải chờ. Browser hầu hết đã tắt pipelining.

### Workaround 6 connection

Browser mở tối đa **6 TCP connection song song mỗi domain** để bypass HOL blocking của HTTP/1.1. Đây là lý do domain sharding ra đời (chia asset sang nhiều domain). Cách làm thô nhưng hiệu quả trước khi có HTTP/2.

### Định dạng message

```
Request:
GET /index.html HTTP/1.1
Host: example.com
Accept: text/html
User-Agent: Mozilla/5.0
[dòng trống]
[body tùy chọn]

Response:
HTTP/1.1 200 OK
Content-Type: text/html
Content-Length: 1234
[dòng trống]
[body]
```

Header là **plaintext** — dài dòng, lặp lại mỗi request (cookie, User-Agent, Accept-Encoding gửi lại mỗi lần).

---

## 3. HTTP/2

### Binary Framing Layer

HTTP/2 thay thế text protocol bằng binary format. Mỗi message được chia thành **frame** — những mảnh binary nhỏ được gắn stream ID.

```
HTTP/1.1 (text):              HTTP/2 (binary frame):
GET /a\r\n                    [frame: HEADERS, stream=1, /a]
Host: ...\r\n                 [frame: HEADERS, stream=3, /b]
\r\n                          [frame: DATA,    stream=1, body]
GET /b\r\n                    [frame: DATA,    stream=3, body]
...
```

### Multiplexing

Nhiều request/response xen kẽ nhau trên **một TCP connection** thông qua stream ID. Không cần workaround 6 connection nữa.

```
Client                          Server
  |--[stream 1: GET /a]-------> |
  |--[stream 3: GET /b]-------> |
  |--[stream 5: GET /c]-------> |
  | <--[stream 3: 200 /b]------ |   (b về trước)
  | <--[stream 1: 200 /a]------ |
  | <--[stream 5: 200 /c]------ |
```

### Nén header (HPACK)

HTTP/2 dùng HPACK để nén header. Cả hai phía duy trì một **dynamic table** các header đã thấy trước đó. Thay vì gửi `User-Agent: Mozilla/5.0...` mỗi request, chỉ cần gửi index vào bảng.

Tiết kiệm điển hình: header từ ~800 byte xuống còn ~20-50 byte mỗi request.

### Server Push

Server có thể chủ động gửi resource trước khi client hỏi. Ví dụ: client request `/index.html`, server push luôn `/style.css` và `/app.js` mà không chờ client parse HTML xong.

Thực tế: server push ít khi được dùng đúng cách và đã bị xóa khỏi Chrome 106 (2022). Overhead thường lớn hơn lợi ích.

### HTTP/2 vẫn có TCP HOL Blocking

Multiplexing của HTTP/2 giải quyết HOL blocking ở *tầng application*. Nhưng tất cả stream vẫn dùng chung một TCP connection — nếu một TCP segment bị mất, **tất cả stream đều bị chặn** chờ retransmit. Đây là hệ quả của cơ chế ordering của TCP.

---

## 4. HTTP/3 và QUIC

### Vấn đề cốt lõi của TCP

Để fix TCP HOL blocking phải fix TCP. Nhưng TCP nằm trong OS kernel — thay đổi đòi hỏi cập nhật kernel trên hàng tỷ thiết bị. Chậm.

Insight: **xây transport layer mới ở user space, trên UDP.**

### QUIC

QUIC (ban đầu của Google, chuẩn hóa thành RFC 9000) là transport protocol chạy trên UDP và tự implement:
- Thiết lập kết nối (0-RTT hoặc 1-RTT)
- Reliability và retransmission
- Flow control và congestion control
- **Ordering theo từng stream** — packet mất chỉ chặn stream của nó, không ảnh hưởng stream khác
- TLS 1.3 tích hợp sẵn (mã hóa bắt buộc, không tùy chọn)

```
HTTP/2 trên TCP:              HTTP/3 trên QUIC:
Stream 1 ─┐                  Stream 1 ── độc lập
Stream 3 ──┤── một TCP ──    Stream 3 ── độc lập
Stream 5 ─┘    (HOL)         Stream 5 ── độc lập
                              (mất packet ở stream 3 chỉ chặn stream 3)
```

### 0-RTT Connection Establishment

TLS 1.3 + QUIC = 1-RTT cho kết nối mới (TCP+TLS 1.2 = 3-RTT). Với kết nối lặp lại, QUIC có thể resume với **0-RTT** — gửi data ngay trong packet đầu tiên.

```
TCP + TLS 1.2 (mới):   SYN → SYN-ACK → ACK → TLS hello → ... → data   (3 RTT)
TCP + TLS 1.3 (mới):   SYN → SYN-ACK → ACK → TLS → data              (2 RTT)
QUIC (mới):            Initial → data                                   (1 RTT)
QUIC (resume):         data                                             (0 RTT)
```

### Connection Migration

QUIC định danh kết nối bằng **Connection ID**, không phải tuple `(IP:port)`. Khi bạn chuyển từ WiFi sang 4G (IP thay đổi), QUIC connection vẫn tiếp tục. TCP sẽ bị đứt vì tuple thay đổi.

---

## 5. HTTPS và TLS

### HTTPS thêm gì

HTTPS = HTTP qua TLS (Transport Layer Security). TLS cung cấp:
- **Bảo mật (Confidentiality)** — data được mã hóa, không ai ở giữa đọc được
- **Toàn vẹn (Integrity)** — data không thể bị sửa mà không bị phát hiện (MAC)
- **Xác thực (Authentication)** — server chứng minh danh tính qua certificate (CA chain)

### TLS Handshake (TLS 1.3)

```
Client                          Server
  |--ClientHello (cipher         |
  |   hỗ trợ, key share)-------> |
  |                              |
  | <--ServerHello (cipher       |
  |    được chọn, key share,     |
  |    certificate, Finished)--- |
  |                              |
  |--Finished -----------------> |
  |                              |
  |====== Data mã hóa ==========|
```

TLS 1.3 giảm handshake từ 2 RTT (TLS 1.2) xuống 1 RTT. Bỏ cipher suite yếu, bắt buộc forward secrecy.

### Certificate Chain

```
Root CA (được OS/browser tin tưởng)
  └── Intermediate CA
        └── Server Certificate (example.com)
```

Browser kiểm tra: cert có được CA tin tưởng ký không? Tên domain có đúng không? Có hết hạn không? Có bị thu hồi không (OCSP/CRL)?

### Forward Secrecy

TLS 1.3 bắt buộc dùng **ephemeral key** (ECDHE) — session key được tạo mới cho mỗi kết nối và không lưu lại. Dù private key của server bị lộ sau này, các session cũ vẫn không thể giải mã được.

---

## 6. So sánh và đánh đổi

| | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| Transport | TCP | TCP | QUIC (UDP) |
| HOL Blocking | App + TCP | Chỉ TCP | Không có |
| Multiplexing | Không (workaround 6 conn) | Có (1 conn) | Có (1 conn) |
| Nén header | Không | HPACK | QPACK |
| Mã hóa | Tùy chọn | Tùy chọn (de-facto bắt buộc) | Bắt buộc |
| Connection migration | Không | Không | Có |
| Độ phức tạp triển khai | Đơn giản | Vừa | Cao (UDP có thể bị firewall chặn) |

### Khi nào HTTP/3 không tốt hơn

- Mạng chất lượng cao (datacenter nội bộ): HTTP/2 là đủ, không có lợi gì từ QUIC
- UDP bị firewall/middlebox chặn: HTTP/3 fallback về HTTP/2
- Debug: HTTP/3 khó inspect hơn (mã hóa ở tầng transport)

---

## 7. Góc độ phỏng vấn

### Câu hỏi thường gặp

**Q: HTTP/1.1 và HTTP/2 khác nhau thế nào?**
HTTP/2 thêm binary framing, multiplexing (nhiều request trên một connection), và HPACK nén header. Loại bỏ nhu cầu domain sharding và connection pool hack. Vẫn có TCP HOL blocking.

**Q: Tại sao HTTP/3 xây trên UDP thay vì TCP?**
Để loại bỏ TCP HOL blocking mà không cần chờ thay đổi TCP ở kernel. QUIC implement reliability riêng theo từng stream ở user space — packet mất chỉ chặn stream của nó.

**Q: TLS là gì và tại sao HTTPS cần nó?**
TLS là cryptographic protocol cung cấp bảo mật, toàn vẹn, và xác thực server. Không có nó, bất kỳ ai ở giữa client và server đều có thể đọc hoặc sửa data (man-in-the-middle attack).

**Q: Forward secrecy là gì và tại sao quan trọng?**
Ephemeral key mỗi session nghĩa là các session cũ vẫn an toàn dù private key của server bị lộ sau này. TLS 1.3 bắt buộc điều này.

**Q: HTTP/2 server push khác CDN thế nào?**
Server push chủ động gửi resource từ origin trước khi client hỏi — cho một connection. CDN cache content ở edge server gần người dùng về mặt địa lý, giảm latency cho tất cả mọi người.

### Điều interviewer cấp Senior kỳ vọng

- Giải thích HOL blocking ở cả tầng HTTP lẫn TCP, phiên bản nào fix tầng nào
- Biết HTTP/2 vẫn có TCP HOL blocking
- Giải thích TLS handshake ở mức cao, biết cải tiến của TLS 1.3
- Hiểu Connection ID của QUIC và connection migration
- Kết nối HTTP/2 multiplexing với lý do browser không cần 6 connection nữa

### Lỗi hay mắc

- Nói "HTTP/2 giải quyết HOL blocking" — chỉ giải quyết tầng application, không phải TCP
- Nhầm TLS với HTTPS (HTTPS = HTTP + TLS)
- Không biết HTTP/3 bắt buộc TLS (tích hợp trong QUIC)
- Quên rằng 0-RTT có nguy cơ replay attack (chỉ an toàn cho idempotent request)

---

## 8. Bài tập thực hành

### Bài tập implement

Xây một HTTP/1.1 server tối giản bằng Python từ raw TCP socket:

```python
# Milestone 1: accept TCP connection, parse HTTP request line và headers
# Milestone 2: route GET request, trả về 200/404
# Milestone 3: hỗ trợ keep-alive (parse Content-Length để biết request kết thúc khi nào)
# Milestone 4: đo chênh lệch latency có/không có keep-alive
```

### Bài tập system design

Thiết kế web server phục vụ 10,000 user đồng thời, mỗi người download file 1MB. Dùng HTTP phiên bản nào? Server duy trì bao nhiêu connection? Bottleneck chuyển về đâu?

### Câu hỏi follow-up

1. User báo tải trang chậm. Bạn thấy browser đang mở 6 TCP connection đến domain của bạn. Điều này nói lên điều gì về HTTP version đang dùng, và bạn fix thế nào?
2. CDN của bạn terminate TLS ở edge. Traffic giữa CDN edge và origin server có cần mã hóa không? Tại sao?
3. Tại sao 0-RTT trong QUIC lại nguy hiểm với POST request?
