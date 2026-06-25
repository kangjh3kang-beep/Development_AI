# 시니어 법무사 spec + 정비사업 종전평가 배선 — 구현계획 (2026-06-25)

## 상세조사 결론 (수집·분석)
1. **종전평가 감정 = 이미 존재** (또 배선): `desk_appraisal_service`가 감정평가규칙 매핑 —
   공시지가기준법(토지·제14조)+거래사례+**원가법 건물(_building_value: 재조달원가×연면적×잔가율,
   하한 20%·경과/내용연수)**. 토지+건물 복합 감정 산출. → 정비사업 종전평가 = desk_appraisal 배선.
2. **법령 실재**: legal_reference_registry에 부동산등기법(_REG)·도시정비법(제35조 등)·소규모정비. 법무사 bases 확보.

## 트랙 A — 시니어 법무사 spec (8번째 에이전트·신규·proven 패턴)
정비사업/개발의 등기·권리분석·조합·신탁 법무. DecisionRule(verified 법조문):
- legal.rights_analysis: 말소기준권리(최선순위 (근)저당·압류·가압류·담보가등기·경매개시) 기준 인수/소멸·대항력 임차인 인수. basis 민사집행법·부동산등기법.
- legal.union_consent: 조합설립 동의율 — 재개발 토지등소유자 3/4+면적 1/2 / 재건축 구분소유자 3/4+동별 과반+면적 3/4. basis 도시정비법 제35조.
- legal.title_registration: 소유권이전등기 선행요건(취득세·실거래신고·검인)·신탁등기. basis 부동산등기법·부동산거래신고법.
- legal.development_trust: 차입형/관리형/담보신탁 — 도산절연·자금조달·시행권 트레이드오프. basis 신탁법·자본시장법.
failure_modes: 말소기준 오판(대항력 누락)·동의율 산정오류(토지등소유자 중복)·신탁 도산절연 과신·예고등기/가처분 간과.
+ **법무사 evaluator(정량)**: legal.union_consent — 동의(수/면적) ≥ 법정요건 CSP(재개발/재건축 모드).

## 트랙 B — 정비사업 종전평가 → urban 비례율 배선 (desk_appraisal 재사용)
- 백엔드: 종전평가 = desk_appraisal(토지+건물 복합) 합. 종후 = feasibility 매출, 총사업비 = feasibility cost.
- urban evaluator는 이미 비례율 산식 보유 → build-inputs에 prior_appraisal_total(desk)·post_appraisal_total(매출)·total_project_cost(cost) 매핑.
- 정직: desk_appraisal은 탁상 추정(정식 감정 아님)·잠정 표기. 건물 미보유 필지는 토지만(정직 고지).

## 순차 구현 (성장루프·검증→빌드→푸시)
1. **트랙 A 법무사 spec + evaluator** (registry 8 agents·specs/legal_scrivener.py·evaluators/legal.py). 단위테스트·리뷰.
2. **트랙 B 종전평가 배선** (desk_appraisal→비례율 inputs·store·build-inputs). end-to-end 라이브.
각 증분: ruff0·pytest·type-check·next build·코드리뷰 ACCEPT·무회귀.

## 정직성
- 종전평가=탁상 추정(감정평가사 의뢰 필요)·잠정·±민감도. 동의율은 입력 의존(미확보 생략).
- 법무사 면허게이트: 최종 등기·권리분석 책임은 법무사·변호사.
