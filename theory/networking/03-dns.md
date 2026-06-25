# DNS — Domain Name System

Session date: 2026-06-23

---

## 1. Concept

### What Problem DNS Solves

Computers communicate via IP addresses (142.250.185.46). Humans remember names (google.com). DNS is the distributed phone book that maps names to IPs.

Without DNS you'd have to memorize IP addresses for every website — and when Google changes their server IP, everyone would break.

### Why Distributed?

A single DNS server for the entire internet would be:
- A single point of failure
- A massive bottleneck (billions of queries/day)
- Impossible to keep updated globally

DNS is a **hierarchical, distributed database** — no single server knows everything, but any name can be resolved by following the hierarchy.

---

## 2. DNS Hierarchy

```
Root (.)
├── .com
│   ├── google.com
│   │   ├── www.google.com
│   │   └── mail.google.com
│   └── example.com
├── .org
└── .vn
    └── vnexpress.vn
```

**Three levels of DNS servers:**

```
Root Nameservers (13 clusters, operated by ICANN/Verisign/etc.)
        |
TLD Nameservers (.com, .org, .vn — operated by registries)
        |
Authoritative Nameservers (google.com — operated by Google)
```

---

## 3. DNS Resolution — Full Flow

When you type `www.google.com` for the first time:

```
Browser → OS DNS cache → miss
OS → Recursive Resolver (your ISP or 8.8.8.8) → miss

Recursive Resolver:
  1. Query Root NS: "who handles .com?"
     Root NS: "ask TLD NS at 192.5.6.30"

  2. Query TLD NS: "who handles google.com?"
     TLD NS: "ask Authoritative NS at 216.239.32.10"

  3. Query Authoritative NS: "what is www.google.com?"
     Auth NS: "142.250.185.46, TTL=300"

Recursive Resolver → OS → Browser
Browser caches for TTL seconds
```

**Key insight:** The recursive resolver does the work, not your computer. It queries the hierarchy on your behalf and caches the result.

---

## 4. DNS Record Types

| Record | Purpose | Example |
|--------|---------|---------|
| **A** | Domain → IPv4 | `google.com → 142.250.185.46` |
| **AAAA** | Domain → IPv6 | `google.com → 2607:f8b0:...` |
| **CNAME** | Alias → another domain | `www.example.com → example.com` |
| **MX** | Mail server for domain | `example.com → mail.example.com` |
| **NS** | Nameserver for domain | `google.com → ns1.google.com` |
| **TXT** | Arbitrary text | SPF, DKIM, domain verification |
| **PTR** | IP → Domain (reverse DNS) | `142.250.185.46 → google.com` |
| **SOA** | Start of Authority — zone metadata | Serial, refresh interval |

### CNAME Chain Danger

```
www.example.com → CNAME → lb.example.com → CNAME → cdn.example.com → A → 1.2.3.4
```

Each CNAME requires an additional lookup. Long chains add latency. CNAME cannot coexist with other records on the same name (CNAME at zone apex is forbidden — use ALIAS/ANAME instead).

---

## 5. TTL and Caching

**TTL (Time To Live):** How long resolvers can cache the answer before re-querying.

```
Low TTL (60s):   Fresh data, but more queries → higher load on authoritative NS
High TTL (86400s): Fewer queries, but changes propagate slowly
```

**Real-world TTL strategy:**
- Normal operation: TTL = 3600 (1 hour)
- Before planned IP change: lower TTL to 300 (5 min) 24h in advance
- After change: raise TTL back to 3600

This is why "DNS propagation" takes time — you're waiting for cached records to expire across all recursive resolvers worldwide.

---

## 6. DNS in System Design

### Load Balancing via DNS

**Round Robin DNS:** Return multiple A records, rotate order:
```
api.example.com → [1.2.3.4, 1.2.3.5, 1.2.3.6]
Query 1: [1.2.3.4, 1.2.3.5, 1.2.3.6]
Query 2: [1.2.3.5, 1.2.3.6, 1.2.3.4]
Query 3: [1.2.3.6, 1.2.3.4, 1.2.3.5]
```

Limitation: DNS load balancing is not health-aware — if 1.2.3.4 goes down, clients still get it until TTL expires.

**Geo DNS:** Return different IPs based on client location:
```
US client → api-us.example.com → 1.2.3.4 (US server)
VN client → api-us.example.com → 5.6.7.8 (SG server)
```

Used by CDNs (Cloudflare, Akamai) to route users to nearest edge server.

### Failover

Lower TTL → can switch IPs faster during incident. But low TTL means more load on DNS infrastructure.

---

## 7. DNS Security

### DNS Spoofing / Cache Poisoning

Attacker injects fake DNS records into a recursive resolver's cache:
```
Attacker → Resolver: "bank.com = 9.9.9.9 (my server)"
Victim queries bank.com → gets 9.9.9.9 → phishing site
```

**DNSSEC** prevents this: authoritative nameservers sign records cryptographically. Resolvers verify the signature. But DNSSEC adoption is low (~30% of domains).

### DNS over HTTPS (DoH) / DNS over TLS (DoT)

Traditional DNS is **plaintext** — ISP and anyone on the network can see every domain you query. DoH/DoT encrypt DNS traffic:
- DoH: DNS queries inside HTTPS (port 443) — looks like normal web traffic
- DoT: DNS queries over TLS (port 853)

Used by Firefox (Cloudflare DoH by default), Chrome, iOS 14+.

---

## 8. Trade-offs and Failure Scenarios

### DNS as Single Point of Failure

If your authoritative nameserver goes down, your entire domain becomes unreachable — even if your web servers are fine. Mitigation: always have at least 2 authoritative nameservers in different locations.

### Negative Caching

DNS also caches **negative responses** (NXDOMAIN — domain doesn't exist). TTL for negative responses is set in the SOA record. Bug: if you deploy a new subdomain but the negative cache hasn't expired, users still get NXDOMAIN.

### Split-horizon DNS

Different DNS answers for internal vs external clients:
```
Internal: api.company.com → 10.0.0.1 (private IP)
External: api.company.com → 52.1.2.3 (public IP)
```

Common in corporate environments — internal traffic stays on private network.

---

## 9. Interview Perspective

### Common Questions

**Q: What happens when you type google.com in a browser?**
Expected full answer: browser cache → OS cache → recursive resolver → root NS → TLD NS → authoritative NS → IP returned → TCP connection → TLS handshake → HTTP request.

**Q: What is the difference between A record and CNAME?**
A record maps directly to an IP. CNAME maps to another domain name (alias), which then resolves to an IP. CNAME adds an extra lookup. Cannot use CNAME at zone apex.

**Q: How does DNS load balancing work and what are its limitations?**
Round-robin returns multiple IPs, client picks one. Limitation: not health-aware, changes are slow (TTL-bound), no session affinity.

**Q: Why does DNS use UDP?**
Queries fit in one packet (<512 bytes typically). UDP avoids TCP handshake overhead. Falls back to TCP for large responses (DNSSEC, zone transfer).

### What Interviewers Expect at Senior Level

- Trace the full resolution path: browser → recursive resolver → root → TLD → authoritative
- Explain TTL trade-off for planned maintenance
- Know when DNS load balancing breaks (health checks, TTL lag)
- Understand split-horizon DNS for internal routing
- Connect Geo DNS to CDN routing

### Common Mistakes

- Saying "DNS server" without specifying which type (recursive vs authoritative)
- Forgetting that DNS changes don't propagate instantly (TTL)
- Not knowing that CNAME at zone apex is forbidden
- Saying DNS is always UDP (forgetting TCP fallback)

---

## 10. Practical Exercise

Build a DNS lookup tool in Python using only `socket`:

```python
# Milestone 1: send a raw DNS query for an A record, parse the response
# Milestone 2: follow CNAME chains automatically
# Milestone 3: measure RTT difference between 8.8.8.8 and 1.1.1.1
```

### System Design Exercise

Design the DNS infrastructure for a global e-commerce platform (like Shopee). Users in VN, SG, US. How do you:
- Route users to nearest server
- Handle failover when a region goes down
- Minimize DNS lookup latency

### Follow-up Questions

1. Your site goes down but DNS is fine. Your colleague says "let's lower the TTL to fix it faster next time." Is this good advice?
2. A user in Hanoi queries api.example.com and gets a US IP instead of a SG IP. What could cause this?
3. What is the difference between a recursive resolver and an authoritative nameserver?
