"""중심 엔진 통합 — 엔진 계약 vendoring(패키지명 `app` 충돌로 엔진 import 불가).

엔진 `core/hashing`(canonical/input_hash)을 **비트동일**하게 복제. BFF 멱등성(engine_run_binding)·
부분응답 input_hash parity 검증의 단일 출처. ⚠️ 엔진과 직렬화 3파라미터(sort_keys·ensure_ascii·
separators) 글자단위 동일해야 함.

drift 차단(살아있는 가드, 2단): (1) `mirror_contract_fingerprint()`가 커밋된 engine fixture
(tests/fixtures/engine_input_contract.json)와 비트동일 — 미러가 fixture에서 벗어나면 RED.
(2) 엔진 워크트리 존재 시 실 `AnalysisInput` 모델을 재덤프해 fixture와 대조 — 엔진이 필드/기본값을
추가하면 RED(fixture 재생성 강제). 두 테스트가 엔진→fixture→미러 체인을 닫아 골든 stale을 막는다.
설계: docs/CENTRAL_ENGINE_INTEGRATION_DESIGN.md §5 패키지격리·§9 R7·§13 parity.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 엔진 enum 실측(vendoring). drift 시 prevalidate 테스트가 차단.
_CALC_TARGETS = frozenset({"building_area", "gross_floor_area", "far_floor_area",
                           "plot_area", "building_height", "floor_count"})
_SEMANTIC_TYPES = frozenset({"PILOTIS", "BALCONY", "EAVE", "BASEMENT", "PARKING",
                             "CORE_STAIR", "EXT_WALL", "PLOT_BOUNDARY", "BUILDING_LINE", "UNKNOWN"})
_COMPARATORS = frozenset({"<=", ">=", "<", ">", "=="})
_PNU_RE = re.compile(r"^([0-9]{19})?$")

# 엔진 버전 핀(이 골든이 깨지면 엔진 hashing 변경 → 동기화 필요). 골든=엔진 input_hash({"input": <대표입력>}).
ENGINE_HASHING_PINNED = "core.hashing@v1"


def canonical(data: Any) -> str:
    """결정적 직렬화 — 엔진 core/hashing.canonical과 글자단위 동일(키 정렬·한글 보존·무공백)."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def input_hash(data: Any) -> str:
    """정규화 입력 → 안정 sha256(엔진 input_hash와 동일)."""
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def analysis_input_hash(analysis_input: dict[str, Any]) -> str:
    """엔진 `run_analysis`의 input_hash와 비트동일: `input_hash({"input": inp.model_dump(mode="json")})`.

    ⚠️ analysis_input은 **AnalysisInput 기본값까지 채운 model_dump 결과**여야 엔진과 일치(snapshot_id 기본
    "snap-1" 등 누락 시 불일치). 입력 어댑터가 미러 모델로 dump한 dict를 넘긴다.
    """
    return input_hash({"input": analysis_input})


def content_input_hash(analysis_input: dict[str, Any]) -> str:
    """멱등/lineage 키 — snapshot_id 단 하나만 제외한 정규화 해시(reconcile가 snapshot 주입해 input_hash가
    바뀌어도 동일 사안을 같은 lineage로 묶음). engine_run_binding UNIQUE(tenant, content_input_hash, snapshot_id).
    """
    return input_hash({k: v for k, v in analysis_input.items() if k != "snapshot_id"})


class MirrorAnalysisInput(BaseModel):
    """엔진 `contracts/analysis.AnalysisInput`의 **필드·기본값 미러**(import 불가→vendoring).

    `model_dump(mode="json")`가 엔진과 동일 dict를 내야 input_hash가 비트동일(parity 테스트로 drift 차단).
    extra="ignore"(엔진 기본과 동일 — 플랫폼이 보낸 잉여 키는 양측 모두 무시). pnu 패턴 등 엔진 validator는
    미적용(유효 입력은 값 동일 통과; 무효는 BFF 선검증/엔진 422가 별도로 처리).
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
    """플랫폼 입력 dict → 엔진 기본값 채운 정규 dump(엔진 model_dump(mode="json")와 동일)."""
    return MirrorAnalysisInput(**payload).model_dump(mode="json")


def _manifest_default(field: Any) -> Any:
    """FieldInfo → json-safe 기본값(factory는 호출). 엔진 매니페스트 generator와 동일 규칙."""
    v = field.default_factory() if field.default_factory is not None else field.default
    try:
        return json.loads(json.dumps(v, default=str))
    except (TypeError, ValueError):
        return str(v)


def mirror_field_manifest() -> dict[str, Any]:
    """미러 모델 필드 매니페스트(이름·기본값·hashing 핀). 엔진 실모델 generator와 동일 산식 →
    커밋된 engine fixture와 비트동일해야(drift=필드추가/기본값변경 시 parity 단위테스트 RED). 살아있는 가드의 미러측."""
    fields = {n: _manifest_default(f) for n, f in MirrorAnalysisInput.model_fields.items()}
    names = sorted(fields)
    return {"field_names": names, "defaults": {k: fields[k] for k in names},
            "hashing": ENGINE_HASHING_PINNED}


def mirror_contract_fingerprint() -> str:
    """매니페스트(field_names+defaults)의 안정 sha256 — 엔진 fixture.fingerprint와 대조(드리프트 차단).
    ENGINE_HASHING_PINNED를 매니페스트에 실어 dead 상수가 아니라 활성 어서션 대상이 된다."""
    m = mirror_field_manifest()
    canon = json.dumps({"field_names": m["field_names"], "defaults": m["defaults"]},
                       sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def is_deterministic_path(dump: dict[str, Any]) -> bool:
    """순수(결정론) 경로만 True — 멱등 재사용 가능. 라이브 발화(VLLM·네트워크·가변 공급미러·임베딩)
    중 하나라도 있으면 False → 매 호출 엔진 위임(캐싱/부분유니크 dedup 금지, §3·§9 R7).

    비결정 사유(엔진 analysis_pipeline 대조):
    - drawings/ifc/elements: VLLM·이중경로 추출(도면 자동해석, 비결정 가능)
    - cross_facts/collect_land_card/collect_surrounding: 라이브 다중출처/VWORLD 수집
    - issue & corpus: L4 유사사례 의미임베딩(OpenAI 라이브 가능; 폴백 전환 시 매칭사례 변동, pipeline:167-176)
    - citations & mirror_rules 미제공: SUPPLY_STORE 가변 미러 게이팅(시점 의존, pipeline:186-200)
    - address & pnu 비19자리: 라이브 지오코딩(pipeline:205)
    순수=pnu(19자리)·application_date·axis_date·snapshot_id·calc_targets·rules·sim_inputs·qual_facts
    (·citations는 mirror_rules 동반 시에만 순수).

    ⚠️ 알려진 한계(parity, 비차단): mirror_rules 미제공 + citations 없음 입력은 결정론으로 캐싱되나,
    엔진은 이때도 default_store().get(pnu)(SUPPLY_STORE 가변)를 읽어 결과의 mirror_source **라벨**을
    시점의존적으로 채운다(첫 호출 None이 캐시되면 이후 공급 적재돼도 stale). citations가 없으면 CitationCheck
    미실행이라 게이팅/findings는 불변 — 드리프트는 provenance 라벨에 한정. 정합 해법=엔진이 결과에
    mirror_version 노출 → content_input_hash lineage에 반영(엔진 수정 #8 트랙). 그 전까지 라벨 stale 수용.
    """
    if dump.get("drawings") or dump.get("ifc") or dump.get("elements"):
        return False  # VLLM/이중경로 추출(비결정 가능)
    if dump.get("cross_facts") or dump.get("collect_land_card") or dump.get("collect_surrounding"):
        return False  # 라이브 다중출처/수집
    if dump.get("issue") and dump.get("corpus"):
        return False  # L4 유사사례 라이브 임베딩(보수적 — BFF는 EMBEDDER 모드 미확신)
    if dump.get("citations") and not dump.get("mirror_rules"):
        return False  # 공급측 가변 미러(SUPPLY_STORE) 의존 게이팅
    # address는 pnu가 19자리가 아닐 때만 라이브 지오코딩 발화(엔진 pipeline:205).
    return not (dump.get("address") and len(str(dump.get("pnu") or "")) != 19)


def _finite(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def prevalidate(dump: dict[str, Any]) -> str | None:
    """엔진 KeyError/ValidationError/ValueError→500을 BFF가 422로 선차단(§6 전체 체크리스트, §5 breaker 오카운트 방지).

    위반 시 'invalid_input:<path>' 문자열, 정상이면 None. 엔진을 import하지 않고 vendored enum/규칙으로 검증.
    """
    if not _PNU_RE.match(str(dump.get("pnu") or "")):
        return "invalid_input:pnu_invalid"

    for i, r in enumerate(dump.get("rules") or []):
        if not isinstance(r, dict) or "rule" not in r:
            return f"invalid_input:rules[{i}].rule_missing"
        rule = r["rule"]
        if not isinstance(rule, dict):
            return f"invalid_input:rules[{i}].rule_type"
        if not rule.get("rule_id"):
            return f"invalid_input:rules[{i}].rule.rule_id_missing"  # 엔진 Rule 필수 필드(부재→500)
        comp = rule.get("comparator")
        if comp is not None and comp not in _COMPARATORS:
            return f"invalid_input:rules[{i}].comparator"
        for k in ("measured", "limit"):
            if r.get(k) is not None and not _finite(r[k]):
                return f"invalid_input:rules[{i}].{k}_nonfinite"
        c = r.get("confidence")  # row-level → 엔진 EvalCase.input_confidence: Probability(ge0 le1)
        if c is not None and (not _finite(c) or not 0.0 <= float(c) <= 1.0):
            return f"invalid_input:rules[{i}].confidence"

    for i, t in enumerate(dump.get("calc_targets") or []):
        if not isinstance(t, dict) or "target" not in t:
            return f"invalid_input:calc_targets[{i}].target_missing"
        if t["target"] not in _CALC_TARGETS:
            return f"invalid_input:calc_targets[{i}].target_enum"
        for j, e in enumerate(t.get("elements") or []):
            err = _validate_calc_element(e, f"calc_targets[{i}].elements[{j}]")
            if err:
                return err

    for i, e in enumerate(dump.get("elements") or []):
        if not isinstance(e, dict) or not e.get("element_id"):
            return f"invalid_input:elements[{i}].element_id_missing"  # 엔진 element_classifier KeyError

    for i, cf in enumerate(dump.get("cross_facts") or []):
        if not isinstance(cf, dict) or "fact_key" not in cf:
            return f"invalid_input:cross_facts[{i}].fact_key_missing"
        for k, s in enumerate(cf.get("sources") or []):
            err = _validate_source(s, f"cross_facts[{i}].sources[{k}]")
            if err:
                return err

    # corpus는 issue 동반 시에만 엔진이 PrecedentCase(**c)로 소비(pipeline:167-169) — 그때만 case_id 강제.
    if dump.get("issue"):
        for i, c in enumerate(dump.get("corpus") or []):
            if not isinstance(c, dict) or not c.get("case_id"):
                return f"invalid_input:corpus[{i}].case_id_missing"  # 엔진 PrecedentCase 필수
    return None


def _validate_source(s: Any, path: str) -> str | None:
    """엔진 SourceValue 선검증(부재/타입 오류→엔진 500 차단): source+value 필수, value∈str|int|float|None,
    max_age_days∈int|None, collected_at/data_vintage∈ISO date|None."""
    if not isinstance(s, dict) or "source" not in s:
        return f"invalid_input:{path}.source_missing"
    if "value" not in s:  # 엔진 SourceValue 필수(source+value)
        return f"invalid_input:{path}.value_missing"
    v = s.get("value")
    if v is not None and not isinstance(v, (str, int, float)):  # bool은 int 하위 — 허용
        return f"invalid_input:{path}.value_type"
    m = s.get("max_age_days")
    if m is not None and not isinstance(m, int):
        return f"invalid_input:{path}.max_age_days_type"
    for k in ("collected_at", "data_vintage"):
        d = s.get(k)
        if d is not None and not _is_iso_date(d):
            return f"invalid_input:{path}.{k}_invalid"
    return None


def _is_iso_date(v: Any) -> bool:
    if isinstance(v, date):
        return True
    try:
        date.fromisoformat(str(v))
        return True
    except (ValueError, TypeError):
        return False


def _validate_calc_element(e: Any, path: str) -> str | None:
    if not isinstance(e, dict):
        return f"invalid_input:{path}.type"
    st = e.get("semantic_type")
    if not st:
        return f"invalid_input:{path}.semantic_type_missing"  # 엔진 CalcElement 필수(부재→500)
    if st not in _SEMANTIC_TYPES:
        return f"invalid_input:{path}.semantic_type"
    c = e.get("confidence")
    if c is not None and (not _finite(c) or not 0.0 <= float(c) <= 1.0):
        return f"invalid_input:{path}.confidence"
    for k in ("area", "length", "depth"):
        if e.get(k) is not None and not _finite(e[k]):
            return f"invalid_input:{path}.{k}_nonfinite"
    return None
