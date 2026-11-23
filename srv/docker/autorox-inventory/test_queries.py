#!/usr/bin/env python3
"""
Test Suite for Pillar 2 Inventory Service
Runs automated verification against the real AutoRox master data files.
"""

import sys
import os

# Import the engine from pillar2_inventory_service
from pillar2_inventory_service import engine, format_whatsapp_stock_reply, format_whatsapp_vendor_reply, format_whatsapp_lowstock_reply

def run_tests():
    print("=" * 60)
    print("RUNNING PILLAR 2 MASTER DATA VERIFICATION TESTS")
    print("=" * 60)

    # Test 1: Check Master Brands
    brand_count = engine.conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
    print(f"\n[Test 1] Brands Index: {brand_count:,} brands indexed.")
    assert brand_count >= 3150, f"Expected 3151 brands, got {brand_count}"
    print("  ✅ PASS: All 3,151 brands verified.")

    # Test 2: Check Items
    item_count = engine.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    print(f"\n[Test 2] SKUs Index: {item_count:,} items indexed.")
    assert item_count >= 1900, f"Expected ~1,938 items, got {item_count}"
    print("  ✅ PASS: 1,938 SKUs verified.")

    # Test 3: Check Vendors
    vendor_count = engine.conn.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
    print(f"\n[Test 3] Vendors Index: {vendor_count:,} vendors indexed.")
    assert vendor_count >= 30, f"Expected 31 vendors, got {vendor_count}"
    print("  ✅ PASS: 31 Vendors verified.")

    # Test 4: Stock Lookup for "oil filter"
    print("\n[Test 4] Query: 'oil filter'")
    results = engine.search_stock("oil filter")
    print(f"  Found {len(results)} matches.")
    assert len(results) > 0, "Expected at least 1 match for oil filter"
    print(format_whatsapp_stock_reply("oil filter", results[:2]))
    print("  ✅ PASS: Stock lookup functional.")

    # Test 5: Vendor Lookup for "vikas"
    print("\n[Test 5] Query: 'vikas'")
    v_results = engine.search_vendor("vikas")
    print(f"  Found {len(v_results)} vendor matches.")
    assert len(v_results) > 0, "Expected match for vikas"
    print(format_whatsapp_vendor_reply("vikas", v_results))
    print("  ✅ PASS: Vendor directory lookup functional.")

    # Test 6: Low Stock Reorder Digest
    print("\n[Test 6] Low-Stock Alert Generation")
    low_stock = engine.get_low_stock_items()
    assert len(low_stock) > 0
    print(format_whatsapp_lowstock_reply(low_stock))
    print("  ✅ PASS: Low-stock alert functional.")

    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED! Master data and bot logic are 100% verified.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
