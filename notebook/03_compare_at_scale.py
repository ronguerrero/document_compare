# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Compare Documents at Scale
# MAGIC
# MAGIC Batch compare a PowerPoint against multiple targets (Word, Excel, Delta table) in one run.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

dbutils.widgets.text("catalog", "ronguerrero", "Catalog")
dbutils.widgets.text("schema", "capital_markets_ai", "Schema")
dbutils.widgets.dropdown("model", "databricks-meta-llama-3-3-70b-instruct", [
    "databricks-meta-llama-3-3-70b-instruct",
    "databricks-claude-sonnet-4-6",
    "databricks-claude-opus-4-6",
], "AI Model")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
MODEL = dbutils.widgets.get("model")
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/document_comparison"
OUTPUT_TABLE = f"{CATALOG}.{SCHEMA}.document_comparisons"

spark.sql(f"USE CATALOG {CATALOG}")

print(f"Catalog:  {CATALOG}")
print(f"Schema:   {SCHEMA}")
print(f"Volume:   {VOLUME_PATH}")
print(f"Model:    {MODEL}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Inventory All Documents

# COMMAND ----------

display(spark.sql(f"""SELECT
  regexp_extract(path, '([^/]+)$', 1) AS filename,
  CASE
    WHEN path LIKE '%.pptx' THEN 'powerpoint'
    WHEN path LIKE '%.docx' THEN 'word'
    WHEN path LIKE '%.xlsx' THEN 'excel'
    WHEN path LIKE '%.pdf' THEN 'pdf'
    ELSE 'other'
  END AS file_type,
  length(content) AS file_size_bytes
FROM read_files('{VOLUME_PATH}/', format => 'binaryFile')
ORDER BY file_type, filename"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Parse All Files

# COMMAND ----------

# Parse pptx and docx with ai_parse_document (xlsx not supported)
_parsed_sql = spark.sql(f"""
SELECT
  regexp_extract(path, '([^/]+)$', 1) AS filename,
  CASE WHEN path LIKE '%.pptx' THEN 'powerpoint' WHEN path LIKE '%.docx' THEN 'word' WHEN path LIKE '%.pdf' THEN 'pdf' ELSE 'other' END AS file_type,
  ai_parse_document(content, map('version', '2.0', 'descriptionElementTypes', '*'))::STRING AS parsed_text
FROM read_files('{VOLUME_PATH}/', format => 'binaryFile')
WHERE path NOT LIKE '%.xlsx'
""")
_parsed_sql.createOrReplaceTempView("parsed_documents")

# Parse xlsx separately with Spark Excel reader
xlsx_path = f"{VOLUME_PATH}/earnings_data.xlsx"
try:
    sheets = spark.read.format("excel").option("operation", "listSheets").load(xlsx_path).collect()
    md_parts = ["# Excel Spreadsheet: earnings_data.xlsx\n"]
    for sheet in sheets:
        sheet_name = sheet["sheetName"]
        df = spark.read.format("excel").option("headerRows", 1).option("dataAddress", sheet_name).load(xlsx_path)
        md_parts.append(f"## Sheet: {sheet_name}\n")
        rows = df.collect()
        if not rows: continue
        headers = df.columns
        md_parts.append("| " + " | ".join(headers) + " |")
        md_parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            vals = [str(row[c]) if row[c] is not None else "" for c in headers]
            if any(v for v in vals):
                md_parts.append("| " + " | ".join(vals) + " |")
        md_parts.append("")
    xlsx_markdown = "\n".join(md_parts)

    from pyspark.sql import Row
    xlsx_df = spark.createDataFrame([Row(filename="earnings_data.xlsx", file_type="excel", parsed_text=xlsx_markdown)])
    _all = _parsed_sql.union(xlsx_df)
    _all.createOrReplaceTempView("parsed_documents")
    print(f"Parsed earnings_data.xlsx: {len(xlsx_markdown):,} chars")
except Exception as e:
    print(f"No xlsx found or error: {e}")

display(spark.sql("SELECT filename, file_type, LENGTH(parsed_text) AS parsed_chars FROM parsed_documents ORDER BY file_type, filename"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Prepare Delta Table as Comparison Target

# COMMAND ----------

delta_table = f"{CATALOG}.{SCHEMA}.earnings_summary"
rows = spark.sql(f"SELECT * FROM {delta_table}").collect()
columns = spark.sql(f"SELECT * FROM {delta_table} LIMIT 1").columns

md_parts = [f"# Delta Table: {delta_table}\n"]
md_parts.append("| " + " | ".join(columns) + " |")
md_parts.append("| " + " | ".join(["---"] * len(columns)) + " |")
for row in rows:
    vals = [str(row[c]) if row[c] is not None else "" for c in columns]
    md_parts.append("| " + " | ".join(vals) + " |")

md_parts.append("\n## Data Summary by Category\n")
categories = spark.sql(f"SELECT DISTINCT category FROM {delta_table} ORDER BY category").collect()
for cat_row in categories:
    cat = cat_row["category"]
    md_parts.append(f"\n### {cat}\n")
    cat_rows = spark.sql(f"SELECT metric, value, comparison, change, notes FROM {delta_table} WHERE category = '{cat}'").collect()
    for r in cat_rows:
        line = f"- **{r['metric']}**: {r['value']}"
        if r['change']: line += f" ({r['change']})"
        if r['comparison']: line += f" — vs {r['comparison']}"
        if r['notes']: line += f" [{r['notes']}]"
        md_parts.append(line)

delta_markdown = "\n".join(md_parts)
print(f"Delta table formatted: {len(delta_markdown):,} chars")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Define Comparison Pairs

# COMMAND ----------

parsed_rows = {row["filename"]: row for row in spark.sql("SELECT * FROM parsed_documents").collect()}

pptx_file = "quarterly_review.pptx"
pptx_text = parsed_rows[pptx_file]["parsed_text"]

pairs = []
if "earnings_summary.docx" in parsed_rows:
    pairs.append({"target_type": "Word Document", "target_name": "earnings_summary.docx", "target_text": parsed_rows["earnings_summary.docx"]["parsed_text"]})
if "earnings_data.xlsx" in parsed_rows:
    pairs.append({"target_type": "Excel Spreadsheet", "target_name": "earnings_data.xlsx", "target_text": parsed_rows["earnings_data.xlsx"]["parsed_text"]})
pairs.append({"target_type": "Delta Table", "target_name": delta_table, "target_text": delta_markdown})

print(f"PowerPoint: {pptx_file} ({len(pptx_text):,} chars)")
print(f"\nComparison pairs ({len(pairs)}):")
for p in pairs:
    print(f"  vs {p['target_type']}: {p['target_name']} ({len(p['target_text']):,} chars)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Run All Comparisons

# COMMAND ----------

comparison_results = []

for p in pairs:
    target_type = p["target_type"]
    target_name = p["target_name"]
    target_text = p["target_text"]

    print(f"\nComparing: {pptx_file} vs {target_name} ({target_type})")
    print("-" * 50)

    prompt = f"""You are a document alignment analyst. Compare the following PowerPoint presentation against the {target_type.lower()}.

IMPORTANT: Your response MUST use proper markdown formatting with ## headings, bullet lists with -, and **bold** text.

=== POWERPOINT PRESENTATION ===
{pptx_text}

=== {target_type.upper()} ===
{target_text}

## Overall Similarity Score

**Score: X%** — [explanation]

## Aligned Content

- **[Topic]** — [slide X] matches [{target_type} section/sheet/row]. [detail]

## Divergences Found

- **[Divergence]**
  - PowerPoint says: [exact claim]
  - {target_type} says: [exact claim]
  - Severity: **Major/Moderate/Minor**
  - Impact: [explanation]

## Content in PowerPoint Only

- [items not in the {target_type.lower()}]

## Content in {target_type} Only

- [items not in the PowerPoint]

## Recommendation

- [specific actions]

Be precise with numbers and exact claims."""

    escaped = prompt.replace("'", "''")
    report = spark.sql(f"SELECT ai_query('{MODEL}', '{escaped}') AS report").collect()[0]["report"]
    print(f"  Report: {len(report):,} chars")

    comparison_results.append({
        "target_type": target_type, "target_name": target_name,
        "pptx_text": pptx_text, "target_text": target_text, "report": report
    })

print(f"\n{'=' * 50}")
print(f"Completed {len(comparison_results)} comparisons")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Formatted Reports

# COMMAND ----------

from IPython.display import display, Markdown

for i, result in enumerate(comparison_results):
    header = f"""---
### Alignment Report #{i+1}: PowerPoint vs {result['target_type']}

**PowerPoint:** `{pptx_file}` ({len(result['pptx_text']):,} chars) &nbsp;&nbsp; **vs** &nbsp;&nbsp; **{result['target_type']}:** `{result['target_name']}` ({len(result['target_text']):,} chars)

**Model:** `{MODEL}`

---
"""
    display(Markdown(header + result["report"]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7: Persist All Results

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

rows = []
for i, result in enumerate(comparison_results):
    rows.append(Row(
        comparison_id=f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i+1:03d}",
        pptx_file=pptx_file,
        compare_to_type=result["target_type"],
        compare_to_source=result["target_name"],
        pptx_parsed_text=result["pptx_text"],
        doc_parsed_text=result["target_text"],
        model=MODEL,
        comparison_report=result["report"],
        created_at=datetime.now()
    ))

if rows:
    spark.createDataFrame(rows).write.mode("append").saveAsTable(OUTPUT_TABLE)
    print(f"Saved {len(rows)} reports to {OUTPUT_TABLE}")

# COMMAND ----------

display(spark.sql(f"""SELECT comparison_id, pptx_file, compare_to_type, compare_to_source, model,
       LEFT(comparison_report, 200) AS report_preview, created_at
FROM {OUTPUT_TABLE}
ORDER BY created_at DESC"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC
# MAGIC | Comparison | What It Tests |
# MAGIC |-----------|--------------|
# MAGIC | **PPT vs Word** | Narrative alignment — does the write-up match the slides? |
# MAGIC | **PPT vs Excel** | Data accuracy — do the numbers in the spreadsheet match? |
# MAGIC | **PPT vs Delta Table** | Structured data alignment — does the presentation match the governed data? |
