"""C2R(Coordinate-to-Render) — 좌표(부지)에서 렌더(이미지)까지의 결정론적 파운데이션.

흐름: 부지 해석(zoning) → 건축가능 인벨로프(solar_envelope) → 구조화 렌더 브리프(텍스트) →
Think-Before 게이팅 → (선택)이미지 렌더 provider 호출.

★1차 증분 원칙(무날조·무목업·무마이그레이션):
- 이미지 렌더는 실제 provider 키가 있을 때만 실호출. 키 없으면 가짜 바이트를 만들지 않고
  정직하게 'provider_unconfigured' 상태를 반환한다(거짓 성공 위장 금지).
- 새 DB 테이블/모델 없이 stateless 컴퓨팅만 — 영속화는 후속 증분.
- 부지 해석·인벨로프는 기존 primitive(AutoZoningService, compute_buildable_envelope)를 재사용.
"""

from app.services.c2r.c2r_service import build_foundation
from app.services.c2r.image_provider import render_image
from app.services.c2r.render_brief import synthesize_brief
from app.services.c2r.think_before import evaluate

__all__ = ["build_foundation", "render_image", "synthesize_brief", "evaluate"]
