# System Design: Web Server 10,000 Concurrent Users

Ngày: 2026-06-23

---

## Bài toán

Thiết kế web server phục vụ 10,000 user đồng thời, mỗi người download file 1MB.

---

## Câu 1 — HTTP Version

**Chọn HTTP/2.**

**Tại sao không HTTP/3:**
- Download file 1MB — connection tồn tại đủ lâu, TCP handshake overhead không đáng kể
- Datacenter network ổn định, ít packet loss → TCP HOL blocking hiếm xảy ra
- HTTP/3 phức tạp hơn khi deploy, UDP có thể bị firewall chặn

**HTTP/3 thắng khi:**
- File nhỏ, nhiều request ngắn → 0-RTT quan trọng
- User trên mobile/WiFi không ổn định → QUIC per-stream ordering có lợi
- User di chuyển giữa WiFi và 4G → connection migration

---

## Câu 2 — Số Connection

**10,000 TCP connection đồng thời.**

HTTP/2 dùng 1 TCP connection mỗi client. 10,000 user = 10,000 TCP connection trên server. Mỗi connection duy trì: socket, buffer, sequence number, TLS session.

---

## Câu 3 — Bottleneck

**Bottleneck chính: Network bandwidth.**

```
10,000 users × 1MB = 10GB data transfer đồng thời
Nếu mỗi user download trong 10 giây → cần 1 GB/s bandwidth
```

**Các bottleneck theo thứ tự:**

| Bottleneck | Lý do |
|------------|-------|
| Network bandwidth | 10k × 1MB = lượng data khổng lồ cần đẩy ra |
| Disk I/O | Đọc 10,000 file 1MB đồng thời từ disk |
| RAM | Buffer mỗi connection ~64KB × 10,000 = ~640MB |
| CPU | TLS encryption cho 10,000 connection |

---

## Giải pháp thực tế

```
User → CDN Edge (gần user) → Origin Server
```

**CDN:** Cache file 1MB ở edge — origin server chỉ serve 1 lần, CDN serve 10,000 user. Giảm bandwidth của origin xuống gần 0 với static file.

**Zero-copy với sendfile():** Kernel đọc file và gửi thẳng ra socket, không copy qua user space.
```
Thông thường: disk → kernel buffer → user buffer → socket buffer → network
sendfile():   disk → kernel buffer → socket buffer → network
```

**Async I/O (nginx):** Không tốn 1 thread/connection — 1 thread xử lý hàng nghìn connection bằng event loop, tránh context switch overhead.

---

## Tóm tắt

- HTTP/2 đủ cho static file download — không cần HTTP/3
- 10k users = 10k TCP connections
- Bottleneck: bandwidth → disk I/O → RAM → CPU
- Giải pháp: CDN + sendfile() + async I/O
- Với static file serving: CDN là giải pháp scale đơn giản và hiệu quả nhất
