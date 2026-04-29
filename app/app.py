"""Document Comparator v4 — ai_parse_document() + ai_query() with user-selectable model."""

import io
import json
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Document Comparator", version="4.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

AVAILABLE_MODELS = [
    {"id": "databricks-gemini-2-5-flash", "name": "Gemini 2.5 Flash", "provider": "Google"},
    {"id": "databricks-meta-llama-3-3-70b-instruct", "name": "Llama 3.3 70B", "provider": "Meta"},
    {"id": "databricks-claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "Anthropic"},
    {"id": "databricks-claude-opus-4-6", "name": "Claude Opus 4.6", "provider": "Anthropic"},
    {"id": "databricks-gemini-2-5-pro", "name": "Gemini 2.5 Pro", "provider": "Google"},
]

CATALOG = os.environ.get("CATALOG_NAME", "")
SCHEMA = os.environ.get("SCHEMA_NAME", "")
VOLUME = os.environ.get("VOLUME_NAME", "")
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")

_ws_client = None

def get_ws():
    global _ws_client
    if _ws_client is None:
        from databricks.sdk import WorkspaceClient
        _ws_client = WorkspaceClient()
    return _ws_client


# ── SQL Execution (async polling) ────────────────────────────

def run_sql(statement: str) -> list[dict]:
    """Execute SQL on the warehouse with async polling."""
    w = get_ws()
    from databricks.sdk.service.sql import StatementState

    resp = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=statement,
        wait_timeout="0s"
    )
    statement_id = resp.statement_id

    max_wait = 600
    elapsed = 0
    poll_interval = 2

    while elapsed < max_wait:
        status = w.statement_execution.get_statement(statement_id)
        if status.status.state == StatementState.SUCCEEDED:
            if not status.result or not status.result.data_array:
                return []
            columns = [col.name for col in status.manifest.schema.columns]
            return [dict(zip(columns, row)) for row in status.result.data_array]
        if status.status.state in (StatementState.FAILED, StatementState.CANCELED, StatementState.CLOSED):
            error_msg = status.status.error.message if status.status.error else "Unknown SQL error"
            raise RuntimeError(f"SQL failed: {error_msg}")
        time.sleep(poll_interval)
        elapsed += poll_interval
        if elapsed > 30:
            poll_interval = 5

    raise RuntimeError(f"SQL query timed out after {max_wait}s")


# ── Volume Upload / Cleanup ──────────────────────────────────

async def upload_to_volume(filename: str, content: bytes) -> str:
    """Upload file to UC Volume."""
    w = get_ws()
    safe_name = f"{uuid4().hex[:8]}_{filename.replace(' ', '_')}"
    file_path = f"{VOLUME_PATH}/{safe_name}"
    try:
        w.files.upload(file_path, io.BytesIO(content), overwrite=True)
        logger.info(f"Uploaded {len(content)} bytes to {file_path}")
        return file_path
    except Exception as e:
        if "NOT_FOUND" in str(e) or "RESOURCE_DOES_NOT_EXIST" in str(e):
            try:
                run_sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")
            except:
                pass
            w.files.upload(file_path, io.BytesIO(content), overwrite=True)
            return file_path
        raise


def cleanup_volume_file(path: str):
    try:
        get_ws().files.delete(path)
    except Exception as e:
        logger.warning(f"Cleanup failed for {path}: {e}")


# ── Single SQL: parse both + compare in one query ────────────

COMPARISON_PROMPT = """You are a document alignment analyst. Compare the two documents below.

IMPORTANT: Your response MUST use proper markdown formatting with ## headings, bullet lists with -, and **bold** text.

=== POWERPOINT ===
{pptx}

=== DOCUMENT ===
{doc}

Respond in this EXACT markdown format:

## Overall Similarity Score

**Score: X%** — [1-2 sentence explanation]

## Aligned Content

- **[Topic 1]** — [PowerPoint slide X] matches [Document section Y]. [Detail]
- **[Topic 2]** — [Detail with specific numbers]
- [Continue for all aligned topics]

## Divergences Found

- **[Divergence 1]**
  - PowerPoint says: [exact claim]
  - Document says: [exact claim]
  - Severity: **Major/Moderate/Minor**
  - Impact: [explanation]
- **[Divergence 2]**
  - [Same format]

## Content in PowerPoint Only

- [Item not found in the document]
- [Item not found in the document]

## Content in Document Only

- [Item not found in the PowerPoint]
- [Item not found in the PowerPoint]

## Recommendation

- [Specific action 1]
- [Specific action 2]

Be precise with numbers, percentages, and exact claims. Do not generalize."""

async def parse_and_compare(pptx_path: str, doc_path: str, model_id: str) -> dict:
    """Parse both documents and compare in a single SQL query."""
    escaped_pptx = pptx_path.replace("'", "''")
    escaped_doc = doc_path.replace("'", "''")

    sql = f"""
    WITH pptx_parsed AS (
      SELECT ai_parse_document(
        content, map('version', '2.0', 'descriptionElementTypes', '*')
      )::STRING AS content
      FROM read_files('{escaped_pptx}', format => 'binaryFile')
    ),
    doc_parsed AS (
      SELECT ai_parse_document(
        content, map('version', '2.0', 'descriptionElementTypes', '*')
      )::STRING AS content
      FROM read_files('{escaped_doc}', format => 'binaryFile')
    )
    SELECT
      pptx.content AS pptx_text,
      doc.content AS doc_text,
      ai_query(
        '{model_id}',
        CONCAT(
          'You are a document alignment analyst. Compare the two documents below.\\n\\n',
          'IMPORTANT: Your response MUST use proper markdown formatting with ## headings, bullet lists with -, and **bold** text.\\n\\n',
          '=== POWERPOINT ===\\n', pptx.content, '\\n\\n',
          '=== DOCUMENT ===\\n', doc.content, '\\n\\n',
          'Respond in this EXACT markdown format:\\n\\n',
          '## Overall Similarity Score\\n\\n',
          '**Score: X%** — [explanation]\\n\\n',
          '## Aligned Content\\n\\n',
          '- **[Topic]** — [slide X] matches [section Y]. [detail with numbers]\\n',
          '- [continue for all aligned topics]\\n\\n',
          '## Divergences Found\\n\\n',
          '- **[Divergence]**\\n',
          '  - PowerPoint says: [exact claim]\\n',
          '  - Document says: [exact claim]\\n',
          '  - Severity: **Major/Moderate/Minor**\\n',
          '  - Impact: [explanation]\\n\\n',
          '## Content in PowerPoint Only\\n\\n',
          '- [items not in document]\\n\\n',
          '## Content in Document Only\\n\\n',
          '- [items not in PowerPoint]\\n\\n',
          '## Recommendation\\n\\n',
          '- [specific actions]\\n\\n',
          'Be precise with numbers and exact claims. Do not generalize.'
        )
      ) AS report
    FROM pptx_parsed pptx
    CROSS JOIN doc_parsed doc
    """

    rows = run_sql(sql)
    if not rows:
        raise RuntimeError("Query returned no results")

    row = rows[0]
    return {
        "pptx_text": row.get("pptx_text", ""),
        "doc_text": row.get("doc_text", ""),
        "report": row.get("report", ""),
    }


# ── API Routes ───────────────────────────────────────────────

@app.get("/api/models")
def list_models():
    return {"models": AVAILABLE_MODELS}


@app.post("/api/parse")
async def parse_file(file: UploadFile = File(...)):
    """Upload and parse a single file using ai_parse_document()."""
    content = await file.read()
    filename = file.filename or "upload"

    if not filename.endswith((".pptx", ".docx", ".pdf", ".txt")):
        return JSONResponse(status_code=400, content={"error": "Unsupported file type. Use .pptx, .docx, .pdf, or .txt"})

    vol_path = await upload_to_volume(filename, content)
    try:
        parsed = await parse_document(vol_path)
        return {"filename": filename, "parsed_content": parsed, "char_count": len(parsed)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        cleanup_volume_file(vol_path)


@app.post("/api/compare")
async def compare_documents(
    pptx_file: UploadFile = File(...),
    doc_file: UploadFile = File(...),
    model: str = Form("databricks-gemini-2-5-flash")
):
    """Compare documents: single SQL query with ai_parse_document() + ai_query()."""
    pptx_content = await pptx_file.read()
    doc_content = await doc_file.read()

    pptx_name = pptx_file.filename or "presentation.pptx"
    doc_name = doc_file.filename or "document.docx"

    if not pptx_name.endswith(".pptx"):
        return JSONResponse(status_code=400, content={"error": "First file must be a .pptx PowerPoint file"})
    if not doc_name.endswith((".docx", ".pdf", ".txt")):
        return JSONResponse(status_code=400, content={"error": "Second file must be .docx, .pdf, or .txt"})

    pptx_path = None
    doc_path = None

    try:
        # Upload both to volume
        pptx_path = await upload_to_volume(pptx_name, pptx_content)
        doc_path = await upload_to_volume(doc_name, doc_content)

        # Single SQL: parse both + compare
        logger.info(f"Running single-query parse+compare with {model}...")
        result = await parse_and_compare(pptx_path, doc_path, model)
        logger.info(f"Done: pptx={len(result['pptx_text'])} chars, doc={len(result['doc_text'])} chars, report={len(result['report'])} chars")

        pptx_text = result["pptx_text"]
        doc_text = result["doc_text"]
        report = result["report"]

        # Section previews
        def extract_sections(text, max_sections=10):
            sections = []
            current_title = "Content"
            current_content = []
            for line in text.split("\n"):
                s = line.strip()
                if s and (s.startswith("#") or (s.isupper() and len(s) < 80)):
                    if current_content:
                        sections.append({"title": current_title, "preview": " ".join(current_content)[:200]})
                    current_title = s.lstrip("#").strip()
                    current_content = []
                elif s:
                    current_content.append(s)
            if current_content:
                sections.append({"title": current_title, "preview": " ".join(current_content)[:200]})
            return sections[:max_sections]

        return {
            "pptx_file": pptx_name,
            "doc_file": doc_name,
            "model": model,
            "pptx_sections": len(extract_sections(pptx_text)),
            "doc_sections": len(extract_sections(doc_text)),
            "pptx_content": extract_sections(pptx_text),
            "doc_content": extract_sections(doc_text),
            "pptx_markdown": pptx_text,
            "doc_markdown": doc_text,
            "comparison_report": report
        }

    except Exception as e:
        logger.error(f"Comparison failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if pptx_path:
            cleanup_volume_file(pptx_path)
        if doc_path:
            cleanup_volume_file(doc_path)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "4.0", "engine": "ai_parse_document + ai_query", "warehouse": WAREHOUSE_ID}


# ── Static Files & SPA ──────────────────────────────────────

dist = Path(__file__).parent / "frontend" / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(dist / "index.html")
else:
    @app.get("/")
    def root():
        return {"message": "Document Comparator API v4.0 (ai_parse_document + ai_query). POST to /api/compare."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
