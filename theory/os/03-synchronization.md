# Synchronization

Session date: 2026-08-27
Bài thứ ba của mảng Operating Systems.

> Viết cho người đã quen đa luồng C++: bỏ qua "mutex là gì", đi vào cơ chế
> bên dưới, con số thực tế, và các bẫy hiệu năng.

---

## 1. Vấn đề thật sự là gì

Không phải "hai thread cùng ghi một biến". Chính xác hơn:

> **Có những khoảnh khắc bất biến của dữ liệu bị phá vỡ tạm thời.
> Đồng bộ hoá là việc đảm bảo không ai nhìn thấy khoảnh khắc đó.**

Chuyển tiền A → B: giữa lúc trừ A và cộng B, **tổng tiền trong hệ thống bị sai**.
Một mili giây thôi. Nhưng ai đọc đúng lúc đó sẽ thấy tiền bốc hơi.

Ba thứ cần đảm bảo, và chúng **khác nhau**:

```
ATOMICITY   — thao tác không bị chen ngang giữa chừng
VISIBILITY  — thread khác THẤY được thay đổi (cache! không phải RAM!)
ORDERING    — thứ tự thao tác không bị đảo (CPU và compiler đều đảo)
```

Hầu hết bug đồng bộ hoá đến từ việc chỉ nghĩ tới cái đầu tiên.

---

## 2. Nền móng phần cứng

```
Mỗi core có L1 cache RIÊNG.
Thread A ghi x=1 trên core 0 → nằm trong L1 của core 0
Thread B đọc x trên core 3   → đọc L1 của core 3 → vẫn thấy x=0

Giao thức MESI đồng bộ cache giữa các core, NHƯNG:
   - compiler được phép sắp xếp lại lệnh
   - CPU được phép thực thi out-of-order
   → không có rào chắn thì không đảm bảo gì về THỜI ĐIỂM và THỨ TỰ
```

Công cụ nguyên thuỷ phần cứng cung cấp:

```
CAS (compare-and-swap)   lock cmpxchg — nền của mọi thứ khác
LL/SC                    ARM/RISC-V: load-linked / store-conditional
Memory barrier           ép thứ tự, chặn CPU và compiler đảo lệnh
```

**`volatile` trong C/C++ KHÔNG dùng cho đa luồng.** Nó chỉ ngăn compiler tối ưu
bỏ lần đọc — không tạo rào chắn bộ nhớ, không đảm bảo nguyên tử. Dùng
`std::atomic`.
*(Java thì `volatile` lại đúng là công cụ đồng bộ — hai ngôn ngữ đặt trùng tên
cho hai thứ khác nhau.)*

---

## 3. Mutex thực chất là gì — futex

Trên Linux, mutex **không phải** một lời gọi kernel:

```
ĐƯỜNG NHANH (không tranh chấp):
   một lệnh CAS trong userspace, thành công
   → ~20 nanosecond. KHÔNG vào kernel.

ĐƯỜNG CHẬM (có tranh chấp):
   CAS thất bại → syscall futex(FUTEX_WAIT)
   → thread vào hàng đợi kernel, ngủ → context switch
   → ~1.000 - 5.000 nanosecond
```

**Chênh nhau 50-250 lần.**

```
Khoá KHÔNG tranh chấp thì gần như miễn phí.
Khoá CÓ tranh chấp thì đắt hơn 100 lần.

→ Vấn đề không bao giờ là "có dùng khoá không".
→ Vấn đề luôn là "có bao nhiêu TRANH CHẤP".
```

---

## 4. Spinlock hay mutex

```
SPINLOCK — quay vòng bận, không ngủ
   while (!try_lock()) { cpu_pause(); }

   ✅ Không context switch → độ trễ cực thấp
   ✅ Đúng khi vùng tới hạn NGẮN HƠN chi phí context switch (~1-5µs)
   ❌ Đốt CPU vô ích khi chờ lâu
   ❌ THẢM HOẠ nếu chủ khoá bị scheduler đá ra:
        chủ khoá không chạy → không nhả khoá
        → thread khác quay vòng vô ích suốt cả time slice
        (lock holder preemption — lý do KHÔNG dùng spinlock thuần ở userspace)

MUTEX ADAPTIVE — mặc định của pthread hiện đại
   quay vòng một lúc ngắn → vẫn không được thì mới ngủ
```

> **Kernel dùng spinlock** (không bị chiếm quyền, vùng tới hạn cực ngắn);
> **userspace dùng mutex adaptive.**

---

## 5. Mutex, Semaphore, Condition Variable — ba thứ khác nhau

```
MUTEX               "chỉ MỘT người được vào"
   Có QUYỀN SỞ HỮU: ai khoá thì người đó mở
   → bảo vệ bất biến của dữ liệu

SEMAPHORE           "tối đa N người được vào"
   Là một BỘ ĐẾM. KHÔNG có quyền sở hữu — A tăng, B giảm cũng được
   → quản lý một BỂ TÀI NGUYÊN
   → chính là connection pool, và là `maxconn` ở bài Load Balancer

CONDITION VARIABLE  "ngủ cho tới khi ĐIỀU KIỆN đúng"
   Không phải tài nguyên — mà là một MỆNH ĐỀ
   → hàng đợi rỗng/đầy, công việc đã xong
```

### Hai bẫy kinh điển của condition variable

```c
// SAI
if (queue.empty()) cond.wait(lock);

// ĐÚNG — phải là VÒNG LẶP
while (queue.empty()) cond.wait(lock);
```

**Spurious wakeup:** POSIX cho phép `wait()` tự thức dậy vô cớ. Và ngay cả không
có nó: giữa lúc được đánh thức và lúc giành lại được khoá, thread khác có thể
đã lấy mất phần tử.

**Lost wakeup:** `signal()` gọi lúc chưa ai `wait()` thì tín hiệu **bốc hơi**,
không được lưu lại. Vì thế điều kiện phải luôn kiểm tra dưới khoá, và trạng thái
phải nằm ở biến chung chứ không phải ở tín hiệu.

---

## 6. RWLock — và sự thật bất ngờ

Trực giác: nhiều reader song song thì phải nhanh hơn mutex. **Thường thì không.**

```
RWLock phải đếm số reader đang giữ khoá
   → mọi reader đều GHI vào cùng một bộ đếm
   → dòng cache đó bị "ping-pong" giữa các core
   → chi phí đồng bộ cache ăn hết lợi ích đọc song song

Đo thực tế: vùng tới hạn ngắn (đọc vài field)
   → RWLock CHẬM HƠN mutex thường
```

RWLock chỉ thắng khi **vùng tới hạn của reader đủ dài** và tỉ lệ đọc áp đảo.
Kèm rủi ro **writer starvation** nếu reader nối đuôi liên tục.

Với tải đọc-nhiều thật sự, câu trả lời hiện đại là **RCU** hoặc **con trỏ nguyên
tử tới cấu trúc bất biến**: reader không khoá gì cả, writer tạo bản sao mới rồi
hoán đổi con trỏ. Kernel Linux dùng RCU khắp nơi.

---

## 7. Tranh chấp mới là kẻ thù, không phải khoá

```
Amdahl: 5% code nằm trong khoá → dù 1000 core, nhanh nhất cũng chỉ 20 lần
```

Thủ phạm thật thường tinh vi hơn — **false sharing**:

```
struct { int64 counter_a; int64 counter_b; };   // chung 1 cache line 64B

Thread 1 chỉ ghi counter_a
Thread 2 chỉ ghi counter_b
→ KHÔNG chia sẻ dữ liệu, KHÔNG cần khoá
→ nhưng chung cache line → mỗi lần ghi làm invalid cache của core kia
→ chậm đi 10-100 lần

Chữa: alignas(64), hoặc chèn đệm cho đủ 64 byte.
```

Chiến lược giảm tranh chấp, theo thứ tự nên thử:

```
1. ĐỪNG CHIA SẺ       — dữ liệu theo thread, gộp lại sau (sharded counter)
2. Thu nhỏ vùng khoá  — tính toán ngoài khoá, chỉ khoá lúc ghi
3. Chia nhỏ khoá      — mỗi bucket một khoá thay vì một khoá cho cả bảng
4. Đổi cấu trúc       — copy-on-write, RCU, cấu trúc bất biến
5. Lock-free          — chỉ khi 4 cách trên đã hết đường
```

---

## 8. Lock-free — và vì sao thường không đáng

```
CAS loop:
   do { old = x.load(); new = f(old); }
   while (!x.compare_exchange_weak(old, new));

✅ Không deadlock, không lock holder preemption
❌ Rất khó viết ĐÚNG — memory ordering sai thì bug chỉ hiện trên ARM,
   một lần mỗi tháng, không tái hiện được
❌ Bài toán ABA: giá trị quay về A nhưng thế giới đã đổi
   → cần tag counter hoặc hazard pointer
❌ Tranh chấp cao thì CAS loop quay lại liên tục → có khi CHẬM HƠN mutex
```

Ba mức memory ordering:
```
relaxed          chỉ nguyên tử, không đảm bảo thứ tự  (bộ đếm thống kê)
acquire/release  công cụ chính — release ghép cặp acquire tạo happens-before
seq_cst          mặc định, dễ đúng nhất, đắt nhất
```

> **Dùng `seq_cst` cho tới khi ĐO ĐƯỢC rằng nó là nút thắt.**
> Tối ưu memory ordering là chỗ sinh bug nhiều nhất trên mỗi dòng code.

---

## 9. Deadlock

Bốn điều kiện Coffman — **phá một cái là hết deadlock**:

```
1. Mutual exclusion   — tài nguyên không chia sẻ được
2. Hold and wait      — giữ cái này chờ cái kia
3. No preemption      — không cướp được khoá từ người khác
4. Circular wait      — A chờ B, B chờ C, C chờ A
```

Thực tế chỉ hai cách đáng dùng:

```
① THỨ TỰ KHOÁ TOÀN CỤC   ★ cách chuẩn
   Mọi nơi lấy khoá theo cùng một thứ tự (ví dụ theo địa chỉ tăng dần)
   → phá điều kiện 4. Đơn giản, hiệu quả, không tốn runtime.

② TRY-LOCK CÓ TIMEOUT
   Không lấy được thì nhả hết, chờ ngẫu nhiên, thử lại
   → phá điều kiện 2. Nhưng coi chừng LIVELOCK:
     hai thread cứ nhả rồi thử lại cùng nhịp mãi mãi
     → phải có JITTER (đúng bài học backoff ở WebSocket)
```

Phát hiện: `gdb thread apply all bt`, `pstack`, hoặc ThreadSanitizer
(`-fsanitize=thread`) khi test.

---

## 10. Bảng số liệu cần thuộc

```
Atomic increment (không tranh chấp)      ~ 5-10 ns
Mutex lock/unlock (không tranh chấp)     ~ 20 ns
Cache line ping-pong giữa 2 core         ~ 50-100 ns
Mutex CÓ tranh chấp (futex + switch)     ~ 1.000-5.000 ns
Context switch                           ~ 1.000-2.000 ns (chưa tính hỏng cache)
```

> **Một lần tranh chấp khoá đắt bằng 100 lần khoá không tranh chấp.**
> Mục tiêu tối ưu luôn là *giảm xác suất tranh chấp*, không phải *bỏ khoá đi*.

---

## 11. Góc nhìn phỏng vấn

**Interviewer mong nghe:**
- Phân biệt **atomicity / visibility / ordering** — rất ít người tách bạch được
- Biết **futex**: đường nhanh userspace, đường chậm mới vào kernel
- Nói được **RWLock không mặc nhiên nhanh hơn mutex**, kèm lý do cache
- **False sharing** — dấu hiệu của người từng tối ưu thật
- Thứ tự khoá toàn cục để chống deadlock
- Không tôn sùng lock-free

**Sai lầm thường gặp:**
- Dùng `volatile` (C++) để đồng bộ
- `if` thay vì `while` quanh `cond.wait()`
- Cho rằng thêm RWLock là tăng tốc
- Nhảy vào lock-free trước khi thử giảm tranh chấp

---

## 12. Checklist tự kiểm tra — KHÔNG NHÌN NOTES

1. Ba thứ đồng bộ hoá phải đảm bảo là gì? Ví dụ mỗi thứ hỏng thế nào.
2. Vì sao `volatile` trong C++ không dùng để đồng bộ được?
3. Mutex không tranh chấp tốn bao nhiêu? Có tranh chấp bao nhiêu? Vì sao chênh lớn?
4. Khi nào spinlock đúng? Vì sao spinlock thuần ở userspace là ý tồi?
5. Mutex khác semaphore chỗ nào? Semaphore ánh xạ sang khái niệm nào ở bài LB?
6. Vì sao `cond.wait()` phải nằm trong vòng `while`?
7. Vì sao RWLock có thể chậm hơn mutex?
8. False sharing là gì? Hai thread không chia sẻ dữ liệu vẫn chậm được không?
9. Bốn điều kiện Coffman — thực tế phá cái nào, bằng cách nào?

---

## 13. Bài tập

**Implementation:** viết bộ đếm đồng thời bằng C++ theo 4 cách — (a) mutex,
(b) atomic `seq_cst`, (c) atomic `relaxed`, (d) sharded counter (mỗi thread một
bộ đếm căn 64 byte, gộp lúc đọc). Đo throughput với 1, 2, 4, 8, 16 thread.
Giải thích tại sao (d) thắng, và chứng minh false sharing bằng cách bỏ `alignas`.

**System design:** thiết kế connection pool có giới hạn cho một service.
Dùng primitive nào? Xử lý ra sao khi pool cạn — chờ, hay từ chối ngay?
Nối lại với bài học load shedding ở Load Balancer.
