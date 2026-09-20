# B+Tree

Session date: 2026-09-20
Bài đầu tiên của mảng Databases (Phase 1 — Foundations).

> Viết cho người đang implement B+Tree page-based, không phải người mới nghe tên.
> Mục 4-7 là phần dùng được ngay cho project.

---

## 1. Vì sao lại là B+Tree, không phải cây nhị phân

Câu hỏi thật sự không phải "cây nào tìm kiếm nhanh" mà là:

> **Dữ liệu nằm trên đĩa. Mỗi lần chạm đĩa tốn 100 micro giây.
> Làm sao chạm ít nhất có thể?**

```
Cây nhị phân cân bằng, 1 triệu bản ghi:
   chiều cao = log₂(1.000.000) ≈ 20
   → 20 lần chạm đĩa = 2.000 micro giây

B+Tree với fanout 340:
   chiều cao = log₃₄₀(1.000.000) ≈ 2,4  →  3 tầng
   → 3 lần chạm đĩa = 300 micro giây
```

> **Cây nhị phân tối ưu SỐ PHÉP SO SÁNH. B+Tree tối ưu SỐ LẦN CHẠM ĐĨA.**
> Khi một lần chạm đĩa đắt gấp 1000 lần một phép so sánh, bạn sẵn sàng
> so sánh nhiều hơn để chạm ít hơn.

Cách làm: **một node = một trang (page) = đơn vị I/O nhỏ nhất.**
Đã phải đọc 8KB rồi thì nhét vào đó càng nhiều khoá càng tốt.

---

## 2. Phép tính fanout — con số nên nằm trong đầu

```
Trang 8KB, khoá 16 byte, con trỏ 8 byte → mỗi entry 24 byte
Trừ header ~50 byte  →  (8192 - 50) / 24 ≈ 340 entry mỗi node
```

| Chiều cao | Số bản ghi chứa được | Lần chạm đĩa |
|---|---|---|
| 2 | ~115.000 | 2 |
| 3 | ~39 triệu | 3 |
| 4 | ~13 tỉ | 4 |

**Gần như mọi database trên đời đều có cây cao 3-4 tầng.** Và nếu buffer pool giữ
được node gốc + tầng 2 (chỉ vài MB), thì mỗi lần tra cứu chỉ tốn **đúng 1 lần
chạm đĩa thật**.

> **Tăng fanout = giảm chiều cao = giảm I/O.**
> Mọi kỹ thuật ở mục 5 đều nhằm nhét thêm khoá vào một trang.

---

## 3. Vì sao "B+" chứ không phải "B"

```
B-Tree:                          B+Tree:
  dữ liệu nằm ở MỌI node           dữ liệu CHỈ nằm ở LÁ
                                   node trong chỉ chứa khoá dẫn đường

     [10 | data]                        [10]
     /         \                       /    \
  [5|data]  [20|data]           [3,5]──▶[10,15]──▶[20,25]
                                  └─ lá nối với nhau bằng con trỏ
```

**① Node trong chứa được nhiều khoá hơn rất nhiều** ← lý do chính.
Không chứa dữ liệu thì mỗi entry chỉ tốn 24 byte thay vì 24 + kích thước bản ghi.
Fanout cao hơn → cây thấp hơn.

**② Quét khoảng cực rẻ.** Lá nối thành danh sách liên kết:
```
WHERE age BETWEEN 25 AND 35
→ tìm 25 (3 lần chạm đĩa) → đi ngang theo con trỏ lá, KHÔNG quay lại gốc
```
Với B-Tree phải đi lên đi xuống liên tục. Đây là lý do B+Tree thống trị database
quan hệ — SQL đầy `BETWEEN`, `ORDER BY`, `>`.

**③ Mọi truy vấn chi phí như nhau.** Luôn đi hết chiều cao → độ trễ ổn định,
dễ dự đoán. B-Tree trúng ở gốc thì nhanh, nhưng p99 khó đoán.

---

## 4. Bên trong một trang — slotted page

Textbook vẽ node như một mảng. Thực tế **không phải vậy**, vì khoá có độ dài
thay đổi.

```
┌──────────────────────────────────────────────────────┐
│ HEADER: loại node, số lượng entry, con trỏ anh em    │
├──────────────────────────────────────────────────────┤
│ MẢNG SLOT:  [→2100] [→1800] [→1500] ...              │  mọc từ trái sang
│             (offset tới dữ liệu, SẮP XẾP theo khoá)  │
├──────────────────────────────────────────────────────┤
│                                                      │
│                  KHOẢNG TRỐNG                        │
│                                                      │
├──────────────────────────────────────────────────────┤
│  ...  [khoá3|giá trị3] [khoá2|giá trị2] [khoá1|...]  │  mọc từ phải sang
└──────────────────────────────────────────────────────┘
```

Vì sao thiết kế này:

```
Chèn một entry mới ở giữa:
   Dữ liệu xếp tuần tự  → phải DỜI hàng nghìn byte
   Slotted page         → ghi dữ liệu vào chỗ trống bất kỳ
                          chỉ dời MẢNG SLOT (mỗi slot 2-4 byte)
                          → rẻ hơn 10-100 lần
```

> **Thứ tự nằm ở SLOT, không nằm ở DỮ LIỆU.**
> Mảng slot được sắp xếp, dữ liệu nằm lộn xộn. Tìm kiếm là nhị phân trên slot.

Xoá thì chỉ gỡ slot, để lại lỗ hổng. Lỗ hổng nhiều quá thì **compact** lại trang.

Postgres, InnoDB, SQLite đều dùng đúng cấu trúc này.

---

## 5. Ba mẹo tăng fanout mà database thật đều dùng

### ① Cắt bớt khoá ở node trong (suffix truncation)

Node trong chỉ cần **dẫn đường**, không cần khoá đầy đủ:

```
Lá trái có khoá lớn nhất:  "Nguyễn Văn Aaa"
Lá phải có khoá nhỏ nhất:  "Nguyễn Văn Bbb"

Khoá dẫn đường chỉ cần đủ để phân biệt  →  "Nguyễn Văn B"
```

Với khoá chuỗi dài, mẹo này tăng fanout **2-5 lần**.

### ② Nén tiền tố chung

```
user:1001:profile      Lưu tiền tố "user:10" MỘT LẦN
user:1002:profile  →   rồi chỉ lưu đuôi: "01:profile", "02:profile"...
user:1003:profile
```

### ③ Tách trang không cân khi chèn tăng dần   ★ quan trọng nhất trong thực tế

Khoá chính thường là số tự tăng:

```
Chèn 1, 2, 3, 4, ... theo thứ tự tăng dần

Tách 50/50 (sách giáo khoa):
   Trang cũ còn 50% và KHÔNG BAO GIỜ được chèn thêm nữa
   (mọi khoá mới đều lớn hơn, đều đi sang phải)
   → cây lãng phí VĨNH VIỄN 50% dung lượng

Tách 90/10 khi phát hiện chèn ở mép phải:
   Trang cũ giữ 90%, trang mới nhận 10% và tiếp tục nhận khoá mới
   → lấp đầy gần 100%
```

InnoDB, Postgres đều có tối ưu này. **Nếu B+Tree chèn khoá tự tăng mà vẫn tách
50/50, file sẽ phình gấp đôi so với cần thiết.**

---

## 6. Xoá — database thật không làm như sách

Sách dạy: node xuống dưới 50% thì **mượn từ anh em** hoặc **gộp lại**.

Thực tế:

```
PostgreSQL:  KHÔNG BAO GIỜ gộp node.
             Trang rỗng hoàn toàn mới được thu hồi (và phải qua VACUUM).

InnoDB:      Có gộp, nhưng ngưỡng rất thấp và hiếm khi kích hoạt.
```

Vì sao? **Gộp node là ác mộng của xử lý đồng thời.** Cần latch cùng lúc trên node
cha, node hiện tại và node anh em — dễ deadlock, dễ đụng thread đang đi xuống.
Cái giá đó không đáng so với chút dung lượng tiết kiệm được.

Hệ quả: **xoá nhiều bản ghi không làm file nhỏ lại.** Phải rebuild index.

> **Cho project:** cứ để node underfull. Đánh dấu trang rỗng vào danh sách trang
> tự do để tái sử dụng. Đừng viết code gộp node ở phiên bản đầu — tốn 80% công
> sức để lấy về 5% giá trị.

---

## 7. Xử lý đồng thời — phần khó nhất

Phân biệt trước:

```
LATCH  — bảo vệ CẤU TRÚC DỮ LIỆU trong bộ nhớ
         giữ vài micro giây, không phát hiện deadlock
         → chính là mutex ở bài Synchronization

LOCK   — bảo vệ DỮ LIỆU LOGIC của giao dịch
         giữ suốt transaction, có phát hiện deadlock
         → chuyện của bài Transaction
```

Mục này nói về **latch**.

### Cách 1 — Latch crabbing (bò như cua)

```
ĐỌC:
   khoá gốc → khoá con → NHẢ GỐC → khoá cháu → NHẢ CON → ...
   Luôn giữ đúng 2 latch. Như cua bò: chân sau nhả khi chân trước đã bám.

GHI:
   khoá theo đường xuống, chỉ NHẢ TẤT CẢ tổ tiên khi gặp node "AN TOÀN"
   (an toàn = còn chỗ trống → chèn vào đây chắc chắn không gây tách lan lên trên)
```

Vấn đề: **node gốc thành nút thắt.** Ở 64 core, đây là tường chắn cứng.

### Cách 2 — Optimistic Lock Coupling (cách hiện đại)

```
Mỗi node có một BỘ ĐẾM PHIÊN BẢN.

Đi xuống mà KHÔNG khoá gì cả:
   1. đọc phiên bản của node
   2. đọc nội dung, chọn con để đi tiếp
   3. đọc lại phiên bản — có đổi không?
        không đổi  → dữ liệu vừa đọc hợp lệ, đi tiếp
        đã đổi     → có ai vừa sửa → QUAY LẠI TỪ ĐẦU
```

Đọc hoàn toàn không cần latch. Chỉ thao tác ghi mới khoá, và chỉ khoá đúng node
nó sửa.

### Cách 3 — B-link tree (mẹo đẹp nhất)

Thêm vào mỗi node: **con trỏ sang phải** + **khoá cao nhất** của node đó.

```
Thread A đang đọc node X.
Thread B tách X, nửa sau chuyển sang node mới Y.

A tra khoá K, thấy K > khoá_cao_nhất(X)
   → "à, chỗ này vừa bị tách, thứ tôi cần đã dọn sang phải"
   → đi theo con trỏ phải sang Y.  ✅ KHÔNG CẦN KHOÁ GÌ.
```

Cây tự mô tả được trạng thái "đang tách dở" → thread đọc **không bao giờ cần
chặn**. Postgres dùng B-link tree.

---

## 8. Độ bền — nối thẳng vào bài Virtual Memory

```
① WAL               ghi nhật ký trước → fsync MỘT lần tuần tự
                    (bài Virtual Memory, mục 5)

② Chống torn page   trang 8KB bị ghi dở → cây hỏng
                    full-page-write / doublewrite / copy-on-write
                    (bài Virtual Memory, mục 6)

③ Page LSN          mỗi trang ghi "tôi đã áp dụng tới bản ghi log số mấy"
                    → khởi động lại biết trang nào cần replay, trang nào bỏ qua
```

Điểm ③ hay thiếu ở B+Tree tự viết. Không có nó, khi replay log bạn không biết
thao tác nào đã kịp xuống đĩa — nên hoặc replay thiếu (mất dữ liệu), hoặc replay
thừa (áp dụng hai lần).

---

## 9. Đánh đổi: B+Tree và LSM Tree

```
                    B+Tree              LSM Tree
Ghi                 ngẫu nhiên          tuần tự (nhanh hơn nhiều trên HDD)
Khuếch đại ghi      ~10-30x             ~10-30x (nhưng do compaction)
Khuếch đại đọc      ~1 (đi thẳng)       cao (phải xem nhiều tầng)
Quét khoảng         xuất sắc            khá (phải trộn các tầng)
Dung lượng          ~50-70% lấp đầy     nén tốt hơn
Độ trễ p99          ổn định             giật khi compaction chạy
```

```
Đọc nhiều, quét khoảng nhiều, cần p99 ổn định → B+Tree   (Postgres, MySQL)
Ghi nhiều, ghi tuần tự, chấp nhận p99 giật    → LSM Tree (RocksDB, Cassandra)
```

Nhớ điều đã nói ở bài File System: **NVMe làm ghi ngẫu nhiên rẻ đi nhiều**, nên
lợi thế lịch sử của LSM đã thu hẹp đáng kể.

---

## 10. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- Lý do tồn tại là **giảm số lần chạm đĩa**, không phải "cây cân bằng"
- Tính được **fanout và chiều cao** từ kích thước trang
- Vì sao dữ liệu chỉ ở lá, và lá nối với nhau (range scan)
- **Latch khác lock** — rất ít ứng viên phân biệt được
- Biết database thật **không gộp node** khi xoá, và vì sao
- So sánh B+Tree vs LSM theo khuếch đại đọc/ghi/dung lượng

**Sai lầm thường gặp:**
- Nói "B+Tree nhanh vì O(log n)" mà không nhắc tới I/O
- Không biết tách 50/50 làm phình file với khoá tự tăng
- Nghĩ xoá làm file nhỏ lại
- Nhầm latch với lock

---

## 11. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. Vì sao B+Tree thắng cây nhị phân trên đĩa? Trả lời bằng đơn vị "lần chạm đĩa".
2. Trang 8KB, khoá 16B, con trỏ 8B → fanout bao nhiêu? Cao 3 tầng chứa được bao nhiêu bản ghi?
3. Vì sao node trong không chứa dữ liệu?
4. Vì sao slotted page dùng mảng slot thay vì xếp dữ liệu tuần tự?
5. Kể 3 mẹo tăng fanout.
6. Chèn khoá tự tăng thì tách trang thế nào? Vì sao không tách 50/50?
7. Vì sao Postgres không gộp node khi xoá?
8. Latch khác lock chỗ nào?
9. B-link tree cho phép đọc không bị chặn bằng cách nào?
10. Page LSN dùng để làm gì khi khôi phục?

---

## 12. Bài tập

**Implementation (cho project đang làm):**
- M1: đo fanout thực tế của trang hiện tại; tính chiều cao cây với 1M, 10M, 100M bản ghi
- M2: thêm tách 90/10 khi phát hiện chèn ở mép phải; so sánh kích thước file khi chèn 1M khoá tự tăng, trước và sau
- M3: thêm suffix truncation cho node trong; đo fanout tăng bao nhiêu với khoá chuỗi
- M4: thêm con trỏ anh em phải + khoá cao nhất (B-link); viết test quét khoảng

**System design:** thiết kế index cho bảng 500 triệu bản ghi, truy vấn chủ yếu là
`WHERE created_at BETWEEN ? AND ? AND status = ?`. Chọn khoá index thế nào?
Clustered hay secondary? Fanout bao nhiêu, cây cao mấy tầng? Buffer pool cần bao
nhiêu RAM để mỗi truy vấn chỉ tốn 1 lần chạm đĩa?
