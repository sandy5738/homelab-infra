# ADR-0004: Direct Operational Controller Integration over Public REST Gateway

## Status
**Accepted**

## Context
AutoRox's system architecture is partitioned across two main cloud services:
1. **Master Data Microservice**: `https://app.autorox.co/masters/api/v1/workshop/{workshop_token}/...`
2. **Core Operational ERP Portal**: `https://bcsin.autorox.co/`

During initial API discovery, attempts to fetch stock items via `https://app.autorox.co/masters/api/v1/workshop/{workshop_token}/items` failed with **`HTTP 401 Unauthorized`**.

Investigation revealed:
* `app.autorox.co/masters/api` is exclusively scoped to static global master definitions (`/brands`, `/vehicles`, `/products`), requiring proprietary OAuth2 tokens.
* Live inventory, batch records, physical shelf allocations, and inwarded stock balances are NOT served by `app.autorox.co`. They are managed exclusively by the core Spring Security web application at **`bcsin.autorox.co`**.

## Decision
We abandoned the public master REST gateway (`app.autorox.co`) for inventory queries and integrated directly with AutoRox's core operational inventory controller:

* **Endpoint**: `POST https://bcsin.autorox.co/workShopInventory/getStockList`
* **Authentication**: Multi-tier authentication consisting of:
  1. Authenticated session cookies (`JSESSIONID`, `AWSALB`, `AWSALBCORS`).
  2. The HS512 JWT Bearer token passed in the `Authorization: Bearer <JWT>` header.
  3. `X-Requested-With: XMLHttpRequest` header.
* **Payload**:
  ```json
  {
    "workshopId": "<encryptedWorkShopId>",
    "pageSize": "20",
    "pageNo": "1",
    "search": "",
    "isFranchisor": "",
    "workshopIds": []
  }
  ```
* **Credential Discovery**: The script navigates to `https://bcsin.autorox.co/inventoryPage/inventoryStockList` to automatically extract the hidden `<input id="encryptedWorkShopId" value="...">` and page token.

## Consequences

### Positive
* **Authentic Live Data**: Accesses real workshop stock (`QoH`), total stock valuation, ageing, and exact physical rack locations (`rack`, e.g. `A1-R2-S2`).
* **Session Consistency**: Uses the same Spring Security session established during user login.
* **Elimination of 401 Errors**: Bypasses the unsupported `masters/api/items` endpoint.

### Negative / Trade-offs
* Endpoint requires session cookies and JWT simultaneously.
* Requires automated extraction of the encrypted workshop ID from the portal HTML.
