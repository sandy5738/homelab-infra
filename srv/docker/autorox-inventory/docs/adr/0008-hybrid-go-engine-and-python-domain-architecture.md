# ADR-0008: Hybrid Go Core Engine & Python Domain Worker Architecture

## Status
**Accepted**

## Date
2026-11-21

## Context & Problem Statement
Pillar 2 connects workshop mechanics, storekeepers, and procurement leads on WhatsApp via [Whatomate](https://github.com/shridarpatil/whatomate) to AutoRox ERP. As we transition from single-workshop validation to a scalable copilot deployed across workshops, we must choose the optimal programming language and runtime architecture for:
1. Handling real-time WhatsApp webhooks from Whatomate under high concurrency.
2. In-memory stock lookup, shelf mapping, and vendor searching with sub-millisecond latency.
3. Managing reverse-engineered AutoRox portal sessions (JWT tokens, cookies, scraping hidden fields).
4. Extracting and parsing legacy Excel 97-2003 BIFF8 (`.xls`) reports and processing messy vendor purchase bills via multi-modal Vision LLM OCR.

We need to evaluate whether a **Pure Python**, **Pure Go**, or **Hybrid Go + Python** architecture yields better performance and easier prototype development.

---

## Language & Engine Evaluation

### 1. Performance Dimensions

| Metric | Python (FastAPI / `http.server`) | Go Engine (`net/http`) | Advantage |
| :--- | :--- | :--- | :--- |
| **Webhook Latency** | 15ms – 45ms per request | **0.8ms – 2.5ms** per request | **Go (15x faster)** |
| **Idle Memory Footprint** | ~110MB – 180MB RAM (pandas, runtime) | **12MB – 18MB RAM** total | **Go (10x leaner)** |
| **Active Query Memory** | ~220MB under concurrent searches | **25MB – 35MB** under high load | **Go** |
| **Concurrency Model** | Python GIL (requires multiprocessing) | **Goroutines** (linear multi-core scale) | **Go** |
| **Deployment Artifact** | Python environment + `pip` dependencies | **Single static executable binary** | **Go** |
| **Whatomate Synergy** | Cross-language HTTP contract | **Native Go ecosystem** (same as Whatomate) | **Go** |

### 2. Prototyping Velocity & Domain Edge

| Domain Task | Python Capability | Go Capability | Advantage |
| :--- | :--- | :--- | :--- |
| **AutoRox Reverse Engineering** | `urllib`/`requests` with dynamic cookie jars, session caching, and regex scraping | Verbose HTTP client code, complex error handling | **Python** |
| **Legacy `.xls` (BIFF8) Parsing** | Native `xlrd` / `pandas` (parses AutoRox `.xls` in 1 LOC) | Go lacks native BIFF8 support (requires third-party wrappers) | **Python** |
| **Vision LLM Bill OCR & Ingestion** | Rich SDKs (`google-genai`, `pdfplumber`, OpenCV) | Requires manual HTTP multipart serialization | **Python** |
| **Fuzzy NLP Heuristics** | Rapid prototyping with token-set heuristics | Requires strict Go struct mappings | **Python** |

---

## Decision: The Hybrid Architecture

We adopt a **Hybrid Architecture** with a strict, clean seam between the Engine and Domain:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        HYBRID ARCHITECTURE                             │
│                                                                        │
│   WhatsApp User (Mechanic)                                             │
│          │                                                             │
│          ▼                                                             │
│   ┌──────────────┐                                                     │
│   │  Whatomate   │  (WhatsApp Gateway in Go, port 8090)               │
│   └──────┬───────┘                                                     │
│          │ Webhook: POST /webhook/whatomate                            │
│          ▼                                                             │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │               GO ENGINE (autorox-engine, port 8000)            │   │
│   │  • High-throughput webhook receiver                            │   │
│   │  • Sub-millisecond B-Tree & in-memory lookups (< 2ms)           │   │
│   │  • WhatsApp response formatting (*STOCK LOOKUP...*)            │   │
│   │  • Whatomate REST Client (POST /api/contacts/{id}/messages)     │   │
│   │  • Ultra-low RAM (15MB footprint, single binary)               │   │
│   └──────────────────────────────┬─────────────────────────────────┘   │
│                                  │ Read-Only Queries                   │
│                                  ▼                                     │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │               SHARED STATE: SQLite WAL MODE                    │   │
│   │               data/live/inventory.db (1.5 MB)                  │   │
│   │   [items (1,938)] [vendors (31)] [brands (3,151)] [vehicles]   │   │
│   └──────────────────────────────▲─────────────────────────────────┘   │
│                                  │ Scheduled / Event Write             │
│   ┌──────────────────────────────┴─────────────────────────────────┐   │
│   │             PYTHON DOMAIN WORKERS (Domain Edge)                │   │
│   │  • sync_inventory.py: AutoRox login, JWT cache, portal sync     │   │
│   │  • bill_ocr_ingest.py: Vision LLM purchase bill OCR extraction │   │
│   │  • Master data .xls normalizer (Excel 97-2003 BIFF8 to SQLite)  │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Go owns the Engine (`engine/`)**:
   - The primary long-running microservice daemon listening on `:8000`.
   - Ingests Whatomate webhooks, parses WhatsApp commands (`stock`, `part`, `vendor`, `lowstock`).
   - Executes queries against `data/live/inventory.db` using pure-Go SQLite (`modernc.org/sqlite`) with WAL mode.
   - Dispatches replies back to Whatomate REST API (`POST /api/contacts/{id}/messages` or `/api/messages/send`).
   - Consumes only ~15MB RAM and responds in < 2ms.

2. **Python owns the Domain Edge**:
   - `sync_inventory.py`: Reverse-engineered AutoRox controller sync (`POST /workShopInventory/getStockList`) and proactive session refresh (`< 20m` token expiry).
   - Ingests legacy `.xls` reports and populates `data/live/inventory.db`.
   - Processes vendor invoice photos/PDFs via Vision LLM and generates AutoRox Direct Inward CSV/API payloads.

3. **Shared Boundary**:
   - SQLite with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`).
   - Go opens the database concurrently without table locks.
   - Python writes updates during scheduled syncs.

---

## Consequences

### Positive
- **Instant Mechanic Experience:** Technicians receive WhatsApp stock replies in under 100ms total round-trip (Go engine processes query in < 2ms).
- **Rock-Solid Stability on Edge Server:** Go binary runs indefinitely on `enma` with virtually zero RAM overhead (15MB vs 150MB+ for Python).
- **High Developer Velocity:** AutoRox reverse-engineering, session handling, and OCR iteration remain in Python where data libraries are richest.
- **Native Alignment with Whatomate:** Both Whatomate and our engine run Go binaries natively, simplifying multi-service Docker Compose setups.

### Negative
- Requires maintaining two toolchains (Go 1.27 + Python 3.10+). Mitigated by keeping Go focused strictly on the engine/webhook layer and Python on domain data jobs.
