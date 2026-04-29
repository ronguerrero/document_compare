# Document Comparator

AI-powered document comparison using Databricks AI Functions. Upload a PowerPoint presentation and a document, and get a detailed alignment report — similarity score, matched content, divergences, and recommendations.

## What It Does

Takes two documents (e.g., a quarterly earnings deck and its written summary), parses both using `ai_parse_document()`, and uses `ai_query()` with a user-selected foundation model to produce a structured comparison report.

**Example output:**
- Overall Similarity Score: 82%
- 12 aligned topics with slide/section citations
- 3 divergences (1 Major, 2 Minor) with specific numbers that differ
- Content in presentation but missing from document
- Content in document but missing from presentation
- Actionable recommendations to bring them into alignment

## Two Solutions

### Databricks App

A full-stack web application with drag-and-drop file upload and a model selector.

- **Frontend:** React + Tailwind CSS + Vite
- **Backend:** Python FastAPI
- **Parsing:** `ai_parse_document()` via SQL Warehouse — handles PPTX, DOCX, PDF, images
- **Comparison:** `ai_query()` with user-selected model — Llama, Claude, GPT, Gemini
- **Hosting:** Databricks Apps — no external infrastructure
- **Auth:** Workspace OAuth — no separate credentials

### Notebooks

Three notebooks for use directly in the Databricks workspace:

| Notebook | Purpose |
|----------|---------|
| `01_generate_sample_documents` | Creates sample .pptx and .docx files in a UC Volume |
| `02_compare_documents` | Compares a single document pair with formatted markdown report |
| `03_compare_at_scale` | Batch compares multiple document pairs with persist to Delta |

Notebooks use `ai_parse_document()` + `ai_query()` — pure SQL, no library installs required for the comparison pipeline. Notebook 02 includes parameterized widgets for file paths, model selection, and output table.

## Key Databricks Features Used

| Feature | How It's Used |
|---------|--------------|
| `ai_parse_document()` | Converts raw PDF/PPTX/DOCX bytes into structured text |
| `ai_query()` | Sends comparison prompt to a foundation model |
| Foundation Model APIs | Llama 3.3 70B, Claude Sonnet/Opus, GPT-5.4, Gemini 2.5 |
| Unity Catalog Volumes | Temporary storage for uploaded files |
| Delta Lake | Persists comparison reports with full history |
| Databricks Apps | Hosts the web application |
| Serverless SQL Warehouse | Executes AI functions with zero infrastructure management |

## Supported File Types

| Format | Parsing Method |
|--------|---------------|
| PowerPoint (.pptx) | `ai_parse_document()` — extracts slides, text, tables, layout |
| Word (.docx) | `ai_parse_document()` — extracts headings, paragraphs, lists, tables |
| PDF (.pdf) | `ai_parse_document()` — includes OCR for scanned documents |
| Plain text (.txt) | Direct text read |

## Available Models

The app and notebooks support any foundation model available through Databricks Model Serving:

| Model | Provider |
|-------|----------|
| Llama 3.3 70B | Meta |
| Claude Sonnet 4.6 | Anthropic |
| Claude Opus 4.6 | Anthropic |
| GPT-5.4 | OpenAI |
| GPT-5.4 Mini | OpenAI |
| Gemini 2.5 Pro | Google |
| Gemini 2.5 Flash | Google |

## Project Structure

```
document-comparator/
├── README.md               # This file
├── DEPLOY.md               # Step-by-step deployment guide
├── app/
│   ├── app.py              # FastAPI backend
│   ├── app.yaml            # Databricks App configuration
│   ├── requirements.txt    # Python dependencies
│   ├── .gitignore
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx     # React UI with model selector
│       │   ├── main.tsx    # Entry point
│       │   └── index.css   # Tailwind styles
│       ├── dist/           # Production build output
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── tailwind.config.js
│       └── postcss.config.js
└── notebook/
    ├── 01_generate_sample_documents.py
    ├── 02_compare_documents.py
    └── 03_compare_at_scale.py
```

## Quick Start

### App

See [DEPLOY.md](DEPLOY.md) for full deployment instructions. Summary:

```bash
# Build frontend
cd app/frontend && npm install && npm run build && cd ../..

# Sync to workspace
databricks sync app /Workspace/Users/<email>/document-comparator --profile=<profile> \
  --exclude "node_modules,.venv,__pycache__,.git"

# Deploy
databricks apps deploy document-comparator \
  --source-code-path /Workspace/Users/<email>/document-comparator \
  --profile=<profile>
```

### Notebooks

```bash
# Upload notebooks
for nb in 01_generate_sample_documents 02_compare_documents 03_compare_at_scale; do
  databricks workspace import /Users/<email>/document_comparator/${nb} \
    --profile=<profile> --language=PYTHON --format=SOURCE \
    --file=notebook/${nb}.py --overwrite
done
```

Run in order: 01 (generate sample files) → 02 (compare a pair) → 03 (compare at scale).

## Configuration

All configuration is externalized — no hardcoded values in the app code.

### App (app.yaml)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABRICKS_WAREHOUSE_ID` | SQL Warehouse for ai_parse_document/ai_query | Bound via `valueFrom: sql-warehouse` |
| `CATALOG_NAME` | Unity Catalog catalog | `my_catalog` |
| `SCHEMA_NAME` | Schema within catalog | `document_intelligence` |
| `VOLUME_NAME` | Volume for temp file uploads | `document_comparison_uploads` |

### Notebooks (widgets)

Notebook 02 uses Databricks widgets for runtime configuration:

| Widget | Description |
|--------|-------------|
| PowerPoint File Path | UC Volume path to .pptx file |
| Document File Path | UC Volume path to .docx file |
| AI Model | Dropdown: Llama, Claude, GPT |
| Output Table | Delta table for persisting reports |

## Requirements

- Databricks workspace with Unity Catalog
- Serverless SQL Warehouse (or Pro/Classic)
- Foundation Model APIs enabled
- Databricks Apps enabled (for the web app)
- Databricks CLI v0.200+ (for deployment)
- Node.js 18+ (for building the frontend)
