"""심의 엔진 계약 미러링 — 엔진(`services/deliberation-review`)을 import하지 않고도
입력을 엔진 `AnalysisInput`과 동일하게 정규화하고, 멱등키 해시를 비트동일하게 만든다.

엔진은 패키지명 `app`이 플랫폼과 충돌해 직접 import할 수 없다. 그래서 엔진 입력 모델의
필드·기본값을 여기에 **복제(vendoring)** 한다. 직렬화 3파라미터(sort_keys·ensure_ascii·
separators)는 엔진 core/hashing과 글자단위 동일해야 한다.

설계 참조: services/deliberation-review/apps/api/app/contracts/analysis.py (AnalysisInput).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def canonical(data: Any) -> str:
    """결정적 직렬화 — 키 정렬·한글 보존·공백 제거(엔진 core/hashing.canonical과 동일)."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def input_hash(data: Any) -> str:
    """주어진 객체 → 안정 sha256(canonical 직렬화 후 해시).

    ★주의(엔진과 비동일): 엔진은 input_hash({"input": inp.model_dump(mode="json")})로
    dump를 {"input": ...}로 한 번 더 래핑해 해시한다(analysis_pipeline.py:51). 본 함수는
    그 래핑을 하지 않으므로 엔진의 input_hash와 비트동일하지 않다. 엔진이 산출한 결과추적용
    input_hash가 필요하면 엔진 응답의 result.input_hash를 그대로 사용하라(여기서 재계산 금지).
    본 함수는 BFF 자체 dedup 키(content_input_hash) 계산의 내부 보조용일 뿐이다.
    """
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def content_input_hash(analysis_input: dict[str, Any]) -> str:
    """BFF 자체 멱등/dedup 키 — snapshot_id 하나만 제외한 정규화 sha256.

    snapshot이 달라도 '같은 입력 내용'이면 같은 키 → 동일 입력 재요청을 dedup(엔진 재호출 방지).
    engine_run_binding의 멱등 컬럼. ★엔진의 input_hash와는 다른 값이다(위 input_hash 주의 참조).

    ★보안(tenant 미포함): 이 해시에는 tenant가 들어가지 않는다(입력 내용만). 따라서 단독으로
    조회 키로 쓰면 교차테넌트 충돌·열람 위험이 있다. 반드시 (tenant_id, content_input_hash)
    복합 스코프로만 조회/영속해야 안전하다(binding_service.lookup/insert가 tenant를 SQL where에
    강제). tenant 스코프 없이 content_input_hash 단독으로 조회하지 말 것.
    """
    return input_hash({k: v for k, v in analysis_input.items() if k != "snapshot_id"})


class MirrorAnalysisInput(BaseModel):
    """엔진 `contracts/analysis.AnalysisInput`의 필드·기본값 미러(직접 import 불가→복제).

    `model_dump(mode="json")`가 엔진과 동일 dict를 내야 멱등 해시가 정합한다.
    extra="ignore" — 플랫폼이 보낸 잉여 키는 (엔진과 동일하게) 무시한다.
    """

    model_config = ConfigDict(extra="ignore")

    pnu: str = ""
    application_date: date | None = None
    axis_date: date | None = None
    snapshot_id: str = "snap-1"
    drawing: dict = Field(default_factory=dict)
    model_version: str = "engine-v1"
    drawings: list = Field(default_factory=list)
    ifc: str | None = None
    elements: list = Field(default_factory=list)
    calc_targets: list = Field(default_factory=list)
    rules: list = Field(default_factory=list)
    sim_inputs: dict = Field(default_factory=dict)
    issue: str | None = None
    corpus: list = Field(default_factory=list)
    mirror_rules: list = Field(default_factory=list)
    citations: list = Field(default_factory=list)
    cross_facts: list = Field(default_factory=list)
    collect_land_card: bool = False
    land_year: str | None = None
    address: str | None = None
    collect_surrounding: bool = False
    surrounding_radius_m: int = 150
    proposed_floors: int | None = None
    qual_facts: list = Field(default_factory=list)


def build_input_dump(payload: dict[str, Any]) -> dict[str, Any]:
    """플랫폼 입력 dict → 엔진 기본값까지 채운 정규 dump(엔진 model_dump(mode="json")와 동일).

    잉여 키는 무시되고, 누락 필드는 엔진 기본값으로 채워진다. 멱등 해시·엔진 POST 본문의 단일 출처.
    """
    return MirrorAnalysisInput(**(payload or {})).model_dump(mode="json")


def prevalidate(dump: dict[str, Any]) -> str | None:
    """엔진 호출 전 최소 선검증 — 위반 시 'invalid_input:<사유>' 문자열, 정상이면 None.

    엔진이 명백한 계약위반에 500을 내는 케이스(필수 필드 부재 등)를 BFF가 먼저 422로 차단해
    엔진 회로(circuit breaker) 오카운트를 막는다. 엔진을 import하지 않고 규칙만 복제한다.
    """
    pnu = str(dump.get("pnu") or "")
    # pnu는 빈 값(주소 기반 진입) 또는 19자리 숫자만 허용.
    if pnu and not (len(pnu) == 19 and pnu.isdigit()):
        return "invalid_input:pnu_invalid"

    # rules: 각 항목에 rule.rule_id 필수(엔진 Rule 필수 필드 — 부재 시 엔진 500).
    for i, r in enumerate(dump.get("rules") or []):
        if not isinstance(r, dict) or not isinstance(r.get("rule"), dict):
            return f"invalid_input:rules[{i}].rule_missing"
        if not r["rule"].get("rule_id"):
            return f"invalid_input:rules[{i}].rule_id_missing"

    # calc_targets: target 필수.
    for i, t in enumerate(dump.get("calc_targets") or []):
        if not isinstance(t, dict) or not t.get("target"):
            return f"invalid_input:calc_targets[{i}].target_missing"

    # elements: element_id 필수(엔진 분류기 KeyError 방지).
    for i, e in enumerate(dump.get("elements") or []):
        if not isinstance(e, dict) or not e.get("element_id"):
            return f"invalid_input:elements[{i}].element_id_missing"
    return None


def is_deterministic_path(dump: dict[str, Any]) -> bool:
    """순수(결정론) 경로만 True — 같은 입력이면 같은 결과라 멱등 dedup 가능.

    라이브 발화(도면 자동해석·다중출처 수집·임베딩·지오코딩) 중 하나라도 있으면 False →
    매 호출 엔진 위임(캐싱·dedup 금지). 결과가 시점 의존적이기 때문.
    """
    if dump.get("drawings") or dump.get("ifc") or dump.get("elements"):
        return False  # 도면 자동해석/BIM·VLLM 추출(비결정 가능)
    if dump.get("cross_facts") or dump.get("collect_land_card") or dump.get("collect_surrounding"):
        return False  # 라이브 다중출처/수집
    if dump.get("issue") and dump.get("corpus"):
        return False  # 유사사례 라이브 임베딩
    # address만 있고 pnu가 19자리가 아니면 라이브 지오코딩 발화.
    if dump.get("address") and len(str(dump.get("pnu") or "")) != 19:
        return False
    return True
