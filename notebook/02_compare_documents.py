# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Compare Documents
# MAGIC
# MAGIC Compare a PowerPoint presentation against a **Word doc**, **Excel file**, or **Delta table**
# MAGIC using `ai_parse_document()` + `ai_query()`.
# MAGIC
# MAGIC **No library installs required** — everything runs as SQL functions.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

dbutils.widgets.text("catalog", "ronguerrero", "Catalog")
dbutils.widgets.text("schema", "capital_markets_ai", "Schema")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOL = f"/Volumes/{CATALOG}/{SCHEMA}/document_comparison"
OUTPUT_TABLE = f"{CATALOG}.{SCHEMA}.document_comparisons"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

dbutils.widgets.text("pptx_file", f"{VOL}/quarterly_review.pptx", "1. PowerPoint File Path")

dbutils.widgets.dropdown("compare_to", "Word Document", [
    "Word Document",
    "Excel Spreadsheet",
    "Delta Table",
], "2. Compare To")

dbutils.widgets.text("docx_file", f"{VOL}/earnings_summary.docx", "3a. Word Document Path")
dbutils.widgets.text("xlsx_file", f"{VOL}/earnings_data.xlsx", "3b. Excel Spreadsheet Path")
dbutils.widgets.text("delta_table", f"{CATALOG}.{SCHEMA}.earnings_summary", "3c. Delta Table Name")

dbutils.widgets.dropdown("model", "databricks-meta-llama-3-3-70b-instruct", [
    "databricks-meta-llama-3-3-70b-instruct",
    "databricks-claude-sonnet-4-6",
    "databricks-claude-opus-4-6",
], "4. AI Model")

dbutils.widgets.text("output_table", OUTPUT_TABLE, "5. Output Table")

PPTX_FILE = dbutils.widgets.get("pptx_file")
COMPARE_TO = dbutils.widgets.get("compare_to")
MODEL = dbutils.widgets.get("model")
OUTPUT_TABLE = dbutils.widgets.get("output_table")

if COMPARE_TO == "Word Document":
    DOC_FILE = dbutils.widgets.get("docx_file")
elif COMPARE_TO == "Excel Spreadsheet":
    DOC_FILE = dbutils.widgets.get("xlsx_file")
else:
    DOC_FILE = None
DELTA_TABLE = dbutils.widgets.get("delta_table")

print(f"PowerPoint:  {PPTX_FILE}")
print(f"Compare To:  {COMPARE_TO}")
if COMPARE_TO == "Delta Table":
    print(f"Delta Table: {DELTA_TABLE}")
else:
    print(f"File:        {DOC_FILE}")
print(f"Model:       {MODEL}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Parse the PowerPoint

# COMMAND ----------

pptx_parsed = spark.sql(f"""
SELECT ai_parse_document(
    content, map('version', '2.0', 'descriptionElementTypes', '*')
)::STRING AS parsed
FROM read_files('{PPTX_FILE}', format => 'binaryFile')
""").collect()[0]["parsed"]

print(f"PowerPoint parsed: {len(pptx_parsed):,} characters")
print(pptx_parsed[:500])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Parse the Comparison Target

# COMMAND ----------

if COMPARE_TO == "Word Document":
    doc_parsed = spark.sql(f"""
    SELECT ai_parse_document(
        content, map('version', '2.0', 'descriptionElementTypes', '*')
    )::STRING AS parsed
    FROM read_files('{DOC_FILE}', format => 'binaryFile')
    """).collect()[0]["parsed"]
    doc_label = DOC_FILE.split("/")[-1]

elif COMPARE_TO == "Excel Spreadsheet":
    # Native Databricks Excel reader
    sheets = (spark.read.format("excel")
              .option("operation", "listSheets")
              .load(DOC_FILE).collect())
    md_parts = [f"# Excel Spreadsheet: {DOC_FILE.split('/')[-1]}\n"]
    for sheet in sheets:
        sheet_name = sheet["sheetName"]
        df = (spark.read.format("excel")
              .option("headerRows", 1)
              .option("dataAddress", sheet_name)
              .load(DOC_FILE))
        md_parts.append(f"## Sheet: {sheet_name}\n")
        rows = df.collect()
        if not rows:
            md_parts.append("(empty sheet)\n"); continue
        headers = df.columns
        md_parts.append("| " + " | ".join(headers) + " |")
        md_parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            vals = [str(row[c]) if row[c] is not None else "" for c in headers]
            if any(v for v in vals):
                md_parts.append("| " + " | ".join(vals) + " |")
        md_parts.append("")
    doc_parsed = "\n".join(md_parts)
    doc_label = DOC_FILE.split("/")[-1]

elif COMPARE_TO == "Delta Table":
    rows = spark.sql(f"SELECT * FROM {DELTA_TABLE}").collect()
    columns = spark.sql(f"SELECT * FROM {DELTA_TABLE} LIMIT 1").columns
    md_parts = [f"# Delta Table: {DELTA_TABLE}\n"]
    md_parts.append("| " + " | ".join(columns) + " |")
    md_parts.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for row in rows:
        vals = [str(row[c]) if row[c] is not None else "" for c in columns]
        md_parts.append("| " + " | ".join(vals) + " |")
    md_parts.append("\n## Data Summary by Category\n")
    categories = spark.sql(f"SELECT DISTINCT category FROM {DELTA_TABLE} ORDER BY category").collect()
    for cat_row in categories:
        cat = cat_row["category"]
        md_parts.append(f"\n### {cat}\n")
        cat_rows = spark.sql(f"SELECT metric, value, comparison, change, notes FROM {DELTA_TABLE} WHERE category = '{cat}'").collect()
        for r in cat_rows:
            line = f"- **{r['metric']}**: {r['value']}"
            if r['change']: line += f" ({r['change']})"
            if r['comparison']: line += f" — vs {r['comparison']}"
            if r['notes']: line += f" [{r['notes']}]"
            md_parts.append(line)
    doc_parsed = "\n".join(md_parts)
    doc_label = DELTA_TABLE

print(f"Comparison target ({COMPARE_TO}): {len(doc_parsed):,} characters")
print(doc_parsed[:500])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Raw Markdown Output

# COMMAND ----------

comparison_prompt = f"""You are a document alignment analyst. Compare the following PowerPoint presentation against the {COMPARE_TO.lower()}.

IMPORTANT: Your response MUST use proper markdown formatting with ## headings, bullet lists with -, and **bold** text.

=== POWERPOINT PRESENTATION ===
{pptx_parsed}

=== {COMPARE_TO.upper()} ===
{doc_parsed}

Respond in this EXACT markdown format:

## Overall Similarity Score

**Score: X%** — [1-2 sentence explanation]

## Aligned Content

- **[Topic 1]** — [PowerPoint slide X] matches [{COMPARE_TO} section/sheet/row]. [Detail]

## Divergences Found

- **[Divergence 1]**
  - PowerPoint says: [exact claim]
  - {COMPARE_TO} says: [exact claim]
  - Severity: **Major/Moderate/Minor**
  - Impact: [explanation]

## Content in PowerPoint Only

- [Items not in the {COMPARE_TO.lower()}]

## Content in {COMPARE_TO} Only

- [Items not in the PowerPoint]

## Recommendation

- [Specific actions]

Be precise with numbers, percentages, and exact claims."""

escaped = comparison_prompt.replace("'", "''")
report_text = spark.sql(f"SELECT ai_query('{MODEL}', '{escaped}') AS report").collect()[0]["report"]

print(report_text)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Formatted Alignment Report

# COMMAND ----------

from IPython.display import display, Markdown

pptx_name = PPTX_FILE.split("/")[-1]

header = f"""---
### Document Alignment Report

**PowerPoint:** `{pptx_name}` ({len(pptx_parsed):,} chars) &nbsp;&nbsp; **vs** &nbsp;&nbsp; **{COMPARE_TO}:** `{doc_label}` ({len(doc_parsed):,} chars)

**Model:** `{MODEL}`

---
"""

display(Markdown(header + report_text))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Save Report to Delta Table

# COMMAND ----------

from datetime import datetime
from pyspark.sql import Row

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {OUTPUT_TABLE} (
  comparison_id STRING,
  pptx_file STRING,
  compare_to_type STRING,
  compare_to_source STRING,
  pptx_parsed_text STRING,
  doc_parsed_text STRING,
  model STRING,
  comparison_report STRING,
  created_at TIMESTAMP
)
""")

row = Row(
    comparison_id=f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    pptx_file=pptx_name,
    compare_to_type=COMPARE_TO,
    compare_to_source=doc_label,
    pptx_parsed_text=pptx_parsed,
    doc_parsed_text=doc_parsed,
    model=MODEL,
    comparison_report=report_text,
    created_at=datetime.now()
)

spark.createDataFrame([row]).write.mode("append").saveAsTable(OUTPUT_TABLE)
print(f"Report saved to {OUTPUT_TABLE}")

# COMMAND ----------

display(spark.sql(f"""SELECT comparison_id, pptx_file, compare_to_type, compare_to_source, model,
       LEFT(comparison_report, 200) AS report_preview, created_at
FROM {OUTPUT_TABLE}
ORDER BY created_at DESC"""))

# COMMAND ----------

# MAGIC %md
# MAGIC **Next:** Run `03_compare_at_scale` to batch compare multiple document pairs.
