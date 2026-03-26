"""Locust 부하 테스트.

STEP 16 품질 게이트: P95 ≤ 3초 (100 동시 사용자)

실행 방법:
  locust -f tests/load/locustfile.py --host http://localhost:8000
  locust -f tests/load/locustfile.py --host http://localhost:8000 \
         --users 100 --spawn-rate 10 --run-time 5m --headless

사용자 유형:
  - PropAIReadUser: 읽기 중심 (프로젝트 목록, 헬스체크) — 60% 비중
  - PropAIWriteUser: 쓰기 중심 (AVM, 법규, 세금, 에스크로) — 30% 비중
  - PropAIAdminUser: 관리 기능 (사용자 정보, 전체 조회) — 10% 비중
"""

from locust import HttpUser, between, tag, task


class _AuthMixin:
    """인증 토큰 공통 로직."""

    token: str = ""

    def on_start(self) -> None:
        """인증 토큰 획득."""
        response = self.client.post("/api/v1/auth/login", json={  # type: ignore[attr-defined]
            "email": "loadtest@propai.kr",
            "password": "loadtest1234!",
        })
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token", "")

    @property
    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


# ──────────────────────────────────────
# 읽기 중심 사용자 (60%)
# ──────────────────────────────────────

class PropAIReadUser(_AuthMixin, HttpUser):
    """프로젝트 조회·헬스체크 중심 사용자. 60% 트래픽 비중."""

    weight = 6
    wait_time = between(1, 3)

    @tag("health")
    @task(5)
    def health_check(self) -> None:
        """헬스체크 — 가장 빈번한 요청."""
        self.client.get("/health")

    @tag("projects")
    @task(3)
    def list_projects(self) -> None:
        """프로젝트 목록 조회."""
        self.client.get("/api/v1/projects", headers=self.auth_headers)

    @tag("projects")
    @task(1)
    def get_project(self) -> None:
        """프로젝트 상세 조회 (임의 UUID)."""
        project_id = "00000000-0000-0000-0000-000000000001"
        self.client.get(
            f"/api/v1/projects/{project_id}",
            headers=self.auth_headers,
            name="/api/v1/projects/[id]",
        )

    @tag("auth")
    @task(1)
    def get_me(self) -> None:
        """현재 사용자 정보 조회."""
        self.client.get("/api/v1/auth/me", headers=self.auth_headers)


# ──────────────────────────────────────
# 쓰기 중심 사용자 (30%)
# ──────────────────────────────────────

class PropAIWriteUser(_AuthMixin, HttpUser):
    """AI 분석·블록체인 기능 호출 사용자. 30% 트래픽 비중."""

    weight = 3
    wait_time = between(2, 5)

    @tag("avm")
    @task(3)
    def avm_estimate(self) -> None:
        """AVM 시세 추정 요청."""
        self.client.post(
            "/api/v1/avm",
            headers=self.auth_headers,
            json={
                "project_id": "00000000-0000-0000-0000-000000000001",
                "address": "서울시 강남구 역삼동",
                "area_sqm": 84.5,
            },
        )

    @tag("regulation")
    @task(2)
    def regulation_check(self) -> None:
        """법규 검토 요청."""
        self.client.post(
            "/api/v1/regulation/check",
            headers=self.auth_headers,
            json={
                "project_id": "00000000-0000-0000-0000-000000000001",
                "regulation_type": "zoning",
                "project_info": {"address": "서울시 강남구"},
            },
        )

    @tag("tax")
    @task(2)
    def tax_calculate(self) -> None:
        """세금 계산 요청."""
        self.client.post(
            "/api/v1/tax/calculate",
            headers=self.auth_headers,
            json={
                "project_id": "00000000-0000-0000-0000-000000000001",
                "tax_type": "acquisition",
                "property_value": 500_000_000,
            },
        )

    @tag("finance")
    @task(1)
    def jeonse_risk(self) -> None:
        """전세 리스크 분석."""
        self.client.post(
            "/api/v1/finance/jeonse-risk",
            headers=self.auth_headers,
            json={
                "project_id": "00000000-0000-0000-0000-000000000001",
                "address": "서울시 강남구 삼성동",
                "jeonse_price": 500_000_000,
                "sale_price": 700_000_000,
            },
        )

    @tag("finance")
    @task(1)
    def union_contribution(self) -> None:
        """조합원 분담금 산정."""
        self.client.post(
            "/api/v1/finance/union-contribution",
            headers=self.auth_headers,
            json={
                "project_id": "00000000-0000-0000-0000-000000000001",
                "total_project_cost": 100_000_000_000,
                "total_appraised_value": 80_000_000_000,
                "individual_appraised_value": 500_000_000,
                "target_area_sqm": 84.0,
                "avg_sale_price_per_sqm": 15_000_000,
            },
        )

    @tag("blockchain")
    @task(1)
    def escrow_status(self) -> None:
        """에스크로 온체인 상태 조회."""
        self.client.get(
            "/api/v1/blockchain/escrow/1",
            headers=self.auth_headers,
            name="/api/v1/blockchain/escrow/[id]",
        )

    @tag("bim")
    @task(1)
    def carbon_calculate(self) -> None:
        """탄소 배출량 산출."""
        self.client.post(
            "/api/v1/bim/carbon",
            headers=self.auth_headers,
            json={
                "project_id": "00000000-0000-0000-0000-000000000001",
                "material_breakdown": [
                    {"type": "IfcWall", "volume_m3": 100},
                    {"type": "IfcSlab", "volume_m3": 50},
                ],
                "total_area_sqm": 5000.0,
            },
        )


# ──────────────────────────────────────
# 관리자 사용자 (10%)
# ──────────────────────────────────────

class PropAIAdminUser(_AuthMixin, HttpUser):
    """관리자 기능 호출 사용자. 10% 트래픽 비중."""

    weight = 1
    wait_time = between(3, 8)

    def on_start(self) -> None:
        """관리자 계정으로 로그인."""
        response = self.client.post("/api/v1/auth/login", json={
            "email": "admin@propai.kr",
            "password": "admin1234!",
        })
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token", "")

    @tag("health")
    @task(3)
    def health_check(self) -> None:
        self.client.get("/health")

    @tag("metrics")
    @task(2)
    def prometheus_metrics(self) -> None:
        """Prometheus 메트릭 수집."""
        self.client.get("/metrics")

    @tag("projects")
    @task(2)
    def list_all_projects(self) -> None:
        """전체 프로젝트 목록 조회."""
        self.client.get("/api/v1/projects", headers=self.auth_headers)

    @tag("auth")
    @task(1)
    def refresh_token(self) -> None:
        """토큰 갱신."""
        self.client.post(
            "/api/v1/auth/refresh",
            headers=self.auth_headers,
            json={"refresh_token": "dummy_refresh_token"},
        )
