"""필드수준 계보 참조 계약 (v4.0 Wave2 W2-2 — [필드수준 계보] 조항 실용 1차).

SPEC v4 [필드수준 계보] 계약(스펙 원문):
  ReportClaim → AnalysisResult field → CalcTrace → Rule/Formula → Normalized Fact
  → SourceSnapshot → Original bytes. 이 사슬이 끊기면 UNTRACED(발행 차단 후보)다.

★실구현과 스펙 원문의 차이(R1 R2 — 정직 표기, 반드시 읽을 것): 스펙 원문 그대로라면
  SourceSnapshot(원본 바이트)까지 닿지 않는 모든 값은 UNTRACED여야 한다. 이번 1차는
  그렇게 엄격하게 구현하지 않았다 — STATIC_CACHE·LIVE_API(아래)는 스냅샷이 없어도
  traced=True(추적됨)로 완화한다. 완화 근거: 이 계약은 어댑터가 점진 채택해야 하는데,
  스냅샷 없는 모든 실제값을 전부 UNTRACED로 잡으면 현재 거의 모든 조례·정적데이터
  경로가 경고 대상이 되어 soft 경고가 의미를 잃는다(노이즈). 그래서 "완전 미상(UNKNOWN)"
  과 "출처는 정직하게 명시했지만 스냅샷은 아직 없음(STATIC_CACHE/LIVE_API)"을 구분해,
  후자만 완화된 traced=True를 준다 — **SNAPSHOT만이 스펙 원문이 말하는 '원본 바이트까지
  진짜 추적됨'을 보증**하고, STATIC_CACHE/LIVE_API는 "출처 명시 수준"의 더 약한 보증이다.
  스냅샷이 실제로 연동되면(예: MOLEG 커넥터가 SourceSnapshot opt-in) 그 값의 등급을
  SNAPSHOT+snapshot_fingerprint로 승격해야 한다(하강 없는 단방향 승격 — 아래 참고).

★이 모듈이 정의하는 것은 "값"이 아니라 "참조 계약"이다(스펙 원문 그대로): 실제 스냅샷
  바이트·계산 트레이스를 다시 담지 않고, 그 필드의 계보가 사슬의 어느 단계에서 왔는지를
  가리키는 경량 태그만 만든다. ``Evidence.lineage``(report/render/model.py)에 이 태그의
  ``to_dict()`` 결과가 실려 보고서 표면까지 전달된다.

스파이크 결론(★근거 — 그린필드 금지, 이 파일이 실제로 풀어야 했던 문제):
- 기존 계보 자산 3곳을 실측했다: ① analysis_ledger(해시체인 — 분석 결과 자체의 무결성만
  보증, 필드 단위 출처는 모름) ② ledger/lineage.py(analysis_lineage — 분석↔분석 파생 DAG,
  '이 분석이 어느 분석에서 파생됐는지'는 알아도 '이 숫자 하나가 어느 원본 바이트에서 왔는지'는
  모름) ③ regulation_analysis_service의 far_basis_detail 근거체인(#406) — 계산 계층(법정
  범위→조례→계획상한→구조상한) 서술은 있지만 Evidence 객체로 정착되지 않고 dict 필드로만
  존재해 보고서(ReportClaim) 표면까지 도달하지 못한다. → 셋 다 "필드 하나의 계보"를 표현하는
  참조 계약은 없었다(이번 모듈이 메우는 공백).
- 절단점(정확한 위치): calc_effective_far(far_tier_service.py)가 만드는 far_basis_detail은
  법정범위/조례값/계획상한/인센티브/최종근거를 이미 계층별로 분리해 갖고 있는데, 이 값이
  routers/auto_zoning.py의 _enrich_effective_and_special()을 거치며 far_eff/bcr_eff/far_basis
  (문자열)만 남고 far_basis_detail 자체와 조례 출처(ordinance.source/provenance)는 그 자리에서
  버려졌다 — land_adapter가 만드는 보고서까지 한 번도 도달한 적이 없다(land-report 핸들러가
  parcels 리스트에 bcr_pct/far_pct 숫자만 실어 보냄). 이번 W2-2가 이 절단점을 메운다.
- 조례값·법제처API 값의 정직한 등급(★핵심 설계결정): ordinance_service.ORDINANCE_CACHE는
  정적 캐시라 W2-1 SourceSnapshot이 없다(SourceSnapshot은 VWorld·G2B 두 커넥터만 opt-in
  — source_snapshot.py 모듈독스트링 참고). "스냅샷이 없다"는 사실을 SNAPSHOT으로 거짓
  격상하지 않고, 별도(더 낮은) 등급 STATIC_CACHE로 표현한다. 법제처 API(법정상한이 아닌
  실시간 조회)도 마찬가지로 아직 SourceSnapshot 미연동(W2-1은 VWorld·G2B만 opt-in)이지만,
  **출처가 정직하게 명시된 실시간 조회**라는 점에서 완전 미상(UNKNOWN)과는 다르다 — 그래서
  같은 완화 논리로 LIVE_API 등급을 신설한다(R1 R2 반영: 정적캐시보다 오히려 신선한 실시간
  값이 UNKNOWN으로 더 낮게 취급되던 등급 역전을 해소). MOLEG 커넥터의 SourceSnapshot
  opt-in은 W2-3 이후 과제 — 연동되는 즉시 이 LIVE_API 분기를 SNAPSHOT으로 승격한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fact_status import VALID_FACT_STATUSES

# 계보 등급(source_kind) 6종 + UNKNOWN — 값이 사슬의 어느 단계에서 왔는지.
#   SNAPSHOT     : SourceSnapshot(W2-1) 1건에 연결됨 — 원본 바이트까지 재현 가능(스펙 원문
#                  그대로의 '진짜 추적됨'은 이 등급뿐).
#   STATIC_CACHE : 코드에 내장된 정적 캐시값(예: ORDINANCE_CACHE) — 출처는 있으나 스냅샷 없음
#                  (완화: traced=True — 위 모듈독스트링 참고).
#   LIVE_API     : 출처가 명시된 실시간 외부 API 조회(예: 법제처 MOLEG) — 아직 SourceSnapshot
#                  미연동이라 원본 바이트 재현은 못 하지만, 출처는 정직하게 명시됨(완화:
#                  traced=True — STATIC_CACHE와 동일 논리). 스냅샷 연동 시 SNAPSHOT으로 승격.
#   CALC         : 결정론적 계산식(far_basis 등)으로 산출된 값 — CalcTrace 단계.
#   RULE         : 법령·시행령 등 규칙/공식 자체(계산이 아니라 규칙 인용).
#   USER_INPUT   : 사용자가 직접 입력한 값(외부 검증 불가·입력 그대로).
#   UNKNOWN      : 위 어느 것도 아니거나 아직 계보를 채우지 않음 — traced=False(미추적).
LINEAGE_SOURCE_KINDS: frozenset[str] = frozenset({
    "SNAPSHOT", "STATIC_CACHE", "LIVE_API", "CALC", "RULE", "USER_INPUT", "UNKNOWN",
})


def _normalize_source_kind(value: str | None) -> str:
    """계보 등급 후보를 정규화한다. 유효하지 않으면 UNKNOWN(정직 하강 — 조기거부 아님).

    ★UNKNOWN을 예외가 아니라 안전한 기본값으로 두는 이유: 이 계약은 소비처(어댑터)가 점진
    채택하는 선택적 필드다. 오탈자·미지원 값이 있다고 렌더링 자체를 막으면(예외) 오히려
    보고서 생성을 깨뜨린다 — 정직하게 '미추적'으로 떨어뜨리고 publish_gate가 soft 경고로
    잡아내는 편이 이 계약의 점진 채택 철학(Evidence.claim_type과 동형)과 맞는다.
    """
    if value is None:
        return "UNKNOWN"
    v = str(value).strip().upper()
    return v if v in LINEAGE_SOURCE_KINDS else "UNKNOWN"


@dataclass(frozen=True)
class LineageRef:
    """필드 1개의 계보 참조(값이 아니라 태그) — 경량·직렬화 가능(dict).

    Attributes:
        source_kind: LINEAGE_SOURCE_KINDS 중 하나(정규화 후 미지정/불법값은 UNKNOWN).
        snapshot_fingerprint: SourceSnapshot.request_fingerprint(있을 때만 — 없으면 None,
            날조 금지). source_kind=SNAPSHOT 이 아니어도 필드 자체는 항상 존재(단순 선택적).
            ★LOW(R1 R2): 이번 W2-2 1차 시점에는 이 필드를 실제로 채우는 생산자가 없다
            (STATIC_CACHE/LIVE_API 분기 모두 스냅샷이 없어 None) — SNAPSHOT 등급이 실제로
            배선되는 후속(W2-3 MOLEG SourceSnapshot opt-in 등)에서 사용될 자리다.
        fact_status: FactStatus(provenance/fact_status.py) 값 문자열 또는 None(미분류).
        basis: 이 계보가 성립하는 근거 문자열(사람이 읽는 설명 — 예: 법령 조문, 캐시
            원문대조 일자, 계산 최종근거 서술).
    """

    source_kind: str = "UNKNOWN"
    snapshot_fingerprint: str | None = None
    fact_status: str | None = None
    basis: str | None = None

    def __post_init__(self) -> None:
        # frozen dataclass 라 object.__setattr__ 로 정규화값을 되써야 한다(정규화 후 값 고정).
        object.__setattr__(self, "source_kind", _normalize_source_kind(self.source_kind))
        if self.fact_status is not None and self.fact_status not in VALID_FACT_STATUSES:
            raise ValueError(f"fact_status 는 FactStatus 값 또는 None 이어야 합니다: {self.fact_status!r}")

    @property
    def traced(self) -> bool:
        """계보가 사슬 끝(원본)까지 추적됐는지(파생값·조기 계산 금지 — source_kind 만으로 판정).

        ★불변식(1차 구현 — R1 R2 정직 표기): "UNKNOWN이면 False, 그 외(SNAPSHOT/STATIC_CACHE/
        LIVE_API/CALC/RULE/USER_INPUT)는 True". 스펙 원문의 "SourceSnapshot까지 안 닿으면
        UNTRACED"를 문자 그대로 구현한 것은 아니다 — STATIC_CACHE·LIVE_API 는 스냅샷이 없어도
        '출처가 정직하게 명시'되어 있으면 완화된 traced=True 로 본다(모듈 독스트링의 완화
        근거 참고). 완전히 미상(UNKNOWN)일 때만 미추적이다. SNAPSHOT만이 스펙 원문 수준의
        진짜 원본 바이트 추적을 보증한다.
        """
        return self.source_kind != "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        """Evidence.lineage 에 실릴 경량 직렬화(dict) — traced 는 파생값이라 함께 동봉한다."""
        return {
            "source_kind": self.source_kind,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "fact_status": self.fact_status,
            "basis": self.basis,
            "traced": self.traced,
        }


def lineage_from_dict(data: dict[str, Any] | None) -> LineageRef | None:
    """직렬화된 dict → LineageRef 역직렬화(감사·재구성용). 형식이 안 맞으면 None(날조 금지)."""
    if not isinstance(data, dict):
        return None
    try:
        return LineageRef(
            source_kind=data.get("source_kind"),
            snapshot_fingerprint=data.get("snapshot_fingerprint"),
            fact_status=data.get("fact_status"),
            basis=data.get("basis"),
        )
    except ValueError:
        return None


__all__ = ["LINEAGE_SOURCE_KINDS", "LineageRef", "lineage_from_dict"]
