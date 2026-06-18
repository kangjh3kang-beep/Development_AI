"""중심 엔진 통합 — 엔진 계약 vendoring(패키지명 `app` 충돌로 엔진 import 불가).

엔진 `core/hashing`(canonical/input_hash)을 **비트동일**하게 복제. BFF 멱등성(engine_run_binding)·
부분응답 input_hash parity 검증의 단일 출처. ⚠️ 엔진과 직렬화 3파라미터(sort_keys·ensure_ascii·
separators) 글자단위 동일해야 함 — drift는 parity 단위테스트(엔진 골든값 대조)가 CI에서 차단.
설계: docs/CENTRAL_ENGINE_INTEGRATION_DESIGN.md §5 패키지격리·§9 R7.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

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
