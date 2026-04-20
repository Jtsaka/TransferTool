# Deploy Compass to Google Cloud Run (PowerShell version).
#
# Required env vars (or edit the defaults below):
#   GCP_PROJECT     - GCP project id (defaults to whatever gcloud is configured with)
#   GEMINI_API_KEY  - Gemini API key for the backend
#
# Optional env vars:
#   GCP_REGION      - Defaults to us-central1
#   SERVICE_NAME    - Defaults to compass
#   SERVICE_ACCOUNT - Defaults to compass-runtime@<project>.iam.gserviceaccount.com
#
# Usage (PowerShell):
#   $env:GEMINI_API_KEY = "your-key"
#   .\scripts\deploy_cloud_run.ps1

$ErrorActionPreference = "Stop"

$Project = if ($env:GCP_PROJECT) { $env:GCP_PROJECT } else { (gcloud config get-value project 2>$null).Trim() }
if (-not $Project) { throw "No GCP project set. Run: gcloud config set project YOUR_PROJECT_ID" }

if (-not $env:GEMINI_API_KEY) { throw "Set `$env:GEMINI_API_KEY = 'your-gemini-key' before running this script." }
$GeminiKey = $env:GEMINI_API_KEY

$Region         = if ($env:GCP_REGION)      { $env:GCP_REGION }      else { "us-central1" }
$ServiceName    = if ($env:SERVICE_NAME)    { $env:SERVICE_NAME }    else { "compass" }
$ServiceAccount = if ($env:SERVICE_ACCOUNT) { $env:SERVICE_ACCOUNT } else { "compass-runtime@$Project.iam.gserviceaccount.com" }
$Timestamp      = Get-Date -Format "yyyyMMdd-HHmmss"
$Image          = "gcr.io/$Project/${ServiceName}:$Timestamp"

Write-Host "==> Building image: $Image" -ForegroundColor Cyan
gcloud builds submit --tag "$Image" --project "$Project"
if ($LASTEXITCODE -ne 0) { throw "gcloud builds submit failed" }

Write-Host "==> Deploying to Cloud Run service: $ServiceName ($Region)" -ForegroundColor Cyan
$envVars = "GEMINI_API_KEY=$GeminiKey,FIREBASE_PROJECT_ID=$Project,DEFAULT_FROM_INSTITUTION=College of San Mateo"
gcloud run deploy $ServiceName `
    --image "$Image" `
    --project "$Project" `
    --region "$Region" `
    --platform managed `
    --allow-unauthenticated `
    --service-account "$ServiceAccount" `
    --set-env-vars "$envVars" `
    --memory 512Mi `
    --cpu 1 `
    --min-instances 0 `
    --max-instances 5 `
    --timeout 120
if ($LASTEXITCODE -ne 0) { throw "gcloud run deploy failed" }

Write-Host "==> Done. Service URL:" -ForegroundColor Green
gcloud run services describe $ServiceName --project "$Project" --region "$Region" --format "value(status.url)"
