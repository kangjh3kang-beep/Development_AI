# 전제 감사 고지가 **두 표면 중 하나에만** 닿는다 — 통합분석에는 0건

작성: development-ai-fe (sid=`dcb7a4f2` · 2026-09-05 · 절대형 서명)
브랜치 `fix/premise-audit-integrated-surface` · base `6d3b39ece`(= origin/main 일치 실측)

---

## 0. 옵시디언 조회 결과 — **조회했고, 착수 방식을 바꿨다**

| 찾을 것 | 결과 |
|---|---|
| ★**이 작업은 「유예된 결정」이다** | ★★**적대 렌즈가 잡았다.** `_workspace/PLAN_premise_audit_surface_2026-09-04.md` **§2C 「하지 않는 것」**이 *"`auto_zoning` 표면 배선은 이 PR 에 넣지 않는다 … 두 표면을 한 PR 에서 건드리면 회귀 범위가 겹친다 → **`it.todo` 로 초록 안에 남긴다**"* 라고 **명시적으로 유예**했고, 그 마커가 실재한다 — `PremiseAuditNotice.test.tsx:283`. ⇒ **「내가 찾은 미발견 결함」이 아니라 「예고된 부채의 상환」**이다. 그렇게 적지 않으면 그 자체가 §증거규율 7 의 거울상이다 |
| **이미 기각된 접근** | ★**있다.** `concepts/형제를_재사용할지는_그_형제가_포기한_축으로_정한다.md` — 이 고지를 **기존 공용 렌더러 `IntegrityWarnings.tsx` 에 밀어 넣는 안이 기각**됐다. 그 형제는 *"배열이 비면 아무것도 그리지 않는다 — **침묵과 무결을 구분해 주장하지 않는다**"* 를 **포기했는데**, `premise_audit` 은 `checked`/`registered` 로 **그 축을 가진다.** 밀어 넣었으면 축이 사라졌을 것이다 |
| **같은 클래스의 앞선 결함** | `#963` 커밋: *"`#940` 에서 「백엔드 계약만 서고 화면 소비처 0」 으로 데였으므로 싣는 것만으로 끝내지 않는다 — **소비처는 별도 좌표로 남긴다**"* ⇒ **이 PR 이 그 좌표의 나머지 절반이다** |
| **미결·부채** | 인계서 §8: *"`auto_zoning` 표면이 감사 고지를 안 쓴다 — 데이터는 있고 소비처만 없다"* |
| **이전 판단의 근거** | `PremiseAuditNotice.tsx` docstring: *"**두 표면**이 그 결과를 응답에 싣는다: `scenario_simulator.py`(#963) · `routers/auto_zoning.py`(통합분석)"* |

★**신선도**: 위는 2026-09-04 기록이다. **승계하지 않고 §1 에서 전부 재측정했다.**

### 0-b. ★이웃 세션 확인 (겹침 방지)

`premise_audit` 영역에 브랜치가 **넷** 있었다. 전수로 확인했다:

| 브랜치 | 상태 | 내 축과 |
|---|---|---|
| `fix/premise-audit-scenarios-path` | **#963 MERGED** | 백엔드 시뮬레이터 — 안 겹침 |
| `fix/premise-audit-surface` | **#978 MERGED** | `PremiseAuditNotice` 를 **만든** 브랜치 — 내가 **재사용할 대상** |
| `fix/premise-audit-checked-contract` | **#982 MERGED** | 백엔드 독스트링/락 — 안 겹침 |
| `fix/premise-audit-integrated-surface` | **이 PR** | 프론트 **통합분석 표면** |

★착수 중 **남의 워크트리에 계획서를 잘못 썼다가 즉시 제거**했다(그 워크트리의 커밋은 건드리지 않았다 —
`git status --porcelain` 으로 원상복구 확인). 워크트리 이름을 추측하면 **남의 것과 충돌한다.**

---

## 1. 전제 표 — 확인 방법과 **실측값**

| # | 전제 | 확인 방법 | 결과(관측) |
|---|---|---|---|
| P1 | 생산자가 **둘**이다 | 비테스트 전수 grep | `scenario_simulator.py` · **`routers/auto_zoning.py`** |
| P2 | auto_zoning 은 **어느 엔드포인트**인가 | 원문 역추적 | **`POST /zoning/integrated-analysis`** (`auto_zoning.py:1715` · 적재 `:1953`) |
| P3 | ★**축이 살아 있는가** | `auto_zoning.py:1953~1957` | `{"checked", "registered", "violations"}` — **`PremiseAuditNotice` 계약과 맞는다** |
| P4 | 공용 렌더러가 **이미 있다** | `PremiseAuditNotice.tsx:104~118` | `PremiseAudit` 타입 + `PremiseAuditState`(`violations`/`failed`/`vacuous`/`partial`/`clean`) |
| P5 | 그 렌더러 소비처 | 전수(비테스트) | **`DevelopmentScenarioCard.tsx` 하나**(`:252`) |
| P6 | ★**결함 실재** | `/zoning/integrated-analysis` 소비처 **11곳** 전수에서 `premise_audit` grep | **11곳 전부 0건** |
| P6-대조 | 조회기 생존 | 같은 방법으로 `/zoning/comprehensive` | **7개 파일 검출** |
| P7 | base 일치 | `rev-parse` | `6d3b39ece` **일치** |

### ★인계서 라벨을 정정한다 — 「한 줄」이 아니다

`premise_audit` 은 **`scenario` 객체 안**에 실리는데(`scenario["premise_audit"]`),
`/zoning/integrated-analysis` 를 받는 프론트 11곳 중 **그 시나리오를 `DevelopmentScenarioCard` 로
그리는 곳이 없다**(P6). ⇒ **컴포넌트를 꽂을 자리부터 정해야 한다. 배선 지점 선정이 설계다.**

---

## 2. 변경 내용 — ★적대 렌즈가 **순서를 뒤집었다**

초판 처방은 *"`PremiseAuditNotice` 를 배선한다(한 줄)"* 였다. **그대로 하면 순이득이 거의 0이고 소음만 는다.**

### 왜 — 렌즈 실측

`auto_zoning.py:1958~1967` 이 위반을 **이미** `warnings`·`disclosure` 에 넣고 `status="tentative"` 로
강등하며, `multi-parcel/page.tsx` 가 그 둘을 **이미 그린다.**
⇒ 이 렌더러가 **더하는 값은 `vacuous`/`partial`/`failed` 세 갈래뿐**인데,
**그중 둘이 현재 원리적으로 도달 불가**다. 배선만 하면 **경고목록·고지문·감사상자 3중 표시**가 되고,
`PremiseAuditNotice` 독스트링이 스스로 경계한 *"위양성 피로가 정확한 보고까지 죽인다"* 에 걸린다.

### 그래서 이 순서로 한다

**① 실패 경로 스키마 대칭** (백엔드 · **먼저**)
`auto_zoning.py` 의 `except`(:1970)가 `premise_audit` **키를 아예 안 만든다.**
`undefined` → 렌더러가 `"clean"` 으로 분류 → **무렌더** ⇒ **감사가 가장 필요한 순간에 화면이 침묵한다.**
`scenario_simulator.py:900~903` 은 이미 `{violations:[], checked:0, registered:None, reason:"audit_failed", detail}` 로
**자기를 구별**한다. **두 생산자 스키마를 일치**시킨다.
★이 사실은 `PremiseAuditNotice.test.tsx:275` 가 **이미 적어 뒀다**(2차 적대 리뷰가 정정한 문장) — 승계하지 않고 재확인했다.

**② `structurally_vacuous` 를 auto_zoning 경로에서 **파생 계산**** (백엔드)
현재 `:1953` 화이트리스트는 `{checked, registered, violations}` 3키뿐이라 그 축이 **없다.**
그러면 화면이 `6/6 · 위반 0` 을 **「6종 전부 실행」**으로 읽는데, 렌즈 실측상 **판별력은 3/6** 이다.
⇒ 이 렌더러가 존재하는 **유일한 근거**(*"침묵과 무결을 구분한다"*)의 정확한 반전이다.
★★**simulator 의 값을 복사하지 않는다.** simulator 는 `["path_invariance_zone"]` 을 공허로 적는데
auto_zoning 에서 그 관계는 **거의 유일하게 살아 있는 신호**다(위임이 폴백했을 때 발화).
복사하면 **살아 있는 감시기를 「공허」로 오표기**한다.
★**손으로 나열하지 않는다** — 「목록이 곧 상한」. 경로 조건에서 파생시킨다.

**③ 배선** (프론트 · `multi-parcel/page.tsx`)
`/zoning/integrated-analysis` 소비처 4곳 중 **`scenario` 를 실제로 읽는 유일한 화면**이다(`:244`).
나머지 셋은 `scenario.status` 만 보거나 타입에 `scenario` 가 없다.

**④ `it.todo:283` 을 실제 락으로 교체** — 부채를 상환했으면 마커를 남기지 않는다.

**회귀가 아닌 근거**
- `PremiseAuditNotice` 는 `state === "clean"` 이면 **아무것도 그리지 않는다** → 정상 경로 화면 불변.
- 기존 소비처(`DevelopmentScenarioCard`)를 **건드리지 않는다**.
- ①은 **예외 경로에만** 키를 더한다(성공 경로 불변).

---

## 3. ★검증하지 못한 것 (비워 두지 않는다)

1. ~~배선 지점 미정~~ → **닫혔다**: `multi-parcel/page.tsx`(`scenario` 를 읽는 유일한 소비처).
1-b. ★**`path_invariance_zone` 의 공허 조건은 「추론(강)」이다** — 렌즈가 반증 조건을 남겼다:
   `build_integrated_context` 는 `area_sqm>0` 만 남기는데(`:1963-1964`) 라우터는 안 거른다.
   **면적 결측 필지가 우세를 가르면** 두 경로가 갈리고 그 관계는 **살아난다.**
   ⇒ ②의 파생을 **조건부**로 짜야 한다. 계측 장치는 실재한다(`_record_multiparcel_collapse`) — **미조회**.
1-c. **위임 실패율 미측정** — MAJOR-3 의 실제 빈도를 모른다(성장루프가 이 축을 안 낸다 = **장치 부재**). 11곳 중 어디가 「통합분석 결과를 사용자에게 보이는 화면」인지
   **재지 않았다.** 적대 렌즈에 판정을 맡겼고 **결과 대기 중**이다.
   ⇒ 잘못 고르면 **보이지 않는 곳에 고지를 다는 것**이 되어 결함이 그대로 남는다.
2. **`structurally_vacuous` 축**: `scenario_simulator.py:893` 은 일부 관계를 그렇게 표시하는데
   **auto_zoning 경로도 같은 처리가 필요한지 미측정**이다. 두 경로가 **다른 관계 집합**을 가지면
   같은 렌더러가 **틀린 고지**를 낼 수 있다.
3. **라이브에서 위반이 실제로 나는지** 재지 않았다 — 「오도가 가능하다」까지가 관측이다.
4. **화면(브라우저) 실측** 없음 — 락은 렌더 테스트로 잠근다.

---

## 4. 되돌리기 경로

단일 PR revert. 프론트 배선만 · 백엔드·계약·데이터 변경 없음.

---

## 5. 잠금 — 이 변경을 지키는 검사

| 잠그는 명제 | 형태 |
|---|---|
| **고지가 실제로 렌더된다** | 위반이 있는 페이로드로 **문구가 나옴**을 단언(이름이 아니라 값) |
| **★`checked=0` 을 「깨끗함」으로 그리지 않는다** | 볼트가 지목한 **그 축** — `checked=0`·위반 0 이 **공허 고지**를 내는가 |
| **두 모집단** | `clean` 과 `violations` 를 **같은 실행에서** 렌더해 **다른 결과**임을 단언 |
| **정상에 배지를 늘리지 않는다** | `clean` 이면 **아무것도 안 그림**(음성 대조군) |
| **공허 진리 방지** | 단언 **앞에** 대상 존재를 먼저 확정 |

★**변이로 CAUGHT 를 확인한다**. ★**닫지 못하는 것**: `structurally_vacuous` 의 경로별 차이 → `it.todo`.
