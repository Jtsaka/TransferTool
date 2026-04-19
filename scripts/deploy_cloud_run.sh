#!/usr/bin/env bash
# Deploy Compass to Google Cloud Run.
#
# Required env vars:
#   GCP_PROJECT     - GCP project id (e.g. compass-12345)
#   GEMINI_API_KEY  - Gemini API key for the backend
#
# Optional env vars:
#   GCP_REGION      - Defaults to us-central1
#   SERVICE_NAME    - Defaults to compass
#   SERVICE_ACCOUNT - Service account email (defaults to compass-runtime@PROJECT.iam.gserviceaccount.com)
#
# Usage:
#   GCP_PROJECT=compass-12345 GEMINI_API_KEY=... ./scripts/deploy_cloud_run.sh

set -euo pipefail

: "${GCP_PROJECT:?Set GCP_PROJECT}"
: "${GEMINI_API_KEY:?Set GEMINI_API_KEY}"

GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-compass}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-compass-runtime@${GCP_PROJECT}.iam.gserviceaccount.com}"
IMAGE="gcr.io/${GCP_PROJECT}/${SERVICE_NAME}:$(date +%Y%m%d-%H%M%S)"

echo "==> Building image: ${IMAGE}"
gcloud builds submit --tag "${IMAGE}" --project "${GCP_PROJECT}"

echo "==> Deploying to Cloud Run service: ${SERVICE_NAME} (${GCP_REGION})"
gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE}" \
    --project "${GCP_PROJECT}" \
    --region "${GCP_REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --service-account "${SERVICE_ACCOUNT}" \
    --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY},FIREBASE_PROJECT_ID=${GCP_PROJECT},DEFAULT_FROM_INSTITUTION=College of San Mateo" \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 5 \
    --timeout 120

echo "==> Done. Service URL:"
gcloud run services describe "${SERVICE_NAME}" \
    --project "${GCP_PROJECT}" \
    --region "${GCP_REGION}" \
    --format 'value(status.url)'
