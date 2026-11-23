# ADR-0003: Role Scoping & Storekeeper Least Privilege Enforcement

## Status
**Accepted**

## Context
Automated inventory synchronization and WhatsApp bot operations require programmatic authentication with AutoRox. AutoRox accounts typically belong to one of several roles:
* `ROLE_WORKSHOPADMIN` (Full Administrator / Owner)
* `ROLE_SPARESINCHARGE` (Store Incharge / Storekeeper)
* `ROLE_SERVICEADVISOR` (Service Advisor / Estimator)
* `ROLE_TECHNICIAN` (Floor Mechanic)

Initial testing utilized Administrator credentials. However, embedding Administrator credentials in automated headless scripts poses significant risks:
1. **Excessive Privilege Exposure**: If server credentials are compromised, an Admin token grants access to financial P&L, bank balances, tax invoice deletion, employee payroll, and labor rate tampering.
2. **Audit Trail Pollution**: Every automated bot action (inwarding, stock polling, MRN creation) would be recorded under the Owner's personal user ID, making operational audits ambiguous.

## Decision
We decided to strictly enforce the **Principle of Least Privilege (PoLP)** by creating a dedicated operational bot user:
1. **User Identity**: Dedicated AutoRox user `whatomate`.
2. **Assigned Role**: **`ROLE_SPARESINCHARGE`** (Store Incharge / Storekeeper).
3. **Privilege Scope**:
   * ✅ **Allowed**: Read parts master, view stock levels (`/inventoryStockList`, `/getStockList`), perform Direct Inwards (`/directInward`), view vendors, create Purchase Orders, and issue spares to Job Cards.
   * ❌ **Forbidden**: Cannot view workshop profit/loss ledgers, edit billing labor rates, or delete finalized invoices.
4. **Audit Separation**: All automated WhatsApp inwarding and stock reconciliation transactions are immutably logged in AutoRox as `Created By: whatomate`.

## Consequences

### Positive
* **Minimal Blast Radius**: A compromised token cannot access financial statements or customer billing ledgers.
* **Crystal-Clear Auditing**: Workshop managers can easily filter automated WhatsApp transactions from manual counter entries.
* **Statutory Compliance**: Meets automotive workshop ERP compliance standards.

### Negative / Trade-offs
* If future pillars expand into vehicle job card creation or customer estimate approvals (Pillar 1), dual-role permissions (`ROLE_SPARESINCHARGE` + `ROLE_SERVICEADVISOR`) will need to be granted to the bot user.
