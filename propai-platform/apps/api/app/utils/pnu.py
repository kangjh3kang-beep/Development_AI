"""PNU(19자리 필지고유번호) → 지번 파생 — **프론트 `apps/web/lib/pnu.ts` 의 백엔드 미러**.

【왜 백엔드에 필요한가 — 2026-08-18 실증】
`/zoning/parcel-boundaries` 는 PNU 를 **해석**하면서도 응답의 `address` 는 **입력을 그대로
echo** 했다. 입력이 동 단위("경기도 오산시 내삼미동")면 출력도 동 단위여서, 77필지 목록이
**전부 같은 글자**로 보였다(사용자 신고). 지번을 붙일 정보(PNU)는 그 자리에 이미 있었다.

★프론트에도 같은 파생이 있지만(`parcelDisplayAddress`), 프론트만 고치면 **PNU 가 행까지
도달하는 경로**에 의존한다. 응답 자체가 지번을 담으면 소비처(토지조서·사통맵·권리분석
·PDF)가 배선과 무관하게 전부 따라온다 — 그래서 파생을 **응답 조립부 한 곳**에 둔다.

두 구현이 갈리면 화면마다 다른 지번이 보이므로 규칙을 그대로 옮긴다:
  자리 0~9=법정동코드 · 10='2'면 산 · 11~14=본번 · 15~18=부번(0이면 생략).
"""

from __future__ import annotations

import re

_PNU_RE = re.compile(r"^\d{19}$")


def is_valid_pnu(pnu: str | None) -> bool:
    return bool(pnu) and bool(_PNU_RE.match(str(pnu).strip()))


def jibun_from_pnu(pnu: str | None) -> str | None:
    """PNU 에서 '467-1' / '산12' 형태의 지번을 만든다. 본번이 0이면 지번이 없다고 본다."""
    if not is_valid_pnu(pnu):
        return None
    s = str(pnu).strip()
    mountain = s[10] == "2"
    bon = int(s[11:15])
    bu = int(s[15:19])
    if not bon:
        return None
    return f"{'산' if mountain else ''}{bon}{f'-{bu}' if bu else ''}"


def parcel_display_address(address: str | None, pnu: str | None) -> str:
    """화면·문서에 쓸 필지 라벨. 주소에 그 지번이 **이미 있으면 중복해 붙이지 않는다.**"""
    addr = (address or "").strip()
    jibun = jibun_from_pnu(pnu)
    if not jibun:
        return addr
    if addr and re.search(rf"(^|\s){re.escape(jibun)}(\s|$)", addr):
        return addr
    return f"{addr} {jibun}" if addr else jibun


# ── 주소 해상도 ─────────────────────────────────────────────────────────────
# ★D8(2026-08-24 화면감사) — 통합 시나리오의 대표 주소가 **번지 없는 동 단위**
#   ("경기도 오산시 내삼미동")라 지오코딩이 **엉뚱한 필지**를 집었다. 그 결과
#   `zone_basis="representative_parcel"` 이라는 라벨까지 거짓이 됐다(대표 필지조차
#   다른 용도지역이었다).
#
# ★"주소가 없다"와 "주소는 있는데 지오코딩하기엔 거칠다"는 **다른 상태**다.
#   전자는 미확보, 후자는 **그럴듯해서 더 위험하다** — 조회가 성공하고 틀린 값을 준다.
#   그래서 값이 아니라 **해상도**를 이름 붙여 반환한다.

RESOLUTION_JIBUN = "jibun"        # 번지까지 있다 — 지오코딩해도 된다
RESOLUTION_DONG_ONLY = "dong_only"  # 동까지만 — 지오코딩하면 엉뚱한 필지를 집는다
RESOLUTION_NONE = "none"          # 주소 자체가 없다

_JIBUN_TAIL_RE = re.compile(r"(?:^|\s)(?:산\s*)?\d+(?:-\d+)?\s*$")


def address_resolution(address: str | None, pnu: str | None = None) -> str:
    """이 주소로 지오코딩해도 되는지를 **해상도 이름**으로 답한다.

    PNU 가 있으면 지번을 파생할 수 있으므로 `jibun` 으로 본다(`parcel_display_address`
    가 실제로 붙여 준다). PNU 가 없으면 주소 문자열 끝의 지번 꼴로 판정한다.
    """
    if jibun_from_pnu(pnu):
        return RESOLUTION_JIBUN
    addr = (address or "").strip()
    if not addr:
        return RESOLUTION_NONE
    return RESOLUTION_JIBUN if _JIBUN_TAIL_RE.search(addr) else RESOLUTION_DONG_ONLY


def pick_representative_parcel(parcels: list[dict] | None) -> dict | None:
    """대표 필지 — **지번까지 해상된 첫 필지**를 고른다(없으면 주소 있는 첫 필지).

    ★종전엔 `next(p for p in enriched if p.get("address"))` 로 **첫 필지**를 집었다.
      그 첫 필지의 주소가 동 단위면 그 거친 주소가 지오코딩·시군구 추출로 흘러간다.
    """
    items = [p for p in (parcels or []) if isinstance(p, dict)]
    if not items:
        return None
    for p in items:
        if address_resolution(p.get("address"), p.get("pnu")) == RESOLUTION_JIBUN:
            return p
    return next((p for p in items if (p.get("address") or "").strip()), None)


# ── 시군구 걸침 ─────────────────────────────────────────────────────────────
# ★D8 전역 스윕이 드러낸 **인접 결함**(2026-08-25). 스윕은 `auto_zoning.py:1964` 를 D8 과
#   같은 패턴으로 집었지만 재보니 **D8 결함은 아니었다** — `_extract_sigungu` 는 동 단위
#   주소로도 같은 답('오산시')을 준다(실측). **위양성이었다.**
#
#   그런데 같은 자리에서 **다른 진짜 결함**이 나왔다: 조례 시군구를 **첫 필지**에서 뽑아
#   전체에 쓴다. 필지가 시군구를 걸치면 나머지에 **틀린 조례**가 적용된다.
#
#   실측(같은 용도지역·면적, 시군구만 변경 — `far_tier_service.calc_upzoning`):
#       오산시 250%  ·  성남시 280%  ·  강남구 250%  ·  미확보 300%(법정 폴백=과대)
#   → **30%p 격차**. 숫자를 몰래 고르는 것이 아니라 **"누구의 조례인지"를 말하게** 한다.

_SIGUNGU_RE = re.compile(r"([가-힣]+(?:특별시|광역시|특별자치시|특별자치도|도))?\s*"
                         r"([가-힣]+(?:시|군|구))")


def _sigungu_of(address: str | None) -> str | None:
    addr = (address or "").strip()
    if not addr:
        return None
    m = _SIGUNGU_RE.search(addr)
    return m.group(2) if m else None


def sigungu_spread(parcels: list[dict] | None) -> dict:
    """필지들이 **몇 개 시군구에 걸쳐 있는지**와 고지 문구.

    반환 `disclosure` 는 **걸쳐 있을 때만** 채운다 — 정상 케이스에 경고를 붙이면
    그것도 결함이다(가드의 위양성).
    """
    names: list[str] = []
    for p in (parcels or []):
        if not isinstance(p, dict):
            continue
        sg = _sigungu_of(p.get("address"))
        if sg and sg not in names:
            names.append(sg)
    mixed = len(names) > 1
    disclosure = ""
    if mixed:
        disclosure = (
            f"필지가 {len(names)}개 시군구({' · '.join(names)})에 걸쳐 있습니다. "
            f"조례 기준 용적률은 대표 시군구 '{names[0]}' 것을 적용했으므로, "
            "다른 시군구 필지에는 실제와 다를 수 있습니다(시군구별 개별 검토 필요)."
        )
    return {"count": len(names), "names": names, "mixed": mixed, "disclosure": disclosure}
