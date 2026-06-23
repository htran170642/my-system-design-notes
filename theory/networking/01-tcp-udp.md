# TCP / UDP

Session date: 2026-06-23

---

## 1. Concept

### The Problem They Solve

The internet delivers data as **packets** — small chunks that travel independently across routers. Without a transport layer, you'd need to handle:
- Packets arriving out of order
- Packets getting lost
- The receiver being overwhelmed with data
- No way to know if the other side is even alive

TCP and UDP are two different answers to "how do we build communication on top of unreliable packet delivery."

### Why Two Protocols Exist

The same core tension appears everywhere in distributed systems: **reliability vs. latency**.

- **TCP** chooses reliability. It guarantees delivery, order, and integrity — but pays for it with overhead (handshakes, ACKs, retransmits).
- **UDP** chooses speed. It fires packets and forgets them — the application decides what to do about loss.

Real-world usage:

| Protocol | Used By |
|----------|---------|
| TCP | HTTP, HTTPS, databases, SSH, email (SMTP/IMAP) |
| UDP | DNS, video streaming, online games, VoIP, QUIC (HTTP/3) |

---

## 2. TCP — Transmission Control Protocol

### Core Properties

- **Connection-oriented:** must establish a connection before sending data (3-way handshake)
- **Reliable delivery:** lost packets are detected and retransmitted
- **Ordered:** bytes arrive in the order they were sent
- **Flow control:** prevents sender from overwhelming receiver
- **Congestion control:** prevents sender from overwhelming the network

### The 3-Way Handshake

```
Client                      Server
  |                            |
  |------- SYN (seq=x) ------> |   "I want to connect, my seq starts at x"
  |                            |
  | <----- SYN-ACK (seq=y,    |   "OK, my seq starts at y, I got your x"
  |         ack=x+1) ---------|
  |                            |
  |------- ACK (ack=y+1) ----> |   "Got it, connection open"
  |                            |
  |====== DATA FLOWS ==========|
```

Why 3 steps and not 2? Both sides must prove they can send AND receive. With 2 steps, the server doesn't know if its SYN-ACK reached the client.

### Connection Teardown (4-Way)

```
Client                      Server
  |                            |
  |------- FIN --------------> |   "I'm done sending"
  | <----- ACK --------------- |   "Got it"
  | <----- FIN --------------- |   "I'm done too"
  |------- ACK --------------> |   "Got it, connection closed"
```

The client enters `TIME_WAIT` (2 * MSL, typically 60s) before fully closing — ensures the final ACK reaches the server if it was lost.

### Sequence Numbers and ACKs

Every byte has a sequence number. The receiver sends ACKs saying "I've received up to byte N, send me N+1 next." This is what enables:
- Ordered delivery (buffer out-of-order packets, deliver in order)
- Retransmission (detect missing ACKs via timeout or duplicate ACKs)

### Flow Control — Sliding Window

The receiver advertises a **receive window** (rwnd) — how many bytes it can buffer right now. The sender can have at most `rwnd` bytes in-flight (sent but not ACK'd). If the receiver's buffer fills up, it sets rwnd=0, pausing the sender.

```
Sender                         Receiver
  |                               |
  | [sent & ACK'd] [in-flight] -> | rwnd = 64KB
  |                [can send more]|
```

### Congestion Control

Flow control handles receiver capacity. Congestion control handles **network capacity** — routers in the middle dropping packets because they're overwhelmed.

TCP infers congestion from packet loss. Key algorithms:

**Slow Start:**
- Start with cwnd (congestion window) = 1 MSS
- Double cwnd every RTT until hitting ssthresh or loss
- Exponential growth

**Congestion Avoidance:**
- Once cwnd > ssthresh, grow by 1 MSS per RTT (linear)

**On loss (timeout):**
- ssthresh = cwnd / 2
- cwnd = 1 (restart slow start)

**On loss (3 duplicate ACKs — Fast Retransmit):**
- ssthresh = cwnd / 2
- cwnd = ssthresh (skip slow start, jump to congestion avoidance)

```
cwnd
 ^
 |     /
 |    /
 |   / (slow start)
 |--/-------- ssthresh
 | /  (congestion avoidance, linear)
 |/
 +----------------------------> time
```

Real-world: Modern Linux uses **CUBIC** (default) or **BBR** (Google's bandwidth-based algorithm). BBR doesn't react to packet loss — it models the bottleneck bandwidth directly.

---

## 3. UDP — User Datagram Protocol

### Core Properties

- **Connectionless:** no handshake, just send
- **Unreliable:** no retransmits, no ACKs
- **Unordered:** packets may arrive in any order
- **No flow/congestion control:** sender can flood the receiver

### What UDP Gives You

A thin wrapper over IP that adds only:
- Source/destination ports (for demultiplexing)
- Length
- Optional checksum

That's it. No state, no overhead, no per-connection machinery.

### When UDP Wins

**Latency-sensitive, loss-tolerant:**
- Video calls: a dropped frame is better than a stale one delivered late
- Gaming: old position data is useless; you want the latest, fast
- DNS: single request/response — TCP's handshake costs more than the query

**Applications that implement their own reliability:**
- QUIC (HTTP/3) uses UDP but implements its own connection, retransmit, and congestion control at the application layer — gaining freedom to innovate without OS kernel changes

**Multicast/broadcast:**
- UDP supports one-to-many; TCP is strictly point-to-point

---

## 4. TCP vs UDP Comparison

| Property | TCP | UDP |
|----------|-----|-----|
| Connection | Yes (3-way handshake) | No |
| Reliability | Guaranteed | Best-effort |
| Ordering | Yes | No |
| Flow control | Yes (rwnd) | No |
| Congestion control | Yes (cwnd) | No |
| Overhead per packet | High (20B header + state) | Low (8B header) |
| Latency | Higher | Lower |
| Use case | Files, web, databases | Video, DNS, gaming |

---

## 5. Trade-offs and Failure Scenarios

### TCP Head-of-Line Blocking

If packet N is lost, packets N+1, N+2, ... are buffered at the receiver and not delivered to the application until N arrives. This is fundamental to how TCP ordering works.

**Impact:** In HTTP/1.1, one slow response blocks the whole connection. HTTP/2 multiplexes requests over one TCP connection but still suffers TCP-level HOL blocking. HTTP/3 (QUIC over UDP) fixes this by implementing per-stream retransmission.

### TCP Connection State Overhead

Each TCP connection requires state at both endpoints (sequence numbers, buffers, timers). A server with 100k concurrent connections holds 100k state machines. This is why `TIME_WAIT` accumulation can exhaust ports on high-traffic servers.

### UDP Amplification Attacks

UDP's lack of connection means a client can spoof a source IP and send small requests to a server that responds with large replies — reflecting traffic to a victim. DNS amplification is the classic example (30B request → 3000B response). TCP's handshake prevents this because the spoofed IP never completes the SYN-ACK.

### Elephant Flows

Long-lived, high-bandwidth TCP flows (database backups, file transfers) can starve smaller flows by hogging congestion windows. ECMP routing and QoS policies address this at the infrastructure level.

---

## 6. Interview Perspective

### Common Questions

**Q: Why does HTTP use TCP and not UDP?**
HTTP was designed for reliable document transfer — you need every byte of HTML/CSS/JS. Retransmitting a missing packet is acceptable; delivering corrupted content is not.

**Q: Why does DNS use UDP?**
DNS queries/responses fit in a single packet (usually <512 bytes). UDP avoids the ~1.5 RTT overhead of the TCP handshake. DNS falls back to TCP for large responses (zone transfers, DNSSEC).

**Q: What happens if a TCP segment is lost?**
The receiver sends duplicate ACKs for the last good byte. After 3 duplicate ACKs, the sender fast-retransmits the missing segment without waiting for a timeout. If the timeout fires first, the sender also retransmits and resets its congestion window.

**Q: How does TCP prevent a fast sender from overwhelming a slow receiver?**
Receive window (rwnd): the receiver tells the sender its buffer capacity. The sender cannot have more than rwnd bytes in-flight.

**Q: What is the difference between flow control and congestion control?**
Flow control is end-to-end: prevents overwhelming the *receiver's buffer*. Congestion control is network-aware: prevents overwhelming *routers in between*. Both limit how much data can be in-flight but they're controlled independently.

### What Interviewers Expect at Senior Level

- Know *why* the 3-way handshake requires 3 steps, not 2
- Explain HOL blocking and how QUIC/HTTP3 addresses it
- Know that congestion control reacts to loss, BBR reacts to bandwidth
- Understand why TIME_WAIT exists and what happens if you disable it
- Connect UDP's properties to real design decisions (why your video call uses UDP)

### Common Mistakes

- Confusing flow control (rwnd) with congestion control (cwnd)
- Saying "TCP guarantees delivery" without qualifying "within a connection" — if the connection drops, data in-flight is lost
- Forgetting that UDP checksum is optional in IPv4
- Not knowing that QUIC runs over UDP

---

## 7. Practical Exercise

### Implementation Exercise

Build a simple reliable UDP layer in Python:

```python
# Goal: implement Stop-and-Wait ARQ over UDP
# - sender sends a packet with a sequence number
# - receiver ACKs it
# - if ACK not received in timeout, sender retransmits
# - implement in ~100 lines to understand what TCP does for you
```

Milestone 1: Basic send/receive with sequence numbers
Milestone 2: Timeout and retransmit
Milestone 3: Measure throughput vs raw UDP and TCP

### System Design Exercise

Design a real-time multiplayer game backend. What transport layer do you use and why? How do you handle:
- A player's move packet being lost
- Ordering of moves from multiple players
- Server reconciliation of game state

### Follow-up Questions

1. You're building a video conferencing app. A user on a bad network loses 10% of packets. How does your choice of TCP vs UDP affect the call quality?
2. Why might a database connection pool use TCP keepalives? What problem do they solve?
3. HTTP/3 uses QUIC over UDP. What does QUIC reimplement that TCP already provides?

---

## Summary

TCP = reliability machinery built into the OS. Pays for it with latency, head-of-line blocking, and connection setup cost. The right choice when you need every byte.

UDP = bare-metal speed. You get ports and checksums; everything else is your problem. Right for latency-sensitive or loss-tolerant applications, or when you want to build custom reliability.

The deeper lesson: TCP's features aren't free. Every time you use TCP, you're paying for ordering, retransmission, flow control, and congestion control — even when you don't need them. Understanding *what those features cost* is what lets you design systems that choose the right tool.
