# Whatomate Setup, Flows & Hands-On Testing Guide

This guide walks through configuring [Whatomate](https://github.com/shridarpatil/whatomate) (WhatsApp Business Gateway) to interface with the **AutoRox Go Copilot Engine**, including webhook wiring, interactive flow testing, and WhatsApp template definitions.

---

## 1. Whatomate Webhook Configuration

### Step 1: Open Whatomate Dashboard
1. Log into your Whatomate instance running on your server (default: `http://localhost:8090` or your Tailscale domain).
2. Navigate to **Settings** $\rightarrow$ **Webhooks** (or **Developer** $\rightarrow$ **Webhooks**).

### Step 2: Add Webhook Endpoint
- **Name:** `AutoRox Inventory Copilot`
- **Webhook URL:**
  - *If Whatomate and Engine are in same Docker Compose:* `http://autorox-engine:8000/webhook/whatomate`
  - *If Whatomate runs directly on host/separate container:* `http://host.docker.internal:8000/webhook/whatomate` (or `http://localhost:8000/webhook/whatomate`)
- **HTTP Method:** `POST`
- **Event Subscriptions:** Select `message.create` (or `messages.upsert` / `incoming_message`)
- **Status:** Enabled / Active

---

## 2. Interactive WhatsApp Flows to Test

Once the webhook is connected, open WhatsApp on your phone and send messages to your connected Whatomate workshop number:

### Flow 1: Floor Mechanic Stock & Shelf Lookup
* **User Input:**
  ```text
  stock Creta oil filter
  ```
  *(or `stock Swift brake pads`, `stock Innova cabin filter`)*
* **Expected WhatsApp Bot Reply:**
  ```text
  🔍 *STOCK LOOKUP: "Creta oil filter"*
  ─────────────────────────────
  *1. OIL FILTER* (BOSCH)
     • *Part No:* `F002H234678F8`
     • *Stock:* 5.0 Nos
     • *Location:* 📍 *A1-R1-S3*
     • *Selling Price:* ₹257.63 (+18.0% GST)

  *2. OIL FILTER* (PUROLATOR)
     • *Part No:* `PI-449500`
     • *Stock:* 5.0 Nos
     • *Location:* 📍 *A1-R1-S3*
     • *Selling Price:* ₹131.36 (+18.0% GST)

  *3. OIL FILTER* (BOSCH)
     • *Part No:* `F002H235238F8`
     • *Stock:* 4.0 Nos
     • *Location:* 📍 *A1-R1-S3*
     • *Selling Price:* ₹144.07 (+18.0% GST)
  ```

---

### Flow 2: Storekeeper Exact Part Number Lookup
* **User Input:**
  ```text
  part F002H234678F8
  ```
* **Expected WhatsApp Bot Reply:**
  ```text
  🔍 *STOCK LOOKUP: "F002H234678F8"*
  ─────────────────────────────
  *1. OIL FILTER* (BOSCH)
     • *Part No:* `F002H234678F8`
     • *Stock:* 5.0 Nos
     • *Location:* 📍 *A1-R1-S3*
     • *Selling Price:* ₹257.63 (+18.0% GST)
  ```

---

### Flow 3: Vendor Directory & Contact Lookup
* **User Input:**
  ```text
  vendor vikas
  ```
* **Expected WhatsApp Bot Reply:**
  ```text
  🏢 *VENDOR DIRECTORY: "vikas"*
  ─────────────────────────────
  • *VIKAS TRADE LINKS * (OES / Brand Distributor )
    Contact: ranjith  | 📱 9513337752
    GSTIN: `N/A`
  ```

---

### Flow 4: Daily 9:00 AM Low-Stock Reorder Digest
* **User Input:**
  ```text
  lowstock
  ```
  *(or `reorder`)*
* **Expected WhatsApp Bot Reply:**
  ```text
  🚨 *DAILY LOW-STOCK REORDER ALERT*
  ─────────────────────────────
  The following fast-moving items are below safety stock:

  *1. ENGINE OIL 5W-30 (BOSCH)*
     • Stock: 8 Litres (Min: 50 Litres)
     • Supplier: VIKAS TRADE LINKS (Ranjith (+91 95133 37752))
     • Reorder: *1x 50L Drum*

  *2. FILTER, OIL (BOSCH - Creta/i20)*
     • Stock: 1 unit (Min: 5 units)
     • Supplier: AUTOVERSE (Rajesh (+91 97410 54321))
     • Reorder: *10 units*

  *3. FILTER, AIR (BOSCH - Swift/Dzire)*
     • Stock: 2 units (Min: 6 units)
     • Supplier: VIKAS TRADE LINKS (Ranjith (+91 95133 37752))
     • Reorder: *10 units*

  ─────────────────────────────
  Reply *PO 1* or *PO ALL* to auto-dispatch POs to vendors via WhatsApp.
  ```

---

### Flow 5: Snap Photo of Vendor Invoice (PP-OCRv6 GPU Acceleration)
* **User Input:** Storekeeper sends a smartphone photo or PDF of a supplier invoice from *Vikas Trade Links* or *Bosch*.
* **Under the Hood:**
  1. Whatomate fires webhook with `image` / `media_url` to the Go Engine (`:8000`).
  2. Go Engine dispatches the image to `http://autorox-ocr:8005/api/ocr/extract`.
  3. `autorox-ocr` processes the bill on the **NVIDIA GTX 1050 Mobile** using **PP-OCRv6** with angle correction (~150ms).
  4. Cross-references line items against 1,938 AutoRox SKUs and flags margin leakage.
* **Expected WhatsApp Bot Reply:**
  ```text
  🧾 *PP-OCRv6 INVOICE PARSED: VIKAS TRADE LINKS*
  ─────────────────────────────
  • *Invoice No:* `INV-2026-9912`
  • *GSTIN:* `29AABCV1234F1Z5`
  • *Date:* 2026-11-21
  • *Parts Extracted:* 3 (OCR Time: 148.5ms on NVIDIA GeForce GTX 1050 Mobile)

  📋 *Verified Line Items:*
  ✅ *1. OIL-FILTER ELEMENT*
     • *Part No:* `F002H234678F8` | *Qty:* 10
     • *Buy Rate:* ₹215.00 (+18% GST)
     • *Shelf:* 📍 *A1-R1-S3*

  ✅ *2. AIR-FILTER INSERT*
     • *Part No:* `F002H24945EHG` | *Qty:* 5
     • *Buy Rate:* ₹340.00 (+18% GST)
     • *Shelf:* 📍 *A1-R1-S4*

  ─────────────────────────────
  🚨 *MARGIN LEAKAGE & PRICE HIKE ALERTS:*
  ⚠️ Low Margin Alert on `F002H234678F8`: Buying at ₹215.00, Selling at ₹257.63 (Margin: 16.5%)

  ─────────────────────────────
  Reply *INWARD YES* to auto-post this bill to AutoRox Direct Inward!
  ```

---

## 3. Whatomate Broadcast / Notification Templates

To send automated outbound notifications (e.g. morning 9:00 AM alerts or purchase orders to distributors), configure these pre-approved WhatsApp templates in Whatomate:

### Template 1: `daily_low_stock_digest` (Utility Category)
* **Template Name:** `daily_low_stock_digest`
* **Language:** `en_US`
* **Category:** `UTILITY`
* **Body:**
  ```text
  🚨 *Daily Workshop Inventory Alert - {{1}}*

  The following fast-moving parts are running low:
  {{2}}

  Reply *PO ALL* to auto-generate vendor purchase orders.
  ```
* **Sample Variables:**
  - `{{1}}`: `Upshift Automotives`
  - `{{2}}`: `1. Bosch 5W-30 Oil (8L remaining)\n2. Creta Oil Filters (1 pc remaining)`

---

### Template 2: `vendor_purchase_order_dispatch` (Utility Category)
* **Template Name:** `vendor_po_dispatch`
* **Language:** `en_US`
* **Category:** `UTILITY`
* **Body:**
  ```text
  📦 *New Purchase Order from {{1}}*
  PO Number: *{{2}}*

  Dear {{3}}, please dispatch the following items:
  {{4}}

  Delivery Location: {{5}}
  Please confirm dispatch date and invoice copy.
  ```
* **Sample Variables:**
  - `{{1}}`: `Upshift Automotives`
  - `{{2}}`: `PO-2026-1121-01`
  - `{{3}}`: `Vikas Trade Links`
  - `{{4}}`: `1x 50L Drum Bosch 5W-30 Engine Oil\n10x Bosch Oil Filter (F002H234678F8)`
  - `{{5}}`: `Upshift Workshop Bay 1, HSR Layout, Bengaluru`

---

## 4. Local CLI Simulation & Health Verification

You can simulate Whatomate webhooks from your terminal without opening WhatsApp:

### Test 1: Verify Engine Health
```bash
curl -s http://localhost:8000/health | jq .
```
Expected output:
```json
{
  "engine": "go-autorox-copilot",
  "status": "ok",
  "uptime": "healthy",
  "version": "1.0.0"
}
```

### Test 2: Simulate Whatomate Webhook Event
```bash
curl -s -X POST http://localhost:8000/webhook/whatomate \
  -H "Content-Type: application/json" \
  -d '{"body": "stock Creta oil filter", "sender": "+919886012345"}' | jq .
```

### Test 3: Test Direct Stock Query API
```bash
curl -s "http://localhost:8000/api/stock?q=brake" | jq .
```
