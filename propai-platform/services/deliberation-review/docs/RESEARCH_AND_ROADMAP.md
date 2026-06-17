# 심의분석 엔진 — 연구 조사 · 경쟁 분석 · 구현/리팩토링 로드맵

작성 2026-06-16. 실제 웹조사(출처 하단) 기반. propai-review(심의분석 엔진, 11계층, /analyze 실구동)의
**차세대 확장 + 병목해결 + 혁신 구현계획**. 추측 아님 — 조사 결과에 근거.

## 1. 경쟁 플랫폼 지형 (실조사)

| 플랫폼 | 성격 | 비고 |
|--------|------|------|
| Archidian | 전체 PDF 도면셋 분석 → cross-sheet 조정·코드위반 사전 검출 | 우리 R0.5 cross-sheet(WB18)와 동일 문제의식 |
| CivCheck | Guided AI Plan Review(신청자+심사자 교육형) | 심사자 워크플로 |
| Articulate AI (YC) | 도면이 IBC/IRC/ADA/소방/에너지 코드 충족 검증 | 코드 커버리지 광범 |
| PlanCheckPro / CodeComply / Archistar | AI 사전검토·재제출 감축 | 미국 시장 |
| **규제 동향** | 미 Florida HB 683(2025): 민간 자동 plan review 법적 허용 | 자동심사 제도화 신호 |

**관찰**: 대부분 **미국 코드(IBC/IRC/ADA) PDF plan review**에 집중. **한국 심의(deliberation)·인허가 + 정성 심의기준** 영역은 상대적 공백(=우리의 "빈 프런티어"). 우리 차별점 = **결정론 코어 + 근거추적(calc_trace/method_trace/인용) + 무음 오판 0 + 3값 판정(완화/특례 CONDITIONAL) + 정성 인용접지**.

## 2. 멀티모달/기술 연구 (실조사)

- **AECV-Bench**(arXiv 2601.04819): 건축·엔지니어링 도면 이해 멀티모달 벤치마크. **off-the-shelf MLLM은 기술도면에서 성능 급락** → 도메인 특화 필요.
- **ArchGPT**(arXiv 2509.20858), **CadVLM**(Autodesk), **CADialogue**(ScienceDirect): 건축/CAD용 멀티모달 LLM.
- **AWS CV+LLM**: 컴퓨터비전 + LLM 결합이 인간 리뷰를 증강(대체 아님).
- **핵심 시사점**: VLLM 단독으로 법규 판정을 시키면 안 됨 → **VLLM은 비수치 추출(시트/요소)만, 법정 산정·판정은 결정론**. ★우리 설계(R0.5 추출 → R1.5/R3 결정론)가 정확히 이 방향. 단, **실 VLLM 추출층이 현재 mock**(최대 갭).

## 3. 국내 동향 (실조사)

- **국토부 'AI 기반 건축설계 자동화' R&D(2021–2025)**: 매스생성기·스페이스메이커·**룰체커**·에이전트시뮬레이터. **인허가 단계 90% 자동화** 목표.
- **BIM 기반 법규 자동평가 + LLM(ChatGPT) 챗봇**: 개정법규 안내 + 검토항목 논리규칙 해석.
- **현실적 접근**: "AI로 모든 법규검토 대체보다 **최소 BIM 기반 점진 확대**". → 우리도 graceful degrade(skip 표면화)와 정합.

## 4. 학술 표준 — BIM/IFC 자동 적합성 검토 (실조사)

표준 4단계: **rule interpretation → model preparation → rule execution → rule reporting**. 우리 11계층 매핑:
- rule interpretation = R2(미러 룰셋)·R3(룰 DAG)
- model preparation = R0.5(시트/요소)·R1.5(법정 산정)
- rule execution = R3(판정)·L3-B(시뮬)·L5(검증)
- rule reporting = L6(구획 리포트)

기법: Semantic Web(SPARQL/RDF), **Knowledge Graph + NLP**, RASE 방법론. → 우리 R3 rule DAG를 **규제 지식그래프**로 확장 여지.

## 5. 구현/리팩토링 로드맵 (근거 기반, 우선순위)

### P0 — 실 VLLM 추출층(최대 갭, "멀티모달 자동해석"의 핵심)
- 현재 R0.5 sheet/element가 **mock 어댑터**. 실 VLLM(예: Claude/Qwen-VL) + CV(YOLO 도면검출)로 교체하되 **기존 3원 합의(INV-8)·confidence 게이팅(INV-9) 계약 불변**으로 끼워넣기(adapters/vision 인터페이스 이미 존재 → 교체만).
- 근거: AECV-Bench(도메인 특화 필요) → 구조화 프롬프트 + 합의 + 보류로 환각 흡수.

### P1 — BIM/IFC 인제스트(국내 R&D 정합 + 추출부담 감소)
- IFC 파서 어댑터 추가 → 기하/요소를 구조화 입력으로(2D 도면 한계 보완). **BIM 있으면 IFC, 없으면 VLLM** 이중경로(혁신).
- 근거: 국토부 BIM 기반 방향 + 학술 IFC 표준.

### P2 — 병목 해결(이전 실측 병목 4건)
- ① 분석결과 **DB 영속화**(L6 모델 존재 → repository 배선) ② **Celery 비동기**(대량 배치, deps 보유) ③ `/analyze` **인증/테넌트**(propai-platform RBAC 패턴 이식) ④ 실 데이터 어댑터(관할 토지이음/VWORLD, 법규 ELIS) 교체.

### P3 — 규제 지식그래프(학술 KG 정합)
- R2 미러 + R3 DAG를 **규제 KG**(조문↔변수↔룰↔완화)로 통합. pgvector + 그래프 질의. 인용접지(L5)와 결합.

### P4 — 평가 하네스(AECV-Bench 스타일)
- 추출층 정확도 + 판정 정합 골든셋. 기존 11계층 AT(124 passed)에 **추출 eval** 추가.

## 6. 혁신 추가 구현방안

1. **이중경로 입력**(BIM↔VLLM) + 교차검증(이미 L5 dual_path_check 보유 → 확장).
2. **3값 판정 + 완화 DAG**(R3): 미 plan-review 경쟁사 대비 차별 — 한국 심의의 "조건부의결·재심의" 현실 반영.
3. **정성 심의 인용접지(L3-C)** + temp0/모델핀 재현성: 경관·배치 등 정성 항목을 공표 루브릭에 접지(경쟁사 미흡 영역).
4. **자기수렴 감사 루프**(거짓 불합격 0·무음 통과 0)를 런타임 게이트로 상시화.

## 7. 다음 실행 단위(검증 가능 단위로 분해)
- [ ] P0-a: adapters/vision에 실 VLLM 어댑터 1종(시트역할) 끼우고 mock과 동일 계약·AT 그린 유지.
- [ ] P2-a: analysis 결과 DB 저장 + `GET /api/v1/analyze/{id}` 조회(L6 모델 활용).
- [ ] P2-c: `/analyze` 인증 가드(platform RBAC 이식).
- 각 단위 = 계약→구현→AT→실호출 검증(기존 하네스 패턴).

---

## 출처 (실조사 2026-06-16)
- 경쟁 플랫폼: [Archidian](https://archidian.ai/), [CivCheck](https://www.civcheck.ai/), [Articulate AI](https://usearticulate.com/for/plan-reviewers/code-compliance), [PlanCheckPro](https://plancheckpro.ai/), [CodeComply](https://codecomply.ai/), [Archistar](https://www.archistar.ai/aiprecheck/ai-plan-review/)
- 멀티모달 연구: [AECV-Bench](https://arxiv.org/pdf/2601.04819), [ArchGPT](https://arxiv.org/pdf/2509.20858), [CadVLM](https://www.research.autodesk.com/publications/cad-vlm/), [AWS CV+LLM](https://aws.amazon.com/blogs/physical-ai/ai-powered-construction-document-analysis-by-leveraging-computer-vision-and-large-language-models/)
- 국내: [국토부 AI 건축설계 R&D(건축사신문)](https://www.ancnews.kr/news/articleView.html?idxno=18725), [BIM 법규 자동평가(buildingSMART)](https://www.buildingsmart.or.kr/thebim/pdf/The_BIM_22/), [경희대 ITlab](http://italab.khu.ac.kr/)
- 학술 BIM/IFC: [BIM 자동 적합성검토 리뷰(IEEE)](https://ieeexplore.ieee.org/document/8002486/), [지식그래프 기반(Nature Sci Reports)](https://www.nature.com/articles/s41598-023-34342-1), [Semantic Web+IFC(MDPI)](https://www.mdpi.com/2075-5309/15/15/2633), [투명성 프레임워크(ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0926580525006387)
