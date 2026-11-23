# ADR-0002: Hybrid Master Data Engine & In-Memory SQLite Store

## Status
**Accepted**

## Context
AutoRox stores tens of thousands of master records across distinct domains:
* **Item Report**: 1,938 SKUs with descriptions, part numbers, brands, tax percentages, and selling prices.
* **Vendor Report**: 31 automotive suppliers, authorized brand distributors, and GST numbers.
* **Brands Dictionary**: 3,151 vehicle and aftermarket spare parts brands.
* **Product Catalog**: 400 standardized automotive product categories.
* **Vehicle Master**: 6,915 Indian vehicle models, sub-models, and engine variants.

Mechanics on the workshop floor send informal queries with varying typos and syntax (e.g. `stock Creta oil filter`, `vikas vendor`, `wiper 3397011650END`). Querying AutoRox's remote cloud backend synchronously for every WhatsApp message introduces a 5–15 second round-trip latency, risk of HTTP timeouts, and frequent failures if the AutoRox portal is under peak load.

## Decision
We implemented a **Hybrid Master Data Engine (`InventoryEngine`)** utilizing Python standard `sqlite3` in `:memory:` with local persistence:

1. **Master Catalog Base Load**:
   On microservice boot, the engine indexes the official AutoRox master reports (`Item Report.xls`, `Vendor Report.xls`, `AutoRox_All_3151_Brands.csv`, `Product Report.xls`, `Vehicle Report.xls`).
2. **Live Stock & Physical Shelf Overlay**:
   When [AutoRox_Live_Inventory.csv](file:///Users/sandeephm/Downloads/autorox-whatsapp-spare-parts-and-inventory/output/AutoRox_Live_Inventory.csv) is synchronized from AutoRox's core controller:
   * Existing SKUs have their `Stock_On_Hand` (`QoH`) and real physical shelf tags (`rack`, e.g. `A1-R2-S2`) updated in-memory.
   * New SKUs not present in historical item reports are inserted dynamically.
   * Items not currently inwarded default to `Stock_On_Hand = 0.0`.
3. **Tokenized Multi-Column Fuzzy Search**:
   Queries are sanitized and split into token sets, filtering across `Part_Name`, `Part_Number`, `Brand`, and `Sub_Category` concurrently (`AND` matched) with sub-millisecond execution.
4. **Automated Shelf Fallback Map**:
   If an item does not yet have a physical inward shelf tag (`rack`), the system falls back to a deterministic category-to-shelf dictionary (e.g. `OIL FILTER` $\rightarrow$ `Rack A1 - Row 1 - Shelf S3`).

## Consequences

### Positive
* **Sub-Millisecond Query Speed**: SQLite `:memory:` searches execute in < 2ms for 1,938 SKUs.
* **Complete Resilience**: WhatsApp bot remains 100% operational even if AutoRox cloud is down or under maintenance.
* **Real Physical Accuracy**: Responses display the exact physical shelf tag (`A1-R2-S2`) recorded during inwarding.
* **Comprehensive Coverage**: Retains full visibility of all 1,938 catalog parts even if only 89 currently have positive stock on shelves.

### Negative / Trade-offs
* In-memory database must be refreshed when the microservice restarts (takes ~0.4s during boot).
* Requires periodic synchronization from AutoRox via `sync_inventory.py` to maintain live stock accuracy.
