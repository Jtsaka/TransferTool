# Deploying Compass to Google Cloud Run

This walks through getting Compass running on Cloud Run with Firestore as
the cache. Total time: ~20 minutes the first time.

## Why Cloud Run

- Same Google project hosts your Firestore and your container, so the
  service account that runs the container can talk to Firestore using
  Application Default Credentials — no key file to manage.
- Scales to zero when idle (cheap), scales up on demand.
- HTTPS endpoint with a managed cert out of the box.

---

## 0. Prereqs

- A Google account.
- The `gcloud` CLI installed: <https://cloud.google.com/sdk/docs/install>.
- Docker is **not** required locally — Cloud Build will build the image
  for you in the cloud.

---

## 1. Create / select a GCP project

You can reuse the same project as Firebase (recommended) or create a new
one. To create a fresh project:

```bash
gcloud auth login
gcloud projects create compass-12345 --name="Compass"
gcloud config set project compass-12345
gcloud beta billing projects link compass-12345 --billing-account=XXXX-XXXX-XXXX
```

If you already have a Firebase project, just point gcloud at it:

```bash
gcloud config set project YOUR_FIREBASE_PROJECT_ID
```

> Billing must be enabled, even though Cloud Run + Firestore have generous
> free tiers and you almost certainly won't be charged for low traffic.

## 2. Enable the APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  containerregistry.googleapis.com
```

## 3. Make sure Firestore exists

If you already enabled Firestore through the Firebase console, skip this.
Otherwise:

```bash
gcloud firestore databases create --location=us-central1
```

(Use a region close to where you'll deploy Cloud Run. `us-central1` is a
safe default.)

## 4. Create a runtime service account

This is the identity Cloud Run will use to call Firestore. Giving the
container its own service account is much safer than mounting a key file.

```bash
PROJECT=$(gcloud config get-value project)

gcloud iam service-accounts create compass-runtime \
  --display-name="Compass Cloud Run runtime"

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:compass-runtime@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

`roles/datastore.user` covers Firestore read/write. (Yes, the role is
named `datastore` — Firestore in Native mode reuses the legacy IAM role.)

## 5. Deploy

You have two equivalent options.

### Option A — the helper script (one command)

```bash
GCP_PROJECT="$(gcloud config get-value project)" \
GEMINI_API_KEY="your-gemini-key-here" \
./scripts/deploy_cloud_run.sh
```

That builds the container with Cloud Build, pushes it to GCR, and creates
or updates the `compass` Cloud Run service. At the end it prints the
public URL — open it in a browser.

### Option B — raw gcloud commands

```bash
PROJECT=$(gcloud config get-value project)
REGION=us-central1
IMAGE="gcr.io/${PROJECT}/compass:latest"

gcloud builds submit --tag "$IMAGE"

gcloud run deploy compass \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "compass-runtime@${PROJECT}.iam.gserviceaccount.com" \
  --set-env-vars "GEMINI_API_KEY=your-gemini-key-here,FIREBASE_PROJECT_ID=${PROJECT}" \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 5
```

## 6. Verify it's healthy

Hit the health endpoint:

```bash
URL=$(gcloud run services describe compass --region=us-central1 --format='value(status.url)')
curl "$URL/api/health"
```

You want to see:

```json
{
  "status": "ok",
  "firestore_remote": true,
  "gemini_ready": true,
  "default_from_institution": "College of San Mateo"
}
```

If `firestore_remote` is `false`, the service account doesn't have
Firestore permission yet (revisit step 4). If `gemini_ready` is `false`,
the `GEMINI_API_KEY` env var didn't get set.

Then load `$URL` in a browser and click through the three pages.

---

## 7. Production hygiene (do once)

### Use Secret Manager for the Gemini key

Setting `GEMINI_API_KEY` via `--set-env-vars` is fine for getting started,
but the value ends up in revision metadata. For real use, store the key
in Secret Manager:

```bash
gcloud services enable secretmanager.googleapis.com

echo -n "your-gemini-key-here" | \
  gcloud secrets create GEMINI_API_KEY --data-file=-

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:compass-runtime@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud run services update compass \
  --region=us-central1 \
  --remove-env-vars GEMINI_API_KEY \
  --update-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest
```

> ⚠️ **Windows / PowerShell gotcha.** The Unix `echo -n ... | gcloud secrets ...`
> trick does not translate to PowerShell cleanly — piping a string to a
> native command typically appends CRLF, which ends up inside the secret
> value. The key will appear to load (`/api/health` reports
> `gemini_ready: true`) but every actual model call fails with
> `INTERNAL:Illegal header value` / `status = UNAVAILABLE, details = "Illegal metadata"`
> because gRPC refuses HTTP/2 headers containing `\r` or `\n`. Use a
> temp file instead:
>
> ```powershell
> [System.IO.File]::WriteAllText("$env:TEMP\gkey.tmp", "your-key-here", [System.Text.Encoding]::ASCII)
> gcloud secrets versions add GEMINI_API_KEY --data-file="$env:TEMP\gkey.tmp"
> Remove-Item "$env:TEMP\gkey.tmp"
> gcloud run services update compass --region=us-central1 --update-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest
> ```

### Custom domain (optional)

```bash
gcloud beta run domain-mappings create \
  --service compass \
  --domain compass.yourdomain.com \
  --region us-central1
```

Then add the DNS records gcloud prints to your domain registrar.

### Cost guardrails

- Cloud Run: $0 when idle. Set `--max-instances 5` (already in the script)
  so a runaway loop can't cost much.
- Gemini: keep an eye on quota in <https://aistudio.google.com/>. The
  cache means repeat lookups are free after the first hit.
- Firestore: the free tier easily covers this app at any reasonable
  traffic (50k reads / 20k writes per day).

---

## 8. Updating the deployment

Any time you push code changes, just re-run the same deploy command. Each
build creates a new immutable revision; Cloud Run flips traffic to it
atomically and you can roll back from the console with one click.

```bash
GCP_PROJECT=$(gcloud config get-value project) \
GEMINI_API_KEY=$(gcloud secrets versions access latest --secret=GEMINI_API_KEY) \
./scripts/deploy_cloud_run.sh
```

(Or just `gcloud builds submit ...` + `gcloud run services update compass --image ...` if you only want to change the image.)

---

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `403 PERMISSION_DENIED` from Firestore in logs | Service account is missing `roles/datastore.user`. Re-run the binding from step 4. |
| `firestore_remote: false` on `/api/health` | `FIREBASE_PROJECT_ID` env var isn't set, or the Firestore database doesn't exist in the project. |
| Container fails to start with `Failed to bind to PORT` | You changed the start command and forgot to bind to `$PORT`. The provided Dockerfile already does this. |
| Cold-start latency feels high | Set `--min-instances 1` (costs a few dollars/month but keeps one instance warm). |
| `/api/ap-scores` returns 502 | Gemini call failed. Check Cloud Run logs: `gcloud run services logs read compass --region us-central1 --limit 50`. |

---

## What this gets you

A public HTTPS URL that serves the static Compass site and the JSON API,
backed by a Firestore database that gets warmer with every lookup. The
container has no long-lived secrets baked into it (key comes from Secret
Manager, Firestore auth comes from ADC), and rebuilds are one command.
