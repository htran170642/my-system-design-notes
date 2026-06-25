# Quiz: DNS — Domain Name System

Ngày: 2026-06-23 (lần 1 — cần quiz lại)

---

## Kết quả

| Câu | Chủ đề | Kết quả |
|-----|--------|---------|
| 1 | Full resolution path | ✅ Đúng |
| 2 | TTL timing cho IP change | ⚠️ Biết hạ TTL nhưng không biết timing |
| 3 | CNAME conflict với record khác | ❌ Chưa biết |
| 4 | Geo DNS trả sai region | ❌ Chưa biết |
| 5 | Debug NXDOMAIN lúc 2 giờ sáng | ❌ Chưa biết |

---

## Câu 1 — Full Resolution Path

**Q:** Trace toàn bộ quá trình resolve `www.google.com` từ đầu.

**A:** ✅
```
browser cache → OS cache → recursive resolver → root NS → TLD NS → authoritative NS → IP → TCP → TLS → HTTP
```

---

## Câu 2 — TTL Timing

**Q:** TTL hiện tại 3600, cần đổi IP lúc 10:00. Chuẩn bị gì?

**A:** Hạ TTL xuống 300 (5 phút), đổi IP xong tăng lại 3600.

**Thiếu:** Phải hạ TTL **trước ít nhất 1 TTL cũ (1 tiếng)**:
```
8:00  → Hạ TTL 3600 → 300
        (chờ 1 tiếng để cache cũ expire trên toàn bộ resolver)
9:00  → Mọi resolver đã pick up TTL=300
10:00 → Đổi IP — worst case 5 phút propagate
10:10 → Tăng TTL lại 3600
```
Nếu hạ lúc 9:55 thì resolver đã cache từ 9:00 vẫn dùng TTL cũ (55 phút còn lại), không biết TTL mới.

---

## Câu 3 — CNAME Conflict

**Q:** `api.example.com` đang có CNAME. Có thể thêm MX record vào cùng tên không?

**A:** Không. **CNAME không thể đứng cùng bất kỳ record nào khác trên cùng tên** (RFC 1034). CNAME có nghĩa "tên này là alias, redirect mọi query sang tên kia" — không thể vừa alias vừa có MX.

Giải pháp: tách email ra subdomain riêng:
```
api.example.com   → CNAME → lb.example.com   ✅
mail.example.com  → MX    → smtp.example.com  ✅
```

**CNAME ở zone apex** (`example.com`) bị cấm hoàn toàn vì apex bắt buộc có SOA + NS. Dùng ALIAS/ANAME thay thế.

---

## Câu 4 — Geo DNS Sai Region

**Q:** User HN query `api.shopee.com` nhận IP US thay vì SG. 3 nguyên nhân?

**A:**

1. **Recursive resolver của user ở US** — Geo DNS dùng IP của resolver, không phải user. `8.8.8.8` anycast có thể hit US node → trả IP US.

2. **Geo DNS database map sai** — IP range của ISP VN bị map nhầm sang US trong database của provider.

3. **Cache stale từ VPN** — User dùng VPN US trước đó → cache TTL chưa expire → vẫn nhận IP US.

Debug:
```bash
nslookup api.shopee.com 8.8.8.8   # resolver ở đâu?
nslookup whoami.akamai.net         # IP của resolver là gì?
```

---

## Câu 5 — Debug NXDOMAIN

**Q:** 2 giờ sáng, `api.company.com` trả NXDOMAIN nhưng web server vẫn chạy. Debug thế nào?

**A:**

Thứ tự check:
```bash
# 1. Domain còn hạn không? (hay gặp nhất)
whois company.com

# 2. NS record còn không?
nslookup -type=NS company.com

# 3. Authoritative NS còn trả đúng không?
nslookup api.company.com <authoritative-NS-IP>

# 4. NS servers còn sống không?
ping ns1.company.com
dig @ns1.company.com api.company.com
```

3 nguyên nhân phổ biến:
1. **Domain expired** — registrar xóa NS khỏi TLD → NXDOMAIN
2. **A record bị xóa nhầm** — audit log DNS provider, compare với backup
3. **Authoritative NS down** — DDoS hoặc misconfiguration

---

## Điểm cần nhớ cho quiz lần 2

1. TTL timing: hạ TTL trước **1 TTL cũ** (không phải ngay trước khi đổi)
2. CNAME không đứng cùng record khác — tách sang subdomain riêng
3. CNAME ở zone apex bị cấm — dùng ALIAS/ANAME
4. Geo DNS dùng IP của **resolver**, không phải user
5. Debug NXDOMAIN: whois → NS record → authoritative → ping NS
