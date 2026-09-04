# 보류값 계약 — **부재의 사유를 코드로** (표준 조사 기반 설계)

- 작성: 2026-08-25 · 브랜치 `feat/withheld-value-contract`
- 계보: D5(#821) · D6·D7(#825) · `#831`(관용 `X_basis` 확정)

## 0. 계획 게이트 §0 — 옵시디언 조회

`nullable|판정 보류|_basis|provenance|무목업` 로 볼트 **517파일** 조회(대조군 확인).
→ **무목업 원칙**(값을 못 구하면 정직 null)은 이 저장소의 오래된 규율로 다수 기록됨.
   그러나 **"왜 없는지를 기계가 읽을 수 있게"** 한 기록은 **없음.** 이 계획이 그 공백을 메운다.

## 1. ★작업 정의부터 틀렸다 — "16파일 일괄 개조"는 잘못된 모집단

`판정 보류|보류 —|산출 보류` 로 뽑은 16파일을 **한 덩어리로 개조하자**는 것이 원안이었다.
파일을 실제로 열어 보니 **세 가지가 섞여 있었다**:

| 부류 | 건수 | 실체 |
|---|---|---|
| **생산자**(응답에 보류값을 싣는다) | **6** | ← **진짜 대상** |
| 주석·상수 설명 | 6 | `FALLBACK_MIN_CALLS = 10  # …판정 보류` — 계약이 아님 |
| 소비자(이미 보류된 값을 그림) | 5 | `ParcelBoundaryMap`·`dominant-zone` 등 |

★**문구로 모집단을 뽑으면 생산자·주석·소비자가 섞인다.** 일괄 개조했다면 절반이 무의미한
변경(churn)이 되고, 신호는 오히려 줄었을 것이다. — *확장자가 영향 범위가 아니듯, 문구도
계약이 아니다.*

## 2. 그리고 생산자 6건은 **부재가 아니라 불일치**였다 (§29)

여섯 곳 **전부 이미 "코드 비슷한 것 + 사유"를 갖고 있다.** 어휘만 다섯 갈래다:

| 파일 | 코드 자리 | 사유 자리 |
|---|---|---|
| `site_score_service` | `grade=None` | `grade_basis` |
| `parcel_rights_survey_service` | `sell_claim_judgment="판정 보류"` ★**센티널 문자열** | `sell_claim_reason` |
| `zoning/ordinance_conditional` | `_bucket="undecidable"` | `why` |
| `sales/pricing/suggest` | `data_source="unavailable"` | `note` |
| `sales/admin/console` | `None` | (주석뿐) |
| `decision_brief_service` | — | `reasons[]` |

★★**`sell_claim_judgment="판정 보류"` 는 D7 과 같은 결함**이다 — 판정 자리에 **판정이 아닌
문자열**이 들어간다. 소비처가 `judgment == "매도청구 가능"` 으로 비교하면 조용히 거짓이 된다.

## 3. 표준 조사 — 세 도메인이 같은 답에 도달해 있다

| 표준 | 무엇 | 이 설계에 주는 것 |
|---|---|---|
| **HL7 FHIR** `dataAbsentReason` | 값이 없는 **이유를 코드**로(`unknown`·`asked-declined`·`masked`·`not-applicable`·`error`) | ★**부재 사유를 닫힌 어휘로** — 산문은 셀 수 없다 |
| **SDMX** `OBS_STATUS`/`CONF_STATUS` | `M`(존재 불가) vs `_Z`(해당 없음) 구분, 기밀 억제는 **별도 축** | ★**"모른다"와 "해당 없음"과 "가렸다"는 다른 상태** |
| **W3C PROV-O** | `wasDerivedFrom`·`wasGeneratedBy` — 값의 **출처** | ★출처는 **값이 있을 때도** 말해야 한다 → `X_basis` 항상 채움 |

**공통 교훈**: null 은 그 자체로 **모호**하다(unknown / not-applicable / withheld 중 무엇인지
알 수 없다). 표준들은 예외 없이 **값 옆에 사유를 코드로** 둔다.

## 4. 계약 (PropAI 판)

    X            : 값 | None
    X_basis      : str        # ★항상 — 값의 출처 또는 보류 사유(저장소 관용, #831)
    X_absent     : 코드 | None # ★X 가 None 일 때만 — 닫힌 어휘

**닫힌 어휘**(FHIR/SDMX 를 부동산 분석 도메인으로 사상):

| 코드 | 뜻 | 표준 대응 |
|---|---|---|
| `insufficient_coverage` | 지표·표본이 하한 미달 | SDMX 표본부족 |
| `single_source` | 독립 추정 1개 — 교차검증 불가 | — (도메인 고유) |
| `source_unavailable` | 외부 원천 조회 실패·무응답 | FHIR `error` |
| `masked_by_source` | 원천이 가림(지번 마스킹 등) | FHIR **`masked`** |
| `ambiguous` | 판정이 갈려 **단일화를 거부** | SDMX `M`(존재 불가) |
| `not_applicable` | 이 대상엔 해당 없음 | FHIR/SDMX **`_Z`** |
| `awaiting_input` | 사용자 입력 대기 | FHIR `not-asked` |

★**센티널 금지**: 값 자리에 `"판정 보류"`·`"mixed_review_required"` 같은 문자열을 넣지 않는다.
값은 `None`, 사유는 `X_absent`, 문구는 `X_basis`.

## 5. 처방 — 공용 모듈 + 생산자 배선 + 파생 락

1. `app/utils/withheld.py` — 어휘 상수 · `withheld(code, text)` · `is_withheld()` · 검증기
2. 생산자 배선(도메인 판단이 명확한 순): `site_score` → `parcel_rights_survey`(센티널 제거)
   → `sales/pricing/suggest` → `ordinance_conditional`
3. **파생 락** — 코드에서 `*_absent` 를 뽑아 ①닫힌 어휘 밖 값 금지 ②`X` 가 None 인데
   `X_absent` 없으면 실패(**양방향**) ③센티널 문자열이 값 자리에 없을 것

## 6. ★완성도에 대한 정직한 정의

*"100%"* 를 **파일 수**로 세지 않는다 — 위 §1 이 보여주듯 그 분모가 틀렸다.
측정 가능한 것만 보고한다:
- **닫힌 어휘 밖 코드 0건**(파생형 검사)
- **양방향 위반 0건**(값 None ↔ 사유 존재)
- **센티널 문자열 0건**(값 자리)
- **배선한 생산자 / 전체 생산자** — 분수로 표기하고 미배선분은 **사유와 함께** 남긴다
