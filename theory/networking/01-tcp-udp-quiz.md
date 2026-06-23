# Quiz: TCP / UDP

Ngày: 2026-06-23

---

## Kết quả

| Câu | Chủ đề | Kết quả |
|-----|--------|---------|
| 1 | TCP vs UDP cho video call | ✅ Đúng (nắm được HOL blocking) |
| 2 | DNS dùng UDP | ⚠️ Một phần — thiếu fallback cases |
| 3 | TIME_WAIT | ❌ Chưa biết |
| 4 | CUBIC vs BBR | ❌ Chưa biết |
| 5 | UDP cho internal service calls | ⚠️ Đúng hướng nhưng chưa đủ sâu |

---

## Câu 1 — TCP vs UDP cho video call

**Câu hỏi:** Bạn đang thiết kế một hệ thống video call như Zoom. Team đề xuất dùng TCP để đảm bảo không mất frame. Bạn phản đối hay đồng ý?

**Trả lời của tôi:** Phản đối. TCP sẽ không mất frame nhưng làm tăng độ trễ. Cơ chế retransmit và ordering là nguyên nhân — frame 5 bị mất, frame 6/7/8 đã đến receiver nhưng phải chờ frame 5, không được chuyển lên application. Đến lúc frame 5 đến thì đã stale. Nên dùng UDP.

**Đánh giá:** ✅ Đúng. Đây là **Head-of-Line Blocking** — TCP buffer các packet đến sau và không deliver lên app cho đến khi packet bị mất đến nơi. Với video call, frame cũ vô nghĩa — thà drop còn hơn delay.

---

## Câu 2 — DNS dùng UDP

**Câu hỏi:** Junior viết DNS resolver mặc định dùng TCP cho mọi query. Có vấn đề gì không?

**Trả lời của tôi:** Có vấn đề. Query/response của DNS vừa trong một packet (thường < 512 byte). UDP tránh được ~1.5 RTT overhead của TCP handshake. DNS fallback sang TCP khi cần.

**Đánh giá:** ⚠️ Đúng nhưng thiếu phần quan trọng: **khi nào DNS fallback sang TCP?**
- Response > 512 byte (DNSSEC, nhiều record) → server set bit `TC=1`, client retry bằng TCP
- Zone Transfer — đồng bộ toàn bộ zone data giữa các DNS server

---

## Câu 3 — TIME_WAIT

**Câu hỏi:** Senior muốn tắt `TIME_WAIT` vì server tích lũy quá nhiều connection ở trạng thái này. Bạn phản đối không?

**Trả lời của tôi:** Không biết.

**Đáp án:** Phản đối. `TIME_WAIT` tồn tại vì 2 lý do:

1. **Đảm bảo ACK cuối đến server:** Nếu ACK cuối của 4-way teardown bị mất, server retransmit FIN. Client cần còn trong `TIME_WAIT` để nhận và gửi lại ACK. Nếu đã đóng hẳn, server nhận RST — kết nối đóng không sạch.

2. **Ngăn packet ma nhiễu kết nối mới:** Nếu mở lại kết nối với cùng tuple `(src IP, src port, dst IP, dst port)`, packet cũ lạc trong mạng có thể bị nhận nhầm là packet mới. `TIME_WAIT = 2 × MSL` (thường 60s) để packet cũ hết hạn.

Giải pháp đúng khi bị tích lũy nhiều TIME_WAIT: dùng `SO_REUSEADDR`, tăng port range, hoặc dùng connection pool.

---

## Câu 4 — CUBIC vs BBR

**Câu hỏi:** Network tắc nghẽn nhẹ, có vài packet drop. Server dùng CUBIC và server dùng BBR phản ứng khác nhau thế nào?

**Trả lời của tôi:** Không biết.

**Đáp án:**

**CUBIC (loss-based):** Coi packet drop = tắc nghẽn → cắt `cwnd` xuống một nửa ngay lập tức, rồi tăng dần lại theo đường cong cubic. Vấn đề: drop đôi khi do wireless noise, không phải tắc nghẽn → cắt tốc độ oan.

**BBR (bandwidth-based):** Không quan tâm packet drop. Liên tục đo bottleneck bandwidth và RTprop (RTT nhỏ nhất). Gửi ở tốc độ phù hợp với băng thông thực đo được. Vài packet drop lẻ tẻ không khiến BBR thay đổi gì.

**Hệ quả:** Trên mạng có loss ngẫu nhiên (WiFi, mobile), BBR giữ throughput cao hơn CUBIC đáng kể. Google deploy BBR trên YouTube, throughput tăng ~4% globally.

---

## Câu 5 — UDP cho internal service calls

**Câu hỏi:** Engineer đề xuất chuyển tất cả internal service-to-service calls từ TCP sang UDP, implement retry ở application layer để tăng tốc. Ý tưởng này tốt không?

**Trả lời của tôi:** Không tốt vì sẽ mất data.

**Đánh giá:** ⚠️ Đúng hướng nhưng chưa đủ — engineer đã nói sẽ implement retry rồi. Trade-off thực sự:

**Có merit khi:** latency cực quan trọng, payload nhỏ/fire-and-forget, internal datacenter network (packet loss gần 0%).

**Vấn đề thực sự khi tự implement reliability:**
- Phải tự viết lại phần lớn TCP: retry, timeout, ordering, deduplication
- Thiếu congestion control → tự gây tắc nghẽn mạng nội bộ
- Không tương thích với load balancer, firewall, monitoring tools
- Debugging khó hơn nhiều so với TCP

**Kết luận:** Với internal calls thông thường — không đáng. TCP overhead trong datacenter là microsecond. Dùng connection pool hoặc HTTP/2 multiplexing trước. UDP custom protocol chỉ hợp lý khi team đủ mạnh và use case cực specific.

---

## Điểm cần ôn lại

1. **TIME_WAIT** — cơ chế, lý do tồn tại, giải pháp khi bị tích lũy nhiều
2. **Congestion control** — phân biệt CUBIC (loss-based) vs BBR (bandwidth-based)
3. **DNS fallback TCP** — trường hợp nào cần (response lớn, zone transfer)
