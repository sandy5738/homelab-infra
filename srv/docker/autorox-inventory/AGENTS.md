# AGENTS.md: WhatsApp Inventory & Bill Copilot

Guidelines, configuration, and workflows for AI agents working in this repository.

---

## 1. Project Overview & Architectural Vision

This project builds an autonomous **WhatsApp Inventory & Purchase-Bill Copilot** for multi-brand automotive repair workshops across India.

- **Beachhead Wedge:** Deep integration with AutoRox Garage ERP (`bcsin.autorox.co`).
- **Target Evolution:** Multi-tenant, ERP-agnostic middleware connecting to TallyPrime, Busy, Marg, Vyapar, and GaragePlug.
- **Core Functionality:**
  1. Instant WhatsApp stock & shelf lookups for mechanics (`stock Creta oil filter` ➔ `Stock: 4 | Shelf: A1-R1-S3`).
  2. OCR bill ingestion: Photo/PDF of vendor invoice ➔ Extraction + Fitment matching + Direct Inward.
  3. Margin leakage & price hike detection on supplier bills.
  4. Daily 9:00 AM automated low-stock reorder digest.

---

## 2. Agent Skills

This repo has Matt Pocock's engineering and productivity skills installed under `.agents/skills/`.

### Core Skills
- `/research`: Investigate questions against primary sources and write Markdown reports.
- `/grill-with-docs`: Interactive architectural alignment before writing code.
- `/to-spec`: Synthesize aligned plans into rigorous technical specifications.
- `/to-tickets`: Decompose specs into vertical, dependency-managed tickets.
- `/implement`: Slice-by-slice implementation with strict test-driven development (TDD).
- `/tdd`: Red-green-refactor loop enforcement.
- `/code-review`: Dual-axis review against repo standards and spec requirements.
- `/domain-modeling`: Refine terms in `GLOSSARY.md` and document decisions in `docs/adr/`.

### Issue Tracker
Issues, specs, and task tracking live as local Markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Domain Docs
Read `GLOSSARY.md` and `docs/adr/` before starting any major architectural changes. See `docs/agents/domain.md`.

---

## 3. Architecture Decision Records (ADRs)

Key architectural decisions are documented in `docs/adr/`:
- **ADR-0001**: Pillar 2 Microservice Architecture & Infrastructure Topology
- **ADR-0002**: Master Data Hybrid Storage & In-Memory SQLite Store
- **ADR-0003**: Role Scoping & Storekeeper Least Privilege Enforcement (`ROLE_SPARESINCHARGE`)
- **ADR-0004**: Core Portal Controller Integration (`POST /workShopInventory/getStockList`)
- **ADR-0005**: Proactive Session & Token Caching with 20-Min Refresh Window
- **ADR-0006**: Accounting-Compliant Stock Inwarding via Direct Inward Engine
- **ADR-0007**: Safe Query Pagination & Server Load Throttling (`pageSize=20`)

---

## 4. Coding & Execution Standards

- **Python Environment**: Python 3.10+, SQLite3 in-memory/WAL mode, requests/urllib session management.
- **TDD Requirement**: All new parsers, query engines, and API connectors must have automated verification tests (e.g. `test_queries.py`).
- **Security & Scoping**: Never hardcode credentials; enforce Principle of Least Privilege across workshop accounts.
