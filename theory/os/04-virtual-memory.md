# Virtual Memory & mmap

Session date: 2026-08-27
Bài thứ tư của mảng Operating Systems.

> Bài này liên quan trực tiếp tới project B+Tree page-based đang làm.
> Mục 5 (mmap vs read/write) và mục 6 (torn page) là hai quyết định thiết kế
> phải trả lời được trước khi viết tiếp storage layer.

---

## 1. Ba ảo giác mà VM tạo ra

```
① CÔ LẬP     mỗi process tin rằng nó sở hữu toàn bộ máy
② LIÊN TỤC   địa chỉ 0x1000 → 0x9000 liền mạch, dù RAM thật rời rạc khắp nơi
③ DƯ DẢ      cấp phát 100GB trên máy 16GB RAM vẫn được
```

Cái giá: **mọi truy cập bộ nhớ đều phải dịch địa chỉ.**
Toàn bộ phần còn lại của bài là hệ quả của cái giá đó.

---

## 2. Cơ chế dịch địa chỉ và TLB

```
Địa chỉ ảo → MMU → bảng trang (4 cấp trên x86-64) → địa chỉ vật lý

Đi hết 4 cấp = 4 lần truy cập RAM ← quá đắt để làm mỗi lần
→ TLB cache lại kết quả dịch

TLB hit   ~ 0.5 ns   (gần như miễn phí)
TLB miss  ~ 100 ns   (page walk 4 cấp)
```

TLB rất nhỏ — cỡ 64-1500 entry. Với page 4KB, 1000 entry chỉ phủ được **4MB**.

```
B+Tree có buffer pool 8GB:
   4KB page      → 2 triệu page → TLB phủ 0.05% → miss liên tục
   2MB huge page → 4000 page    → TLB phủ TOÀN BỘ
```

Đây là lý do database và JVM đều có tuỳ chọn **huge page** — không phải để tiết
kiệm RAM, mà để **giảm TLB miss**. Với buffer pool lớn, `MADV_HUGEPAGE` hoặc
hugetlbfs là thứ đáng đo.

---

## 3. Page fault — con số quyết định mọi thứ

```
MINOR FAULT   trang đã ở RAM, chỉ chưa ánh xạ
              (page cache hit, cấp phát lười, copy-on-write)
              ~ 1 µs

MAJOR FAULT   phải ĐỌC TỪ ĐĨA
              ~ 100 µs (NVMe)   ~ 10.000 µs (HDD)
              CHÊNH 100 - 10.000 LẦN
```

**Cấp phát lười:** `malloc(1GB)` không hề chiếm RAM. Kernel chỉ ghi nhận một vùng
địa chỉ. Chỉ khi **chạm** vào từng trang thì mới có RAM thật (minor fault).

Hệ quả: **`malloc` thành công KHÔNG có nghĩa là bạn có bộ nhớ.** Hệ thống có thể
chết lúc bạn ghi vào, chứ không phải lúc cấp phát. Đó là **overcommit**, và là
lý do OOM killer tồn tại.

---

## 4. Page cache — trái tim của I/O

```
read(fd, buf, 4096):
   Đĩa ──▶ PAGE CACHE (RAM của kernel) ──COPY──▶ buffer của bạn
                                          └─ 1 lần copy + 1 syscall

write(fd, buf, 4096):
   buffer của bạn ──COPY──▶ PAGE CACHE ──▶ đánh dấu DIRTY ──▶ TRẢ VỀ NGAY
                                                              └─ CHƯA XUỐNG ĐĨA!
```

> **`write()` trả về thành công không có nghĩa dữ liệu đã an toàn.**
> Nó mới nằm trong RAM của kernel. Mất điện lúc này là mất dữ liệu.

Trang bẩn được ghi xuống đĩa khi:
```
- vm.dirty_background_ratio (~10%)  → kernel bắt đầu ghi ngầm
- vm.dirty_ratio (~20%)             → tiến trình GHI BỊ CHẶN cho tới khi giảm
- vm.dirty_expire_centisecs (~30s)  → trang quá cũ
- fsync() / fdatasync()             → BẠN yêu cầu, và CHỜ
```

Ngưỡng `dirty_ratio` là thủ phạm của hiện tượng "ghi nhanh, nhanh, nhanh, rồi
**đứng hình 2 giây**" — hệ thống tích luỹ trang bẩn tới ngưỡng rồi chặn tất cả.
Đây chính là **load shedding của kernel**, cùng ý tưởng với `maxconn` (bài Load
Balancer) và `cpu.max` (bài Scheduling).

```
fsync()      ~ 0.1 - 10 ms   ← đắt gấp 1000 lần write()
```

Con số nền tảng của mọi storage engine:
**WAL tồn tại để chỉ phải `fsync` MỘT chỗ tuần tự, thay vì fsync khắp nơi ngẫu nhiên.**

---

## 5. ★ mmap vs read/write — quyết định thiết kế cho B+Tree

```
read/write:  Đĩa ──▶ page cache ──COPY──▶ buffer của bạn
             Mỗi lần truy cập = 1 syscall + 1 copy
             BẠN tự quản lý buffer pool

mmap:        Đĩa ──▶ page cache ──ÁNH XẠ THẲNG──▶ không gian địa chỉ của bạn
             Truy cập = đọc bộ nhớ bình thường, không syscall, không copy
             KERNEL quản lý buffer pool hộ bạn
```

Nghe thì `mmap` thắng tuyệt đối. Nhưng **hầu hết database nghiêm túc không dùng
nó** — Postgres, MySQL/InnoDB, RocksDB đều tự viết buffer pool.
(Bài báo *"Are You Sure You Want to Use MMAP in Your DBMS?"*, CIDR 2022.)

### ① Mất quyền kiểm soát thứ tự ghi — lý do chí mạng

```
Quy tắc vàng của WAL:  log PHẢI xuống đĩa TRƯỚC trang dữ liệu.

Với mmap: kernel có thể ghi BẤT KỲ trang bẩn nào, vào BẤT KỲ lúc nào.
   → nó có thể ghi trang dữ liệu TRƯỚC khi log kịp xuống
   → mất điện → khôi phục sai → HỎNG DỮ LIỆU

Không có cách nào nói với kernel "khoan, chưa được ghi trang này".
```

Với một B+Tree có WAL, đây gần như là dấu chấm hết cho `mmap` ở đường ghi.

### ② Mất quyền kiểm soát việc đuổi trang

Bạn biết trang gốc của B+Tree là nóng nhất. Kernel không biết — nó dùng LRU chung
cho cả máy. Một lệnh `cp` file lớn có thể quét sạch trang nóng ra khỏi page cache.

### ③ Page fault là đồng bộ và vô hình

```
node->key[i]      ← trông như một phép đọc bộ nhớ
                  ← thực tế có thể là major fault → THREAD ĐỨNG 100µs

Không prefetch được. Không async I/O được. Không io_uring được.
Không biết chỗ nào sẽ block để mà thiết kế.
```

### ④ Lỗi I/O biến thành `SIGBUS`
Không phải mã lỗi trả về. Rất khó xử lý tử tế.

### ⑤ TLB shootdown
Khi bỏ ánh xạ một vùng trong chương trình đa luồng, kernel phải gửi ngắt liên xử
lý (IPI) tới mọi core để xoá TLB. Rất đắt, tăng theo số core.

### Khi nào mmap vẫn đúng

LMDB dùng `mmap` rất thành công — nhưng nó **chỉ ánh xạ để đọc**, chỉ có **một
writer**, và dùng **copy-on-write B+tree** nên không bao giờ ghi đè trang đang có
người đọc. Ràng buộc thiết kế chặt chẽ mới làm `mmap` an toàn.

> **Khuyến nghị cho project:** tự viết buffer pool với `pread`/`pwrite`.
> Cần kiểm soát thứ tự ghi cho WAL, và cần biết chính xác chỗ nào block.
> `mmap` sẽ làm code NGẮN HƠN và ĐÚNG KHÓ HƠN.

---

## 6. Torn page — cái bẫy B+Tree nào cũng phải trả lời

```
Page của B+Tree:  8 KB
Page của OS:      4 KB
Sector của đĩa:   512 B hoặc 4 KB

Mất điện giữa lúc ghi 8KB:
   → 4KB đầu là dữ liệu MỚI, 4KB sau là dữ liệu CŨ
   → một trang B+Tree LAI TẠP, checksum sai, cấu trúc hỏng
   → KHÔNG khôi phục được từ WAL vì bản thân trang đã rác
```

Ba cách chữa mà database thật dùng:

```
Postgres:  full_page_writes — ghi TOÀN BỘ trang vào WAL ở lần sửa đầu tiên
                              sau mỗi checkpoint
InnoDB:    doublewrite buffer — ghi trang vào vùng đệm tuần tự TRƯỚC,
                                ghi xong mới ghi vào vị trí thật
LMDB:      copy-on-write — không bao giờ ghi đè trang đang dùng
                           → torn page KHÔNG THỂ xảy ra về mặt cấu trúc
```

Cách thứ ba là cách duy nhất **loại bỏ** vấn đề thay vì **vá** nó.
Đáng cân nhắc cho thiết kế B+Tree đang làm.

---

## 7. Copy-on-write và `fork()`

```
fork() KHÔNG copy bộ nhớ. Nó copy BẢNG TRANG, đánh dấu mọi trang read-only.
   → Ghi vào trang nào → page fault → lúc đó mới copy trang đó

Redis BGSAVE dùng đúng cơ chế này:
   fork() → tiến trình con có ảnh chụp nhất quán, gần như miễn phí
   → con ghi file RDB thong thả, cha vẫn phục vụ bình thường

Cái bẫy: nếu cha ghi vào NHIỀU trang trong lúc đó
   → mỗi trang bị copy → RAM có thể phình tới GẤP ĐÔI
   → OOM đúng lúc đang backup
```

---

## 8. Swap, thrashing, và cgroup

```
Thrashing: working set > RAM
   → mỗi truy cập là major fault → đọc đĩa → đuổi trang khác ra
   → hệ thống chạy chậm 1000 lần nhưng CPU trông RẢNH, không có lỗi nào

Máy chạy database: thường TẮT swap (hoặc vm.swappiness=1)
   → thà bị OOM kill nhanh và rõ ràng, còn hơn chậm 1000 lần một cách âm thầm
```

Trong container, `memory.max` của cgroup **tính cả page cache**. Một tiến trình
đọc file nhiều có thể bị OOM kill dù heap nhỏ — kernel cố thu hồi page cache
trước, nhưng dưới áp lực thì vẫn giết. Song song hoàn hảo với `cpu.max` ở bài
Scheduling.

---

## 9. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- `write()` xong **không** phải là bền vững — cần `fsync`, đắt gấp 1000 lần
- Nói được **vì sao database không dùng mmap**, đặc biệt lý do thứ tự ghi/WAL
- Phân biệt **minor vs major fault** và độ chênh
- Biết **torn page** và ba cách chữa
- `malloc` thành công không đảm bảo có RAM (overcommit)

**Sai lầm thường gặp:**
- Tưởng `mmap` luôn nhanh hơn `read`
- Quên `fsync` rồi tuyên bố hệ thống bền vững
- Đo hiệu năng ghi mà không tính giai đoạn `dirty_ratio` chặn lại
- Bật swap trên máy database

---

## 10. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. Ba ảo giác VM tạo ra là gì? Cái giá phải trả?
2. TLB miss tốn bao nhiêu? Vì sao huge page giúp database?
3. Minor fault khác major fault bao nhiêu lần?
4. `write()` trả về thành công thì dữ liệu đang ở đâu?
5. `fsync()` đắt gấp bao nhiêu lần `write()`? Vì sao WAL tồn tại?
6. Kể **ba** lý do database không dùng `mmap`. Lý do nào chí mạng nhất?
7. Torn page là gì? Postgres, InnoDB, LMDB chữa bằng cách nào?
8. Vì sao Redis `BGSAVE` có thể làm RAM tăng gấp đôi?
9. Vì sao máy database thường tắt swap?

---

## 11. Bài tập

**Implementation:** với B+Tree đang làm — viết hai backend cho storage layer:
(a) `pread`/`pwrite` + buffer pool tự quản, (b) `mmap`. Đo throughput đọc ngẫu
nhiên và ghi tuần tự. Rồi thử tắt nguồn giả lập (kill -9 giữa lúc ghi) và kiểm
tra tính toàn vẹn — quan sát xem (b) có bảo toàn được thứ tự WAL không.

**System design:** thiết kế storage layer cho một key-value store cần đảm bảo
bền vững. Chọn mmap hay buffer pool tự quản? Chống torn page bằng cách nào?
`fsync` ở đâu, bao nhiêu lần cho mỗi commit? Đánh đổi giữa độ bền và throughput
ra sao (group commit)?
