# Process & Thread

Session date: 2026-08-27
Bài đầu tiên của mảng Operating Systems (Phase 1 — Foundations).

> Viết cho người đã quen đa luồng C++: bỏ qua "thread là gì", đi thẳng vào
> chi phí thật và ba mô hình concurrency.
> Cùng cách viết với CDN/WebSocket/gRPC: gọn, kết bằng checklist tự kiểm tra.

---

## 1. Hai thứ này giải quyết hai bài toán khác nhau

Hay bị dạy là "process nặng, thread nhẹ" — sai trọng tâm. Khác biệt thật là
**cô lập hay chia sẻ**:

```
PROCESS  — đơn vị CÔ LẬP
   Không gian địa chỉ riêng → lỗi ở đây không giết được cái kia
   Crash một process = mất một process

THREAD   — đơn vị LẬP LỊCH
   Chung không gian địa chỉ → chia sẻ dữ liệu miễn phí
   Crash một thread = MẤT CẢ PROCESS
```

**Cái gì chung, cái gì riêng:**

```
                        Process A        Thread 1   Thread 2   (trong process A)
Không gian địa chỉ      riêng            ═══════ chung ═══════
Bảng file descriptor    riêng            ═══════ chung ═══════
Heap                    riêng            ═══════ chung ═══════
Biến toàn cục           riêng            ═══════ chung ═══════
─────────────────────────────────────────────────────────────
Stack                   riêng            riêng      riêng
Thanh ghi / PC          riêng            riêng      riêng
TLS (thread-local)      riêng            riêng      riêng
```

> **Chia sẻ dữ liệu giữa thread là miễn phí nhưng nguy hiểm;
> giữa process thì tốn kém nhưng an toàn.**
> Mọi lựa chọn thiết kế sau đó đều từ câu này mà ra.

---

## 2. Chi phí thật — những con số cần thuộc

```
Tạo process (fork+exec)      ~ 1.000 - 10.000 µs
Tạo thread                   ~ 10 - 100 µs          (nhanh hơn ~100 lần)
Context switch cùng process  ~ 1 - 2 µs             (chỉ đổi thanh ghi + stack)
Context switch khác process  ~ 3 - 5 µs             (thêm chuyển bảng trang)
Chuyển ngữ cảnh coroutine    ~ 0.05 - 0.2 µs        (userspace, không vào kernel)

Stack mỗi thread             8 MB ảo, ~4-8 KB thực (cấp phát lười)
```

**Nhưng con số µs ở trên đang nói dối.** Chi phí thật nằm chỗ khác:

```
Context switch làm HỎNG CACHE.
   L1/L2 đang đầy dữ liệu nóng của thread A
   → chuyển sang B → B nạp dữ liệu của nó, đẩy hết A ra
   → A quay lại → cache miss hàng loạt

   Chi phí trực tiếp:  ~2 µs
   Chi phí gián tiếp:  10 - 100 µs (khôi phục cache)
   → chi phí thật lớn hơn 5-50 LẦN so với con số sách vở
```

Với process còn thêm: đổi bảng trang → **TLB flush**. Kiến trúc hiện đại có
PCID/ASID gắn nhãn TLB theo process nên giảm bớt, nhưng không xoá hết.

> **Thread không đắt lúc tạo ra — đắt lúc bị chuyển đi chuyển lại.**

---

## 3. Context switch xảy ra khi nào

```
TỰ NGUYỆN (voluntary)
   Thread gọi I/O, chờ mutex, sleep → tự nhường CPU
   → hợp lý, không tránh được

BỊ ÉP (involuntary)
   Hết time slice, hoặc thread ưu tiên cao hơn giành CPU
   → đây mới là thứ cần theo dõi
```

Đo bằng `vmstat 1` (cột `cs`) hoặc `pidstat -w`.
**Involuntary switch cao bất thường = quá nhiều thread tranh nhau quá ít CPU** —
dấu hiệu kinh điển của oversubscription.

```
1000 thread trên 8 core:
   Mỗi thread chạy vài µs rồi bị đá ra
   → CPU dành phần lớn thời gian CHUYỂN NGỮ CẢNH, không phải LÀM VIỆC
   → thêm thread làm hệ thống CHẬM ĐI, không nhanh lên
```

---

## 4. Ba mô hình concurrency — phần quan trọng nhất

Nối thẳng vào toàn bộ mảng Networking:

```
① THREAD MỖI REQUEST                    Apache prefork, Tomcat cổ điển
   10.000 connection → 10.000 thread → 80 GB stack ảo
                    → CPU bận chuyển ngữ cảnh
   ✅ Code tuần tự, dễ đọc, dễ debug
   ❌ SỤP ĐỔ ở mức ~10.000 connection   ← chính là bài toán C10K

② EVENT LOOP                            nginx, Redis, Node.js
   10.000 connection → 1 thread + epoll → vài MB RAM
                    → gần như không switch
   ✅ Nuôi được hàng TRIỆU connection
   ❌ MỘT lời gọi blocking là ĐỨNG HÌNH TẤT CẢ
   ❌ Code đảo ngược luồng điều khiển (callback / async)

③ COROUTINE / GREEN THREAD              Go, Python asyncio, Java virtual thread
   10.000 connection → 10.000 coroutine → runtime ghép vào N thread OS
                    → switch trong userspace, ~0.1 µs
   ✅ Viết như code tuần tự, chạy như event loop   ← tốt nhất cả hai
   ❌ Cần runtime hỗ trợ; vẫn dính bẫy blocking call
```

**Kiến trúc thắng cuộc trong thực tế là lai:**

```
nginx:  N worker PROCESS (bằng số core, cô lập lẫn nhau)
        mỗi worker chạy MỘT event loop xử lý hàng nghìn connection

        → tận dụng hết CPU (nhiều process)
        → chịu tải cao (event loop)
        → một worker crash không kéo sập cả server (cô lập)
```

Đây chính xác là câu trả lời cho "1 triệu WebSocket connection thì làm sao" ở
bài WebSocket: **event loop, không phải thread mỗi connection.**

---

## 5. Ghi chú riêng cho Python — GIL

```
GIL = chỉ MỘT thread Python chạy bytecode tại một thời điểm.

I/O-bound:  thread VẪN HIỆU QUẢ
   → khi chờ mạng/đĩa, thread NHẢ GIL cho thread khác chạy

CPU-bound:  thread VÔ DỤNG
   → 8 thread trên 8 core vẫn chỉ nhanh bằng 1 core, còn tệ hơn vì tranh GIL
   → phải dùng multiprocessing, hoặc đẩy xuống C/C++ (numpy, torch — chúng
     nhả GIL trong vòng lặp tính toán)
```

Mô hình quen thuộc với nền GPU/DeepStream/Triton: **Python điều phối, phần nặng
chạy ngoài GIL.** Python 3.13+ có chế độ free-threaded (bỏ GIL) nhưng chưa phổ
biến trong production.

---

## 6. Các kiểu hỏng thường gặp

| Hiện tượng | Nguyên nhân | Cách chữa |
|---|---|---|
| **Thread explosion** | Thread pool không giới hạn, mỗi request một thread | Pool có trần + hàng đợi có trần (đúng tinh thần `maxconn` ở bài LB) |
| **Context switch thrash** | Nhiều thread hơn core rất nhiều | Giảm pool về ~số core cho việc CPU-bound |
| **False sharing** | Hai thread ghi hai biến chung một cache line 64B | Chèn đệm cho đủ 64 byte |
| **Priority inversion** | Thread ưu tiên thấp giữ mutex mà thread ưu tiên cao đang cần | Priority inheritance |
| **Blocking trong event loop** | Một `time.sleep()` hoặc query đồng bộ | Đẩy sang thread pool riêng |

**Quy tắc chọn số thread:**
```
CPU-bound:  số thread ≈ số core       (thêm nữa chỉ tổ chuyển ngữ cảnh)
I/O-bound:  số thread ≫ số core       (phần lớn thời gian là ngồi chờ)
            hoặc tốt hơn: dùng async, đừng dùng thread
```

---

## 7. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- Chọn mô hình theo **loại tải** (CPU-bound vs I/O-bound), không theo thói quen
- Biết **C10K** và vì sao thread-per-connection sụp đổ
- Nói được **chi phí thật của context switch là hỏng cache**, không phải µs kernel
- Nhắc kiến trúc lai của nginx (process theo core + event loop)

**Sai lầm thường gặp:**
- "Chậm thì thêm thread" — thường làm chậm thêm
- Không phân biệt CPU-bound và I/O-bound
- Chặn event loop bằng một lời gọi đồng bộ
- Nghĩ GIL làm Python vô dụng với mọi loại đồng thời

---

## 8. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. Thread chia sẻ những gì, không chia sẻ những gì?
2. Vì sao context switch giữa process đắt hơn giữa thread?
3. Chi phí **thật** của context switch nằm ở đâu? Vì sao con số µs gây hiểu nhầm?
4. C10K là gì? Thread-per-connection sụp đổ ở đâu?
5. Kể 3 mô hình concurrency + một hệ thống thật cho mỗi mô hình.
6. nginx dùng process hay thread? Vì sao chọn như vậy?
7. CPU-bound đặt bao nhiêu thread? I/O-bound bao nhiêu? Vì sao khác nhau?
8. Với Python, khi nào thread có ích, khi nào vô dụng?

---

## 9. Bài tập

**Implementation:** viết ba phiên bản của cùng một echo server bằng Python —
(a) thread mỗi connection, (b) `asyncio` event loop, (c) process pool. Đo RAM và
throughput ở 100, 1.000, 10.000 connection đồng thời. Vẽ đồ thị chỗ (a) sụp đổ.

**System design:** thiết kế tầng inference cho hệ thống xử lý video 1.000 luồng
camera. Bao nhiêu process, bao nhiêu thread, đặt ở đâu? Phần nào CPU-bound, phần
nào I/O-bound, phần nào GPU-bound? GIL ảnh hưởng chỗ nào?
