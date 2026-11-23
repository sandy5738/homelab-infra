# Architecture Decision Records (ADRs)

This directory documents the key architectural, technical, and operational decisions made during the design, implementation, and integration of **Pillar 2: Spare Parts & Inventory (Storekeeper & Procurement Automation)** for Upshift Automotives.

## Register of Decisions

| ADR | Title | Date | Status | Scope |
| :---: | :--- | :---: | :---: | :--- |
| [**ADR-0001**](0001-pillar2-architecture-and-infrastructure-topology.md) | Pillar 2 Microservice Architecture & Infrastructure Topology | 2026-11-20 | **Accepted** | System Topology & Hosting |
| [**ADR-0002**](0002-master-data-hybrid-storage-and-in-memory-sqlite.md) | Hybrid Master Data Engine & In-Memory SQLite Store | 2026-11-20 | **Accepted** | Data Model & Query Engine |
| [**ADR-0003**](0003-role-scoping-and-storekeeper-least-privilege.md) | Role Scoping & Storekeeper Least Privilege Enforcement | 2026-11-21 | **Accepted** | Security & Compliance |
| [**ADR-0004**](0004-core-portal-controller-integration-over-rest-gateway.md) | Direct Operational Controller Integration over Public REST Gateway | 2026-11-21 | **Accepted** | AutoRox API Integration |
| [**ADR-0005**](0005-proactive-session-caching-with-20-minute-refresh-window.md) | Proactive Session & Token Caching with 20-Minute Refresh Window | 2026-11-21 | **Accepted** | Performance & Auth Lifecycle |
| [**ADR-0006**](0006-accounting-compliant-stock-inwarding-workflow.md) | Accounting-Compliant Stock Inwarding via Direct Inward Engine | 2026-11-20 | **Accepted** | Inventory Accounting & GST |
| [**ADR-0007**](0007-query-pagination-and-server-load-throttling.md) | Safe Query Pagination & Server Load Throttling | 2026-11-21 | **Accepted** | API Resilience & Stability |
| [**ADR-0008**](0008-hybrid-go-engine-and-python-domain-architecture.md) | Hybrid Go Core Engine & Python Domain Worker Architecture | 2026-11-21 | **Accepted** | Architecture & Performance |
| [**ADR-0009**](0009-gpu-accelerated-edge-ocr-pipeline.md) | GPU-Accelerated Edge OCR Pipeline for Vendor Invoices | 2026-11-21 | **Accepted** | Edge AI & Hardware Acceleration |
