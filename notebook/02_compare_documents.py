# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Compare Documents
# MAGIC
# MAGIC Parse a PowerPoint and a document using **`ai_parse_document()`**, then compare them
# MAGIC with **`ai_query()`** to generate an alignment report.
# MAGIC
# MAGIC **No library installs required** — everything runs as SQL functions on the SQL Warehouse.
# MAGIC
# MAGIC **Input:** `.pptx` and `.docx` files in the UC Volume
# MAGIC **Output:** Formatted alignment report + persisted to Delta table

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration
# MAGIC
# MAGIC Use the widgets at the top of the notebook to select your files and model.

# COMMAND ----------

dbutils.widgets.text("pptx_file", "/Volumes/lakedoom_demo_catalog/capital_markets_ai/document_comparison/quarterly_review.pptx", "PowerPoint File Path")
dbutils.widgets.text("doc_file", "/Volumes/lakedoom_demo_catalog/capital_markets_ai/document_comparison/earnings_summary.docx", "Document File Path")
dbutils.widgets.dropdown("model", "databricks-gemini-2-5-flash", [
    "databricks-gemini-2-5-flash",
    "databricks-gemini-2-5-pro",
    "databricks-meta-llama-3-3-70b-instruct",
    "databricks-claude-sonnet-4-6",
    "databricks-claude-opus-4-6",
], "AI Model")
dbutils.widgets.text("output_table", "lakedoom_demo_catalog.capital_markets_ai.document_comparisons", "Output Table")

PPTX_FILE = dbutils.widgets.get("pptx_file")
DOC_FILE = dbutils.widgets.get("doc_file")
MODEL = dbutils.widgets.get("model")
OUTPUT_TABLE = dbutils.widgets.get("output_table")

print(f"PowerPoint: {PPTX_FILE}")
print(f"Document:   {DOC_FILE}")
print(f"Model:      {MODEL}")
print(f"Output:     {OUTPUT_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Parse Both Documents with `ai_parse_document()`

# COMMAND ----------

parsed_df = spark.sql(f"""
SELECT
  'pptx' AS file_type,
  ai_parse_document(
    content, map('version', '2.0', 'descriptionElementTypes', '*')
  )::STRING AS parsed_text
FROM read_files('{PPTX_FILE}', format => 'binaryFile')

UNION ALL

SELECT
  'doc' AS file_type,
  ai_parse_document(
    content, map('version', '2.0', 'descriptionElementTypes', '*')
  )::STRING AS parsed_text
FROM read_files('{DOC_FILE}', format => 'binaryFile')
""")

parsed_rows = {row["file_type"]: row["parsed_text"] for row in parsed_df.collect()}
pptx_text = parsed_rows["pptx"]
doc_text = parsed_rows["doc"]

print(f"PowerPoint parsed: {len(pptx_text):,} characters")
print(f"Document parsed:   {len(doc_text):,} characters")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Preview Parsed Content

# COMMAND ----------

print("=" * 60)
print("POWERPOINT (first 800 chars)")
print("=" * 60)
print(pptx_text[:800])
print("\n")
print("=" * 60)
print("DOCUMENT (first 800 chars)")
print("=" * 60)
print(doc_text[:800])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: AI-Powered Comparison

# COMMAND ----------

comparison_prompt = f"""You are a document alignment analyst. Compare the following PowerPoint presentation and document.

=== POWERPOINT PRESENTATION ===
{pptx_text}

=== DOCUMENT ===
{doc_text}

Produce a structured analysis:

## Overall Similarity Score
Rate alignment 0-100% with explanation.

## Aligned Content
Key topics consistent between both. Cite specific slides and sections.

## Divergences Found
Information that differs. For each state what PowerPoint says vs Document says, severity (Minor/Moderate/Major), and impact.

## Content in PowerPoint Only
Information in the presentation but missing from the document.

## Content in Document Only
Information in the document but missing from the presentation.

## Recommendation
What needs updating to bring documents into full alignment.

Be specific with numbers, percentages, and exact claims."""

escaped = comparison_prompt.replace("'", "''")
report_df = spark.sql(f"SELECT ai_query('{MODEL}', '{escaped}') AS report")
report_text = report_df.collect()[0]["report"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Raw Markdown Output
# MAGIC
# MAGIC The AI comparison report in its raw markdown form — before any formatting is applied:

# COMMAND ----------

print(report_text)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Formatted Alignment Report

# COMMAND ----------

from IPython.display import display, Markdown

pptx_name = PPTX_FILE.split("/")[-1]
doc_name = DOC_FILE.split("/")[-1]

header = f"""---
### Document Alignment Report
**PowerPoint:** `{pptx_name}` ({len(pptx_text):,} chars) &nbsp;&nbsp; **vs** &nbsp;&nbsp; **Document:** `{doc_name}` ({len(doc_text):,} chars)

*Powered by `ai_parse_document()` + `ai_query()`*

---
"""

display(Markdown(header + report_text))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Save Report to Delta Table

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {OUTPUT_TABLE} (
  comparison_id STRING,
  pptx_file STRING,
  doc_file STRING,
  pptx_parsed_text STRING,
  doc_parsed_text STRING,
  comparison_report STRING,
  created_at TIMESTAMP
)
""")

from datetime import datetime
from pyspark.sql import Row

row = Row(
    comparison_id=f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    pptx_file=pptx_name,
    doc_file=doc_name,
    pptx_parsed_text=pptx_text,
    doc_parsed_text=doc_text,
    comparison_report=report_text,
    created_at=datetime.now()
)

spark.createDataFrame([row]).write.mode("append").saveAsTable(OUTPUT_TABLE)
print(f"Report saved to {OUTPUT_TABLE}")

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT comparison_id, pptx_file, doc_file,
# MAGIC        LENGTH(pptx_parsed_text) AS pptx_chars,
# MAGIC        LENGTH(doc_parsed_text) AS doc_chars,
# MAGIC        LEFT(comparison_report, 300) AS report_preview,
# MAGIC        created_at
# MAGIC FROM lakedoom_demo_catalog.capital_markets_ai.document_comparisons
# MAGIC ORDER BY created_at DESC

# COMMAND ----------

# MAGIC %md
# MAGIC **Next:** Run notebook `03_compare_at_scale` to compare entire document libraries.