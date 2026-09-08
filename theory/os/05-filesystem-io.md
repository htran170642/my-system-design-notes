# File Systems & I/O

Session date: 2026-08-27
Bài cuối của mảng Operating Systems (Phase 1 — Foundations).

> Viết theo cách chậm hơn 4 bài trước (giải thích từng bước, ít thuật ngữ dồn).
> Nền trực tiếp cho WAL, B+Tree và LSM Tree ở Phase 2.

---

## 1. File system thực chất làm gì

Đĩa chỉ biết một việc: **"đưa tao số thứ tự của khối, tao trả về 4KB"**.
Nó không biết file, không biết thư mục, không biết tên.

File system là lớp phiên dịch:

```
Bạn nói:      "mở /home/hieptt/data.db"
                        │
File system:   tra tên → tìm ra INODE số 8472
               inode ghi: "file này nằm ở các khối 100-500, 2000-2100"
                        │
Đĩa:          "khối 100 đây"
```

Hai thứ nằm **tách rời** nhau — điều này gây ra cái bẫy ở mục 3:

```
INODE       = nội dung + thông tin file (kích thước, quyền, khối nào)
DIRECTORY   = một bảng ánh xạ  "data.db" → inode 8472
```

**Tên file KHÔNG nằm trong file. Nó nằm trong thư mục.**

---

## 2. Đường đi của một byte khi bạn ghi

Hình quan trọng nhất của bài — **mỗi tầng là một chỗ có thể mất dữ liệu**:

```
   buffer trong chương trình bạn
            │  write()
            ▼
   ① PAGE CACHE (RAM của kernel)        ← mất điện: MẤT
            │  writeback / fsync
            ▼
   ② File system + block layer
            │
            ▼
   ③ CACHE TRONG Ổ ĐĨA (RAM trên ổ)     ← mất điện: VẪN CÓ THỂ MẤT!
            │  FLUSH
            ▼
   ④ NAND / đĩa từ thật sự              ← an toàn
```

Tầng ③ hay bị bỏ sót. Ổ SSD/HDD **có RAM riêng**. Ổ nhận dữ liệu, nhét vào RAM
của nó, rồi báo "xong" — dù chưa ghi thật.

`fsync()` đúng chuẩn phải gửi thêm lệnh **FLUSH** xuống ổ để ép ghi hết ra NAND.
Một số ổ giá rẻ **nói dối**: nhận lệnh flush, trả lời "xong" ngay, thực ra chưa
ghi. Đó là lý do SSD dùng cho server có **tụ điện dự phòng** — đủ điện ghi nốt
phần trong RAM khi mất điện đột ngột.

---

## 3. ★ Cái bẫy: `fsync` file là chưa đủ

Lỗi kinh điển, bắt nguồn từ chuyện "tên file nằm ở thư mục" ở mục 1:

```c
fd = open("data.db", O_CREAT|O_WRONLY);
write(fd, data, size);
fsync(fd);          // ✅ nội dung file đã an toàn
close(fd);
// mất điện ngay lúc này
```

Khởi động lại: **file không tồn tại.**

`fsync(fd)` chỉ đảm bảo **nội dung** xuống đĩa. Nhưng dòng
`"data.db" → inode 8472` nằm trong **thư mục** — một file khác, chưa được fsync.

```
Có nội dung, nhưng không ai biết tên nó là gì → coi như không tồn tại.
```

Cách đúng:

```c
fsync(fd);                              // nội dung file
dir = open("/home/hieptt", O_RDONLY);
fsync(dir);                             // ← BẮT BUỘC, đăng ký cái tên
```

> **Tạo file mới hoặc đổi tên file thì phải `fsync` cả thư mục cha.**
> Rất nhiều storage engine tự viết quên bước này, chỉ lộ ra khi mất điện thật.

**`fdatasync()`** chỉ ghi nội dung, bỏ qua metadata không quan trọng (thời gian
sửa đổi). Nhanh hơn `fsync` một chút. Dùng được khi kích thước file không đổi —
ví dụ ghi đè trang trong B+Tree.

---

## 4. File system cũng có nhật ký riêng

**ext4 giải quyết vấn đề của nó bằng đúng cách bạn giải quyết vấn đề của B+Tree.**

```
Xoá một file = sửa 3 chỗ: đánh dấu khối trống, xoá inode, xoá tên trong thư mục
Mất điện giữa chừng → file system rác

→ ext4 ghi NHẬT KÝ trước, rồi mới sửa thật.  Y hệt WAL.
```

Ba chế độ của ext4:

```
data=ordered   (mặc định)  chỉ ghi nhật ký METADATA, nhưng đảm bảo
                           dữ liệu xuống đĩa TRƯỚC metadata
                           → cân bằng tốt nhất

data=journal               ghi nhật ký cả DỮ LIỆU
                           → an toàn nhất, nhưng ghi MỌI THỨ HAI LẦN

data=writeback             không đảm bảo thứ tự
                           → nhanh nhất, có thể đọc ra rác sau khi crash
```

Nghĩa là dữ liệu có thể bị ghi **hai lần** (nhật ký của bạn + nhật ký của ext4)
trước khi tới đĩa.

---

## 5. Direct I/O — khi database bảo kernel "tránh ra"

```
Bình thường:  chương trình → PAGE CACHE → đĩa
O_DIRECT:     chương trình ─────────────→ đĩa      (bỏ qua page cache)
```

Vì sao database muốn bỏ qua page cache:

```
① CACHE HAI LẦN, TỐN RAM GẤP ĐÔI
   Buffer pool của bạn giữ trang X
   Page cache của kernel CŨNG giữ trang X
   → RAM 8GB dùng được chỉ như 4GB

② BẠN BIẾT RÕ HƠN KERNEL
   Bạn biết trang gốc của B+Tree là nóng nhất.
   Kernel dùng LRU chung, có thể vứt nó đi vì một lệnh `cp` file lớn.

③ KIỂM SOÁT THỜI ĐIỂM GHI
   Không qua page cache thì không có trang bẩn nằm chờ → thứ tự rõ ràng.
```

Cái giá: `O_DIRECT` **rất khó tính**.

```
Buffer phải căn biên 512B hoặc 4KB   (posix_memalign, KHÔNG dùng malloc)
Kích thước đọc/ghi phải là bội số của khối
Offset phải căn biên
Sai một điều kiện → EINVAL, không có thông báo gì rõ ràng
```

Và mất luôn readahead của kernel — phải tự làm.

---

## 6. Ghi 8KB thành ghi 4MB — khuếch đại ghi

Chồng các tầng có kích thước khác nhau, mỗi tầng làm phình ra:

```
Trang B+Tree của bạn        8 KB
Khối file system            4 KB
Trang vật lý của NAND      16 KB
KHỐI XOÁ của NAND           4 MB   ← NAND không sửa được tại chỗ,
                                      chỉ XOÁ ĐƯỢC CẢ KHỐI 4MB rồi ghi lại
```

SSD không ghi đè được. Muốn sửa 8KB, bộ điều khiển trong ổ phải:
```
ghi 8KB mới vào chỗ trống khác  →  đánh dấu chỗ cũ là rác
                                →  lúc rảnh: gom rác, dồn dữ liệu còn sống,
                                   xoá cả khối 4MB
```

Cơ chế này gọi là **garbage collection** của SSD. Hệ quả:

```
Ghi 8KB có thể khiến ổ ghi thật 100KB-1MB xuống NAND.
Khuếch đại ghi = 10-100 lần.
→ Ổ mòn nhanh hơn, và có những lúc TRỄ ĐỘT BIẾN khi GC chạy
   (một nguồn p99 xấu mà nhiều người không ngờ tới)
```

**Ghi tuần tự thì khuếch đại thấp hơn nhiều** — dữ liệu ghi liền nhau thì cả khối
cùng chết một lúc, dọn rác dễ. Một lý do nữa để WAL ghi nối đuôi.

---

## 7. Con số quyết định mọi thiết kế lưu trữ

```
                     Tuần tự          Ngẫu nhiên 4KB
NVMe SSD             3-7 GB/s         ~500K IOPS  (~2 GB/s)   → chênh ~3 lần
Ổ cứng cơ (HDD)      200 MB/s         ~150 IOPS   (0.6 MB/s)  → chênh ~300 LẦN
```

Con số 300 lần trên HDD là lý do lịch sử khiến **LSM Tree** ra đời:

```
B+Tree:    sửa chỗ nào ghi chỗ đó → GHI NGẪU NHIÊN
LSM Tree:  gom lại, ghi thành khối lớn nối đuôi → GHI TUẦN TỰ

→ Trên HDD, LSM ghi nhanh hơn B+Tree hàng trăm lần.
→ Trên NVMe, khoảng cách hẹp lại nhiều — B+Tree đã quay lại cạnh tranh được.
```

Ví dụ đẹp về việc **phần cứng thay đổi thì lựa chọn kiến trúc cũng thay đổi**.

---

## 8. Ba đời của I/O bất đồng bộ

```
① BLOCKING + THREAD POOL
   Mỗi I/O chiếm một thread ngồi chờ. Đơn giản, nhưng tốn thread.

② io_submit (AIO cũ của Linux)
   Chỉ chạy async khi dùng O_DIRECT. Ngoài ra vẫn blocking ngầm.
   → tiếng xấu là "async giả".

③ io_uring  (Linux 5.1+)   ★ hiện đại
   Hai vòng đệm chia sẻ giữa chương trình và kernel:
      bạn bỏ yêu cầu vào vòng NỘP → kernel bỏ kết quả vào vòng HOÀN THÀNH
   → gần như KHÔNG CÓ syscall, không copy
   → async thật cho cả file lẫn socket
```

`io_uring` là hướng đi của mọi storage engine mới.

---

## 9. Danh sách kiểm tra độ bền cho storage engine

Muốn tuyên bố "dữ liệu không mất", phải trả lời được hết:

```
☐ Có fsync/fdatasync sau khi ghi nhật ký không?
☐ Có fsync THƯ MỤC CHA sau khi tạo/đổi tên file không?
☐ Chống torn page bằng cách nào? (full-page-write / doublewrite / COW)
☐ Nhật ký có checksum để phát hiện bản ghi cụt không?
☐ Ổ đĩa có nói thật khi nhận lệnh flush không? (có tụ điện không?)
☐ Đã thử kill -9 và cắt điện thật giữa lúc ghi chưa?
```

> Dòng cuối quan trọng nhất: **độ bền không được chứng minh bằng suy luận,
> mà bằng cách thật sự giết tiến trình hàng nghìn lần rồi kiểm tra.**

---

## 10. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- **fsync thư mục cha** — rất ít người biết, nói được là nổi bật
- Bốn tầng của đường ghi, đặc biệt là cache trong ổ đĩa
- Vì sao database dùng `O_DIRECT` (double caching + kiểm soát eviction)
- Khuếch đại ghi và GC của SSD gây trễ đột biến
- Chênh lệch tuần tự/ngẫu nhiên → vì sao có LSM Tree

**Sai lầm thường gặp:**
- Tin rằng `write()` xong là an toàn
- Chỉ `fsync` file mà quên thư mục
- Đo hiệu năng SSD mà không tính GC
- Cho rằng `O_DIRECT` luôn nhanh hơn

---

## 11. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. Tên file nằm ở đâu? Vì sao điều đó dẫn tới việc phải `fsync` thư mục?
2. Kể 4 tầng dữ liệu đi qua khi ghi. Tầng nào hay bị quên?
3. `fsync` khác `fdatasync` chỗ nào?
4. Vì sao database muốn dùng `O_DIRECT`? Cái giá là gì?
5. Vì sao ghi 8KB có thể khiến SSD ghi thật cả MB?
6. Ghi tuần tự vs ngẫu nhiên chênh bao nhiêu trên HDD? Trên NVMe?
7. Vì sao LSM Tree ra đời? Vì sao NVMe làm B+Tree cạnh tranh trở lại?
8. `io_uring` giải quyết vấn đề gì của AIO cũ?

---

## 12. Bài tập

**Implementation:** viết chương trình ghi 1000 bản ghi theo 4 cách —
(a) `write` không fsync, (b) `write` + `fsync` mỗi bản ghi, (c) `write` +
`fsync` theo lô 100 bản (group commit), (d) `O_DIRECT`. Đo throughput từng cách.
Rồi `kill -9` giữa chừng và đếm xem mỗi cách mất bao nhiêu bản ghi.

**System design:** thiết kế lớp WAL cho B+Tree đang làm. Định dạng bản ghi thế
nào (checksum ở đâu)? `fsync` bao lâu một lần? Group commit ra sao? Khi khởi
động lại thì replay từ đâu tới đâu, và làm sao biết bản ghi cuối bị cụt?
