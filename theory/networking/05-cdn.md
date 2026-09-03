# CDN — Content Delivery Network

Session date: 2026-08-27

> Bài này viết gọn hơn 4 bài trước, và kết thúc bằng danh sách tự kiểm tra
> thay vì thêm một bức tường chữ. Lý do: mock interview 01 cho thấy vấn đề
> không nằm ở lượng notes mà ở khả năng nhớ lại và diễn đạt.
> Xem `mock-interview-01-networking.md`.

---

## 1. Vấn đề nó giải quyết

Ba giới hạn. Cái đầu tiên là **giới hạn vật lý không thể vượt qua**:

```
Hà Nội → São Paulo: ~18.000 km
Ánh sáng trong sợi quang: ~200.000 km/s
   → một chiều: 90ms
   → khứ hồi:  180ms  ← SÀN TUYỆT ĐỐI. Không code nào phá được.

Nhớ lại câu 1 của mock interview: cần 4 round-trip trước khi server làm gì.
4 × 180ms = 720ms độ trễ thuần tuý.
```

Không làm ánh sáng nhanh hơn được. Chỉ **rút ngắn quãng đường** — đặt bản sao
nội dung gần người dùng.

Hai vấn đề còn lại:
- **Năng lực origin:** 1 triệu user tải cùng một logo 200KB = 200GB đi qua
  server của bạn, để phục vụ MỘT file.
- **Chi phí băng thông:** egress AWS ≈ $0.09/GB, CDN ≈ $0.01-0.02/GB.
  Chênh 5-9 lần ở quy mô petabyte.

---

## 2. Request tới edge bằng cách nào

Chỗ DNS và Load Balancer ghép vào:

```
CÁCH 1 — DNS-based (phổ biến nhất)
   cdn.shopee.vn  CNAME→  shopee.akamai.net
                              │
                    DNS của CDN nhìn IP của RESOLVER
                    (bẫy Geo DNS: là IP resolver, KHÔNG phải IP user)
                              │
                          trả IP của POP gần nhất

   ✅ linh hoạt, chọn được POP theo tải
   ❌ dính mọi vấn đề TTL: resolver ở xa → chọn POP sai

CÁCH 2 — Anycast (Cloudflare)
   Một IP duy nhất announce từ 300 POP qua BGP
   → định tuyến mạng tự đưa tới POP gần nhất
   ✅ không phụ thuộc TTL, failover ở tầng định tuyến
   ❌ ít quyền kiểm soát POP nào phục vụ ai
```

---

## 3. Cơ chế cache — phần quan trọng nhất

### Cache key

Quyết định hai request có được coi là một hay không.

```
Mặc định:  host + path + query string
Cẩn thận:  thêm header nào vào key là NHÂN ĐÔI số bản sao
           → Vary: Accept-Encoding  ✅ hợp lý (gzip/br)
           → Vary: User-Agent       ❌ hàng nghìn biến thể, hit ratio về 0
```

### Điều khiển thời gian sống

```http
Cache-Control: public, max-age=60, s-maxage=3600, stale-while-revalidate=86400
               │       │             │                │
               │       │             │                └─ hết hạn rồi vẫn trả bản
               │       │             │                   cũ NGAY, đồng thời âm
               │       │             │                   thầm lấy bản mới
               │       │             │                   → user không phải chờ
               │       │             └─ CDN giữ 1 tiếng (đè lên max-age)
               │       └─ trình duyệt giữ 60 giây
               └─ CDN được phép cache (private = chỉ trình duyệt)
```

`stale-while-revalidate` tách **"hết hạn"** khỏi **"phải chờ"** — món đáng nhớ
nhất trong nhóm này.

`stale-if-error` cho phép CDN tiếp tục phục vụ bản cũ **khi origin chết** →
hệ thống vẫn sống dù backend sập. Đây là tính năng khả dụng, không phải bug.

### Validation (khi hết hạn thật)

```
ETag: "a3f9c2"            → lần sau client gửi If-None-Match: "a3f9c2"
                          → chưa đổi thì server trả 304 Not Modified (không body)
Last-Modified / If-Modified-Since  → phiên bản cũ hơn, độ phân giải 1 giây
```

---

## 4. Toán học của cache hit ratio

```
Hit ratio 90%  → origin nhận 10% traffic  → nhẹ đi  10 lần
Hit ratio 99%  → origin nhận  1% traffic  → nhẹ đi 100 lần

Từ 90% lên 99% chỉ tăng 9 điểm phần trăm, nhưng tải origin GIẢM 10 LẦN.
```

Đây là lý do mọi nỗ lực tối ưu CDN đổ vào cache key: **thêm một header vào key
có thể kéo hit ratio từ 99% xuống 60% → tải origin tăng 40 lần.**

---

## 5. Vô hiệu hoá cache — bài toán khó thật sự

```
CÁCH 1 — Purge theo URL
   API: purge https://cdn.site.com/logo.png
   Chậm (vài giây tới vài phút để lan ra 300 POP), phải biết chính xác URL.

CÁCH 2 — Surrogate key / cache tag   ★ cách đúng cho nội dung động
   Response gắn: Surrogate-Key: product-123 category-shoes
   Sản phẩm 123 đổi giá → purge tag "product-123"
   → xoá MỌI trang chứa nó (trang chủ, danh mục, tìm kiếm, chi tiết)
   Fastly, Cloudflare Enterprise hỗ trợ.

CÁCH 3 — URL có phiên bản   ★ tốt nhất cho tài sản tĩnh
   /app.a3f9c2.js  với  Cache-Control: max-age=31536000, immutable
   Đổi nội dung → đổi tên file → KHÔNG BAO GIỜ CẦN PURGE.
   Cache một năm, an toàn tuyệt đối.
```

> **Đừng vô hiệu hoá cache — hãy đổi tên.**
> Purge dành cho thứ không đổi tên được (trang HTML, API response).

---

## 6. Origin shield — bài học Load Balancer quay lại

```
KHÔNG có shield:
   300 POP cùng miss cùng lúc (file mới, hoặc TTL cùng hết hạn)
   → 300 request đập vào origin CÙNG MỘT GIÂY cho CÙNG MỘT FILE
   → cache stampede = THUNDERING HERD ở buổi Load Balancer

CÓ shield:
   300 POP  →  1 POP shield (tầng 2)  →  origin

   Shield gộp request (request coalescing):
   300 request giống hệt nhau → gửi origin ĐÚNG 1 → phát lại cho cả 300
   → origin nhận 1 thay vì 300
```

Cùng ý tưởng với `maxconn` và load shedding ở buổi Load Balancer:
**đứng giữa và gộp lại.**

Chống TTL cùng hết hạn hàng loạt: thêm **jitter** vào TTL (±10%) để các POP
không hết hạn đồng thời — giống nguyên tắc tránh đồng bộ hoá thất bại.

---

## 7. Đánh đổi và các kiểu hỏng

| Vấn đề | Cơ chế | Cách chống |
|---|---|---|
| **Nội dung cũ** | TTL chưa hết | Versioned URL, surrogate key, TTL ngắn cho HTML |
| **Cache poisoning** | Header không nằm trong key nhưng ảnh hưởng response | Cache key chặt, `Vary` đúng, không tin header từ client |
| **Rò rỉ dữ liệu riêng tư** | Trang có cookie đăng nhập bị cache `public` | `Cache-Control: private, no-store` cho mọi thứ có xác thực |
| **Hit ratio thấp** | Query string rác (`?utm_source=...`) tạo key khác nhau | Chuẩn hoá cache key, bỏ tham số marketing |
| **Chi phí bất ngờ** | Purge quá thường xuyên → miss liên tục → origin gánh | Đừng dùng purge thay cho TTL |

**Bẫy rất hay dính:** `?utm_source=facebook` và `?utm_source=zalo` trỏ cùng một
trang nhưng là **hai cache key khác nhau** → cùng một nội dung lưu hàng nghìn
bản, hit ratio sụp đổ. Phải cấu hình CDN bỏ qua tham số marketing khi tạo key.

---

## 8. Dynamic acceleration — CDN không chỉ cho ảnh

Nội dung động không cache được, nhưng CDN vẫn giúp:

```
Không CDN:  user ──── 4 RTT × 180ms ────▶ origin ở xa
Có CDN:     user ── 4 RTT × 10ms ──▶ POP gần ══ connection NÓNG sẵn ══▶ origin
                    (DNS+TCP+TLS+request đều diễn ra với POP)
```

- Edge terminate TLS → bắt tay diễn ra ở khoảng cách 10ms thay vì 180ms
- POP giữ connection keep-alive sẵn tới origin → bỏ qua TCP + TLS + slow start
  (đúng bài học keep-alive ở câu 3 mock interview)
- Đường đi tối ưu trong mạng riêng của CDN thay vì internet công cộng

---

## 9. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- CDN không chỉ cho ảnh — **dynamic acceleration** cũng giá trị lớn
- Nói được về **cache key** và **hit ratio**, không chỉ "đặt CDN vào cho nhanh"
- Nhắc **origin shield / request coalescing** khi bàn bảo vệ origin
- Phân biệt **purge vs versioned URL**

**Sai lầm thường gặp:**
- Cache trang có thông tin đăng nhập → rò rỉ dữ liệu người dùng khác
- Quên rằng CDN phục vụ được nội dung cũ khi origin chết (`stale-if-error`)
- Coi CDN là hộp đen thần kỳ thay vì **một cache có cache key**

---

## 10. Danh sách tự kiểm tra — trả lời KHÔNG NHÌN NOTES

Phần này thay thế cho "đọc lại bài". Không trả lời trôi chảy được nghĩa là
chưa học xong.

1. Vì sao CDN nhanh hơn? Nói bằng đơn vị **round-trip**, đừng nói "vì gần hơn".
2. `max-age` khác `s-maxage` chỗ nào? Ai đọc cái nào?
3. `stale-while-revalidate` giải quyết vấn đề gì mà `max-age` không giải quyết?
4. Hit ratio từ 95% lên 99% thì tải origin thay đổi bao nhiêu lần?
5. Vì sao versioned URL tốt hơn purge?
6. Origin shield chống hiện tượng nào? Hiện tượng đó gặp ở buổi nào trước đây?
7. `?utm_source=facebook` phá hỏng cache như thế nào?
8. Trang có cookie đăng nhập mà lỡ set `Cache-Control: public` thì sao?

---

## 11. Bài tập

**Implementation:** viết một caching reverse proxy nhỏ bằng Python —
cache key từ (host, path, query đã chuẩn hoá), tôn trọng `max-age`, thêm
`stale-while-revalidate`, rồi thêm request coalescing để 100 request đồng thời
cùng một URL chỉ sinh 1 request tới origin.

**System design:** thiết kế tầng phân phối nội dung cho một sàn thương mại
điện tử VN — ảnh sản phẩm (tĩnh), giá (đổi thường xuyên), tồn kho (đổi liên
tục), trang cá nhân (riêng tư). Mỗi loại cache thế nào, TTL bao nhiêu,
vô hiệu hoá ra sao?
