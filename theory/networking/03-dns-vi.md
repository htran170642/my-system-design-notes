# DNS — Domain Name System

Ngày học: 2026-06-23

---

## 1. Khái niệm

### DNS giải quyết vấn đề gì

Máy tính giao tiếp qua IP address (142.250.185.46). Con người nhớ tên (google.com). DNS là cuốn danh bạ điện thoại phân tán ánh xạ tên sang IP.

Không có DNS bạn phải nhớ IP của mọi website — và khi Google đổi server IP, mọi người đều bị broken.

### Tại sao phải phân tán?

Một DNS server duy nhất cho toàn internet sẽ:
- Là single point of failure
- Là bottleneck khổng lồ (hàng tỷ query/ngày)
- Không thể cập nhật kịp thời trên toàn cầu

DNS là **cơ sở dữ liệu phân cấp, phân tán** — không server nào biết tất cả, nhưng bất kỳ tên nào cũng có thể resolve bằng cách đi theo hierarchy.

---

## 2. Phân cấp DNS

```
Root (.)
├── .com
│   ├── google.com
│   │   ├── www.google.com
│   │   └── mail.google.com
│   └── example.com
├── .org
└── .vn
    └── vnexpress.vn
```

**Ba tầng DNS server:**

```
Root Nameservers (13 cluster, vận hành bởi ICANN/Verisign/...)
        |
TLD Nameservers (.com, .org, .vn — vận hành bởi registry)
        |
Authoritative Nameservers (google.com — vận hành bởi Google)
```

---

## 3. DNS Resolution — Toàn bộ flow

Khi bạn gõ `www.google.com` lần đầu tiên:

```
Browser → OS DNS cache → miss
OS → Recursive Resolver (ISP hoặc 8.8.8.8) → miss

Recursive Resolver:
  1. Query Root NS: ".com do ai quản?"
     Root NS: "hỏi TLD NS tại 192.5.6.30"

  2. Query TLD NS: "google.com do ai quản?"
     TLD NS: "hỏi Authoritative NS tại 216.239.32.10"

  3. Query Authoritative NS: "www.google.com là gì?"
     Auth NS: "142.250.185.46, TTL=300"

Recursive Resolver → OS → Browser
Browser cache trong TTL giây
```

**Insight quan trọng:** Recursive resolver làm toàn bộ công việc, không phải máy của bạn. Nó query hierarchy thay bạn và cache kết quả.

---

## 4. Các loại DNS Record

| Record | Mục đích | Ví dụ |
|--------|---------|---------|
| **A** | Domain → IPv4 | `google.com → 142.250.185.46` |
| **AAAA** | Domain → IPv6 | `google.com → 2607:f8b0:...` |
| **CNAME** | Alias → domain khác | `www.example.com → example.com` |
| **MX** | Mail server của domain | `example.com → mail.example.com` |
| **NS** | Nameserver của domain | `google.com → ns1.google.com` |
| **TXT** | Text tùy ý | SPF, DKIM, xác thực domain |
| **PTR** | IP → Domain (reverse DNS) | `142.250.185.46 → google.com` |
| **SOA** | Start of Authority — metadata của zone | Serial, refresh interval |

### Nguy hiểm của CNAME chain

```
www.example.com → CNAME → lb.example.com → CNAME → cdn.example.com → A → 1.2.3.4
```

Mỗi CNAME cần thêm một lookup. Chain dài = thêm latency. CNAME không thể đứng cùng record khác trên cùng tên (CNAME ở zone apex bị cấm — dùng ALIAS/ANAME thay thế).

---

## 5. TTL và Caching

**TTL (Time To Live):** Thời gian resolver được phép cache câu trả lời trước khi query lại.

```
TTL thấp (60s):   Data mới, nhưng nhiều query hơn → tải cao trên authoritative NS
TTL cao (86400s): Ít query, nhưng thay đổi lan truyền chậm
```

**Chiến lược TTL thực tế:**
- Bình thường: TTL = 3600 (1 giờ)
- Trước khi đổi IP: hạ TTL xuống 300 (5 phút) trước 24 giờ
- Sau khi đổi: tăng TTL lại 3600

Đây là lý do "DNS propagation" mất thời gian — bạn đang chờ các record cached hết hạn trên toàn bộ recursive resolver thế giới.

---

## 6. DNS trong System Design

### Load Balancing qua DNS

**Round Robin DNS:** Trả về nhiều A record, xoay vòng thứ tự:
```
api.example.com → [1.2.3.4, 1.2.3.5, 1.2.3.6]
Query 1: [1.2.3.4, 1.2.3.5, 1.2.3.6]
Query 2: [1.2.3.5, 1.2.3.6, 1.2.3.4]
Query 3: [1.2.3.6, 1.2.3.4, 1.2.3.5]
```

Hạn chế: DNS load balancing không biết server nào đang down — nếu 1.2.3.4 chết, client vẫn nhận IP đó cho đến khi TTL hết.

**Geo DNS:** Trả về IP khác nhau theo vị trí client:
```
Client US → api.example.com → 1.2.3.4 (server US)
Client VN → api.example.com → 5.6.7.8 (server SG)
```

CDN (Cloudflare, Akamai) dùng Geo DNS để route user đến edge server gần nhất.

### Failover

TTL thấp → có thể đổi IP nhanh hơn khi có incident. Nhưng TTL thấp = tải cao hơn trên DNS infrastructure.

---

## 7. DNS Security

### DNS Spoofing / Cache Poisoning

Attacker inject fake DNS record vào cache của recursive resolver:
```
Attacker → Resolver: "bank.com = 9.9.9.9 (server của tôi)"
Victim query bank.com → nhận 9.9.9.9 → phishing site
```

**DNSSEC** ngăn điều này: authoritative nameserver ký record bằng cryptography. Resolver xác minh chữ ký. Nhưng adoption của DNSSEC còn thấp (~30% domain).

### DNS over HTTPS (DoH) / DNS over TLS (DoT)

DNS truyền thống là **plaintext** — ISP và bất kỳ ai trên mạng đều thấy mọi domain bạn query. DoH/DoT mã hóa DNS traffic:
- DoH: DNS query trong HTTPS (port 443) — trông như web traffic bình thường
- DoT: DNS query qua TLS (port 853)

Firefox (Cloudflare DoH mặc định), Chrome, iOS 14+ dùng DoH/DoT.

---

## 8. Đánh đổi và tình huống lỗi

### DNS là Single Point of Failure

Nếu authoritative nameserver của bạn down, toàn bộ domain không thể truy cập — dù web server vẫn chạy. Giải pháp: luôn có ít nhất 2 authoritative nameserver ở các vị trí khác nhau.

### Negative Caching

DNS cũng cache **negative response** (NXDOMAIN — domain không tồn tại). TTL cho negative response được set trong SOA record. Bug hay gặp: deploy subdomain mới nhưng negative cache chưa hết hạn → user vẫn nhận NXDOMAIN.

### Split-horizon DNS

Trả về DNS khác nhau cho client nội bộ vs bên ngoài:
```
Nội bộ: api.company.com → 10.0.0.1 (IP private)
Bên ngoài: api.company.com → 52.1.2.3 (IP public)
```

Phổ biến trong môi trường doanh nghiệp — traffic nội bộ đi qua private network.

---

## 9. Góc độ phỏng vấn

### Câu hỏi thường gặp

**Q: Chuyện gì xảy ra khi bạn gõ google.com vào browser?**
Đáp án đầy đủ: browser cache → OS cache → recursive resolver → root NS → TLD NS → authoritative NS → IP trả về → TCP connection → TLS handshake → HTTP request.

**Q: A record và CNAME khác nhau thế nào?**
A record map trực tiếp sang IP. CNAME map sang domain khác (alias), domain đó mới resolve sang IP. CNAME thêm một lookup. Không dùng CNAME ở zone apex.

**Q: DNS load balancing hoạt động thế nào và hạn chế là gì?**
Round-robin trả nhiều IP, client chọn một. Hạn chế: không biết server health, thay đổi chậm theo TTL, không có session affinity.

**Q: Tại sao DNS dùng UDP?**
Query vừa trong một packet (<512 byte). UDP tránh TCP handshake overhead. Fallback sang TCP cho response lớn (DNSSEC, zone transfer).

### Điều interviewer cấp Senior kỳ vọng

- Trace đầy đủ resolution path: browser → recursive resolver → root → TLD → authoritative
- Giải thích TTL trade-off cho planned maintenance
- Biết DNS load balancing bị gì (health check, TTL lag)
- Hiểu split-horizon DNS cho internal routing
- Kết nối Geo DNS với CDN routing

### Lỗi hay mắc

- Nói "DNS server" mà không phân biệt loại (recursive vs authoritative)
- Quên DNS change không propagate ngay (TTL)
- Không biết CNAME ở zone apex bị cấm
- Nói DNS luôn dùng UDP (quên TCP fallback)

---

## 10. Bài tập thực hành

Xây DNS lookup tool bằng Python dùng `socket`:

```python
# Milestone 1: gửi raw DNS query cho A record, parse response
# Milestone 2: tự động follow CNAME chain
# Milestone 3: đo RTT giữa 8.8.8.8 và 1.1.1.1
```

### Bài tập system design

Thiết kế DNS infrastructure cho e-commerce platform toàn cầu (như Shopee). User ở VN, SG, US. Làm thế nào để:
- Route user đến server gần nhất
- Xử lý failover khi một region down
- Giảm thiểu DNS lookup latency

### Câu hỏi follow-up

1. Site bạn down nhưng DNS vẫn ổn. Đồng nghiệp nói "hạ TTL xuống để lần sau fix nhanh hơn." Đây có phải lời khuyên tốt không?
2. User ở Hà Nội query api.example.com nhận được IP của US thay vì SG. Nguyên nhân có thể là gì?
3. Recursive resolver và authoritative nameserver khác nhau thế nào?
