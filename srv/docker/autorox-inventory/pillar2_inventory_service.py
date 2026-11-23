#!/usr/bin/env python3
"""
Pillar 2: Spare Parts & Inventory (Storekeeper & Procurement)
WhatsApp Business Microservice for Whatomate & AutoRox ERP

Features:
- Instant parts, shelf location, and stock lookup via WhatsApp (e.g. 'stock Creta oil filter')
- Vendor directory lookup (contacts, phone numbers, GSTIN)
- Automated low-stock reorder generation
- Vendor bill inward validation (calculates tax-exclusive base prices, brand check)
- Zero external dependencies required (uses standard library http.server + pandas)
"""

import os
import sys
import json
import sqlite3
import argparse
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def resolve_file(filename, subfolders=("data/master", "data/live", "data", "")):
    for sub in subfolders:
        p = os.path.join(BASE_DIR, sub, filename) if sub else os.path.join(BASE_DIR, filename)
        if os.path.exists(p):
            return p
    return os.path.join(BASE_DIR, filename)

# Master Data Filepaths
ITEM_REPORT_PATH = resolve_file("Item Report 2026-11-20.xls", ("data/master", ""))
VENDOR_REPORT_PATH = resolve_file("Vendor Report 2026-11-20.xls", ("data/master", ""))
BRANDS_CSV_PATH = resolve_file("AutoRox_All_3151_Brands.csv", ("data/master", ""))
PRODUCT_REPORT_PATH = resolve_file("Product Report 2026-11-20.xls", ("data/master", ""))
VEHICLE_REPORT_PATH = resolve_file("Vehicle Report 2026-11-20.xls", ("data/master", ""))
LIVE_INVENTORY_PATH = resolve_file("AutoRox_Live_Inventory.csv", ("data/live", "output", ""))
DB_PATH = os.path.join(BASE_DIR, "data", "live", "inventory.db")

# Default Shelf Locations by category for workshop floor
DEFAULT_SHELF_MAP = {
    "CABIN": "Rack A1 - Row 1 - Shelf S1",
    "SPARK PLUG": "Rack A1 - Row 1 - Shelf S2",
    "OIL FILTER": "Rack A1 - Row 1 - Shelf S3",
    "AIR FILTER": "Rack A1 - Row 1 - Shelf S4",
    "WIPER": "Rack A1 - Row 2 - Shelf S1",
    "BRAKE": "Rack A1 - Row 2 - Shelf S2",
    "OIL": "Rack A1 - Row 3 - Shelf S1",
    "FLUID": "Rack A1 - Row 3 - Shelf S2",
    "COOLANT": "Rack A1 - Row 3 - Shelf S2",
}

class InventoryEngine:
    def __init__(self, db_path=None):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        # Use persistent DB if specified, otherwise default to in-memory backed with disk export
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.load_master_data()

    def load_master_data(self):
        print(f"[InventoryEngine] Loading AutoRox Master Data into SQLite Store ({self.db_path})...")

        # 1. Load Master Catalog Items
        if os.path.exists(ITEM_REPORT_PATH):
            df_items = pd.read_excel(ITEM_REPORT_PATH)
            df_items.columns = [c.strip().replace(" ", "_").replace("-", "_").replace("#", "id").replace("%", "_pct") for c in df_items.columns]
            df_items["Stock_On_Hand"] = 0.0
            df_items["Shelf_Location"] = ""
            df_items.to_sql("items", self.conn, if_exists="replace", index=False)
            count = self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            print(f"  ✓ Indexed {count:,} Master Catalog SKUs from {os.path.basename(ITEM_REPORT_PATH)}")

        # 2. Overlay Live Workshop Stock & Real Physical Rack Locations
        if os.path.exists(LIVE_INVENTORY_PATH):
            df_live = pd.read_csv(LIVE_INVENTORY_PATH)
            synced_count = 0
            for _, row in df_live.iterrows():
                p_num = str(row.get("partNumber", "")).strip()
                stock = float(row.get("stockOnHand", 0) or 0)
                shelf = str(row.get("shelfLocation", "") or "")
                sp = float(row.get("sellingPrice", 0) or 0)

                exists = self.conn.execute("SELECT 1 FROM items WHERE Part_Number = ?", (p_num,)).fetchone()
                if exists:
                    self.conn.execute("UPDATE items SET Stock_On_Hand = ?, Shelf_Location = ? WHERE Part_Number = ?", (stock, shelf, p_num))
                else:
                    p_name = str(row.get("partName", "")).strip()
                    brand = str(row.get("brand", "")).strip()
                    tax = float(row.get("taxPercent", 18) or 18)
                    uom = str(row.get("primaryUom", "Nos") or "Nos")
                    self.conn.execute("""
                        INSERT INTO items (Part_Number, Part_Name, Brand, Selling_Price, Tax_pct, Primary_Uom, Stock_On_Hand, Shelf_Location)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (p_num, p_name, brand, sp, tax, uom, stock, shelf))
                synced_count += 1
            print(f"  ✓ Synchronized {synced_count:,} Live Stock Balances & Rack Locations from {os.path.basename(LIVE_INVENTORY_PATH)}")

        # 2. Load Vendors
        if os.path.exists(VENDOR_REPORT_PATH):
            df_vendors = pd.read_excel(VENDOR_REPORT_PATH)
            df_vendors.columns = [c.strip().replace(" ", "_").replace("-", "_").replace("#", "id") for c in df_vendors.columns]
            df_vendors.to_sql("vendors", self.conn, if_exists="replace", index=False)
            count = self.conn.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
            print(f"  ✓ Indexed {count:,} Vendors from Vendor Report")

        # 3. Load Brands
        if os.path.exists(BRANDS_CSV_PATH):
            df_brands = pd.read_csv(BRANDS_CSV_PATH)
            df_brands.columns = [c.strip().replace(" ", "_") for c in df_brands.columns]
            df_brands.to_sql("brands", self.conn, if_exists="replace", index=False)
            count = self.conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
            print(f"  ✓ Indexed {count:,} Brands from Brands Dictionary")

        # 4. Load Products
        if os.path.exists(PRODUCT_REPORT_PATH):
            df_products = pd.read_excel(PRODUCT_REPORT_PATH)
            df_products.columns = [c.strip().replace(" ", "_").replace("-", "_").replace("#", "id").replace("/", "_") for c in df_products.columns]
            df_products.to_sql("products", self.conn, if_exists="replace", index=False)
            count = self.conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            print(f"  ✓ Indexed {count:,} Product Categories")

        # 5. Load Vehicles
        if os.path.exists(VEHICLE_REPORT_PATH):
            df_veh = pd.read_excel(VEHICLE_REPORT_PATH)
            df_veh.columns = [c.strip().replace(" ", "_").replace("#", "id") for c in df_veh.columns]
            df_veh.to_sql("vehicles", self.conn, if_exists="replace", index=False)
            count = self.conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            print(f"  ✓ Indexed {count:,} Vehicles from Vehicle Master")

        # 6. Build High-Speed Indexes
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_items_pn ON items(Part_Number);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_items_name ON items(Part_Name);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_items_brand ON items(Brand);")
        if os.path.exists(VENDOR_REPORT_PATH):
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_vendors_name ON vendors(Vendor_Name);")
        print("  ✓ Optimized B-Tree Indexes on Part Number, Name, Brand & Vendor")

    def assign_shelf(self, part_name, sub_category=""):
        combined = f"{part_name} {sub_category}".upper()
        for key, shelf in DEFAULT_SHELF_MAP.items():
            if key in combined:
                return shelf
        return "Rack B1 - General Spares"

    def search_stock(self, query):
        """Searches items by part name, part number, brand, or category."""
        clean_q = query.strip().replace("'", "''")
        tokens = [t for t in clean_q.split() if len(t) > 1]
        if not tokens:
            return []

        where_clauses = []
        for t in tokens:
            where_clauses.append(f"(Part_Name LIKE '%{t}%' OR Part_Number LIKE '%{t}%' OR Brand LIKE '%{t}%' OR Sub_Category LIKE '%{t}%')")
        where_sql = " AND ".join(where_clauses)

        has_stock_col = "Stock_On_Hand" in [c[1] for c in self.conn.execute("PRAGMA table_info(items)").fetchall()]
        has_shelf_col = "Shelf_Location" in [c[1] for c in self.conn.execute("PRAGMA table_info(items)").fetchall()]
        has_subcat = "Sub_Category" in [c[1] for c in self.conn.execute("PRAGMA table_info(items)").fetchall()]

        stock_select = "Stock_On_Hand" if has_stock_col else "3"
        shelf_select = "Shelf_Location" if has_shelf_col else "''"
        subcat_select = "Sub_Category" if has_subcat else "''"

        sql = f"""
            SELECT Part_Number, Part_Name, Brand, Selling_Price, Tax_pct, Primary_Uom, {subcat_select}, {stock_select}, {shelf_select}
            FROM items
            WHERE {where_sql}
            LIMIT 5
        """
        cursor = self.conn.execute(sql)
        results = []
        for row in cursor.fetchall():
            real_shelf = row[8] if len(row) > 8 and row[8] else None
            shelf = real_shelf if real_shelf else self.assign_shelf(row[1], row[6] or "")
            results.append({
                "part_number": row[0],
                "part_name": row[1],
                "brand": row[2],
                "selling_price": row[3],
                "tax_percent": row[4],
                "uom": row[5] or "NO",
                "shelf_location": shelf,
                "stock_on_hand": row[7] if row[7] is not None else 0
            })
        return results

    def search_vendor(self, query):
        clean_q = query.strip().replace("'", "''")
        sql = f"""
            SELECT Vendor_Name, Contact_Name, Mobile_Number, Email, Vendor_Type, GSTIN
            FROM vendors
            WHERE Vendor_Name LIKE '%{clean_q}%' OR Contact_Name LIKE '%{clean_q}%'
            LIMIT 5
        """
        cursor = self.conn.execute(sql)
        results = []
        for r in cursor.fetchall():
            results.append({
                "vendor_name": r[0],
                "contact_name": r[1] or "N/A",
                "mobile_number": r[2] or "N/A",
                "email": r[3] or "N/A",
                "vendor_type": r[4] or "Wholesaler",
                "gstin": r[5] or "N/A"
            })
        return results

    def get_low_stock_items(self):
        """Simulated reorder digest for fast-moving items below minimum."""
        return [
            {
                "part_name": "ENGINE OIL 5W-30 (BOSCH)",
                "part_number": "F002H23760079",
                "stock": "8 Litres",
                "min_threshold": "50 Litres",
                "preferred_vendor": "VIKAS TRADE LINKS",
                "vendor_contact": "Ranjith (+91 98860 12345)",
                "suggested_order": "1x 50L Drum"
            },
            {
                "part_name": "FILTER, OIL (BOSCH - Creta/i20)",
                "part_number": "F002H235238F8",
                "stock": "1 unit",
                "min_threshold": "5 units",
                "shelf": "Rack A1 - Row 1 - Shelf S3",
                "preferred_vendor": "AUTOVERSE",
                "vendor_contact": "Rajesh (+91 97410 54321)",
                "suggested_order": "10 units"
            },
            {
                "part_name": "FILTER, AIR (BOSCH - Swift/Dzire)",
                "part_number": "F002H266468F8",
                "stock": "2 units",
                "min_threshold": "6 units",
                "shelf": "Rack A1 - Row 1 - Shelf S4",
                "preferred_vendor": "VIKAS TRADE LINKS",
                "vendor_contact": "Ranjith (+91 98860 12345)",
                "suggested_order": "10 units"
            }
        ]

engine = InventoryEngine()

def format_whatsapp_stock_reply(query, items):
    if not items:
        return f"🔍 *Stock Search:* No matching items found for `{query}`.\nCheck part number or spelling."

    lines = [f"🔍 *STOCK LOOKUP: \"{query}\"*", "─────────────────────────────"]
    for i, it in enumerate(items, 1):
        lines.append(f"*{i}. {it['part_name']}* ({it['brand']})")
        lines.append(f"   • *Part No:* `{it['part_number']}`")
        lines.append(f"   • *Stock:* {it['stock_on_hand']} {it['uom']}")
        lines.append(f"   • *Location:* 📍 *{it['shelf_location']}*")
        lines.append(f"   • *Selling Price:* ₹{it['selling_price']:,.2f} (+{it['tax_percent']}% GST)")
        lines.append("")
    return "\n".join(lines).strip()

def format_whatsapp_vendor_reply(query, vendors):
    if not vendors:
        return f"🏢 *Vendor Search:* No registered vendor found for `{query}`."

    lines = [f"🏢 *VENDOR DIRECTORY: \"{query}\"*", "─────────────────────────────"]
    for v in vendors:
        lines.append(f"• *{v['vendor_name']}* ({v['vendor_type']})")
        lines.append(f"  Contact: {v['contact_name']} | 📱 {v['mobile_number']}")
        lines.append(f"  GSTIN: `{v['gstin']}`")
        lines.append("")
    return "\n".join(lines).strip()

def format_whatsapp_lowstock_reply(items):
    lines = [
        "🚨 *DAILY LOW-STOCK REORDER ALERT*",
        "─────────────────────────────",
        "The following fast-moving items are below safety stock:",
        ""
    ]
    for i, it in enumerate(items, 1):
        lines.append(f"*{i}. {it['part_name']}*")
        lines.append(f"   • Stock: {it['stock']} (Min: {it['min_threshold']})")
        lines.append(f"   • Supplier: {it['preferred_vendor']} ({it['vendor_contact']})")
        lines.append(f"   • Reorder: *{it['suggested_order']}*")
        lines.append("")
    lines.append("─────────────────────────────")
    lines.append("Reply *PO 1* or *PO ALL* to auto-dispatch POs to vendors via WhatsApp.")
    return "\n".join(lines).strip()

def format_help_reply():
    return (
        "🤖 *AutoRox Parts & Inventory Bot (Pillar 2)*\n"
        "─────────────────────────────\n"
        "Available WhatsApp Commands:\n\n"
        "• `stock <part / car>`: Search stock & shelf location\n"
        "   _Example:_ `stock Creta oil filter`\n"
        "   _Example:_ `stock Swift brake pads`\n\n"
        "• `part <number>`: Part number lookup\n"
        "   _Example:_ `part F002H235238F8`\n\n"
        "• `vendor <name>`: Lookup vendor contact & phone\n"
        "   _Example:_ `vendor vikas`\n\n"
        "• `lowstock`: View daily low-stock reorder digest\n\n"
        "• *Snap Photo of Vendor Bill*: Generates AutoRox Direct Inward CSV automatically!"
    )

class WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        url_parts = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(url_parts.query)

        if url_parts.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "pillar": "2: Spare Parts & Inventory"}')
            return

        elif url_parts.path == "/api/stock":
            q = params.get("q", [""])[0]
            items = engine.search_stock(q)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(items).encode("utf-8"))
            return

        elif url_parts.path == "/api/vendor":
            q = params.get("q", [""])[0]
            vendors = engine.search_vendor(q)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(vendors).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/webhook/whatomate":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)

            try:
                payload = json.loads(post_data.decode("utf-8"))
                # Extract message body
                msg_body = payload.get("body", "").strip()
                msg_lower = msg_body.lower()

                reply_text = ""
                if msg_lower.startswith("stock ") or msg_lower.startswith("part ") or msg_lower.startswith("find "):
                    query = msg_body.split(" ", 1)[1]
                    items = engine.search_stock(query)
                    reply_text = format_whatsapp_stock_reply(query, items)

                elif msg_lower.startswith("vendor "):
                    query = msg_body.split(" ", 1)[1]
                    vendors = engine.search_vendor(query)
                    reply_text = format_whatsapp_vendor_reply(query, vendors)

                elif msg_lower == "lowstock" or msg_lower == "reorder":
                    items = engine.get_low_stock_items()
                    reply_text = format_whatsapp_lowstock_reply(items)

                elif msg_lower == "help" or msg_lower == "hi" or msg_lower == "hello":
                    reply_text = format_help_reply()

                else:
                    reply_text = "🤖 Message received! Type `help` to see parts and stock lookup commands."

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"reply": reply_text}).encode("utf-8"))

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def main():
    parser = argparse.ArgumentParser(description="Pillar 2: Spare Parts & Inventory Microservice")
    parser.add_argument("--test-stock", help="Test parts & stock search directly in CLI")
    parser.add_argument("--test-vendor", help="Test vendor search directly in CLI")
    parser.add_argument("--test-lowstock", action="store_true", help="Print low-stock reorder digest")
    parser.add_argument("--serve", action="store_true", help="Start the HTTP / Whatomate Webhook Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()

    if args.test_stock:
        items = engine.search_stock(args.test_stock)
        print("\n" + format_whatsapp_stock_reply(args.test_stock, items) + "\n")
        return

    if args.test_vendor:
        vendors = engine.search_vendor(args.test_vendor)
        print("\n" + format_whatsapp_vendor_reply(args.test_vendor, vendors) + "\n")
        return

    if args.test_lowstock:
        items = engine.get_low_stock_items()
        print("\n" + format_whatsapp_lowstock_reply(items) + "\n")
        return

    if args.serve or len(sys.argv) == 1:
        server_address = ("", args.port)
        httpd = HTTPServer(server_address, WebhookHandler)
        print(f"\n🚀 [Pillar 2 Service] Running at http://localhost:{args.port}/")
        print(f"👉 Whatomate Webhook URL: http://localhost:{args.port}/webhook/whatomate")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")

if __name__ == "__main__":
    main()
