# Quiz: Load Balancer

Ngày: 2026-08-27 (lần 1)

---

## Kết quả

| Câu | Chủ đề | Kết quả |
|-----|--------|---------|
| 1 | L4 vs L7 — chọn tầng theo tình huống | ⚠️ Ngược ban đầu, tự sửa sau gợi ý. Ý 2, 3 không trả lời |
| 2 | Sticky session + IP hash khi scale | ❌ Không trả lời |
| 3 | Health check gây cascading failure | ❌ Không trả lời |
| 4 | LB là SPOF — VRRP / VIP / anycast | ❌ Không trả lời |
| 5 | Traffic spike — death spiral, load shedding | ❌ Không trả lời |

**Ghi chú:** Buổi này chủ yếu là giảng giải, không phải kiểm tra. Cần quiz lại
để lấy điểm thật trước khi coi topic này là mastered.

---

## Câu 1 — Chọn L4 hay L7

**Q:** REST API (HTTPS, 20ms, cần route `/v1` vs `/v2`) và video ingest
(RTMP over TCP, connection sống 2-4 tiếng) — mỗi loại dùng LB tầng nào?

**A:** API → **L7** (phải đọc URL path mới route được).
Video ingest → **L4** (RTMP không phải HTTP; connection sống lâu).

**Hai câu hỏi phản xạ khi gặp bài toán chọn tầng:**
1. Có cần đọc nội dung request để quyết định route không? → cần thì L7.
2. Connection sống bao lâu? → sống lâu thì đẩy về L4, tránh state ở LB.

### Vì sao không nhét video ingest vào L7 ALB

1. **Protocol mismatch** — ALB chỉ biết HTTP/HTTPS/gRPC. RTMP là binary
   protocol riêng (handshake C0/C1/C2, chunk stream). ALB không parse nổi.
   Không phải "chậm hơn" mà là "không chạy được".

2. **Chi phí mỗi byte** —
   ```
   L4 (NLB/IPVS): packet vào kernel → rewrite địa chỉ → forward.
                  Data KHÔNG lên userspace. Có thể dùng DSR.
   L7 (ALB):      mọi byte copy lên userspace → parse → buffer → copy xuống.
   ```
   5k conn × 5 Mbps = 25 Gbps xuyên qua userspace của LB. LB thành bottleneck.
   Trên cloud, ALB tính tiền theo LCU (có processed bytes) → hóa đơn khủng.

3. **Connection 4 tiếng phá vỡ vòng đời L7 LB** —
   - Idle timeout ALB mặc định 60s → mất sóng 90s là bị cắt
   - Connection draining bất khả thi: grace period thực tế 30s-5 phút,
     nhưng phải chờ 4 tiếng. Deploy LB = ngắt sóng 5000 streamer.

   Nguyên tắc: **connection sống càng lâu, LB càng phải vô hình.**

Kiến trúc thật luôn tách:
```
DNS ──┬── ALB (L7) ──▶ API pool      (short-lived, cần routing)
      └── NLB (L4) ──▶ Ingest pool   (long-lived, cần throughput)
```

### Thuật toán cho video ingest: Least Connections

Round robin chỉ nhớ "lần trước gửi cho ai" — **không biết** server nào đang
gánh bao nhiêu. Với request 20ms, mất cân bằng tự tan trong mili giây.
Với connection 4 tiếng, mất cân bằng **tích tụ và không tự sửa**:

```
14:00  A: 2000 conn (sống tới 17:00)   B: 2000 conn   C: VỪA THÊM, 0 conn

Round Robin (300 conn mới/giờ):
   A: 2100   B: 2100   C: 100   ← C rỗng suốt nhiều tiếng, A/B vẫn quá tải

Least Connections:
   Mọi conn mới vào C cho tới khi bằng A, B. Không bao giờ đẩy thêm
   tải vào node đang nặng nhất.
```

Nâng cao: số connection chỉ là proxy cho tải thật (stream 4K 20Mbps nặng gấp
10 lần 480p 2Mbps). Hệ thống chín muồi dùng **weighted least connections**
theo `bytes/sec` + CPU do agent trên node báo về.

**Bắt buộc kèm slow start:** server vừa hồi phục có 0 connection → least-conn
dồn toàn bộ traffic vào nó → sập lần hai. Ramp dần 30-60s.

---

## Câu 2 — Sticky session vỡ khi scale

**Q:** Session in-memory trên app server, LB dùng IP hash, scale 3 → 5 server.

### Chuyện gì xảy ra

```
server_index = hash(client_IP) % N     ← N nằm TRONG công thức
```

Đổi `N` là đổi toàn bộ ánh xạ cho **mọi user đang đăng nhập**, ngay lập tức.

```
hash = 94:   94 % 3 = 1 → Server 1 [có session]
             94 % 5 = 4 → Server 4 [RỖNG]  ❌ đăng xuất, mất giỏ hàng
```

Nghịch lý: **hành động cứu hệ thống (scale) chính là hành động phá hỏng UX.**

### Bao nhiêu % bị ảnh hưởng — tính chính xác được

Key giữ nguyên server chỉ khi `h%3 == h%5`. Vì 3×5=15, xét `h%15`:

```
h%15:   0  1  2  3  4  5  6  7  8  9 10 11 12 13 14
h%3:    0  1  2  0  1  2  0  1  2  0  1  2  0  1  2
h%5:    0  1  2  3  4  0  1  2  3  4  0  1  2  3  4
giống?  ✓  ✓  ✓  ✗  ✗  ✗  ✗  ✗  ✗  ✗  ✗  ✗  ✗  ✗  ✗
```

3/15 → **20% giữ được, 80% mất session.**

So sánh: **consistent hashing chỉ remap 40%** — mức tối thiểu về mặt toán học
(2 node mới / 5 node). Modulo làm **gấp đôi lượng xáo trộn cần thiết**.
Đây là lý do consistent hashing tồn tại.

### Điểm yếu chí mạng ở Việt Nam: CGNAT

Viettel/VNPT/FPT NAT hàng chục nghìn thuê bao sau MỘT public IP:

```
50.000 user Viettel 4G → CGNAT → cùng IP 27.68.x.x
→ hash(27.68.x.x) % 5 = 2
→ TẤT CẢ 50.000 user dồn vào Server 2
```

IP hash giả định "1 IP ≈ 1 user" — **sai hoàn toàn** ở VN. Không còn là load
balancing: một server cháy, bốn server ngồi chơi.

Điểm yếu thứ hai: **IP user thay đổi** — chuyển WiFi ↔ 4G, đổi cell → hash đổi
→ mất session. Với mobile app thì xảy ra liên tục.

### Sửa kiến trúc: bỏ state khỏi app server

Mọi cách xử lý ở tầng LB đều là vá tạm. Nguyên nhân gốc: **app server giữ state.**

```
TRƯỚC (stateful)                    SAU (stateless)
User → LB --IP hash--> S1[session]  User → LB --least conn--> S1,S2,S3 → Redis
```

| Vấn đề | Sau khi stateless |
|---|---|
| Scale 3→5 | Không ai mất session |
| Server chết | User chuyển server khác, không hay biết |
| Deploy | Rolling deploy thoải mái |
| CGNAT | Không dùng IP hash nữa |
| Thuật toán LB | Tự do dùng least connections |

**Hai lựa chọn lưu session:**

- **Redis (shared store):** thu hồi tức thì ✅ / thêm dependency + 1 hop ~1ms ❌
- **JWT tự chứa:** không cần lookup ✅ / không thu hồi được trước hạn ❌

Thực tế dùng cả hai: JWT ngắn hạn (5-15 phút) cho auth + Redis giữ refresh
token và giỏ hàng.

**Khi buộc phải sticky** (WebSocket, cache cục bộ nóng): dùng **cookie-based
affinity ở L7** (`AWSALB`, nginx sticky cookie), KHÔNG dùng IP hash. Cookie gắn
với browser, không gắn với IP → CGNAT hết ảnh hưởng.

> "Sticky session không phải giải pháp, nó là triệu chứng — triệu chứng của
> việc app server đang giữ state. Nếu buộc phải sticky thì dùng cookie
> affinity, vì IP không đại diện cho user."

---

## Câu 3 — Health check giết chết hệ thống

**Q:** `/health` gọi `db.execute("SELECT 1")` + `redis.ping()` +
`requests.get(PAYMENT_SVC + "/health")`. Timeout 2s, 2 fail → gỡ khỏi pool.
DB chậm từ 5ms → 3000ms (vẫn sống, chỉ chậm).

### Chuỗi sự kiện

```
T+0s   DB chậm 3s > timeout 2s → FAIL trên CẢ 10 SERVER CÙNG LÚC
T+5s   FAIL lần 2 → LB gỡ cả 10 server
T+5s   POOL RỖNG → mọi user nhận 503 → TOÀN BỘ HỆ THỐNG SẬP
```

```
Sự cố thật:     DB chậm → một số request chậm → degraded
Sự cố thực tế:  DB chậm → gỡ hết server → 100% downtime
```

10 server đó vẫn phục vụ được trang chủ, sản phẩm cache, static asset —
ta đã tự tay vứt bỏ toàn bộ năng lực còn lại.

**Feedback loop:** 1000 server → 200 health check/s đập vào DB đang hấp hối
→ DB càng chậm → càng nhiều fail. Health check tự trở thành nguồn tải.

**Cứu cánh:** AWS ALB **fail-open** — khi TẤT CẢ target unhealthy thì bỏ qua
health check, gửi traffic tới tất cả. HAProxy/nginx tự cấu hình thường KHÔNG có.

### Vấn đề gốc: deep health check anti-pattern

Nhầm lẫn giữa **liveness** và **dependency health**.

> Health check trả lời: "Có nên gửi traffic tới *instance này* thay vì các
> instance khác không?" — đây là câu hỏi **so sánh giữa các instance**.

```
Kiểm tra thứ RIÊNG của instance  → có ý nghĩa phân biệt
   → gỡ server này, 9 server kia gánh tiếp                    ✅
Kiểm tra thứ CHUNG của mọi instance → KHÔNG có ý nghĩa phân biệt
   → hoặc tất cả pass, hoặc tất cả fail → sập toàn bộ cùng lúc ❌
```

Kiểm tra shared dependency biến nó thành **correlated failure** — 10 server
mất tính độc lập, chết như một.

Lỗi thứ hai: **timeout 2s < dependency latency 3s** → report "chết" cho thứ
chỉ đang "chậm". Timeout phải rộng hơn hẳn p99 bình thường.

### Vì sao gọi `/health` của service khác đặc biệt nguy hiểm

**1. Cascade nhiều tầng:** Payment chậm → App /health fail → App bị gỡ →
service gọi App cũng fail → sập dây chuyền. Blast radius đáng lẽ chỉ là
"checkout lỗi", thực tế thành "không ai vào được website".

**2. Fan-out khuếch đại:** 500 server → 100 req/s health check thuần túy đập
vào bank gateway (thứ chắc chắn có rate limit). Bạn đang DDoS đối tác.

**3. Phụ thuộc vòng tròn (chí mạng nhất):**
```
App /health → gọi Payment /health
Payment /health → gọi App /health
Restart cả cụm → DEADLOCK → hệ thống KHÔNG THỂ khởi động lại
```
Kiểu sự cố biến outage 5 phút thành 5 tiếng — vì restart không cứu được.

**Nguyên tắc: health check KHÔNG BAO GIỜ gọi health check của service khác.**

### Chiến lược đúng: 3 endpoint

| Endpoint | Ai gọi | Kiểm tra gì |
|---|---|---|
| `/livez` | orchestrator → **RESTART** | Không check gì. Chỉ `return 200` |
| `/readyz` | **LOAD BALANCER** → **GỠ KHỎI POOL** | Chỉ trạng thái CỤC BỘ: warm-up xong chưa, thread pool còn chỗ, đang shutdown không |
| `/health/deep` | **MONITORING** → **BÁO ĐỘNG** | Dependency thật + latency. LB TUYỆT ĐỐI không gọi |

Mấu chốt: **tách "cái gì hỏng" khỏi "phải làm gì".**
DB chậm → deep check đỏ → báo người trực. `/readyz` vẫn xanh → LB vẫn gửi
traffic → user vẫn xem được trang cache. Hệ thống **degrade từ từ**, không
**sập đột ngột**.

```python
@app.get("/livez")
def livez():
    # Không kiểm tra gì cả. Trả lời được nghĩa là process còn sống.
    return {"status": "alive"}

@app.get("/readyz")
def readyz():
    # Chỉ kiểm tra trạng thái CỤC BỘ của instance này.
    if not app.state.warmup_done:
        return JSONResponse({"status": "warming_up"}, status_code=503)
    if app.state.shutting_down:
        return JSONResponse({"status": "draining"}, status_code=503)
    if db_pool.available_connections() == 0:
        # Pool cạn = riêng instance NÀY quá tải → nhường cho instance khác
        return JSONResponse({"status": "saturated"}, status_code=503)
    return {"status": "ready"}
```

Chi tiết senior nên nói thêm:
- Cache kết quả deep check 5-10s để monitoring không tự tạo tải
- Hysteresis bất đối xứng: gỡ nhanh (2 fail), thêm lại chậm (5 pass) + slow start
- Ngưỡng an toàn: "không gỡ quá 50% pool dù health check nói gì" — quá nửa pool
  fail cùng lúc thì thủ phạm là dependency chung, không phải server

---

## Câu 4 — LB là SPOF

### Sơ đồ đúng

```
                    VIP: 1.2.3.4          ← client CHỈ biết IP này
                         │
          ┌──────────────┴──────────────┐
    ┌─────▼──────┐               ┌──────▼─────┐
    │ LB Primary │◀── VRRP ─────▶│ LB Backup  │
    │ (ACTIVE)   │  heartbeat 1s │ (STANDBY)  │
    │ giữ VIP    │               │ không VIP  │
    └─────┬──────┘               └────────────┘
          ▼  App × 20
```

### Cơ chế failover ở mức gói tin: Gratuitous ARP

```
Bình thường:
  VRRP chia sẻ Virtual IP 1.2.3.4 VÀ Virtual MAC 00:00:5e:00:01:01
  Primary gửi advertisement mỗi 1s (multicast 224.0.0.18)
  ARP router:  1.2.3.4 → 00:00:5e:00:01:01
  CAM switch:  00:00:5e:00:01:01 → Port 5 (LB Primary)

Primary chết:
  T+0s  Ngừng gửi VRRP advertisement
  T+3s  Backup mất 3 chu kỳ → tự tuyên bố MASTER
  T+3s  ★ Backup gửi GRATUITOUS ARP ★
        broadcast "1.2.3.4 hiện ở MAC 00:00:5e:00:01:01"
  T+3s  Switch nhận ở Port 9 → CẬP NHẬT CAM: MAC ảo → Port 9
  T+3s  Packet tới 1.2.3.4 đi ra Port 9 → tới Backup. Phục hồi ~3 giây.
```

Chi tiết đẹp nhất của VRRP: **MAC ảo KHÔNG đổi**, chỉ vị trí vật lý của nó đổi
→ router không cần cập nhật ARP cache, chỉ switch cập nhật CAM → failover nhanh.

**Quan trọng nhất — connection TCP đang mở thì CHẾT HẾT.** TCP state (seq
number, window, buffer) nằm trong RAM của Primary. Backup nhận packet của
connection nó không biết → trả RST → client phải mở lại connection.

> **VRRP failover khôi phục *dịch vụ*, không khôi phục *connection*.**

Muốn giữ connection phải sync state (`pfsync`, HAProxy `stick-table peers`) —
đắt, phức tạp, kênh sync lại thành điểm hỏng mới. Hầu hết chấp nhận mất
connection và đẩy trách nhiệm retry về client.

### Active-Passive vs Active-Active

| | Active-Passive | Active-Active |
|---|---|---|
| Tận dụng | 50% | ~100% |
| Độ phức tạp | Thấp | Cao (state chia sẻ) |
| Failover | 1-3s đứt quãng | Gần như tức thì |
| Sticky session | Đơn giản | Khó |
| Split-brain | Có rủi ro | Rủi ro cao hơn |

**Cái bẫy của active-active:**
```
2 LB active-active, mỗi con 70%. LB-A chết → LB-B nhận 140% → chết luôn.
Mất trắng cả hai. TỆ HƠN active-passive.
```
**Quy tắc: N node active-active thì mỗi node ≤ `(N-1)/N` công suất.**
Với N=2 → tối đa 50% — đúng bằng active-passive. Lợi ích thật chỉ xuất hiện
khi N lớn (10 node → mỗi node chạy được 90%).

**Split-brain:** mạng giữa 2 LB đứt nhưng cả hai còn sống → cả hai giành VIP
→ ARP đánh nhau. Chống bằng fencing/STONITH, quorum số lẻ, hoặc heartbeat
qua đường vật lý riêng.

**Chọn gì:** dưới ~10 Gbps thì active-passive gần như luôn đúng. Active-active
dành cho quy mô một LB không kham nổi — và lúc đó thường đã dùng anycast.

### Sao không để 2 IP vào DNS cho client tự chọn?

**Phản đối:**
- **DNS không biết health.** LB-A chết lúc 10:00 nhưng resolver đã cache TTL
  300 → 5 phút gửi user vào một cái xác, không rút lại được.
- **Client cư xử không lường trước được.** Browser có Happy Eyeballs (RFC 8305)
  — thử IP thứ hai sau ~250ms, khá tốt. Nhưng `curl` cũ chỉ thử IP đầu; JVM
  cache DNS vĩnh viễn ở một số cấu hình. **Bạn không kiểm soát được client.**
- **Phân phối không đều** — một ISP lớn cache 1 IP → toàn bộ khách đổ vào 1 LB.

**Ủng hộ — các hệ lớn nhất ĐÚNG LÀ làm vậy, nhờ hai thứ:**

**1. Anycast BGP** (Cloudflare, Google):
```
CÙNG MỘT IP 1.1.1.1 announce qua BGP từ 300 datacenter.
Client HN → POP Singapore.  Client London → POP London.

POP Singapore chết → ngừng announce prefix
→ router toàn cầu hội tụ ~30s → traffic chảy sang POP gần thứ hai.
KHÔNG cần đổi DNS. KHÔNG chờ TTL.
Failover nằm ở TẦNG ĐỊNH TUYẾN, không ở tầng DNS.
```
IP không bao giờ đổi, chỉ **đường đi tới nó** đổi → tránh được DNS caching.

**2. DNS thông minh + client retry đúng chuẩn:** nhiều bản ghi A, TTL 30-60s,
health check chủ động rút IP chết, cộng Happy Eyeballs phía client.

> "DNS một mình không đủ vì nó không biết health và bạn không kiểm soát được
> cache lẫn client — TTL 300 nghĩa là 5 phút gửi user vào một cái xác. Trong
> một datacenter tôi dùng VIP + VRRP: failover 3s, client không hay biết. Lên
> quy mô nhiều khu vực thì đúng cách là anycast BGP, chuyển failover xuống
> tầng định tuyến thay vì phụ thuộc TTL. VRRP lo LB chết, anycast lo cả
> datacenter chết."

---

## Câu 5 — Traffic spike: bán vé concert

**Q:** 800k user, 2 triệu request/10s. Autoscaling cần 90s/instance.
Server OOM, restart xong lại chết ngay.

### Ba vòng lặp chết chạy đồng thời

**Vòng 1 — Tái phân phối tải:**
```
30 server ở 95%. S1 chết → 3.3% chia cho 29 con → 98% → S2 chết → 101%
→ S3, S4 chết cùng lúc... TỐC ĐỘ CHẾT TĂNG DẦN. Không có điểm dừng tự nhiên.
```

**Vòng 2 — Cold start + Least Connections = bẫy chết người:**
```
Server vừa restart:  cache RỖNG → mọi request xuống DB
                     connection pool CHƯA MỞ → bắt tay TCP+TLS từng cái
                     JIT chưa nóng → chậm 5-10 lần
                     → nó là server YẾU NHẤT cụm.

LB (least conn) thấy 0 connection → "con này rảnh nhất!"
→ DỒN TOÀN BỘ REQUEST MỚI VÀO SERVER YẾU NHẤT
→ OOM sau 5 giây → restart → lại 0 conn → lại bị dồn → VÒNG LẶP VÔ TẬN
```
→ **Slow start không phải tính năng phụ, nó BẮT BUỘC.**

**Vòng 3 — Khuếch đại do retry:**
```
1 request gốc → user F5 + app retry 3 + SDK retry 2 = 6 request thật
Tải hiệu dụng gấp 5-10 lần tải thật.
```
Và công việc vô ích:
```
19:00:00 request vào queue → 19:00:30 client TIMEOUT, bỏ đi, retry
→ 19:00:45 server xử lý xong, gửi cho connection ĐÃ ĐÓNG. 100% vứt đi.
```
Đây là **metastable failure**: traffic về bình thường hệ thống vẫn không tự
hồi phục vì đang bận tiêu hóa hàng đợi rác. Phải can thiệp thủ công.

### Công cụ ở tầng LB

**1. Giới hạn connection tới mỗi backend (quan trọng nhất)**
```
HAProxy:  server app1 10.0.0.1:8080 maxconn 100
nginx:    server 10.0.0.1:8080 max_conns=100;
```
> **Hàng đợi ở LB thì rẻ (vài KB), hàng đợi ở app server thì đắt**
> (thread, buffer, DB connection — chính những thứ gây OOM). Chặn Vòng 1.

**2. Load shedding** — `if queue_depth > threshold: return 503` (~0ms).
Hệ thống quá tải chỉ có hai lựa chọn: **từ chối một phần, hoặc chết toàn bộ.**

**3. Slow start** — `slowstart 60s` / `slow_start=30s`. Chặn Vòng 2.

**4. Timeout hàng đợi** — `timeout queue 5s`. Client đã timeout ở giây 30,
xử lý ở giây 45 là lãng phí thuần túy. Chặn Vòng 3.

**5. Rate limiting ở biên** (Cloudflare) — chặn bot, giảm khuếch đại retry
trước khi chạm hạ tầng.

**6. `/readyz` báo bão hòa** — server tự nói "tôi đầy" → LB gỡ tạm → tự điều tiết.

**7. Circuit breaker + `Retry-After`.**

### Autoscaling không cứu được — giải pháp thật

```
Traffic tăng vọt: 10 giây.  Instance sẵn sàng: 90 giây.  ĐI SAU 80 GIÂY.
```
**Autoscaling là công cụ phản ứng; đây là sự kiện biết trước.** Dùng sai khái niệm.

**1. Pre-scaling (bắt buộc):** 19:00 scale 30 → 300 instance, warm-up đầy đủ.
Chi phí vài trăm đô, so với doanh thu + báo chí + niềm tin của một lần mở bán
thất bại.

**2. Phòng chờ ảo (Virtual Waiting Room) — kiến trúc đúng:**
```
800.000 user → PHÒNG CHỜ ở edge (Cloudflare Waiting Room)
               "Bạn ở vị trí 47.293 — chờ khoảng 12 phút"
               cấp token 2.000 user/phút
             → Hệ thống thật (30 instance là ĐỦ)

TRƯỚC: 2 triệu request/10s   → không hệ thống nào sống nổi
SAU:   2.000 request/phút    → 30 server thoải mái
```
Không tăng năng lực — **định hình lại nhu cầu**. Đây là **admission control**,
cách Ticketmaster và đăng ký vaccine đều làm. Và trung thực hơn với user.

**3. Kiến trúc hấp thụ đỉnh:** cache trang pre-sale ở edge (800k F5 không chạm
origin); kho vé trong Redis không Postgres (decrement nguyên tử ~50k ops/s);
đặt vé ghi vào Kafka xử lý async → "đã giữ chỗ, đang xác nhận".
**Postgres không nên nằm trên đường đi của 2 triệu request — nó nên nằm ở
cuối một hàng đợi.**

### 500k lỗi ngay vs 800k chờ 45s rồi timeout?

**Từ chối nhanh. Dứt khoát.**

```
Từ chối NHANH:  300.000 mua được vé. 500.000 biết ngay, vào phòng chờ.
                Hệ thống sống.
Từ chối CHẬM:   0 người mua được. 800.000 chờ 45s rồi lỗi. Hệ thống sập.
                100% tài nguyên đổ vào việc bị vứt đi.
```
Từ chối chậm **thua ở cả hai mặt**: phục vụ ít người hơn VÀ làm mọi người bực hơn.

**Hàng đợi không tạo ra năng lực:** hệ thống 10k req/s nhận 200k req/s — thêm
hàng đợi vẫn 10k req/s, chỉ có độ trễ tăng vô hạn. Nó chuyển "thất bại nhanh"
thành "thất bại chậm" và đốt thêm RAM.

**Timeout gây bão retry, 503 thì không:** `503 + Retry-After: 60` → client biết
chờ bao lâu. Từ chối nhanh **kèm thông tin** là cách duy nhất phá vòng khuếch đại.

**Cách trả lời hay nhất là bác bỏ câu hỏi:**
> "Tôi chọn từ chối nhanh, nhưng không chấp nhận đây là hai lựa chọn duy nhất.
> Cả hai đều là thất bại — một cái rẻ, một cái đắt. Lựa chọn thứ ba là
> admission control: phòng chờ ở edge, cho user biết vị trí thật và thời gian
> chờ thật. User không nhận lỗi, cũng không chờ trong vô định — họ nhận sự
> thật. Backend chỉ thấy đúng lượng traffic nó kham nổi. Nếu buộc phải chọn
> trong hai cái ban đầu thì từ chối nhanh, luôn luôn — nhưng câu hỏi đúng là:
> tại sao ta lại để bản thân rơi vào tình huống chỉ còn hai lựa chọn đó?"

> **Khi hệ thống quá tải, thất bại nhanh và trung thực. Đừng bao giờ để user
> chờ một thứ bạn biết chắc sẽ không tới.**

---

## Điểm cần nhớ cho quiz lần 2

1. **Chọn L4/L7:** hỏi 2 câu — cần đọc nội dung request không? connection sống
   bao lâu? Sống lâu → L4, tránh state ở LB.
2. **Round robin tệ khi connection sống lâu** — mất cân bằng tích tụ, không tự sửa.
   Least connections + **slow start** (bắt buộc, nếu không thì cold start = tự sát).
3. **`hash % N`: đổi N = 80% user bị remap** (3→5). Consistent hashing chỉ 40%.
4. **CGNAT ở VN phá nát IP hash** — 1 IP ≠ 1 user. Sticky thì dùng **cookie
   affinity**, không dùng IP hash.
5. **Health check chỉ kiểm tra thứ RIÊNG của instance**, không kiểm tra shared
   dependency. Không bao giờ gọi `/health` của service khác.
6. **3 endpoint:** `/livez` (restart) — `/readyz` (LB gỡ pool) — `/health/deep`
   (báo động cho người).
7. **VRRP failover = gratuitous ARP** cập nhật bảng CAM của switch. Khôi phục
   **dịch vụ**, không khôi phục **connection**.
8. **Active-active: mỗi node ≤ (N-1)/N công suất**, nếu không thì failover =
   mất trắng cả hai.
9. **Anycast BGP** chuyển failover xuống tầng định tuyến → không phụ thuộc TTL.
10. **Quá tải thì thất bại nhanh.** Hàng đợi không tạo ra năng lực. Sự kiện biết
    trước thì **pre-scale + admission control**, không trông vào autoscaling.
