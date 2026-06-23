# System Design: Real-time Multiplayer Game Backend

Ngày: 2026-06-23

---

## Bài toán

Thiết kế backend cho game bắn súng real-time (như CS:GO, Valorant).
- 100 players trong cùng một match
- Mỗi player gửi position update 60 lần/giây

---

## Câu 1 — Transport Layer

**Dùng TCP hay UDP?**

**Trả lời: UDP.**

Nếu dùng TCP:
- Position update 60 lần/giây → packet t=100ms bị mất → TCP retransmit
- Packet t=116ms, t=133ms đã đến receiver nhưng bị buffer do HOL blocking
- Đến lúc t=100ms retransmit xong, data đã stale — player đã di chuyển rồi
- Game engine nhận data cũ → giật lag

Với UDP: t=100ms mất → bỏ qua, render t=116ms luôn. Mượt hơn dù thiếu một frame.

---

## Câu 2 — Xử lý packet mất

**Có cần retry không khi position update bị mất?**

**Trả lời: Không.**

Position update là **stale data** — cái mới nhất luôn quan trọng hơn cái cũ. Packet t=100ms mất, packet t=116ms đến → server dùng t=116ms, không cần biết t=100ms nữa.

Pattern này gọi là **fire-and-forget** — sender bắn liên tục, không cần confirmation.

> Retry chỉ cần thiết với data quan trọng không thể bỏ qua: chat message, kết quả match, transaction. Không phải position update.

---

## Câu 3 — Ordering

**100 players gửi đồng thời, packet đến không theo thứ tự. Server xử lý thế nào?**

**Trả lời: Timestamp + Sequence number.**

**Cách 1 — Timestamp:**

Mỗi packet kèm timestamp của client. Server luôn lấy packet có timestamp mới nhất cho mỗi player, bỏ qua packet cũ hơn dù đến sau.

```
Player A gửi:  t=116ms (đến trước)
               t=133ms (đến sau)

Server: nhận t=116ms → update position A
        nhận t=133ms → mới hơn → update position A
        nhận t=100ms muộn → bỏ qua, cũ hơn t=116ms
```

**Cách 2 — Sequence number:**

Mỗi packet có seq number tăng dần. Server chỉ xử lý seq lớn hơn seq cuối đã xử lý.

```
Player A: seq=10 → xử lý
          seq=12 → xử lý
          seq=11 → drop (đã qua seq=12)
```

**Thực tế:** Game dùng cả hai — seq number để detect out-of-order, timestamp để interpolate vị trí giữa các frame.

---

## Câu 4 — Server Reconciliation (Lag Compensation)

**Player A thấy mình bắn trúng Player B lúc t=100ms trên client. Server tính lại thấy Player B đã chạy khỏi đó lúc t=95ms. Ai đúng?**

**Trả lời: Server-side Lag Compensation.**

**Vấn đề gốc rễ:**

```
Client A (ping 50ms):  thấy player B ở vị trí X lúc t=100ms → bắn
Server nhận shot lúc:  t=150ms (100ms + 50ms network delay)
Lúc t=150ms:          Player B thực ra đã ở vị trí Y rồi
```

**Giải pháp:** Server lưu lịch sử game state trong rolling buffer (~1 giây):

```
t=50ms:  {playerB: position=X-2}
t=100ms: {playerB: position=X}
t=150ms: {playerB: position=Y}  ← hiện tại
```

Khi nhận shot từ Player A timestamp t=100ms:
1. Server rewind game state về t=100ms
2. Hit detection tại thời điểm đó → Player B ở X → trúng
3. Apply damage vào game state hiện tại

**Trade-off:**

| | Server Authority | Lag Compensation |
|--|--|--|
| Fairness với người ping thấp | Có lợi | Cân bằng hơn |
| Fairness với người ping cao | Bất lợi | Cải thiện |
| Khả năng bị exploit | Khó | Dễ nếu không giới hạn rewind time |

**Thực tế:** Valve (CS:GO) giới hạn rewind tối đa **200ms** — ping cao hơn 200ms thì shot không được lag compensate nữa.

---

## Tóm tắt kiến trúc

```
Client (60 updates/giây, UDP, fire-and-forget)
         |
         v
Game Server
  - Nhận UDP packet
  - Validate timestamp/seq, drop stale
  - Lag compensation: rewind state để hit detection
  - Broadcast game state ra 100 clients
         |
         v
State History Buffer (rolling ~1 giây)
```

## Điểm cần nhớ

- Position update → UDP + fire-and-forget (stale data không cần retry)
- Ordering → timestamp hoặc seq number, drop packet cũ
- Lag compensation → server rewind state, giới hạn rewind window (200ms)
- Server là authority cuối cùng — client chỉ predict, server confirm
