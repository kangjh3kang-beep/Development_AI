# 분양앱 전 메뉴 UX 개선안 — 가독성·직관력·사용자편의성 (2026-07-23)

> 요청: "분양앱 각 메뉴별 인터페이스·워크플로우를 분석해 가독성·직관력·사용자편의성을 고려한 최적 개선안 수립"
> 근거: 전 21탭+홈 코드 라인단위 감사(architect 에이전트, READ-ONLY) + 2026-07-22 화면스펙 문서.
> 기준: 390px 모바일 · ①모바일적합성 ②워크플로우 단계수 ③직관력 ④가독성 ⑤일관성.

## 총평

- **셸은 모바일 우선으로 완성**(하단 5탭+전체메뉴 시트, 역할별 홈, 세대상태 SSOT, 오프라인 정직표기) — 유지.
- **실제 업무 패널 대부분은 데스크톱 폼/테이블 문법을 모바일에 그대로 노출** — 여기가 체감 품질의 병목.
- 하드 P0는 1건, 나머지는 **여러 메뉴에 반복되는 4개 공통 패턴** → 공용 컴포넌트 추출로 한 번에 해소(버그수정 정책 '공용화' 원칙 적용 대상).

## P0 — 즉시 (트랙 A, 0.5일)

**세대배치도 상세 드로어가 모바일 화면보다 넓음**
- `components/sales/Unit360Panel.tsx:107` — `fixed right-0 w-[420px]` 고정폭이 390px 뷰포트 초과, 우측 잘림+딤 배경 없음. **배치도에서 세대 탭→상태전이·계약체결 워크플로우가 모바일에서 사실상 불능.**
- 수정: 같은 레포의 정답 패턴 `CustomerCardDrawer.tsx:206-213`(`fixed inset-0 flex justify-end` + `bg-black/50` 백드롭 + `w-full max-w-md`)로 교체. ✕ 버튼 44px화.

## 공통 패턴 결함 Top 5 (공용화 대상 — 트랙 B·C·D)

| # | 패턴 | 대표 지점 | 해법(공용 추출) |
|---|------|-----------|----------------|
| 1 | **네이티브 alert/prompt/confirm 남용** — PWA가 순간 브라우저 크롬으로 전락 | DrawMode(12+)·OrgTree(11+→재설계로 축소중)·DeveloperProjection(7+)·DeskCheckin(5)·Subscription(2) | `useToast()` + `<ConfirmDialog>` (정답 참조: PaymentsPanel Reverse 모달·WorkLogPanel 토스트) |
| 2 | **원시 UUID 입력/표시 요구** — 현장 사용자는 UUID를 알 수 없음(전문가대행 원칙 위배) | WorkLogPanel:239(고객ID)·TerminationCertPanel:387(user_id)·Payments:100/Loan:91/Resale:104(계약ID 수기)·Loan:78/DutchPay:422(`slice(0,8)` 조각) | `<EntityPicker kind="customer\|contract\|member">` 검색선택 컴포넌트. 표시용 UUID 조각은 전부 라벨 해석으로 |
| 3 | **44px 미만 터치타깃** — 오탭 유발 | 핵심 6패널 버튼 `py-1.5`≈32px·삭제 `h-7 w-7`=28px·텍스트-온리 승인/반려(Resale:134) | `<Button>` 프리미티브(min-h 44 기본) — 셸 `sa-tab`은 이미 44px 준수 |
| 4 | **데스크톱 테이블/원시 enum 그대로 노출** | 언랩 테이블 5곳(Tax:89·Resale:123·Commission:144·OrgTree:176→재설계·Projection:444)·원시코드(OPEN/DRAWN·HUG·DRAFT…) | md 미만 카드리스트 `<DataList>` 분기 + 상태 라벨·색 SSOT를 `unitStatus.ts` 방식으로 도메인별 확장 |
| 5 | **raw Tailwind 의미색 156곳이 토큰 SSOT 우회** — 라이트 테마 WCAG 대비 실패 | `-300/-400` 계열(CrmPanel·WorkLog·Integrity 등). 기존 `sa-chip`/`--status-*` 토큰(양 테마 보장)을 미사용 | `sa-chip`/토큰 일괄 치환(codemod 가능)·중복 포맷터(`won` 등)/폼상수(`IN/BTN/fcls`) 단일화 |

## 메뉴별 판정 요약

- **P0**: units(세대배치도 — Unit360Panel 드로어).
- **P1**: customers(등급칩 raw색·버튼 32px), worklog(고객 UUID 입력), pricing(28px 삭제버튼·원시 가중치 소수), subscription(alert 통지·원시 상태코드), payments(8열 테이블·계약ID 수기), loan(UUID 조각·원시코드), resale(언랩 테이블·텍스트 승인/반려), tax(언랩 테이블·원시코드), commission(언랩 테이블·원시 요율), desk(alert 통지), projection(confirm 남용·언랩 테이블), cert(프리랜서 UUID 입력).
- **P2**: integrity(다크튜닝 색의 라이트 대비).
- **양호(유지)**: home, social(채팅 UI 적절), market, profile, referral, **staff(모범 — sa-seg·토큰·래핑 테이블: 다른 패널의 참조 기준)**.
- **org(조직도)**: 별도 트랙에서 재설계 진행 중(2026-07-23) — 내조직 카드(/org/context SSOT)·아코디언 트리·행 액션시트·직속 지정 파이프라인 게이팅·prompt 제거.

## 실행 로드맵

1. **트랙 A(P0, 0.5일)**: Unit360Panel 반응형 드로어 교체. 1파일·정답 참조 존재·위험 낮음.
2. **트랙 B(P1 프리미티브, 2~3일)**: `components/common/`에 ①Button(44px) ②Input/Select(IN/fcls 흡수) ③useToast+ConfirmDialog ④EntityPicker 추출 → 결함 #1·#2·#3 전역 치환.
3. **트랙 C(P1 목록·상태, 2일)**: 도메인별 상태 라벨·색 SSOT 확장(payment/loan/resale/tax/subscription) + `<DataList>` md 분기로 언랩 5곳+밀집 3곳 카드화.
4. **트랙 D(P2 청소, 1일)**: raw 의미색 156곳 토큰 치환·포맷터/폼상수 단일화.

순서 주의: **org 재설계(진행 중)가 트랙 B 프리미티브를 소비하도록** B 완료 후 org의 잔여 confirm 2곳(해제·시드)을 ConfirmDialog로 마감.

## 워크플로우 개선(단계 수) 관점 핵심

- 고객 등록(2필드 1탭)·현장 체크인(서명 캔버스)은 이미 최단 경로 — 유지.
- **수납 기록**: 계약 선택이 UUID 수기 폴백 → EntityPicker 도입 시 3단계→2단계.
- **조직원 추가**: (재설계 반영) 상위 셀렉트+직급 셀렉트+이름 3필드 → 노드 탭→"하위 추가"→직급 칩(허용만)+이름 = 인지 부하 절반.
- **해촉증명 발급**: UUID 입력 불능 상태 → 멤버 선택기로 실사용 가능화.
