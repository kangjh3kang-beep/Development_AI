# 토지필지 후속과제 — 상세 구현계획 (2026-08-16)

P0~P2 머지·배포 후 남은 것. **`/insight-loop` 3렌즈(범위·재사용·성장루프)로 자기 전제를 먼저
반증**했고, 그 결과 **원래 후속목록의 우선순위가 뒤집혔다.**

---

## 0. ★반증된 전제 3가지 (이걸 모르고 착수하면 틀린 걸 만든다)

### 0-1. "후속과제 = 변이 생존 24건 + 시행자유형 입력필드" → **둘 다 1순위가 아니다**

실측 결과 **프로덕션에서 지금 사용자에게 틀린 것을 보여주는 결함**이 따로 있었다(§1).
내가 만든 부채보다 그게 먼저다.

### 0-2. "동의현황 입력이 플랫폼에 없다" → **틀렸다. 있는데 안 쓴다**

`parcel_excel_service` 가 토지조서 엑셀에서 동의 3종을 **이미 파싱**한다:
`consent_land`(토지사용) · `consent_district`(지구단위) · `consent_operator`(시행자지정), O/X.

- 헤더 매핑 `parcel_excel_service.py:114-116` · 파싱 `:751-753` · 응답 적재 `:785-787`
- **소비처 0** — 라우터가 DB 에 쓰지 않고(`auto_zoning.py:2263` 은 그대로 반환만),
  프론트 응답 타입(`GlobalAddressSearch.tsx:1036`, `SatongMapShell.tsx:251-256`)에
  consent 키가 **선언돼 있지 않아 타입 경계에서 파괴**된다.
- ★**이건 dead code 보다 나쁘다.** 사용자가 받는 양식 안내 시트(`:518-519`)가
  *"→ 정비·도시개발사업의 동의율 산정과 시행자 지정요건 판정에 **활용됩니다**"* 라고 적는다.
  **제품이 사용자에게 한 약속이 거짓**이다(무목업·정직표기 위반).

### 0-3. "시행자유형 필드를 P2 에 추가하면 된다" → **P2 자체가 화면 소비처 0이다**

`grep -rn "survey/strategy" apps/web` → **0건**. P1 의 소비처 0 을 P2 로 봉합했는데
**P2 자신이 UI 소비처 0** 이 됐다 — 봉합이 한 층 위로 이동했을 뿐이다.
입력 필드를 먼저 더하면 **검증할 표면이 없어 배선 락이 또 공허해진다.**

---

## 1. ★★P0 — 프로덕션 오표시: `_magdo()` 와 `scheme_legal_profile()` 이 갈라져 있다

**지금 배포된 화면이 법적으로 틀린 안내를 한다.** 실행 확증:

| 사업방식 | 화면 경로 `_magdo()` | 실제 `scheme_legal_profile()` |
|---|---|---|
| 도시개발사업 | "매도청구 가능 잔여 **33%**" | `instrument=`**수용**(토지보상법 준용) |
| 가로주택정비사업 | "매도청구 가능 잔여 **20%**" | `requires_track_input=True` → **판정보류** |

`_magdo()`(`scenario_simulator.py:153-166`)는 `instrument`·`requires_track_input` 을
**반환조차 하지 않는다**. 이 값이 `_magdo_summary`(`:782-813`) → `/development-methods/scenarios`
→ `DevelopmentScenarioCard.tsx:304-321` 로 흘러 **3개 화면에 배포 중**이다
(`projects/[id]/canvas`, `site-analysis`, `PreCheckWorkspace`).

**왜 심각한가**: 수용과 매도청구는 절차(협의→재결→보상 vs 3개월협의→소)도, 보상 기준
(공시지가·개발이익 배제 vs **시가**)도 다르다. 사용자가 잘못된 트랙을 준비한다.

### 처방 — 일원화(둘 중 하나에만 필드를 더하면 안 된다)

1. `_magdo()` 를 **삭제**하고 `scheme_legal_profile()` + `claimable_remainder_pct` 파생으로 통합.
2. `_magdo_summary` 가 `instrument` 를 보고, **수용이면 "매도청구" 문구를 내지 않는다.**
3. `requires_track_input` 이면 잔여비율을 **단정하지 않고** 판정보류를 낸다(P2 와 같은 계약).
4. `DevelopmentScenarioCard` 가 `instrument` 를 렌더한다.

**락**: 한 픽스처 × 두 사업방식(도시개발 vs 주택법 계열)이 **다른 문구**를 내야 한다.
차가 0이면 잠금이 아니다.

---

## 2. ★P0 — 성장루프가 도메인 필드를 **한 개도** 적재하지 않는다 (내 버그)

실행 확증:
```
내 이벤트   parcel_purchase_strategy → {'event_type': 'parcel_purchase_strategy'}
정답 기준선 design_proposal          → {'event_type':…,'service':…,'payload':{전부 보존}}
```

`capture_service._EVENT_COLS` 화이트리스트가 **평면 키를 버린다**(`capture_service.py:50, 136`).
내 두 emitter(`registry.py:752-760`, `:886-898`)는 도메인 값을 평면 키로 넘긴다 → **전량 폐기**.

★**정답이 같은 저장소에 주석까지 달려 있다** — `design_ingest/orchestrator.py:877`:
`# 도메인 메타는 payload 아래로(capture 화이트리스트 규약 — 평면 키는 폐기됨).`
**형제·미러 스윕(CLAUDE.md 규율 6)을 어긴 재발**이다.

★그리고 이걸 잠근다던 테스트가 **`record_event` 자체를 스텁**한다
(`test_parcel_purchase_strategy.py:1111-1121`) → 단언 6줄이 **전부 공허한 참**.
P0 쪽은 성장루프 테스트가 **아예 0건**.

### 처방
1. 두 emitter 를 `{"service":…, "tenant_id":…, "payload": {…}}` 로 감싼다(로직 0줄, 배선만).
2. **테스트를 `capture_service._drain()` 으로 교체** — 실제 적재된 row 를 단언.
   1번이 없으면 빨갛게 떠야 한다.
3. P0 emitter 에도 같은 테스트를 신설.

---

## 3. P1 — `consent_pct` 는 **행마다 기준이 다르다**. 단일 임계로 쓰면 틀린다

`MAGDO_RULES` 실측:

| scheme | `consent_pct` | 그 숫자의 실제 기준 | 소실되는 두 번째 임계 |
|---|---|---|---|
| 재개발·재건축 | 75 | 소유자 수 | 면적 1/2 |
| 가로주택 | 80 | 소유자 수 | 면적 2/3 |
| 모아주택 | 75 | 소유자 수 | 면적 3/4·동별 과반 |
| **도시개발** | 67 | ★**면적** (기준이 뒤집힌다) | 소유자 총수 1/2 |
| 주택법 계열 3종 | 95 | ★**사용권원(면적)** | — |

**이미 프로덕션에서 발현 중**: `_magdo_summary:782-813` 이
`need = ceil(parcel_count × thr / 100)` — **면적 임계를 필지 개수에 곱한다.**
같은 95% 를 P2 `secured_ratio` 는 **면적 기준으로 올바르게** 계산한다 → 두 기준이 이미 갈라졌다.

### 처방
`MAGDO_RULES` 에 **명시 필드** `consent_basis: "owner_count"|"land_area"|"use_right_area"` 추가.
소유자·면적 임계가 **둘 다 있는 방식은 둘 다 싣는다**(`consent_pct_owner`+`consent_pct_area`).
`governing_act`·`instrument` 가 이미 확립한 "추론 금지, 명시" 패턴 그대로.

---

## 4. P1 — consent 3종 배선 (거짓 고지 해소)

★**새 계산기를 만들지 마라.** `consent_land` ≡ `use_right_secured` 다:
- `use_right_secured` 는 P2 가 읽지만 **생산자 0**(테스트 픽스처에만 존재)
- `consent_land` 는 엑셀이 생산하지만 **소비처 0**
- **서로가 서로의 결측 반쪽이다.**

`secured_ratio`·`_parcel_secured_area`·`min_count_combination`·`severability` 는
**거부 규율(면적 미상·지분 미파싱 → 숫자 안 냄)까지 완비**돼 있다. 잇기만 하면 살아난다.

### 처방
1. 프론트 응답 타입 2곳에 `consent_*` 선언 + `.map()` 에서 보존
2. 엑셀 `consent_land` → **소유자 단위** `owners[].use_right_secured` 매핑
   ★⚠️ **필지 플래그로 접으면 안 된다** — 공유지분 필지에서 1인만 동의했는데 필지 전체를
   확보로 세면 **분자 과대**가 된다. `_parcel_secured_area` 는 지분 가중을 하므로 소유자 단위여야 한다.
3. 분모(토지등소유자 총수)는 **등기부에서 이미 온다** — `_derive_ownership`
   (`registry_analysis_service.py:166-180`) → P1 카드 `owners`(`parcel_rights_survey_service.py:388`).
   ★**프론트 배열 길이를 세면 안 된다** — `GlobalAddressSearch.tsx:1073-1081` 이
   같은 필지 여러 행을 **1필지=1행으로 접는다**. 분모는 반드시 백엔드 등기부 경로.

---

## 5. P2 — 신호 정직화 (성장루프가 잘못 배우는 것을 막는다)

- `undecided_rows` 정수 → **`undecided_by_reason: {code: count}`**.
  `_row_action` 이 이미 `(action, reason)` 을 돌려주므로 **사유는 이미 계산돼 있다** —
  안정 코드만 붙이면 된다: `UNDECIDED_NO_ACT` / `TRACK_INPUT_MISSING` /
  `HOLDING_PERIOD` / `TOPOLOGY_UNKNOWN` / `NO_ANALYSIS`.
  → `TRACK_INPUT_MISSING` 이 "데이터 부족"이 아니라 **"제품에 입력 필드가 없다"** 로 분리된다.
  ★제거가 아니라 **분리**다. 계약 상수에 결속(문자열 금지).
- **조인 키** `strategy_run_id = uuid4()` — 응답 + 이벤트 payload 에 동봉.
  ★**PNU 해시 금지** — 저엔트로피 공개 식별자라 해시해도 역산된다.
  선행 패턴: `payload.project_id`(design_ingest) · `run_id`(c2r).

---

## 6. P2 — P2 를 화면에 붙인다 (소비처 0 해소)

붙는 자리는 이미 있다 — `ParcelSurveyQuotePanel.tsx:181-190` 이 필지 선택·요청 조립을
갖고 있으므로 **후속 버튼 하나**다. 신규 화면 0개.

⚠️ **용량 불일치**: 엑셀 상한 500행(`parcel_excel_service.py:40`) vs P2 상한 100
(`MAX_STRATEGY_PARCELS`, 초과 422). 500필지 조서 사용자가 422 를 맞는다.
상한을 올리는 게 아니라(유료라 정당) **분할 안내 UX** 로 푼다.

---

## 7. 변이 생존 잠그기 — **전량이 아니라 트리아지**

★CLAUDE.md: *"생존이 곧 결함은 아니다. 이중 가드·도달 불가 방어라면 **그 사실을 코드에 적어라**.
설명할 수 없는 생존만 진짜 구멍이다."* → **점수 올리기용 테스트는 안티패턴**이다.
`--base 2839a37a --max 3000` 전수 실측을 기준선으로, 각 생존을 **TEST / ANNOTATE / 무시**로 분류한다.
(이전 보고의 "24건"은 머지 전 트리 기준이라 재측정 중.)

---

## 8. 범위 밖 — 정직하게 미결로 남긴다

- **결과 라벨 표면**: "판정 대비 실제"가 성장루프의 전제인데 실세계 결과
  (협의성사/제척확정)를 기록하는 표면이 **저장소 전역 0건**. 입력만 있고 정답이 없다.
  신규 테이블+입력 UI 가 필요하며 이 작업의 범위를 넘는다.
- **analyzer 도메인 축**: 기존 인사이트 5종은 전부 플랫폼 헬스 축. 판정 품질 축은 미존재.
- **시행자유형 입력**: 넣는다면 **`Project.metadata_` JSON**(사업 단위 속성이므로 필지 레벨 금지,
  alembic 0건). 단 §0-3 때문에 **P2 화면 배선 이후**가 맞다.
- **`MAX_PARCELS_FOR_GRAPH=200` 성능**: 재개발 구역은 300~800필지. **재보지 않았다** — 측정 후 판단.

### ★실행자 금지사항 3개

1. **`consent_pct` 를 단일 임계로 쓰지 마라** — 기준이 소유자수/면적/사용권원으로 갈린다(§3).
2. **`"관리지역"` 문자열 매칭 금지** — 이 코드베이스에서 그 단어는 **용도지역**
   (보전/생산/계획관리지역)이다. 모아타운 관리지역은 **별도 불리언 필드**로만.
   실증: `land_info_service.py:778` 이 "관리지역"을 용도지역 대분류로 하드코딩한다.
3. **`_magdo()` 를 남겨두고 `scheme_legal_profile()` 만 고치지 마라** — 사용자가 보는 화면은
   `_magdo()` 쪽이다(§1). 일원화가 조건이다.

---

## 실행 순서 (의존성 반영)

```
1) §1 _magdo 일원화      ← 프로덕션 오표시. 최우선
2) §2 성장루프 payload   ← 내 버그. 배선만, 리스크 최소
3) §3 consent_basis 명시 ← §1·§4 의 선행
4) §4 consent 배선       ← 거짓 고지 해소
5) §5 신호 정직화        ← 성장루프가 잘못 배우는 것 차단
6) §6 P2 화면 배선       ← 소비처 0 해소
7) §7 변이 트리아지      ← 위 작업이 코드를 바꾸므로 마지막
```

§8 은 인계.

---

## 9. ★멱등성 — **만들지 마라. 이미 있고 소비처가 0이다** (2026-08-16 실측)

`app/core/idempotency.py` 는 **완성된 모듈**이다 — `normalize_key` · `compute_request_hash` ·
`ensure_schema` · `lookup`(miss/replay/conflict 3상태) · `save`. 테넌트 격리
(`COALESCE(tenant_id,'')·endpoint·key` 유니크)와 **fail-open**(DB 장애 시 일반 실행)까지 있다.

**그런데 라우터 소비처가 0이다.** `sales/actions.py:537` 이 `idempotency_key` 를 받지만 그건
자체 파라미터지 이 모듈이 아니다. → **"정의만 하고 소비처 0"** 이 과금 안전장치에서 또 났다.

### 배선 경로 (그대로 따르면 된다)

대상: `/registry/get-one` · `/bulk` · `/analyze` · `/survey/strategy` (과금 4곳)

1. 각 핸들러에 `db: AsyncSession = Depends(get_db)` 추가
   — 지금은 과금 헬퍼가 내부에서 `async_session_factory()` 를 열어서 핸들러에 `db` 가 없다.
2. 핸들러 진입 직후:
   `key = normalize_key(request.headers.get("Idempotency-Key"))` → 없으면 그냥 실행(하위호환)
   `h = compute_request_hash(req.model_dump())`
   `r = await lookup(db=db, key=key, tenant_id=…, endpoint="registry.bulk", request_hash=h)`
   · `replay` → **저장된 body 를 그대로 반환**(과금 경로를 타지 않는다 — 이게 핵심)
   · `conflict` → 422(키 오사용)
   · `miss` → 실행 후 `save(...)`
3. ★**순서가 계약이다**: `save` 는 과금 **뒤**여야 한다. 앞이면 과금 실패 시 성공 응답이 박제된다.

### ★락은 이렇게 (두 모집단이 아니라 **세 모집단**)

- 같은 키 2회 → 원장 증분 **1회분**(replay 는 과금하지 않는다)
- 다른 키 2회 → **2회분** ← 이게 없으면 "멱등성"이 그냥 "과금 안 함"과 구분되지 않는다
- 같은 키·다른 바디 → **422**
★셋이 **서로 다른 결과**를 내야 잠금이다. 차가 0이면 잠금이 아니다.

### 왜 이번 PR 에서 안 했나 (정직)

4곳 DI + 응답 재생은 실질 변경이고, **반쯤 만든 멱등성은 "멱등성 있음"이라는 거짓 확신**을
만든다(부분 커버리지가 무커버리지보다 나쁜 전형).

★현재 노출: 더블서브밋·재시도가 **그대로 이중청구**된다. 이번에 넣은 레이트리밋(20/분·IP 기준)은
**빈도 축이지 중복 축이 아니다** — 간격이 넉넉해도 두 번은 두 번이다.

---

## 10. 잔여 요약 (2026-08-16 갱신)

| 항목 | 상태 |
|---|---|
| `_magdo` 통로 일원화 + 축(`consent_basis`) 명시 | **완료**(#644) |
| 유료 경로 레이트리밋 | **완료**(#644 · IP 기준 — 계정 기준은 후속) |
| 등기 PDF 무인증URL · 성장루프 payload · 형제 상한 | **완료**(#639 · 배포·라이브 확인) |
| **멱등성 배선** | **미착수** — §9(모듈 실재·소비처 0) |
| **consent 3종 배선** | 미착수 — §4(수집되는데 소비처 0, 사용자에겐 "활용됩니다" 고지 중) |
| **성장루프 라벨 표면** | 미착수 — §8(실세계 결과 기록 표면이 저장소 전역 0건) |
| 계정 기준 레이트리밋 | 미착수(IP 기준의 한계 — NAT·IP 변경) |

★**검증 경계(정직)**: 성장루프 payload 적재는 **미검증**이다(이벤트 테이블 조회 수단 없음).
  `pdf_url` 제거의 **반대 방향**(`registry` 요약은 남아야 함)도 라이브에선 못 태웠다 —
  가짜 PNU 라 성공 카드가 없었고, 실주소는 실제 과금이 나가서 하지 않았다. 로컬 잠금뿐이다.
