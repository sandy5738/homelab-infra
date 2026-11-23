# ADR-0009: PP-OCRv6 GPU-Accelerated Edge OCR Pipeline for Vendor Invoices

## Status
**Accepted**

## Date
2026-11-21

## Context & Problem Statement
When garage storekeepers or mechanics receive physical vendor invoices from parts distributors (*Vikas Trade Links*, *Autoverse*, *Bosch*), manual entry into AutoRox causes data entry lag and margin leakage. Sending hundreds of multi-page invoices each month to commercial cloud Vision APIs (e.g., Google Cloud Vision, AWS Textract, OpenAI Vision) incurs recurring per-call fees and latency.

The Ubuntu home server (`sandy@enma`) is equipped with an **NVIDIA GeForce GTX 1050 Mobile (4GB VRAM, Driver 580+, CUDA 13.0)** and `nvidia-container-toolkit`. We evaluated local OCR engines to run directly on the edge GPU within the 4GB VRAM envelope.

---

## Technical Evaluation: PP-OCRv6 vs. EasyOCR vs. Cloud Vision

| Evaluation Metric | PP-OCRv6 (PaddleOCR) | EasyOCR (PyTorch) | Cloud Vision API |
| :--- | :---: | :---: | :---: |
| **VRAM Consumption** | **~650MB – 800MB** | ~1.1 GB – 1.4 GB | 0 MB (Remote) |
| **Inference Latency** | **~120ms – 180ms / page** | ~250ms – 400ms / page | 1,200ms – 3,500ms |
| **Angle Classification (`cls`)** | **Built-in (`use_angle_cls`)** | Manual pre-rotation | Auto-oriented |
| **Multi-Column Alignment** | **High (preserves tables)** | Moderate | High |
| **Recurring Monthly Cost** | **₹0.00** | **₹0.00** | ₹0.15 – ₹0.35 / bill |
| **Offline Privacy** | **100% On-Premise** | 100% On-Premise | Sent over Internet |
| **Hardware Fit (GTX 1050)** | **Ideal (< 20% VRAM used)** | Good | N/A |

### Why PP-OCRv6 Won Over EasyOCR:
1. **Built-in Text Direction / Angle Correction:** Workshop mechanics snap photos at awkward angles, handheld under poor bay lighting. PP-OCRv6's integrated angle classifier detects and rotates rotated invoice lines without requiring OpenCV deskewing heuristics.
2. **Tabular Part Number Preservation:** Invoices have dense tables (Part Number, Description, Qty, Rate, Tax). PP-OCRv6's detection model groups columns and lines with higher precision than EasyOCR.
3. **Ultra-Low Memory Footprint:** At ~700MB VRAM, PP-OCRv6 leaves over 3.2GB of free VRAM on the GTX 1050 Mobile, preventing out-of-memory (OOM) crashes during concurrent processing.

---

## Architectural Decision

1. **Dedicated Microservice (`autorox-ocr`) on Port 8005**:
   - Packaged in [Dockerfile.ocr](../../Dockerfile.ocr) with PaddlePaddle-GPU and PaddleOCR.
   - Initialized via [ocr_service.py](../../ocr_service.py) with `use_angle_cls=True`, `lang='en'`, and `use_gpu=True`.
   - Automatically detects CUDA via `paddle.device.is_compiled_with_cuda()`. If run on non-GPU dev machines, it falls back to CPU mode seamlessly.

2. **Docker Compose Device Reservation**:
   - In [docker-compose.yml](../../docker-compose.yml), `autorox-ocr` declares the NVIDIA device reservation:
     ```yaml
     deploy:
       resources:
         reservations:
           devices:
             - driver: nvidia
               count: all
               capabilities: [gpu]
     ```
   - Sets `NVIDIA_VISIBLE_DEVICES=all` and `NVIDIA_DRIVER_CAPABILITIES=compute,utility`.

3. **In-Flight Cross-Referencing & Margin Leakage Detection**:
   - `ocr_service.py` connects to the shared SQLite database (`data/live/inventory.db`) in read-only WAL mode.
   - As line items are extracted from bill images, the engine:
     1. Matches extracted part codes against 1,938 AutoRox master SKUs.
     2. Flags **Low Margin / Price Hike Alerts** if the vendor's invoiced unit rate exceeds historical thresholds or erodes the workshop margin below 15%.
     3. Prepares the AutoRox Step 2 Direct Inward CSV payload.

---

## Consequences

### Positive
- **Zero API Meter Costs:** Unlimited bill ingestion without third-party cloud vision meter charges.
- **Fast Turnaround:** Invoice text extraction completes in ~150ms on the GTX 1050 Mobile.
- **Data Privacy:** Confidential vendor purchase rates and GST invoices never leave the workshop's local server.
- **Clean Failure Domain:** If GPU memory is exhausted by a large batch, only `autorox-ocr` resets; the Go WhatsApp engine continues responding to mechanics uninterrupted.
