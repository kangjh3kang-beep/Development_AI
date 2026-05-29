# 주소 1회 입력 → 전체 플랫폼 자동 반영 워크플로우

## 참조 UX 원칙

### 1. Single Source of Truth (단일 진실 공급원)
주소 데이터를 한 곳에서 관리하고 모든 모듈이 이를 참조.
중복 입력 제거로 데이터 불일치 방지.
> "주소를 수동 재입력하면 오타/변형으로 중복 레코드 발생" — NN/G EAS Framework

### 2. Progressive Disclosure (점진적 공개)
주소 입력 → 기본 정보 표시 → 상세 분석 단계별 공개.
사용자가 필요할 때만 깊은 정보를 볼 수 있도록.
> "즉각적 과업에 필요한 것만 보여주고 나머지는 뒤로 미루라" — Jakob Nielsen, 1995

### 3. Once-and-Done Input (1회 입력 원칙)
Chrome 자동완성 연구: 폼 완료율 25% 향상 (Google Chrome, 2024).
주소 1회 입력으로 전체 분석 파이프라인 자동 트리거.

### 4. Contextual Disclosure (맥락적 공개)
주소 입력 후 해당 토지의 용도지역에 따라 관련 분석 항목만 표시.
예: 녹지지역이면 "공동주택 개발" 옵션 비활성화.

---

## 워크플로우 아키텍처

```
┌─────────────────────────────────────────────┐
│  주소 검색 입력 (카카오 주소 API)             │
│  ┌─────────────────────────────────────┐     │
│  │ 🔍 경기 의정부시 의정부동 224       │     │
│  │    + [필지 추가] (다필지 지원)       │     │
│  └─────────────────────────────────────┘     │
└─────────────────┬───────────────────────────┘
                  │ 주소 확정
                  ▼
┌─────────────────────────────────────────────┐
│  STEP 1: 자동 데이터 수집 (백그라운드)        │
│                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │PNU 변환  │ │용도지역  │ │공시지가  │    │
│  │(VWORLD)  │ │(VWORLD)  │ │(VWORLD)  │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘    │
│       │            │            │           │
│  ┌────┴─────┐ ┌────┴─────┐ ┌───┴──────┐   │
│  │건축물대장│ │토지이용  │ │조례분석  │   │
│  │(공공데이터)│ │계획     │ │(법제처)  │   │
│  └──────────┘ └──────────┘ └──────────┘    │
│                                             │
│  → ProjectLandData (단일 진실 공급원)        │
└─────────────────┬───────────────────────────┘
                  │ 데이터 수집 완료
                  ▼
┌─────────────────────────────────────────────┐
│  STEP 2: 전체 모듈 자동 반영                  │
│                                             │
│  📊 대시보드     ← 토지 요약 카드 자동 표시   │
│  🗺️ 입지분석    ← 용도지역/규제/시세 자동반영 │
│  ⚖️ 법규검토    ← 건폐율/용적률/조례 자동반영 │
│  🎨 건축설계    ← 대지면적/법규한도 자동반영   │
│  📈 수지분석    ← 분양가/토지비/공시지가 자동  │
│  🏗️ BIM         ← 면적/층수 자동반영          │
│  📝 인허가      ← 허가가능종목 자동분류        │
│                                             │
│  → 사용자 추가 입력: 0건 (완전 자동)          │
└─────────────────────────────────────────────┘
```

---

## 구현 계획

### Phase 1: 글로벌 주소 입력 컴포넌트

**파일**: `apps/web/components/common/GlobalAddressSearch.tsx`

```
- 카카오 주소 검색 API (팝업)
- 다필지 지원 (+ 필지 추가 버튼)
- 검색 결과 → PNU 자동 추출 (VWORLD PARCEL 지오코딩)
- 결과를 ProjectContextStore.siteAnalysis에 저장
```

**사용 위치**: 
- 대시보드 상단
- 입지분석 SiteInitiator
- 수지분석 AutoRecommendPanel
- 모든 주소 입력 필드를 이 컴포넌트로 통일

### Phase 2: 데이터 자동 수집 파이프라인

**주소 입력 즉시 자동 실행**:
1. VWORLD 지오코딩 → PNU 획득
2. `/zoning/comprehensive` 호출 (PNU 포함)
3. 응답을 ProjectLandData에 저장
4. 각 모듈의 useEffect가 ProjectLandData 변경 감지 → 자동 반영

### Phase 3: 모듈별 자동 반영

| 모듈 | 자동 반영 항목 | 구현 상태 |
|------|-------------|---------|
| 입지분석 | 용도지역, 건폐율, 용적률, 규제 | 부분 완료 |
| 법규검토 | 주소, 용도지역 | 완료 |
| 건축설계 | 대지면적, 용도지역 | 완료 |
| 수지분석 | 대지면적, 공시지가, 지역 | 완료 |
| BIM | 면적, 층수 | 완료 |
| 재무분석 | 주소, 면적, PNU | 완료 |
| ESG | esgData 연동 | 완료 |

### Phase 4: 구독자 등급별 데이터 접근

| 등급 | 접근 데이터 |
|------|----------|
| Free | 기본 용도지역 + 건폐율/용적률 |
| Basic | + 공시지가 + 토지이용계획 + 실거래가 |
| Pro | + 건축물대장 + 조례 상세 + 인허가 분석 |
| Enterprise | + AI 심층 분석 + 수지분석 + 보고서 생성 |

---

## 참고 문헌

- [NN/G EAS Framework — Simplifying Forms](https://www.nngroup.com/articles/eas-framework-simplify-forms/)
- [Progressive Disclosure (UXPin, 2026)](https://www.uxpin.com/studio/blog/what-is-progressive-disclosure/)
- [Chrome Autofill 폼 완료율 25% 향상 연구](https://www.zuko.io/blog/does-browser-autofill-affect-form-conversion-rate)
- [Form Input Design Best Practices (UXPin)](https://www.uxpin.com/studio/blog/form-input-design-best-practices/)
- [Progressive Disclosure in SaaS UX (Lollypop, 2025)](https://lollypop.design/blog/2025/may/progressive-disclosure/)
