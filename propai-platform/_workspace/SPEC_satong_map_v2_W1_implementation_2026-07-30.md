# SPEC — 사통맵 v2 / W1 상세 구현계획 (지배 제약 + 높이 상한)

작성 2026-07-30 · 상태: **구현 착수 가능** · 1차 타깃: 설계사·디벨로퍼
상위: `PLAN_satong_map_v2_execution_2026-07-30.md`

---

## 0. ★계획 수정 — 착수 전 검증에서 잡힌 것

상위 계획에 `높이 상한: min(고도지구 20m, 정북일조 18m, 비행안전 30m) = 18m`라고 썼으나 **코드 실측 결과 실현 불가**다.

| 재료 | 실태 | 근거 |
|---|---|---|
| 정북일조 최고높이 | ✅ **숫자 산출 가능** | `common/sunlight_setback.py:30 max_height_for_north_distance_m(distance_m)` |
| 고도지구 높이 | ❌ **수치 룩업 없음** | 고도지구는 WMS 타일(`lt_c_uq123`) = 그림. 조례 수치 테이블 grep 0건 |
| 비행안전구역 높이 | ❌ **수치 없음** | `protection_zone_severity`가 severity(높음/보통)만 보유 |
| 지배 제약 랭킹 | ✅ 가능 | `regulation/protection_zone_severity.py: SEVERITY_ORDER · severity_rank()` |

**→ W1은 "수치 min() 통합"이 아니라 다음 두 가지로 확정한다.**
1. **지배 제약 한 줄** — 완전 실현 가능(severity 랭킹)
2. **높이 상한** — **수치가 있는 항목만 숫자로**, 나머지는 `지정됨(수치 미보유 — 조례 확인 필요)`로 정직 표기

이 정직 표기가 오히려 사용자 가치다: "고도지구에 걸렸는데 수치는 조례를 봐야 한다"는 것 자체가 설계사에게 필요한 정보다.

**부수 티켓(별건)**: 고도지구 수치 룩업 부재 → 조례 수집 필요.

---

## 1. 산출물 계약

### 1-1. 백엔드: `dominant_constraint` 블록 (신설)

**위치**: `apps/api/app/services/regulation/dominant_constraint.py` (신설)
**소비**: `comprehensive_analysis_service.analyze()` 및 지도 필지 상세 응답

```python
def resolve_dominant_constraint(
    regulations: list[str],          # 규제명 목록(기존 land_use districts)
    *,
    north_distance_m: float | None,  # 정북 인접지 거리(있으면 일조 높이 산출)
    slope_pct: float | None,         # terrain 평균 경사도
) -> dict:
    """이 필지에서 '무엇이 가장 발목인가'를 한 줄로 답한다.

    반환:
      {
        "headline": "군사 통제보호구역 — 군부대 협의 없이는 건축 불가",
        "severity": "극히 높음",
        "ranked": [                       # 상위 3개까지
          {"name": "군사 통제보호구역", "severity": "극히 높음", "action": "군부대 협의"},
          {"name": "경사도 18%", "severity": "보통", "action": "토공 계획 검토"},
        ],
        "height": {
          "governing_m": 18.0 | None,     # 수치가 있는 것 중 최소
          "governing_source": "정북일조" | None,
          "items": [
            {"source": "정북일조", "limit_m": 18.0, "basis": "건축법 시행령 §86"},
            {"source": "고도지구", "limit_m": None,
             "note": "지정됨 — 수치는 조례 확인 필요(플랫폼 미보유)"},
          ],
        },
      }
    """
```

**규칙**
- severity는 `protection_zone_severity.severity_rank()`로 정렬(SSOT 재사용, 새 등급 정의 금지)
- `governing_m`은 **수치 보유 항목만**으로 계산. 미보유 항목이 있으면 `height.incomplete = True`
- 경사도는 severity 매핑(예: ≥20% 높음 / 10~20 보통 / <10 낮음) — 임계는 상수로 노출

### 1-2. 프론트: 필지 상세 최상단 배너

**위치**: `SatongMapShell.tsx` 필지 상세 팝오버(z-430) 최상단
```
┌─────────────────────────────────────────┐
│ ⚠ 지배 제약                              │
│ 군사 통제보호구역 — 군부대 협의 없이 건축 불가 │
│ 그다음: 경사도 18%                         │
├─────────────────────────────────────────┤
│ 높이 상한  18m  (정북일조가 지배)           │
│ · 정북일조 18m — 건축법 시행령 §86         │
│ · 고도지구 지정됨 — 수치는 조례 확인 필요     │  ← 정직 표기
└─────────────────────────────────────────┘
```
- `height.incomplete === true`면 숫자 옆에 **"일부 미반영"** 배지 — 18m가 최종이 아님을 명시
- 제약 0건이면 배너 자체를 렌더하지 않는다(빈 배너 금지)

---

## 2. 구현 순서 (커밋 단위)

| # | 작업 | 파일 | 게이트 |
|---|---|---|---|
| 1 | `dominant_constraint.py` 신설 + 단위 테스트 | 백엔드 신규 1 | pytest·ruff |
| 2 | `analyze()` 주경로 배선 + 응답 키 추가(additive) | `comprehensive_analysis_service.py` | 기존 골든 무회귀 |
| 3 | 필지 상세 응답에 포함(지도 경로) | 경계/상세 엔드포인트 | — |
| 4 | 프론트 배너 컴포넌트 + 렌더 | `SatongMapShell.tsx` | tsc·eslint·vitest |
| 5 | **배선 불변식** | `assertWiredThrough` 사용 | 변이 3층 |

---

## 3. 테스트 계약 (필수)

### 3-1. 단위 (`test_dominant_constraint.py`)
- 군사 통제보호구역 + 경사도 18% → headline이 **군사**(더 높은 severity)
- 규제 0건 + 경사 5% → `ranked` 비어 있고 headline None
- 정북거리 有 → `governing_m` 숫자 · `governing_source="정북일조"`
- 고도지구만 있고 수치 없음 → `governing_m is None` · `incomplete True`
- ★**severity SSOT 재사용 확인**: `protection_zone_severity`를 import해서 쓰는지(자체 등급 재정의 금지)

### 3-2. 배선 (★이번 세션 반복 결함 방지)
```ts
assertWiredThrough({
  file: "components/precheck/SatongMapShell.tsx",
  scope: /dominantConstraint/,
  mustContain: "detailFeature",
  minMatches: 1,
});
```
+ analyze() 응답에 키가 실제로 실리는지 관통 테스트(순수함수만 고정 금지)

### 3-3. 변이 3층 (규칙: `feedback_mutation_wiring_and_scope`)
1. **로직**: severity 정렬 뒤집기 → headline 바뀌어야 FAIL
2. **배선**: `analyze()`에서 키 제거 → FAIL
3. **표면**: 프론트 배너 렌더 제거 → FAIL

각 변이는 **주입 성공을 먼저 확인**하고, 동일 문자열이 여러 곳이면 **전부 치환**한다.

---

## 4. 완료 정의 (100%)

- [ ] 단위 테스트 통과 · 배선 테스트 통과 · **변이 3층 전부 CAUGHT**
- [ ] `ruff` 0 · `tsc` 0 · `eslint` 0 error
- [ ] 기존 전체 스위트 무회귀
- [ ] **게이트는 마지막 변경 뒤 재실행**(이번 세션에 순서 어겨 CI 차단 5건 자초)
- [ ] R1 적대적 리뷰 APPROVE (REVISE면 R2까지)
- [ ] PR 본문에 **정직 경계 명시**: 고도지구·비행안전 수치 미보유
- [ ] 머지 후 **통합자에게 배포 인계**

---

## 5. 하지 말 것

- 고도지구 수치를 **추정하지 마라.** 없으면 없다고 표기한다(이번 세션에서 "명세 표기 ≠ 실제"로 데인 지점).
- `protection_zone_severity` 밖에 **새 severity 등급을 만들지 마라.** SSOT 이중화는 이 저장소의 반복 결함.
- 배너를 **항상 렌더하지 마라.** 제약 0건이면 숨긴다(빈 배너는 노이즈).
