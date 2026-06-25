# Load Balancer

Session date: 2026-06-25

---

## 1. Concept

### What Problem It Solves

A single server has limits — CPU, RAM, network bandwidth, concurrent connections. When traffic grows beyond one server's capacity, you need multiple servers. But the client only knows one address.

A **load balancer** sits in front of a pool of servers and distributes incoming requests across them. To clients, it looks like a single endpoint. Behind it, you can scale horizontally to hundreds of servers.

```
                    ┌──────────────┐
Client ──────────▶  │ Load Balancer│ ──▶ Server 1
                    │              │ ──▶ Server 2
                    └──────────────┘ ──▶ Server 3
```

### Why Not Just DNS Round Robin?

DNS round robin distributes at the DNS level — clients get different IPs. Problems:
- Not health-aware: DNS keeps returning a dead server's IP until TTL expires
- No session affinity: next request may go to a different server
- Client-side caching breaks the distribution

Load balancers operate at the connection/request level — much finer-grained control.

---

## 2. Types of Load Balancers

### Layer 4 (Transport Layer)

Operates on TCP/UDP — routes based on IP and port only, without looking at packet contents.

```
Client TCP connection → LB → Server TCP connection
(LB sees: src IP, dst IP, src port, dst port)
```

- **Fast:** minimal processing, just routing
- **Blind:** can't route based on URL, headers, or cookies
- Examples: AWS NLB, HAProxy in TCP mode

### Layer 7 (Application Layer)

Operates on HTTP/HTTPS — can inspect request content before routing.

```
Client HTTP request → LB reads headers/URL → routes to appropriate server
```

- **Smart:** route `/api/*` to API servers, `/static/*` to CDN, `/admin/*` to admin servers
- **Slower:** must parse HTTP, terminate TLS
- **More features:** SSL termination, request rewriting, A/B testing, rate limiting
- Examples: nginx, AWS ALB, Cloudflare, HAProxy in HTTP mode

---

## 3. Load Balancing Algorithms

### Round Robin

Requests distributed in rotation: 1→2→3→1→2→3...

```
Request 1 → Server 1
Request 2 → Server 2
Request 3 → Server 3
Request 4 → Server 1
```

Simple but ignores server load — sends equal requests regardless of whether Server 1 is handling a 1s query and Server 3 is idle.

### Weighted Round Robin

Servers with more capacity get more requests.

```
Server 1 (weight=3): gets 3 requests
Server 2 (weight=1): gets 1 request
→ 75% traffic to Server 1
```

Useful when servers have different hardware specs.

### Least Connections

Route to server with fewest active connections.

```
Server 1: 100 connections
Server 2: 20 connections  ← next request goes here
Server 3: 80 connections
```

Better than round robin when requests have variable duration (some take 10ms, some take 5s).

### Least Response Time

Route to server with lowest average response time + fewest connections. More sophisticated version of least connections.

### IP Hash

Hash the client IP → always route same client to same server.

```
hash(client_IP) % num_servers = server_index
```

Provides **session affinity** (sticky sessions) — same client always hits same server. Useful when session state is stored locally on the server. Problem: uneven distribution if one IP has many clients (corporate NAT).

### Consistent Hashing

More advanced version of IP hash. Minimizes re-routing when servers are added/removed. Used in distributed caches. (Covered in depth in Phase 3.)

---

## 4. Health Checks

Load balancer continuously probes servers to detect failures:

```
LB → GET /health → Server 1 → 200 OK ✅
LB → GET /health → Server 2 → timeout ❌ → remove from pool
LB → GET /health → Server 3 → 200 OK ✅

(Server 2 recovers)
LB → GET /health → Server 2 → 200 OK ✅ → add back to pool
```

**Passive health check:** detect failure from actual request errors (5xx, timeout).
**Active health check:** LB proactively pings `/health` endpoint every N seconds.

Health check endpoint should verify the full stack: DB connection, cache connection, not just HTTP 200.

---

## 5. SSL Termination

Layer 7 LB can terminate TLS:

```
Client ──[HTTPS]──▶ LB ──[HTTP]──▶ Server pool
         (encrypted)      (plaintext, internal network)
```

Benefits:
- Servers don't need to handle TLS overhead (CPU-intensive)
- Single place to manage certificates
- LB can inspect/modify requests (needed for routing decisions)

Drawback: traffic between LB and servers is unencrypted — acceptable on private VPC, not on public network. Solution: re-encrypt (end-to-end TLS) or use mTLS internally.

---

## 6. High Availability for the Load Balancer Itself

The LB is now a single point of failure. Fix: two LBs in active-passive or active-active mode.

```
                 ┌─── LB Primary (active)
DNS / VIP ───▶  │
                 └─── LB Secondary (standby)
                      (takes over via VRRP/keepalived if primary fails)
```

**Virtual IP (VIP):** A floating IP that belongs to whichever LB is active. When primary fails, secondary claims the VIP — clients reconnect transparently.

---

## 7. Load Balancer in System Design

### Global vs Local Load Balancing

```
User
 |
 ▼
Global LB (DNS-based, Geo DNS) → routes to nearest region
 |
 ▼
Regional LB (Layer 7) → distributes to servers in region
 |
 ▼
Server pool
```

### Reverse Proxy vs Load Balancer

Often confused:
- **Reverse proxy:** intermediary that handles requests on behalf of servers. Can do caching, compression, SSL termination, request rewriting.
- **Load balancer:** distributes requests across multiple servers.

A reverse proxy can include load balancing. nginx does both. Conceptually distinct but practically overlapping.

---

## 8. Trade-offs

| | Layer 4 LB | Layer 7 LB |
|---|---|---|
| Speed | Faster (no content inspection) | Slower |
| Routing intelligence | IP + port only | URL, headers, cookies |
| SSL termination | No | Yes |
| Cost | Lower | Higher |
| Use case | Raw TCP throughput, gaming, streaming | HTTP APIs, microservices |

### Connection Draining

When removing a server from the pool (deploy, scale-down), don't kill active connections immediately:
1. Stop sending new requests to the server
2. Wait for in-flight requests to complete (grace period, e.g., 30s)
3. Then terminate

Without draining: users get mid-request errors during deployments.

### Thundering Herd

When a server comes back online after failure, LB floods it with backlogged requests → server crashes again. Solution: **slow start** — gradually ramp up traffic to new/recovered servers.

---

## 9. Interview Perspective

### Common Questions

**Q: What is the difference between L4 and L7 load balancer?**
L4 routes based on TCP/IP (fast, blind). L7 routes based on HTTP content (slower, smart — can route by URL, headers, cookies, do SSL termination).

**Q: What algorithm would you use for a stateful application?**
IP hash or consistent hashing for session affinity. Or move session state to a shared store (Redis) so any server can handle any request.

**Q: How do you make the load balancer itself highly available?**
Active-passive pair with Virtual IP (VIP). VRRP/keepalived for failover. Or use a managed LB (AWS ALB) that has HA built-in.

**Q: What is connection draining and why is it needed?**
Graceful removal of a server — stop new traffic but let existing requests complete. Prevents errors during deployments.

### What Interviewers Expect at Senior Level

- Know the difference between L4 and L7, when to use each
- Choose the right algorithm for the use case (round robin vs least connections vs IP hash)
- Address LB as a SPOF — active-passive HA
- Mention connection draining for zero-downtime deployments
- Connect to global architecture: DNS/Geo DNS for global routing, regional LB for local distribution

### Common Mistakes

- Designing a system with a load balancer but forgetting it's a SPOF
- Using round robin for long-running connections (use least connections instead)
- Not mentioning health checks
- Confusing reverse proxy with load balancer

---

## 10. Practical Exercise

Build a simple L7 load balancer in Python:

```python
# Milestone 1: round-robin across 3 HTTP servers
# Milestone 2: health check — skip unhealthy servers
# Milestone 3: least-connections algorithm
```

### System Design Exercise

Design the load balancing layer for a ride-hailing app (like Grab) during peak hours (New Year's Eve — 10x normal traffic). How do you handle:
- Sudden traffic spike
- Driver location update service (high write throughput)
- Rider-driver matching service (stateful)
