package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func getTestEngine(t *testing.T) *Engine {
	t.Helper()
	dbPath, err := filepath.Abs("../data/live/inventory.db")
	if err != nil {
		t.Fatalf("Failed to resolve db path: %v", err)
	}

	cfg := Config{
		Port:   8000,
		DBPath: dbPath,
	}

	eng, err := NewEngine(cfg)
	if err != nil {
		t.Fatalf("Failed to create engine: %v", err)
	}
	return eng
}

func TestStockSearch(t *testing.T) {
	eng := getTestEngine(t)
	defer eng.db.Close()

	items, err := eng.SearchStock("oil filter")
	if err != nil {
		t.Fatalf("SearchStock failed: %v", err)
	}

	if len(items) == 0 {
		t.Fatal("Expected at least 1 match for 'oil filter', got 0")
	}

	t.Logf("Found %d items for 'oil filter'. First match: %s (%s)", len(items), items[0].PartName, items[0].PartNumber)

	reply := FormatStockReply("oil filter", items)
	if !strings.Contains(reply, "STOCK LOOKUP") {
		t.Errorf("Reply missing STOCK LOOKUP header: %s", reply)
	}
	if !strings.Contains(reply, "A1-R1-S3") && !strings.Contains(reply, "Rack A1") {
		t.Errorf("Reply missing expected Rack location: %s", reply)
	}
}

func TestVendorSearch(t *testing.T) {
	eng := getTestEngine(t)
	defer eng.db.Close()

	vendors, err := eng.SearchVendor("vikas")
	if err != nil {
		t.Fatalf("SearchVendor failed: %v", err)
	}

	if len(vendors) == 0 {
		t.Fatal("Expected at least 1 match for 'vikas', got 0")
	}

	reply := FormatVendorReply("vikas", vendors)
	if !strings.Contains(reply, "VIKAS") {
		t.Errorf("Reply missing VIKAS: %s", reply)
	}
}

func TestProcessCommand(t *testing.T) {
	eng := getTestEngine(t)
	defer eng.db.Close()

	tests := []struct {
		input       string
		mustContain string
	}{
		{"stock Creta oil filter", "STOCK LOOKUP"},
		{"part F002H235238F8", "STOCK LOOKUP"},
		{"vendor vikas", "VENDOR DIRECTORY"},
		{"lowstock", "DAILY LOW-STOCK REORDER ALERT"},
		{"help", "Available WhatsApp Commands"},
	}

	for _, tc := range tests {
		res := eng.ProcessCommand(tc.input)
		if !strings.Contains(res, tc.mustContain) {
			t.Errorf("For input %q, expected reply to contain %q, got: %s", tc.input, tc.mustContain, res)
		}
	}
}

func TestHasMedia(t *testing.T) {
	p1 := WhatomateWebhookPayload{Body: "stock oil filter"}
	if p1.HasMedia() {
		t.Errorf("Expected false for text-only payload")
	}

	p2 := WhatomateWebhookPayload{Type: "image", MediaURL: "http://example.com/bill.jpg"}
	if !p2.HasMedia() {
		t.Errorf("Expected true for image payload")
	}

	p3 := WhatomateWebhookPayload{ImageBase64: "dGVzdA=="}
	if !p3.HasMedia() {
		t.Errorf("Expected true for base64 image payload")
	}
}

func TestOCRReplyFormatting(t *testing.T) {
	mockData := OCRResponse{
		Engine:        "PP-OCRv6",
		VendorName:    "VIKAS TRADE LINKS",
		VendorGSTIN:   "29AABCV1234F1Z5",
		InvoiceNumber: "INV-2026-9912",
		InvoiceDate:   "2026-11-21",
		ItemsCount:    2,
		LatencyMS:     148.5,
		Hardware:      "NVIDIA GeForce GTX 1050 Mobile",
		LineItems: []OCRExtractedItem{
			{
				PartNumber:    "F002H234678F8",
				CatalogName:   "OIL-FILTER ELEMENT",
				Quantity:      10,
				UnitRate:      215.00,
				GSTPercent:    18,
				Status:        "MATCHED_MASTER",
				ShelfLocation: "Rack A1 - Row 1 - Shelf S3",
			},
		},
		PriceAlerts: []string{
			"⚠️ Low Margin Alert on `F002H234678F8`: Buying at ₹215.00, Selling at ₹257.63 (Margin: 16.5%)",
		},
	}

	reply := FormatOCRReply(mockData)
	if !strings.Contains(reply, "PP-OCRv6 INVOICE PARSED") {
		t.Errorf("Expected header in OCR reply, got: %s", reply)
	}
	if !strings.Contains(reply, "VIKAS TRADE LINKS") {
		t.Errorf("Expected vendor name in OCR reply")
	}
	if !strings.Contains(reply, "Rack A1 - Row 1 - Shelf S3") {
		t.Errorf("Expected shelf location in OCR reply")
	}
	if !strings.Contains(reply, "INWARD YES") {
		t.Errorf("Expected call to action in OCR reply")
	}
}

func BenchmarkStockSearch(b *testing.B) {
	dbPath, _ := filepath.Abs("../data/live/inventory.db")
	eng, err := NewEngine(Config{DBPath: dbPath})
	if err != nil {
		b.Fatalf("Failed to create engine: %v", err)
	}
	defer eng.db.Close()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = eng.SearchStock("oil filter")
	}
}
