# /ko/regulations 워크플로우·정합·실효FAR 수정 실행계획 (2026-07-16)

- **작성**: 통합자 세션. 감사 기준 **origin/main d60db9ca**(읽기전용). 라이브 실측 보강(168 키 상태).
- **트리거**: 사용자 라이브 지적(용인 신봉동 56-16 외 11필지, 자연녹지) — 자연녹지 실효용적률 100% 오표기·다필지 배선 미흡·법규링크 미흡·필지구획도 불일치·전문가패널 미구동.
- **핵심 공통 진단**: 5개 증상 전부 **SSOT는 이미 존재하는데 /regulations만 소비 안 하는 "미배선"** 패턴(그린필드 아님). 정답 기준선(다른 화면)이 이미 있어 난이도 낮음.
- **대상 파일**:
  - 백엔드: `apps/api/app/services/regulation/regulation_analysis_service.py`(중심)
  - 프론트: `apps/web/components/operations/RegulationsWorkspaceClient.tsx`·`components/regulation/RegulationHierarchyView.tsx`
  - 전문가패널: `apps/api/app/services/expert_panel_service.py`·`components/.../ExpertPanelCard.tsx`

---

## WP-R1 (CRITICAL): 자연녹지 실효 FAR 100%→80% — SSOT 소비 봉합
**근본원인(단일 지점·확정)**: `far_tier_service.calc_effective_far`가 이미 구조상한 80%(건폐 20%×4층)를 계산해 `result["effective_far"]`(land_info_service.py:651)에 저장하는데, `regulation_analysis_service`가 이를 **소비하지 않고** `zone_limits.max_far_pct`(법정 100%)를 "실효"로 라벨(regulation_analysis_service.py:248-254,264). `zone_limits`엔 `effective_far_pct` 키 자체가 없어 법정으로 폴백. AI "실효 100%" 단언(:475-476)도 이 값의 하류 복창. **설계 스튜디오는 SSOT를 쓰므로 80% — 데이터원 발산.**

**수정(재계산 금지·소비만)**:
1. `regulation_analysis_service.analyze`에서 `eff = comp.get("effective_far")` 읽어 `limits["far"]["effective"] = eff["effective_far_pct"]`(80), `limits["bcr"]["effective"] = eff["effective_bcr_pct"]`로 세팅. trio의 `effective` 슬롯은 이 SSOT값 최우선(zone_limits 법정 폴백 제거).
2. 백엔드 결과 dict(:156)·TS `RegResult`(RegulationHierarchyView.tsx:64-86)에 `effective_far`(structural_cap_pct·floor_cap·floor_cap_basis) 통과키 추가.
3. evidence 트레이스에 "구조상한(건폐 20%×4층=80%)" 1건 추가(근거패널에 80% 실체 노출).
4. LLM 프롬프트 `far` 포맷을 `100/100/80` + `far_basis="구조상한(건폐율×층수)"` 주입 → AI가 "실효 80%(4층 제한 바인딩)" 서술.
5. 다필지 통합: integrated의 blended `effective_far_pct`(각 필지 calc_effective_far 경유·이미 클램프) 우선.
- **★전역 스윕(버그정책)**: `far.effective`가 zone_limits 법정값으로 폴백하는 패턴을 전수 grep — comprehensive/land_report/기타 소비처가 같은 발산을 하는지 확인, 공용 계약(far.effective는 항상 far_tier_service SSOT 단일경유)으로 봉합.
- **게이트**: 자연녹지 부지 규제분석 → 용적률 한도 "실효 80%"(법정 100% 소행)·evidence에 구조상한 트레이스·AI 해석 "실효 80%". 설계 스튜디오와 동일 80%.

## WP-R2 (HIGH): 법규 링크 미배선 봉합
**근본원인**: 인프라(legal_reference_registry·verified·per-district 매핑 `legal_refs_for_districts`)는 견고하고 **다른 화면에선 작동**(land_info_service:487·comprehensive:1575). /regulations만 미소비.

**수정(기존 SSOT 호출만)**:
1. 상위법령 attach(`_level_ref_keys`:349-352)에 `bcr_law`(국토계획법 §77)·`far_law`(§78) 추가 — 레지스트리에 키 존재(L215-216), 클릭 칩 부착.
2. 개별 규제·지구·구역 레벨4에서 `legal_refs_for_districts(districts, sigungu)` 호출(현재 `[]` 반환) — 상대보호구역(즉시 매핑됨)·비행안전구역·토지거래허가는 `_DISTRICT_LAW_KEYWORDS`에 키워드 추가(비행안전/공항→군사기지법, 토지거래→realtx_report 키).
3. 자연녹지 4층 근거: 새 레지스트리 키(**국토계획법 시행령 별표17 "4층 이하"** — legal_zone_limits.py:54 FLOOR_CAP_BASIS 기준. ★"건축법 별표"가 아니라 국토계획법 시행령 별표가 정답) + 높이 카드(RegulationHierarchyView.tsx:205-207)에 LegalRefChip 부착.
4. 칩에 `url_status`(verified/pending) 시각 배지(미검증 인용 책임 리스크 표기).
- **게이트**: 상위법령 §77/§78 클릭링크·개별 10건 전부 법령칩·높이 4층 근거칩·verified 배지.

## WP-R3 (HIGH): 필지 구획도 ↔ 사통맵 정합
**근본원인(1줄)**: `RegulationsWorkspaceClient.tsx:177` `<ParcelBoundaryMap parcels={[result.address]} />` — 대표주소 1개만 전달. 다필지 목록이 구획도에 미전파(분석/요약/시니어/계층은 통합 12,079㎡로 정상). `effRows`(run 지역변수)를 스냅샷 미보존.

**수정(정답 기준선 MarketInsights:690·multi-parcel:272 패턴)**:
1. run() 시점 필지 스냅샷 상태 보존(`runParcelAddrs` 패턴) → `parcels={runParcelAddrs.length>0 ? runParcelAddrs : [result.address]} primaryZone={result.zone_type}`.
2. (parity 계약·아이디어1) `/regulation/analyze` 응답에 해결된 필지목록 echo `result.parcels_used`(addresses+PNUs) 추가 → 구획도·패널·향후 PDF가 단일 권위목록 소비(클라 재파생 드리프트 제거).
3. 비인접 다필지 경고(아이디어7): adjacency 미확인 시 "통합 면적/FAR은 합필 가정 — 비인접 필지는 개별 적용" 정직 병기.
- **게이트**: 12필지 분석 → 구획도 헤더 "12필지·12,079㎡", primaryZone 오버레이 적용.

## WP-R4 (MEDIUM): 전문가 검토 패널 구동
**근본원인(라이브 실측으로 정정)**: 공유 LLM 다운 아님(168 ANTHROPIC_API_KEY SET·같은 요청서 AI 규제해석은 정상 생성). **패널 고유** — `_single`(expert_panel_service.py:271-285) `get_llm(max_tokens=3500)`가 4전문가 JSON을 절단 → `json.loads` 실패 → `except`가 **침묵 폴백**(:283-285, "일시적으로 제공되지 않습니다").

**수정**:
1. max_tokens 상향(패널 4전문가 응답 실측 크기 기준, 예 6000~8000) + JSON 복원(truncated repair) 또는 스트리밍.
2. **침묵 폴백 제거**: `except`가 실패 사유(truncation/timeout/validation/provider)를 로깅·구분해 프론트에 degraded 사유 전달(무목업·정직). ExpertPanelCard가 "LLM 미연결" vs "저신뢰" vs 402(쿼터)를 구분 표기(아이디어3).
3. 프롬프트가 과대 JSON을 요구하지 않게 스키마 슬림화(전문가별 핵심 필드만).
- **게이트**: 라이브 규제 패널 실행 → 4전문가 실의견 생성(generated:true), 실패 시 사유 명시(침묵 금지).

## WP-R5(백로그·아이디어): 시니어 규제검토 고도화
혼재 용도지역 BCR/FAR/높이 매트릭스+필지귀속(아이디어2)·지구단위 실지침 연동(GosiSearch·토지이음, 아이디어5)·접도/맹지 규제단계 판정(아이디어6)·인접성 게이트로 통합FAR 제한(아이디어7)·캐시 staleness 토큰(아이디어9).

---

## 실행 순서·게이트
- WP-R1(실효FAR)+R2(링크)+R3(구획도)는 regulation 서비스/페이지 공유 파일 → **한 브랜치·한 PR**(자초충돌 방지). R4(패널)는 독립 파일이라 병행 가능하나 같은 PR로 묶어도 무방.
- 성장루프: 구현→적대리뷰(★R1 수치 정확성·전역 스윕·R4 침묵폴백 제거 검증)→REVISE→R2→CI→머지→sw bump 배포→라이브검증(자연녹지 80%·구획도 12필지·패널 생성).
- 무목업·정직: 실효 미산정은 미산정 표기, 링크 없으면 텍스트 폴백(날조 금지). 라이브 육안(자연녹지 부지) 필수.
- 완성도 기준선: 배선 ~85% → 목표 100%(실효FAR 정확·링크 완비·구획도 parity·패널 생성).
