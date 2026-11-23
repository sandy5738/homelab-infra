package main

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

// Global cache for deduplicating incoming webhook message IDs
var processedMessageIDs sync.Map

// PartItem represents an automotive stock item in the database
type PartItem struct {
	PartNumber    string  `json:"part_number"`
	PartName      string  `json:"part_name"`
	Brand         string  `json:"brand"`
	SellingPrice  float64 `json:"selling_price"`
	TaxPercent    float64 `json:"tax_percent"`
	PrimaryUom    string  `json:"uom"`
	StockOnHand   float64 `json:"stock_on_hand"`
	ShelfLocation string  `json:"shelf_location"`
}

// VendorItem represents an approved workshop supplier
type VendorItem struct {
	VendorName   string `json:"vendor_name"`
	VendorType   string `json:"vendor_type"`
	ContactName  string `json:"contact_name"`
	MobileNumber string `json:"mobile_number"`
	GSTIN        string `json:"gstin"`
}

// LowStockItem represents a fast-moving item below minimum reorder threshold
type LowStockItem struct {
	PartName        string `json:"part_name"`
	Stock           string `json:"stock"`
	MinThreshold    string `json:"min_threshold"`
	PreferredVendor string `json:"preferred_vendor"`
	VendorContact   string `json:"vendor_contact"`
	SuggestedOrder  string `json:"suggested_order"`
}

// MediaObject represents attached media metadata
type MediaObject struct {
	ID       string `json:"id,omitempty"`
	URL      string `json:"url,omitempty"`
	MimeType string `json:"mime_type,omitempty"`
}

// WhatomateWebhookPayload represents incoming Whatomate WhatsApp events in flat, nested, or Whatomate outbound dispatch format
type WhatomateWebhookPayload struct {
	Event       string      `json:"event,omitempty"`
	Body        string      `json:"body,omitempty"`
	Sender      string      `json:"sender,omitempty"`
	From        string      `json:"from,omitempty"`
	ContactID   string      `json:"contact_id,omitempty"`
	MessageID   string      `json:"message_id,omitempty"`
	Type        string      `json:"type,omitempty"`
	ImageBase64 string      `json:"image_base64,omitempty"`
	MediaURL    string      `json:"media_url,omitempty"`
	Image       MediaObject `json:"image,omitempty"`
	Document    MediaObject `json:"document,omitempty"`
	Text        struct {
		Body string `json:"body,omitempty"`
	} `json:"text,omitempty"`
	Data struct {
		MessageID        string `json:"message_id,omitempty"`
		ContactID        string `json:"contact_id,omitempty"`
		ContactPhone     string `json:"contact_phone,omitempty"`
		ContactName      string `json:"contact_name,omitempty"`
		MessageType      string `json:"message_type,omitempty"`
		Direction        string `json:"direction,omitempty"`
		Content          string `json:"content,omitempty"`
		MediaURL         string `json:"media_url,omitempty"`
		MediaMimeType    string `json:"media_mime_type,omitempty"`
		MediaFilename    string `json:"media_filename,omitempty"`
		ReplyToMessageID string `json:"reply_to_message_id,omitempty"`
		WhatsAppAccount  string `json:"whatsapp_account,omitempty"`
	} `json:"data,omitempty"`
	Entry []struct {
		Changes []struct {
			Value struct {
				Messages []struct {
					From     string      `json:"from,omitempty"`
					Type     string      `json:"type,omitempty"`
					Text     struct {
						Body string `json:"body,omitempty"`
					} `json:"text,omitempty"`
					Image    MediaObject `json:"image,omitempty"`
					Document MediaObject `json:"document,omitempty"`
				} `json:"messages,omitempty"`
			} `json:"value,omitempty"`
		} `json:"changes,omitempty"`
	} `json:"entry,omitempty"`
}

func (p *WhatomateWebhookPayload) HasMedia() bool {
	if p.Data.MediaURL != "" || p.Data.MessageType == "image" || p.Data.MessageType == "document" {
		return true
	}
	if p.ImageBase64 != "" || p.MediaURL != "" || p.Image.ID != "" || p.Image.URL != "" || p.Document.ID != "" {
		return true
	}
	if p.Type == "image" || p.Type == "document" {
		return true
	}
	if len(p.Entry) > 0 && len(p.Entry[0].Changes) > 0 {
		msgs := p.Entry[0].Changes[0].Value.Messages
		if len(msgs) > 0 {
			m := msgs[0]
			return m.Type == "image" || m.Type == "document" || m.Image.ID != "" || m.Image.URL != "" || m.Document.ID != ""
		}
	}
	return false
}

func (p *WhatomateWebhookPayload) GetMediaInfo() (mediaType, mediaID, mediaURL, base64Data string) {
	if p.Data.MediaURL != "" {
		mType := p.Data.MessageType
		if mType == "" {
			mType = "image"
		}
		return mType, p.Data.MessageID, p.Data.MediaURL, ""
	}
	if p.ImageBase64 != "" {
		return "image", "", "", p.ImageBase64
	}
	if p.MediaURL != "" {
		return "image", "", p.MediaURL, ""
	}
	if p.Image.URL != "" {
		return "image", p.Image.ID, p.Image.URL, ""
	}
	if p.Image.ID != "" {
		return "image", p.Image.ID, "", ""
	}
	if p.Document.URL != "" {
		return "document", p.Document.ID, p.Document.URL, ""
	}
	if len(p.Entry) > 0 && len(p.Entry[0].Changes) > 0 {
		msgs := p.Entry[0].Changes[0].Value.Messages
		if len(msgs) > 0 {
			m := msgs[0]
			if m.Image.URL != "" || m.Image.ID != "" {
				return "image", m.Image.ID, m.Image.URL, ""
			}
			if m.Document.URL != "" || m.Document.ID != "" {
				return "document", m.Document.ID, m.Document.URL, ""
			}
		}
	}
	return "", "", "", ""
}

func (p *WhatomateWebhookPayload) GetMessageText() string {
	if p.Data.Content != "" {
		return p.Data.Content
	}
	if p.Body != "" {
		return p.Body
	}
	if p.Text.Body != "" {
		return p.Text.Body
	}
	if len(p.Entry) > 0 && len(p.Entry[0].Changes) > 0 {
		msgs := p.Entry[0].Changes[0].Value.Messages
		if len(msgs) > 0 {
			return msgs[0].Text.Body
		}
	}
	return ""
}

func (p *WhatomateWebhookPayload) GetSender() string {
	if p.Data.ContactPhone != "" {
		return p.Data.ContactPhone
	}
	if p.Sender != "" {
		return p.Sender
	}
	if p.From != "" {
		return p.From
	}
	if len(p.Entry) > 0 && len(p.Entry[0].Changes) > 0 {
		msgs := p.Entry[0].Changes[0].Value.Messages
		if len(msgs) > 0 {
			return msgs[0].From
		}
	}
	return ""
}

func (p *WhatomateWebhookPayload) GetContactID() string {
	if p.Data.ContactID != "" {
		return p.Data.ContactID
	}
	if p.ContactID != "" {
		return p.ContactID
	}
	return p.GetSender()
}

// Config holds server runtime options
type Config struct {
	Port         int
	DBPath       string
	WhatomateURL string
	WhatomateKey string
	OCRURL       string
}

// Engine encapsulates the database pool and search methods
type Engine struct {
	db     *sql.DB
	config Config
}

func NewEngine(cfg Config) (*Engine, error) {
	// Connect to SQLite in read-only WAL mode for extreme concurrency and low memory
	dsn := fmt.Sprintf("file:%s?mode=ro&_journal_mode=WAL&_busy_timeout=5000", cfg.DBPath)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open sqlite database: %w", err)
	}

	db.SetMaxOpenConns(50)
	db.SetMaxIdleConns(10)
	db.SetConnMaxLifetime(time.Hour)

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("database ping failed: %w", err)
	}

	return &Engine{db: db, config: cfg}, nil
}

// SearchStock queries items matching tokens across Part_Name, Part_Number, Brand, Sub_Category
func (e *Engine) SearchStock(query string) ([]PartItem, error) {
	cleanQuery := strings.TrimSpace(query)
	tokens := strings.Fields(cleanQuery)
	if len(tokens) == 0 {
		return nil, nil
	}

	// 1. Try strict AND match across all tokens
	results, err := e.queryStockTokens(tokens, true)
	if err == nil && len(results) > 0 {
		return results, nil
	}

	// 2. If strict match fails and we have multiple tokens (e.g. "Creta oil filter"),
	// identify known vehicle names or try matching the remaining part tokens
	if len(tokens) > 1 {
		var partTokens []string
		for _, t := range tokens {
			lower := strings.ToLower(t)
			// Common vehicle names in Indian workshops
			if lower == "creta" || lower == "swift" || lower == "i20" || lower == "innova" ||
				lower == "verna" || lower == "baleno" || lower == "dzire" || lower == "city" {
				continue
			}
			partTokens = append(partTokens, t)
		}

		if len(partTokens) > 0 && len(partTokens) < len(tokens) {
			results, err = e.queryStockTokens(partTokens, true)
			if err == nil && len(results) > 0 {
				return results, nil
			}
		}

		// 3. Fallback: OR search with ranking by match count
		return e.queryStockTokens(tokens, false)
	}

	return results, nil
}

func (e *Engine) queryStockTokens(tokens []string, matchAll bool) ([]PartItem, error) {
	var whereClauses []string
	var args []any

	for _, token := range tokens {
		pattern := "%" + token + "%"
		whereClauses = append(whereClauses, "(Part_Name LIKE ? OR Part_Number LIKE ? OR Brand LIKE ?)")
		args = append(args, pattern, pattern, pattern)
	}

	operator := " AND "
	if !matchAll {
		operator = " OR "
	}

	querySQL := fmt.Sprintf(`
		SELECT Part_Number, Part_Name, Brand, COALESCE(Selling_Price, 0), 
		       COALESCE(Tax_pct, 18), COALESCE(Primary_Uom, 'Nos'), 
		       COALESCE(Stock_On_Hand, 0), COALESCE(Shelf_Location, '')
		FROM items
		WHERE %s
		ORDER BY Stock_On_Hand DESC, Part_Name ASC
		LIMIT 5
	`, strings.Join(whereClauses, operator))

	rows, err := e.db.Query(querySQL, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []PartItem
	for rows.Next() {
		var it PartItem
		if err := rows.Scan(&it.PartNumber, &it.PartName, &it.Brand, &it.SellingPrice, &it.TaxPercent, &it.PrimaryUom, &it.StockOnHand, &it.ShelfLocation); err != nil {
			continue
		}
		if it.ShelfLocation == "" {
			it.ShelfLocation = e.assignDefaultShelf(it.PartName)
		}
		results = append(results, it)
	}

	return results, nil
}

// SearchVendor queries registered vendors
func (e *Engine) SearchVendor(query string) ([]VendorItem, error) {
	pattern := "%" + strings.TrimSpace(query) + "%"
	querySQL := `
		SELECT Vendor_Name, COALESCE(Vendor_Type, 'Distributor'), 
		       COALESCE(Contact_Name, 'N/A'), COALESCE(Mobile_Number, 'N/A'), 
		       COALESCE(GSTIN, 'N/A')
		FROM vendors
		WHERE Vendor_Name LIKE ? OR Contact_Name LIKE ? OR Mobile_Number LIKE ?
		LIMIT 5
	`
	rows, err := e.db.Query(querySQL, pattern, pattern, pattern)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []VendorItem
	for rows.Next() {
		var v VendorItem
		if err := rows.Scan(&v.VendorName, &v.VendorType, &v.ContactName, &v.MobileNumber, &v.GSTIN); err != nil {
			continue
		}
		results = append(results, v)
	}
	return results, nil
}

// GetLowStockItems returns standard fast-moving items below safety stock
func (e *Engine) GetLowStockItems() []LowStockItem {
	return []LowStockItem{
		{
			PartName:        "ENGINE OIL 5W-30 (BOSCH)",
			Stock:           "8 Litres",
			MinThreshold:    "50 Litres",
			PreferredVendor: "VIKAS TRADE LINKS",
			VendorContact:   "Ranjith (+91 95133 37752)",
			SuggestedOrder:  "1x 50L Drum",
		},
		{
			PartName:        "FILTER, OIL (BOSCH - Creta/i20)",
			Stock:           "1 unit",
			MinThreshold:    "5 units",
			PreferredVendor: "AUTOVERSE",
			VendorContact:   "Rajesh (+91 97410 54321)",
			SuggestedOrder:  "10 units",
		},
		{
			PartName:        "FILTER, AIR (BOSCH - Swift/Dzire)",
			Stock:           "2 units",
			MinThreshold:    "6 units",
			PreferredVendor: "VIKAS TRADE LINKS",
			VendorContact:   "Ranjith (+91 95133 37752)",
			SuggestedOrder:  "10 units",
		},
	}
}

func (e *Engine) assignDefaultShelf(partName string) string {
	upper := strings.ToUpper(partName)
	switch {
	case strings.Contains(upper, "CABIN"):
		return "Rack A1 - Row 1 - Shelf S1"
	case strings.Contains(upper, "SPARK PLUG"):
		return "Rack A1 - Row 1 - Shelf S2"
	case strings.Contains(upper, "OIL FILTER") || strings.Contains(upper, "OIL-FILTER"):
		return "Rack A1 - Row 1 - Shelf S3"
	case strings.Contains(upper, "AIR FILTER") || strings.Contains(upper, "AIR-FILTER"):
		return "Rack A1 - Row 1 - Shelf S4"
	case strings.Contains(upper, "WIPER"):
		return "Rack A1 - Row 2 - Shelf S1"
	case strings.Contains(upper, "BRAKE"):
		return "Rack A1 - Row 2 - Shelf S2"
	case strings.Contains(upper, "OIL"):
		return "Rack A1 - Row 3 - Shelf S1"
	case strings.Contains(upper, "FLUID") || strings.Contains(upper, "COOLANT"):
		return "Rack A1 - Row 3 - Shelf S2"
	default:
		return "Rack B1 - General Spares"
	}
}

// OCRExtractedItem represents an invoice item parsed by PP-OCRv6
type OCRExtractedItem struct {
	PartNumber            string  `json:"part_number"`
	Description           string  `json:"description"`
	Quantity              float64 `json:"quantity"`
	UnitRate              float64 `json:"unit_rate"`
	GSTPercent            float64 `json:"gst_percent"`
	TaxExclusiveBasePrice float64 `json:"tax_exclusive_base_price"`
	Status                string  `json:"status"`
	CatalogName           string  `json:"catalog_name"`
	Brand                 string  `json:"brand"`
	SellingPrice          float64 `json:"selling_price"`
	CurrentStock          float64 `json:"current_stock"`
	ShelfLocation         string  `json:"shelf_location"`
}

// OCRResponse represents the structured invoice analysis from autorox-ocr
type OCRResponse struct {
	Engine        string             `json:"engine"`
	VendorName    string             `json:"vendor_name"`
	VendorGSTIN   string             `json:"vendor_gstin"`
	InvoiceNumber string             `json:"invoice_number"`
	InvoiceDate   string             `json:"invoice_date"`
	ItemsCount    int                `json:"items_count"`
	LineItems     []OCRExtractedItem `json:"line_items"`
	PriceAlerts   []string           `json:"price_alerts"`
	LatencyMS     float64            `json:"latency_ms"`
	Hardware      string             `json:"hardware"`
}

// FormatOCRReply converts structured PP-OCRv6 invoice data into a rich WhatsApp message
func FormatOCRReply(data OCRResponse) string {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("🧾 *PP-OCRv6 INVOICE PARSED: %s*\n", data.VendorName))
	sb.WriteString("─────────────────────────────\n")
	sb.WriteString(fmt.Sprintf("• *Invoice No:* `%s`\n", data.InvoiceNumber))
	sb.WriteString(fmt.Sprintf("• *GSTIN:* `%s`\n", data.VendorGSTIN))
	sb.WriteString(fmt.Sprintf("• *Date:* %s\n", data.InvoiceDate))
	sb.WriteString(fmt.Sprintf("• *Parts Extracted:* %d (OCR Time: %.1fms on %s)\n\n", data.ItemsCount, data.LatencyMS, data.Hardware))

	if len(data.LineItems) > 0 {
		sb.WriteString("📋 *Verified Line Items:*\n")
		for i, it := range data.LineItems {
			statusIcon := "✅"
			if it.Status == "NEW_SKU" {
				statusIcon = "🆕"
			}
			name := it.CatalogName
			if name == "" {
				name = it.Description
			}
			sb.WriteString(fmt.Sprintf("%s *%d. %s*\n", statusIcon, i+1, name))
			sb.WriteString(fmt.Sprintf("   • *Part No:* `%s` | *Qty:* %.0f\n", it.PartNumber, it.Quantity))
			sb.WriteString(fmt.Sprintf("   • *Buy Rate:* ₹%.2f (+%.0f%% GST)\n", it.UnitRate, it.GSTPercent))
			sb.WriteString(fmt.Sprintf("   • *Shelf:* 📍 *%s*\n\n", it.ShelfLocation))
		}
	}

	if len(data.PriceAlerts) > 0 {
		sb.WriteString("─────────────────────────────\n")
		sb.WriteString("🚨 *MARGIN LEAKAGE & PRICE HIKE ALERTS:*\n")
		for _, alert := range data.PriceAlerts {
			sb.WriteString(alert + "\n")
		}
		sb.WriteString("\n")
	}

	sb.WriteString("─────────────────────────────\n")
	sb.WriteString("Reply *INWARD YES* to auto-post this bill to AutoRox Direct Inward!")
	return strings.TrimSpace(sb.String())
}

// FetchAndProcessOCR dispatches image data to the PP-OCRv6 microservice on port 8005
func (e *Engine) FetchAndProcessOCR(payload *WhatomateWebhookPayload) (string, error) {
	if e.config.OCRURL == "" {
		return "", fmt.Errorf("OCR service URL not configured")
	}

	mediaType, mediaID, mediaURL, base64Data := payload.GetMediaInfo()
	targetURL := fmt.Sprintf("%s/api/ocr/extract", strings.TrimRight(e.config.OCRURL, "/"))

	var reqBody []byte
	var err error

	if base64Data != "" {
		reqBody, _ = json.Marshal(map[string]string{"image_base64": base64Data})
	} else if mediaURL != "" {
		// Download image from media URL
		resp, err := http.Get(mediaURL)
		if err != nil {
			return "", fmt.Errorf("failed to download media from %s: %w", mediaURL, err)
		}
		defer resp.Body.Close()
		reqBody, err = io.ReadAll(resp.Body)
		if err != nil {
			return "", fmt.Errorf("failed to read media body: %w", err)
		}
	} else if mediaID != "" && e.config.WhatomateURL != "" {
		// Download media from Whatomate API
		downloadURL := fmt.Sprintf("%s/api/media/%s", strings.TrimRight(e.config.WhatomateURL, "/"), mediaID)
		req, _ := http.NewRequest("GET", downloadURL, nil)
		if e.config.WhatomateKey != "" {
			req.Header.Set("X-API-Key", e.config.WhatomateKey)
		}
		client := &http.Client{Timeout: 10 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			return "", fmt.Errorf("failed to fetch media from whatomate: %w", err)
		}
		defer resp.Body.Close()
		reqBody, err = io.ReadAll(resp.Body)
		if err != nil {
			return "", fmt.Errorf("failed to read whatomate media bytes: %w", err)
		}
	} else {
		return "", fmt.Errorf("no valid image data or media URL found in webhook (type: %s)", mediaType)
	}

	// Dispatch to PP-OCRv6
	ocrReq, err := http.NewRequest("POST", targetURL, bytes.NewBuffer(reqBody))
	if err != nil {
		return "", fmt.Errorf("failed to create OCR request: %w", err)
	}
	ocrReq.Header.Set("Content-Type", "application/json")

	ocrClient := &http.Client{Timeout: 30 * time.Second}
	ocrResp, err := ocrClient.Do(ocrReq)
	if err != nil {
		return "", fmt.Errorf("PP-OCRv6 microservice unreachable at %s: %w", targetURL, err)
	}
	defer ocrResp.Body.Close()

	if ocrResp.StatusCode >= 300 {
		errBytes, _ := io.ReadAll(ocrResp.Body)
		return "", fmt.Errorf("PP-OCRv6 returned status %d: %s", ocrResp.StatusCode, string(errBytes))
	}

	var ocrData OCRResponse
	if err := json.NewDecoder(ocrResp.Body).Decode(&ocrData); err != nil {
		return "", fmt.Errorf("failed to parse OCR response JSON: %w", err)
	}

	return FormatOCRReply(ocrData), nil
}

// WhatsApp Markdown Formatters
func FormatStockReply(query string, items []PartItem) string {
	if len(items) == 0 {
		return fmt.Sprintf("🔍 *Stock Search:* No matching items found for `%s`.\nCheck part number or vehicle spelling.", query)
	}

	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("🔍 *STOCK LOOKUP: \"%s\"*\n", query))
	sb.WriteString("─────────────────────────────\n")

	for i, it := range items {
		sb.WriteString(fmt.Sprintf("*%d. %s* (%s)\n", i+1, it.PartName, it.Brand))
		sb.WriteString(fmt.Sprintf("   • *Part No:* `%s`\n", it.PartNumber))
		sb.WriteString(fmt.Sprintf("   • *Stock:* %.1f %s\n", it.StockOnHand, it.PrimaryUom))
		sb.WriteString(fmt.Sprintf("   • *Location:* 📍 *%s*\n", it.ShelfLocation))
		sb.WriteString(fmt.Sprintf("   • *Selling Price:* ₹%.2f (+%.1f%% GST)\n\n", it.SellingPrice, it.TaxPercent))
	}

	return strings.TrimSpace(sb.String())
}

func FormatVendorReply(query string, vendors []VendorItem) string {
	if len(vendors) == 0 {
		return fmt.Sprintf("🏢 *Vendor Search:* No registered vendor found matching `%s`.", query)
	}

	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("🏢 *VENDOR DIRECTORY: \"%s\"*\n", query))
	sb.WriteString("─────────────────────────────\n")

	for _, v := range vendors {
		sb.WriteString(fmt.Sprintf("• *%s* (%s)\n", v.VendorName, v.VendorType))
		sb.WriteString(fmt.Sprintf("  Contact: %s | 📱 %s\n", v.ContactName, v.MobileNumber))
		sb.WriteString(fmt.Sprintf("  GSTIN: `%s`\n\n", v.GSTIN))
	}

	return strings.TrimSpace(sb.String())
}

func FormatLowStockReply(items []LowStockItem) string {
	var sb strings.Builder
	sb.WriteString("🚨 *DAILY LOW-STOCK REORDER ALERT*\n")
	sb.WriteString("─────────────────────────────\n")
	sb.WriteString("The following fast-moving items are below safety stock:\n\n")

	for i, it := range items {
		sb.WriteString(fmt.Sprintf("*%d. %s*\n", i+1, it.PartName))
		sb.WriteString(fmt.Sprintf("   • Stock: %s (Min: %s)\n", it.Stock, it.MinThreshold))
		sb.WriteString(fmt.Sprintf("   • Supplier: %s (%s)\n", it.PreferredVendor, it.VendorContact))
		sb.WriteString(fmt.Sprintf("   • Reorder: *%s*\n\n", it.SuggestedOrder))
	}

	sb.WriteString("─────────────────────────────\n")
	sb.WriteString("Reply *PO 1* or *PO ALL* to auto-dispatch POs to vendors via WhatsApp.")
	return strings.TrimSpace(sb.String())
}

func FormatHelpReply() string {
	return `🤖 *AutoRox Parts & Inventory Bot (Pillar 2)*
─────────────────────────────
Available WhatsApp Commands:

• stock <part / car>: Search stock & shelf location
   Example: stock Creta oil filter
   Example: stock Swift brake pads

• part <number>: Exact part number lookup
   Example: part F002H235238F8

• vendor <name>: Lookup vendor contact & phone
   Example: vendor vikas

• lowstock: View daily low-stock reorder digest

• Snap Photo of Vendor Bill: Auto-inwarding & price leak detection!`
}

// ProcessCommand parses incoming WhatsApp text and generates the response
func (e *Engine) ProcessCommand(text string) string {
	clean := strings.TrimSpace(text)
	lower := strings.ToLower(clean)

	switch {
	case strings.HasPrefix(lower, "stock "):
		q := strings.TrimSpace(clean[6:])
		items, err := e.SearchStock(q)
		if err != nil {
			return fmt.Sprintf("⚠️ Database query error: %v", err)
		}
		return FormatStockReply(q, items)

	case strings.HasPrefix(lower, "part ") || strings.HasPrefix(lower, "find "):
		q := strings.TrimSpace(clean[5:])
		items, err := e.SearchStock(q)
		if err != nil {
			return fmt.Sprintf("⚠️ Database query error: %v", err)
		}
		return FormatStockReply(q, items)

	case strings.HasPrefix(lower, "vendor "):
		q := strings.TrimSpace(clean[7:])
		vendors, err := e.SearchVendor(q)
		if err != nil {
			return fmt.Sprintf("⚠️ Database query error: %v", err)
		}
		return FormatVendorReply(q, vendors)

	case lower == "lowstock" || lower == "reorder":
		items := e.GetLowStockItems()
		return FormatLowStockReply(items)

	case lower == "help" || lower == "hi" || lower == "hello":
		return FormatHelpReply()

	default:
		return "🤖 AutoRox Copilot received your message!\nType `help` to see stock lookup and shelf commands."
	}
}

// DispatchToWhatomate sends an asynchronous reply back to Whatomate
func (e *Engine) DispatchToWhatomate(contactID, replyText string) error {
	if e.config.WhatomateURL == "" || contactID == "" {
		return nil
	}

	targetURL := fmt.Sprintf("%s/api/contacts/%s/messages", strings.TrimRight(e.config.WhatomateURL, "/"), contactID)
	payload := map[string]any{
		"type": "text",
		"content": map[string]string{
			"body": replyText,
		},
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequest("POST", targetURL, bytes.NewBuffer(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if e.config.WhatomateKey != "" {
		req.Header.Set("X-API-Key", e.config.WhatomateKey)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("whatomate dispatch failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("whatomate returned status %d: %s", resp.StatusCode, string(respBody))
	}
	return nil
}

func main() {
	port := flag.Int("port", 8000, "Port for the HTTP webhook server")
	dbPath := flag.String("db", "../data/live/inventory.db", "Path to SQLite inventory.db")
	whatomateURL := flag.String("whatomate-url", "http://localhost:8090", "Whatomate WhatsApp Gateway URL")
	whatomateKey := flag.String("whatomate-key", "", "Whatomate API Key")
	ocrURL := flag.String("ocr-url", "http://localhost:8005", "URL to autorox-ocr microservice")
	flag.Parse()

	// Resolve absolute path to database
	absDBPath, err := filepath.Abs(*dbPath)
	if err != nil {
		absDBPath = *dbPath
	}

	// Environment variable fallback
	resolvedWhatomateURL := *whatomateURL
	if envURL := os.Getenv("WHATOMATE_URL"); envURL != "" {
		resolvedWhatomateURL = envURL
	}

	resolvedWhatomateKey := *whatomateKey
	if envKey := os.Getenv("WHATOMATE_KEY"); envKey != "" {
		resolvedWhatomateKey = envKey
	}
	if envKey := os.Getenv("WHATOMATE_API_KEY"); envKey != "" && resolvedWhatomateKey == "" {
		resolvedWhatomateKey = envKey
	}

	resolvedOCRURL := *ocrURL
	if envOCR := os.Getenv("OCR_URL"); envOCR != "" && *ocrURL == "http://localhost:8005" {
		resolvedOCRURL = envOCR
	}

	cfg := Config{
		Port:         *port,
		DBPath:       absDBPath,
		WhatomateURL: resolvedWhatomateURL,
		WhatomateKey: resolvedWhatomateKey,
		OCRURL:       resolvedOCRURL,
	}

	log.Printf("[AutoRox Engine] Starting Go Copilot Engine on :%d", cfg.Port)
	log.Printf("[AutoRox Engine] SQLite Database: %s", cfg.DBPath)
	log.Printf("[AutoRox Engine] PP-OCRv6 Microservice URL: %s", cfg.OCRURL)

	engine, err := NewEngine(cfg)
	if err != nil {
		log.Fatalf("[AutoRox Engine] Fatal initialization error: %v", err)
	}
	defer engine.db.Close()

	// HTTP Routes
	mux := http.NewServeMux()

	// Health Check
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"status":   "ok",
			"engine":   "go-autorox-copilot",
			"version":  "1.0.0",
			"ocr_url":  cfg.OCRURL,
			"uptime":   "healthy",
		})
	})

	// Direct REST Stock API
	mux.HandleFunc("/api/stock", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query().Get("q")
		items, err := engine.SearchStock(q)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(items)
	})

	// Direct REST Vendor API
	mux.HandleFunc("/api/vendor", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query().Get("q")
		vendors, err := engine.SearchVendor(q)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(vendors)
	})

	// Low Stock Digest API
	mux.HandleFunc("/api/lowstock", func(w http.ResponseWriter, r *http.Request) {
		items := engine.GetLowStockItems()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(items)
	})

	// Primary Whatomate Webhook (Handles Text Commands AND PP-OCRv6 Bill Photos)
	mux.HandleFunc("/webhook/whatomate", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		bodyBytes, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "Bad Request", http.StatusBadRequest)
			return
		}
		defer r.Body.Close()

		var payload WhatomateWebhookPayload
		if err := json.Unmarshal(bodyBytes, &payload); err != nil {
			http.Error(w, "Invalid JSON", http.StatusBadRequest)
			return
		}

		// 1. Event filter: Only process incoming WhatsApp messages (ignore message.sent, message.outgoing, etc.)
		if payload.Event != "" && payload.Event != "message.incoming" {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"status": "ignored", "event": payload.Event})
			return
		}

		// 2. Direction filter: Ignore outbound or echoed messages
		if strings.EqualFold(payload.Data.Direction, "outbound") {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"status": "ignored", "reason": "outbound_direction"})
			return
		}

		// 3. Deduplication: Suppress duplicate deliveries of the same message within a short window
		msgID := payload.Data.MessageID
		if msgID == "" {
			msgID = payload.MessageID
		}
		if msgID != "" {
			if _, loaded := processedMessageIDs.LoadOrStore(msgID, time.Now()); loaded {
				log.Printf("[Webhook] Duplicate message ID %s suppressed", msgID)
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(map[string]any{"status": "ignored", "reason": "duplicate_message_id"})
				return
			}
		}

		// 4. Anti-Echo Safeguard: Never process messages generated by AutoRox Copilot itself
		msgText := strings.TrimSpace(payload.GetMessageText())
		if strings.HasPrefix(msgText, "🤖 AutoRox") ||
			strings.HasPrefix(msgText, "🔍 *STOCK LOOKUP") ||
			strings.HasPrefix(msgText, "🔍 *Stock Search") ||
			strings.HasPrefix(msgText, "🚨 *DAILY LOW-STOCK") ||
			strings.HasPrefix(msgText, "🏢 *VENDOR DIRECTORY") ||
			strings.HasPrefix(msgText, "🏢 *Vendor Search") ||
			strings.HasPrefix(msgText, "⚠️ Unable to parse") ||
			strings.HasPrefix(msgText, "🤖 *AutoRox Parts") {
			log.Printf("[Webhook] Self-echo detected from sender %s; suppressed.", payload.GetSender())
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"status": "ignored", "reason": "self_echo_suppressed"})
			return
		}

		// 5. Empty payload check
		if msgText == "" && !payload.HasMedia() {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"status": "ignored", "reason": "empty_content"})
			return
		}

		start := time.Now()
		sender := payload.GetSender()
		var reply string

		if payload.HasMedia() {
			log.Printf("[Webhook] Media attachment detected from %s. Dispatching to PP-OCRv6...", sender)
			ocrReply, err := engine.FetchAndProcessOCR(&payload)
			if err != nil {
				log.Printf("[OCR Pipeline Error]: %v", err)
				reply = fmt.Sprintf("⚠️ Unable to parse invoice image via PP-OCRv6: %v\nPlease ensure the bill photo is clear.", err)
			} else {
				reply = ocrReply
			}
		} else {
			reply = engine.ProcessCommand(msgText)
			log.Printf("[Webhook] Sender: %s | Query: %q ➔ Processed in %v", sender, msgText, time.Since(start))
		}
		duration := time.Since(start)

		// Dispatch to Whatomate REST API if contact ID or sender is provided
		recipient := payload.GetContactID()
		if recipient == "" {
			recipient = sender
		}
		if recipient != "" && engine.config.WhatomateURL != "" {
			go func(rec, rep string) {
				if err := engine.DispatchToWhatomate(rec, rep); err != nil {
					log.Printf("[Whatomate Dispatch Error to %s]: %v", rec, err)
				} else {
					log.Printf("[Whatomate Dispatch] Successfully dispatched reply to %s", rec)
				}
			}(recipient, reply)
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"reply":        reply,
			"processed_ms": float64(duration.Microseconds()) / 1000.0,
		})
	})

	server := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Port),
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Printf("[AutoRox Engine] Ready for Whatomate webhooks at http://0.0.0.0:%d/webhook/whatomate", cfg.Port)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("[AutoRox Engine] Server error: %v", err)
	}
}
