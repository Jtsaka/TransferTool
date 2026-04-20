# Deploying Compass to Fly.io

Fly.io runs your container on micro-VMs in regions close to your users.
For Compass it's a great fit: the Windows CLI installs cleanly, deploys
are one command, and Fly auto-stops machines when idle so it stays cheap.

This is the **Windows-friendly alternative** to the Cloud Run path in
`docs/DEPLOY_CLOUD_RUN.md`. Pick whichever you prefer — Fly only hosts
the app; Firestore (the cache) still lives in Google.

---

## What you need before starting

1. A Fly.io account: <https://fly.io/app/sign-up> (you'll add a credit
   card, but the free trial covers everything for this app).
2. The `flyctl` CLI installed on Windows.
3. A Gemini API key from <https://aistudio.google.com/app/apikey>.
4. (Recommended) Firebase service-account JSON from your Firebase project.
   Without it, the backend falls back to a local file inside the VM that
   gets wiped on every deploy — fine for testing, useless for production.

## 1. Install flyctl on Windows

In PowerShell:

```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

Then **close and reopen PowerShell** so the new PATH takes effect, and
verify:

```powershell
flyctl version
fly version       # `fly` is an alias for `flyctl` after install
```

If `flyctl` still isn't found after a restart, the installer prints the
exact `Set-Item Env:\Path` command at the end of the install — run that
or add `C:\Users\YOUR_USER\.fly\bin` to your PATH manually.

## 2. Log in

```powershell
fly auth login
```

This opens a browser. Sign in (or create an account) and come back to
the terminal.

## 3. Get a Firebase service-account key (recommended)

Cloud Run could use Application Default Credentials because it runs
inside Google's network. Fly is outside Google, so we need an explicit
service-account key.

1. Open <https://console.firebase.google.com> → your project →
   ⚙ Project settings → **Service accounts** tab.
2. Click **Generate new private key** → save the JSON file somewhere
   safe on your laptop (NOT inside the repo). For example
   `C:\Users\YOU\Documents\compass-firebase.json`.
3. Don't commit it. Don't share it. The repo's `.gitignore` already
   covers common names like `serviceAccountKey.json`, but the safest
   thing is to keep it outside the project folder entirely.

## 4. Launch the app

From the repo root in PowerShell:

```powershell
fly launch --no-deploy
```

flyctl will:

1. Notice the existing `fly.toml` and `Dockerfile`.
2. Ask **"Would you like to copy its configuration to the new app?"** →
   say **Yes**.
3. Ask you to pick an app name (must be globally unique on Fly — try
   something like `compass-yourlastname`). The app name in `fly.toml`
   gets updated automatically.
4. Ask for a region — pick `sjc` (San Jose) or whatever's close to you.
5. Skip the Postgres/Redis prompts — say **No** to both. Compass uses
   Firestore for storage.
6. Skip "deploy now?" — we need to set secrets first. Say **No**.

## 5. Set the secrets

Fly secrets are encrypted at rest and injected as env vars at runtime.
This is where the Gemini key and Firebase creds go.

### Gemini key

```powershell
fly secrets set GEMINI_API_KEY="your-gemini-key-here"
```

### Firebase credentials

The service-account JSON contains real newlines, and PowerShell will
split it on those newlines if you try to pass it directly as an
argument (you'll see `Error: could not parse secrets: 'PRIVATE': must
be in the format NAME=VALUE`). The reliable way is to compress the
JSON to a single line and pipe it to `fly secrets import`:

```powershell
$json = (Get-Content -Raw "C:\Users\YOU\Documents\compass-firebase.json") | ConvertFrom-Json | ConvertTo-Json -Compress
"FIREBASE_CREDENTIALS_JSON=$json" | fly secrets import
```

`fly secrets import` reads `KEY=VALUE` lines from stdin, which sidesteps
the PowerShell argument-splitting issue entirely.

The backend supports both `FIREBASE_CREDENTIALS` (a file path) and
`FIREBASE_CREDENTIALS_JSON` (the raw JSON value) — we use the JSON form
here because secrets work better than mounted files on Fly.

### (Optional) project id

If you want `firestore_remote: true` to be unambiguous in `/api/health`
even before the first request, set:

```powershell
fly secrets set FIREBASE_PROJECT_ID="your-firebase-project-id"
```

## 6. Deploy

```powershell
fly deploy
```

That uploads your code, builds the image **on Fly's builders** (no local
Docker required), and rolls out a new release. First deploy takes ~3–5
minutes; subsequent ones are usually under a minute.

When it finishes, flyctl prints your URL — something like
`https://compass-yourlastname.fly.dev`. The `/api/health` check is
configured in `fly.toml`, so Fly will refuse to roll out a broken image.

## 7. Verify it works

```powershell
$URL = (fly status --json | ConvertFrom-Json).Hostname
Invoke-RestMethod "https://$URL/api/health"
```

You want:

```json
{
  "status": "ok",
  "firestore_remote": true,
  "gemini_ready": true,
  "default_from_institution": "College of San Mateo"
}
```

Then open `https://$URL` in a browser and walk through the three pages.

## 8. Day-to-day commands

| Task | Command |
| --- | --- |
| Push new code | `fly deploy` |
| Tail live logs | `fly logs` |
| SSH into the VM (debugging) | `fly ssh console` |
| List secrets (names only) | `fly secrets list` |
| Update a secret | `fly secrets set KEY="new-value"` (triggers a redeploy) |
| Open the dashboard | `fly dashboard` |
| Pause the app (free up resources) | `fly scale count 0` |
| Resume | `fly scale count 1` |

## 9. Cost expectations

Fly charges per VM-hour, not per request. The `shared-cpu-1x` / 512 MB
VM in `fly.toml` runs a few dollars a month if you keep it on 24/7.
Because we set `auto_stop_machines = "stop"`, the machine **suspends to
disk when idle** and resumes on the first request (~1–2 second cold
start). At hobby usage levels you'll usually be inside the free trial
allowance and pay $0.

If you want to guarantee zero cold starts, change `min_machines_running`
in `fly.toml` from `0` to `1` and redeploy. That gives up the free
auto-stop but keeps latency snappy.

---

## Updating later

```powershell
git pull
fly deploy
```

That's the whole loop. If you change `fly.toml`, the next `fly deploy`
applies it; if you change a secret, the redeploy is automatic.

---

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `fly: command not found` after install | Open a fresh PowerShell window, or add `C:\Users\YOU\.fly\bin` to PATH manually. |
| Health check failing on first deploy | Hit `fly logs` — usually a missing secret. Check `fly secrets list`. |
| `firestore_remote: false` on `/api/health` | `FIREBASE_CREDENTIALS_JSON` not set or invalid. Re-run step 5; the JSON must be the full file content, not just the key. |
| `Error: could not parse secrets: 'PRIVATE': must be in the format NAME=VALUE` when setting the Firebase secret | PowerShell split the multi-line JSON into separate args. Use the `ConvertTo-Json -Compress` + `fly secrets import` form shown in step 5. |
| `gemini_ready: false` | `GEMINI_API_KEY` not set. `fly secrets set GEMINI_API_KEY="..."`. |
| `503` from `/api/ap-scores` even though Gemini key is set | Almost always means the secret rollout hasn't completed. Run `fly status` and check the latest release. |
| Local cache file behavior is weird in production | Don't rely on the local-file cache on Fly — it lives inside the VM and gets wiped on every deploy. Set `FIREBASE_CREDENTIALS_JSON` so Firestore is the cache. |
| Cold-start latency is annoying | Set `min_machines_running = 1` in `fly.toml` and `fly deploy`. |

---

## Why both deploy paths exist

- **Cloud Run** (`docs/DEPLOY_CLOUD_RUN.md`) is the most natural fit
  *if* you can get gcloud installed and on PATH, since the same Google
  project hosts the container and Firestore. No service-account key to
  manage.
- **Fly.io** (this doc) is friendlier on Windows, deploys faster, and
  the CLI is one PowerShell line to install. The tradeoff is that you
  manage a Firebase service-account key as a Fly secret.

You only need one. If both `gcloud` and `flyctl` work for you, Cloud
Run wins on operational simplicity; otherwise Fly is the path of least
resistance.
