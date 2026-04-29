# Document Comparator — Deployment Guide

## Overview

This guide covers deploying the Document Comparator Databricks App from scratch. The app uses `ai_parse_document()` and `ai_query()` to compare PowerPoint presentations against documents, with a user-selectable foundation model.

## Prerequisites

### Tools Required

- **Databricks CLI** (v0.200+): `brew install databricks/tap/databricks`
- **Node.js** (v18+): Required to build the React frontend
- **npm**: Comes with Node.js

### Workspace Requirements

- Databricks workspace with **Unity Catalog** enabled
- **Serverless SQL Warehouse** available (or Pro/Classic warehouse)
- **Foundation Model APIs** enabled on the workspace
- **Databricks Apps** enabled on the workspace
- Workspace admin access (or permissions to create apps, schemas, and volumes)

---

## Step 1: Authenticate to Databricks

```bash
# Login to your workspace (opens browser for SSO)
databricks auth login https://<your-workspace>.cloud.databricks.com --profile=<profile-name>

# Verify authentication
databricks auth profiles | grep <profile-name>
# Should show "YES" in the last column
```

## Step 2: Create Unity Catalog Resources

The app needs a catalog, schema, and volume to store uploaded documents temporarily.

```bash
# Set your profile
PROFILE="<profile-name>"
WH_ID="<your-warehouse-id>"

# Find your warehouse ID if you don't know it
databricks warehouses list --profile=$PROFILE

# Create schema (use an existing catalog or create one)
databricks api post /api/2.0/sql/statements/ --profile=$PROFILE --json='{
  "statement": "CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>",
  "warehouse_id": "'$WH_ID'",
  "wait_timeout": "30s"
}'

# Create volume for temp file uploads
databricks api post /api/2.0/sql/statements/ --profile=$PROFILE --json='{
  "statement": "CREATE VOLUME IF NOT EXISTS <catalog>.<schema>.document_comparison_uploads",
  "warehouse_id": "'$WH_ID'",
  "wait_timeout": "30s"
}'
```

## Step 3: Verify Foundation Model APIs

The app uses `ai_query()` which requires Foundation Model APIs to be enabled.

```bash
# Test that ai_query works on your warehouse
databricks api post /api/2.0/sql/statements/ --profile=$PROFILE --json='{
  "statement": "SELECT ai_query('"'"'databricks-meta-llama-3-3-70b-instruct'"'"', '"'"'Say hello'"'"') AS test",
  "warehouse_id": "'$WH_ID'",
  "wait_timeout": "30s"
}'
```

If this fails with a permission error:
1. Go to **Workspace Settings** > **AI/BI** > Enable **Foundation Model APIs**
2. Or contact your workspace admin to enable it

## Step 4: Build the Frontend

```bash
cd document-comparator/app/frontend

# Install dependencies
npm install

# Build production bundle
npm run build

# Verify the build output
ls dist/
# Should contain: index.html, assets/
```

## Step 5: Configure app.yaml

Edit `app.yaml` to match your environment:

```yaml
command:
  - python
  - app.py
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse          # Binds to a warehouse resource in the app
  - name: CATALOG_NAME
    value: "<your-catalog>"            # Unity Catalog catalog name
  - name: SCHEMA_NAME
    value: "<your-schema>"             # Schema within the catalog
  - name: VOLUME_NAME
    value: "document_comparison_uploads"  # Volume for temp uploads
  - name: NODE_ENV
    value: "production"
```

## Step 6: Sync to Workspace

```bash
# Upload app files to workspace (excluding node_modules)
databricks sync document-comparator/app \
  /Workspace/Users/<your-email>/document-comparator \
  --profile=$PROFILE \
  --exclude "node_modules,.venv,__pycache__,.git"
```

## Step 7: Create the Databricks App

```bash
# Create the app (first time only)
databricks apps create document-comparator \
  --description "AI-powered document comparison using ai_parse_document and ai_query" \
  --profile=$PROFILE

# Wait for the app compute to become active (30-60 seconds)
databricks apps get document-comparator --profile=$PROFILE
```

## Step 8: Add SQL Warehouse Resource

The app needs a SQL warehouse resource binding for the `valueFrom: sql-warehouse` in app.yaml.

**Via UI (recommended):**
1. Go to **Compute** > **Apps** in the workspace
2. Click on **document-comparator**
3. Click **Edit**
4. Under **Resources**, click **Add resource**
5. Select **SQL Warehouse**
6. Choose your serverless SQL warehouse
7. Save

**Via CLI:**
```bash
databricks apps update document-comparator --profile=$PROFILE --json='{
  "resources": [{
    "name": "sql-warehouse",
    "sql_warehouse": {
      "id": "<your-warehouse-id>",
      "permission": "CAN_USE"
    }
  }]
}'
```

## Step 9: Grant Permissions to the App Service Principal

When a Databricks App is created, it gets a **service principal** that runs the app code. This service principal needs permissions on:

### a) Unity Catalog (schema and volume access)

```sql
-- Run these in the SQL Editor or via CLI
-- Replace <app-service-principal> with the app's SP name (e.g., "app-xxxx document-comparator")

GRANT USE CATALOG ON CATALOG <catalog> TO `<app-service-principal>`;
GRANT USE SCHEMA ON SCHEMA <catalog>.<schema> TO `<app-service-principal>`;
GRANT READ VOLUME, WRITE VOLUME ON VOLUME <catalog>.<schema>.document_comparison_uploads TO `<app-service-principal>`;
```

**To find the app's service principal name:**
```bash
databricks apps get document-comparator --profile=$PROFILE --output=json | python3 -c "
import sys, json
app = json.load(sys.stdin)
print('Service Principal:', app.get('service_principal_name', ''))
print('SP Client ID:', app.get('service_principal_client_id', ''))
"
```

### b) SQL Warehouse (query execution)

The SQL warehouse resource binding (Step 8) handles this automatically. If you added it via UI, the app SP gets `CAN_USE` permission.

### c) Foundation Model APIs

The app SP needs permission to call foundation model endpoints. This is typically granted by default, but if `ai_query()` fails:

```sql
-- Grant access to the serving endpoint
GRANT QUERY ON SERVING ENDPOINT `databricks-meta-llama-3-3-70b-instruct` TO `<app-service-principal>`;
```

## Step 10: Deploy the App

```bash
databricks apps deploy document-comparator \
  --source-code-path /Workspace/Users/<your-email>/document-comparator \
  --profile=$PROFILE
```

The deployment takes 30-60 seconds. Check status:

```bash
databricks apps get document-comparator --profile=$PROFILE
```

Look for `"state": "RUNNING"` in compute_status and `"state": "SUCCEEDED"` in the deployment status.

## Step 11: Access the App

The app URL follows this pattern:
```
https://document-comparator-<workspace-id>.aws.databricksapps.com
```

Find the exact URL:
```bash
databricks apps get document-comparator --profile=$PROFILE --output=json | python3 -c "
import sys, json; print(json.load(sys.stdin).get('url', ''))
"
```

---

## Troubleshooting

### "No running SQL warehouse found"
- The warehouse auto-stopped. The app will start it automatically, but the first request may take 30-60 seconds while the warehouse starts.
- Alternatively, set a longer auto-stop timeout on the warehouse.

### "The wait_timeout field must be 0 seconds..."
- The app uses async polling (`wait_timeout=0s`). If you see this error, the app code may have been reverted. Redeploy.

### "PERMISSION_DENIED" on ai_query or ai_parse_document
- The app's service principal needs `CAN_USE` on the SQL warehouse and access to Foundation Model APIs.
- Check: Compute > Apps > document-comparator > Resources — ensure a SQL warehouse is attached.
- Run the GRANT statements from Step 9.

### "'dict' object has no attribute 'as_dict'"
- SDK version mismatch. The app uses `run_sql()` with `statement_execution` API which avoids this. If you see this error, ensure `app.py` is v4+ (uses SQL, not Model Serving REST calls).

### "ai_parse_document returned no content"
- The file may be corrupted or empty. Try a different file.
- Check that the volume exists and the app SP has WRITE VOLUME permission.

### App shows "Application Error" or blank page
- Check app logs: Compute > Apps > document-comparator > Logs
- Common causes: missing dependencies in `requirements.txt`, frontend not built (`dist/` missing), Python syntax error in `app.py`.

### Frontend not loading (API works but UI is blank)
- Ensure `frontend/dist/` was built and synced. The `dist/` directory must contain `index.html` and `assets/`.
- Rebuild: `cd frontend && npm run build`
- Resync and redeploy.

---

## Redeployment (after code changes)

```bash
# 1. If frontend changed, rebuild
cd document-comparator/app/frontend && npm run build

# 2. Sync files
databricks sync document-comparator/app \
  /Workspace/Users/<your-email>/document-comparator \
  --profile=$PROFILE \
  --exclude "node_modules,.venv,__pycache__,.git"

# 3. Redeploy
databricks apps deploy document-comparator \
  --source-code-path /Workspace/Users/<your-email>/document-comparator \
  --profile=$PROFILE
```

---

## Architecture

```
User Browser
    │
    ▼
┌─────────────────────────────────────┐
│  Databricks App (FastAPI + React)   │
│  ┌──────────┐  ┌─────────────────┐  │
│  │ React UI │  │ FastAPI Backend  │  │
│  │ (model   │──│ /api/compare    │  │
│  │ selector)│  │ /api/parse      │  │
│  └──────────┘  └────────┬────────┘  │
└─────────────────────────┼───────────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
              ▼           ▼           ▼
    ┌──────────────┐ ┌────────┐ ┌─────────┐
    │ UC Volume    │ │ SQL    │ │ ai_query│
    │ (temp files) │ │ WH     │ │ (model  │
    │              │ │        │ │ select) │
    └──────────────┘ └───┬────┘ └─────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ai_parse_document│
                │ (PDF, PPTX,     │
                │  DOCX, images)  │
                └─────────────────┘
```

## File Structure

```
document-comparator/
├── app/
│   ├── app.py              # FastAPI backend (v4)
│   ├── app.yaml            # Databricks App config (all env vars)
│   ├── requirements.txt    # Python dependencies
│   ├── .gitignore
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx     # React UI with model selector
│       │   ├── main.tsx    # React entry point
│       │   └── index.css   # Tailwind styles
│       ├── dist/           # Built frontend (after npm run build)
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── tailwind.config.js
│       └── postcss.config.js
├── notebook/
│   ├── 01_generate_sample_documents.py
│   ├── 02_compare_documents.py
│   └── 03_compare_at_scale.py
└── DEPLOY.md               # This file
```
