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
- `ORACLE_WEB_URL`: public web origin for smoke checks
- `ORACLE_HEALTH_URL`: optional, defaults to `${ORACLE_WEB_URL}/health`

## Workflow Dispatch

Use GitHub Actions workflow:

- Workflow name: `Deploy to Oracle Cloud`
- File path: `.github/workflows/deploy-cloudflare.yml` (legacy filename)
- Target: `both`
- Deploy ref: `codex/dashboard-ia-ui-20260629` for this stage branch, or `main` after merge

## Oracle Server Direct Run

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
curl -fsSL "$ORACLE_HEALTH_URL"
curl -fsSL "$ORACLE_WEB_URL/ko" >/tmp/propai-live-home.html
curl -fsSL "$ORACLE_WEB_URL/ko/analysis" >/tmp/propai-live-analysis.html
```

## Completion Criteria

- Web deploy gate passes: type-check, lint, Dashboard IA regression tests
- Oracle `safe-deploy.sh` completes with `DONE web=200 api=200`
- Public smoke checks pass for `/health`, `/ko`, `/ko/analysis`
- Deployment status and smoke evidence are recorded in the implementation log
