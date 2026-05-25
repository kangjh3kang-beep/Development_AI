from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts.release.cutover_checklist import (
    build_cutover_checklist,
    render_cutover_markdown,
)
from scripts.release.release_hardening import (
    ReleaseSmokeError,
    normalize_api_base_url,
    normalize_web_base_url,
    run_observability_smoke,
    run_release_smoke,
    validate_release_assets,
    validate_release_environment,
)
from scripts.release.release_report import (
    build_release_evidence_report,
    render_release_markdown,
)


def _sample_kube_config() -> str:
    raw = "\n".join(
        [
            "apiVersion: v1",
            "clusters: []",
            "contexts: []",
            "current-context: default",
            "users: []",
        ]
    )
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def test_validate_release_environment_accepts_valid_staging_contract() -> None:
    report = validate_release_environment(
        "staging",
        {
            "RELEASE_KUBE_CONFIG": _sample_kube_config(),
            "RELEASE_API_URL": "https://staging-api.propai.io/api/v1",
            "RELEASE_WEB_URL": "https://staging.propai.io/en",
            "RELEASE_SMOKE_TOKEN": "header.payload.signature",
        },
    )

    assert report.errors == []
    assert report.warnings == []


def test_validate_release_environment_flags_bad_production_values() -> None:
    report = validate_release_environment(
        "production",
        {
            "RELEASE_KUBE_CONFIG": "not-kube-config",
            "RELEASE_API_URL": "http://api.propai.io",
            "RELEASE_WEB_URL": "https://example.com",
            "RELEASE_SMOKE_TOKEN": "changeme",
            "SLACK_WEBHOOK_URL": "",
        },
    )

    error_keys = {issue.key for issue in report.errors}
    assert {
        "RELEASE_KUBE_CONFIG",
        "RELEASE_API_URL",
        "RELEASE_WEB_URL",
        "RELEASE_SMOKE_TOKEN",
        "SLACK_WEBHOOK_URL",
    } <= error_keys


def test_normalize_release_urls_strip_api_and_locale_suffixes() -> None:
    assert normalize_api_base_url("https://api.propai.io/api/latest") == "https://api.propai.io"
    assert normalize_api_base_url("https://api.propai.io/api/v1") == "https://api.propai.io"
    assert normalize_web_base_url("https://app.propai.io/en") == "https://app.propai.io"
    assert normalize_web_base_url("https://app.propai.io/ko") == "https://app.propai.io"


def test_validate_release_assets_accepts_current_repo_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    report = validate_release_assets(repo_root)

    assert report.errors == []


def test_validate_release_assets_flags_legacy_deploy_contract(tmp_path: Path) -> None:
    required_files = {
        ".github/workflows/deploy-staging.yml": "python scripts/release/validate_release_env.py --target staging",
        ".github/workflows/deploy-prod.yml": "python scripts/release/validate_release_env.py --target production",
        ".github/workflows/cicd.yml": "Trigger ArgoCD Sync",
        "infra/k8s/base/worker-deployment.yaml": "ghcr.io/propai/propai-backend:latest",
        "infra/k8s/overlays/staging/kustomization.yaml": "namespace: propai-staging",
        "infra/k8s/overlays/production/kustomization.yaml": "namespace: propai",
        "infra/monitoring/prometheus/alert_rules.yml": "APIHighErrorRate",
        "infra/monitoring/alertmanager/alertmanager.yml": "/api/v1/webhooks/alertmanager",
        "infra/monitoring/grafana/dashboards/api-overview.json": "{}",
        "infra/monitoring/grafana/dashboards/database-overview.json": "{}",
        "infra/monitoring/grafana/dashboards/worker-overview.json": "{}",
    }

    for relative_path, contents in required_files.items():
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")

    report = validate_release_assets(tmp_path)

    error_keys = {issue.key for issue in report.errors}
    assert ".github/workflows/cicd.yml" in error_keys
    assert "infra/k8s/base/worker-deployment.yaml" in error_keys
    assert "infra/k8s/overlays/production/kustomization.yaml" in error_keys


def test_build_release_evidence_report_recommends_cutover_when_complete(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    for name in (
        "rollout-api.log",
        "rollout-web.log",
        "rollout-worker.log",
        "kubectl-overview.txt",
        "kubectl-pods.json",
        "kubectl-events.log",
        "release-smoke.log",
        "observability-smoke.log",
    ):
        (artifact_dir / name).write_text("ok", encoding="utf-8")

    report = build_release_evidence_report(
        target="staging",
        workflow_name="Deploy to Staging",
        git_ref="main",
        commit_sha="abcdef123456",
        namespace="propai-staging",
        workflow_run_url="https://github.example/run/1",
        artifact_dir=artifact_dir,
        step_statuses={
            "preflight": "success",
            "build": "success",
            "rollout": "success",
            "release_smoke": "success",
            "observability_smoke": "success",
        },
        image_refs={
            "api": "ghcr.io/org/repo/api:staging-latest",
            "web": "ghcr.io/org/repo/web:staging-latest",
            "worker": "ghcr.io/org/repo/worker:staging-latest",
        },
    )

    markdown = render_release_markdown(report)

    assert report.missing_expected_artifacts == []
    assert report.recommendation.startswith("Ready for cutover review")
    assert "Deploy to Staging" in markdown
    assert "ghcr.io/org/repo/api:staging-latest" in markdown


def test_build_release_evidence_report_flags_incomplete_evidence(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "rollout-api.log").write_text("ok", encoding="utf-8")

    report = build_release_evidence_report(
        target="production",
        workflow_name="Deploy to Production",
        git_ref="v53.0.0",
        commit_sha="abcdef123456",
        artifact_dir=artifact_dir,
        step_statuses={
            "preflight": "success",
            "build": "success",
            "rollout": "failure",
            "release_smoke": "skipped",
            "observability_smoke": "skipped",
        },
        image_refs={},
    )

    assert "rollout-web.log" in report.missing_expected_artifacts
    assert report.recommendation.startswith("Hold release")


def test_build_cutover_checklist_marks_ready_for_review_when_all_gates_pass(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    for name in (
        "rollout-api.log",
        "rollout-web.log",
        "rollout-worker.log",
        "kubectl-overview.txt",
        "kubectl-pods.json",
        "kubectl-events.log",
        "release-smoke.log",
        "observability-smoke.log",
    ):
        (artifact_dir / name).write_text("ok", encoding="utf-8")

    report = build_release_evidence_report(
        target="staging",
        workflow_name="Deploy to Staging",
        git_ref="main",
        commit_sha="abcdef123456",
        artifact_dir=artifact_dir,
        step_statuses={
            "preflight": "success",
            "build": "success",
            "rollout": "success",
            "release_smoke": "success",
            "observability_smoke": "success",
        },
        image_refs={
            "api": "ghcr.io/org/repo/api:staging-latest",
            "web": "ghcr.io/org/repo/web:staging-latest",
            "worker": "ghcr.io/org/repo/worker:staging-latest",
        },
    )

    checklist = build_cutover_checklist(report)
    markdown = render_cutover_markdown(checklist)

    assert checklist.overall_status == "ready-for-review"
    assert checklist.blockers == []
    assert "Overall status: `ready-for-review`" in markdown


def test_build_cutover_checklist_blocks_when_evidence_is_incomplete(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "rollout-api.log").write_text("ok", encoding="utf-8")

    report = build_release_evidence_report(
        target="production",
        workflow_name="Deploy to Production",
        git_ref="v53.0.0",
        commit_sha="abcdef123456",
        artifact_dir=artifact_dir,
        step_statuses={
            "preflight": "success",
            "build": "success",
            "rollout": "failure",
            "release_smoke": "skipped",
            "observability_smoke": "skipped",
        },
        image_refs={
            "api": "ghcr.io/org/repo/api:v53.0.0",
            "web": "",
            "worker": "ghcr.io/org/repo/worker:v53.0.0",
        },
    )

    checklist = build_cutover_checklist(report)

    assert checklist.overall_status == "no-go"
    assert "Kubernetes rollout completed" in checklist.blockers
    assert "Release evidence bundle complete" in checklist.blockers


@pytest.fixture()
def observability_server() -> tuple[str, ThreadingHTTPServer]:
    grafana_token = "grafana-release-token"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/-/ready":
                self._text("Prometheus is Ready.")
                return

            if self.path == "/api/v1/query?query=up":
                self._json({"status": "success", "data": {"resultType": "vector", "result": []}})
                return

            if self.path == "/api/v2/status":
                self._json({"configYAML": "route: default"})
                return

            if self.path == "/api/v2/receivers":
                self._json([{"name": "default"}, {"name": "critical"}])
                return

            if self.path == "/api/health":
                self._auth()
                self._json({"database": "ok", "version": "10.4.0"})
                return

            if self.path == "/api/search?query=PropAI":
                self._auth()
                self._json(
                    [
                        {"uid": "propai-api-overview"},
                        {"uid": "propai-db-overview"},
                        {"uid": "propai-worker-overview"},
                    ]
                )
                return

            self.send_response(404)
            self.end_headers()

        def _auth(self) -> None:
            if self.headers.get("Authorization") != f"Bearer {grafana_token}":
                self.send_response(401)
                self.end_headers()
                raise AssertionError("unexpected grafana token")

        def _json(self, body: object) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _text(self, body: str) -> None:
            raw = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base_url, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_run_observability_smoke_checks_monitoring_endpoints(
    observability_server: tuple[str, ThreadingHTTPServer],
) -> None:
    base_url, _ = observability_server

    checks = run_observability_smoke(
        "staging",
        prometheus_url=base_url,
        alertmanager_url=base_url,
        grafana_url=base_url,
        grafana_api_key="grafana-release-token",
        timeout=2.0,
    )

    assert "observability:prometheus-ready" in checks
    assert "observability:alertmanager-receivers" in checks
    assert "observability:grafana-dashboards" in checks


def test_run_observability_smoke_raises_on_missing_dashboard_uid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(url: str, **_: object) -> dict:
        if "api/search" in url:
            return [{"uid": "propai-api-overview"}]
        if "api/health" in url:
            return {"database": "ok"}
        if "api/v1/query" in url:
            return {"status": "success", "data": {}}
        if "api/v2/status" in url:
            return {"configYAML": "route: default"}
        if "api/v2/receivers" in url:
            return [{"name": "default"}, {"name": "critical"}]
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("scripts.release.release_hardening._request_json", fake_request)
    monkeypatch.setattr(
        "scripts.release.release_hardening._request_text",
        lambda *args, **kwargs: "Prometheus is Ready.",
    )

    with pytest.raises(ReleaseSmokeError, match="missing expected UIDs"):
        run_observability_smoke(
            "production",
            prometheus_url="https://prometheus.propai.io",
            alertmanager_url="https://alertmanager.propai.io",
            grafana_url="https://grafana.propai.io",
            grafana_api_key="grafana-release-token",
            timeout=1.0,
        )


@pytest.fixture()
def release_server() -> tuple[str, ThreadingHTTPServer]:
    token = "release-token"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json(
                    {
                        "status": "healthy",
                        "version": "53.0.0",
                        "services": {"postgres": "healthy", "redis": "healthy", "qdrant": "healthy"},
                    }
                )
                return

            if self.path == "/api/v1/auth/me":
                self._require_token()
                self._json(
                    {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "tenant_id": "22222222-2222-2222-2222-222222222222",
                        "email": "ops@propai.io",
                        "role": "admin",
                    }
                )
                return

            if self.path == "/api/v1/system/version":
                self._require_token()
                self._json(
                    {
                        "app_name": "PropAI",
                        "version": "53.0.0",
                        "environment": "staging",
                        "api_prefixes": ["/api/v1"],
                    }
                )
                return

            if self.path == "/api/v1/system/health/full":
                self._require_token()
                self._json(
                    {
                        "status": "healthy",
                        "version": "53.0.0",
                        "environment": "staging",
                        "services": {"postgres": "healthy", "redis": "healthy", "qdrant": "healthy"},
                        "checked_at": "2026-03-26T12:00:00+00:00",
                    }
                )
                return

            if self.path == "/api/v1/dashboard/stats":
                self._require_token()
                self._json(
                    {
                        "total_projects": 1,
                        "projects_by_status": {"active": 1},
                        "active_webhooks": 0,
                        "active_api_keys": 1,
                        "ai_cost_month_usd": 0.12,
                        "ai_tokens_month": 512,
                    }
                )
                return

            if self.path in {
                "/en",
                "/en/approvals",
                "/en/dashboard/kdx",
                "/en/feasibility",
                "/offline",
                "/en/projects/demo-project",
                "/en/projects/demo-project/contracts",
            }:
                self._html("<!DOCTYPE html><html><body><div id='__next'>PropAI</div></body></html>")
                return

            self.send_response(404)
            self.end_headers()

        def _require_token(self) -> None:
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_response(401)
                self.end_headers()
                raise AssertionError("unexpected token")

        def _json(self, body: dict) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _html(self, body: str) -> None:
            raw = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base_url, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_run_release_smoke_checks_api_and_web_routes(release_server: tuple[str, ThreadingHTTPServer]) -> None:
    base_url, _ = release_server

    checks = run_release_smoke(
        "staging",
        api_base_url=f"{base_url}/api/v1",
        web_base_url=f"{base_url}/en",
        access_token="release-token",
        project_id="demo-project",
        timeout=2.0,
    )

    assert "api:/health" in checks
    assert "api:/api/v1/system/version" in checks
    assert "api:/api/v1/dashboard/stats" in checks
    assert "web:/en/projects/demo-project/contracts" in checks


def test_run_release_smoke_raises_on_unhealthy_api(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_request(*args: object, **kwargs: object) -> dict:
        return {"status": "degraded", "version": "53.0.0", "services": {}}

    monkeypatch.setattr("scripts.release.release_hardening._request_json", broken_request)

    with pytest.raises(ReleaseSmokeError, match="non-healthy status"):
        run_release_smoke(
            "staging",
            api_base_url="https://api.propai.io",
            web_base_url="https://app.propai.io",
            timeout=1.0,
        )
