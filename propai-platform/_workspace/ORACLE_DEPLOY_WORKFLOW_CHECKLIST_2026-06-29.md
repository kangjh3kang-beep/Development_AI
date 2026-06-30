# Oracle Deploy Workflow Checklist - 2026-06-29

## Purpose

Stage 01 changes must be deployed and verified through the Oracle Cloud path, not Cloudflare Workers.

## Required GitHub Secrets

- `ORACLE_SSH_HOST`: Oracle server host or IP
- `ORACLE_SSH_KEY`: private key with access to the Oracle server
- `ORACLE_SSH_USER`: optional, defaults to `ubuntu`
- `ORACLE_SSH_PORT`: optional, defaults to `22`
- `ORACLE_DEPLOY_PATH`: optional, defaults on remote script to `$HOME/Development_AI`
- `ORACLE_INTERNAL_URL`: optional, defaults to `http://localhost:80`
- `ORACLE_WEB_URL`: public web origin for smoke checks, defaults to `https://4t8t.net`
- `ORACLE_HEALTH_URL`: public backend health URL, defaults to `https://api.4t8t.net/health`

## Workflow Dispatch

Use GitHub Actions workflow:

- Workflow name: `Deploy to Oracle Cloud`
- File path: `.github/workflows/deploy-cloudflare.yml` (legacy filename)
- Target: `both`
- Deploy ref: `codex/dashboard-ia-ui-20260629` for this stage branch, or `main` after merge

## Oracle Server Direct Run

### Frontend A1 - web UI deploy target

Use this target for `4t8t.net` 화면/UI changes:

```bash
ssh -i ~/.oci.key ubuntu@158.179.174.207
cd ~/Development_AI
setsid bash /tmp/codex-safe-deploy.sh web codex/dashboard-ia-ui-20260629 \
  </dev/null >/dev/null 2>&1 &
watch -n5 cat /tmp/deploy_status.txt
```

Confirmed:

- SSH: `ubuntu@158.179.174.207`
- Key: `~/.oci.key`
- Hostname: `4t8t`
- Repo: `/home/ubuntu/Development_AI`
- Script: `/tmp/codex-safe-deploy.sh` or `propai-platform/scripts/safe-deploy.sh`

### Backend A1 - API target, not frontend deploy target

Do not use `168.110.125.89` when verifying whether frontend UI changes were deployed.
That host is the backend/API A1. A publickey failure there does not mean `4t8t.net`
frontend deployment is blocked.

- Backend SSH host: `ubuntu@168.110.125.89`
- Hostname from prior records: `4t8tpropai-backend-a1`

### Generic direct run on the target host

When running directly on Oracle:

```bash
cd ~/Development_AI
VERIFY_BASE_URL=http://localhost:80 \
  bash propai-platform/scripts/safe-deploy.sh both codex/dashboard-ia-ui-20260629
cat /tmp/deploy_status.txt
tail -n 120 /tmp/deploy.log
```

## Required Smoke Checks

```bash
curl -fsSL http://localhost:80/health
curl -fsSL http://localhost:80/ko >/tmp/propai-home.html
curl -fsSL http://localhost:80/ko/analysis >/tmp/propai-analysis.html
```

Public checks should use the configured production/staging origin:

```bash
ORACLE_WEB_URL="${ORACLE_WEB_URL:-https://4t8t.net}"
ORACLE_HEALTH_URL="${ORACLE_HEALTH_URL:-https://api.4t8t.net/health}"
curl -fsSL "$ORACLE_HEALTH_URL"
curl -fsSL "${ORACLE_WEB_URL%/}/ko" >/tmp/propai-live-home.html
curl -fsSL "${ORACLE_WEB_URL%/}/ko/analysis" >/tmp/propai-live-analysis.html
```

## Completion Criteria

- Web deploy gate passes: type-check, lint, Dashboard IA regression tests
- Oracle `safe-deploy.sh` completes with `DONE web=200 api=200`
- Public smoke checks pass for `https://api.4t8t.net/health`, `https://4t8t.net/ko`, `https://4t8t.net/ko/analysis`
- Deployment status and smoke evidence are recorded in the implementation log

## Stage 01 Direct Deploy Evidence

- SSH key used: `~/.oci.key`
- Front server: `ubuntu@158.179.174.207`
- Backend server access checked: `ubuntu@168.110.125.89`
- Deploy target: `web`
- Deploy ref: `codex/dashboard-ia-ui-20260629`
- Deployed commit: `bd22b7a8 docs: use 4t8t live smoke urls`
- Deploy status: `DONE web=200 api=200 @ bd22b7a8 docs: use 4t8t live smoke urls 02:47:12`
- Server disk before cleanup: 99%
- Server disk after cleanup/deploy: 54%
- Internal smoke:
  - `http://localhost:80/ko` 200
  - `http://localhost:80/ko/analysis` 200
  - `http://localhost:80/health` 200
- Public smoke:
  - `https://api.4t8t.net/health` 200
  - `https://4t8t.net/ko` 200
  - `https://4t8t.net/ko/analysis` 200
  - `https://4t8t.net/health` 200
- Note: health body currently reports `status=degraded` because `redis=unhealthy`; this does not block HTTP smoke, but remains an operations follow-up.
