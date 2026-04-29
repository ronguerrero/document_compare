# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Compare Documents at Scale
# MAGIC
# MAGIC Process an entire document library using **`ai_parse_document()`** and **`ai_query()`**.
# MAGIC
# MAGIC **Use case:** You have a folder of PowerPoint presentations and their corresponding documents.
# MAGIC This notebook parses all files, pairs them by naming convention, and generates comparison
# MAGIC reports for every pair — in a single pipeline.
# MAGIC
# MAGIC **No library installs required.**

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

CATALOG = "lakedoom_demo_catalog"
SCHEMA = "capital_markets_ai"
VOLUME = "document_comparison"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
MODEL = "databricks-meta-llama-3-3-70b-instruct"
OUTPUT_TABLE = f"{CATALOG}.{SCHEMA}.document_comparisons"

print(f"Document library: {VOLUME_PATH}")
print(f"Model: {MODEL}")
print(f"Output table: {OUTPUT_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Inventory All Documents
# MAGIC
# MAGIC Scan the volume and parse every document in one query:

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   regexp_extract(path, '([^/]+)$', 1) AS filename,
# MAGIC   CASE
# MAGIC     WHEN path LIKE '%.pptx' THEN 'powerpoint'
# MAGIC     WHEN path LIKE '%.docx' THEN 'document'
# MAGIC     WHEN path LIKE '%.pdf' THEN 'pdf'
# MAGIC     WHEN path LIKE '%.txt' THEN 'text'
# MAGIC     ELSE 'other'
# MAGIC   END AS file_type,
# MAGIC   length(content) AS file_size_bytes
# MAGIC FROM read_files(
# MAGIC   '/Volumes/lakedoom_demo_catalog/capital_markets_ai/document_comparison/',
# MAGIC   format => 'binaryFile'
# MAGIC )
# MAGIC ORDER BY file_type, filename

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Parse All Documents at Once

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Parse every file in the volume using ai_parse_document()
# MAGIC CREATE OR REPLACE TEMP VIEW parsed_documents AS
# MAGIC SELECT
# MAGIC   regexp_extract(path, '([^/]+)$', 1) AS filename,
# MAGIC   CASE
# MAGIC     WHEN path LIKE '%.pptx' THEN 'powerpoint'
# MAGIC     WHEN path LIKE '%.docx' THEN 'document'
# MAGIC     WHEN path LIKE '%.pdf' THEN 'pdf'
# MAGIC     ELSE 'text'
# MAGIC   END AS file_type,
# MAGIC   length(content) AS file_size_bytes,
# MAGIC   ai_parse_document(
# MAGIC     content, map('version', '2.0', 'descriptionElementTypes', '*')
# MAGIC   )::STRING AS parsed_text
# MAGIC FROM read_files(
# MAGIC   '/Volumes/lakedoom_demo_catalog/capital_markets_ai/document_comparison/',
# MAGIC   format => 'binaryFile'
# MAGIC );
# MAGIC
# MAGIC SELECT filename, file_type, file_size_bytes, LENGTH(parsed_text) AS parsed_chars
# MAGIC FROM parsed_documents
# MAGIC ORDER BY file_type, filename

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Define Document Pairs
# MAGIC
# MAGIC Pair PowerPoints with their corresponding documents. Two strategies:
# MAGIC
# MAGIC **Strategy A — Manual pairing** (explicit mapping):

# COMMAND ----------

# Manual pair mapping — edit this to match your files
pairs = [
    ("quarterly_review.pptx", "earnings_summary.docx"),
    # Add more pairs here:
    # ("strategy_deck.pptx", "strategy_document.docx"),
    # ("board_presentation.pptx", "board_memo.pdf"),
]

# Create a pairs table
from pyspark.sql import Row
pairs_df = spark.createDataFrame(
    [Row(pptx_file=p[0], doc_file=p[1]) for p in pairs]
)
pairs_df.createOrReplaceTempView("document_pairs")
pairs_df.show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC **Strategy B — Auto-pairing** (match every PowerPoint against every document):

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Auto-pair: every pptx matched with every docx
# MAGIC CREATE OR REPLACE TEMP VIEW auto_pairs AS
# MAGIC SELECT
# MAGIC   p.filename AS pptx_file,
# MAGIC   d.filename AS doc_file
# MAGIC FROM parsed_documents p
# MAGIC CROSS JOIN parsed_documents d
# MAGIC WHERE p.file_type = 'powerpoint'
# MAGIC   AND d.file_type IN ('document', 'pdf');
# MAGIC
# MAGIC SELECT * FROM auto_pairs

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Run Comparisons for All Pairs

# COMMAND ----------

# Using the manual pairs from Step 3 Strategy A
comparison_results = []

for pptx_file, doc_file in pairs:
    print(f"\nComparing: {pptx_file} vs {doc_file}")
    print("-" * 50)

    # Parse both
    parsed = spark.sql(f"""
    SELECT
      filename,
      parsed_text
    FROM parsed_documents
    WHERE filename IN ('{pptx_file}', '{doc_file}')
    """).collect()

    parsed_map = {row["filename"]: row["parsed_text"] for row in parsed}

    if pptx_file not in parsed_map:
        print(f"  WARNING: {pptx_file} not found in parsed documents, skipping")
        continue
    if doc_file not in parsed_map:
        print(f"  WARNING: {doc_file} not found in parsed documents, skipping")
        continue

    pptx_text = parsed_map[pptx_file]
    doc_text = parsed_map[doc_file]
    print(f"  PowerPoint: {len(pptx_text):,} chars")
    print(f"  Document:   {len(doc_text):,} chars")

    # Compare
    prompt = f"""Compare the following PowerPoint and document. Provide:
1. Overall Similarity Score (0-100%)
2. Aligned Content (cite specific slides/sections)
3. Divergences (with severity: Minor/Moderate/Major)
4. Content in PowerPoint Only
5. Content in Document Only
6. Recommendations

Be specific with numbers, percentages, and exact claims.

=== POWERPOINT ===
{pptx_text}

=== DOCUMENT ===
{doc_text}"""

    escaped = prompt.replace("'", "''")
    report = spark.sql(f"SELECT ai_query('{MODEL}', '{escaped}') AS report").collect()[0]["report"]
    print(f"  Report: {len(report):,} chars generated")

    comparison_results.append({
        "pptx_file": pptx_file,
        "doc_file": doc_file,
        "pptx_text": pptx_text,
        "doc_text": doc_text,
        "report": report
    })

print(f"\n{'=' * 50}")
print(f"Completed {len(comparison_results)} comparisons")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Formatted Reports for All Pairs

# COMMAND ----------

from IPython.display import display, Markdown

for i, result in enumerate(comparison_results):
    pptx_name = result["pptx_file"]
    doc_name = result["doc_file"]
    report_text = result["report"]
    pptx_len = len(result["pptx_text"])
    doc_len = len(result["doc_text"])

    header = f"""---
### Alignment Report #{i+1}

**PowerPoint:** `{pptx_name}` ({pptx_len:,} chars) &nbsp;&nbsp; **vs** &nbsp;&nbsp; **Document:** `{doc_name}` ({doc_len:,} chars)

---
"""
    display(Markdown(header + report_text))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 6: Persist All Results to Delta Table

# COMMAND ----------

from datetime import datetime
from pyspark.sql import Row

spark.sql(f"""
CREATE OR REPLACE TABLE {OUTPUT_TABLE} (
  comparison_id STRING,
  pptx_file STRING,
  doc_file STRING,
  pptx_parsed_text STRING,
  doc_parsed_text STRING,
  comparison_report STRING,
  created_at TIMESTAMP
)
""")

rows = []
for i, result in enumerate(comparison_results):
    rows.append(Row(
        comparison_id=f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i+1:03d}",
        pptx_file=result["pptx_file"],
        doc_file=result["doc_file"],
        pptx_parsed_text=result["pptx_text"],
        doc_parsed_text=result["doc_text"],
        comparison_report=result["report"],
        created_at=datetime.now()
    ))

if rows:
    spark.createDataFrame(rows).write.mode("append").saveAsTable(OUTPUT_TABLE)
    print(f"Saved {len(rows)} comparison reports to {OUTPUT_TABLE}")
else:
    print("No comparisons to save")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 7: Query Comparison History

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   comparison_id,
# MAGIC   pptx_file,
# MAGIC   doc_file,
# MAGIC   LENGTH(pptx_parsed_text) AS pptx_chars,
# MAGIC   LENGTH(doc_parsed_text) AS doc_chars,
# MAGIC   LENGTH(comparison_report) AS report_chars,
# MAGIC   LEFT(comparison_report, 200) AS report_preview,
# MAGIC   created_at
# MAGIC FROM lakedoom_demo_catalog.capital_markets_ai.document_comparisons
# MAGIC ORDER BY created_at DESC

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC
# MAGIC | Notebook | Purpose |
# MAGIC |----------|---------|
# MAGIC | **01_generate_sample_documents** | Create sample .pptx and .docx files for demo |
# MAGIC | **02_compare_documents** | Compare a single pair of documents with formatted report |
# MAGIC | **03_compare_at_scale** (this notebook) | Compare multiple document pairs in batch |
# MAGIC
# MAGIC ### Scaling Strategies
# MAGIC
# MAGIC | Strategy | When to Use |
# MAGIC |----------|------------|
# MAGIC | **Manual pairs** | You know which pptx maps to which docx |
# MAGIC | **Auto-pairing** | Compare every presentation against every document |
# MAGIC | **Naming convention** | Files share a prefix (e.g., `project_a.pptx` + `project_a.docx`) |
# MAGIC | **Workflow scheduling** | Run this notebook on a schedule with new files landing in the volume |
# MAGIC
# MAGIC ### To Scale Further
# MAGIC - **Schedule as a Workflow:** Trigger when new files land in the volume
# MAGIC - **Parameterize:** Use Databricks widgets for dynamic volume path and model selection
# MAGIC - **Parallelize:** Use `spark.sql()` with concurrent threads for large batches
# MAGIC - **Monitor:** Build an AI/BI dashboard on the `document_comparisons` table