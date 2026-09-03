# gRPC

Session date: 2026-08-27

> Bài cuối của Phase 1 — Networking. Cùng cách viết với CDN và WebSocket:
> gọn, kết bằng checklist tự kiểm tra.

---

## 1. Vấn đề nó giải quyết

REST/JSON tốt cho API công khai. Nhưng khi có **200 microservice gọi nhau hàng
triệu lần mỗi giây**, những điểm yếu này thành nghiêm trọng:

```
❌ Không có hợp đồng bắt buộc
   Backend đổi "userId" → "user_id"
   Client vẫn build được, vẫn deploy được, chỉ CHẾT LÚC CHẠY THẬT.
   Không gì phát hiện được ở compile time.

❌ Text quá tốn kém
   {"user_id":12345,"active":true}  = 31 byte
   × 10 tỷ request/ngày → hàng terabyte băng thông chỉ để truyền TÊN FIELD,
   lặp lại y nguyên hàng tỷ lần.

❌ Không có streaming thật sự
   Trả 1 triệu bản ghi → gói hết vào một response khổng lồ, hoặc tự chế phân trang.

❌ Client phải viết tay
   Mỗi service mới → mỗi ngôn ngữ viết lại client thủ công.
```

**gRPC:** định nghĩa service một lần trong `.proto` → **sinh tự động** code
client + server cho 10+ ngôn ngữ → truyền **Protobuf nhị phân** trên **HTTP/2**.

```protobuf
service UserService {
  rpc GetUser (GetUserRequest) returns (User);
}

message User {
  int64  id     = 1;      // ← con số này quan trọng hơn cái tên
  string name   = 2;
  bool   active = 3;
}
```

---

## 2. Protobuf — giá trị thật nằm ở đây

**Trên đường truyền, TÊN FIELD KHÔNG ĐƯỢC GỬI ĐI.** Chỉ có **số hiệu field**:

```
JSON:      {"user_id":12345,"active":true}     31 byte
                └─ 9 byte chỉ để nói "đây là user_id", gửi lại mỗi request

Protobuf:  08 B9 60 18 01                       5 byte
           │  └──┘  │  └─ giá trị true
           │   │    └─ field 3, kiểu varint
           │   └─ 12345 mã hoá varint
           └─ field 1, kiểu varint

Nhỏ hơn 6 lần. Parse nhanh hơn nhiều — không phân tích cú pháp text.
```

### Quy tắc tiến hoá schema — phần interviewer hay đào

```
✅ ĐƯỢC PHÉP:
   Thêm field mới với số hiệu MỚI     → client cũ bỏ qua field lạ, vẫn chạy
   Đổi TÊN field (giữ nguyên số hiệu) → trên dây chỉ có số, tên không đi đâu cả
   Xoá field → nhưng PHẢI đánh dấu:  reserved 3;  reserved "old_field";

❌ TUYỆT ĐỐI KHÔNG:
   Đổi số hiệu của field đang dùng
   Tái sử dụng số hiệu của field đã xoá   ← lỗi kinh điển, hỏng dữ liệu ÂM THẦM
   Đổi kiểu dữ liệu không tương thích
```

Vì sao tái sử dụng số hiệu nguy hiểm:

```
v1:  int64 user_id = 3;
v2:  xoá user_id, dùng lại số 3 cho:  string email = 3;

Một service cũ chưa deploy vẫn gửi user_id=12345 ở field 3
Service mới đọc field 3 → cố hiểu thành string
→ dữ liệu rác, hoặc crash. KHÔNG CÓ CẢNH BÁO NÀO.
```

> **Số hiệu field là hợp đồng vĩnh viễn. Tên field chỉ là thứ cho con người đọc.**

---

## 3. Vì sao bắt buộc HTTP/2

```
Multiplexing     → hàng nghìn RPC song song trên MỘT connection
                   (HTTP/1.1 thì mỗi request chiếm trọn một connection)
HPACK            → header nén; metadata lặp đi lặp lại gần như miễn phí
Stream hai chiều → ánh xạ trực tiếp thành streaming RPC
Connection lâu   → không bắt tay TCP + TLS lại cho từng lời gọi
                   (nhớ 4 round-trip ở câu 1 mock interview)
```

Nhưng **thừa hưởng nhược điểm**: vẫn là **TCP head-of-line blocking**. Mất một
gói thì **mọi RPC đang bay trên connection đó cùng đứng hình** — đúng bài học
câu 4 mock interview. Vì thế mới có gRPC trên QUIC đang dần xuất hiện.

---

## 4. Bốn kiểu gọi

```
UNARY                 Client ──req──▶ Server
                      Client ◀─resp── Server        (giống REST)

SERVER STREAMING      Client ──req──▶ Server
                      Client ◀─resp── Server        tải file, theo dõi log,
                      Client ◀─resp── Server        kết quả tìm kiếm dần dần
                      Client ◀─resp── Server

CLIENT STREAMING      Client ──req──▶ Server        upload, gom số liệu,
                      Client ──req──▶ Server        ghi cảm biến hàng loạt
                      Client ◀─resp── Server

BIDIRECTIONAL         Client ──req──▶ Server        chat, đồng bộ realtime,
                      Client ◀─resp── Server        vị trí tài xế
                      Client ──req──▶ Server        (hai chiều ĐỘC LẬP,
                      Client ◀─resp── Server         không cần luân phiên)
```

---

## 5. Deadline propagation — thứ đáng giá nhất trong gRPC

Giải quyết trực tiếp vấn đề "hàng đợi toàn request đã chết" ở buổi Load Balancer:

```
Client đặt deadline 500ms
        │
        ▼
Service A nhận, còn 480ms ──▶ gọi Service B, TRUYỀN TIẾP deadline còn lại
                                      │
                                      ▼
                        Service B còn 400ms ──▶ gọi Service C, còn 380ms
                                                        │
                                                        ▼
                                        Service C thấy chỉ còn 380ms
                                        Biết query này cần 2 giây
                                        → HUỶ LUÔN, không thèm chạy
                                        → trả DEADLINE_EXCEEDED
```

**Không có deadline propagation:** client đã bỏ đi từ giây 0.5, nhưng C vẫn cắm
cúi chạy query 2 giây, giữ connection DB, tốn CPU — để tạo ra kết quả **không ai
còn chờ nữa**. Đúng hiện tượng lãng phí 100% ở câu 5 buổi Load Balancer.

> `timeout` chỉ bảo vệ MỘT CHẶNG. `deadline` bảo vệ TOÀN BỘ CHUỖI.

Kèm theo là **status code riêng** (không dùng mã HTTP): `OK`,
`DEADLINE_EXCEEDED`, `UNAVAILABLE`, `RESOURCE_EXHAUSTED`, `FAILED_PRECONDITION`...
Quan trọng vì nó cho biết **có nên retry không**: `UNAVAILABLE` thì nên,
`INVALID_ARGUMENT` thì retry bao nhiêu lần cũng vô ích.

---

## 6. Cái bẫy load balancing — phần quan trọng nhất

Điểm mà **hầu hết ứng viên trả lời sai**, nối thẳng vào bài Load Balancer:

```
gRPC dùng MỘT connection HTTP/2 sống lâu, ghép hàng nghìn RPC vào đó.

LB tầng L4 cân bằng cái gì? CONNECTION.
gRPC gửi cái gì? REQUEST bên trong MỘT connection.

Kết quả:
   Client 1 ──[1 connection, 10.000 RPC/s]──▶ Server A   ← cháy
   Client 2 ──[1 connection,     10 RPC/s]──▶ Server B   ← ngồi chơi
   Client 3 ──[1 connection,     50 RPC/s]──▶ Server C   ← ngồi chơi

   LB nói: "hoàn hảo, mỗi server đúng 1 connection!"
   Thực tế: lệch tải khủng khiếp.
```

Tệ hơn: **thêm server mới thì không có gì xảy ra.** Connection đã dựng rồi cứ thế
chạy tiếp — y hệt bài toán connection sống lâu ở buổi Load Balancer.

**Ba cách chữa:**

```
1. Proxy hiểu gRPC (L7) — Envoy, Linkerd, nginx có module gRPC
   Cân bằng theo TỪNG RPC, không theo connection.    ★ phổ biến nhất

2. Client-side load balancing
   Client tự phân giải TẤT CẢ địa chỉ backend, mở nhiều subchannel,
   tự round-robin. Không cần proxy → bớt một chặng mạng.
   (cách Google dùng nội bộ)

3. MAX_CONNECTION_AGE
   Server chủ động đóng connection sau ~30 phút → client buộc nối lại
   → LB có cơ hội phân phối lại. Vá tạm nhưng rất hiệu quả.
```

---

## 7. Khi nào KHÔNG nên dùng gRPC

| Tình huống | Vì sao |
|---|---|
| **API công khai cho bên thứ ba** | Dev bên ngoài muốn `curl` được, đọc được JSON. Ép dùng protobuf = ma sát lớn |
| **Gọi trực tiếp từ trình duyệt** | JS không điều khiển được frame HTTP/2 thô → phải dùng **gRPC-Web** + proxy chuyển đổi |
| **Team nhỏ, ít service** | Chi phí codegen, build pipeline không đáng |
| **Debug là ưu tiên** | Nhị phân không đọc bằng mắt; cần `grpcurl` + server reflection |

**Nên dùng khi:** service gọi service nội bộ, nhiều ngôn ngữ, lưu lượng lớn,
cần streaming, cần hợp đồng chặt.

---

## 8. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- Biết **cái bẫy L4 LB** — câu phân loại rõ nhất
- Nói được **quy tắc tiến hoá schema** (số hiệu vĩnh viễn, `reserved`)
- Nhắc **deadline propagation**, không chỉ "timeout"
- Biết trình duyệt cần **gRPC-Web**
- Không tôn sùng gRPC — nói được khi nào REST tốt hơn

**Sai lầm thường gặp:**
- Vẽ gRPC sau một NLB rồi tưởng đã cân bằng tải
- Tái sử dụng số hiệu field đã xoá
- Nghĩ browser gọi gRPC trực tiếp được
- Dùng gRPC cho API công khai

---

## 9. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. Trên đường truyền, Protobuf gửi tên field hay số hiệu field? Hệ quả là gì?
2. Đổi tên một field có phá vỡ tương thích không? Vì sao?
3. Vì sao tuyệt đối không tái sử dụng số hiệu field đã xoá?
4. gRPC bắt buộc HTTP/2 vì tính năng nào? Thừa hưởng nhược điểm nào?
5. Kể 4 kiểu gọi và một ví dụ thực tế cho mỗi kiểu.
6. `deadline` khác `timeout` chỗ nào? Cứu ta khỏi vấn đề gì đã gặp ở buổi trước?
7. Vì sao đặt gRPC sau L4 LB gây lệch tải? Ba cách chữa?
8. Vì sao browser không gọi gRPC trực tiếp được?

---

## 10. Bài tập

**Implementation:** viết một service gRPC bằng Python — M1 unary `GetUser`;
M2 server streaming `ListUsers`; M3 interceptor ghi log + đo thời gian;
M4 deadline và xử lý `DEADLINE_EXCEEDED` đúng cách.

**System design:** thiết kế lớp giao tiếp nội bộ cho hệ thống 50 microservice.
Service nào dùng gRPC, service nào dùng REST, service nào dùng message queue?
Cân bằng tải ra sao? Quản lý phiên bản `.proto` thế nào khi 20 team cùng sửa?
