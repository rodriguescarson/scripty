#!/usr/bin/env bash
# Deploys a single-node ClickHouse to Cloud Run (self-hosted cluster for the mcp-clickhouse runtime requirement).
set -euo pipefail
cd "$(dirname "$0")"
PROJECT=${PROJECT:-mealstogo-76a00}; REGION=${REGION:-us-central1}; SVC=scripty-clickhouse
gcloud run deploy "$SVC" --source . --project "$PROJECT" --region "$REGION" --platform managed \
  --allow-unauthenticated --port 8080 --memory 2Gi --cpu 1 --min-instances 1 --max-instances 1 \
  --timeout 300 --concurrency 40 --quiet
gcloud run services describe "$SVC" --project "$PROJECT" --region "$REGION" --format='value(status.url)'
