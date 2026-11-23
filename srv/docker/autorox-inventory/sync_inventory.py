#!/usr/bin/env python3
"""
AutoRox Live Inventory Sync & Intelligent Session Caching Tool
=============================================================
Automates authentication with AutoRox (Storekeeper or Admin credentials),
caches the active session, JWT, and encrypted workshop credentials to avoid
unnecessary login calls, and fetches live stock inventory from AutoRox's
core controller: `POST https://bcsin.autorox.co/workShopInventory/getStockList`.

Token Expiry & Smart Caching:
  - AutoRox tokens are valid for ~4 hours.
  - The script checks the JWT's `exp` timestamp.
  - If more than 20 minutes of validity remain, the cached session is reused
    instantly (~0.3s) without making any login or auth calls.
  - When fewer than 20 minutes remain (or if a 401 is encountered), it
    automatically executes a fresh login and updates the session cache.

Outputs:
  - Live CSV: output/AutoRox_Live_Inventory.csv
  - Raw JSON: output/AutoRox_Live_Inventory.json
  - SQLite:   output/inventory.db (when --update-db is passed)
  - Cache:    output/.autorox_session.json

Usage:
  1. Standard run (reuses cache if valid > 20 mins):
     python3 autorox_sync_inventory.py -u "whatomate" -p "YourPassword" --update-db

  2. Force immediate re-authentication:
     python3 autorox_sync_inventory.py -u "whatomate" -p "YourPassword" --force-login
"""

import os
import sys
import re
import time
import json
import csv
import ssl
import base64
import getpass
import argparse
import urllib.request
import urllib.parse
from datetime import datetime

# URLs
BASE_BCS_URL = "https://bcsin.autorox.co"
LOGIN_URL = f"{BASE_BCS_URL}/login"
STOCK_PAGE_URL = f"{BASE_BCS_URL}/inventoryPage/inventoryStockList"
STOCK_API_URL = f"{BASE_BCS_URL}/workShopInventory/getStockList"

# Minimum validity threshold (20 minutes in seconds)
EXPIRY_BUFFER_SECONDS = 20 * 60

# Setup SSL context (bypasses local intermediate chain validation issues)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


class AutoRoxClient:
    def __init__(self, username, password, cache_file=None):
        self.username = username.strip()
        self.password = password.strip()
        self.cache_file = cache_file
        self.cookies = {}
        self.cookie_str = ""
        self.jwt_token = None
        self.encrypted_workshop_id = None
        self.page_id = None
        self.workshop_id = None
        self.exp_ts = None
        self.token_expiry = None
        self.role = None

    def _update_cookies_from_response(self, resp):
        # resp.headers can be HTTPMessage
        set_cookies = resp.headers.get_all('Set-Cookie', []) if hasattr(resp.headers, 'get_all') else resp.headers.getheaders('Set-Cookie')
        for header_val in set_cookies:
            cookie_part = header_val.split(';')[0].strip()
            if '=' in cookie_part:
                k, v = cookie_part.split('=', 1)
                self.cookies[k.strip()] = v.strip()
        if self.cookies:
            self.cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def _request(self, url, data=None, headers=None, method=None, timeout=35):
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:160.0) Gecko/20100101 Firefox/160.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self.cookie_str:
            req_headers["Cookie"] = self.cookie_str
        if headers:
            req_headers.update(headers)

        if data and isinstance(data, dict):
            if "application/json" in req_headers.get("Content-Type", ""):
                encoded_data = json.dumps(data).encode("utf-8")
            else:
                encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        elif data and isinstance(data, str):
            encoded_data = data.encode("utf-8")
        else:
            encoded_data = data

        req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method=method)
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        self._update_cookies_from_response(resp)
        return resp

    def ensure_authenticated(self, force=False):
        """
        Reuses cached session if valid with at least 20 minutes remaining before expiry.
        Only contacts AutoRox auth endpoints when near expiry or cache is missing.
        """
        if not force and self.cache_file and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)

                cached_user = cache.get("username", "")
                cached_exp = int(cache.get("exp", 0))
                now_ts = int(time.time())
                remaining_secs = cached_exp - now_ts

                if cached_user.lower() == self.username.lower() and remaining_secs > EXPIRY_BUFFER_SECONDS:
                    remaining_mins = remaining_secs // 60
                    expiry_str = cache.get("token_expiry") or datetime.fromtimestamp(cached_exp).strftime('%Y-%m-%d %H:%M:%S')

                    print(f"\n⚡ [Cached Session Active]")
                    print(f"  ✓ Token valid for another {remaining_mins} minutes (expires: {expiry_str})")
                    print(f"  ✓ Remaining validity > 20 min threshold — skipping login API calls.")

                    self.jwt_token = cache.get("jwt_token")
                    self.encrypted_workshop_id = cache.get("encrypted_workshop_id")
                    self.page_id = cache.get("page_id")
                    self.workshop_id = cache.get("workshop_id")
                    self.exp_ts = cached_exp
                    self.token_expiry = expiry_str
                    self.role = cache.get("role")
                    self.cookie_str = cache.get("cookie_str", "")
                    cached_cookies = cache.get("cookies", {})
                    if isinstance(cached_cookies, dict):
                        self.cookies = cached_cookies
                    elif isinstance(cached_cookies, list):
                        self.cookies = {c["name"]: c["value"] for c in cached_cookies if isinstance(c, dict) and "name" in c and "value" in c}
                    else:
                        self.cookies = {}

                    print(f"  ✓ Session restored for '{self.username}' ({self.role or 'Active Role'})")
                    return
                else:
                    if 0 < remaining_secs <= EXPIRY_BUFFER_SECONDS:
                        print(f"\n⏳ [Session Near Expiry] Token has only {remaining_secs // 60}m remaining (< 20m threshold). Refreshing now...")
                    else:
                        print("\n⌛ [Session Expired] Cached token expired. Performing fresh login...")
            except Exception as e:
                print(f"⚠️ Cache read error: {e}. Performing fresh login...")

        # If cache invalid, missing, or near expiry:
        self.login()
        self._save_session_cache()

    def login(self):
        print(f"\n🔐 [1/3] Connecting to AutoRox Portal ({BASE_BCS_URL})...")
        try:
            resp = self._request(BASE_BCS_URL)
            html = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to AutoRox login page: {e}")

        # Extract CSRF token
        csrf_match = re.search(r'name=[\'\"]csrf_token[\'\"]\s+value=[\'\"]([^\'\"]+)[\'\"]', html)
        if not csrf_match:
            csrf_match = re.search(r'value=[\'\"]([^\'\"]+)[\'\"]\s+name=[\'\"]csrf_token[\'\"]', html)

        csrf_token = csrf_match.group(1) if csrf_match else ""
        print(f"  ✓ Handshake successful (CSRF token: {csrf_token[:10]}...)")

        # Submit Credentials
        print(f"🔐 [2/3] Authenticating account '{self.username}'...")
        post_data = {
            "csrf_token": csrf_token,
            "ssoId": self.username,
            "password": self.password,
            "rememberMe": "on"
        }

        login_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{BASE_BCS_URL}/"
        }

        try:
            login_resp = self._request(LOGIN_URL, data=post_data, headers=login_headers)
            final_url = login_resp.geturl()
            content = login_resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            raise RuntimeError(f"Authentication request failed: {e}")

        if "login?error" in final_url or "The entered username is invalid" in content or "Bad credentials" in content:
            err_matches = re.findall(
                r'<div[^>]*class=[\'\"][^\'\"]*(?:error|alert|danger)[^\'\"]*[\'\"][^>]*>(.*?)</div>',
                content,
                re.I
            )
            err_msg = re.sub(r'<[^>]+>', '', err_matches[0]).strip() if err_matches else "Invalid username or password."
            raise ValueError(f"AutoRox Login Failed: {err_msg}")

        print("  ✅ Login successful! Session established.")

        # Step 3: Extract Tokens and Identifiers from Inventory Controller
        print("🔐 [3/3] Resolving Workshop Credentials & Inventory Controller Gateway...")
        try:
            stock_page_resp = self._request(STOCK_PAGE_URL, headers={"Referer": final_url})
            dest_url = stock_page_resp.geturl()
            page_html = stock_page_resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            raise RuntimeError(f"Failed to reach Inventory Stock page: {e}")

        combined_text = dest_url + "\n" + page_html

        # Extract JWT Token
        token_match = re.search(r'token=([a-zA-Z0-9_\-\.]+)', combined_text)
        if not token_match:
            token_match = re.search(r'eyJhbGciOi[a-zA-Z0-9_\-\.]+', page_html)

        if token_match:
            raw_token = token_match.group(1) if hasattr(token_match, 'group') and token_match.group(0).startswith('token=') else token_match.group(0)
            self.jwt_token = raw_token.split('#')[0].split('&')[0]
            self._decode_jwt(self.jwt_token)

        # Extract encryptedWorkShopId from hidden input
        ws_id_match = re.search(r'id=[\'\"]encryptedWorkShopId[\'\"]\s+value=[\'\"]([^\'\"]+)[\'\"]', page_html)
        if not ws_id_match:
            ws_id_match = re.search(r'value=[\'\"]([^\'\"]+)[\'\"]\s+id=[\'\"]encryptedWorkShopId[\'\"]', page_html)

        if ws_id_match:
            self.encrypted_workshop_id = ws_id_match.group(1)

        # Extract page id (zdMt7_...)
        id_match = re.search(r'id=[\'\"]id[\'\"]\s+value=[\'\"]([^\'\"]+)[\'\"]', page_html)
        if not id_match:
            id_match = re.search(r'value=[\'\"]([^\'\"]+)[\'\"]\s+id=[\'\"]id[\'\"]', page_html)
        if not id_match:
            id_match = re.search(r'[?&]id=([a-zA-Z0-9_\-]+)', dest_url)

        if id_match:
            self.page_id = id_match.group(1)

        # Fallback to JWT encryptedWorkshopId if hidden input wasn't present
        if not self.encrypted_workshop_id and hasattr(self, 'encrypted_ws_id') and self.encrypted_ws_id:
            self.encrypted_workshop_id = self.encrypted_ws_id

        print(f"  ✓ Account / Role: {self.username} ({self.role or 'Active'})")
        print(f"  ✓ Workshop ID: {self.workshop_id or '49045'}")
        print(f"  ✓ Encrypted Workshop ID: {self.encrypted_workshop_id[:16]}..." if self.encrypted_workshop_id else "  ⚠️ Workshop ID extracted from session")
        print(f"  ✓ Access Token (JWT): Valid until {self.token_expiry or 'Active Session'}")

    def _decode_jwt(self, jwt_str):
        try:
            parts = jwt_str.split('.')
            if len(parts) >= 2:
                padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                payload_json = base64.urlsafe_b64decode(padded).decode('utf-8')
                payload = json.loads(payload_json)
                self.workshop_id = payload.get("workshop_id")
                self.encrypted_ws_id = payload.get("encryptedWorkshopId")
                self.role = payload.get("roles")
                self.exp_ts = payload.get("exp")
                if self.exp_ts:
                    self.token_expiry = datetime.fromtimestamp(self.exp_ts).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

    def _save_session_cache(self):
        if not self.cache_file:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.cache_file)), exist_ok=True)
        cache_data = {
            "username": self.username,
            "jwt_token": self.jwt_token,
            "encrypted_workshop_id": self.encrypted_workshop_id,
            "page_id": self.page_id,
            "workshop_id": self.workshop_id,
            "exp": self.exp_ts,
            "token_expiry": self.token_expiry,
            "role": self.role,
            "cookies": self.cookies,
            "cookie_str": self.cookie_str,
            "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
        print(f"  💾 Session credentials cached to: {self.cache_file}")

    def fetch_all_inventory(self, page_size=20, retried=False):
        print(f"\n📦 Fetching Live Stock via AutoRox Stock Controller ({STOCK_API_URL})...")

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_BCS_URL,
            "Referer": f"{STOCK_PAGE_URL}?id={self.page_id or ''}&token={self.jwt_token or ''}"
        }

        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"

        all_items = []
        page_no = 1
        total_count = None
        total_qty = 0
        total_price = 0

        while True:
            body = {
                "workshopId": self.encrypted_workshop_id or "",
                "pageSize": str(page_size),
                "pageNo": str(page_no),
                "search": "",
                "isFranchisor": "",
                "workshopIds": []
            }

            try:
                resp = self._request(STOCK_API_URL, data=body, headers=headers, method="POST")
                raw_content = resp.read().decode("utf-8")
                res_json = json.loads(raw_content)
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and not retried:
                    print(f"  ⚠️ HTTP {e.code} received with cached credentials. Refreshing login...")
                    self.ensure_authenticated(force=True)
                    return self.fetch_all_inventory(page_size=page_size, retried=True)
                raise RuntimeError(f"HTTP Error {e.code} fetching stock list: {e}")
            except Exception as e:
                raise RuntimeError(f"Failed to fetch stock list page {page_no}: {e}")

            if total_count is None:
                total_count = int(res_json.get("totalcount", 0))
                total_qty = res_json.get("totalQty", 0)
                total_price = res_json.get("totalPrice", 0)
                print(f"  📊 AutoRox Live Stock: {total_count:,} SKUs | Total Qty: {total_qty} units | Valuation: ₹{total_price:,.2f}")

            page_items = res_json.get("response", [])
            if not page_items:
                break

            all_items.extend(page_items)
            print(f"  • Page {page_no}: +{len(page_items)} SKUs (Progress: {len(all_items)} / {total_count})")

            if len(all_items) >= total_count:
                break

            page_no += 1

        return all_items


def save_inventory(items, output_dir="output"):
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "AutoRox_Live_Inventory.csv")
    json_path = os.path.join(output_dir, "AutoRox_Live_Inventory.json")

    print(f"\n💾 Saving {len(items):,} live stock items to disk...")

    # 1. Save Full JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    print(f"  ✓ Raw JSON saved: {json_path}")

    # 2. Save Normalized CSV
    fieldnames = [
        "partNumber", "partName", "brand", "category",
        "shelfLocation", "stockOnHand", "sellingPrice",
        "taxPercent", "taxAmount", "primaryUom", "licence", "ageing"
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for it in items:
            row = {
                "partNumber": it.get("partNo") or it.get("partNumber", ""),
                "partName": it.get("partName") or it.get("name", ""),
                "brand": it.get("brand") or "",
                "category": it.get("categoryName") or it.get("category", ""),
                "shelfLocation": it.get("rack") or it.get("shelfLocation", ""),
                "stockOnHand": it.get("QoH") if it.get("QoH") is not None else it.get("stockOnHand", 0),
                "sellingPrice": it.get("avgSellingPrice") or it.get("sellingPrice", 0),
                "taxPercent": it.get("gstPer") or it.get("taxPercent", 18),
                "taxAmount": it.get("txAmount") or 0,
                "primaryUom": it.get("primaryUom") or "Nos",
                "licence": it.get("licence") or "",
                "ageing": it.get("ageing") or 0
            }
            writer.writerow(row)

    print(f"  ✓ Normalized CSV saved: {csv_path}")
    return csv_path, json_path


def update_sqlite_db(items, db_path="inventory.db"):
    import sqlite3
    print(f"\n🗄️ Updating SQLite High-Speed Store ({db_path})...")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            Part_Number TEXT PRIMARY KEY,
            Part_Name TEXT,
            Brand TEXT,
            Category TEXT,
            Shelf_Location TEXT,
            Stock_On_Hand REAL,
            Selling_Price REAL,
            Tax_pct REAL,
            Primary_Uom TEXT,
            Licence TEXT,
            Ageing INTEGER,
            Last_Updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    updated = 0
    for it in items:
        p_num = str(it.get("partNo") or it.get("partNumber", "")).strip()
        p_name = str(it.get("partName") or it.get("name", "")).strip()
        brand = str(it.get("brand") or "").strip()
        cat = str(it.get("categoryName") or it.get("category", "")).strip()
        shelf = str(it.get("rack") or it.get("shelfLocation", "")).strip()

        try:
            stock = float(it.get("QoH") if it.get("QoH") is not None else it.get("stockOnHand", 0))
        except (ValueError, TypeError):
            stock = 0.0

        try:
            sp = float(it.get("avgSellingPrice") or it.get("sellingPrice", 0))
        except (ValueError, TypeError):
            sp = 0.0

        try:
            tax = float(it.get("gstPer") or it.get("taxPercent", 18))
        except (ValueError, TypeError):
            tax = 18.0

        uom = str(it.get("primaryUom") or "Nos").strip()
        licence = str(it.get("licence") or "")
        ageing = int(it.get("ageing") or 0)

        cur.execute("""
            INSERT OR REPLACE INTO items (
                Part_Number, Part_Name, Brand, Category, Shelf_Location,
                Stock_On_Hand, Selling_Price, Tax_pct, Primary_Uom,
                Licence, Ageing, Last_Updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (p_num, p_name, brand, cat, shelf, stock, sp, tax, uom, licence, ageing))
        updated += 1

    conn.commit()
    conn.close()
    print(f"  ✓ Successfully synchronized {updated:,} items in {db_path}")


def main():
    parser = argparse.ArgumentParser(
        description="AutoRox Live Inventory Sync & Intelligent Session Caching Tool"
    )
    parser.add_argument("-u", "--username", help="AutoRox username / SSO ID (e.g. whatomate)")
    parser.add_argument("-p", "--password", help="AutoRox account password")
    parser.add_argument("-o", "--output-dir", default="output", help="Directory to save exported files (default: output)")
    parser.add_argument("--update-db", action="store_true", help="Sync directly into local SQLite inventory store")
    parser.add_argument("--force-login", action="store_true", help="Bypass cached session and force a new login handshake")
    parser.add_argument("--session-file", help="Path to session cache file (default: <output-dir>/.autorox_session.json)")

    args = parser.parse_args()

    session_file = args.session_file or os.path.join(args.output_dir, ".autorox_session.json")

    username = args.username or os.getenv("AUTOROX_USERNAME")
    password = args.password or os.getenv("AUTOROX_PASSWORD")

    if not username and os.path.exists(session_file) and not args.force_login:
        try:
            with open(session_file, "r") as f:
                c = json.load(f)
                username = c.get("username")
        except Exception:
            pass

    if not username:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("🔑 AutoRox Secure Login Prompt")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        username = input("Enter AutoRox Username / SSO ID (e.g. whatomate): ").strip()

    cache_valid = False
    if os.path.exists(session_file) and not args.force_login:
        try:
            with open(session_file, "r") as f:
                c = json.load(f)
            remaining = int(c.get("exp", 0)) - int(time.time())
            if c.get("username", "").lower() == username.lower() and remaining > EXPIRY_BUFFER_SECONDS:
                cache_valid = True
        except Exception:
            cache_valid = False

    if not cache_valid and not password:
        password = getpass.getpass(f"Enter AutoRox Password for '{username}': ").strip()

    try:
        client = AutoRoxClient(username, password or "", cache_file=session_file)
        client.ensure_authenticated(force=args.force_login)
        items = client.fetch_all_inventory()
        save_inventory(items, args.output_dir)

        if args.update_db:
            db_file = os.path.join(args.output_dir, "inventory.db")
            update_sqlite_db(items, db_file)

        print("\n🎉 [SUCCESS] Live inventory sync completed successfully!")
    except Exception as err:
        print(f"\n❌ Error during sync: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
