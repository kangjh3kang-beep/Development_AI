# 새 세션 인계 문서 (2026-06-12, KB심화 + 업로드 상호연동 웨이브)

> **✅ 2026-06-12 갱신: 본 웨이브는 완료·검증·커밋됨 (`2d1139b`).** §2 체크리스트 6개 WP 전부 구현 완료,
> 중앙 검증 그린(pytest 3185 passed/0 failed, tsc·vitest 40·pnpm build). 새 세션은 §4 이후 로드맵부터 진행하라.
> 주의: `tests/test_auction_demock_court.py`·`tests/test_molit_client.py` 2건은 **다른 세션의 커밋**(ed2c5bd·bb17dc7)이
> 모듈 심볼을 변경해 수집 단계부터 깨져 있음(본 웨이브 무관) — molit/tilko/경매 영역은 그 세션 소관이므로 조율 후 수정.
> `unit/` 디렉터리는 pytest 표준 경로(testpaths) 밖의 레거시 — 18건 실패도 본 웨이브 무관.

## 0. 불변 규칙 (위반 금지)

1. **브랜치**: `feature/trust-infra-2026-06-11` 에서 작업, **main 직접 푸시 금지**. 푸시는 작업 브랜치만(remote: `git@github.com:kangjh3kang-beep/Development_AI.git`). main 머지·Oracle 배포는 다른 Claude 담당.
2. **additive·하위호환**: 기존 응답 키·store·테스트 계약 제거/변경 금지. 새 필드는 옵셔널 가산.
3. **정직 표기**: 가짜값·날조 한글 실명·할루시네이션 법령링크 금지. 법령 URL은 `legal_reference_registry` 출력만. 미라벨 추정은 `inferred=True`+confidence.
4. **출처 등급 분리**: 법령(`_legal`) ≠ 표준(`_std`) ≠ 실무(`_practice`) ≠ 논문(`_paper`, source='논문' 태그 강제). 논문 휴리스틱을 법령처럼 표기 금지.
5. **arch_grammar.py**: KB 보강(KB1) 외에는 읽기전용(import만).
6. 검증은 WSL: `wsl.exe -d Ubuntu -- bash -c 'cd ~/My_Projects/Development_AI/propai-platform && ...'` (API venv: `apps/api/.venv`, 프론트: pnpm).

## 1. 직전 세션 상태 스냅샷

- 브랜치 HEAD(당시): `24a3363` (이 세션 커밋 13건 포함, 전부 그린 베이스라인 3022 passed/0 failed).
- 완성 문서: `docs/ARCH_KNOWLEDGE_DEEPENING_2026-06-12.md`(건축지식 심화 — KB 보강항목표·스키마확장안), `docs/UPLOAD_SYNERGY_DESIGN_2026-06-12.md`(업로드 상호연동 설계 WI-1~10 — **이 문서가 구현 사양서**).
- **확정 라이브 버그 2건** (UPLOAD_SYNERGY_DESIGN §0):
  - ①`cad-shapes.ts` dxfImportToShapes가 `result.polylines`를 읽는데 백엔드는 `result.shapes` 반환 → DXF 가져오기 항상 빈 결과.
  - ②라우터 `design_audit.py:297`이 `orchestrator.run()` 호출하나 클래스엔 `audit()`만 존재 → 설계심사 라이브 503(테스트 fake로만 통과).
- 직전 세션은 6병렬 구현 워크플로우(KB1·UP1~UP5)를 가동 중이었고 일부만 디스크 반영된 채 종료됐을 수 있다.

## 2. 구현 체크리스트 (디스크 대조 후 미완만 수행)

| WP | 내용 | 사양 출처 | 완료 판정 기준 |
|---|---|---|---|
| KB1 | arch_grammar.py 지식 심화: `_std/_practice/_paper` 헬퍼 + ADJACENCY_WEIGHTS·CLEARANCES·STRUCTURE_SPANS·SECTION_RULES·PARKING_MODULE·ADJACENCY_DETECT 상수(데이터 전용) + ROOM_TYPES.furniture_clearance_ref | ARCH_KNOWLEDGE_DEEPENING ②·③ | arch_grammar.py에 상수 존재 + test_arch_grammar.py 신규 케이스(상수 무결성·frozenset 대칭·논문 태그) 통과 + 기존 케이스 무파손 |
| UP1 | `services/cad/shapes_to_rooms.py`: extract_rooms(닫힌폴리곤·라벨귀속·미라벨 정직추정·bbox 사각화+원본 보존) | UPLOAD_SYNERGY WI-1 | 파일 존재 + **tests/test_shapes_to_rooms.py 존재·통과** (직전 세션엔 테스트 미생성 상태였음) |
| UP2 | `services/cad/cad_upload_hub.py`: distribute() 4소비형 분배 + boundaries_from_bbox_rooms는 UP1에 | WI-2·WI-3 | 파일 존재 + **tests/test_cad_upload_hub.py 존재·통과** |
| UP3 | `design_audit_orchestrator.py`: **run() 어댑터 신설(버그② 수정)** + audit(rooms=) grammar 9번째 섹션 | WI-4·WI-5 | `grep "async def run" design_audit_orchestrator.py`에 클래스 메서드 존재(모듈수준 run_design_audit 말고) + verdict 영문 별칭 + test_design_audit_core.py 케이스 |
| UP4 | `routers/design_audit.py`: run-upload에 dxf_file 수용 → hub.distribute 배선, RunRequest.rooms, _build_report_sections grammar 핑거 | WI-6·WI-7 | dxf_file 파라미터 존재 + test_design_audit_api.py dxf e2e |
| UP5 | 프론트: **cad-shapes.ts 키버그① 수정**(shapes 1차·polylines 폴백) + cad-shapes.test.ts + DesignAuditWorkspace DXF 슬롯 활성화(disabled 해제·FormData dxf_file) | WI-10·WI-8 | dxfImportToShapes가 result.shapes 수용 + DXF 슬롯 활성 + vitest 통과 |

직전 세션 종료 시점 디스크 반영 상황(참고 — 재확인 필수):
- 반영됨: arch_grammar.py+test(M), cad-shapes.ts+test(M), shapes_to_rooms.py(신규), cad_upload_hub.py(신규)
- 미반영: test_shapes_to_rooms.py, test_cad_upload_hub.py, orchestrator run()/grammar, 라우터 dxf_file, CADEditor, DesignAuditWorkspace
- 주의: 반영된 파일도 **품질 검증 전**이다. 사양 대비 재검토 후 수용/보완.

## 3. 중앙 검증 절차 (전 WP 완료 후)

```bash
# 1) 컴파일
python -m py_compile apps/api/app/services/cad/{arch_grammar,shapes_to_rooms,cad_upload_hub}.py \
  apps/api/app/services/design_audit/design_audit_orchestrator.py apps/api/app/routers/design_audit.py
# 2) 신규·관련 테스트
cd apps/api && .venv/bin/python -m pytest tests/test_arch_grammar.py tests/test_shapes_to_rooms.py \
  tests/test_cad_upload_hub.py tests/test_design_audit_core.py tests/test_design_audit_api.py \
  tests/test_unit_plan_generator.py tests/test_dxf_import.py -q
# 3) 전체 회귀 (기준: 3022 passed / 0 failed에서 증가만 허용)
.venv/bin/python -m pytest -q
# 4) 프론트
cd ../../apps/web && pnpm tsc --noEmit && pnpm vitest run lib/cad-shapes.test.ts && pnpm build
```

전부 그린이면 커밋(작업 브랜치): 메시지 예 `feat(cad/audit): KB 심화 + 업로드 상호연동(역추출·허브·run()/import-dxf 버그수정)` → `git push origin feature/trust-infra-2026-06-11`.

## 4. 이후 로드맵 (이번 웨이브 다음)

1. **WI-9**: 템플릿 등록 shapes 경유 정합(dxf_to_geometry 폴백 보존).
2. KB 활용 검증룰: ADJACENCY_WEIGHTS·CLEARANCES를 unit_plan_generator/심사 grammar 섹션의 실제 검사로 승격(현재는 데이터만).
3. ARCH_KNOWLEDGE_DEEPENING P1·P2: SECTION_RULES 단면 검증, STRUCTURE_SPANS 경간 검사, PARKING_MODULE 주차 정합.
4. 잔존(보류): IFC opening 전파, 룰테이블 기하결함 보정, R3-2 ML floorplan, web-ifc 뷰어.

## 5. 맥락 요약 (왜 이 작업인가)

사용자 의도: "CAD 도면을 업로드하면 상호연동 → 시너지". 업로드 1회가 ①편집 ②템플릿엔 흐르나 ③설계심사 ④건축문법검증으로는 안 흐르던 것을 연동 허브+shapes→rooms 역추출기로 완성. 동시에 건축지식 KB(인접·클리어런스·구조·단면·주차)를 출처등급 분리 원칙으로 심화 — 역추출된 rooms를 보강 KB로 검증하는 것이 "도면 올리면 즉시 공학·법규 종합검증" 시너지의 완성형.
