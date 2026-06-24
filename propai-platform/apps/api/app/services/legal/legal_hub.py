"""LegalHub — 법령 단일 진실원천(SSOT) 파사드 (#2 법령 통합).

분산 해소: 플랫폼에는 두 법령 인덱스가 공존했다 —
  (1) legal_reference_registry: '개념키'(far_limit·bcr_limit·acquisition_tax…) 인덱스(분석·근거용).
  (2) 심의엔진 인용: '조문키'(국토계획법§78…) 인덱스(판정 근거용).
LegalHub는 registry를 **정본으로 위임**하고, 조문(law§article) **역인덱스**를 추가해 어느 쪽
키로 조회하든 동일한 검증 URL·제목·요지를 돌려준다(개념키 ↔ 조문키 교차 = 단일경유).

원칙:
- 무날조: URL은 registry.build_law_url(law.go.kr 검증 한글주소)만 — 미확보는 url_status='pending'.
- 비계산: 데이터 매핑·문자열 조립만(법규 수치 생성 없음).
- 비파괴: 기존 get_legal_refs/build_law_url 계약 그대로 위임(소비처 무회귀). 신규·교차조회만 추가.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.legal import legal_reference_registry as _reg

# "법령 제78조", "국토계획법§78"(조 생략·심의엔진 형식), "제84조의2" 등에서 (법령, 조문) 추출.
#   ★'조'는 옵션 — 심의엔진 인용키는 '§78'처럼 조 표기가 없다(이걸 필수화하면 파싱 실패).
_LAW_ARTICLE_RE = re.compile(r"^\s*(?P<law>.+?)\s*(?:§|제)\s*(?P<num>\d+)\s*(?:조)?(?:\s*의\s*(?P<sub>\d+))?\s*$")


class _LegalHub:
    """법령 조회 단일 진입점(facade). 인스턴스 1개를 LegalHub로 노출."""

    _article_idx: dict[tuple[str, str], dict[str, str]] | None = None

    # ── 개념키 경로(registry 위임 — 기존 계약 동일) ──
    def refs(self, keys, *, sigungu: str | None = None) -> list[dict]:
        """개념키 목록 → 검증 레코드 목록(registry.get_legal_refs 위임)."""
        return _reg.get_legal_refs(keys, sigungu=sigungu)

    def ref(self, key: str) -> dict | None:
        """개념키 1건 → 레코드 또는 None."""
        return _reg.get_legal_ref(key)

    def url(self, law_name: str, article: Any = None) -> str:
        """임의 법령·조문 → 검증 URL(law.go.kr 한글주소). 미확보 시 법령 루트."""
        return _reg.build_law_url(law_name, article)

    # ── 고시 계층(국가 행정규칙 + 지역 고시) ──
    def gosi(self, name: str) -> dict:
        """국가 고시·훈령·예규(행정규칙) → 검증 레코드. 국가기관이 법령 위임으로 발한 구속력 있는 규칙.

        예: 분양가상한제 산정 고시, 건축물 에너지효율등급 인증 고시. law.go.kr/행정규칙 검증 링크.
        """
        url = _reg.build_admrule_url(name)
        return {
            "name": name, "category": "고시",
            "url": url,
            "url_status": "verified" if _reg._is_trusted_legal_host(url) else "pending",
        }

    def regional_gosi(self, sido: str | None = None, sigungu: str | None = None) -> dict:
        """지역 고시(도시관리계획 결정·지형도면·실시계획인가) → 토지이음 고시정보 deep-link(시군구 스코프).

        부지단위 자동매칭은 LURIS 고시 API 연동 시 제공(현재 시군구 목록 링크). tojieum_supplement 위임.
        """
        from app.services.legal.tojieum_supplement import gosi_info
        return gosi_info(sido, sigungu)

    # ── 조문키 경로(심의엔진 인용 통합) ──
    def by_article(self, law_name: str, article: Any = None) -> dict:
        """조문 인용(law§article) → 통합 레코드.

        registry에 동일 (법령, 조문)이 있으면 그 개념키·제목을 함께 반환(교차), 없으면 검증 URL만.
        반환: {law_name, article, url, url_status, key?, title?}.
        """
        art = _reg._format_article(article) or ""
        url = _reg.build_law_url(law_name, article)
        rec: dict[str, Any] = {
            "law_name": law_name,
            "article": art,
            "url": url,
            "url_status": "verified" if _reg._is_trusted_legal_host(url) else "pending",
        }
        hit = self._index().get((_reg._normalize_name(law_name), art))
        if hit:
            rec["key"] = hit["key"]
            rec["title"] = hit.get("title", "")
        return rec

    def resolve(self, query: str, *, sigungu: str | None = None) -> dict | None:
        """범용 해석 — 개념키('far_limit') 또는 조문문자열('국토계획법§78')을 단일 레코드로.

        개념키가 registry에 있으면 그 레코드, 아니면 'X§N조' 패턴을 파싱해 by_article로 해석.
        해석 불가 시 None(가짜 생성 금지).
        """
        if not query:
            return None
        # 개념키면 refs 경유(조례 {sigungu} 치환·url_status 일관) — 단일 레코드로 반환.
        if _reg.get_legal_ref(query) is not None:
            recs = self.refs([query], sigungu=sigungu)
            return recs[0] if recs else None
        m = _LAW_ARTICLE_RE.match(query)
        if m:
            num = m.group("num")
            sub = m.group("sub")
            article = f"제{num}조의{sub}" if sub else f"제{num}조"
            return self.by_article(m.group("law"), article)
        return None

    def _index(self) -> dict[tuple[str, str], dict[str, str]]:
        """registry 역인덱스 (정규화 법령명, 조문) → {key, title}. 지연 1회 구성·캐시."""
        if self._article_idx is None:
            idx: dict[tuple[str, str], dict[str, str]] = {}
            for k, v in _reg.LEGAL_REFERENCES.items():
                key2 = (_reg._normalize_name(v.get("law_name", "")), v.get("article", ""))
                # 첫 등록 우선(중복 조문은 가장 먼저 정의된 개념키로 대표).
                idx.setdefault(key2, {"key": k, "title": v.get("title", "")})
            self._article_idx = idx
        return self._article_idx


# 플랫폼 단일 진입점. 신규/교차 법령 조회는 이 인스턴스를 경유한다.
LegalHub = _LegalHub()
