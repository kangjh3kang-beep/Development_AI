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
