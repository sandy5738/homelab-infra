# Domain Glossary: WhatsApp Inventory & Bill Copilot for Auto Workshops

This glossary establishes canonical terminology for multi-brand automotive garage operations, ERP integrations, spare parts catalogs, and WhatsApp automation.

---

## 1. Core Platform & Domain Terms

**Workshop (Garage / Outlet)**:
A licensed automotive repair and servicing facility operating multiple service bays. In India, multi-brand workshops repair diverse OEM models (Hyundai, Maruti, Tata, Mahindra, Honda, etc.).
_Avoid_: store, repair shop, branch (unless referring specifically to franchise outlets).

**Multi-Tenancy**:
An architectural model where a single software instance serves multiple distinct workshops, with complete tenant data isolation (isolated catalogs, physical stock balances, purchase histories, and WhatsApp business channels).

**ERP Wedge**:
The initial beachhead product strategy: starting with deep integration for a specific Garage Management System (AutoRox), then abstracting into an ERP-agnostic middleware layer (supporting TallyPrime, Marg, Busy, Vyapar, GaragePlug, Google Sheets).

**Storekeeper (Parts Manager / Spares In-Charge)**:
The workshop personnel responsible for physical parts inventory, receiving supplier shipments, issuing parts to job cards, and maintaining warehouse order.
_Avoid_: inventory clerk, warehouse boy.

**Service Advisor (SA)**:
The customer-facing workshop executive who diagnoses vehicle complaints, prepares estimates, creates job cards, and coordinates parts allocation.

---

## 2. Parts & Inventory Terminology

**SKU (Part Number / OEM Part No)**:
The unique alphanumeric identifier assigned by an OEM (e.g. `F002H24945EHG`, `01245255084AV`) or aftermarket component maker (Bosch, TVS, Valeo, Lumax, Uno Minda).

**Part Description / Colloquial Query**:
The informal, natural-language phrasing used by mechanics and advisors to identify a component (e.g., *"Creta petrol cabin filter"*, *"Swift Dzire front brake pads"*), as opposed to strict 12-digit OEM part numbers.

**Fuzzy Part & Fitment Matching**:
The algorithmic layer that bridges natural language queries, box photos, and partial part numbers across OEM codes, aftermarket equivalents, and vehicle make/model/year compatibilities.

**Stock-on-Hand (Physical Stock)**:
The actual, count-verified quantity of a part currently physically present on workshop shelves and available for allocation.

**Bin / Shelf Coordinate**:
The 3-tier warehouse address system (`[Rack]-[Row]-[Shelf]`, e.g., `A1-R1-S3`) identifying where a part is physically stored.

**Direct Inward**:
The statutory ERP transaction whereby incoming supplier invoices are posted to the ledger, increasing physical stock quantities while establishing unit purchase rates, tax credits (ITC), and accounts payable.
_Avoid_: stock increment, manual stock adjustment, balance bump.

**MRN (Material Requisition Note / Pick List)**:
The internal digital document transferring parts from the warehouse shelves to an active vehicle Job Card for immediate mechanic fitting.

---

## 3. Financial & Accounting Terminology

**GSTIN (Goods and Services Tax Identification Number)**:
The 15-character statutory tax identifier of vendors and workshops in India.

**Input Tax Credit (ITC)**:
The GST paid by the workshop on spare parts purchases from distributors, which offsets the workshop's output GST liability when billing car owners. Preserving accurate purchase tax slabs (18% vs 28%) is mandatory for ITC compliance.

**HSN Code (Harmonized System of Nomenclature)**:
Standard 4-to-8-digit commodity code classifying automotive spare parts under Indian GST (e.g., 8708 for vehicle accessories, 4016 for rubber parts).

**Vendor Price Creep (Margin Leakage)**:
Unnoticed price increases on incoming supplier invoices compared to historical purchase rates, eroding workshop gross margins.

---

## 4. WhatsApp & Infrastructure Terminology

**WABA (WhatsApp Business Account)**:
The official Meta API entity for business messaging. Governed by Cloud API tier limits and conversation-based pricing.

**WABA Phone Number Isolation**:
Provisioning a dedicated phone number per workshop under Meta Cloud API rather than routing all workshops through a single shared number. This ensures each small workshop benefits from Meta's monthly free tier (1,000 free service replies/month) and avoids cross-tenant rate limits.

**User-Initiated Service Conversation**:
A 24-hour messaging window opened when a mechanic, advisor, or vendor messages the workshop bot. Under Meta's Oct 1, 2026 pricing, incoming messages and initial replies within the free tier cost ₹0; subsequent utility replies are billed at ₹0.115/reply.
