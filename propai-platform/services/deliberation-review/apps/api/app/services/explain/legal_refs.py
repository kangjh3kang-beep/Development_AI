"""법령 인용 사전(SSOT) — 조문 식별자 → LegalRef(법령명·조항호·요지·시행일·1차출처).

엔진이 인용하는 모든 조문/조례/운영기준의 메타데이터 단일 출처. 수치 법령상수가 아닌
'근거 메타데이터'이므로 코드 사전으로 보유(INV-20은 수치값 주입 대상). 1차출처 검증:
docs/VERIFIED_FACTS_zoning.md. 미등록 식별자는 placeholder로 표면화(무음 금지).
"""
from __future__ import annotations

from app.contracts.rationale import LegalRef

_LAW = "https://www.law.go.kr"

_REFS: dict[str, LegalRef] = {
    "국토계획법§36": LegalRef(
        ref_id="국토계획법§36", law="국토의 계획 및 이용에 관한 법률", article="제36조(용도지역의 지정)",
        summary="도시지역(주거·상업·공업·녹지)·관리·농림·자연환경보전지역의 용도지역 분류 체계.",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률"),
    "국토계획법§77": LegalRef(
        ref_id="국토계획법§77", law="국토의 계획 및 이용에 관한 법률", article="제77조(용도지역의 건폐율)",
        summary="용도지역별 건폐율 최대한도의 범위를 정하고 구체 수치를 시·도/시·군 조례에 위임.",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률"),
    "국토계획법§78": LegalRef(
        ref_id="국토계획법§78", law="국토의 계획 및 이용에 관한 법률", article="제78조(용도지역에서의 용적률)",
        summary="용도지역별 용적률 최대한도의 범위를 정하고 구체 수치를 시·도/시·군 조례에 위임.",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률"),
    "국토계획법§84": LegalRef(
        ref_id="국토계획법§84", law="국토의 계획 및 이용에 관한 법률",
        article="제84조(둘 이상의 용도지역 등에 걸치는 대지에 대한 적용 기준)",
        summary="하나의 대지가 둘 이상 용도지역에 걸치면 각 부분 면적 비율로 안분 적용(가장 작은 부분 330㎡ 이하 등 예외).",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률"),
    "국토계획법시행령§84": LegalRef(
        ref_id="국토계획법시행령§84", law="국토의 계획 및 이용에 관한 법률 시행령",
        article="제84조(용도지역 안에서의 건폐율)",
        summary="용도지역별 건폐율 최대한도(예: 제1·2종일반주거 60%, 제3종일반 50%) — 조례로 강화 가능.",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률시행령"),
    "국토계획법시행령§85": LegalRef(
        ref_id="국토계획법시행령§85", law="국토의 계획 및 이용에 관한 법률 시행령",
        article="제85조(용도지역 안에서의 용적률)",
        summary="용도지역별 용적률 최대한도(범위). 구체 수치는 시·도 도시계획조례로 정함(예: 일반주거 100~500%).",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률시행령"),
    "국토계획법§52": LegalRef(
        ref_id="국토계획법§52", law="국토의 계획 및 이용에 관한 법률", article="제52조(지구단위계획의 내용)",
        summary="지구단위계획구역에서 건폐율·용적률·높이 등을 완화·강화. 기반시설 기부채납 비례 인센티브 근거.",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률"),
    "도시정비법": LegalRef(
        ref_id="도시정비법", law="도시 및 주거환경정비법", article="제2조·제9조·시행령(용적률 완화)",
        summary="정비구역(노후·불량 밀집)의 재건축·재개발. 증가 용적률 일부를 임대주택 등 공공기여로 충당.",
        source=f"{_LAW}/법령/도시및주거환경정비법"),
    "서울도시계획조례§55": LegalRef(
        ref_id="서울도시계획조례§55", law="서울특별시 도시계획 조례", article="제55조(용적률)",
        summary="서울시 용도지역별 용적률(제1종일반 150%·제2종일반 200%·제3종일반 250%·준주거 400%·일반상업 800% 등) — 시행령 범위 내 강화.",
        source=f"{_LAW}/자치법규/서울특별시도시계획조례"),
    "서울도시계획조례§54": LegalRef(
        ref_id="서울도시계획조례§54", law="서울특별시 도시계획 조례", article="제54조(건폐율)",
        summary="서울시 용도지역별 건폐율 — 시행령 한도 내 조례 지정값.",
        source=f"{_LAW}/자치법규/서울특별시도시계획조례"),
    "서울한시완화2025": LegalRef(
        ref_id="서울한시완화2025",
        law="서울특별시 도시계획 조례 일부개정(규제철폐안 33호, 소규모건축물 한시완화)",
        article="한시적 용적률 완화(부칙 한시조항)",
        summary=("제2종일반주거 200→250%·제3종일반주거 250→300%(각 +50%p). 소규모건축물 한정"
                 "(건축허가, 자율주택정비·소규모재건축·소규모재개발, 전용 85㎡ 이하). 친환경·공개공지 등 도입 시 "
                 "도시·건축공동위 심의로 시행령 상한 120%까지 추가 가능. 상시 완화 아님(조건 충족 시에만)."),
        effective_date="2025-05-19",
        source="docs/VERIFIED_FACTS_zoning.md · https://opengov.seoul.go.kr/press/33046223"),
    "서울역세권활성화조례": LegalRef(
        ref_id="서울역세권활성화조례", law="서울특별시 역세권 활성화사업 운영 및 지원에 관한 조례",
        article="제1장·운영기준 1-3-1·2-1-2",
        summary=("역세권에서 용도지역 상향+복합개발. 증가 용적률의 약 50%를 공공기여. 대상 역 거리: 가목(도심·"
                 "광역중심·환승역) 승강장 경계 350m, 나목(지구중심·비중심지) 250m(직각 산출)."),
        source="docs/VERIFIED_FACTS_zoning.md · https://news.seoul.go.kr/citybuild/archives/521155"),
    "서울청년안심주택조례§2": LegalRef(
        ref_id="서울청년안심주택조례§2", law="서울특별시 청년안심주택 공급 지원에 관한 조례",
        article="제2조제1호 가목·제19조",
        summary="역세권 청년안심주택: 역 승강장 경계 기본 250m, 통합심의 거쳐 예외 350m(승강장 경계 및 출입구).",
        source=f"{_LAW}/LSW/ordinInfoP.do?ordinSeq=1703625"),
    "서울사전협상조례": LegalRef(
        ref_id="서울사전협상조례", law="서울특별시 도시계획변경 사전협상 운영에 관한 조례",
        article="사전협상 운영지침",
        summary="5천㎡↑ 유휴부지/이전적지의 용도지역 변경 시 토지가치 상승분 일부(약 60%)를 공공기여로 협상.",
        source=f"{_LAW}/자치법규/서울특별시"),
    "입지규제최소구역지침": LegalRef(
        ref_id="입지규제최소구역지침", law="국토의 계획 및 이용에 관한 법률 제40조의2·입지규제최소구역 지정 지침",
        article="입지규제최소구역계획",
        summary="용도지역 규제를 구역계획으로 대체해 용적률·용도를 별도 설정(거점·역사 인접 노후밀집지).",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률"),
    "건축법§6": LegalRef(
        ref_id="건축법§6", law="건축법", article="제6조(기존의 건축물 등에 대한 특례)",
        summary="법령 제·개정으로 기존 건축물이 부적합(기존불적합)해진 경우 증축·개축 등의 허용 범위를 정함.",
        source=f"{_LAW}/법령/건축법"),
    "건축법§61": LegalRef(
        ref_id="건축법§61", law="건축법", article="제61조(일조 등의 확보를 위한 건축물의 높이 제한)",
        summary="전용·일반주거지역에서 정북방향 인접 대지경계선으로부터 일정 거리 이격(일조 확보).",
        source=f"{_LAW}/법령/건축법"),
    "건축법시행령§86": LegalRef(
        ref_id="건축법시행령§86", law="건축법 시행령",
        article="제86조(일조 등의 확보를 위한 건축물의 높이 제한)",
        summary="정북방향 이격거리 산식, 공동주택 동지 09~15시 연속/총 일조시간 확보 기준.",
        source=f"{_LAW}/법령/건축법시행령"),
    "건축법시행령§119": LegalRef(
        ref_id="건축법시행령§119", law="건축법 시행령", article="제119조(면적 등의 산정방법)",
        summary="건축면적(제1항제2호)·연면적(제4호)·용적률 산정 연면적(지하·주차 제외)·높이(제5호)·층수(제9호) 산정방법.",
        source=f"{_LAW}/법령/건축법시행령"),
    "건축법§60": LegalRef(
        ref_id="건축법§60", law="건축법", article="제60조(건축물의 높이 제한)",
        summary="가로구역별 최고 높이 지정·제한.",
        source=f"{_LAW}/법령/건축법"),
    "경관법§9": LegalRef(
        ref_id="경관법§9", law="경관법", article="제9조(경관계획)·지자체 경관조례·경관심의",
        summary="가로경관 연속성·스카이라인 관리. 절대 높이제한과 별개로 주변 대비 돌출을 경관심의로 조정.",
        source=f"{_LAW}/법령/경관법"),
    # 법령 수준(조문 무관) — basis_article이 조문번호 없이 법령명만일 때(R3 룰 등) 해소용(match=law_level).
    "국토계획법시행령": LegalRef(
        ref_id="국토계획법시행령", law="국토의 계획 및 이용에 관한 법률 시행령",
        article="제84조(건폐율)·제85조(용적률) 등",
        summary="용도지역별 건폐율·용적률 최대한도를 정하고 구체 수치는 시·도 조례로 위임.",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률시행령"),
    "국토계획법": LegalRef(
        ref_id="국토계획법", law="국토의 계획 및 이용에 관한 법률",
        article="제36조·제76~78조 등",
        summary="용도지역 지정·용도지역별 건축제한·건폐율/용적률 조례 위임 등 도시계획 기본법.",
        source=f"{_LAW}/법령/국토의계획및이용에관한법률"),
    "건축법시행령": LegalRef(
        ref_id="건축법시행령", law="건축법 시행령",
        article="제86조(일조 높이제한)·제119조(면적·높이·층수 산정) 등",
        summary="면적·높이·층수 산정방법, 일조 등 확보 높이제한 등 건축법 위임사항.",
        source=f"{_LAW}/법령/건축법시행령"),
    "건축법": LegalRef(
        ref_id="건축법", law="건축법",
        article="제46조(건축선)·제60조(높이제한)·제61조(일조) 등",
        summary="건축선·대지안의 공지·높이·일조 등 건축물 일반 규제.",
        source=f"{_LAW}/법령/건축법"),
}


def resolve(ref_id: str) -> LegalRef | None:
    """식별자 → LegalRef. 미등록 None."""
    return _REFS.get(ref_id)


def refs(*ref_ids: str) -> list[LegalRef]:
    """식별자들 → LegalRef 리스트. 미등록은 placeholder로 표면화(무음 금지)."""
    out: list[LegalRef] = []
    for rid in ref_ids:
        r = _REFS.get(rid)
        out.append(r if r is not None else LegalRef(
            ref_id=rid, law="(미등록)", article=rid, summary="법령 사전 미등록 — 보완 필요"))
    return out


def resolve_text(text: str | None) -> dict | None:
    """거친 basis_article 문자열(조문번호 없는 법령명 등, R3 룰)을 best-effort 해소.

    반환: LegalRef 필드 + match. match=exact(정확 키) | law_level(법령 수준 — 조문 미특정, 대표 요지).
    해소 실패 None(소비측에서 '본문 미해소'로 표면화 — 무음 금지). 결정론(사전 고정).
    """
    if not text:
        return None
    if text in _REFS:
        return {**_REFS[text].model_dump(), "match": "exact"}
    norm = "".join(text.split())
    # 1) 법령 수준 키 정확 매칭(§ 없는 키)
    if norm in _REFS:
        return {**_REFS[norm].model_dump(), "match": "law_level"}
    # 2) 정밀 키의 법령부(§ 앞)가 norm과 동일 → 법령 수준 폴백
    for k, ref in _REFS.items():
        if "§" in k and k.split("§", 1)[0] == norm:
            return {**ref.model_dump(), "match": "law_level"}
    # 3) 법령 수준 키가 norm에 포함(예: '건축법 제46조/도시계획' → '건축법')
    for k, ref in _REFS.items():
        if "§" not in k and k in norm:
            return {**ref.model_dump(), "match": "law_level"}
    return None
