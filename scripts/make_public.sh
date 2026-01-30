#!/usr/bin/env bash
set -e

# ======== CONFIG (改一次就夠) ========
PROJECT_ID="ffmpeg-mcp-server"
REGION="asia-southeast1"

# ======== INPUT ========
SERVICE_NAME="$1"

if [ -z "$SERVICE_NAME" ]; then
  echo "Usage: ./scripts/make_public.sh <service-name>"
  exit 1
fi

echo "Making Cloud Run service public:"
echo "  project = $PROJECT_ID"
echo "  region  = $REGION"
echo "  service = $SERVICE_NAME"
echo ""

gcloud config set project "$PROJECT_ID"

gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region="$REGION" \
  --member="allUsers" \
  --role="roles/run.invoker"

echo ""
echo "DONE. Service is now public."
