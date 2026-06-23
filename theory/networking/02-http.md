# HTTP / HTTPS / HTTP2 / HTTP3

Session date: 2026-06-23

---

## 1. Concept

### What Problem HTTP Solves

TCP gives you a reliable byte stream between two endpoints. But a byte stream has no structure — you don't know where one message ends and another begins, what format the data is in, or what the other side should do with it.

HTTP is an **application-layer protocol** that adds structure on top of TCP:
- Request/response model
- Methods (GET, POST, PUT, DELETE...)
- Headers (metadata about the message)
- Status codes (what happened)
- Content negotiation (what format the body is in)

### Evolution Timeline

```
HTTP/0.9 (1991) → plain GET, no headers
HTTP/1.0 (1996) → headers, status codes, methods — but new TCP per request
HTTP/1.1 (1997) → persistent connections, pipelining, Host header — still HOL blocking
HTTP/2  (2015)  → binary framing, multiplexing, header compression, server push
HTTP/3  (2022)  → QUIC (UDP), eliminates TCP HOL blocking
```

Each version solves a bottleneck the previous version created.

---

## 2. HTTP/1.1

### Persistent Connections

HTTP/1.0 opened a new TCP connection per request (3-way handshake overhead × every request). HTTP/1.1 introduced `Connection: keep-alive` by default — reuse the same TCP connection for multiple requests.

```
HTTP/1.0:
  [TCP handshake] GET /a → response [TCP close]
  [TCP handshake] GET /b → response [TCP close]

HTTP/1.1:
  [TCP handshake]
  GET /a → response
  GET /b → response
  GET /c → response
  [TCP close]
```

### Pipelining (and why it failed)

HTTP/1.1 added pipelining — send multiple requests without waiting for each response. But responses must come back **in order** (HOL blocking at HTTP layer). If request A is slow, requests B and C wait. Browsers mostly disabled pipelining.

### The 6-Connection Workaround

Browsers open up to **6 parallel TCP connections per domain** to work around HTTP/1.1 HOL blocking. This is why domain sharding existed (splitting assets across multiple domains). Hacky but effective before HTTP/2.

### Message Format

```
Request:
GET /index.html HTTP/1.1
Host: example.com
Accept: text/html
User-Agent: Mozilla/5.0
[blank line]
[optional body]

Response:
HTTP/1.1 200 OK
Content-Type: text/html
Content-Length: 1234
[blank line]
[body]
```

Headers are **plaintext** — verbose, repeated on every request (cookies, User-Agent, Accept-Encoding sent every time).

---

## 3. HTTP/2

### Binary Framing Layer

HTTP/2 replaces the text protocol with a binary format. Every message is split into **frames** — small binary chunks tagged with a stream ID.

```
HTTP/1.1 (text):              HTTP/2 (binary frames):
GET /a\r\n                    [frame: HEADERS, stream=1, /a]
Host: ...\r\n                 [frame: HEADERS, stream=3, /b]
\r\n                          [frame: DATA,    stream=1, body]
GET /b\r\n                    [frame: DATA,    stream=3, body]
...
```

### Multiplexing

Multiple requests/responses interleave on **one TCP connection** via stream IDs. No more 6-connection workaround needed.

```
Client                          Server
  |--[stream 1: GET /a]-------> |
  |--[stream 3: GET /b]-------> |
  |--[stream 5: GET /c]-------> |
  | <--[stream 3: 200 /b]------ |   (b came back first)
  | <--[stream 1: 200 /a]------ |
  | <--[stream 5: 200 /c]------ |
```

### Header Compression (HPACK)

HTTP/2 uses HPACK to compress headers. Both sides maintain a **dynamic table** of previously seen headers. Instead of sending `User-Agent: Mozilla/5.0...` on every request, you send an index into the table.

Typical savings: headers shrink from ~800 bytes to ~20-50 bytes per request.

### Server Push

Server can proactively send resources before the client asks. Example: client requests `/index.html`, server pushes `/style.css` and `/app.js` immediately without waiting for the client to parse the HTML.

In practice: server push was rarely used correctly and was removed in Chrome 106 (2022). The overhead often outweighed the benefit.

### HTTP/2 Still Has TCP HOL Blocking

HTTP/2 multiplexing solves *application-layer* HOL blocking. But all streams share one TCP connection — if a TCP segment is lost, **all streams stall** waiting for the retransmit. This is TCP's ordering guarantee at work.

---

## 4. HTTP/3 and QUIC

### The Core Problem with TCP

To fix TCP HOL blocking you have to fix TCP itself. But TCP is implemented in the OS kernel — changing it requires kernel updates across billions of devices. Slow.

The insight: **build a new transport layer in user space, on top of UDP.**

### QUIC

QUIC (originally Google's QUIC, standardized as RFC 9000) is a transport protocol that runs over UDP and implements:
- Connection establishment (0-RTT or 1-RTT)
- Reliability and retransmission
- Flow control and congestion control
- **Per-stream ordering** — a lost packet only stalls the stream it belongs to, not others
- Built-in TLS 1.3 (encryption is mandatory, not optional)

```
HTTP/2 over TCP:              HTTP/3 over QUIC:
Stream 1 ─┐                  Stream 1 ── independent
Stream 3 ──┤── one TCP ──    Stream 3 ── independent
Stream 5 ─┘    (HOL)         Stream 5 ── independent
                              (lost packet in stream 3 only blocks stream 3)
```

### 0-RTT Connection Establishment

TLS 1.3 + QUIC = 1-RTT for new connections (TCP+TLS 1.2 = 3-RTT). For repeat connections, QUIC can resume with **0-RTT** — send data in the very first packet.

```
TCP + TLS 1.2 (new):   SYN → SYN-ACK → ACK → TLS hello → ... → data   (3 RTT)
TCP + TLS 1.3 (new):   SYN → SYN-ACK → ACK → TLS → data              (2 RTT)
QUIC (new):            Initial → data                                   (1 RTT)
QUIC (resume):         data                                             (0 RTT)
```

### Connection Migration

QUIC identifies connections by a **Connection ID**, not by `(IP:port)` tuple. When you switch from WiFi to 4G (your IP changes), your QUIC connection continues. TCP would break because the tuple changed.

---

## 5. HTTPS and TLS

### What HTTPS Adds

HTTPS = HTTP over TLS (Transport Layer Security). TLS provides:
- **Confidentiality** — data is encrypted, nobody in the middle can read it
- **Integrity** — data cannot be tampered with undetected (MAC)
- **Authentication** — server proves its identity via certificate (CA chain)

### TLS Handshake (TLS 1.3)

```
Client                          Server
  |--ClientHello (supported     |
  |   ciphers, key share)-----> |
  |                             |
  | <--ServerHello (chosen      |
  |    cipher, key share,       |
  |    certificate, Finished)-- |
  |                             |
  |--Finished ----------------> |
  |                             |
  |====== Encrypted data ======|
```

TLS 1.3 reduced handshake from 2 RTT (TLS 1.2) to 1 RTT. Removes weak cipher suites, mandatory forward secrecy.

### Certificate Chain

```
Root CA (trusted by OS/browser)
  └── Intermediate CA
        └── Server Certificate (example.com)
```

Browser verifies: is this cert signed by a trusted CA? Is the domain name correct? Is it expired? Is it revoked (OCSP/CRL)?

### Forward Secrecy

TLS 1.3 mandates **ephemeral keys** (ECDHE) — the session key is generated fresh for every connection and never stored. Even if the server's private key is stolen later, past sessions cannot be decrypted.

---

## 6. Key Trade-offs

| | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| Transport | TCP | TCP | QUIC (UDP) |
| HOL Blocking | App + TCP layer | TCP layer only | None |
| Multiplexing | No (6 conn workaround) | Yes (1 conn) | Yes (1 conn) |
| Header compression | No | HPACK | QPACK |
| Encryption | Optional | Optional (but de-facto required) | Mandatory |
| Connection migration | No | No | Yes |
| Adoption complexity | Simple | Moderate | High (UDP may be blocked by firewalls) |

### When HTTP/3 Isn't Better

- High-quality networks (datacenter internal): HTTP/2 is fine, no TCP HOL benefit
- UDP blocked by firewall/middleboxes: HTTP/3 falls back to HTTP/2
- Debugging: HTTP/3 is harder to inspect (encrypted at transport layer)

---

## 7. Interview Perspective

### Common Questions

**Q: What is the difference between HTTP/1.1 and HTTP/2?**
HTTP/2 adds binary framing, multiplexing (multiple requests on one connection), and HPACK header compression. Eliminates the need for domain sharding and connection pooling hacks. Still shares TCP's HOL blocking.

**Q: Why was HTTP/3 built on UDP instead of TCP?**
To eliminate TCP HOL blocking without waiting for kernel-level TCP changes. QUIC implements its own reliability per stream in user space, so a lost packet only stalls its own stream.

**Q: What is TLS and why does HTTPS need it?**
TLS is a cryptographic protocol providing confidentiality, integrity, and server authentication. Without it, anyone between client and server can read or modify the data (man-in-the-middle attack).

**Q: What is forward secrecy and why does it matter?**
Per-session ephemeral keys mean past sessions are safe even if the server key is later compromised. TLS 1.3 makes this mandatory.

**Q: What's the difference between HTTP/2 server push and a CDN?**
Server push proactively sends resources from the origin before the client requests them — for one connection. A CDN caches content at edge servers geographically close to users, reducing latency for everyone.

### What Interviewers Expect at Senior Level

- Explain HOL blocking at both HTTP and TCP layers, and which HTTP version fixes which
- Know that HTTP/2 still has TCP HOL blocking
- Explain the TLS handshake at a high level, know TLS 1.3 improvements
- Understand QUIC's connection ID and connection migration
- Connect HTTP/2 multiplexing to why browsers no longer need 6 connections per domain

### Common Mistakes

- Saying "HTTP/2 solves HOL blocking" — it only solves the application-layer HOL, not TCP-layer
- Confusing TLS with HTTPS (HTTPS = HTTP + TLS)
- Not knowing that HTTP/3 requires TLS (it's built into QUIC)
- Forgetting that 0-RTT has replay attack risk (safe for idempotent requests only)

---

## 8. Practical Exercise

### Implementation Exercise

Build a minimal HTTP/1.1 server in Python from raw TCP sockets:

```python
# Milestone 1: accept TCP connection, parse HTTP request line and headers
# Milestone 2: route GET requests, return 200/404
# Milestone 3: support keep-alive (parse Content-Length to know when request ends)
# Milestone 4: measure latency difference with/without keep-alive
```

### System Design Exercise

Design a web server that serves 10,000 concurrent users downloading a 1MB file each. What HTTP version do you use? How many connections does the server maintain? Where does the bottleneck move to?

### Follow-up Questions

1. A user reports slow page loads. You see the browser is opening 6 TCP connections to your domain. What does this tell you about the HTTP version in use, and how would you fix it?
2. Your CDN terminates TLS at the edge. Does the traffic between CDN edge and your origin server need to be encrypted? Why or why not?
3. Why can 0-RTT in QUIC be dangerous for POST requests?
