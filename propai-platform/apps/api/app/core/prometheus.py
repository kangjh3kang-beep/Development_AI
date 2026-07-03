"""Prometheus 메트릭 수집.

인메모리로 요청 카운터, 지연시간 히스토그램, 활성 연결 게이지를 관리하며,
/metrics 엔드포인트에서 Prometheus exposition format으로 내보낸다.
prometheus_client 라이브러리 없이도 동작한다.
"""

from collections import defaultdict


class PrometheusMetrics:
    """인메모리 Prometheus 메트릭 수집기."""

    def __init__(self, namespace: str = "propai"):
        self._namespace = namespace
        self._request_count: dict[str, int] = defaultdict(int)
        self._request_latency: dict[str, list[float]] = defaultdict(list)
        self._active_connections: int = 0
        self._error_count: dict[str, int] = defaultdict(int)
        self._custom_gauges: dict[str, float] = {}

    def record_request(self, method: str, path: str, status: int,
                       duration_sec: float) -> None:
        """요청 기록."""
        key = f"{method}:{path}:{status}"
        self._request_count[key] += 1
        self._request_latency[key].append(duration_sec)
        if status >= 400:
            error_key = f"{method}:{path}"
            self._error_count[error_key] += 1

    def inc_connections(self) -> None:
        """활성 연결 수 증가."""
        self._active_connections += 1

    def dec_connections(self) -> None:
        """활성 연결 수 감소."""
        self._active_connections = max(0, self._active_connections - 1)

    def set_gauge(self, name: str, value: float) -> None:
        """커스텀 게이지 설정."""
        self._custom_gauges[name] = value

    def get_gauge(self, name: str) -> float | None:
        """커스텀 게이지 조회."""
        return self._custom_gauges.get(name)

    @property
    def total_requests(self) -> int:
        """전체 요청 수."""
        return sum(self._request_count.values())

    @property
    def total_errors(self) -> int:
        """전체 에러 수."""
        return sum(self._error_count.values())

    @property
    def active_connections(self) -> int:
        """활성 연결 수."""
        return self._active_connections

    def get_latency_stats(self, method: str, path: str,
                          status: int) -> dict:
        """특정 요청의 지연시간 통계."""
        key = f"{method}:{path}:{status}"
        latencies = self._request_latency.get(key, [])
        if not latencies:
            return {"count": 0, "avg": 0, "min": 0, "max": 0, "p50": 0, "p99": 0}
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        return {
            "count": n,
            "avg": round(sum(sorted_lat) / n, 6),
            "min": round(sorted_lat[0], 6),
            "max": round(sorted_lat[-1], 6),
            "p50": round(sorted_lat[n // 2], 6),
            "p99": round(sorted_lat[int(n * 0.99)], 6),
        }

    def get_metrics(self) -> str:
        """Prometheus exposition format 문자열 반환."""
        ns = self._namespace
        lines = []

        # 요청 카운터
        lines.append(f"# HELP {ns}_http_requests_total 전체 HTTP 요청 수")
        lines.append(f"# TYPE {ns}_http_requests_total counter")
        for key, count in self._request_count.items():
            method, path, status = key.split(":", 2)
            lines.append(
                f'{ns}_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )

        # 활성 연결 게이지
        lines.append(f"# HELP {ns}_active_connections 활성 연결 수")
        lines.append(f"# TYPE {ns}_active_connections gauge")
        lines.append(f"{ns}_active_connections {self._active_connections}")

        # 에러 카운터
        lines.append(f"# HELP {ns}_http_errors_total HTTP 에러 수")
        lines.append(f"# TYPE {ns}_http_errors_total counter")
        for key, count in self._error_count.items():
            method, path = key.split(":", 1)
            lines.append(
                f'{ns}_http_errors_total{{method="{method}",path="{path}"}} {count}'
            )

        # 커스텀 게이지
        for name, value in self._custom_gauges.items():
            lines.append(f"# HELP {ns}_{name} 커스텀 게이지")
            lines.append(f"# TYPE {ns}_{name} gauge")
            lines.append(f"{ns}_{name} {value}")

        return "\n".join(lines) + "\n"

    def get_summary(self) -> dict:
        """메트릭 요약 딕셔너리."""
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "active_connections": self._active_connections,
            "unique_endpoints": len(self._request_count),
            "custom_gauges": dict(self._custom_gauges),
        }

    def reset(self) -> None:
        """모든 메트릭 초기화."""
        self._request_count.clear()
        self._request_latency.clear()
        self._error_count.clear()
        self._custom_gauges.clear()
        self._active_connections = 0


_metrics = PrometheusMetrics()


def get_prometheus_metrics() -> PrometheusMetrics:
    """전역 PrometheusMetrics 반환."""
    return _metrics
