# WebSocket

Session date: 2026-08-27

> Cùng cách viết với bài CDN: gọn, kết bằng checklist tự kiểm tra.
> Xem `mock-interview-01-networking.md` để biết vì sao đổi cách viết.

---

## 1. Vấn đề nó giải quyết

HTTP có một giả định nằm sâu trong thiết kế: **client hỏi, server đáp**.
Server không có cách nào chủ động nói chuyện trước.

Nhưng rất nhiều hệ thống cần điều ngược lại — chat, thông báo, giá cổ phiếu,
vị trí tài xế, cộng tác thời gian thực. Ba cách chữa cháy trước khi có WebSocket:

```
POLLING — hỏi lại mỗi 5 giây
   Client: "có gì mới không?" → "không"   (lặp lại 720 lần/giờ)
   ❌ Độ trễ trung bình = 1/2 chu kỳ
   ❌ 99% request là vô ích
   ❌ Mỗi request mang ~700 byte header để nhận về "không"

LONG POLLING — hỏi rồi server GIỮ LẠI không trả lời
   Client hỏi → server im lặng giữ connection → có tin thì trả lời ngay
              → client lập tức hỏi lại
   ✅ Độ trễ gần như 0
   ❌ Mỗi tin nhắn = một chu kỳ HTTP đầy đủ

SSE (Server-Sent Events) — một connection HTTP, server đẩy liên tục
   ✅ Đơn giản, TỰ ĐỘNG RECONNECT, chạy trên HTTP thuần
   ❌ MỘT CHIỀU (server → client)
   ❌ Chỉ text
```

**WebSocket:** một connection TCP duy nhất, **hai chiều**, giữ mở lâu dài,
overhead mỗi tin nhắn chỉ **2-14 byte** thay vì ~700 byte header HTTP.

---

## 2. Bắt tay — bắt đầu bằng HTTP rồi "lột xác"

```http
CLIENT:
GET /chat HTTP/1.1                    ← là HTTP thật, GET bình thường
Host: example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13

SERVER:
HTTP/1.1 101 Switching Protocols      ← mã 101, hiếm gặp
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
                      └─ base64(sha1(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))
```

Sau dòng `101`, **connection TCP không còn là HTTP nữa**. Cùng một ống,
giao thức khác hẳn.

**Vì sao mượn HTTP để mở đầu?** Để đi lọt qua thế giới thực: dùng port 80/443,
tái sử dụng TLS, và quan trọng nhất — **proxy/firewall doanh nghiệp cho qua**
vì chúng thấy một request HTTP hợp lệ. Đúng vấn đề *ossification* ở phần HTTP/3.

`Sec-WebSocket-Accept` không phải để bảo mật — nó chứng minh server **thật sự
hiểu** WebSocket, tránh việc một server HTTP thường vô tình trả 101.

---

## 3. Frame — và câu hỏi bẫy về masking

```
Mỗi frame:  [FIN][opcode][MASK][độ dài][masking-key][payload]
                    │                        │
                    │                        └─ 4 byte, CHỈ có ở chiều client→server
                    └─ 0x1 text  0x2 binary  0x8 close  0x9 ping  0xA pong
```

**Vì sao client BẮT BUỘC mask payload còn server thì không?**

Không phải để bảo mật (masking key gửi kèm ngay trong frame — ai đọc được cũng
giải được). Lý do là **chống cache poisoning ở proxy trung gian**:

```
Không có masking:
  Kẻ tấn công điều khiển nội dung client gửi
  → tự soạn payload trông y hệt một request HTTP hợp lệ
  → proxy cũ (không hiểu WebSocket) đọc nhầm thành request HTTP
  → cache một response độc hại cho URL của người khác

Có masking (XOR với khoá ngẫu nhiên mỗi frame):
  Kẻ tấn công không đoán được byte thực tế trên đường truyền
  → không chế tạo được request HTTP giả
```

Server → client không cần mask vì server không bị client điều khiển nội dung.

`ping`/`pong` là opcode có sẵn trong chuẩn — dùng làm heartbeat (mục 6).

---

## 4. Chọn cái nào — bảng quyết định

| | Polling | Long Polling | SSE | WebSocket |
|---|---|---|---|---|
| Chiều | 1 (kéo) | 1 (kéo) | **1** (đẩy) | **2 chiều** |
| Độ trễ | ~½ chu kỳ | thấp | thấp | thấp nhất |
| Overhead/tin | ~700B | ~700B | ~10B | **2-14B** |
| Tự reconnect | — | thủ công | **có sẵn** | **tự viết** |
| Qua proxy cũ | ✅ | ✅ | ✅ | ⚠️ đôi khi bị chặn |
| Nhị phân | ✅ | ✅ | ❌ | ✅ |

> **Câu hỏi phải tự hỏi TRƯỚC TIÊN: có thật sự cần HAI CHIỀU không?**
>
> Thông báo, dashboard, tiến độ, feed — chỉ cần đẩy một chiều.
> **SSE đơn giản hơn nhiều**, tự reconnect sẵn, không bị proxy chặn.
> Rất nhiều hệ thống dùng WebSocket trong khi SSE là đủ và ít lỗi hơn hẳn.
>
> Chat, game, cộng tác realtime, ra lệnh hai chiều → WebSocket.

---

## 5. Mở rộng quy mô — bài Load Balancer quay lại

**Vấn đề 1 — chọn tầng LB.** Connection sống hàng giờ. Hai câu hỏi phản xạ:
*cần đọc nội dung không? sống bao lâu?* → **L4**, hoặc L7 có hỗ trợ WebSocket
riêng. Đừng nhét vào ALB HTTP thường.

**Vấn đề 2 — connection là STATE, và state nằm sai chỗ:**

```
User A nối vào Server 1.  User B nối vào Server 3.
A gửi tin cho B.
   → Server 1 KHÔNG có connection của B. Nó không gửi được.
```

Cần **backplane pub/sub**:

```
       ┌── Server 1 ──┐
User A ┤              ├── Redis Pub/Sub ── Server 3 ── User B
       └──────────────┘   (hoặc Kafka, NATS)

Server 1 publish vào kênh "user:B"
Server 3 đang subscribe kênh đó → đẩy xuống connection của B
```

Kèm **connection registry**: `user_id → server_id` lưu trong Redis.

**Vấn đề 3 — chi phí mỗi connection:**

```
1 connection ≈ socket + buffer gửi/nhận ≈ 10-50 KB
1 TRIỆU connection ≈ 10-50 GB RAM

Bắt buộc chỉnh:
   ulimit -n              (mặc định 1024 file descriptor)
   net.core.somaxconn     (hàng đợi accept)
   ip_local_port_range    (phía LB — đúng bài toán cạn ephemeral port ở TIME_WAIT)

Và BẮT BUỘC dùng EVENT LOOP (epoll/kqueue), không phải thread mỗi connection.
1 triệu thread = tự sát. Đây là bài toán C10K/C10M.
```

**Vấn đề 4 — deploy:**

```
Rolling deploy giết pod → TẤT CẢ connection trên pod đó đứt cùng lúc
→ hàng chục nghìn client reconnect ĐỒNG THỜI
→ THUNDERING HERD (lần thứ ba xuất hiện trong lộ trình này)

Chống: client backoff có JITTER (backoff đều thì tất cả vẫn đồng bộ với nhau)
       + drain từ từ + slow start
```

---

## 6. Vấn đề vận hành thực tế

**Idle timeout giết connection âm thầm.** LB, proxy, NAT nhà mạng đều tự dọn
connection không có traffic (thường 60s). Chat lúc 3 giờ sáng không ai nhắn →
connection bị cắt, **cả hai bên đều không biết**. Bắt buộc `ping`/`pong` mỗi
~30 giây. Không phải tuỳ chọn.

**IP đổi là connection chết.** WiFi → 4G → 4-tuple đổi → TCP chết. Chính xác
vấn đề mà **QUIC connection migration** giải quyết (đã học ở HTTP/3). Với
WebSocket phải tự xử: reconnect + **số thứ tự tin nhắn** để phát lại phần lỡ.

**Backpressure — cái bẫy làm sập server:**
```
Client mạng yếu, đọc chậm. Server vẫn bơm tin nhắn.
→ hàng đợi gửi phình to → RAM cạn → OOM → CẢ SERVER SẬP
   kéo theo hàng chục nghìn connection của người khác

Phải: giới hạn hàng đợi gửi. Vượt ngưỡng → bỏ tin cũ, hoặc ngắt client đó.
Hy sinh một người để cứu tất cả — đúng tinh thần load shedding.
```

**Xác thực bị vướng:** API WebSocket của trình duyệt **không cho set header
tuỳ ý** — không gắn được `Authorization: Bearer ...`. Ba cách:
- Token trong query string → ❌ **bị ghi vào access log của mọi proxy**
- Cookie → được, nhưng dính CSRF, cần kiểm tra header `Origin`
- ✅ Nối trước, **tin nhắn đầu tiên là token**, chưa xác thực thì chưa cho làm gì

**Luôn dùng `wss://`** (WebSocket over TLS). `ws://` thường bị proxy trung gian
can thiệp làm hỏng.

---

## 7. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- Cân nhắc **SSE trước** thay vì mặc định chọn WebSocket
- Nhận ra connection là **state** → cần backplane pub/sub + registry
- Nhắc **heartbeat** (không có thì connection chết âm thầm)
- Nhắc **backpressure** — rất ít ứng viên nói tới, nói được là nổi bật
- Biết deploy/reconnect gây thundering herd → backoff có jitter

**Sai lầm thường gặp:**
- Vẽ WebSocket sau một LB L7 HTTP thường
- Quên rằng scale ngang cần backplane — tưởng cứ thêm server là xong
- Không có heartbeat
- Dùng WebSocket cho thứ chỉ cần một chiều

---

## 8. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. Bắt tay WebSocket bắt đầu bằng giao thức gì? Mã trạng thái nào?
2. Vì sao mượn HTTP để mở đầu thay vì tự định nghĩa giao thức riêng?
3. Vì sao client bắt buộc mask payload còn server thì không?
4. Khi nào chọn SSE thay vì WebSocket?
5. User A ở Server 1, User B ở Server 3 — A nhắn cho B thế nào?
6. Vì sao bắt buộc phải có ping/pong?
7. Backpressure là gì, không xử lý thì hỏng như thế nào?
8. Deploy lại cụm WebSocket gây hiện tượng gì? Đã gặp ở những buổi nào?

---

## 9. Bài tập

**Implementation:** viết một chat server WebSocket bằng Python (`asyncio` +
`websockets`) — M1 broadcast một phòng; M2 heartbeat ping/pong + dọn connection
chết; M3 nhiều phòng + registry `user → connection`; M4 giới hạn hàng đợi gửi
(backpressure) và ngắt client đọc quá chậm.

**System design:** thiết kế hệ thống chat cho 10 triệu user đang online.
Bao nhiêu server? Định tuyến tin nhắn ra sao? Lưu lịch sử thế nào? Xử lý user
offline? Deploy mà không ngắt hết connection bằng cách nào?
