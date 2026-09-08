# Scheduling

Session date: 2026-08-27
Bài thứ hai của mảng Operating Systems.

> Context switch (cơ chế + chi phí) đã nói ở `01-process-thread.md`.
> Bài này tập trung vào: AI được chạy, BAO LÂU, và vì sao production hay hỏng.

---

## 1. Bài toán

`N` thread sẵn sàng chạy, `M` core. Chọn ai, cho chạy bao lâu?
Ba mục tiêu **mâu thuẫn nhau**:

```
THROUGHPUT   → time slice dài, ít chuyển ngữ cảnh, cache nóng
LATENCY      → time slice ngắn, phản hồi nhanh cho việc tương tác
FAIRNESS     → ai cũng có phần, không ai chết đói

Chọn cái này là hy sinh cái kia. Scheduler là một cuộc THOẢ HIỆP,
không phải một lời giải tối ưu.
```

---

## 2. CFS — cách Linux giải quyết

Điểm thông minh: **không phát time slice cố định**, mà theo dõi **thời gian ảo**
mỗi thread đã tiêu thụ.

```
vruntime = thời gian CPU đã dùng, CÓ TRỌNG SỐ

Scheduler luôn chọn thread có vruntime NHỎ NHẤT
   (cây đỏ-đen, lấy phần tử trái nhất — O(log n))

Thread chạy → vruntime tăng → tụt xuống dưới trong hàng
Thread ngủ  → vruntime ĐỨNG YÊN → khi thức dậy nó ở đầu hàng
```

Hệ quả đẹp: **tính tương tác xuất hiện TỰ NHIÊN, không cần luật riêng.**

```
Thread nén video:      chạy liên tục → vruntime tăng nhanh → bị đẩy xuống cuối
Thread xử lý gõ phím:  ngủ 99% thời gian → vruntime rất thấp
                       → vừa thức dậy là ĐƯỢC CHẠY NGAY
→ Gõ phím vẫn mượt dù máy đang render.
```

**`nice` điều chỉnh TỐC ĐỘ TRÔI của vruntime:**

```
nice -20 (ưu tiên cao)  → vruntime tăng CHẬM  → được chạy nhiều hơn
nice +19 (ưu tiên thấp) → vruntime tăng NHANH → nhanh bị đẩy xuống

Mỗi bậc nice ≈ 1.25 lần CPU. Chênh 5 bậc ≈ 3 lần.
```

Hai tham số điều chỉnh:
```
sched_latency     ~6-24ms   → chu kỳ mà MỌI thread sẵn sàng đều được chạy 1 lần
min_granularity   ~0.75-3ms → thời gian tối thiểu mỗi lần, tránh thrash

1000 thread sẵn sàng: 24ms / 1000 = 0.024ms mỗi thread
→ nhỏ hơn min_granularity → hệ thống buộc phải KÉO DÀI chu kỳ
→ độ trễ phản hồi tăng vọt. Chính là oversubscription ở bài trước.
```

*Từ Linux 6.6, CFS đã được thay bằng **EEVDF** (Earliest Eligible Virtual
Deadline First) — cùng triết lý công bằng theo vruntime nhưng thêm khái niệm
deadline để phục vụ việc cần độ trễ thấp tốt hơn. Nói được điều này là điểm cộng.*

---

## 3. Các lớp lập lịch

```
SCHED_FIFO / SCHED_RR   ưu tiên 1-99, LUÔN chiếm quyền trước mọi thứ khác
                        FIFO: chạy tới khi tự nhả — KHÔNG bị ngắt vì hết giờ
                        ⚠ Một thread FIFO lặp vô hạn sẽ KHOÁ CỨNG một core
                        Dùng cho: audio, điều khiển công nghiệp, HFT

SCHED_DEADLINE          khai báo (runtime, deadline, period), kernel đảm bảo
                        hoặc từ chối. Mạnh nhất cho realtime thật sự.

SCHED_OTHER             CFS/EEVDF — 99.9% tiến trình bình thường

SCHED_BATCH             coi như không tương tác → time slice dài, cache tốt hơn
SCHED_IDLE              chỉ chạy khi máy rảnh
```

---

## 4. Nhiều core — cân bằng và cache

```
Mỗi core có RUN QUEUE RIÊNG
   (dùng chung một hàng đợi toàn cục thì khoá của nó thành nút thắt)

→ Cân bằng tải định kỳ: core rảnh "trộm việc" từ core bận

MÂU THUẪN CỐT LÕI:
   Di chuyển thread sang core khác  → cân bằng tốt hơn
                                    → NHƯNG mất toàn bộ cache nóng (L1/L2)
   Giữ thread ở nguyên core         → cache nóng
                                    → NHƯNG có thể lệch tải
```

Scheduler ưu tiên giữ thread ở lại (**cache affinity**), chỉ di chuyển khi lệch
đủ nhiều.

Máy **NUMA** còn nặng hơn: chuyển thread sang socket khác thì mọi truy cập RAM
thành **remote memory access**, chậm 1.5-2 lần. Kernel cố giữ thread gần vùng
nhớ của nó.

Ép thủ công: `taskset`, `sched_setaffinity`. Hữu ích cho tải độ trễ cực thấp,
nhưng dễ phản tác dụng nếu ghim sai.

---

## 5. ★ cgroup CPU limit — thủ phạm số một trong production

Phần đáng giá nhất của bài, và là thứ **rất nhiều kỹ sư gặp mà không nhận ra**.

```
cpu.shares / cpu.weight    → TRỌNG SỐ tương đối, chỉ tác dụng KHI TRANH CHẤP
                             Không tranh chấp → dùng thoải mái

cpu.max (cfs_quota/period) → TRẦN CỨNG trong mỗi chu kỳ 100ms
                             Hết quota → BỊ ĐÓNG BĂNG tới hết chu kỳ
```

### Cái bẫy

```
Container giới hạn "1 CPU"  →  quota = 100ms CPU mỗi chu kỳ 100ms
App có 4 thread chạy song song

   t=0ms   4 thread cùng chạy, tiêu thụ 4ms CPU mỗi 1ms thực
   t=25ms  đã tiêu hết 100ms quota
   t=25ms  ★ TOÀN BỘ CONTAINER BỊ ĐÓNG BĂNG ★
   ...     đóng băng suốt 75ms
   t=100ms chu kỳ mới, được chạy lại

Quan sát được:
   - CPU utilization báo ~40%   ("còn thừa mà?")
   - p99 latency vọt lên 75ms+  ("sao lại chậm?")
   - KHÔNG CÓ LOG LỖI NÀO CẢ
```

**Đây là nguyên nhân của vô số sự cố p99 bí ẩn.** Metric CPU trông đẹp, nhưng
ứng dụng bị treo 75ms mỗi 100ms.

### Cách phát hiện

```bash
cat /sys/fs/cgroup/cpu.stat
   nr_throttled     ← khác 0 là có vấn đề
   throttled_usec   ← tổng thời gian bị đóng băng
```

### Nguyên nhân gốc — thư viện nhìn nhầm số core

```
Máy chủ vật lý 64 core. Container giới hạn 2 CPU.

Go:      GOMAXPROCS mặc định = 64      ← nhìn máy chủ, không nhìn giới hạn
Java:    ForkJoinPool = 64 thread      (JVM mới đã biết đọc cgroup)
Python:  os.cpu_count() = 64
nginx:   worker_processes auto → 64 worker

→ 64 thread tranh nhau 2 CPU quota → đốt quota trong 3ms → đóng băng 97ms
```

### Cách chữa

```
1. Đặt song song theo GIỚI HẠN, không theo máy chủ
   GOMAXPROCS=2,  worker_processes 2,  thread pool = 2
2. Nới quota, hoặc bỏ limit và chỉ dùng request (nhiều nơi khuyến nghị)
3. Rút ngắn period → đóng băng vụn hơn, đỡ giật
```

---

## 6. Load average — con số bị hiểu sai nhiều nhất

```
Load average trên Linux ĐẾM CẢ:
   - thread đang chạy hoặc chờ CPU  (runnable)
   - thread ở trạng thái D (uninterruptible — thường là ĐANG CHỜ ĐĨA)

→ load = 50 trên máy 8 core CÓ THỂ là:
     (a) 50 thread tranh CPU     → nghẽn CPU
     (b) 50 thread chờ đĩa/NFS   → CPU RẢNH RỖI, nghẽn I/O

Load average MỘT MÌNH không cho biết nghẽn ở đâu.
Phải xem thêm: %util CPU, iowait, cột `b` (blocked) của vmstat.
```

---

## 7. Các kiểu hỏng

| Hiện tượng | Nguyên nhân | Cách chữa |
|---|---|---|
| **p99 giật cục, CPU trông rảnh** | cgroup throttling | Sửa song song theo limit; xem `nr_throttled` |
| **Máy đứng hình hoàn toàn** | Thread `SCHED_FIFO` lặp vô hạn | `sched_rt_runtime_us` chừa chỗ cho task thường |
| **Load cao nhưng CPU rảnh** | Thread kẹt D-state chờ I/O | Xem `iowait`, `iostat` |
| **Throughput giảm khi thêm thread** | Context switch thrash | Giảm pool về ~số core |
| **Latency lệch giữa các request giống nhau** | Bị đẩy sang NUMA node khác | Ghim CPU, `numactl` |

---

## 8. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- **cgroup throttling** — nói được là nổi bật ngay, rất ít người biết
- CFS công bằng theo **vruntime**, không phát time slice cố định
- Mâu thuẫn **cache affinity vs cân bằng tải**
- Load average **không** đồng nghĩa với nghẽn CPU
- Nguy hiểm của `SCHED_FIFO`

**Sai lầm thường gặp:**
- Chỉnh `nice` để "tăng tốc" trong khi nút thắt là I/O
- Đặt thread pool theo số core máy chủ trong môi trường container
- Tin rằng CPU utilization thấp nghĩa là còn dư năng lực

---

## 9. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. CFS chọn thread tiếp theo dựa trên cái gì? Vì sao tính tương tác tự xuất hiện?
2. `nice` thực chất thay đổi điều gì? Chênh 5 bậc khác nhau bao nhiêu?
3. `cpu.shares` khác `cpu.max` chỗ nào? Cái nào gây đóng băng?
4. Container 1 CPU, app 4 thread — mô tả chuyện xảy ra trong 100ms.
5. Vì sao CPU utilization 40% mà p99 vẫn 75ms?
6. Vì sao mỗi core có run queue riêng thay vì dùng chung một hàng đợi?
7. Load average 50 trên máy 8 core — có chắc nghẽn CPU không? Kiểm tra thế nào?
8. Một thread `SCHED_FIFO` chạy vòng lặp vô hạn thì sao?

---

## 10. Bài tập

**Implementation:** viết script Python tạo N thread CPU-bound, chạy trong
container giới hạn 1 CPU. Với N = 1, 2, 4, 8: đo throughput, p99 latency, và
`nr_throttled` trong `cpu.stat`. Chứng minh bằng số liệu rằng N tăng làm p99 tệ đi.

**System design:** một service p99 latency 200ms trong khi p50 chỉ 5ms.
CPU utilization 35%. Liệt kê giả thuyết theo thứ tự ưu tiên và cách kiểm chứng
từng cái.
