# Domain Docs

How agents should consume this repository's domain documentation when exploring or implementing features.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root: Defines canonical automotive, inventory, ERP, and WhatsApp terminology.
- **`docs/adr/`**: Read ADRs that touch the area you are working on:
  - `0001`: Microservice architecture & topology (`enma`, Whatomate, Tailscale Funnel)
  - `0002`: Master data hybrid storage & in-memory SQLite
  - `0003`: Role scoping & storekeeper least privilege (`ROLE_SPARESINCHARGE`)
  - `0004`: Core portal controller integration (`POST /workShopInventory/getStockList`)
  - `0005`: Proactive session & token caching (20-minute threshold)
  - `0006`: Accounting-compliant stock inwarding (`/inventoryPage/directInward`)
  - `0007`: Safe query pagination (`pageSize=20`, 35s timeout)

## Vocabulary Rules

When naming a domain concept (in API design, SQL schema, ticket titles, or bot replies), use the exact canonical term defined in `GLOSSARY.md`. Avoid synonyms that create confusion (e.g. use `Part Number` or `SKU`, not `Item Code`; use `Direct Inward`, not `Stock Increment`).

## ADR Compliance

If an implementation or proposal contradicts an existing ADR, explicitly surface the conflict rather than silently overriding it.
