# Load Balancer

Ngày học: 2026-06-25

---

## 1. Khái niệm

### Vấn đề cần giải quyết

Một server có giới hạn — CPU, RAM, băng thông, số connection đồng thời. Khi traffic tăng vượt ngưỡng, cần nhiều server hơn. Nhưng client chỉ biết một địa chỉ.

**Load balancer** đứng trước một pool server và phân phối request đến chúng. Với client, trông như một endpoint duy nhất. Phía sau có thể scale ngang lên hàng trăm server.

```
                    ┌──────────────┐
Client ──────────▶  │ Load Balancer│ ──▶ Server 1
                    │              │ ──▶ Server 2
                    └──────────────┘ ──▶ Server 3
```

### Tại sao không dùng DNS Round Robin?

DNS round robin phân phối ở tầng DNS — client nhận IP khác nhau. Vấn đề:
- Không biết server health: DNS vẫn trả IP server chết cho đến khi TTL hết
- Không có session affinity: request tiếp có thể đến server khác
- Client cache DNS phá vỡ phân phối

Load balancer hoạt động ở tầng connection/request — kiểm soát chi tiết hơn nhiều.

---

## 2. Phân loại Load Balancer

### Layer 4 (Transport Layer)

Hoạt động trên TCP/UDP — route dựa trên IP và port, không nhìn vào nội dung packet.

```
TCP connection từ client → LB → TCP connection đến server
(LB thấy: src IP, dst IP, src port, dst port)
```

- **Nhanh:** xử lý tối thiểu, chỉ routing
- **Mù:** không thể route theo URL, header, hay cookie
- Ví dụ: AWS NLB, HAProxy mode TCP

### Layer 7 (Application Layer)

Hoạt động trên HTTP/HTTPS — có thể đọc nội dung request trước khi route.

```
HTTP request từ client → LB đọc header/URL → route đến server phù hợp
```

- **Thông minh:** route `/api/*` đến API server, `/static/*` đến CDN, `/admin/*` đến admin server
- **Chậm hơn:** phải parse HTTP, terminate TLS
- **Nhiều tính năng hơn:** SSL termination, rewrite request, A/B testing, rate limiting
- Ví dụ: nginx, AWS ALB, Cloudflare, HAProxy mode HTTP

---

## 3. Thuật toán phân phối

### Round Robin

Request phân phối theo vòng: 1→2→3→1→2→3...

```
Request 1 → Server 1
Request 2 → Server 2
Request 3 → Server 3
Request 4 → Server 1
```

Đơn giản nhưng bỏ qua tải thực tế — gửi request đều nhau dù Server 1 đang xử lý query nặng 1 giây còn Server 3 đang rảnh.

### Weighted Round Robin

Server có capacity lớn hơn nhận nhiều request hơn.

```
Server 1 (weight=3): nhận 3 request
Server 2 (weight=1): nhận 1 request
→ 75% traffic đến Server 1
```

Hữu ích khi các server có cấu hình phần cứng khác nhau.

### Least Connections

Route đến server có ít active connection nhất.

```
Server 1: 100 connections
Server 2: 20 connections  ← request tiếp đến đây
Server 3: 80 connections
```

Tốt hơn round robin khi request có thời gian xử lý khác nhau (cái 10ms, cái 5 giây).

### Least Response Time

Route đến server có response time thấp nhất + ít connection nhất. Phiên bản nâng cao của least connections.

### IP Hash

Hash IP của client → luôn route cùng client đến cùng server.

```
hash(client_IP) % num_servers = server_index
```

Cung cấp **session affinity** (sticky session) — cùng client luôn hit cùng server. Hữu ích khi session state lưu local trên server. Vấn đề: phân phối không đều nếu một IP có nhiều client (corporate NAT).

### Consistent Hashing

Phiên bản nâng cao của IP hash. Giảm thiểu re-routing khi thêm/xóa server. Dùng trong distributed cache. (Chi tiết ở Phase 3.)

---

## 4. Health Check

Load balancer liên tục probe server để phát hiện lỗi:

```
LB → GET /health → Server 1 → 200 OK ✅
LB → GET /health → Server 2 → timeout ❌ → xóa khỏi pool
LB → GET /health → Server 3 → 200 OK ✅

(Server 2 recover)
LB → GET /health → Server 2 → 200 OK ✅ → thêm lại vào pool
```

**Passive health check:** phát hiện lỗi từ request thực (5xx, timeout).
**Active health check:** LB chủ động ping `/health` mỗi N giây.

Endpoint `/health` nên kiểm tra toàn bộ stack: DB connection, cache connection — không chỉ trả HTTP 200.

---

## 5. SSL Termination

Layer 7 LB có thể terminate TLS:

```
Client ──[HTTPS]──▶ LB ──[HTTP]──▶ Pool server
         (mã hóa)       (plaintext, mạng nội bộ)
```

Lợi ích:
- Server không phải xử lý TLS overhead (tốn CPU)
- Quản lý certificate tập trung ở một chỗ
- LB có thể đọc/sửa request (cần thiết để routing)

Nhược điểm: traffic giữa LB và server không mã hóa — chấp nhận được trên private VPC, không chấp nhận được trên mạng public. Giải pháp: re-encrypt (end-to-end TLS) hoặc dùng mTLS nội bộ.

---

## 6. High Availability cho bản thân Load Balancer

LB bây giờ là single point of failure. Fix: hai LB chạy active-passive hoặc active-active.

```
                 ┌─── LB Primary (active)
DNS / VIP ───▶  │
                 └─── LB Secondary (standby)
                      (takeover qua VRRP/keepalived nếu primary fail)
```

**Virtual IP (VIP):** IP nổi thuộc về LB nào đang active. Khi primary fail, secondary claim VIP — client reconnect trong suốt.

---

## 7. Load Balancer trong System Design

### Global vs Local Load Balancing

```
User
 |
 ▼
Global LB (DNS-based, Geo DNS) → route đến region gần nhất
 |
 ▼
Regional LB (Layer 7) → phân phối đến server trong region
 |
 ▼
Server pool
```

### Reverse Proxy vs Load Balancer

Hay bị nhầm:
- **Reverse proxy:** trung gian xử lý request thay mặt server. Có thể cache, nén, SSL termination, rewrite request.
- **Load balancer:** phân phối request đến nhiều server.

Reverse proxy có thể bao gồm load balancing. nginx làm cả hai. Về mặt khái niệm khác nhau nhưng thực tế overlap.

---

## 8. Đánh đổi

| | Layer 4 LB | Layer 7 LB |
|---|---|---|
| Tốc độ | Nhanh hơn (không inspect nội dung) | Chậm hơn |
| Routing | IP + port | URL, header, cookie |
| SSL termination | Không | Có |
| Chi phí | Thấp hơn | Cao hơn |
| Use case | TCP throughput, game, streaming | HTTP API, microservices |

### Connection Draining

Khi xóa server khỏi pool (deploy, scale-down), không kill connection ngay:
1. Ngừng gửi request mới đến server
2. Chờ request đang xử lý hoàn thành (grace period, ví dụ 30 giây)
3. Sau đó terminate

Không có draining: user nhận lỗi giữa request khi deploy.

### Thundering Herd

Khi server recover sau lỗi, LB flood ngay với toàn bộ request tồn đọng → server crash lại. Giải pháp: **slow start** — tăng dần traffic đến server mới/vừa recover.

---

## 9. Góc độ phỏng vấn

### Câu hỏi thường gặp

**Q: L4 và L7 load balancer khác nhau thế nào?**
L4 route theo TCP/IP (nhanh, mù). L7 route theo nội dung HTTP (chậm hơn, thông minh — có thể route theo URL, header, cookie, làm SSL termination).

**Q: Dùng thuật toán nào cho stateful application?**
IP hash hoặc consistent hashing để có session affinity. Hoặc chuyển session state ra shared store (Redis) để server nào cũng xử lý được.

**Q: Làm thế nào để LB bản thân có high availability?**
Active-passive pair với Virtual IP. VRRP/keepalived để failover. Hoặc dùng managed LB (AWS ALB) có HA sẵn.

**Q: Connection draining là gì và tại sao cần?**
Xóa server gracefully — ngừng traffic mới nhưng để request đang xử lý hoàn thành. Tránh lỗi khi deploy.

### Điều interviewer cấp Senior kỳ vọng

- Biết sự khác nhau L4 vs L7, khi nào dùng cái nào
- Chọn đúng algorithm cho use case (round robin vs least connections vs IP hash)
- Đề cập LB là SPOF — active-passive HA
- Nhắc đến connection draining cho zero-downtime deployment
- Kết nối kiến trúc global: Geo DNS cho global routing, regional LB cho local distribution

### Lỗi hay mắc

- Thiết kế hệ thống có LB nhưng quên LB cũng là SPOF
- Dùng round robin cho long-running connection (nên dùng least connections)
- Không nhắc đến health check
- Nhầm reverse proxy với load balancer

---

## 10. Bài tập thực hành

Xây L7 load balancer đơn giản bằng Python:

```python
# Milestone 1: round-robin qua 3 HTTP server
# Milestone 2: health check — bỏ qua server unhealthy
# Milestone 3: thuật toán least-connections
```

### Bài tập system design

Thiết kế load balancing layer cho ride-hailing app (như Grab) trong peak hours (đêm giao thừa — traffic gấp 10 lần bình thường). Xử lý thế nào với:
- Traffic spike đột ngột
- Driver location update service (write throughput cao)
- Rider-driver matching service (stateful)
