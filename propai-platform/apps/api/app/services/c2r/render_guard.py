"""C2R 렌더 가드 — '검증 안 된 브리프'로 이미지 렌더되는 오염 경로를 막는 순수 헬퍼.

(C2R 문서 §P3b geometry_hash 필수 render guard ADAPT)

이 파일이 푸는 문제(쉬운 설명):
- /c2r/render 가 브리프를 받아 인벨로프 검증 없이 바로 이미지로 렌더하면, 인벨로프와
  무관한 '아무 브리프'로도 그림이 나온다 → AI가 만든 그림이 거꾸로 '법규·면적의 원천'처럼
  쓰이는 오염(문서 중심사상 정면위반)이 생긴다.
- 그래서 우리 파이프라인이 만든 브리프에는 '기하 지문(geometry_hash)'을 붙여두고(/brief 단계),
  렌더 직전에 이 지문이 ①있는지 ②그 지문이 브리프의 기하요약과 실제로 일치하는지를 확인한다.
  지문이 없거나(검증 안 됨) 어긋나면(위조/변조 의심) 렌더를 막을 근거를 정직하게 돌려준다.

★무날조: 통과/차단 판정 사유를 '있는 그대로의 한국어'로 적는다. 가짜 통과·가짜 차단을 만들지 않는다.
★신규 의존성 0: 해시 계산은 INC3 provenance.compute_geometry_hash 를 그대로 재사용한다.

이 모듈은 '판정'만 한다(어떻게 처리할지는 라우터가 결정). shadow/enforce 분기는 라우터 책임.
"""

from __future__ import annotations

from typing import Any

from app.services.cad.provenance import compute_geometry_hash


def check_render_allowed(brief: dict[str, Any]) -> dict[str, Any]:
    """브리프가 '검증된 기하'에서 나왔는지 확인해 렌더 허용 여부를 판정한다.

    돌려주는 값(항상 같은 모양):
        {allowed: bool, reason: str | None, status: str}
        - allowed : True면 렌더 허용, False면 차단 사유 있음.
        - reason  : 차단 사유(정직한 한국어). 허용이면 None.
        - status  : 기계가 읽는 상태 코드(allowed / blocked_by_* — 응답·로그에 그대로 사용).

    판정 규칙(쉬운 설명):
      1) geometry_hash 가 아예 없다 → 우리 파이프라인을 거치지 않은 '검증 안 된 브리프'다(차단).
      2) geometry_hash 도 있고 geometry_fingerprint(기하요약)도 있다 → 지문을 다시 계산해 대조한다.
         - 다시 계산한 값이 브리프의 geometry_hash 와 다르면 위조/변조 의심(차단).
         - 같으면 우리가 만든 그대로다(허용).
      3) geometry_hash 만 있고 fingerprint 가 없다 → 외부에서 이미 검증된 해시로 보고 허용한다
         (지문 존재만으로 충분한 현 단계 정책 — 추후 fingerprint 필수로 승격 가능).
    """
    geometry_hash = brief.get("geometry_hash") if isinstance(brief, dict) else None

    # 1) 지문 자체가 없으면 = 검증 안 된 브리프(인벨로프와 연동되지 않음).
    if not geometry_hash:
        return {
            "allowed": False,
            "reason": "geometry_hash 없음 — 검증 안 된 브리프(인벨로프 미연동)",
            "status": "blocked_by_unverified_geometry",
        }

    fingerprint = brief.get("geometry_fingerprint")

    # 2) 지문과 기하요약이 둘 다 있으면 재계산해 대조한다(변조 탐지).
    if isinstance(fingerprint, dict):
        recomputed = compute_geometry_hash(fingerprint)
        if recomputed != geometry_hash:
            return {
                "allowed": False,
                "reason": "geometry_hash 불일치 — 브리프 위조/변조 의심",
                "status": "blocked_by_geometry_mismatch",
            }
        return {"allowed": True, "reason": None, "status": "allowed"}

    # 3) 지문만 있고 기하요약은 없다 → 외부 검증 해시로 간주해 허용(현 단계 정책).
    return {"allowed": True, "reason": None, "status": "allowed"}
