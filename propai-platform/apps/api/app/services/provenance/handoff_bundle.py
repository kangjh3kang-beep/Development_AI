"""Stage Handoff bundle 공용 계약 (v4.0 Wave2 W2-3 — [단계 인계계약 Stage Handoff Contract] 실용 1차).

SPEC v4 원문(§[단계 인계계약]):
  "각 Px는 단순 JSON 한 개가 아니라 manifest.json(bundle_id·producer·version·created_at·
  parent_bundle_ids·checksums)을 포함한 immutable bundle을 생성한다 ... decision.json:
  PASS/CONDITIONAL/BLOCKED. 소비 단계는 bundle checksum, schema version, Gate decision,
  expiry를 검증한 뒤에만 실행한다."

이 파일이 푸는 문제(쉬운 설명):
- 지금까지 단계간 인계는 두 극단이었다 — ① submission_bundle(report/submission_bundle.py)처럼
  "제출용 zip 1건"에 한정된 무겁고 특수한 계약, ② project_pipeline.py의
  SiteToDesignPayload/DesignToCostPayload처럼 "그냥 dict/Pydantic 모델을 다음 단계 함수가
  그대로 읽는" 무계약 전달. 이 모듈은 그 사이 — 어떤 payload(dict)든 감쌀 수 있는 경량
  범용 계약(bundle_id·checksum·decision·expiry)을 제공해, 필요한 소비처가 점진적으로
  seal()/verify_for_consumption()을 채택하게 한다(claim_type·lineage와 동일한 "점진 채택"
  철학 — LineageRef/GateResult 선례와 동형).

★스파이크 결론(그린필드 금지 — 근거):
- submission_bundle 은 이미 bundle_hash(=payload_checksum)·manifest(=payload)·양방향 무결성
  검증(verify_bundle)을 갖추고 있었지만, bundle_id/parent_bundle_ids/decision/expiry 개념은
  없었다(제출 시점 1회성 zip이라 "인계 대상"이라는 발상 자체가 없었음) — 이번 W2-3이 그
  공백(계보·조건부 통과·소비 전 사전검증)을 메운다. submission_bundle 은 재작성하지 않는다
  — 이 공용 계약의 "특수 사례"로 문서화하고(``from_submission_bundle_manifest``), 그 파일이
  이미 쓰는 정규화 JSON 해시 알고리즘(키정렬·ensure_ascii=False·구분자 고정·default=str)을
  이 모듈도 동일하게 재사용해 두 계약의 checksum이 같은 입력에 대해 항상 같은 값을 낸다
  (알고리즘 동일성은 test_handoff_bundle.py의 상호운용 테스트로 고정).
- 대표 1경로 선정(orphan handoff 최다 이력 클래스): project_pipeline.py의
  ``SiteToDesignPayload``(부지분석→설계) — 코드 주석에 이미 "0.0=미산정 센티널"·
  "W3-8 assumed_fields 정직 표기"·"_restore_previous 복원 시 60/200 날조 금지" 등 이 정확한
  경계에서 반복 발생한 결함 패턴이 명시돼 있고, 세션 메모리에도 "실효FAR 미전달→250%폴백"
  (project_design_studio_refactor)·"필드는 최종표면까지 추적(orphan handoff 2연발)"
  (project_analysis_integrity_storyline) 이 같은 경계 부류로 기록돼 있다. 실제 배선은
  project_pipeline.py의 ``_run_site_analysis``(producer, seal)→``_run_design``(consumer,
  verify_for_consumption)에 있다.

★hard/soft 경계(무회귀 — W2-2 UNTRACED와 동일 전략, 반드시 지킬 것):
  - **hard(예외 전파, 소비 자체를 막음)**: payload_checksum 불일치(=봉인 이후 payload가
    변조됨) 단 하나뿐이다. 무결성은 타협 불가 — soft로 격하하지 않는다.
  - **soft(경고만, 절대 소비를 막지 않음)**: decision=BLOCKED·만료(expiry 경과)·
    schema_version 미허용은 모두 ``HandoffBundleRejectedError`` 하위 예외로 구분해 던지되,
    소비측(예: project_pipeline._run_design)이 이를 catch해 경고 로그+표식만 남기고 기존
    로직을 그대로 진행한다 — 채택률 확보 전까지는 hard 승격하지 않는다(W2-2 UNTRACED 문서와
    동일 문구·동일 철학).
  - 이 모듈 자체는 hard/soft를 강제하지 않는다 — ``verify_for_consumption()``은 위반이면
    항상 예외를 던질 뿐이고, 그 예외를 hard로 볼지 soft로 흡수할지는 호출부의 몫이다(예외
    타입으로 구분 가능하게 만든 것이 이 모듈의 책임).

★decision 어휘와 W1-A/W1-C 정합: PASS/CONDITIONAL/BLOCKED 3값은 W1-A ApprovalState의
  선형 전이 사슬과는 다른 축(승인 상태가 아니라 "이 인계 결과를 다음 단계가 그대로 써도
  되는가")이라 ApprovalState를 재사용하지 않고 별도 StrEnum으로 신설한다. 대신 W1-C
  GateResult(violations/warnings)와는 값 형태가 근접해, ``decision_from_gate_result()``로
  변환 헬퍼를 둔다(violations 있음→BLOCKED, warnings만 있음→CONDITIONAL, 둘 다 없음→PASS).
  publish_gate.GateResult를 이 모듈이 직접 import하지 않는 이유는 provenance→report 역방향
  의존을 만들지 않기 위함이다(호출부가 이미 계산한 ok/has_warnings 두 bool만 받는다).

★영속 불요(과업 범위): 이 계약은 "전달 시점"에만 의미가 있는 계약이라 새 테이블을 만들지
  않는다. 필요하면 호출부가 기존 구조(analysis_ledger 등)에 payload를 실어 나른다 — 이
  모듈은 순수 인메모리 계약(dataclass)이다.

신규 의존성 0: uuid·hashlib·json·copy·datetime 는 표준 라이브러리.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

# 이 계약의 schema_version 기본값 — submission_bundle.BUNDLE_VERSION과 동일 명명 관례
# ("propai.<계약이름>/<메이저>.<마이너>").
CURRENT_SCHEMA_VERSION = "propai.handoff_bundle/1.0"


class HandoffDecision(StrEnum):
    """단계 인계 결정 3원형 — SPEC v4 decision.json 어휘 그대로(W1-A ApprovalState와 별도 축)."""

    PASS = "PASS"                # 조건 없이 그대로 소비 가능
    CONDITIONAL = "CONDITIONAL"  # conditions에 명시된 제약 하에 소비 가능(예: 가정치 폴백 적용됨)
    BLOCKED = "BLOCKED"          # 소비 불가(생산 단계 자체가 실패/거부됨)


def decision_from_gate_result(ok: bool, *, has_warnings: bool = False) -> str:
    """W1-C GateResult(violations/warnings) → 이 계약의 decision 어휘 매핑(선택적 헬퍼).

    ok=False(violations 존재) → BLOCKED. ok=True 인데 warnings 있음 → CONDITIONAL(연성 조건부
    통과). ok=True·warnings 없음 → PASS. GateResult 객체 자체가 아니라 호출부가 이미 계산한
    두 bool만 받아, provenance → report.render 역방향 의존을 만들지 않는다.
    """
    if not ok:
        return HandoffDecision.BLOCKED.value
    if has_warnings:
        return HandoffDecision.CONDITIONAL.value
    return HandoffDecision.PASS.value


class HandoffBundleRejectedError(Exception):
    """소비 거부 공통 베이스 — bundle_id·producer·사유를 항상 명확히 담는다.

    ★hard/soft 판단은 이 클래스가 아니라 서브클래스(타입)로 한다 — 호출부는
    ``except HandoffChecksumMismatchError: raise`` 로 무결성 위반만 재전파(hard)하고,
    나머지 ``HandoffBundleRejectedError``는 catch해 soft 경고로 흡수한다.
    """

    def __init__(self, bundle: HandoffBundle, reason: str) -> None:
        self.bundle_id = bundle.bundle_id
        self.producer = bundle.producer
        self.reason = reason
        super().__init__(f"[{bundle.producer}:{bundle.bundle_id}] 인계 번들 소비 거부 — {reason}")


class HandoffChecksumMismatchError(HandoffBundleRejectedError):
    """★hard 전용 — payload가 seal() 이후 변조됨(무결성 위반, soft 격하 금지)."""

    def __init__(self, bundle: HandoffBundle, expected: str, actual: str) -> None:
        self.expected_checksum = expected
        self.actual_checksum = actual
        super().__init__(
            bundle,
            f"payload_checksum 불일치(변조 의심): expected={expected} actual={actual}",
        )


class HandoffBlockedDecisionError(HandoffBundleRejectedError):
    """soft(호출부 판단) — decision=BLOCKED인 번들을 소비하려 함."""

    def __init__(self, bundle: HandoffBundle) -> None:
        super().__init__(bundle, "decision=BLOCKED(생산 단계가 이 인계를 거부함)")


class HandoffExpiredError(HandoffBundleRejectedError):
    """soft(호출부 판단) — expiry 경과."""

    def __init__(self, bundle: HandoffBundle, now_iso: str) -> None:
        super().__init__(bundle, f"만료됨(expiry={bundle.expiry!r} now={now_iso!r})")


class HandoffSchemaVersionError(HandoffBundleRejectedError):
    """soft(호출부 판단) — schema_version이 소비측 허용목록에 없음."""

    def __init__(self, bundle: HandoffBundle, allowed: set[str]) -> None:
        super().__init__(
            bundle,
            f"schema_version={bundle.schema_version!r} 허용되지 않음(allowed={sorted(allowed)})",
        )


def _sha256_bytes(data: bytes) -> str:
    """바이트의 sha256 지문(16진수 64자) — submission_bundle._sha256_bytes와 동일 알고리즘."""
    return hashlib.sha256(data or b"").hexdigest()


def _canonical_json_bytes(obj: Any) -> bytes:
    """정규화 JSON(키 정렬·공백 제거·한글 원문) 바이트.

    ★submission_bundle._canonical_json_bytes와 파라미터가 완전히 동일하다(sort_keys=True·
    ensure_ascii=False·separators=(",", ":")·default=str) — 같은 dict라면 두 모듈이 항상 같은
    checksum을 낸다(어댑터 상호운용의 전제, test_handoff_bundle.py로 고정).
    """
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _to_aware(dt: datetime) -> datetime:
    """naive datetime을 UTC로 간주해 tzinfo를 채운다(비교 시 naive/aware 혼합 TypeError 방지)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class HandoffBundle:
    """단계 인계 번들 — SPEC v4 [단계 인계계약]의 실용 1차(경량 인메모리 계약).

    Attributes:
        bundle_id: 이 번들의 고유 식별자(uuid4 hex).
        producer: 이 번들을 만든 단계명(예: "site_analysis").
        created_at: 봉인 시각(ISO8601, UTC).
        payload_checksum: payload의 canonical JSON sha256(무결성 지문).
        payload: 실제 인계 데이터(dict) — seal() 시점의 깊은 복사본(스냅샷).
        schema_version: payload 스키마 버전(소비측 allowlist 대조 대상).
        decision: HandoffDecision 값 중 하나(PASS/CONDITIONAL/BLOCKED).
        conditions: decision=CONDITIONAL일 때 그 제약 사유 목록(그 외에도 비어있지 않을 수
            있음 — 소비측 참고용 자유 텍스트, 강제 스키마 아님).
        parent_bundle_ids: 이 번들이 파생된 상위 번들 id 목록(계보 — W2-2 LineageRef와는
            "필드 값의 출처"가 아니라 "번들 자체의 상위 인계"라는 별개 축).
        expiry: 만료 시각(ISO8601) 또는 None(무제한).
    """

    bundle_id: str
    producer: str
    created_at: str
    payload_checksum: str
    payload: dict[str, Any]
    schema_version: str = CURRENT_SCHEMA_VERSION
    decision: str = HandoffDecision.PASS.value
    conditions: list[str] = field(default_factory=list)
    parent_bundle_ids: list[str] = field(default_factory=list)
    expiry: str | None = None

    def __post_init__(self) -> None:
        # decision 값 자체의 무결성 — LineageRef.source_kind/ApprovalState 선례와 달리 이
        # 필드는 "정직 하강"(UNKNOWN 폴백) 대상이 아니다. 잘못된 decision을 UNKNOWN류로
        # 조용히 격하하면 BLOCKED를 다른 값으로 오인해 소비 거부가 무력화될 수 있어(안전
        # 회귀), 즉시 거부(raise)한다 — GateResult류의 "무날조" 원칙과 동일하게 조기 실패.
        valid = {d.value for d in HandoffDecision}
        if self.decision not in valid:
            raise ValueError(
                f"decision 은 {sorted(valid)} 중 하나여야 합니다: {self.decision!r}"
            )

    def verify_for_consumption(
        self,
        *,
        allowed_schema_versions: Iterable[str] | None = None,
        now: str | None = None,
    ) -> None:
        """소비 전 사전검증 — checksum 일치·decision!=BLOCKED·미만료·schema_version 허용목록.

        위반 시 ``HandoffBundleRejectedError`` 하위 예외를 던진다(항상 예외 — 반환값 없음).
        검사 순서: checksum(★hard 전용, 항상 최우선) → decision → expiry → schema_version.
        checksum이 어긋나면 이후 검사는 의미가 없으므로(payload 자체를 신뢰할 수 없음)
        가장 먼저 검사한다.
        """
        recomputed = _sha256_bytes(_canonical_json_bytes(self.payload))
        if recomputed != self.payload_checksum:
            raise HandoffChecksumMismatchError(self, self.payload_checksum, recomputed)

        if self.decision == HandoffDecision.BLOCKED.value:
            raise HandoffBlockedDecisionError(self)

        if self.expiry:
            now_dt = _to_aware(_parse_iso(now)) if now else datetime.now(UTC)
            try:
                expiry_dt = _to_aware(_parse_iso(self.expiry))
            except ValueError as exc:
                # 만료값 자체가 파싱 불가 — 정직하게 "판정 불가=만료 취급"(fail-closed).
                raise HandoffExpiredError(self, now_dt.isoformat()) from exc
            if now_dt > expiry_dt:
                raise HandoffExpiredError(self, now_dt.isoformat())

        if allowed_schema_versions is not None:
            allowed = set(allowed_schema_versions)
            if self.schema_version not in allowed:
                raise HandoffSchemaVersionError(self, allowed)

    def to_dict(self) -> dict[str, Any]:
        """직렬화(dict) — PipelineState처럼 dataclass를 못 담는 Pydantic 모델에 실을 때 사용."""
        return {
            "bundle_id": self.bundle_id,
            "producer": self.producer,
            "created_at": self.created_at,
            "payload_checksum": self.payload_checksum,
            "payload": self.payload,
            "schema_version": self.schema_version,
            "decision": self.decision,
            "conditions": list(self.conditions),
            "parent_bundle_ids": list(self.parent_bundle_ids),
            "expiry": self.expiry,
        }


def seal(
    *,
    producer: str,
    payload: dict[str, Any],
    schema_version: str = CURRENT_SCHEMA_VERSION,
    decision: str = HandoffDecision.PASS.value,
    conditions: list[str] | None = None,
    parent_bundle_ids: list[str] | None = None,
    expiry: str | None = None,
    bundle_id: str | None = None,
    created_at: str | None = None,
) -> HandoffBundle:
    """새 HandoffBundle을 봉인한다 — bundle_id 발급(미지정 시 uuid4)+payload_checksum 계산.

    payload는 seal() 시점에 깊은 복사(스냅샷)돼 bundle.payload에 저장된다 — 호출부가 원본
    dict를 이후 계속 수정해도(흔한 재사용 패턴) 봉인된 스냅샷은 영향받지 않는다. 반대로
    봉인 이후 bundle.payload 자체를 직접 mutate하면(변조) verify_for_consumption이 checksum
    불일치로 반드시 잡아낸다(★hard — 이 모듈의 유일한 하드 계약).
    """
    payload_snapshot = copy.deepcopy(payload) if payload else {}
    checksum = _sha256_bytes(_canonical_json_bytes(payload_snapshot))
    return HandoffBundle(
        bundle_id=bundle_id or uuid4().hex,
        producer=producer,
        created_at=created_at or _utc_now_iso(),
        payload_checksum=checksum,
        payload=payload_snapshot,
        schema_version=schema_version,
        decision=HandoffDecision(decision).value,
        conditions=list(conditions or []),
        parent_bundle_ids=list(parent_bundle_ids or []),
        expiry=expiry,
    )


def bundle_from_dict(data: dict[str, Any] | None) -> HandoffBundle | None:
    """직렬화된 dict → HandoffBundle 역직렬화(``to_dict()``의 역함수).

    형식이 안 맞으면 None(날조 금지 — ``provenance.lineage_ref.lineage_from_dict`` 동형).
    소비측(예: project_pipeline._run_design)이 PipelineState에 dict로 실어둔 번들을
    복원할 때 쓴다.
    """
    if not isinstance(data, dict):
        return None
    try:
        return HandoffBundle(
            bundle_id=str(data.get("bundle_id") or ""),
            producer=str(data.get("producer") or ""),
            created_at=str(data.get("created_at") or ""),
            payload_checksum=str(data.get("payload_checksum") or ""),
            payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
            schema_version=str(data.get("schema_version") or CURRENT_SCHEMA_VERSION),
            decision=str(data.get("decision") or HandoffDecision.PASS.value),
            conditions=list(data.get("conditions") or []),
            parent_bundle_ids=list(data.get("parent_bundle_ids") or []),
            expiry=data.get("expiry"),
        )
    except (ValueError, TypeError):
        return None


def from_submission_bundle_manifest(
    manifest: dict[str, Any],
    *,
    decision: str = HandoffDecision.PASS.value,
    conditions: list[str] | None = None,
    parent_bundle_ids: list[str] | None = None,
    expiry: str | None = None,
) -> HandoffBundle:
    """submission_bundle.build_submission_bundle()의 manifest → HandoffBundle 변환 어댑터.

    submission_bundle은 이 공용 계약의 특수 사례(제출용 zip 한정)다 — 재작성하지 않고 이
    어댑터로 편입한다. manifest["bundle_hash"]는 submission_bundle._sha256_bytes(
    submission_bundle._canonical_json_bytes(manifest_core))로 이미 계산돼 있고, 이 모듈의
    ``_canonical_json_bytes``는 파라미터가 완전히 동일하므로(정렬키·ensure_ascii=False·
    구분자·default=str) 재계산 없이 그대로 payload_checksum으로 신뢰할 수 있다 — 호출부가
    다시 ``verify_for_consumption()``을 호출하면 이 모듈이 같은 알고리즘으로 재계산해
    왕복 검증한다(상호운용은 test_handoff_bundle.py로 고정).

    decision 기본값 PASS인 이유: submission_bundle은 이미 build_submission_bundle() 단계에서
    필수시트 게이트(RequiredSheetsMissingError)를 통과해야만 zip이 생성되므로, 생성된
    manifest 자체가 이미 "무조건 통과 가능한" 상태다 — 별도 CONDITIONAL 판단 근거가 없다.
    """
    if "bundle_hash" not in manifest:
        raise ValueError("submission_bundle manifest 에 bundle_hash 가 없습니다(변환 불가).")
    core = {k: v for k, v in manifest.items() if k != "bundle_hash"}
    run_id = (manifest.get("provenance") or {}).get("run_id")
    return HandoffBundle(
        bundle_id=str(run_id) if run_id else uuid4().hex,
        producer="submission_bundle",
        created_at=str(manifest.get("issue_date") or "") or _utc_now_iso(),
        payload_checksum=str(manifest["bundle_hash"]),
        payload=core,
        schema_version=str(manifest.get("bundle_version") or CURRENT_SCHEMA_VERSION),
        decision=HandoffDecision(decision).value,
        conditions=list(conditions or []),
        parent_bundle_ids=list(parent_bundle_ids or []),
        expiry=expiry,
    )


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "HandoffBlockedDecisionError",
    "HandoffBundle",
    "HandoffBundleRejectedError",
    "HandoffChecksumMismatchError",
    "HandoffDecision",
    "HandoffExpiredError",
    "HandoffSchemaVersionError",
    "bundle_from_dict",
    "decision_from_gate_result",
    "from_submission_bundle_manifest",
    "seal",
]
