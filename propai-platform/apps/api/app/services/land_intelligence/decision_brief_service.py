"""Stage1 통합 의사결정 브리프(Decision Brief) 오케스트레이터.

주소(또는 프로젝트)를 1회 입력하면 3개 통합 도메인 카드(①부지·입지·시장 통합 ②법규·규제
③인허가·사업모델 Top3/설계개요)를 한 번에 '모아서' 표준 요약 계약으로 돌려주고, 디벨로퍼
페르소나 Go/No-Go를 재사용해 단일 종합 판정(GO/CONDITIONAL/HOLD)을 산출한다. 비전문가도 한
화면에서 "이 땅, 추진할까?"에 답을 얻도록 하는 게 목표다(인간개입 최소화·전문가 대행).

★기존 엔진 재사용 우선(신규 분석엔진 금지):
  - 부지/입지+시장 = ComprehensiveAnalysisService.analyze (실효용적률·공급면적·시세·실거래·
    분양가·입지·특이부지·근거·법령링크 일괄 반환)
  - 법규 = RegulationAnalysisService.analyze (상위법령→조례 한도·verified 법령링크·근거)
  - 인허가+설계개요 Top3 = FeasibilityServiceV2.auto_recommend_top3
  - 종합 판정 = persona.runner.run_persona('developer') 의 Go/No-Go(체크리스트·게이트 종합)

설계 원칙:
  - 3개 도메인(부지·시장 통합/법규/인허가·Top3) 호출을 asyncio.gather(return_exceptions=True)로 병렬 집계.
  - 한 도메인 실패 → 그 part 만 status='unavailable'+정직 사유, 전체는 안 깨짐(graceful).
    예외는 분류 로깅(silent-fail 금지 — 빈값 은폐 금지).
  - 무거운 호출은 analysis_cache(영속 캐시)로 입력 동일 시 재사용(force_refresh로만 재분석).
  - 특이부지(developability!=POSSIBLE)·법규 BLOCKED는 자동 HOLD/CONDITIONAL 강등(가짜 GO 금지).
  - LLM 단일경유 계측은 각 하위 엔진이 그대로 유지한다(use_llm 플래그를 그대로 전달).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.services.common import analysis_cache

logger = structlog.get_logger(__name__)

# 캐시 종류 키 — analysis_cache(kind, cache_key) 복합 PK 의 kind.
_CACHE_KIND = "decision_brief"

# 표준 요약 계약의 part 식별자(프론트 도메인무관 렌더 키).
PART_SITE_MARKET = "site_market"
PART_REGULATION = "regulation"
PART_PERMIT_DESIGN = "permit_design"


class DecisionBriefService:
    """Stage1 통합 의사결정 브리프 오케스트레이터(기존 엔진 조립 레이어)."""

    async def build(
        self,
        *,
        address: str | None = None,
        project_id: str | None = None,
        parcels: list[str] | None = None,
        tenant_id: str | None = None,
        land_area_sqm: float | None = None,
        equity_won: int | None = None,
        use_llm: bool = False,
        force_refresh: bool = False,
        include_specialists: bool = True,
        db: Any | None = None,
    ) -> dict[str, Any]:
        """통합 의사결정 브리프를 생성한다.

        Args:
            address: 대표 분석 주소(다필지면 대표 개발가능 필지 권장).
            project_id: 프로젝트 ID(원장 체인 스코프·캐시 키).
            parcels: 다필지 주소 목록(통합면적 산출용).
            tenant_id: 테넌트 ID(격리·캐시 키).
            land_area_sqm: ★유효 대지면적(㎡) 종단배선 — 프론트가 보낸 다필지 통합면적(우선).
                공유 엔진 ComprehensiveAnalysisService.analyze 는 address만 받으므로(공유서비스
                비변경), 이 값이 주어지면 decision_brief 레이어에서 부지 part 의 대지면적·계획 GFA
                메트릭을 이 면적 기준으로 재계산한다(GFA = 면적 × 실효용적률/100). 통합면적이 KPI에
                실반영된다. None이면 엔진 산출 대표면적을 그대로 쓴다(무회귀).
            equity_won: 자기자본(원) — 디벨로퍼 Go/No-Go ROE 경로 확보용.
            use_llm: LLM 내러티브 포함 여부(기본 false=무과금·무LLM).
            force_refresh: True면 캐시 무시하고 재분석(기본 false=캐시 재사용).
            include_specialists: ★결정론 SpecialistAgent(zoning/permit) 모세혈관 배선 — 부지·인허가
                데이터로 auto-dispatch해 도메인 findings·prior 모순·원장 cite를 브리프에 주입(소비처
                연결). LLM·과금 없음(결정론 도메인만)·graceful(실패는 스킵). 기본 True.
            db: 페르소나 Go/No-Go(run_persona) 호출용 AsyncSession(없으면 verdict 폴백).

        Returns:
            표준 의사결정 브리프 dict(parts·verdict·meta·billing).
        """
        if not (address or project_id):
            # 입력 부재는 은폐하지 않고 명시 사유로 반환(silent-fail 금지).
            return self._empty_brief(
                address=address,
                project_id=project_id,
                reason="주소 또는 프로젝트 ID가 필요합니다(무목업).",
            )

        # ── 캐시 조회(영속) — 입력 동일 시 재사용. force_refresh면 건너뜀 ──
        # ★캐시 키에 use_llm·db가용성 경로 구분자 포함 — db 미주입(폴백 verdict) 결과가
        #   db 주입(페르소나 verdict) 경로로 교차오염되지 않게 분리한다(MED).
        cache_key = analysis_cache._key(
            tenant_id or "",
            project_id or "",
            (address or "").strip(),
            "|".join(sorted(parcels or [])),
            # ★유효면적을 캐시 키에 포함 — 면적이 다르면(다필지 통합면적 보강 등) 캐시를 분리해
            #   옛 대표면적 기준 브리프가 새 통합면적 요청에 재사용되지 않게 한다(stale 방지).
            str(land_area_sqm or ""),
            str(equity_won or ""),
            "llm" if use_llm else "norm",
            "db" if db is not None else "nodb",
        )
        if not force_refresh:
            cached = await analysis_cache.cache_get(_CACHE_KIND, cache_key)
            if cached is not None:
                return cached

        # ── 다필지 통합면적(있으면) — 대표 주소는 호출자가 재조준한 개발가능 필지 ──
        parcel_count = len([p for p in (parcels or []) if p]) or (1 if address else 0)

        # ── 3개 도메인 병렬 집계(부지·시장/법규/인허가·Top3 — 부분실패 graceful) ──
        site_task = self._run_site_market(address, tenant_id, project_id, use_llm)
        reg_task = self._run_regulation(address, use_llm)
        # ★통합면적 종단배선 — 다필지 통합면적(land_area_sqm)을 Top3 엔진에 전달해 판정 ROI 도
        #   통합면적 기준으로 산정(표시 GFA 와 판정 기준 단위 일치). 양수일 때만 적용(무회귀).
        permit_task = self._run_permit_design(address, equity_won, use_llm, land_area_sqm)

        site_res, reg_res, permit_res = await asyncio.gather(
            site_task, reg_task, permit_task, return_exceptions=True
        )

        # 예외는 분류 로깅 후 part='unavailable'로 정직 강등(전체 무손상).
        site_raw = self._unwrap(site_res, PART_SITE_MARKET)
        reg_raw = self._unwrap(reg_res, PART_REGULATION)
        permit_raw = self._unwrap(permit_res, PART_PERMIT_DESIGN)

        parts = [
            self._summarize_site_market(site_raw, parcel_count, land_area_sqm),
            self._summarize_regulation(reg_raw),
            self._summarize_permit_design(permit_raw),
        ]

        # ── 종합 verdict(디벨로퍼 Go/No-Go 재사용 + 특이부지/법규 강등) ──
        verdict = await self._build_verdict(
            db=db,
            address=address,
            project_id=project_id,
            parcels=parcels,
            equity_won=equity_won,
            site_raw=site_raw,
            reg_raw=reg_raw,
            permit_raw=permit_raw,
            use_llm=use_llm,
            # ★override 통합면적을 verdict 레이어로 전달 — '표시 GFA(override) vs 판정 기준
            #   (엔진 대표면적)' 단위 불일치를 silent로 두지 않고 reasons에 정직 고지하기 위함.
            override_area=land_area_sqm,
        )

        # ★면적 override 괴리 메타(보안·정직성): 프론트가 보낸 통합면적이 엔진 대표면적과
        #   과도하게(>5배) 다르면 잘못된 면적(다른 부지·단위오류·악의 입력) 가능성을 경고로 남긴다.
        #   422 상한(라우터)을 통과한 값이라도, 권위 KPI가 되기 전에 괴리를 가시화한다.
        area_override_meta = self._area_override_meta(site_raw, land_area_sqm)

        meta: dict[str, Any] = {
            "use_llm": use_llm,
            # 라이브DB/공공API/LLM 실호출 가능 여부 — 배포 환경 게이팅(자기 라이브성 과소표기 제거).
            #   settings.DEPLOY_PENDING(기본 True=배포 전)로 게이팅한다. 라이브 배포 시 False.
            "deploy_pending": self._deploy_pending(),
            "deploy_pending_note": (
                "라이브 DB·공공데이터 API·LLM 실호출은 배포 환경에서만 동작합니다"
                "(샌드박스 검증은 순수 로직·계약 단위테스트 기준)."
            ),
        }
        if area_override_meta is not None:
            meta["area_override"] = area_override_meta

        # ── ★SpecialistAgent 모세혈관 배선(소비처 연결) — 결정론 도메인 auto-dispatch ──
        #   부지·인허가 raw에서 추출한 데이터로 zoning/permit 전문가를 호출해 findings·prior 모순·
        #   원장 cite를 브리프에 주입한다. LLM·과금 0(결정론 도메인만)·전체 graceful(실패는 빈 list).
        specialists = (
            await self._run_specialists(
                site_raw=site_raw, reg_raw=reg_raw, permit_raw=permit_raw,
                use_llm=use_llm,
                tenant_id=tenant_id, project_id=project_id, address=address,
            )
            if include_specialists else []
        )

        brief = {
            "address": address,
            "project_id": project_id,
            "parcel_count": parcel_count,
            "parts": parts,
            "verdict": verdict,
            "specialists": specialists,
            "billing": self._billing(use_llm),
            "meta": meta,
        }

        # ── 캐시 저장(best-effort) — 멱등 upsert ──
        await analysis_cache.cache_put(_CACHE_KIND, cache_key, brief)
        return brief

    # ------------------------------------------------------------------
    # 도메인 호출(각 기존 엔진 재사용) — 예외는 상위에서 분류 처리
    # ------------------------------------------------------------------

    async def _run_site_market(
        self, address: str | None, tenant_id: str | None,
        project_id: str | None, use_llm: bool,
    ) -> dict[str, Any]:
        """부지/입지+시장 = ComprehensiveAnalysisService.analyze 재사용."""
        if not address:
            raise _DomainSkipError("주소 미확보 — 부지/시장 분석은 주소 기준입니다.")
        from app.services.land_intelligence.comprehensive_analysis_service import (
            ComprehensiveAnalysisService,
        )
        # use_llm=False면 llm_provider 미지정으로 호출(인터프리터 LLM 생략 경로 유지).
        # ★include_specialists=False: decision_brief는 _run_specialists에서 zoning+permit을 자체
        #   디스패치하므로, comprehensive의 zoning 디스패치를 끄고 이중 디스패치/중복 원장기록을 피한다.
        return await ComprehensiveAnalysisService().analyze(
            address=address,
            llm_provider="anthropic" if use_llm else None,
            tenant_id=tenant_id,
            project_id=project_id,
            include_specialists=False,
        )

    async def _run_regulation(self, address: str | None, use_llm: bool) -> dict[str, Any]:
        """법규 = RegulationAnalysisService.analyze 재사용(상위법령→조례·법령링크·근거)."""
        if not address:
            raise _DomainSkipError("주소 미확보 — 법규 계층 분석은 주소 기준입니다.")
        from app.services.regulation.regulation_analysis_service import (
            RegulationAnalysisService,
        )
        return await RegulationAnalysisService().analyze(address, use_llm=use_llm)

    async def _run_permit_design(
        self, address: str | None, equity_won: int | None, use_llm: bool,
        land_area_sqm: float | None = None,
    ) -> dict[str, Any]:
        """인허가+설계개요 Top3 = FeasibilityServiceV2.auto_recommend_top3 재사용.

        ★통합면적 verdict 종단배선(land_area_sqm): 엔진(auto_recommend_top3)은 land_area_sqm 을
        수용해(feasibility_service_v2.py:92 — site_area = land_area_sqm or zoning area or 1000)
        FAR→GFA→세대수→매출→ROI 전체를 그 면적 기준으로 산정한다. 따라서 프론트가 보낸 다필지
        통합면적을 여기서 엔진에 전달하면 '표시 GFA(통합면적)'와 '판정 ROI'가 같은 면적 기준이
        되어 단위 괴리(표시≠판정)가 실제로 봉합된다. 양수일 때만 전달(0/음수/None=무회귀로 엔진
        대표면적 사용). 이 결과는 _developer_go_nogo 가 recommend_override 로 페르소나에 핸드오프해
        Go/No-Go 도 동일 통합면적 기준으로 나온다(이중 재계산 방지·정합).
        """
        if not address:
            raise _DomainSkipError("주소 미확보 — Top3 사업모델은 주소 기준입니다.")
        from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
        kwargs: dict[str, Any] = {"address": address, "use_llm": use_llm}
        # ★0(전액 차입) 구분: 'if equity_won' 은 0을 falsy 로 보아 자기자본=0 입력을 누락시킨다.
        #   'is not None' 로 명시 분기해, 자기자본 0(레버리지 100%) 시나리오도 엔진에 전달한다.
        if equity_won is not None:
            kwargs["equity_won"] = int(equity_won)
        # ★통합면적 종단배선 — 양수일 때만 엔진에 전달(가짜 0면적 차단·무회귀 보수).
        if isinstance(land_area_sqm, (int, float)) and land_area_sqm > 0:
            kwargs["land_area_sqm"] = float(land_area_sqm)
        return await FeasibilityServiceV2().auto_recommend_top3(**kwargs)

    # ------------------------------------------------------------------
    # SpecialistAgent 모세혈관 배선(소비처 연결) — 결정론 도메인 auto-dispatch
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_dev_type(permit_raw: dict[str, Any] | None) -> str:
        """Top3(auto_recommend_top3) raw에서 대표 개발방식 코드(M코드)를 best-effort 추출.

        ★실엔진 계약 = auto_recommend_top3 의 recommendations[i]['development_type']('M06' 등 코드).
        permit 도구(check_permit_feasibility)는 이 M코드를 ZONE_PERMIT_MATRIX 와 매칭하므로 반드시
        코드를 넘겨야 한다. type_name(한글명, 예 '일반분양')은 매트릭스 키가 아니므로 추출 대상에서
        제외한다(한글명을 넘기면 항상 '불가'로 오판). 미확보면 '' 반환 — permit 은 dev_type 미상이면
        보수적으로 '불가'로 본다(가짜 통과를 만들지 않음)."""
        if not isinstance(permit_raw, dict):
            return ""
        recs = (
            permit_raw.get("recommendations")
            or permit_raw.get("top3")
            or permit_raw.get("recommended_models")
            or []
        )
        first = recs[0] if isinstance(recs, list) and recs and isinstance(recs[0], dict) else {}
        # development_type(실엔진 정본·M코드) 최우선. 나머지는 형태변동 대비 폴백(type_name은 의도적 제외).
        for k in ("development_type", "dev_type", "type", "model_key", "model"):
            v = first.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    async def _run_specialists(
        self, *,
        site_raw: dict[str, Any] | None,
        reg_raw: dict[str, Any] | None,
        permit_raw: dict[str, Any] | None,
        use_llm: bool = False,
        tenant_id: str | None,
        project_id: str | None,
        address: str | None,
    ) -> list[dict[str, Any]]:
        """SpecialistAgent를 부지·인허가 데이터로 auto-dispatch(분석 코어 소비처 연결).

        SpecialistAgent 계층(결정론 도구 → prior → 원장 cite → 모순탐지)을 의사결정 브리프의
        실제 소비처로 연결한다(이전엔 dispatch 엔드포인트만 있고 호출하는 곳이 없어 미배선).
        - 기본(무과금·결정론): zoning(용도지역 허용용도)·permit(대표 개발방식 인허가 가능성).
          interpreter/panel 미장착 = LLM·과금 0.
        - ★use_llm 옵트인 시 추가: cost·market(LLM 다관점 패널=과금)·심의·설계(외부 심의엔진).
          과금=관리자설정·미설정 시 무료 원칙에 따라 기본 off. 심의/설계는 Stage1엔 상세 설계도면
          (rules/elements) 부재라 zone·주소 기반 프로세스만 — 엔진 미설정/입력부족 시 graceful
          unavailable로 정직 표면화(가짜 결과 생성 안 함).
        - 전체·도메인별 graceful: 데이터 부족/실패는 unavailable 엔트리로 표면화, 브리프는 무손상.
        반환: [{domain, status, ...}] (공용 헬퍼 run_specialist_domains 계약).
        """
        site_raw = site_raw if isinstance(site_raw, dict) else {}
        reg_raw = reg_raw if isinstance(reg_raw, dict) else {}
        zone = site_raw.get("zone_type") or reg_raw.get("zone_type")
        if not zone:
            # 용도지역 없으면 결정론 도메인 입력 불가 — 가짜 디스패치 대신 정직 스킵.
            return []
        dev_type = self._pick_dev_type(permit_raw)
        # ★pnu 전파: 원장 체인은 pnu 우선 키이므로, comprehensive(pnu 키 기록)와 동일 체인에 묶여
        #   prior 모순탐지가 단절되지 않도록 site_raw의 pnu를 함께 넘긴다(없으면 None=address 키 폴백).
        pnu = site_raw.get("pnu") or reg_raw.get("pnu")
        domains: dict[str, dict[str, Any]] = {
            "zoning": {"zone_type": zone},
            "permit": {"zone_type": zone, "dev_type": dev_type},
        }
        if use_llm:
            # cost: 결정론 공사비(상수×GFA) + LLM 다관점 패널. GFA는 부지 supply_areas 우선·면적×용적률 폴백.
            eff = site_raw.get("effective_far") or {}
            far = eff.get("effective_far_pct")
            area = site_raw.get("land_area_sqm")
            gfa = self._pick_supply_gfa(site_raw.get("supply_areas"), far, area) or self._gfa_from_area_far(area, far)
            # ★official_price: comprehensive 는 land_prices(sec3)에 중첩 — top-level 아님. 중첩 우선·폴백.
            _lp = site_raw.get("land_prices") if isinstance(site_raw.get("land_prices"), dict) else {}
            official = _lp.get("official_price_per_sqm") or site_raw.get("official_price_per_sqm")
            # ★입력 가드(빈 입력에 LLM 패널 과금 방지 — zoning/permit의 입력가드와 동일 원칙):
            #   GFA 산출 가능할 때만 cost, 공시지가 신호 있을 때만 market 디스패치(가짜 0원/빈 시장 분석 금지).
            if gfa:
                domains["cost"] = {"dev_type": dev_type, "gfa_sqm": gfa}
            if official:
                domains["market"] = {"official_price_per_sqm": official}
            # 심의·설계: 외부 심의엔진(/permit·design/process). Stage1 가용 컨텍스트(용도지역·대지면적·
            #   계획 연면적·개발방식)를 엔진 입력으로 정규화 공급 → legal_precheck(법정 용적/건폐 한도+근거)
            #   + massing 용량검증(계획 GFA vs 법정 최대 연면적)이 실수치 산출(이전엔 zone·주소만 → 빈 결과).
            #   상세 도면(rules/elements) 부재분은 엔진이 HELD/NEEDS_INPUT로 정직 표면화(가짜 생성 0).
            #   엔진 미설정/처리불가(summary.available=False)면 헬퍼가 status='unavailable'로 정직 강등.
            #   pnu는 19자리 ASCII 정규형만 전송(전각/유니코드 숫자 포함 비규격은 엔진 ASCII 패턴 422 →
            #   빈값 전송으로 address 지오코딩 폴백, 무음 실패 방지).
            _pnu_s = str(pnu) if pnu else ""
            _pnu19 = _pnu_s if (_pnu_s.isascii() and _pnu_s.isdigit() and len(_pnu_s) == 19) else ""
            _engine_input: dict[str, Any] = {"pnu": _pnu19, "address": address, "use_zone": zone}
            if dev_type:
                _engine_input["dev_type"] = dev_type
            # 대지면적 → plot_area 산정입력(calc_targets) — 용량검증·용적/건폐 비율의 분모(부재 시 엔진 '미상').
            if isinstance(area, (int, float)) and not isinstance(area, bool) and area > 0:
                _engine_input["calc_targets"] = [
                    {"target": "plot_area", "payload": {"parcel_area": float(area)}}]
            domains["심의"] = dict(_engine_input)
            # 설계는 추가로 계획 GFA를 provided로 공급 → massing 용량검증(제안 GFA ≤ 최대 연면적 = 대지×용적률)
            #   수행. program=기획정보(용도·규모) 가용 표시(기획 단계 완결성). 상세 매스/배치/평면은 도면 확보 후.
            _design_input = dict(_engine_input)
            _design_provided: dict[str, Any] = {"program": True}
            if gfa:
                _design_provided["proposed_gfa"] = float(gfa)
            _design_input["provided"] = _design_provided
            domains["설계"] = _design_input
        # ★dispatch·graceful·status 표준화는 공용 헬퍼 단일경유(comprehensive 부지분석과 동일 경로).
        from app.services.agents.specialist_dispatch import run_specialist_domains

        return await run_specialist_domains(
            domains,
            tenant_id=tenant_id, project_id=project_id, address=address, pnu=pnu,
        )

    # ------------------------------------------------------------------
    # 표준 요약 계약 — 도메인별 변환(프론트 도메인무관 동일 렌더)
    # ------------------------------------------------------------------

    def _summarize_site_market(
        self, raw: dict[str, Any] | None, parcel_count: int,
        land_area_override: float | None = None,
    ) -> dict[str, Any]:
        """부지/입지+시장 → 표준 요약 계약.

        ★이 메서드는 gather 경계 밖(build)에서 직접 호출되므로 여기서 크래시하면 전체 브리프가
        500으로 깨진다. 따라서 변환 로직 전체를 try/except로 감싸 어떤 키 형태 변동에도 part 만
        'unavailable'로 강등(graceful)하고 분류 로깅한다(silent-fail·HTTP500 금지).

        ★land_area_override(다필지 통합면적 종단배선): 양수면 엔진이 낸 대표면적(raw.land_area_sqm)
        대신 이 면적을 대지면적 KPI로 쓰고, 계획 GFA 도 이 면적 기준으로 재계산한다
        (GFA = override_area × 실효용적률/100). 통합면적이 KPI에 실반영된다. None/0/음수면
        엔진 대표면적을 그대로 쓴다(무회귀). 공유 엔진(ComprehensiveAnalysisService)은 비변경.
        """
        if not raw or raw.get("_unavailable"):
            return self._unavailable_part(PART_SITE_MARKET, "부지·시장 종합", raw,
                                          detail_route="/projects/{id}/canvas")
        try:
            eff = raw.get("effective_far") or {}
            far = eff.get("effective_far_pct")
            bcr = eff.get("effective_bcr_pct")
            # ★override 면적 우선(다필지 통합면적). 양수일 때만 대표면적을 대체한다(무회귀 보수).
            override_area = (
                float(land_area_override)
                if isinstance(land_area_override, (int, float)) and land_area_override > 0
                else None
            )
            area = override_area if override_area is not None else raw.get("land_area_sqm")
            # ★supply_areas 계약 = ComprehensiveAnalysisService._calc_supply_areas 가 반환하는
            #   list[dict](permit_complexity 오름차순 정렬, 키 total_gfa_sqm·applied_far_pct·
            #   permit_complexity). 과거 dict.get('total_gfa_sqm') 오접근은 list에서 조용히 None을
            #   내어 '계획 GFA 미확보'를 은폐(silent-fail)했다. sale_prices 와 동형 헬퍼로 list 우선
            #   추출 — 인허가 단순(permit_complexity 최소)·applied_far 최대 물건의 total_gfa_sqm 를
            #   대표 계획 연면적으로 쓴다. list 부재 시 실효용적률×대지면적 단일산식으로 폴백한다.
            # ★GFA 산정: override 면적이 주어지면 supply_areas(엔진 대표면적 기준 산출값)를 쓰지
            #   않고 'override_area × 실효용적률/100' 단일산식으로 재계산한다 — 통합면적이 GFA에
            #   실반영(다필지 통합 KPI 일관). override 없으면 기존대로 supply_areas 우선·폴백 산식.
            if override_area is not None:
                gfa = self._gfa_from_area_far(override_area, far)
            else:
                gfa = self._pick_supply_gfa(raw.get("supply_areas"), far, area)
            # ★sale_prices 계약 = ComprehensiveAnalysisService._calc_sale_prices 가 반환하는
            #   list[dict](키 sale_price_per_pyeong_man). 과거 dict.get() 오접근이 AttributeError →
            #   HTTP500을 냈다. list 첫 물건의 평당 분양가(만원)를 대표값으로 쓴다.
            sale_pp = self._pick_sale_price_per_pyeong(raw.get("sale_prices"))
            zone = raw.get("zone_type") or "-"

            gfa_val = round(gfa, 1) if isinstance(gfa, (int, float)) else None
            # ★key = 안정 식별자(라벨 변경에도 프론트 findMetric이 silent-null 안 나게).
            #   라벨은 표시 전용, key는 TS DecisionKeyMetric.key와 1:1(decision-brief-types.ts).
            key_metrics: list[dict[str, Any]] = [
                {"key": "zone", "label": "용도지역", "value": zone, "unit": ""},
                {"key": "land_area", "label": "대지면적", "value": area, "unit": "㎡"},
                {"key": "effective_far", "label": "실효 용적률", "value": far, "unit": "%"},
                {"key": "effective_bcr", "label": "실효 건폐율", "value": bcr, "unit": "%"},
                {"key": "gfa", "label": "계획 연면적(GFA)", "value": gfa_val, "unit": "㎡"},
                {"key": "presale_price", "label": "예상 분양가", "value": sale_pp, "unit": "만원/평"},
            ]
            if parcel_count > 1:
                key_metrics.insert(0, {
                    "key": "parcel_count", "label": "통합 필지수",
                    "value": parcel_count, "unit": "필지",
                })

            # 특이부지(개발가능성)는 한줄 요약·confidence에 반영.
            developability = raw.get("developability")
            special = raw.get("special_parcel") or {}
            oneliner = (
                f"{zone} · 실효 용적률 {far if far is not None else '미확보'}% · "
                f"계획 GFA {round(gfa, 0) if isinstance(gfa, (int, float)) else '미확보'}㎡"
            )
            if developability and developability != "POSSIBLE":
                oneliner += f" · 특이부지({special.get('severity_label') or developability})"
            # 다필지 정직 고지: override 통합면적이 반영됐으면 '통합면적 기준', 아니면 '대표필지 기준'.
            #   (용도지역·법규 한도는 대표필지 산출이므로 그 한계는 그대로 고지한다.)
            if parcel_count > 1:
                if override_area is not None:
                    oneliner += f" · 통합면적 기준({parcel_count}필지·용도/법규는 대표필지)"
                else:
                    oneliner += f" · 대표필지 기준(통합 {parcel_count}필지)"

            return {
                "part": PART_SITE_MARKET,
                "title": "부지·입지·시장",
                "summary_oneliner": oneliner,
                "key_metrics": key_metrics,
                "evidence": raw.get("evidence") or [],
                "legal_links": self._legal_links(raw.get("legal_refs")),
                "confidence": self._confidence_from_developability(developability),
                "detail_route": "/projects/{id}/canvas",
                "status": "ok",
            }
        except Exception as e:  # noqa: BLE001 — 변환 실패는 part만 강등(전체 무손상)
            logger.warning(
                "부지·시장 요약 변환 실패 — part unavailable 강등",
                error_type=type(e).__name__, error=str(e)[:200],
            )
            return self._unavailable_part(
                PART_SITE_MARKET, "부지·시장 종합",
                {"reason": f"요약 변환 오류({type(e).__name__}) — 원본 데이터 형태를 확인하세요."},
                detail_route="/projects/{id}/canvas",
            )

    @staticmethod
    def _pick_sale_price_per_pyeong(sale_prices: Any) -> Any:
        """sale_prices(list[dict] 계약)에서 대표 평당 분양가(만원)를 뽑는다.

        ComprehensiveAnalysisService 계약은 list[dict](sale_price_per_pyeong_man).
        하위호환: 혹시 dict로 오면 estimated/avg 키를 시도(가짜값 생성은 않음).
        """
        if isinstance(sale_prices, list):
            for item in sale_prices:
                if isinstance(item, dict):
                    v = item.get("sale_price_per_pyeong_man")
                    if v is not None:
                        return v
            return None
        if isinstance(sale_prices, dict):
            return (sale_prices.get("estimated_price_per_pyeong")
                    or sale_prices.get("avg_price_per_pyeong"))
        return None

    @staticmethod
    def _gfa_from_area_far(land_area_sqm: Any, effective_far_pct: Any) -> Any:
        """대지면적(㎡) × 실효용적률(%) → 계획 연면적(GFA, ㎡). 실측 산식(가짜값 아님).

        GFA = 대지면적 × 용적률/100. 둘 중 하나라도 비-수치/비양수면 None(미확보 정직).
        면적 종단배선(override) 과 supply_areas 폴백이 같은 산식을 공유하도록 단일화한다.
        """
        if (isinstance(effective_far_pct, (int, float))
                and isinstance(land_area_sqm, (int, float)) and land_area_sqm > 0):
            return round(land_area_sqm * (effective_far_pct / 100.0), 1)
        return None

    @staticmethod
    def _pick_supply_gfa(
        supply_areas: Any, effective_far_pct: Any, land_area_sqm: Any,
    ) -> Any:
        """supply_areas(list[dict] 계약)에서 대표 계획 연면적(GFA, ㎡)을 뽑는다.

        ★정본 계약 = ComprehensiveAnalysisService._calc_supply_areas → list[dict]
        (permit_complexity 오름차순 정렬, 키 total_gfa_sqm·applied_far_pct·permit_complexity).
        과거 dict.get('total_gfa_sqm') 로 list 를 읽어 조용히 None(GFA 미확보 은폐)이 됐다.

        선택 규칙: 인허가가 단순한(permit_complexity 최소) 물건들 중 적용 용적률(applied_far_pct)이
        최대인 물건의 total_gfa_sqm 를 대표 GFA 로 쓴다(가장 현실적·달성 가능한 최대 규모).
        list 부재/빈값이면 실효용적률×대지면적 단일산식으로 폴백한다(가짜값 생성 아님 — 실측 산식).
        하위호환: 혹시 dict 로 오면 total_gfa_sqm/gfa_sqm 키를 직접 시도한다.
        """
        if isinstance(supply_areas, list):
            candidates = [s for s in supply_areas
                          if isinstance(s, dict) and s.get("total_gfa_sqm") is not None]
            if candidates:
                # permit_complexity 오름차순(없으면 큰값) → applied_far_pct 내림차순으로 최선 물건.
                def _rank(s: dict[str, Any]) -> tuple[float, float]:
                    pc = s.get("permit_complexity")
                    af = s.get("applied_far_pct")
                    return (
                        float(pc) if isinstance(pc, (int, float)) else 999.0,
                        -(float(af) if isinstance(af, (int, float)) else 0.0),
                    )
                best = sorted(candidates, key=_rank)[0]
                return best.get("total_gfa_sqm")
            # list 지만 total_gfa_sqm 가 전혀 없으면 단일산식 폴백으로 진행(아래).
        elif isinstance(supply_areas, dict):
            gfa = supply_areas.get("total_gfa_sqm") or supply_areas.get("gfa_sqm")
            if gfa is not None:
                return gfa
        # 폴백: 실효용적률(%) × 대지면적(㎡) — 실측 산식(공용 _gfa_from_area_far 로 단일화).
        return DecisionBriefService._gfa_from_area_far(land_area_sqm, effective_far_pct)

    def _summarize_regulation(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        """법규 계층 → 표준 요약 계약.

        ★graceful 대칭(_summarize_site_market 과 동형): 이 메서드도 gather 경계 밖(build)에서
        직접 호출되므로 키 형태 변동(계약 드리프트)에 크래시하면 전체 브리프가 HTTP500으로 깨진다.
        docstring 약속('어떤 키 변동에도 part 만 강등')을 지키려면 변환 전체를 try/except 로 감싸
        part 만 'unavailable' 강등 + 분류 로깅한다(silent-fail·HTTP500 금지).
        ★detail_route 는 실재 프론트 라우트(/projects/{id}/legal)만 사용한다(/regulation 은 404).
        """
        # 실재 확인된 라우트만 사용(죽은링크 금지) — apps/web .../projects/[id]/legal 존재.
        detail_route = "/projects/{id}/legal"
        if not raw or raw.get("_unavailable"):
            return self._unavailable_part(PART_REGULATION, "법규 계층", raw,
                                          detail_route=detail_route)
        try:
            limits = raw.get("limits") or {}
            far = (limits.get("far") or {})
            bcr = (limits.get("bcr") or {})
            districts = raw.get("districts") or []
            high_impact = [d.get("name") for d in districts if isinstance(d, dict) and d.get("impact") == "상"]
            zone = raw.get("zone_type") or "-"

            # ★key = 안정 식별자(라벨 변경 silent-null 차단). 라벨은 표시 전용.
            key_metrics = [
                {"key": "far_trio", "label": "용적률(법정/조례/실효)",
                 "value": self._trio_str(far), "unit": "%"},
                {"key": "bcr_trio", "label": "건폐율(법정/조례/실효)",
                 "value": self._trio_str(bcr), "unit": "%"},
                {"key": "district_count", "label": "적용 규제·지구 수",
                 "value": len(districts), "unit": "건"},
                {"key": "high_impact", "label": "고영향 규제",
                 "value": ", ".join([h for h in high_impact if h]) or "없음", "unit": ""},
            ]

            # 법규 차단성: 특이부지(개발제한 등 고영향) → confidence/한줄에 반영.
            special = raw.get("special_parcel") or {}
            oneliner = f"{zone} · 적용 규제 {len(districts)}건"
            if high_impact:
                oneliner += f" · 고영향 {len(high_impact)}건({', '.join([h for h in high_impact if h][:2])})"

            return {
                "part": PART_REGULATION,
                "title": "법규·규제",
                "summary_oneliner": oneliner,
                "key_metrics": key_metrics,
                "evidence": raw.get("evidence") or [],
                "legal_links": self._regulation_legal_links(raw.get("hierarchy")),
                "confidence": self._confidence_from_developability(
                    special.get("developability") if special else "POSSIBLE"
                ),
                "detail_route": detail_route,
                "status": "ok",
            }
        except Exception as e:  # noqa: BLE001 — 변환 실패는 part만 강등(전체 무손상)
            logger.warning(
                "법규 요약 변환 실패 — part unavailable 강등",
                error_type=type(e).__name__, error=str(e)[:200],
            )
            return self._unavailable_part(
                PART_REGULATION, "법규 계층",
                {"reason": f"요약 변환 오류({type(e).__name__}) — 원본 데이터 형태를 확인하세요."},
                detail_route=detail_route,
            )

    def _summarize_permit_design(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        """인허가+설계개요 Top3 → 표준 요약 계약.

        ★graceful 대칭(_summarize_site_market 과 동형): gather 경계 밖에서 직접 호출되므로 변환
        실패가 전체 브리프 HTTP500 으로 번지지 않도록 변환 전체를 try/except 로 감싸 part 만
        'unavailable' 강등 + 분류 로깅한다(silent-fail·HTTP500 금지).
        """
        detail_route = "/projects/{id}/feasibility"
        if not raw or raw.get("_unavailable"):
            return self._unavailable_part(PART_PERMIT_DESIGN, "인허가·사업모델 Top3", raw,
                                          detail_route=detail_route)
        try:
            recs = raw.get("recommendations") or []
            top1 = recs[0] if recs else {}
            feas = (top1.get("feasibility") or {}) if isinstance(top1, dict) else {}
            scenario_status = raw.get("scenario_status")  # "actual" | "tentative"
            honest = raw.get("honest_disclosure")

            top1_name = top1.get("type_name") if isinstance(top1, dict) else None
            # ★key = 안정 식별자(라벨 변경 silent-null 차단). 라벨은 표시 전용.
            key_metrics = [
                {"key": "top1_model", "label": "추천 1순위 모델", "value": top1_name, "unit": ""},
                {"key": "roi", "label": "1순위 ROI(사업수익률)", "value": feas.get("roi_pct"), "unit": "%"},
                {"key": "net_profit", "label": "1순위 순이익", "value": feas.get("net_profit_won"), "unit": "원"},
                {"key": "grade", "label": "1순위 등급", "value": feas.get("grade"), "unit": ""},
                {"key": "types_analyzed", "label": "분석 사업유형 수",
                 "value": raw.get("total_types_analyzed"), "unit": "종"},
                {"key": "effective_far_top3", "label": "실효 용적률(Top3 산정)",
                 "value": raw.get("effective_far_pct"), "unit": "%"},
            ]

            # 잠정 시나리오(선행절차 전제)면 확정 % 노출 억제 신호.
            oneliner = (
                f"추천 {top1.get('type_name') or '미확보'} · "
                f"ROI {feas.get('roi_pct') if feas.get('roi_pct') is not None else '미확보'}% · "
                f"{len(recs)}개 Top 모델"
            )
            if scenario_status == "tentative":
                oneliner += " · 잠정(선행절차 전제)"

            # 토지비 신뢰성 False·잠정이면 confidence 하향.
            if not recs:
                confidence = "low"
            elif scenario_status == "tentative" or raw.get("land_price_reliable") is False:
                confidence = "medium"
            else:
                confidence = "high"

            part = {
                "part": PART_PERMIT_DESIGN,
                "title": "인허가·사업모델 Top3",
                "summary_oneliner": oneliner,
                "key_metrics": key_metrics,
                "evidence": [],
                "legal_links": [],
                "confidence": confidence,
                "detail_route": detail_route,
                "status": "ok",
                "scenario_status": scenario_status,
            }
            if honest:
                part["honest_disclosure"] = honest
            return part
        except Exception as e:  # noqa: BLE001 — 변환 실패는 part만 강등(전체 무손상)
            logger.warning(
                "인허가·Top3 요약 변환 실패 — part unavailable 강등",
                error_type=type(e).__name__, error=str(e)[:200],
            )
            return self._unavailable_part(
                PART_PERMIT_DESIGN, "인허가·사업모델 Top3",
                {"reason": f"요약 변환 오류({type(e).__name__}) — 원본 데이터 형태를 확인하세요."},
                detail_route=detail_route,
            )

    # ------------------------------------------------------------------
    # 종합 verdict(디벨로퍼 Go/No-Go 재사용 + 강등)
    # ------------------------------------------------------------------

    async def _build_verdict(
        self, *, db: Any | None, address: str | None, project_id: str | None,
        parcels: list[str] | None, equity_won: int | None,
        site_raw: dict[str, Any] | None, reg_raw: dict[str, Any] | None,
        permit_raw: dict[str, Any] | None, use_llm: bool,
        override_area: float | None = None,
    ) -> dict[str, Any]:
        """단일 종합 판정(GO/CONDITIONAL/HOLD).

        1) 디벨로퍼 페르소나 run_persona('developer')의 Go/No-Go(go_nogo)를 재사용한다(있으면).
           run_persona 호출엔 AsyncSession(db)이 필요 — 미주입 시 Top3 결과 기반 폴백.
        2) ★특이부지(developability!=POSSIBLE)·법규 BLOCKED는 자동 강등(가짜 GO 금지):
           BLOCK → HOLD, TENTATIVE/CONDITIONAL → 최대 CONDITIONAL.
        3) ★단위 일관성 고지(override_area·iter-5 갭 봉합 반영): 통합면적은 이제 Top3 엔진
           (auto_recommend_top3)에 land_area_sqm 으로 전달돼 수익성 판정(ROI)도 통합면적 기준으로
           산정된다 — 표시 GFA 와 판정 ROI 의 '단위 괴리'는 실제로 봉합됐다(iter-5). 다만 부지 카드의
           '정성 분석'(용도지역·실효용적률·특이부지 판정)은 공유 엔진(ComprehensiveAnalysisService.
           analyze)이 address만 받아 산출한 대표필지 기준이라는 잔여 격차가 남는다. 따라서 통합면적이
           대표면적과 유의미하게 다를 때만, reasons에 '규모·수익성은 통합면적 기준이나 용도지역/규제
           판정은 대표필지 기준'이라는 잔여 격차 고지를 넣는다(이전 '판정=엔진 대표면적' 고지는 갭
           봉합으로 폐기). 정밀 통합 규제·수지는 상세 사업성 단계가 SSOT.
        """
        reasons: list[str] = []
        blockers: list[str] = []

        # 1) 디벨로퍼 Go/No-Go(있으면) — 라우터 우회 service 직접 호출.
        #    ★정본 소비형태(persona.runner:528·developer_report.py:129) = artifacts['go_nogo']은
        #    inner value dict({decision,top1,grade,roi_pct}) 그 자체다(status/value 래핑 없음).
        #    따라서 go_nogo.get('decision') 한국어 문구를 직접 읽어 매핑한다(dead-wire 제거).
        go_nogo = await self._developer_go_nogo(
            db=db, address=address, project_id=project_id,
            parcels=parcels, equity_won=equity_won, use_llm=use_llm,
            permit_raw=permit_raw, land_area_sqm=override_area,
        )
        base_decision = "HOLD"
        base_conf = "low"
        # 잠정 사유의 '보류'(차단 아닌 조건부)인지 — TENTATIVE 게이트 상향 허용 판별용.
        base_tentative_hold = False
        if go_nogo and go_nogo.get("decision"):
            base_decision, base_conf, base_tentative_hold = self._map_go_nogo_decision(go_nogo.get("decision"))
            reasons.append(f"디벨로퍼 Go/No-Go: {go_nogo.get('decision')}")
        elif go_nogo:
            # 페르소나는 떴으나 사업타당성 미확보(value.decision 없음) → 판정 보류.
            base_decision, base_conf = "HOLD", "low"
            reasons.append("사업타당성(Top3 수지) 미확보 — 판정 보류")
        else:
            # 폴백: Top3 결과로 직접 판정(db 미주입·페르소나 실패 시).
            base_decision, base_conf = self._fallback_decision(permit_raw, reasons)

        # 2) 특이부지/법규 강등 — gate_decision SSOT 재사용(가짜 GO 차단).
        decision = base_decision
        confidence = base_conf
        gate = self._gate_from_raw(site_raw, reg_raw, permit_raw)
        if gate == "BLOCK":
            decision = "HOLD"
            confidence = "low"
            blockers.append("특이부지/법규 차단 — 통상 절차로 해결 불가능한 제약(개발규모 미산정·정직).")
        elif gate == "TENTATIVE":
            # ★잠정 게이트(선행절차 전제) — 플랫폼 컨벤션상 '잠정=CONDITIONAL'.
            #   GO여도 최대 CONDITIONAL로 강등(가짜 확정 GO 금지).
            if decision == "GO":
                decision = "CONDITIONAL"
                confidence = "medium"
            # ★HIGH(production↔폴백 일치): 잠정 사유의 '보류'(차단 아닌 조건부)는 CONDITIONAL로
            #   상향한다. production(go_nogo='보류(선행절차/신뢰성 전제)')과 폴백(scenario_status=
            #   'tentative'→CONDITIONAL)이 동일 결과가 되도록 통일. 진짜 No-Go HOLD 는 상향 안 함.
            elif decision == "HOLD" and base_tentative_hold:
                decision = "CONDITIONAL"
                confidence = "medium"
                reasons.append("잠정 보류(선행절차/신뢰성 전제) — 조건부로 해석(차단 아님)")
            blockers.append("특이부지/도로·인허가 선행절차 전제 — 확정 GO 강등(잠정).")

        # (법규 BLOCK/특이 신호는 이미 _gate_from_raw 가 reg_raw.special_parcel 까지 종합해
        #  BLOCK→HOLD·TENTATIVE→CONDITIONAL 로 강등하므로 별도 reg 강등 블록은 제거 — 중복 방지.)

        # ★잔여 격차 정직 고지(iter-5 갭 봉합 반영) — 통합면적은 이제 Top3 엔진에 전달돼 규모(GFA)와
        #   수익성 판정(ROI)이 같은 통합면적 기준이다(단위 괴리 봉합). 다만 용도지역/규제·특이부지 판정은
        #   공유 엔진이 대표필지(주소) 기준으로 산출하므로, 통합면적이 대표면적과 유의미하게 다를 때만
        #   '규모·수익성=통합면적 기준, 용도/규제 판정=대표필지 기준'이라는 잔여 격차를 명시한다.
        if self._override_diverges(site_raw, override_area):
            reasons.append(
                "개략 규모(GFA)와 수익성 판정(ROI)은 통합면적 기준으로 산정했으나, 용도지역·규제·특이부지 "
                "판정은 대표필지(분석 주소) 기준입니다 — 정밀 통합 규제·수지는 상세 사업성 단계에서 산출합니다."
            )

        # go_nogo 패스스루 — 프론트 배지용 status 동반(정합형태). 원본 inner value dict 보존.
        go_nogo_out = self._go_nogo_passthrough(go_nogo, decision)

        return {
            "decision": decision,
            "confidence": confidence,
            "reasons": reasons,
            "blockers": blockers,
            "go_nogo": go_nogo_out,  # {decision,top1,grade,roi_pct,status}(투명성·배지)
            "gate": gate,
        }

    @staticmethod
    def _override_diverges(
        site_raw: dict[str, Any] | None, override_area: float | None,
    ) -> bool:
        """override 통합면적이 엔진 대표면적과 유의미하게 다른지(>5% 또는 엔진면적 미확보).

        override 가 양수일 때만 판단한다. 엔진 대표면적(site_raw.land_area_sqm)이 없으면 표시
        GFA(override)와 판정 기준(엔진 추정)이 다른 셈이라 True. 둘 다 있으면 5% 초과 차이만 True
        (반올림 오차·동일면적은 고지 생략 — 잡음 방지).
        """
        if not (isinstance(override_area, (int, float)) and override_area > 0):
            return False
        engine_area = (site_raw or {}).get("land_area_sqm")
        if not (isinstance(engine_area, (int, float)) and engine_area > 0):
            return True  # 엔진 대표면적 미확보 → 판정 기준이 표시 GFA 와 다름(고지)
        return abs(override_area - engine_area) / engine_area > 0.05

    @staticmethod
    def _area_override_meta(
        site_raw: dict[str, Any] | None, override_area: float | None,
    ) -> dict[str, Any] | None:
        """면적 override 괴리 메타 — 통합면적이 엔진 대표면적과 과도(>5배)하면 경고.

        라우터 Field(gt=0, le=1e7)를 통과한 값이라도, 엔진이 주소에서 도출한 대표면적과 5배 넘게
        차이나면 '다른 부지·단위오류·악의 입력' 가능성이 있어 권위 KPI 가 되기 전에 가시화한다.
        override 미적용(None/0/음수)이거나 엔진 대표면적 미확보면 None(메타 생략).
        """
        if not (isinstance(override_area, (int, float)) and override_area > 0):
            return None
        engine_area = (site_raw or {}).get("land_area_sqm")
        if not (isinstance(engine_area, (int, float)) and engine_area > 0):
            return None
        ratio = override_area / engine_area
        meta: dict[str, Any] = {
            "override_area_sqm": round(float(override_area), 1),
            "engine_area_sqm": round(float(engine_area), 1),
            "ratio": round(ratio, 2),
        }
        if ratio > 5 or ratio < 0.2:
            meta["warning"] = (
                "입력 통합면적이 엔진 대표면적과 5배 이상 차이납니다 — 면적/필지 입력을 확인하세요"
                "(잘못된 면적이 사업 규모·수익성 KPI 를 왜곡할 수 있습니다)."
            )
        return meta

    @staticmethod
    def _deploy_pending() -> bool:
        """라이브 호출 가능 여부 게이트 — DEPLOY_PENDING(명시) 우선, 미설정이면 APP_ENV로 추론.

        ★우선순위(라이브 배포 수동조치 의존 제거):
          1) DEPLOY_PENDING 이 .env/환경변수로 '명시' 설정됐으면 그 값을 그대로 쓴다(운영자 명시 의도 최우선).
          2) 명시되지 않았으면 APP_ENV 로 추론한다 — 'production'이면 라이브 환경이므로 자동 False
             (DEPLOY_PENDING=false 를 따로 설정하지 않아도 자기 라이브성을 과소표기하지 않음).
          3) 그 외(development/test/staging 등) 또는 설정 로딩 실패는 보수적으로 True(정직: 라이브
             확신 못 하면 '배포 전'으로 본다).

        ★명시 여부 판별: Settings.DEPLOY_PENDING 기본값은 True 라 bool 만으로는 '명시 True'와
        '기본 True'를 구분할 수 없다. pydantic-settings 의 model_fields_set(실제 입력으로 채워진
        필드 집합)에 'DEPLOY_PENDING'이 있으면 '명시'로 본다.
        """
        try:
            from app.core.config import settings
            fields_set = getattr(settings, "model_fields_set", None) or set()
            if "DEPLOY_PENDING" in fields_set:
                # 운영자가 .env/환경변수로 명시 설정 → 그 값 우선(자동 추론 무시).
                return bool(getattr(settings, "DEPLOY_PENDING", True))
            # 명시 안 됐으면 APP_ENV 로 추론 — production = 라이브 → False.
            app_env = str(getattr(settings, "APP_ENV", "") or "").strip().lower()
            if app_env == "production":
                return False
            return bool(getattr(settings, "DEPLOY_PENDING", True))
        except Exception:  # noqa: BLE001 — 설정 로딩 실패는 보수적으로 deploy_pending=True
            return True

    @staticmethod
    def _go_nogo_passthrough(
        go_nogo: dict[str, Any] | None, verdict_decision: str,
    ) -> dict[str, Any] | None:
        """페르소나 go_nogo(inner value dict)에 프론트 배지용 status를 더해 패스스루한다.

        status = 최종 verdict 결정과 정합(GO→go·CONDITIONAL→conditional·HOLD→hold).
        원본 키(decision/top1/grade/roi_pct)는 그대로 보존(투명성). go_nogo None이면 None.
        """
        if not go_nogo:
            return None
        status = {"GO": "go", "CONDITIONAL": "conditional", "HOLD": "hold"}.get(verdict_decision, "hold")
        return {**go_nogo, "status": status}

    async def _developer_go_nogo(
        self, *, db: Any | None, address: str | None, project_id: str | None,
        parcels: list[str] | None, equity_won: int | None, use_llm: bool,
        permit_raw: dict[str, Any] | None, land_area_sqm: float | None = None,
    ) -> dict[str, Any] | None:
        """디벨로퍼 Go/No-Go(inner value dict {decision,top1,grade,roi_pct})를 재사용한다.

        반환 계약: run_persona artifacts['go_nogo']와 동형(inner value dict). 미가용 시 None
        (상위가 Top3 폴백 판정). 예외도 None(graceful·분류 로깅).

        ★중복연산 제거(MED): 이미 산출한 Top3(permit_raw)를 recommend_override 로 페르소나 ctx에
        핸드오프해 _run_developer 가 auto_recommend_top3 를 재실행하지 않게 한다. 따라서 db가 있어도
        무거운 수지 재계산이 한 번만 일어난다.

        ★통합면적 정합(land_area_sqm): permit_raw(Top3)는 이미 통합면적 기준으로 산정됐고 그대로
        recommend_override 로 넘기므로 Go/No-Go(사업타당성) 판정도 통합면적 기준이다. land_area_sqm 은
        설계 매스(runner 의 land_area_sqm 경로)도 통합면적을 쓰도록 ctx 에 함께 전달한다(양수일 때만).
        """
        if db is None:
            return None
        recommend = permit_raw if (isinstance(permit_raw, dict) and not permit_raw.get("_unavailable")) else None
        try:
            from app.services.persona.runner import run_persona
            ctx: dict[str, Any] = {
                "project_id": project_id,
                "address": address,
                "parcels": parcels,
                "equity_won": equity_won,
            }
            # ★통합면적을 페르소나 ctx 에 전달 — 설계 매스 산출도 통합면적 기준(양수일 때만·무회귀).
            if isinstance(land_area_sqm, (int, float)) and land_area_sqm > 0:
                ctx["land_area_sqm"] = float(land_area_sqm)
            if recommend is not None:
                ctx["recommend_override"] = recommend  # Top3 핸드오프(재계산 방지)
            report = await run_persona("developer", db, ctx, use_llm=use_llm)
            return (report.get("artifacts") or {}).get("go_nogo")
        except Exception as e:  # noqa: BLE001 — 페르소나 실패는 폴백 판정으로 진행
            logger.warning("디벨로퍼 Go/No-Go 재사용 실패 — Top3 폴백 판정", err=str(e)[:120])
            return None

    @staticmethod
    def _map_go_nogo_decision(decision: str | None) -> tuple[str, str, bool]:
        """디벨로퍼 go_nogo 한국어 문구 → (verdict.decision, confidence, is_tentative_hold).

        ★정본 문구(persona.checklist.judge_dev_go_nogo):
          'Go(추진 권고)'·'추진' → GO / '조건부' → CONDITIONAL / '보류'·'No-Go' → HOLD.
        문구 변형에 견고하도록 부분일치(키워드)로 분기한다(정확매칭 실패 시 HOLD 보수).

        ★HIGH(잠정 비결정 해소): judge_dev_go_nogo 는 잠정(scenario_status='tentative' 또는
        land_price_reliable=False)일 때 '보류(선행절차/신뢰성 전제)'를 낸다. 이 '보류'는 사업을
        '차단'하는 No-Go 가 아니라 '선행절차가 충족되면 추진 가능한 조건부'다(플랫폼 컨벤션:
        잠정=CONDITIONAL). 폴백 경로(_fallback_decision)는 같은 입력을 이미 CONDITIONAL 로 낸다.
        둘의 불일치(production HOLD vs 폴백 CONDITIONAL)를 없애기 위해, 잠정 사유의 '보류'는
        is_tentative_hold=True 로 표시해 상위(TENTATIVE 게이트)가 HOLD→CONDITIONAL 로 상향하게 한다.
        반대로 'No-Go(재검토)'(진짜 차단)는 is_tentative_hold=False 로 HOLD 를 유지한다(가짜 GO 금지).
        """
        d = (decision or "").strip()
        dl = d.lower()
        # 진짜 차단(No-Go) — 잠정이 아닌 거절. HOLD 유지(상향 불가).
        if "No-Go" in d or "no-go" in dl:
            return "HOLD", "low", False
        # 잠정 사유의 '보류'(선행절차/신뢰성 전제) — 차단이 아닌 조건부 신호로 표시.
        #   judge_dev_go_nogo 정본 문구는 '보류(선행절차/신뢰성 전제)'. 키워드로 견고 판별.
        if "보류" in d:
            is_tentative = ("선행절차" in d) or ("신뢰성" in d) or ("전제" in d) or ("조건" in d)
            return "HOLD", "low", is_tentative
        if "조건부" in d:
            return "CONDITIONAL", "medium", False
        if "추진" in d or d == "Go" or d.startswith("Go("):
            return "GO", "high", False
        # 알 수 없는 문구는 가짜 GO 금지 원칙상 보수적으로 HOLD(상향 불가).
        return "HOLD", "low", False

    def _fallback_decision(
        self, permit_raw: dict[str, Any] | None, reasons: list[str],
    ) -> tuple[str, str]:
        """페르소나 미가용 시 Top3 결과로 직접 판정(checklist.judge_dev_go_nogo 규칙 동형)."""
        if not permit_raw or permit_raw.get("_unavailable"):
            reasons.append("사업타당성(Top3) 미확보 — 판정 보류")
            return "HOLD", "low"
        # ★계약감사: recommendations 는 list[dict] 정본이나, 계약 위반(비-list/항목 비-dict)이어도
        #   _build_verdict 는 gather 경계 밖에서 직접 호출되므로 여기서 크래시하면 HTTP500 으로 번진다.
        #   타입 가드로 비정상 형태를 정직 보류(HOLD)로 강등한다(silent-fail·HTTP500 금지).
        recs_raw = permit_raw.get("recommendations")
        recs = recs_raw if isinstance(recs_raw, list) else []
        top = recs[0] if recs and isinstance(recs[0], dict) else None
        if top is None:
            reasons.append("추천 사업모델 없음 — 판정 보류")
            return "HOLD", "low"
        feas = top.get("feasibility") or {}
        grade = feas.get("grade")
        roi = feas.get("roi_pct")
        tentative = permit_raw.get("scenario_status") == "tentative"
        reliable = permit_raw.get("land_price_reliable")
        if tentative or reliable is False:
            reasons.append("선행절차/공시지가 신뢰성 전제 — 조건부")
            return "CONDITIONAL", "medium"
        if grade in ("A", "B") or (isinstance(roi, (int, float)) and roi >= 8):
            reasons.append(f"Top1 {top.get('type_name')} 등급 {grade}·ROI {roi}% — 추진 권고")
            return "GO", "high"
        if isinstance(roi, (int, float)) and roi >= 0:
            reasons.append(f"Top1 ROI {roi}% — 수익성 점검 필요(조건부)")
            return "CONDITIONAL", "medium"
        reasons.append("Top1 수익성 부진 — 재검토 권고")
        return "HOLD", "low"

    def _gate_from_raw(
        self, site_raw: dict[str, Any] | None, reg_raw: dict[str, Any] | None,
        permit_raw: dict[str, Any] | None,
    ) -> str:
        """특이부지/법규 게이트(BLOCK/TENTATIVE/PASS) — gate_decision SSOT 재사용.

        부지분석(site_raw.special_parcel)·★법규(reg_raw.special_parcel)·Top3(permit_raw)의
        세 신호를 모두 모아 가장 보수적인(가장 강한) 게이트를 반환한다(BLOCK>TENTATIVE>PASS).
        ★HIGH: 법규 계층이 BLOCK이면 부지/Top3가 멀쩡해도 가짜 GO가 나지 않도록 HOLD로 강등된다.
        """
        from app.services.zoning.special_parcel import gate_decision

        severity = {"PASS": 0, "TENTATIVE": 1, "BLOCK": 2}
        worst = "PASS"

        def _consider(g: str | None) -> None:
            nonlocal worst
            if g and severity.get(g, 0) > severity.get(worst, 0):
                worst = g

        # 부지분석 special_parcel(developability/resolvable).
        site_sp = (site_raw or {}).get("special_parcel") if site_raw and not site_raw.get("_unavailable") else None
        if site_sp:
            _consider(gate_decision(site_sp.get("developability"), site_sp.get("resolvable")))

        # ★법규 special_parcel(RegulationAnalysisService.analyze 가 is_special일 때만 부착).
        reg_sp = (reg_raw or {}).get("special_parcel") if reg_raw and not reg_raw.get("_unavailable") else None
        if reg_sp:
            _consider(gate_decision(reg_sp.get("developability"), reg_sp.get("resolvable")))

        # Top3 — 잠정 시나리오(선행절차 전제)면 TENTATIVE, special_parcel 있으면 gate 환산.
        if permit_raw and not permit_raw.get("_unavailable"):
            if permit_raw.get("scenario_status") == "tentative":
                _consider("TENTATIVE")
            permit_sp = permit_raw.get("special_parcel")
            if permit_sp:
                _consider(gate_decision(permit_sp.get("developability"), permit_sp.get("resolvable")))

        return worst

    # ------------------------------------------------------------------
    # 공통 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _unwrap(res: Any, part: str) -> dict[str, Any]:
        """gather 결과를 풀어 예외면 _unavailable 마커 dict로 변환(분류 로깅)."""
        if isinstance(res, _DomainSkipError):
            logger.info("의사결정 브리프 도메인 스킵", part=part, reason=str(res))
            return {"_unavailable": True, "reason": str(res), "error_type": "skip"}
        if isinstance(res, Exception):
            # 예외 분류 로깅(silent-fail 금지) — 타입·메시지 남김.
            logger.warning(
                "의사결정 브리프 도메인 실패",
                part=part,
                error_type=type(res).__name__,
                error=str(res)[:200],
            )
            return {
                "_unavailable": True,
                "reason": f"{type(res).__name__}: {str(res)[:160]}",
                "error_type": type(res).__name__,
            }
        if isinstance(res, dict):
            # 일부 엔진은 정상 반환 안에 error 키로 실패를 표현(예: 인허가 가능 모델 없음).
            if res.get("error"):
                return {"_unavailable": True, "reason": str(res.get("error")), "error_type": "domain_error"}
            return res
        # 예상치 못한 타입(silent-fail 금지) — 명시 사유로 강등.
        logger.warning("의사결정 브리프 도메인 비정상 반환", part=part, got=type(res).__name__)
        return {"_unavailable": True, "reason": f"비정상 반환 타입: {type(res).__name__}", "error_type": "bad_type"}

    @staticmethod
    def _unavailable_part(
        part: str, title: str, raw: dict[str, Any] | None, *, detail_route: str,
    ) -> dict[str, Any]:
        """표준 계약의 'unavailable' part — 정직 사유 동반(빈값 은폐 금지)."""
        reason = (raw or {}).get("reason") or "데이터 미확보(정직 고지)."
        return {
            "part": part,
            "title": title,
            "summary_oneliner": f"{title} 미확보 — {reason}",
            "key_metrics": [],
            "evidence": [],
            "legal_links": [],
            "confidence": "low",
            "detail_route": detail_route,
            "status": "unavailable",
            "reason": reason,
        }

    @staticmethod
    def _legal_ref_label(r: dict[str, Any]) -> str:
        """legal_ref 레코드 → 사람이 읽는 라벨(계약 정본 키 우선).

        ★정본 계약 = legal_reference_registry.get_legal_refs 레코드 = {key, law_name, article,
        title, url, url_status}. 따라서 'law_name + article'(예: '국토계획법 시행령 제85조')을
        우선 사용한다. 과거엔 존재하지 않는 label/law 키만 시도해 law_name 을 무시(라벨 드리프트)했다.
        하위호환: label/title/law 도 폴백으로 둔다(픽스처·타 출처 호환). 모두 없으면 '법령'.
        """
        law_name = (r.get("law_name") or "").strip()
        article = (r.get("article") or "").strip()
        if law_name:
            return f"{law_name} {article}".strip()
        return (r.get("label") or r.get("title") or r.get("law") or "법령")

    @classmethod
    def _legal_links(cls, legal_refs: Any) -> list[dict[str, Any]]:
        """comprehensive/registry legal_refs → 표준 legal_links(verified url만·죽은링크 금지)."""
        out: list[dict[str, Any]] = []
        for r in legal_refs or []:
            if not isinstance(r, dict):
                continue
            url = r.get("url") or r.get("legal_link")
            # url 없는 항목은 죽은링크 방지 위해 라벨만(가짜 url 금지). url None 보존.
            out.append({"label": cls._legal_ref_label(r), "url": url or None})
        return out

    @classmethod
    def _regulation_legal_links(cls, hierarchy: Any) -> list[dict[str, Any]]:
        """규제 계층(hierarchy) 각 level의 legal_refs를 평탄화해 표준 legal_links로."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for level in hierarchy or []:
            if not isinstance(level, dict):
                continue
            for r in level.get("legal_refs") or []:
                if not isinstance(r, dict):
                    continue
                url = r.get("url") or None
                label = cls._legal_ref_label(r)
                dedup = f"{label}|{url}"
                if dedup in seen:
                    continue
                seen.add(dedup)
                out.append({"label": label, "url": url})
        return out

    @staticmethod
    def _trio_str(trio: dict[str, Any]) -> str:
        """법정/조례/실효 3종을 한 문자열로(미확보는 '-')."""
        def s(v: Any) -> str:
            return str(v) if v not in (None, "") else "-"
        return f"{s(trio.get('legal'))}/{s(trio.get('ordinance'))}/{s(trio.get('effective'))}"

    @staticmethod
    def _confidence_from_developability(developability: str | None) -> str:
        """개발가능성 라벨 → confidence(high/medium/low)."""
        dev = (developability or "").strip().upper()
        if dev in ("", "POSSIBLE"):
            return "high"
        if dev in ("BLOCKED", "IMPOSSIBLE"):
            return "low"
        return "medium"  # CONDITIONAL/PRECONDITION/CAUTION 등

    @staticmethod
    def _billing(use_llm: bool) -> dict[str, Any]:
        """과금 — 관리자 설정(analysis_modules) 기준. 미설정 시 0원(무료·실행)."""
        fee = 0.0
        if use_llm:
            try:
                from app.core.billing import service_fee_analysis_module
                fee = service_fee_analysis_module("decision_brief")
            except Exception:  # noqa: BLE001 — 과금 조회 실패는 무료로(차단 금지)
                fee = 0.0
        return {
            "use_llm": use_llm,
            "billing_key": "decision_brief",
            "estimated_fee_krw": fee,
            "note": (
                "use_llm=False면 무과금. 과금은 관리자가 analysis_modules에 "
                "'decision_brief' 키를 설정한 경우만(미설정=무료)."
            ),
        }

    @staticmethod
    def _empty_brief(*, address: str | None, project_id: str | None, reason: str) -> dict[str, Any]:
        """입력 부재 등 사전 차단 — 표준 빈 브리프(정직 사유)."""
        return {
            "address": address,
            "project_id": project_id,
            "parcel_count": 0,
            "parts": [],
            "verdict": {
                "decision": "HOLD",
                "confidence": "low",
                "reasons": [reason],
                "blockers": [reason],
                "go_nogo": None,
                "gate": "PASS",
            },
            "billing": DecisionBriefService._billing(False),
            "meta": {
                "use_llm": False,
                # build() 본 경로와 동일하게 settings.DEPLOY_PENDING 게이팅(하드코딩 제거).
                "deploy_pending": DecisionBriefService._deploy_pending(),
                "reason": reason,
            },
        }


class _DomainSkipError(Exception):
    """도메인 입력 미충족(예: 주소 없음) — 실패가 아닌 '정상 스킵'으로 분류 로깅."""
