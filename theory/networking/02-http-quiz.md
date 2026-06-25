# Quiz: HTTP / HTTPS / HTTP2 / HTTP3

Ngày: 2026-06-23 (lần 1 — cần quiz lại)

---

## Kết quả

| Câu | Chủ đề | Kết quả |
|-----|--------|---------|
| 1 | HTTP/1.1 6-connection workaround | ❌ Chưa biết |
| 2 | TCP HOL blocking trong HTTP/2 | ❌ Chưa biết |
| 3 | TLS 1.2 vs TLS 1.3 RTT | ❌ Chưa biết |
| 4 | HTTP/3 firewall fallback | ❌ Chưa biết |
| 5 | Latency comparison HTTP/1.1/2/3 | ❌ Chưa biết |

---

## Câu 1 — HTTP/1.1 6-connection workaround

**Q:** Browser tải 30 file qua HTTP/1.1 xử lý thế nào?

**A:** Browser mở tối đa **6 TCP connection song song mỗi domain**. 30 file chia thành 5 batch, mỗi batch 6 file song song. Đây là lý do domain sharding ra đời — tách asset sang nhiều subdomain để có thêm 6 connection. HTTP/2 multiplexing loại bỏ hoàn toàn workaround này.

---

## Câu 2 — TCP HOL Blocking trong HTTP/2

**Q:** HTTP/2 vẫn còn HOL blocking nào?

**A:** **TCP HOL blocking.** HTTP/2 giải quyết app-layer HOL blocking bằng multiplexing, nhưng tất cả stream vẫn dùng chung 1 TCP connection. Nếu 1 TCP segment mất → toàn bộ stream bị block chờ retransmit. HTTP/1.1 với 6 connection độc lập thực ra ít bị ảnh hưởng hơn trong trường hợp này. HTTP/3 (QUIC) fix bằng per-stream ordering.

---

## Câu 3 — TLS 1.2 vs TLS 1.3

**Q:** Upgrade TLS 1.2 → 1.3 cải thiện gì?

**A:** Giảm 1 RTT cho new connection:
```
TLS 1.2: TCP (1 RTT) + TLS (2 RTT) = 3 RTT tổng
TLS 1.3: TCP (1 RTT) + TLS (1 RTT) = 2 RTT tổng
```
TLS 1.3 gộp certificate + Finished vào 1 round trip. Thêm **0-RTT** cho repeat connection — data gửi ngay trong packet đầu. Nhược điểm 0-RTT: replay attack risk, chỉ dùng cho idempotent request (GET).

---

## Câu 4 — HTTP/3 Firewall Fallback

**Q:** UDP bị firewall chặn, HTTP/3 xử lý thế nào?

**A:** HTTP/3 tự động **fallback về HTTP/2/HTTP/1.1 (TCP)**. Server gửi header `Alt-Svc: h3=":443"` để báo hỗ trợ HTTP/3. Browser thử HTTP/3 trước, nếu bị block thì dùng TCP. ~30% traffic thực tế không qua được HTTP/3 do firewall. Luôn giữ HTTP/2 fallback khi deploy HTTP/3.

---

## Câu 5 — Latency Comparison (RTT 200ms)

**Q:** 5 API calls với HTTP/1.1, HTTP/2, HTTP/3 — khác nhau thế nào?

**A:**

| | Lần đầu | Lần sau |
|--|--|--|
| HTTP/1.1 (tuần tự) | ~1600ms | ~1000ms |
| HTTP/2 | ~400ms | ~200ms |
| HTTP/3 | ~400ms | ~200ms |

Bài học: bước nhảy lớn nhất là **HTTP/1.1 → HTTP/2** (multiplexing), không phải HTTP/2 → HTTP/3. Với high-latency network, multiplexing quan trọng hơn QUIC.

---

## Điểm cần nhớ cho quiz lần 2

1. HTTP/1.1 → 6 parallel connections per domain (không phải 1 connection)
2. HTTP/2 vẫn có TCP HOL blocking (chỉ fix app layer)
3. TLS 1.3 = tiết kiệm 1 RTT + 0-RTT cho repeat (cẩn thận replay attack)
4. HTTP/3 fallback TCP khi UDP bị chặn (`Alt-Svc` header)
5. HTTP/1.1→HTTP/2 là bước nhảy lớn nhất về latency
