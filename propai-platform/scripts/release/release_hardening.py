"""Reusable deployment hardening helpers for release automation."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_WEB_ROUTES = (
    "/en",
    "/en/approvals",
    "/en/dashboard/kdx",
    "/en/feasibility",
    "/offline",
)

DEFAULT_REQUIRED_ENV: dict[str, tuple[str, ...]] = {
    "staging": (
        "RELEASE_KUBE_CONFIG",
        "RELEASE_API_URL",
        "RELEASE_WEB_URL",
        "RELEASE_SMOKE_TOKEN",
    ),
    "production": (
        "RELEASE_KUBE_CONFIG",
        "RELEASE_API_URL",
        "RELEASE_WEB_URL",
        "RELEASE_SMOKE_TOKEN",
        "SLACK_WEBHOOK_URL",
    ),
}

URL_ENV_KEYS = {"RELEASE_API_URL", "RELEASE_WEB_URL", "SLACK_WEBHOOK_URL"}
PLACEHOLDER_MARKERS = (
    "changeme",
    "your-",
    "your_",
    "example",
    "placeholder",
    "<secret>",
    "<token>",
    "replace-me",
)
HTML_ERROR_MARKERS = (
    "internal server error",
    "application error",
    "route could not be loaded",
)
EXPECTED_GRAFANA_UIDS = (
    "propai-api-overview",
    "propai-db-overview",
    "propai-worker-overview",
)


class ReleaseSmokeError(RuntimeError):
    """Raised when release smoke validation fails."""


@dataclass(slots=True)
class ValidationIssue:
    level: str
    key: str
    message: str


@dataclass(slots=True)
class ValidationReport:
    target: str
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    def add_error(self, key: str, message: str) -> None:
        self.issues.append(ValidationIssue(level="error", key=key, message=message))

    def add_warning(self, key: str, message: str) -> None:
        self.issues.append(ValidationIssue(level="warning", key=key, message=message))


def normalize_api_base_url(value: str) -> str:
    normalized = value.rstrip("/")
    for suffix in ("/api/latest", "/api/v1", "/api/v2"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def normalize_web_base_url(value: str) -> str:
    normalized = value.rstrip("/")
    for suffix in ("/en", "/ko", "/zh-CN"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def build_default_web_routes(project_id: str | None = None) -> list[str]:
    routes = list(DEFAULT_WEB_ROUTES)
    if project_id:
        routes.extend(
            [
                f"/en/projects/{project_id}",
                f"/en/projects/{project_id}/contracts",
            ]
        )
    return routes


def _has_placeholder_value(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _validate_url(key: str, value: str, target: str, report: ValidationReport) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        report.add_error(key, "must be an absolute http(s) URL")
        return
    if target == "production" and parsed.scheme != "https":
        report.add_error(key, "must use https in production")


def _validate_kube_config(value: str) -> str | None:
    if "apiVersion:" in value and "clusters:" in value:
        return None

    try:
        decoded = base64.b64decode(value, validate=True).decode("utf-8")
    except Exception:
        return "must be raw kubeconfig content or a base64-encoded kubeconfig"

    if "apiVersion:" not in decoded or "clusters:" not in decoded:
        return "must decode to a kubeconfig document"
    return None


def validate_release_environment(
    target: str,
    env: Mapping[str, str],
    *,
    extra_required: tuple[str, ...] = (),
) -> ValidationReport:
    target_key = target.lower()
    if target_key not in DEFAULT_REQUIRED_ENV:
        raise ValueError(f"Unsupported target: {target}")

    report = ValidationReport(target=target_key)
    required_keys = (*DEFAULT_REQUIRED_ENV[target_key], *extra_required)

    for key in required_keys:
        value = str(env.get(key, "")).strip()
        if not value:
            report.add_error(key, "is required but missing")
            continue
        if _has_placeholder_value(value):
            report.add_error(key, "contains a placeholder value")
            continue
        if key in URL_ENV_KEYS:
            _validate_url(key, value, target_key, report)
        elif key == "RELEASE_KUBE_CONFIG":
            kube_error = _validate_kube_config(value)
            if kube_error:
                report.add_error(key, kube_error)

    if (
        env.get("RELEASE_API_URL", "").strip()
        and env.get("RELEASE_WEB_URL", "").strip()
        and normalize_api_base_url(env["RELEASE_API_URL"]) == normalize_web_base_url(env["RELEASE_WEB_URL"])
    ):
        report.add_warning(
            "RELEASE_WEB_URL",
            "is identical to RELEASE_API_URL; confirm ingress routing intentionally shares one host",
        )

    return report


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_release_assets(repo_root: Path) -> ValidationReport:
    report = ValidationReport(target="release-assets")

    required_files = {
        ".github/workflows/deploy-staging.yml": (
            "python scripts/release/validate_release_env.py --target staging",
            "python scripts/release/run_release_smoke.py",
            "python scripts/release/run_observability_smoke.py",
            "workflow_dispatch:",
            "kubectl set image deployment/propai-api",
            "kubectl set image deployment/propai-web",
            "kubectl set image deployment/propai-worker",
        ),
        ".github/workflows/deploy-prod.yml": (
            "python scripts/release/validate_release_env.py --target production",
            "python scripts/release/run_release_smoke.py",
            "python scripts/release/run_observability_smoke.py",
            "workflow_dispatch:",
            "kubectl set image deployment/propai-api",
            "kubectl set image deployment/propai-web",
            "kubectl set image deployment/propai-worker",
        ),
        ".github/workflows/cicd.yml": (),
        "infra/k8s/base/worker-deployment.yaml": ("ghcr.io/propai/propai-worker:latest",),
        "infra/k8s/overlays/staging/kustomization.yaml": (
            "namespace: propai-staging",
            "ghcr.io/propai/propai-worker",
        ),
        "infra/k8s/overlays/production/kustomization.yaml": (
            "namespace: propai-production",
            "ghcr.io/propai/propai-worker",
        ),
        "infra/monitoring/prometheus/alert_rules.yml": (
            "APIHighErrorRate",
            "APIDown",
            "WorkerDown",
            "PostgresDown",
            "RedisDown",
        ),
        "infra/monitoring/alertmanager/alertmanager.yml": ("/api/v1/webhooks/alertmanager",),
        "infra/monitoring/grafana/dashboards/api-overview.json": (),
        "infra/monitoring/grafana/dashboards/database-overview.json": (),
        "infra/monitoring/grafana/dashboards/worker-overview.json": (),
    }

    for relative_path, expectations in required_files.items():
        file_path = repo_root / relative_path
        if not file_path.exists():
            report.add_error(relative_path, "required release asset is missing")
            continue
        contents = _read_text(file_path)
        for expectation in expectations:
            if expectation not in contents:
                report.add_error(relative_path, f"missing expected contract: {expectation}")

    cicd_contents = _read_text(repo_root / ".github/workflows/cicd.yml")
    if "Trigger ArgoCD Sync" in cicd_contents or "Deploy to Production" in cicd_contents:
        report.add_error(
            ".github/workflows/cicd.yml",
            "legacy production deployment path is still present",
        )

    return report


def _request_json(
    url: str,
    *,
    token: str | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 8.0,
) -> dict:
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ReleaseSmokeError(f"{url} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise ReleaseSmokeError(f"{url} could not be reached: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseSmokeError(f"{url} did not return valid JSON") from exc


def _request_text(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 8.0,
) -> str:
    request_headers = {"Accept": "text/html"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ReleaseSmokeError(f"{url} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise ReleaseSmokeError(f"{url} could not be reached: {exc.reason}") from exc


def _assert_payload_keys(payload: Mapping[str, object], keys: tuple[str, ...], *, endpoint: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ReleaseSmokeError(f"{endpoint} missing keys: {', '.join(missing)}")


def run_release_smoke(
    target: str,
    *,
    api_base_url: str,
    web_base_url: str,
    access_token: str | None = None,
    routes: tuple[str, ...] | None = None,
    project_id: str | None = None,
    timeout: float = 8.0,
) -> list[str]:
    target_key = target.lower()
    api_base = normalize_api_base_url(api_base_url)
    web_base = normalize_web_base_url(web_base_url)
    executed_checks: list[str] = []

    health = _request_json(f"{api_base}/health", timeout=timeout)
    _assert_payload_keys(health, ("status", "version", "services"), endpoint="/health")
    if health["status"] != "healthy":
        raise ReleaseSmokeError(f"/health returned non-healthy status: {health['status']}")
    executed_checks.append("api:/health")

    if access_token:
        me = _request_json(f"{api_base}/api/v1/auth/me", token=access_token, timeout=timeout)
        _assert_payload_keys(me, ("id", "tenant_id", "email", "role"), endpoint="/api/v1/auth/me")
        executed_checks.append("api:/api/v1/auth/me")

        version_payload = _request_json(
            f"{api_base}/api/v1/system/version",
            token=access_token,
            timeout=timeout,
        )
        _assert_payload_keys(
            version_payload,
            ("app_name", "version", "environment", "api_prefixes"),
            endpoint="/api/v1/system/version",
        )
        if str(version_payload["environment"]).lower() != target_key:
            raise ReleaseSmokeError(
                "/api/v1/system/version returned unexpected environment "
                f"{version_payload['environment']!r}"
            )
        executed_checks.append("api:/api/v1/system/version")

        full_health = _request_json(
            f"{api_base}/api/v1/system/health/full",
            token=access_token,
            timeout=timeout,
        )
        _assert_payload_keys(
            full_health,
            ("status", "version", "environment", "services", "checked_at"),
            endpoint="/api/v1/system/health/full",
        )
        if full_health["status"] != "healthy":
            raise ReleaseSmokeError(
                "/api/v1/system/health/full returned non-healthy status "
                f"{full_health['status']}"
            )
        if str(full_health["environment"]).lower() != target_key:
            raise ReleaseSmokeError(
                "/api/v1/system/health/full returned unexpected environment "
                f"{full_health['environment']!r}"
            )
        if full_health["version"] != health["version"]:
            raise ReleaseSmokeError("health/version mismatch between /health and /system/health/full")
        executed_checks.append("api:/api/v1/system/health/full")

        dashboard = _request_json(
            f"{api_base}/api/v1/dashboard/stats",
            token=access_token,
            timeout=timeout,
        )
        _assert_payload_keys(
            dashboard,
            (
                "total_projects",
                "projects_by_status",
                "active_webhooks",
                "active_api_keys",
                "ai_cost_month_usd",
                "ai_tokens_month",
            ),
            endpoint="/api/v1/dashboard/stats",
        )
        executed_checks.append("api:/api/v1/dashboard/stats")

    for route in routes or tuple(build_default_web_routes(project_id)):
        html = _request_text(f"{web_base}{route}", timeout=timeout)
        lowered = html.lower()
        if "<html" not in lowered and "<!doctype html" not in lowered:
            raise ReleaseSmokeError(f"{route} did not render an HTML document")
        if any(marker in lowered for marker in HTML_ERROR_MARKERS):
            raise ReleaseSmokeError(f"{route} rendered an application error surface")
        executed_checks.append(f"web:{route}")

    return executed_checks


def run_observability_smoke(
    target: str,
    *,
    prometheus_url: str,
    alertmanager_url: str,
    grafana_url: str,
    grafana_api_key: str | None = None,
    timeout: float = 8.0,
) -> list[str]:
    target_key = target.lower()
    executed_checks: list[str] = []

    prometheus_base = prometheus_url.rstrip("/")
    alertmanager_base = alertmanager_url.rstrip("/")
    grafana_base = grafana_url.rstrip("/")
    grafana_headers = (
        {"Authorization": f"Bearer {grafana_api_key}"} if grafana_api_key else None
    )

    readiness = _request_text(f"{prometheus_base}/-/ready", timeout=timeout)
    if "ready" not in readiness.lower():
        raise ReleaseSmokeError("Prometheus readiness endpoint did not report ready")
    executed_checks.append("observability:prometheus-ready")

    query_payload = _request_json(
        f"{prometheus_base}/api/v1/query?{urlencode({'query': 'up'})}",
        timeout=timeout,
    )
    if query_payload.get("status") != "success":
        raise ReleaseSmokeError("Prometheus query API did not return success")
    executed_checks.append("observability:prometheus-query")

    status_payload = _request_json(f"{alertmanager_base}/api/v2/status", timeout=timeout)
    if "configYAML" not in status_payload:
        raise ReleaseSmokeError("Alertmanager status payload missing configYAML")
    executed_checks.append("observability:alertmanager-status")

    receivers_payload = _request_json(
        f"{alertmanager_base}/api/v2/receivers",
        timeout=timeout,
    )
    receiver_names = {receiver.get("name") for receiver in receivers_payload if isinstance(receiver, dict)}
    if {"default", "critical"} - receiver_names:
        raise ReleaseSmokeError("Alertmanager receivers missing default or critical")
    executed_checks.append("observability:alertmanager-receivers")

    grafana_health = _request_json(
        f"{grafana_base}/api/health",
        headers=grafana_headers,
        timeout=timeout,
    )
    if str(grafana_health.get("database", "")).lower() != "ok":
        raise ReleaseSmokeError("Grafana health check did not report database=ok")
    executed_checks.append(f"observability:grafana-health:{target_key}")

    if grafana_api_key:
        search_payload = _request_json(
            f"{grafana_base}/api/search?{urlencode({'query': 'PropAI'})}",
            headers=grafana_headers,
            timeout=timeout,
        )
        grafana_uids = {item.get("uid") for item in search_payload if isinstance(item, dict)}
        missing_uids = [uid for uid in EXPECTED_GRAFANA_UIDS if uid not in grafana_uids]
        if missing_uids:
            raise ReleaseSmokeError(
                "Grafana dashboard search is missing expected UIDs: "
                + ", ".join(missing_uids)
            )
        executed_checks.append("observability:grafana-dashboards")

    return executed_checks
