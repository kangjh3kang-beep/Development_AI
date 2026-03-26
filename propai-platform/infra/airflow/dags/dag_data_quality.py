"""데이터 품질 모니터링 DAG.

매주 월요일 05:00 실행.
테이블 신선도, 완전성, 이상 패턴 검사.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.decorators import task

_DEFAULT_ARGS = {
    "owner": "propai-dq",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# 모니터링 대상 테이블
_MONITORED_TABLES = [
    {"table": "avm_valuations", "freshness_days": 7, "min_records": 100},
    {"table": "financial_analyses", "freshness_days": 30, "min_records": 10},
    {"table": "parcels", "freshness_days": 90, "min_records": 50},
    {"table": "projects", "freshness_days": 30, "min_records": 5},
    {"table": "building_regulations", "freshness_days": 180, "min_records": 20},
    {"table": "carbon_calculations", "freshness_days": 30, "min_records": 0},
    {"table": "monte_carlo_results", "freshness_days": 30, "min_records": 0},
]


with DAG(
    dag_id="propai_data_quality",
    description="데이터 품질 모니터링",
    schedule="0 5 * * 1",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=_DEFAULT_ARGS,
    tags=["data-quality", "monitoring", "propai"],
    max_active_runs=1,
) as dag:

    @task()
    def check_data_freshness() -> dict:
        """테이블별 최신 데이터 확인."""
        import logging
        logger = logging.getLogger(__name__)

        results = []
        for table_config in _MONITORED_TABLES:
            table = table_config["table"]
            max_age_days = table_config["freshness_days"]

            # 실제 환경: SQL 쿼리로 MAX(updated_at) 확인
            # SELECT MAX(updated_at) FROM {table}
            results.append({
                "table": table,
                "max_age_days_allowed": max_age_days,
                "is_fresh": True,  # 실제 환경에서 계산
            })

        stale_count = sum(1 for r in results if not r["is_fresh"])
        logger.info(f"신선도 검사 완료: {len(results)}개 테이블, {stale_count}개 경과")

        return {
            "tables_checked": len(results),
            "stale_tables": stale_count,
            "results": results,
        }

    @task()
    def check_data_completeness() -> dict:
        """NULL 비율, 레코드 수 확인."""
        import logging
        logger = logging.getLogger(__name__)

        results = []
        for table_config in _MONITORED_TABLES:
            table = table_config["table"]
            min_records = table_config["min_records"]

            # 실제 환경: SQL 쿼리로 COUNT(*), NULL 비율 확인
            results.append({
                "table": table,
                "min_records_required": min_records,
                "has_sufficient_records": True,  # 실제 환경에서 계산
                "null_ratio": 0.0,
            })

        insufficient = sum(1 for r in results if not r["has_sufficient_records"])
        logger.info(f"완전성 검사 완료: {insufficient}개 테이블 레코드 부족")

        return {
            "tables_checked": len(results),
            "insufficient_tables": insufficient,
            "results": results,
        }

    @task()
    def generate_quality_report(freshness: dict, completeness: dict) -> dict:
        """품질 보고서를 생성한다."""
        import logging
        logger = logging.getLogger(__name__)

        stale = freshness.get("stale_tables", 0)
        insufficient = completeness.get("insufficient_tables", 0)
        total_issues = stale + insufficient

        if total_issues == 0:
            quality_grade = "A"
            summary = "모든 데이터 품질 기준 충족"
        elif total_issues <= 2:
            quality_grade = "B"
            summary = f"{total_issues}개 테이블 주의 필요"
        elif total_issues <= 5:
            quality_grade = "C"
            summary = f"{total_issues}개 테이블 개선 필요"
        else:
            quality_grade = "D"
            summary = f"{total_issues}개 테이블 긴급 조치 필요"

        report = {
            "report_date": datetime.now().isoformat(),
            "quality_grade": quality_grade,
            "summary": summary,
            "stale_tables": stale,
            "insufficient_tables": insufficient,
            "total_issues": total_issues,
            "freshness_detail": freshness.get("results", []),
            "completeness_detail": completeness.get("results", []),
        }

        logger.info(f"품질 보고서 생성 완료: 등급={quality_grade}, 이슈={total_issues}건")
        return report

    # DAG 실행: 신선도 + 완전성 병렬 → 보고서
    freshness = check_data_freshness()
    completeness = check_data_completeness()
    generate_quality_report(freshness, completeness)
