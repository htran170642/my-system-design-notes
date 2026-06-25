# System Design: DNS Infrastructure cho Shopee

Ngày: 2026-06-23

---

## Bài toán

Thiết kế DNS infrastructure cho e-commerce platform toàn cầu (Shopee).
- User ở VN, SG, US
- Yêu cầu: route user đến server gần nhất, failover tự động, latency thấp

---

## Câu 1 — Route user đến server gần nhất

**Giải pháp: Geo DNS**

```
User HN  → query api.shopee.com → Geo DNS thấy IP từ VN → trả server SG
User US  → query api.shopee.com → Geo DNS thấy IP từ US → trả server US
User SG  → query api.shopee.com → Geo DNS thấy IP từ SG → trả server SG
```

Geo DNS xác định vị trí dựa trên **IP của recursive resolver** (không phải user). AWS Route 53, Cloudflare, Google Cloud DNS đều hỗ trợ.

**TTL:** 60-300s — thấp để re-route nhanh khi user đổi vị trí hoặc resolver.

---

## Câu 2 — Failover khi region down

**Giải pháp: Health check + DNS failover**

```
Route 53 / Cloudflare DNS
  ├── api.shopee.com → SG (primary)   ← health check mỗi 10s
  └── api.shopee.com → US (failover)  ← chỉ active khi SG down
```

**Flow khi SG down:**
```
1. Health checker ping SG → fail 3 lần liên tiếp
2. DNS remove SG record, promote US record
3. TTL hết hạn (60s) → user nhận IP US
4. SG recover → health check pass → DNS add SG lại
```

**Giới hạn:** Worst case user bị down đúng bằng TTL (60s) trước khi nhận IP mới.

**Giải pháp thực tế — CDN layer:**
```
User → CDN Edge (Cloudflare/Akamai) → Origin (SG hoặc US)
```
CDN giữ persistent connection đến origin — failover sub-second, không phụ thuộc DNS TTL. DNS chỉ route user đến CDN edge gần nhất.

---

## Câu 3 — Giảm DNS lookup latency

**3 cách:**

**1. DNS caching ở client**
```
Mobile app cache DNS result theo TTL
api.shopee.com → 10.sg.shopee.com (cache 300s)
→ 10 API calls chỉ tốn 1 DNS lookup, 9 cái còn lại dùng cache
```

**2. TTL hợp lý — không quá thấp**

TTL 300s thay vì 30s → resolver cache lâu hơn → ít round trip lên authoritative NS. Đánh đổi với tốc độ failover.

**3. Dùng resolver nhanh gần user**

| Resolver | Latency từ VN |
|----------|--------------|
| 1.1.1.1 (Cloudflare) | ~20ms |
| 8.8.8.8 (Google) | ~30ms |
| ISP resolver | Gần nhất nhưng cache kém |

**Pre-resolve:** App resolve domain khi khởi động, trước khi user cần — giấu latency hoàn toàn.

**DNS over HTTPS (DoH):** Tránh ISP chặn/spoof DNS, bảo mật hơn, latency tương đương.

---

## Kiến trúc tổng thể

```
User (VN/SG/US)
    |
    | DNS query (Geo DNS → edge gần nhất)
    v
CDN Edge (Cloudflare/Akamai — nhiều PoP toàn cầu)
    |
    | Health-check-aware routing
    v
Origin Server (SG primary / US failover)
```

## Điểm cần nhớ

- Geo DNS dùng IP của **resolver**, không phải user → cẩn thận khi user dùng VPN hoặc resolver ở nước khác
- DNS failover bị giới hạn bởi TTL → dùng CDN để failover nhanh hơn
- TTL thấp = failover nhanh nhưng tốn DNS query; TTL cao = ngược lại
- Pre-resolve + client cache để giấu DNS latency khỏi user
