# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Generate Sample Documents
# MAGIC
# MAGIC Generates a sample PowerPoint presentation and Word document for the comparison demo.
# MAGIC These files are uploaded to a Unity Catalog Volume.
# MAGIC
# MAGIC **Output:** Two files in `/Volumes/lakedoom_demo_catalog/capital_markets_ai/document_comparison/`
# MAGIC - `quarterly_review.pptx` — Q1 2026 earnings presentation (6 slides)
# MAGIC - `earnings_summary.docx` — Q1 2026 earnings write-up (7 sections)
# MAGIC
# MAGIC The documents cover the same material but with deliberate differences to demonstrate the comparison.

# COMMAND ----------

# MAGIC %pip install python-pptx python-docx --quiet
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG = "lakedoom_demo_catalog"
SCHEMA = "capital_markets_ai"
VOLUME = "document_comparison"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")
print(f"Volume ready: {VOLUME_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Generate PowerPoint Presentation

# COMMAND ----------

from pptx import Presentation

prs = Presentation()

slides = [
    ("Q1 2026 Business Review", [
        "Revenue grew 23% YoY to $4.82B",
        "Cloud Platform segment leads with 31% growth",
        "Operating margin expanded to 30.1%",
        "Raised FY2026 guidance to $20.5B-$21.0B"
    ]),
    ("Revenue Breakdown", [
        "Cloud Platform: $2.41B (50% of total, +31% YoY)",
        "AI & Analytics: $1.21B (25% of total, +29% YoY)",
        "Cybersecurity: $723M (15% of total, +15% YoY)",
        "Professional Services: $482M (10% of total, +8% YoY)"
    ]),
    ("Key Metrics", [
        "Gross Margin: 70.1% (up 210bps YoY)",
        "Free Cash Flow: $1.62B (+41% YoY)",
        "Net Income: $1.18B (+45% YoY)",
        "EPS: $2.94 (beat consensus by 9.7%)"
    ]),
    ("Strategic Priorities", [
        "Accelerate AI platform adoption across enterprise customers",
        "Expand international presence, particularly in APAC and EMEA",
        "Drive cloud migration for existing on-premise customers",
        "Invest in cybersecurity capabilities through M&A"
    ]),
    ("Risk Factors", [
        "Macroeconomic slowdown could impact enterprise IT spending",
        "Competitive pressure from hyperscalers (AWS, Azure, GCP)",
        "Foreign currency headwinds from strong USD (~150bps impact)",
        "Talent retention costs in AI/ML engineering"
    ]),
    ("FY2026 Outlook", [
        "Q2 Revenue: $5.05B - $5.15B (21-23% YoY growth)",
        "FY2026 Revenue: $20.5B - $21.0B (raised from $19.8B-$20.3B)",
        "Operating Margin target: 31-32%",
        "FY2026 EPS: $12.80 - $13.20"
    ]),
]

for title, bullets in slides:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = title
    tf = slide.placeholders[1].text_frame
    tf.clear()
    for i, b in enumerate(bullets):
        if i == 0:
            tf.paragraphs[0].text = b
        else:
            tf.add_paragraph().text = b

pptx_path = f"{VOLUME_PATH}/quarterly_review.pptx"
prs.save(pptx_path)
print(f"Created PowerPoint: {pptx_path} ({len(slides)} slides)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Generate Word Document
# MAGIC
# MAGIC The document covers the same topics as the presentation but with:
# MAGIC - More detail in some areas (analyst consensus, partner ecosystem)
# MAGIC - Slightly different numbers for strategic initiatives (5 vs 4 priorities)
# MAGIC - Additional risk factors (customer concentration, EU AI Act)
# MAGIC - Extra content (capital allocation, analyst consensus section)

# COMMAND ----------

from docx import Document

doc = Document()
doc.add_heading('TechNova Corporation — Q1 2026 Earnings Summary', 0)

doc.add_heading('Financial Highlights', level=1)
doc.add_paragraph(
    'TechNova reported strong Q1 2026 results with total revenue of $4.82 billion, '
    'representing 23.3% year-over-year growth. The company exceeded analyst expectations '
    'across all major metrics.'
)
for item in [
    'Revenue: $4.82B vs. $4.58B consensus estimate (+5.2% beat)',
    'Gross Margin: 70.1%, expanding 210 basis points from prior year',
    'Operating Income: $1.45B with 30.1% operating margin',
    'Net Income: $1.18B, up 45.3% year-over-year',
    'Diluted EPS: $2.94 vs. $2.68 consensus (+9.7% beat)',
    'Free Cash Flow: $1.62B, representing 33.6% FCF margin',
]:
    doc.add_paragraph(item, style='List Bullet')

doc.add_heading('Segment Performance', level=1)
doc.add_paragraph(
    'The Cloud Platform segment continued to be the primary growth driver, generating '
    '$2.41B in revenue (50% of total) with 31.2% YoY growth. AI & Analytics contributed '
    '$1.21B (25%) growing 28.7%. Cybersecurity revenue was $723M (15%) with 15.4% growth. '
    'Professional Services generated $482M (10%) growing 8.1%.'
)

doc.add_heading('Strategic Initiatives', level=1)
doc.add_paragraph('Management outlined four strategic priorities for the remainder of FY2026:')
for item in [
    'AI Platform Expansion: Accelerating enterprise AI adoption with new GenAI capabilities',
    'Geographic Growth: Expanding sales teams in APAC (+40% headcount) and EMEA (+25%)',
    'Cloud Migration: Converting 200+ on-premise customers to cloud platform',
    'Cybersecurity M&A: Evaluating 3 acquisition targets to strengthen security portfolio',
    'Partner Ecosystem: Launching 15 new ISV integrations by Q4',
]:
    doc.add_paragraph(item, style='List Bullet')

doc.add_heading('Risk Assessment', level=1)
doc.add_paragraph(
    'The company identified several key risks: potential enterprise IT spending slowdown '
    'due to macroeconomic uncertainty, increasing competition from cloud hyperscalers, '
    'and approximately 150bps foreign currency headwind from USD strength. Additionally, '
    'customer concentration risk remains elevated with top 10 clients representing 28% '
    'of total revenue. Regulatory risk from the EU AI Act could impact product roadmap timelines.'
)

doc.add_heading('Forward Guidance', level=1)
doc.add_paragraph('Management raised full-year FY2026 guidance:')
for item in [
    'Q2 2026 Revenue: $5.05B to $5.15B (21-23% YoY growth)',
    'FY2026 Revenue: $20.5B to $21.0B (raised from prior $19.8B-$20.3B)',
    'Operating Margin: Targeting 31-32% for Q2, expanding through year',
    'EPS Guidance: $12.80 to $13.20 for full year',
    'Capital Allocation: $2.5B share repurchase program authorized',
]:
    doc.add_paragraph(item, style='List Bullet')

doc.add_heading('Analyst Consensus', level=1)
doc.add_paragraph(
    'Following the earnings release, 8 analysts raised price targets with an average '
    'target of $142 per share, representing 18% upside. The consensus rating moved to '
    'Strong Buy with 12 out of 14 analysts recommending the stock.'
)

docx_path = f"{VOLUME_PATH}/earnings_summary.docx"
doc.save(docx_path)
print(f"Created Word document: {docx_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify Files

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   regexp_extract(path, '([^/]+)$', 1) AS filename,
# MAGIC   length(content) AS file_size_bytes
# MAGIC FROM read_files(
# MAGIC   '/Volumes/lakedoom_demo_catalog/capital_markets_ai/document_comparison/',
# MAGIC   format => 'binaryFile'
# MAGIC )

# COMMAND ----------

# MAGIC %md
# MAGIC **Next:** Run notebook `02_compare_documents` to parse and compare these files.
