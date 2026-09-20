# LSM Tree

Session date: 2026-09-20
Bài thứ hai của mảng Databases. Đối trọng trực tiếp của B+Tree (`01-btree.md`).

---

## 1. Vấn đề nó giải quyết

B+Tree có một điểm yếu cố hữu: **mỗi lần ghi là sửa tại chỗ, ở vị trí ngẫu
nhiên trên đĩa.**

```
Ghi khoá "user:88421" → tìm đúng trang lá chứa nó → sửa tại chỗ
Ghi khoá "user:12003" → trang lá hoàn toàn khác, cách xa trên đĩa
Ghi khoá "user:55019" → lại một trang khác nữa

→ GHI NGẪU NHIÊN. Trên HDD: ~150 IOPS (đã học ở bài File System).
```

LSM Tree đặt cược ngược lại: **đừng bao giờ sửa tại chỗ. Chỉ ghi thêm vào cuối.**

```
Mọi thao tác ghi → chỉ APPEND vào cuối một file đang mở
→ GHI TUẦN TỰ. Trên HDD: ~200 MB/s, nhanh hơn ngẫu nhiên tới 300 lần.
```

Đánh đổi cốt lõi, không miễn phí: **ghi rẻ đi, nhưng đọc phải trả giá, và có
một tiến trình nền (compaction) phải dọn dẹp liên tục.**

---

## 2. Kiến trúc — ba tầng

```
GHI:
   client ──▶ ① WAL (append, fsync)  ──▶ ② MemTable (cây trong RAM, có thứ tự)
                    │
              (an toàn khi crash)     đầy → flush thành file bất biến

ĐỌC:
   client ──▶ tìm ② MemTable trước
                    │  không thấy
                    ▼
              tìm ③ SSTable mới nhất → cũ hơn → cũ hơn nữa ...
```

**① WAL** — giống hệt WAL của B+Tree: ghi log trước, fsync một lần, sống sót
qua crash trước khi MemTable kịp flush.

**② MemTable** — cấu trúc có thứ tự trong RAM (skip list hoặc red-black tree).
Ghi cực nhanh vì không chạm đĩa. Đọc cũng tra được ngay vì có thứ tự.

**③ SSTable (Sorted String Table)** — khi MemTable đầy (thường 4-64MB), ghi ra
đĩa thành một file **bất biến**: đã sắp xếp theo khoá, ghi tuần tự một lần, và
**không bao giờ bị sửa nữa**.

```
Ghi user:88421 → MemTable (RAM)
Ghi user:12003 → MemTable (RAM)
... (đầy 32MB) ...
FLUSH → SSTable-001 (đĩa, bất biến, đã sắp xếp)

Ghi tiếp → MemTable mới (RAM)
... đầy nữa ...
FLUSH → SSTable-002 (đĩa, bất biến)
```

> **Tính bất biến là chìa khoá của cả thiết kế.** File không đổi thì không cần
> latch phức tạp khi đọc, không sợ torn page (không ai ghi vào nữa), và nén cực
> tốt vì dữ liệu đã yên vị.

---

## 3. Cái giá của đọc — vấn đề đầu tiên phải trả lời

Một khoá có thể tồn tại ở **nhiều nơi cùng lúc**: MemTable, SSTable-050,
SSTable-023, SSTable-004... vì mỗi lần ghi/sửa lại tạo bản ghi mới ở tầng mới nhất.

```
Tìm "user:12003":
   MemTable       → không có
   SSTable-050    → không có
   SSTable-049    → không có
   ...
   SSTable-004    → CÓ! (nhưng phải kiểm tra hết 46 file trước đó)

WORST CASE: phải chạm TẤT CẢ SSTable → tệ hơn B+Tree rất nhiều
```

Gọi là **read amplification** — một lần đọc logic sinh ra nhiều lần đọc vật lý.
Ba cơ chế dựng lên chỉ để giải quyết vấn đề này.

---

## 4. Bloom Filter — trả lời "chắc chắn không có" trong O(1)

```
Mỗi SSTable kèm một Bloom Filter — cấu trúc xác suất nhỏ gọn (~10 bit/khoá)

filter.check("user:12003")
   → "CHẮC CHẮN KHÔNG CÓ"     → bỏ qua SSTable này, KHÔNG cần đọc đĩa  ✅
   → "CÓ THỂ CÓ"              → phải đọc SSTable để kiểm tra thật
                                (có thể là false positive)
```

Bloom Filter **không bao giờ nói sai kiểu "không có" khi thực ra có** — chỉ có
thể nói "có thể có" nhầm (false positive), không bao giờ "chắc chắn không" nhầm
(false negative). Đủ để loại bỏ phần lớn SSTable mà không cần chạm đĩa.

```
Không có Bloom Filter, 50 SSTable: worst case 50 lần đọc đĩa
Có Bloom Filter (false positive rate 1%): trung bình ~1 lần đọc đĩa thật
```

RocksDB, Cassandra không thể thiếu Bloom Filter — biến "phải xem hết mọi tầng"
thành "gần như chỉ xem đúng tầng có dữ liệu".

---

## 5. Sparse Index — không cần index từng khoá

Mỗi SSTable đã **sắp xếp**, nên chỉ cần lưu vị trí khoá đầu **mỗi khối** (block,
thường 4KB), không cần lưu vị trí từng khoá:

```
Sparse index của SSTable-050:
   "user:00001" → offset 0
   "user:00512" → offset 4096
   "user:01203" → offset 8192
   ...

Tìm "user:00700":
   nhị phân trên sparse index → nằm giữa offset 4096 và 8192
   → đọc đúng khối 4KB đó, quét tuyến tính trong khối
```

Sparse index nhỏ (vài trăm KB cho SSTable vài GB) → **luôn nằm gọn trong RAM**.
Lý do LSM Tree không cần buffer pool phức tạp như B+Tree.

---

## 6. Compaction — cái giá thật sự của LSM Tree

Không dọn dẹp thì số SSTable tăng vô hạn, đọc ngày càng chậm, bản ghi cũ (bị
ghi đè/xoá) chiếm chỗ mãi mãi.

```
Xoá một khoá trong LSM Tree KHÔNG XOÁ GÌ CẢ.
Nó ghi thêm một "TOMBSTONE" — bản ghi đánh dấu "đã xoá".

Compaction mới là lúc TOMBSTONE thật sự dọn dữ liệu cũ đi.
```

**Compaction = trộn nhiều SSTable cũ thành SSTable mới, loại bỏ bản trùng và
tombstone.**

Hai chiến lược chính — **đánh đổi trung tâm**, không có cách nào thắng cả ba
mặt cùng lúc:

```
SIZE-TIERED (Cassandra, ScyllaDB mặc định)
   Gộp các SSTable CÙNG CỠ khi đủ số lượng
   ✅ Ghi rẻ — ít phải viết lại dữ liệu
   ❌ Đọc đắt — nhiều SSTable cùng tồn tại cùng lúc
   ❌ Tốn dung lượng tạm thời gấp đôi lúc compact

LEVELED (RocksDB, LevelDB mặc định)
   Chia thành LEVEL (L0, L1, L2...), mỗi level lớn gấp ~10 lần level trước
   Trong mỗi level (trừ L0), các SSTable KHÔNG chồng lấn khoảng khoá
   ✅ Đọc rẻ hơn — khoá chỉ nằm ở nhiều nhất 1 SSTable/level
   ✅ Ít tốn dung lượng dư
   ❌ Ghi đắt hơn nhiều — một khoá có thể bị viết lại qua nhiều level
```

```
Write Amplification thực tế:
   Size-tiered:  ~10-30x
   Leveled:      ~10-30x (thậm chí cao hơn)

Đây chính là "khuếch đại ghi" ở bài File System, chỉ khác nguồn gốc:
   B+Tree:    khuếch đại ghi từ GC của SSD (ghi 8KB → SSD ghi thật ~1MB)
   LSM Tree:  khuếch đại ghi từ COMPACTION (ghi 1 lần → viết lại qua nhiều tầng)
```

> **Compaction chạy nền, tốn CPU và I/O, và CẠNH TRANH TRỰC TIẾP với traffic
> ghi/đọc đang phục vụ user.** Đây là nguồn gốc của p99 latency giật cục.
> Cấu hình sai có thể gây "compaction storm": ghi dồn ứ chờ compaction theo kịp.

---

## 7. Vì sao HDD ưu ái LSM, còn NVMe thì không rõ ràng nữa

```
Trên HDD:  ghi tuần tự nhanh hơn ghi ngẫu nhiên ~300 lần
           → dù LSM ghi lại nhiều lần (write amplification 10-30x)
           → 300 / 20 ≈ vẫn thắng B+Tree đậm

Trên NVMe: ghi tuần tự chỉ nhanh hơn ghi ngẫu nhiên ~3 lần
           → LSM ghi lại 10-30 lần do compaction
           → 3 / 20 ≈ THUA B+Tree về tổng lượng I/O thật
```

Lý do các engine mới cho NVMe (WiscKey, B-Tree hiện đại) đang thu hẹp khoảng
cách. Nhưng LSM Tree vẫn thắng rõ ràng ở khía cạnh không phụ thuộc loại đĩa:
**nén tốt hơn nhiều** — dữ liệu sắp xếp và nén theo khối lớn, còn B+Tree phải
chừa chỗ trống để chèn (thường chỉ lấp đầy 50-70%).

---

## 8. Bảng đối chiếu — B+Tree vs LSM Tree

| | B+Tree | LSM Tree |
|---|---|---|
| Ghi | Ngẫu nhiên, tại chỗ | Tuần tự, append-only |
| Đọc 1 khoá | ~1 lần chạm đĩa (đi thẳng) | Có thể nhiều SSTable (giảm nhờ Bloom Filter) |
| Xoá | Sửa tại chỗ, giải phóng ngay (không co file) | Tombstone, dọn khi compaction |
| Write amplification | ~10-30x (GC của SSD) | ~10-30x (compaction) |
| Read amplification | Thấp, ổn định | Cao hơn, giảm nhờ Bloom Filter + sparse index |
| Dung lượng | 50-70% lấp đầy | Nén tốt, ít dư thừa |
| Độ trễ | Ổn định, dễ đoán | Giật khi compaction chạy |
| Range scan | Xuất sắc (lá liên kết) | Khá — phải trộn nhiều tầng đã sắp xếp |
| Ví dụ thật | PostgreSQL, MySQL/InnoDB | RocksDB, Cassandra, LevelDB, HBase |

---

## 9. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- Đánh đổi cốt lõi: **ghi rẻ đổi lấy đọc đắt hơn + cần compaction**
- Bloom Filter giải quyết vấn đề gì cụ thể (không phải chỉ "để nhanh hơn")
- Phân biệt **size-tiered vs leveled compaction** và đánh đổi của mỗi cái
- Compaction là nguồn gốc của **p99 giật**, không phải điều bất ngờ
- Liên hệ write amplification ở đây với write amplification của SSD (hai nguồn
  khác nhau, cùng khái niệm)

**Sai lầm thường gặp:**
- Nói "LSM Tree nhanh hơn B+Tree" mà không nói rõ nhanh ở khía cạnh nào
- Quên rằng xoá trong LSM không giải phóng dung lượng ngay
- Không biết compaction cạnh tranh tài nguyên với traffic thật

---

## 10. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. Vì sao LSM Tree ghi nhanh hơn B+Tree? Đơn vị đo là gì?
2. MemTable đầy thì chuyện gì xảy ra? SSTable khác gì trang B+Tree?
3. Một khoá đọc có thể phải tìm ở bao nhiêu SSTable trong trường hợp xấu nhất?
4. Bloom Filter trả lời được câu hỏi gì? Sai theo chiều nào, không sai theo chiều nào?
5. Sparse index khác gì lưu vị trí từng khoá? Vì sao làm được vậy?
6. Xoá một khoá trong LSM Tree thực chất làm gì?
7. Size-tiered và leveled compaction khác nhau ở đâu? Mỗi cái đánh đổi gì?
8. Vì sao compaction gây ra p99 giật cục?
9. Trên NVMe, lợi thế của LSM Tree so với B+Tree còn rõ như trên HDD không? Vì sao?

---

## 11. Bài tập

**Implementation:** viết một LSM Tree tối giản bằng Python — M1: WAL + MemTable
(dict/sorted structure) + flush thành SSTable JSON khi đầy; M2: đọc theo thứ tự
MemTable → SSTable mới nhất → cũ nhất; M3: thêm Bloom Filter đơn giản cho mỗi
SSTable; M4: compaction gộp 2 SSTable cũ nhất, loại bỏ tombstone + bản trùng.

**System design:** thiết kế storage layer cho một time-series database ghi
1 triệu điểm dữ liệu/giây, đọc chủ yếu theo khoảng thời gian gần đây. Chọn
LSM hay B+Tree? Chiến lược compaction nào? Bloom Filter cấu hình false positive
rate bao nhiêu là hợp lý? Compaction chạy khi nào để không ảnh hưởng traffic giờ cao điểm?
