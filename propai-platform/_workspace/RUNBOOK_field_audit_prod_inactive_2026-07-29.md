# 런북 — field_audit 프로덕션 "비활성" 진단 (2026-07-29) → **[해소·전제 무효] 2026-07-31**

> ## ★★ 종결 결론 (2026-07-31) — 이 런북의 전제는 **틀렸다**
>
> **field_audit은 프로덕션에서 비활성이었던 적이 없다.** 실제 원인은 검증 *대상*이 아니라 검증
> **경로(호스트)** 오염이었다:
>
> - 158 공개 nginx가 `location /api/` → `http://api:8000`(158에 **동거 중인 구버전 컨테이너**,
>   이미지 2026-07-02 ≈4주 전)으로 프록시하고 있었다. 그래서 `https://4t8t.net/api/*` 로 재면
>   `field-audit-status` 404 · `age_status`/`current_far_pct`/`total_floor_area_sqm`/
>   `dominant_constraint` 키 부재로 관측됐다.
> - 반면 실사용 origin `https://api.4t8t.net/*`(Caddy→168)는 **계속 최신**이었고 field_audit도
>   `{enabled:true, rules_registered:8}`로 **계속 활성**이었다. 168 공개 전환은 실패한 적이 없다.
> - 봉합 = **#507**(nginx 4개 location을 upstream `backend_api=168:80`으로 수렴 — 블루그린
>   8000↔8001 교대 때문에 `:8000` 직결이 아니라 Caddy `:80`) + **#508**(`app/api/proxy/[...path]`
>   의 `http://api:8000` 하드코드를 `NEXT_PUBLIC_API_BASE_URL` 우선 SSOT로 — nginx를 우회하는
>   유일 잔여경로). main 머지·158 배포 완료(1dd3f1e8).
>
> **배포 후 재측정(2026-07-31)**: apex/www/api openapi 라우트 752→**813 세 호스트 수렴** ·
> apex `field-audit-status` 404→**200 {enabled:true, rules_registered:8}**.
>
> ### 이 런북에서 살릴 것 / 버릴 것
> - **버릴 것**: "배포 stale/env/import 3원인" 진단표와 그에 딸린 수정절차 — 원인이 그 셋 중
>   어느 것도 아니었다(공개 호스트 프록시 대상 오류).
> - **살릴 것**: 아래 "확정 근거"의 **분석 방법**(analyze()가 :1103을 항상 통과·미들웨어 strip
>   부재 전수확인)은 유효하다. 다만 그 관측이 **어느 호스트에서 나온 값인지**를 고정하지 않아
>   잘못된 결론으로 갔다.
>
> ### ★교훈 (재발방지 — 이게 이 문서의 유일한 잔존가치)
> 1. **측정경로를 먼저 고정하라.** "공개 endpoint로 검증"까지는 옳았으나 *공개 endpoint가 여러
>    호스트로 갈라져 서로 다른 백엔드를 가리킬 수 있다*는 가능성을 세우지 않았다. apex·www·api
>    세 호스트의 openapi 라우트 수를 **대조**했으면 즉시 드러났다(752 vs 813).
> 2. **차단신호를 결론으로 승격하지 말 것.** `field-audit-status` 404는 "#497 미전환"만 증명하고
>    "기능 비활성"을 증명하지 않는다 — 8규칙은 전부 #497 **이전**(#483~#493) 머지분이다.
>    (2026-07-30 세션이 이 구분을 명시해 비활성 단정을 보류한 것이 결과적으로 옳았다.)
> 3. **반증조건을 사전에 명시하라.** 통합자가 배포 전에 "813이면 확증 / 752면 내 진단 오류"를
>    적어두고 착지시킨 방식이 정답 패턴이다.
>
> ### 라이브검증 결과 (2026-07-31·게이트 해소 후 수행)
> - `GET /api/v1/data-integrity/field-audit-status` (apex·api 양쪽) → **200**,
>   `enabled:true`, `rules_registered:8`, rule_ids 8종 전량(G1·G2·G3·MARKET_PRICE_METHODOLOGY·
>   PROV_STALE_DATA·PROV_UNKNOWN_SOURCE·SALE_PRICE_POINT_ESTIMATE·TERRAIN_SLOPE_COLLECTION_GAP).
> - 실분석(호미곶 대보리 산1-1·200/108s) → `result["field_audit"]` **부착 확증**,
>   metadata `{enabled:true, rules_registered:8, rules_executed:8, zone_type:"보전관리지역"}`,
>   findings 1건 = `MARKET_PRICE_METHODOLOGY`(P2·계층B).
> - **G1 무발동은 정상(근원수정 확증)**: `parcel-boundaries`(PNU 4711135022200010001) 실응답의
>   `dominant_constraint` = headline "통제보호구역(방공기지:500m) — 군부대 협의 없이는 건축 불가",
>   **severity "높음"**, ranked 2건(통제보호·제한보호 모두 높음). 즉 원 결함(통제보호구역인데
>   리스크 '낮음')은 SSOT 수준에서 교정됐고, `_research_dev_plans`가 동일 SSOT
>   (`severity_for`/`max_severity`)를 소비하므로 risk_level이 하한을 충족 → G1이 침묵하는 것이
>   설계대로다(정상 필지 배지 인플레 방지).
> - **정직 바운딩**: `development_plans.risk_level` 필드값 자체는 직접 눈으로 확인하지 못했다
>   (종합분석이 CF 524 경계에 걸쳐 재현 실패 — 아래 잔여이슈). 위 판정은 ①동일 SSOT 소비 코드경로
>   ②`dominant_constraint`의 severity "높음" 실측 ③G1 무발동 세 근거의 합이다.
> - **가드 한계(정직 고지)**: G1의 오라클과 생산자가 **같은 SSOT**를 읽는다 → G1은 "생산자가 SSOT에서
>   이탈하는 회귀"는 잡지만 **SSOT 자체의 오분류는 구조적으로 잡을 수 없다**. 진짜 독립오라클이
>   아니므로 SSOT 등재값은 별도 근거(법령·고시)로 주기 검증해야 한다.
>
> ### ★잔여 이슈 (이 런북 범위 밖·별건 티켓 필요)
> **종합분석 CF 524** — `POST /api/v1/analysis/comprehensive`가 공개경로에서 108s(성공 1회) vs
> 124~126s(524 6회)로 **Cloudflare 한계에 걸쳐 있다**. 2026-07-31 실측 7회 중 성공 1·실패 6.
> 07-29 시점 103s/94s(마진 6초)에서 마진이 소진된 상태. 프론트는 동기 호출이고 비동기 잡 경로가
> 없어 **실사용자도 간헐 524**를 받는다. 근본해소=비동기 잡+폴링 전환(대공사) 또는 서브분석
> 병렬화/타임박스. 자가검증과 무관한 별건이나 사용자영향은 이쪽이 더 크다.

---

## (이하 원본 — 2026-07-29 작성 시점 기록·전제 무효이나 방법론 참고용 보존)

## 증상 (라이브검증 확정 ← ★무효: 아래 관측은 158 동거 구버전 컨테이너에서 나온 값이었다)
배포된 168 백엔드의 `POST /api/v1/analysis/comprehensive` 응답에 **`result["field_audit"]` 키가 부재**.
자가검증 레이어(W0~W3-2·#483~#493·6모듈·8규칙)가 **프로덕션에서 비활성**.

### 확정 근거 (오탐 아님)
- 직호출 status **200·신선 실행**(103초·`analyzed_at` UTC 일치 = 캐시 아님)인데 응답 top-level에 `field_audit` 키 없음(비어있음 아니라 부재).
- `analyze()`(comprehensive_analysis_service.py :479-1119)는 `return`이 **:1118 단 하나**로 field_audit 배선(:1103)을 **항상 통과**. 조기 return/raise 없음.
- 응답 본문을 벗기는 미들웨어/직렬화 **없음**(VersionHeader=헤더·GrowthTelemetry=관찰·custom=컨텍스트·SlowAPI=레이트리밋·전수 확인).
- → 부착 부재 = 배포 백엔드가 실제로 안 붙임.

## 빠른 확인 (가드 PR #497 배포 후)
가드 엔드포인트는 **무인증 공개**라 서버 로컬뿐 아니라 **프론트 프록시(4t8t.net) 경유로도** 확인 가능:
```bash
# 서버 로컬
curl -s http://localhost:<PORT>/api/v1/data-integrity/field-audit-status
# 또는 외부(에이전트 포함 누구나·SSH 불필요)
curl -s https://4t8t.net/api/v1/data-integrity/field-audit-status
# 또는 스모크
PROPAI_API_BASE=http://localhost:<PORT> bash propai-platform/scripts/smoke_field_audit.sh
```
기대: `{"enabled": true, "rules_registered": 8, "rule_ids": [...]}`

> ★2026-07-30 진단 실측: 현 배포는 `field-audit-status` **404**(=#497 미배포·현 배포는 #497 이전) / `data-integrity/status` **200 healthy**(백엔드 정상). 에이전트 환경에서 **백엔드 SSH(134.185.104.167/.168:22)는 네트워크 차단**(Oracle 보안리스트)이라 SSH 진단 불가 — **현 main 배포(#497 포함) 후 위 4t8t.net curl로 원인·활성 확인**이 가장 빠른 도달 경로.

| 응답 | 원인 |
|---|---|
| `404` | 배포 stale (가드 엔드포인트 미배포 = field_audit 코드도 구버전) |
| `"enabled": false` | env `FIELD_AUDIT_ENABLED=0` |
| `500` | prod 임포트/런타임 예외 |
| `"rules_registered": 0` | invariants 등록 파손 |

## 진단 (3 원인 · 가드 미배포 시 수동)
### ① Stale 배포
running process가 `15092782`(또는 field_audit 포함 커밋) 인지:
```bash
docker ps                                   # 컨테이너 생성시각 vs #483(be517bd6~) 머지시각
ls .../apps/api/app/services/verification/field_audit/invariants/   # 6모듈 존재?
grep -n "field_audit" .../comprehensive_analysis_service.py | grep 110  # :1103 배선 존재?
```
### ② env FIELD_AUDIT_ENABLED
```bash
docker exec <container> printenv FIELD_AUDIT_ENABLED   # unset 또는 1 기대 · 0/false/off면 원인
```
### ③ prod 임포트/런타임 예외
```bash
grep "field_audit 하네스 스킵" <backend.log>           # graceful-skip(DEBUG)·있으면 그 예외가 원인
docker exec <container> python -c "from app.services.verification.field_audit import runner; print(runner.audit_status())"
```

## 수정 (원인별)
1. **Stale** → `15092782`+ 재배포·**프로세스 재시작 확인**(blue-green 활성 포트가 새 이미지인지·`이미지<시각>` vs 머지시각).
2. **env** → `FIELD_AUDIT_ENABLED` unset 또는 `=1` · 재시작.
3. **import** → 로그의 예외를 코드/의존성 수정.

## 검증 (수정 후)
```bash
bash propai-platform/scripts/smoke_field_audit.sh        # exit 0 · {enabled:true, rules_registered:8}
```
- 실분석 1건 → `result["field_audit"]` 존재 확인.
- 이후 에이전트가 호미곶 G1(리스크 낮음→높음) 실제수정 라이브검증 재수행.

## 전역 전파방지 (필수)
**배포 파이프라인에 `scripts/smoke_field_audit.sh`를 배포후 게이트로 추가** → field_audit(관측전용·UI 무변화)의 무성 회귀 영구 차단. 통합자 배포검증이 health200/sw/arq만 보던 갭을 봉합.

## 부수 관찰 (insight-loop 정직 재평가·과장 배제)
- **CF 524 (간헐적 엣지·확정 P0 아님)**: 종합분석은 **동기 단일응답**(`ComprehensiveAnalysisPanel.tsx:447` `/analysis/comprehensive`·override 타임아웃 없음·주석 :596 "최대 2분" 인정). 느린 첫 분석(>~110초)은 Cloudflare ~110초 한계 초과로 524 가능. **단** `analysis-fetch-cache.ts`(localStorage)+프로젝트 "l3" 캐시로 **재진입은 캐시히트(빠름)**·degraded(103초)는 CF 통과 — **첫 분석·느린 필지에서만 간헐**. "실사용자 전면 차단"은 과장(초기 판정 정정). 근본해소 원하면 async 잡+폴링化(대공사)·아니면 캐시 워밍/CF 타임아웃 조정(통합자). **실측 미완**(해결필지 분석이 CF로 막혀 단일필지 정상경로 실시간 확인 불가) — 필요시 통합자 직결 백엔드로 재측정.
- **직접 API 지오코딩**: address-only 호출은 필지 미해결(pnu=null·키워드 추론 폴백). UI는 VWorld로 필지 해결 후 parcels[] 전달 — 직호출 아티팩트(실사용자 UI경로 아님).
