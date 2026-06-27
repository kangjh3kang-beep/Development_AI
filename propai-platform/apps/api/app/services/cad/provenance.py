"""provenance — 설계 산출물에 'run_id + 해시'를 붙여 재현·출처추적·변조탐지·멱등을 가능케 하는 순수 헬퍼.

(C2R 문서 §4 공통계약 ADAPT·INC3)

이 파일이 푸는 문제(쉬운 설명):
- 같은 부지를 똑같이 입력했는데 결과가 매번 다른 '실행 ID'를 달면, 같은 결과인지(멱등)·
  누가 어떤 입력으로 만든 산출물인지(출처추적)·중간에 값이 바뀌었는지(변조탐지)를 알 수 없다.
- 그래서 입력 핑거프린트와 산출 기하를 '정규화된 문자열'로 바꾼 뒤 sha256으로 지문(해시)을 찍고,
  그 입력해시 앞 16자로 run_id를 '결정론적으로' 만든다 → 같은 입력이면 언제 돌려도 같은 run_id.

★결정론(핵심): run_id는 입력해시 기반이라 날짜·uuid·랜덤 같은 '돌릴 때마다 변하는 값'을 절대 쓰지 않는다.
  같은 입력 → 같은 입력해시 → 같은 run_id → 멱등(중복 산출 방지·캐시 재사용 가능).

★무날조: 가짜 해시를 지어내지 않는다. 입력 핑거프린트가 없으면 input_hash/run_id는 None으로 둔다
  (소비처에서 'provenance 미상'을 정직하게 표기). 기하 해시는 산출 기하에서 항상 계산한다(빈 기하면 빈 dict 해시).

신규 의존성 0: hashlib·json은 파이썬 표준 라이브러리다.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# 엔진 출처 버전(코드 상수라 항상 유효) — 어느 코드·법규 기준으로 만든 산출물인지 표기.
# 추후 git sha 주입이 필요하면 이 상수 대신 옵셔널 파라미터로 덮을 수 있게 헬퍼를 둔다(아래 source_version).
ENGINE_SOURCE_VERSION = "propai.auto_design_engine.v1 (국토계획법 시행령 제84·85조 기준)"

# run_id 접두사 — C2R 좌표기반 렌더 계열 산출물 표식.
_RUN_ID_PREFIX = "c2r_"
# run_id에 쓰는 입력해시 자릿수(16hex = 64bit 정도면 충돌 확률 충분히 낮음·짧고 읽기 쉬움).
_RUN_ID_HASH_LEN = 16


def canonical_json(obj: Any) -> str:
    """객체를 '정규화된 한 줄 JSON 문자열'로 바꾼다 — 해시 안정성의 핵심.

    같은 내용이면 키 순서가 달라도, 공백이 달라도 '완전히 같은 문자열'이 나오게 한다:
    - sort_keys=True   : 키를 알파벳순 정렬(딕셔너리 입력 순서 무관)
    - separators       : 구분자에서 공백 제거(', ' → ',' / ': ' → ':')
    - ensure_ascii=False: 한글을 그대로(이스케이프 없이) — 동일내용 동일문자열
    - default=str      : JSON으로 못 바꾸는 값(예: enum)은 문자열로(예외 없이 흡수)
    """
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def sha256_hex(s: str) -> str:
    """문자열의 sha256 지문(16진수 64자)을 돌려준다."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# 핑거프린트 수치 양자화 자릿수 — 미세 부동소수 차이(1 ULP 등)를 같은 값으로 본다.
_FINGERPRINT_ROUND = 6


def normalize_fingerprint(obj: Any) -> Any:
    """핑거프린트의 숫자를 '같은 값=같은 표현'으로 정규화한다(멱등 안정성·전역 공용).

    왜(쉬운 설명): 같은 부지인데 2000(정수)과 2000.0(실수)을 넣으면 JSON 문자열이 달라져
      run_id가 갈린다. 모든 숫자를 float로 통일하고 소수 6자리로 반올림해 int/float·미세
      부동소수 변동에 둔감하게 만든다(불리언은 숫자로 취급하지 않음). dict/list는 재귀 적용.
    """
    if isinstance(obj, bool):
        return obj  # True/False는 숫자가 아니다(파이썬 bool은 int 하위형이라 먼저 거른다)
    if isinstance(obj, (int, float)):
        return round(float(obj), _FINGERPRINT_ROUND)
    if isinstance(obj, dict):
        return {k: normalize_fingerprint(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalize_fingerprint(v) for v in obj]
    return obj


def compute_input_hash(fingerprint: dict) -> str:
    """입력 핑거프린트(결정적 입력 필드 dict)의 해시 — 같은 입력이면 항상 같은 값.

    ★수치 정규화 후 해시 — int/float·미세 부동소수 차이에 둔감(멱등 강건성).
    """
    return sha256_hex(canonical_json(normalize_fingerprint(fingerprint)))


def compute_geometry_hash(geometry: dict) -> str:
    """산출 기하(치수 dict)의 해시 — 기하가 같으면 같은 값(변조탐지·기하 동일성 비교)."""
    return sha256_hex(canonical_json(geometry))


def make_run_id(input_hash: str) -> str:
    """입력해시 앞 16자로 결정론적 run_id를 만든다 — 'c2r_' + input_hash[:16].

    ★결정론: 같은 입력해시 → 같은 run_id(날짜·uuid 같은 비결정 요소 0 → 멱등 보장).
    """
    return f"{_RUN_ID_PREFIX}{input_hash[:_RUN_ID_HASH_LEN]}"
