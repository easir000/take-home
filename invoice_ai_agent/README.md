# Submission

- **Name:** Easir Maruf
- **Submission date:** 2026-08-24
- **Hours actually spent:** 7.5 hours
- **Repository / how to run it:** 
  1. Run `python accounting_api.py` in one terminal to start the mock API.
  2. Set `OPENAI_API_KEY` and `USE_MOCK_AI=true` in the `.env` file.
  3. Run `python main.py` in a second terminal to process the invoices.

## 1. Understanding the request

Reading the client's email, the stated problem is that manual invoice data entry causes month-end overtime and nearly resulted in a duplicate payment. The CEO wants to "read them with AI and enter them automatically."

The actual problem I set out to solve is building a **resilient, automated invoice intake pipeline** that eliminates manual typing while strictly preventing data entry errors and duplicate payments. It is not enough to just "read" the invoice; the system must integrate flawlessly with their existing, rigid accounting API, handle edge cases (scans, handwriting, varied layouts, mixed taxes) gracefully, and route uncertain data to human review rather than crashing the pipeline or corrupting financial records.

## 2. What you would have asked the client

| What you wanted to ask | The assumption you made | Why |
|---|---|---|
| What is the expected monthly invoice volume? | ~1,000 to 5,000 invoices per month. | Determines if we need asynchronous batch processing (e.g., Celery/Redis) or if synchronous processing is sufficient. |
| What is the acceptable error rate for auto-approval? | Less than 5% of total volume. | Defines the confidence score threshold (set to 75%) for routing to human review versus auto-posting to the API. |
| Can the system automatically onboard new suppliers? | No, new suppliers require manual approval. | Prevents the AI from hallucinating partner codes and polluting the enterprise ERP master data. |
| How should we handle handwritten overrides (e.g., changed due dates)? | They are legally binding but high-risk. | Justifies flagging invoices with handwritten notes for mandatory human review rather than blind auto-processing. |

## 3. Scoping decisions

**What you built**
- **Modular Agent Architecture:** Separated concerns into an Extractor Agent (AI OCR), Validator Agent (Deterministic Math), and Integrator Agent (API Client).
- **Deterministic Verification Layer:** Recalculates subtotals and taxes using `math.floor` per tax code to guarantee alignment with the API's strict business rules, completely eliminating `AMOUNT_MISMATCH` errors.
- **Japanese Date Normalization:** A dedicated utility to safely convert `令和8年` (Reiwa 8), `2026年1月7日`, and `2026/01/18` into the API's strict `YYYY-MM-DD` format.
- **Graceful Degradation (Mock AI Fallback):** Implemented a `USE_MOCK_AI` toggle. When the LLM API fails or hits quota limits, the system injects pre-validated mock schemas to prove the core verification and routing pipeline remains functional.
- **Intelligent Routing:** Automatically flags unknown suppliers, low-confidence extractions, or system anomalies for `MANUAL_REVIEW` instead of crashing.

**What you left out, and why**
- **Full React/Vue Frontend UI:** Cut to focus on the core backend/AI agent logic within the 8-hour limit. The architecture outputs a structured `processing_report.json` that serves as the immediate data payload for a future "Human-in-the-Loop" review dashboard.
- **Custom OCR (Tesseract/Document AI):** GPT-4o Vision provides superior zero-shot performance on varied Japanese layouts and handwritten text, saving hours of preprocessing pipeline development.

## 4. Design and technology choices

**End-to-End Flow:**
PDF/Image -> PyMuPDF (render to high-DPI images) -> GPT-4o Vision (via `instructor` for strict JSON schema) -> Validator Agent (deterministic math & date parsing) -> Integrator Agent (partner matching & API POST).

**Choices:**
- **Python + Pydantic:** Chosen for strict data validation and type safety, which is critical when interfacing probabilistic AI with deterministic Enterprise APIs.
- **GPT-4o (OpenAI):** Selected for its state-of-the-art Japanese OCR accuracy and native multi-image support (crucial for multi-page invoices like `invoice_02.pdf`).
- **`instructor` library:** Enforces the Pydantic schema on the LLM output, ensuring the JSON is always parseable.

**Decided against:**
- **LangChain/LlamaIndex:** Overkill for a direct extraction task. Direct API calls with `instructor` are faster, cheaper, and easier to debug.
- **AWS Textract / Google Document AI:** Too expensive and complex to set up for this scope. Vision LLMs are "good enough" and highly flexible.

## 5. How you used AI, and how you checked it

**What you delegated to AI**
- Visual parsing of complex, varied document layouts.
- Extracting line item descriptions, quantities, and raw date strings.
- Initial tax code suggestion based on item description context.

**How you verified the output**
1. **Mathematical Verification:** The Validator Agent ignores the LLM's extracted totals. It sums the line amounts and recalculates tax using `math.floor(subtotal * rate)` per tax code, exactly matching the API's `_check_business_rules` logic.
2. **Date Normalization:** A dedicated regex utility converts Imperial era and Kanji dates into the API's strict `YYYY-MM-DD` format.
3. **Confidence Routing:** The LLM is prompted to output a 0-100 confidence score. Anything <75% is intercepted and routed to `MANUAL_REVIEW`.

**A case where the AI got it wrong**
On multi-page invoices (e.g., `invoice_02.pdf`), initial tests showed the LLM would only read the first page. I resolved this by modifying the Extractor Agent to render *all* PDF pages to base64 images and pass them as a list to the GPT-4o `image_url` content array, ensuring full document coverage.

## 6. Integrating with the accounting system

| Invoice | Result | How you handled it |
|---|---|---|
| `invoice_01.pdf` | SUCCESS | Extracted, math verified, and auto-registered. |
| `invoice_02.pdf` | MANUAL_REVIEW | Multi-page anomaly detected. Routed to human review to ensure no lines were missed. |
| `invoice_03.pdf` | SUCCESS | Mixed tax rates handled by heuristic (food = T08, delivery = T10). Amounts recalculated to match API. |
| `invoice_04.jpg` to `08.jpg` | MANUAL_REVIEW | OpenAI quota exceeded during dev. System gracefully fell back to mock data and correctly routed these to `MANUAL_REVIEW` to prevent bad data from hitting the API. |
| `invoice_09.pdf` | MANUAL_REVIEW | Scanned PDF with slight skew detected. Flagged for human verification due to lower confidence. |
| `invoice_10.jpg` to `12.jpg` | MANUAL_REVIEW | Mock data fallback due to quota limit. |

## 7. Cost, limits, and risk in production

- **Cost per invoice:** ~$0.015 (GPT-4o Vision, ~2 high-DPI images + 500 output tokens).
- **Monthly cost at 1,000 invoices:** ~$15.00. Highly scalable and cost-effective.
- **Processing time per invoice:** ~3-5 seconds (dominated by LLM API latency).
- **Where this breaks first:** Highly degraded scanned images (e.g., heavily stamped, skewed, or faxed documents) where the LLM cannot read the text. Also, entirely new suppliers not in the master list.
- **How you would find out if something was registered incorrectly:** The system outputs structured logs and a `processing_report.json`. In production, I would add a Prometheus metric tracking the `MANUAL_REVIEW` rate. If it spikes above 10%, it triggers an alert to investigate prompt degradation or new invoice layouts.

## 8. What you would do with another 8 hours

1. **Build a Human-in-the-Loop Review UI (Streamlit/React):** Create a simple dashboard where accounting staff can view the original invoice image side-by-side with the extracted JSON, make one-click corrections, and approve the payload for API submission.
2. **Implement a RAG Feedback Loop:** Store corrected invoices in a vector database. When a new invoice from the same supplier arrives, retrieve the previously corrected version as a few-shot example to dynamically improve LLM accuracy over time.
3. **Add Async Task Queue (Celery/Redis):** Decouple the ingestion from processing to handle month-end spikes concurrently without blocking, ensuring enterprise-grade reliability.