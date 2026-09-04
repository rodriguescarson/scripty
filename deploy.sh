#!/usr/bin/env bash
# Cloud Run deploy for the Scripty app (frames are served from GCS; ClickHouse is the Cloud Run service in infra/).
set -euo pipefail
cd "$(dirname "$0")"
PROJECT=${PROJECT:-mealstogo-76a00}; REGION=${REGION:-us-central1}
set -a; . ./.env; set +a
gcloud run deploy scripty --source . --project "$PROJECT" --region "$REGION" --platform managed --allow-unauthenticated \
  --port 8080 --memory 2Gi --cpu 2 --timeout 300 --concurrency 20 --min-instances 0 --max-instances 3 --quiet \
  --set-env-vars "CLICKHOUSE_HOST=$CLICKHOUSE_HOST,CLICKHOUSE_PORT=$CLICKHOUSE_PORT,CLICKHOUSE_SECURE=$CLICKHOUSE_SECURE,CLICKHOUSE_USER=$CLICKHOUSE_USER,CLICKHOUSE_PASSWORD=$CLICKHOUSE_PASSWORD,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,GOOGLE_GENAI_USE_VERTEXAI=true,SCRIPTY_FRAMES_BASE_URL=${SCRIPTY_FRAMES_BASE_URL:-},SCRIPTY_MODEL=${SCRIPTY_MODEL:-gemini-2.5-flash},SCRIPTY_VERIFY_MODEL=${SCRIPTY_VERIFY_MODEL:-gemini-2.5-pro}"
gcloud run services describe scripty --project "$PROJECT" --region "$REGION" --format='value(status.url)'
