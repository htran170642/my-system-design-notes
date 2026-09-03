# Mock Interview 01 — Networking (tổng hợp)

Ngày: 2026-08-27
Phạm vi: TCP/UDP · HTTP/HTTPS/H2/H3 · DNS · Load Balancer
Kết quả: **17.5 / 60 — 29%** (ngưỡng Senior: 70%) — **CHƯA ĐẠT**

---

## Bảng điểm

| Câu | Chủ đề | Điểm | Nhận xét |
|---|---|---|---|
| 1 | Enter → pixel đầu tiên | 0.5/10 | Nói được 2/6 giai đoạn (DNS, TLS). Thiếu hẳn TCP handshake, không có khái niệm round-trip |
| 2 | Debug `connection refused` | 0/10 | Chọn A (firewall). Câu phụ xác nhận nhầm RST với im lặng |
| 3 | TIME_WAIT / cạn ephemeral port | 5/10 | Chọn đúng C, không giải thích được cơ chế |
| 4 | HTTP/2 head-of-line blocking | 6/10 | Chọn đúng B, sai phần nền tảng của HTTP/3 |
| 5 | DNS TTL / cutover | 6/10 | Chọn đúng B, dính bẫy "DNS propagation" |
| 6 | Rolling update / 502 | 0/10 | Bỏ qua |

## Chẩn đoán — điểm quan trọng nhất của buổi

```
Câu trắc nghiệm A/B/C/D:   3/3 ĐÚNG    ← trực giác kỹ thuật TỐT
Câu tự do diễn đạt:        0/2         ← không nói ra được
Câu phụ hỏi "tại sao":     0/5         ← không giải thích được cơ chế
```

> **Nhận ra ≠ Nhớ lại ≠ Giải thích được.**
> Đọc notes chỉ luyện được cái đầu tiên. Phỏng vấn kiểm tra cái thứ ba.

Không phải thiếu kiến thức — notes đã đủ và tốt. Vấn đề là **thông tin đã đi vào
nhưng không đi ra được**. Đây là lý do 4 topic liên tiếp đều dưới chuẩn dù notes
ngày càng dày: **viết thêm notes không sửa được lỗ hổng này.**

### Ba lỗ hổng cần vá

1. **Không có "bản đồ" trong đầu** — câu 1 chỉ là kể lại 6 giai đoạn theo thứ tự,
   phải thuộc như đường về nhà.
2. **Chưa tư duy bằng round-trip** — đơn vị tư duy của kỹ sư mạng. Mọi câu hỏi
   hiệu năng đều quy về: bao nhiêu vòng, mỗi vòng bao xa?
3. **Nhìn triệu chứng chưa suy ra cơ chế** — `refused` vs `timeout`,
   `502` vs `504`: mỗi thông điệp lỗi chỉ đúng tầng bị hỏng.

---

## Câu 1 — Enter tới pixel đầu tiên (`https://shopee.vn`, 800ms)

Câu mở đầu kinh điển. Không kiểm tra kiến thức — kiểm tra **có bản đồ trong đầu
hay không**. Interviewer sẽ dừng ở bất kỳ bước nào và đào sâu.

### Giai đoạn 0 — Trước khi có gói tin nào rời máy (~1ms)

```
1. Parse URL: scheme=https, host=shopee.vn, path=/
2. HSTS preload list → biết trước phải dùng HTTPS
   → tiết kiệm nguyên vòng redirect http:// → https:// (1 RTT + 1 TCP handshake)
3. Kiểm tra cache theo tầng:
   - đã có connection sẵn chưa? (connection pool)
   - Service Worker chặn không?
   - HTTP cache (memory → disk) → còn hạn thì HIỆN NGAY, 0ms mạng
4. Phân giải tên theo tầng:
   - DNS cache trình duyệt (Chrome ~60s) → DNS cache OS → /etc/hosts
```

> **Đường nhanh nhất là đường không đi.** Phần lớn tối ưu web là làm sao để
> KHÔNG PHẢI làm những bước bên dưới.

### Giai đoạn 1 — DNS (~20-120ms)

```
stub resolver ──UDP:53──▶ recursive resolver (VNPT/Viettel, 8.8.8.8, 1.1.1.1)
                              │
                    có cache? ─┴─ trả ngay, 1 RTT ~5-30ms   ← phổ biến
                              │
                    cold path → Root NS (.) → TLD NS (.vn) → Authoritative NS
                                3-4 RTT, nhưng root/TLD dùng ANYCAST nên gần;
                                .vn đặt server tại VN → nhanh hơn tưởng
```

Hai chi tiết ăn điểm:
- Kết quả thường là **CNAME trỏ sang CDN**, rồi CDN trả IP POP gần nhất →
  **bạn không hề kết nối tới datacenter của Shopee**.
- DNS chạy UDP. Response > 512 byte mà không có EDNS0 → cờ TC (truncated) →
  **làm lại toàn bộ query trên TCP** → thêm 1 handshake + 1 RTT.
  (Đây chính là "DNS fallback sang TCP" còn thiếu ở quiz TCP/UDP.)

### Giai đoạn 2 — TCP handshake (1 RTT, ~30-40ms)

```
Client                    Server
   │──── SYN ────────────▶│   seq=x
   │◀─── SYN-ACK ─────────│   seq=y, ack=x+1
   │──── ACK ────────────▶│   ack=y+1
   Tốn 1 RTT trước khi gửi được byte dữ liệu đầu tiên.
```
HN → Singapore ≈ 30-40ms. HN → POP nội địa ≈ 5-15ms.

### Giai đoạn 3 — TLS handshake (1-2 RTT)

```
TLS 1.2 — 2 RTT (~70ms)
  → ClientHello
  ← ServerHello + Certificate + ServerKeyExchange
  → ClientKeyExchange + ChangeCipherSpec + Finished
  ← ChangeCipherSpec + Finished

TLS 1.3 — 1 RTT (~35ms)  ★ tiêu chuẩn hiện nay
  → ClientHello + key_share        (đoán trước nhóm khoá, gửi luôn)
  ← ServerHello + key_share + Certificate + Finished
  → Finished + DỮ LIỆU ỨNG DỤNG

TLS 1.3 resumption — 0 RTT
  → ClientHello + PSK + DỮ LIỆU LUÔN
  ⚠ 0-RTT data có thể bị REPLAY → chỉ dùng cho request idempotent
```

**ALPN** thương lượng ngay trong bắt tay này (`h2` hay `http/1.1`) → HTTP/2
không tốn thêm round-trip nào để thoả thuận.

### Giai đoạn 4 — HTTP request/response (1 RTT + thời gian server)

```
GET / HTTP/2 ──▶ CDN edge ──┬── cache hit → trả luôn (~5ms)
                            └── miss → origin → LB → app → DB (~100-200ms)
TTFB = tổng mọi thứ ở trên.
```

**TCP slow start — chi tiết hầu như ai cũng bỏ sót:**
```
Connection mới có initcwnd = 10 segment ≈ 14 KB. Server KHÔNG được bắn hết ngay.
HTML 50 KB:  RTT1 gửi 14KB → RTT2 gửi 28KB → RTT3 phần còn lại
             → thêm 2 RTT CHỈ ĐỂ tải HTML
```
Đây là lý do lời khuyên "giữ HTML dưới 14KB" có thật, và là lý do **tái sử dụng
connection** quan trọng — connection đã nóng thì cwnd đã lớn sẵn.

### Giai đoạn 5 — Render tới pixel đầu tiên

```
HTML → parse → gặp <link rel="stylesheet">
             → CSS CHẶN RENDER
             → nếu CSS ở domain khác (cdn.shopee.vn)
               → LÀM LẠI TỪ ĐẦU: DNS + TCP + TLS cho domain đó!
→ DOM + CSSOM → Render Tree → Layout → Paint → First Contentful Paint
```

### Ngân sách 800ms

```
  0ms  ┌─ HSTS + cache lookup                      ~1ms
  1ms  ├─ DNS (resolver cache miss)                 50ms
 51ms  ├─ TCP handshake            1 RTT            35ms
 86ms  ├─ TLS 1.3 handshake        1 RTT            35ms
121ms  ├─ Gửi HTTP request         1 RTT            35ms
156ms  ├─ Server xử lý                             150ms   ← TTFB = 306ms
306ms  ├─ Tải HTML (slow start)                     50ms
356ms  ├─ Tải CSS/JS (có thể cần connection mới)   250ms
606ms  ├─ Parse + Layout + Paint                   194ms
800ms  └─ FIRST CONTENTFUL PAINT
```

### Kết luận đắt giá nhất

```
Trước khi server làm BẤT KỲ việc gì:
   DNS(1) + TCP(1) + TLS(1) + request(1) = 4 ROUND-TRIP
RTT 35ms  → 140ms độ trễ thuần tuý
RTT 200ms (3G) → 800ms, và CHƯA có gì để hiển thị
```

Từ đây bật ra mọi thứ interviewer muốn nghe:
- **HTTP/3 (QUIC)**: gộp TCP + TLS handshake → 1 RTT tổng, hoặc 0-RTT
- **CDN**: không giảm được SỐ round-trip thì giảm ĐỘ DÀI mỗi round-trip.
  POP từ Singapore về HN: 35ms → 8ms, tiết kiệm ~110ms trên cả 4 vòng
- **Keep-alive**: request thứ hai bỏ qua cả DNS, TCP, TLS
- **HTTP/2 multiplexing**: subresource dùng chung connection đã nóng

> **Trên mạng, thứ đắt nhất không phải băng thông — mà là round-trip.
> Tối ưu web về bản chất là cuộc chiến giảm số round-trip và rút ngắn từng vòng.**

---

## Câu 2 — `connection refused` nhưng `curl localhost` chạy tốt

**Đáp án: B — app bind `127.0.0.1:8080` thay vì `0.0.0.0:8080`.**

Mấu chốt: **gói tin nào quay về.**

```
connection REFUSED
   SYN ──▶ ; ◀── RST
   └─ CÓ AI ĐÓ trả lời: "tao sống, nhưng port này không ai nghe"
   → lỗi sau ~1 RTT. NHANH.

connection TIMED OUT
   SYN ──▶ ✂ (rơi vào hư vô) ... im lặng
   SYN lại sau 1s, 2s, 4s, 8s, 16s (exponential backoff)
   → bỏ cuộc sau ~30-130s. CHẬM.
```

Firewall an toàn **không bao giờ trả lời** — triết lý bảo mật: im lặng thì kẻ
tấn công không biết máy có tồn tại không. `iptables -j DROP` và AWS Security
Group đều nuốt gói tin không tiếng động → **timeout**, không phải refused.

*(Công bằng: `iptables -j REJECT` ĐÚNG LÀ trả refused vì chủ động gửi ICMP
port-unreachable / RST. Nhưng DROP mới là mặc định, và cloud SG luôn là DROP.)*

Ghép hai manh mối:
```
"connection refused"      → có RST → gói tin ĐÃ TỚI máy → routing OK, firewall OK
                          → TCP stack nói: port 8080 trên interface này KHÔNG AI NGHE
"curl localhost chạy tốt" → process ĐANG NGHE port 8080
Ghép lại: đang nghe, nhưng chỉ trên loopback → bind sai.
```

```bash
ss -tlnp | grep 8080
127.0.0.1:8080    ← chỉ loopback. LỖI.
0.0.0.0:8080      ← mọi interface. Đúng.
```

Lỗi số một khi deploy Docker/K8s — Flask/Uvicorn mặc định bind `127.0.0.1`.

### Bảng cần thuộc lòng

| Lỗi client thấy | Gói tin nhận được | Kết luận |
|---|---|---|
| `connection refused` | **RST** | Tới được máy. Không ai nghe port / bind sai interface |
| `connection timed out` | **im lặng** | Firewall DROP, sai route, hoặc máy chết |
| `no route to host` | **ICMP unreachable** | Router bảo không biết đường |
| `TLS handshake failed` | TCP đã xong | Vấn đề **trên** tầng transport — cert, SNI, protocol |
| `502 Bad Gateway` | HTTP đã xong | LB sống, backend chết |

> **Thông điệp lỗi cho biết mình đi tới tầng nào rồi mới ngã.**

---

## Câu 3 — 28.000 socket TIME_WAIT trên nginx

**Đáp án: C — nginx đóng connection tới backend sau mỗi request → cạn ephemeral
port. Bật keep-alive tới upstream.**

### TIME_WAIT nằm ở bên GỬI FIN TRƯỚC (bên chủ động đóng)

```
   Bên A (chủ động đóng)              Bên B (bị động đóng)
        │────────── FIN ────────────────────▶│   A: FIN_WAIT_1
        │◀───────── ACK ─────────────────────│   B: CLOSE_WAIT
        │                                    │   A: FIN_WAIT_2
        │◀───────── FIN ─────────────────────│   B: LAST_ACK
        │────────── ACK ────────────────────▶│
   ★ A: TIME_WAIT (60s) ★               B: CLOSED (xong ngay)
```
**Ai đóng trước, người đó gánh.** Bên bị động được giải phóng ngay.

### Vì sao phải chờ — hai lý do, cả hai là chuyện đúng/sai của dữ liệu

**1. Gói ACK cuối có thể mất:**
```
A gửi ACK cuối ──▶ ✂ MẤT
B tưởng FIN thất lạc → GỬI LẠI FIN
  Nếu A đã đóng hẳn: A trả RST → close() của B báo lỗi → B kẹt ở LAST_ACK
  Có TIME_WAIT: A còn đủ state để ACK lại lần nữa ✅
```

**2. Gói tin lạc đường từ "kiếp trước" (nguy hiểm hơn nhiều):**
```
Connection cũ (10.0.0.1:54321 → 10.0.0.9:8080), một gói kẹt ở router, đi lang thang.
Connection đóng. 1 giây sau mở connection MỚI TRÙNG Y HỆT 4-tuple.
Gói lạc tới nơi → kernel thấy 4-tuple khớp → GIAO DỮ LIỆU CŨ VÀO CONNECTION MỚI
→ HỎNG DỮ LIỆU. Âm thầm. Không lỗi. Không log.
```

Chờ **2×MSL** để mọi gói của kiếp trước chết hẳn (hết TTL). RFC: MSL 2 phút →
4 phút. **Linux cứng hoá 60 giây** (`TCP_TIMEWAIT_LEN`) — không chỉnh được bằng
sysctl, phải sửa kernel và biên dịch lại.

> **TIME_WAIT không phải bug. Nó là cái giá của tính đúng đắn.**
> Bug là ở chỗ bạn tạo quá nhiều connection ngắn.

### Vì sao nginx lãnh đủ

```
nginx nhận request → MỞ connection tới backend → nhận response → ĐÓNG
                     └─ nginx là bên chủ động đóng → nginx gánh TIME_WAIT

Dải ephemeral mặc định 32768-60999 ≈ 28.000 cổng.
28.000 TIME_WAIT = CẠN SẠCH
→ connect() lỗi EADDRNOTAVAIL "Cannot assign requested address" → 502 hàng loạt
```
Bình thường **client** mới là bên đóng trước nên web server không tích TIME_WAIT.
Reverse proxy **đóng vai client** với backend nên lãnh trọn.

### Cách sửa, xếp theo mức độ đúng đắn

**1. Keep-alive tới upstream — cách sửa THẬT:**
```nginx
upstream backend {
    server 10.0.0.9:8080;
    keepalive 64;
}
location / {
    proxy_pass http://backend;
    proxy_http_version 1.1;          # BẮT BUỘC — mặc định là 1.0
    proxy_set_header Connection "";  # BẮT BUỘC — xoá header "close"
}
```
Hai dòng cuối **luôn bị quên**, thiếu chúng thì `keepalive 64` vô tác dụng.
28.000 conn/phút → 64 conn dùng lại mãi. Và connection nóng có sẵn cwnd lớn.

**2.** Nới `net.ipv4.ip_local_port_range` — vá tạm.
**3.** `net.ipv4.tcp_tw_reuse = 1` — tái dùng socket TIME_WAIT cho kết nối ĐI RA,
an toàn khi bật TCP timestamps. Chấp nhận được.
**4.** `tcp_tw_recycle` — ❌ **ĐÃ BỊ GỠ KHỎI LINUX 4.12**, phá mọi client sau NAT.
Biết điều này là điểm cộng lớn (nhiều blog cũ vẫn khuyên dùng).

---

## Câu 4 — HTTP/2 chậm hơn HTTP/1.1 trên 4G sóng yếu

**Đáp án: B — TCP head-of-line blocking.**

```
TCP — MỘT dòng byte, kernel BẮT BUỘC giao đúng thứ tự:
  [stream1][stream2][ ✂ MẤT ][stream4]...[stream40]
                        └─ kernel giữ TOÀN BỘ phần sau lại
                           Cả 40 luồng ĐỨNG HÌNH chờ 1 gói gửi lại
HTTP/1.1 dùng 6 connection → chỉ 1/6 bị ảnh hưởng.
```

### HTTP/3 = HTTP trên QUIC, QUIC trên **UDP**

Vì sao không sửa thẳng TCP:

**1. TCP đã bị hoá đá (ossification).** NAT, firewall, CGNAT, WAN optimizer, DPI
đều ĐỌC HIỂU header TCP và được viết từ 2005. Gặp option lạ → nhiều hộp DROP
thẳng. TCP Fast Open, MPTCP đều bị chặn ngoài đời thật. Muốn thêm tính năng cho
TCP phải chờ CẢ INTERNET nâng cấp thiết bị — không bao giờ xảy ra.

**2. TCP nằm trong kernel.**
```
Sửa TCP  → cập nhật kernel MỌI OS trên đời → chu kỳ 10 năm
QUIC ở USERSPACE (trong trình duyệt) → Chrome đẩy update → thứ Ba tuần sau
                                        3 tỷ người có transport mới → chu kỳ 6 tuần
```

> **UDP được chọn không phải vì UDP tốt** — mà vì nó là thứ duy nhất đi xuyên
> internet mà không hộp đen nào ngó vào payload. QUIC dùng UDP như ống trống rồi
> tự xây lại: tin cậy, thứ tự, congestion control, mã hoá.

### Sửa head-of-line blocking thế nào

```
QUIC — stream là công dân hạng nhất, mỗi stream một không gian số thứ tự RIÊNG:
  stream1  ────────────▶ ✅      stream7  ────✂ MẤT ──── CHỈ stream 7 dừng ⏸
  stream2  ────────────▶ ✅      stream8  ────────────▶ ✅
```
Packet loss 2%: HTTP/2 mỗi gói mất là cả trang khựng. HTTP/3 chỉ ảnh hưởng
một tài nguyên.

### Hai món quà kèm theo

**Bắt tay 1 RTT:**
```
TCP + TLS1.3 = 2 RTT (240ms @ RTT 120ms)   |  QUIC = 1 RTT (120ms)
QUIC + 0-RTT resume = 0 RTT
```

**Connection migration:**
```
TCP định danh bằng 4-tuple → WiFi sang 4G → IP đổi → 4-tuple đổi → CONNECTION CHẾT
QUIC định danh bằng Connection ID (số ngẫu nhiên, không dính IP)
    → IP đổi → Connection ID KHÔNG ĐỔI → connection SỐNG TIẾP
```
Chính là vấn đề "IP user thay đổi phá IP hash" ở buổi Load Balancer — QUIC giải
quyết ngay tại tầng transport.

### Cái giá phải trả
- Một số firewall doanh nghiệp **chặn UDP 443** → phải có đường lùi về TCP
- Tốn CPU hơn: userspace, mã hoá từng gói, chưa có hardware offload rộng rãi
- Một số nhà mạng ưu tiên TCP hơn UDP → throughput đôi khi tệ hơn

*(Vì sao A sai: domain sharding là mẹo thời HTTP/1.1. Với HTTP/2 nó PHẢN TÁC DỤNG
— mỗi domain thêm một vòng DNS + TCP + TLS, lại phá vỡ ngữ cảnh nén header.)*

---

## Câu 5 — 6 tiếng sau cutover vẫn còn 3% traffic vào IP cũ

**Đáp án: B — có những kẻ phớt lờ TTL.**

### "DNS propagation" KHÔNG TỒN TẠI

Trong DNS **không hề có cơ chế đẩy dữ liệu**. Hoàn toàn là **kéo về + cache hết hạn**.

```
NIỀM TIN SAI: đổi bản ghi → dữ liệu được ĐẨY ra 10 triệu DNS server trong 48h
              → cơ chế này KHÔNG TỒN TẠI

THỰC TẾ: đổi bản ghi → authoritative NS cập nhật NGAY (<1 giây)
  ├── Resolver hỏi lúc này → nhận IP MỚI ✅ tức thì
  └── Resolver đã cache IP cũ → trả IP cũ TỚI KHI CACHE HẾT HẠN, rồi hỏi lại
```

> **"Thời gian propagation" chỉ là: TTL dài nhất bạn đã lỡ phát ra trước khi đổi.**

### Con số 24-48 tiếng ở đâu ra

1. **Di sản lịch sử** — xưa primary/secondary NS đồng bộ qua zone transfer theo
   `SOA refresh`. Nay dùng API + DB dùng chung + anycast, đồng bộ dưới 1 giây.
2. **Nhầm lẫn thật sự đáng chú ý** —
   ```
   Đổi bản ghi A tại NS của bạn  → tức thì, chỉ vướng TTL bạn kiểm soát được
   Đổi NAMESERVER tại nhà đăng ký → phải vào zone của TLD (.com/.vn)
                                    → NS record ở TLD có TTL riêng, thường 48 TIẾNG
                                    → BẠN KHÔNG KIỂM SOÁT ĐƯỢC. Cái này CHẬM THẬT.
   ```
3. **Support hosting nói "chờ 48 tiếng"** vì đó là câu trả lời an toàn đóng ticket.

### 3% lì lợm thật sự do đâu

| Thủ phạm | Chi tiết |
|---|---|
| **ISP ép TTL sàn** | Có nhà mạng đặt TTL tối thiểu 300s-3600s để giảm tải query → TTL 60s bị phớt lờ |
| **JVM** | `networkaddress.cache.ttl` mặc định `-1` ở cấu hình cũ = **cache vĩnh viễn**, giữ IP cũ tới khi restart |
| **Connection pool** | ★ Lớn nhất — app phân giải DNS MỘT LẦN lúc khởi động, mở connection, dùng lại mãi, **không bao giờ hỏi DNS nữa**. HTTP keep-alive, pool DB, gRPC channel đều vậy |
| **nginx** | `proxy_pass http://backend.example.com` phân giải MỘT LẦN lúc start. Muốn re-resolve phải có `resolver 8.8.8.8 valid=30s;` VÀ dùng biến |
| **IP hardcode** | `/etc/hosts`, file config, biến môi trường không ai nhớ |

### Cách làm đúng

> **DNS là cơ chế *khám phá*, không phải cơ chế *chuyển đổi*.** Đừng thiết kế
> migration mà tính đúng đắn phụ thuộc vào việc mọi client tôn trọng TTL.

```
1. Giữ IP CŨ SỐNG, proxy sang IP mới.
   Theo dõi LOG, không theo dõi ĐỒNG HỒ. Traffic về 0 mới tắt. Vài ngày cũng được.
2. Tốt hơn: ĐỪNG ĐỔI IP.
   Đặt LB / anycast IP phía trước, đổi thứ nằm SAU nó. IP công khai không đổi.
   → lý do thật sự khiến kiến trúc có LB đứng trước lại quan trọng.
```

---

## Câu 6 — Rolling update sinh 502 (bỏ qua, chưa trả lời)

**Đáp án: B** — K8s gửi `SIGTERM` giết pod nhưng LB chưa kịp biết nên vẫn gửi
request tới. Cần `preStop` hook + connection draining: pod nhận `SIGTERM` →
**báo `/readyz` trả 503 TRƯỚC** → chờ LB gỡ khỏi pool → xử lý nốt request đang
bay → mới thoát.

### 502 vs 503 vs 504

| Mã | Nghĩa | Hỏng ở đâu |
|---|---|---|
| **502** Bad Gateway | LB kết nối được backend nhưng nhận **phản hồi rác** hoặc bị **đóng đột ngột** | Backend **chết giữa chừng** — đúng ca pod bị `SIGTERM` |
| **503** Service Unavailable | LB **không có backend nào** để gửi tới | Pool rỗng, hoặc LB đang shed tải |
| **504** Gateway Timeout | Kết nối được, gửi được, nhưng **backend không trả lời kịp** | Backend **sống nhưng chậm** |

Ba mã, ba vị trí hỏng. Đọc đúng mã là biết đi tìm ở đâu.

---

## Việc cần làm tiếp

Kết luận quan trọng nhất: **ngừng viết thêm notes.** 4 topic đều dưới chuẩn không
phải vì thiếu tài liệu, mà vì thiếu **luyện nhớ lại và diễn đạt**.

1. **Practical exercise Load Balancer** — code hoá khái niệm (round robin →
   health check → least connections + slow start). Gõ tay giúp nhớ hơn đọc.
2. **Luyện nói 2 phút** — mỗi ngày chọn 1 chủ đề, nói to trong 2 phút, KHÔNG NHÌN
   NOTES. Ghi âm lại rồi so với notes để biết mình quên gì.
3. **Bản đồ câu 1 phải thuộc** — 6 giai đoạn + số round-trip của từng cái.
4. **Quiz lại theo lịch giãn cách** — TCP/UDP, HTTP, DNS, LB, dạng tự luận,
   không trắc nghiệm.

### Chỉ số cần đạt trước khi sang topic mới
- Kể lại câu 1 đủ 6 giai đoạn kèm số RTT, không nhìn notes
- Giải thích được TIME_WAIT tồn tại vì cái gì
- Phân biệt được refused / timeout / 502 / 503 / 504 và ý nghĩa từng cái
- Mock interview lần 2 đạt ≥ 70%
