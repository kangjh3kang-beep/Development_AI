// v377: ★링크 클릭 이동 불가(플랫폼 전역) 근본수정 — RSC(Next App Router 클라 네비게이션
//        데이터)를 stale-while-revalidate 로 캐시해, 옛 빌드의 RSC(죽은 청크해시 참조)를
//        Link 클릭 시 반환 → 클라 네비게이션 침묵 실패하던 근본원인. RSC 는 콘텐츠해시가
//        없어(같은 라우트 URL·빌드마다 다른 내용) 절대 캐시하면 안 되므로 network-only 분기.
//        버전 범프로 v376 캐시(오염된 stale RSC 포함) 일괄 삭제.
// v393: use_llm 공용 토글(UseLlmToggle)·VerificationBadge ledgerHash 조인키 배선 반영(구캐시 일괄 삭제).
// v396: wave3 리팩토링(dead code 삭제·web 15소스).
// v397: 다필지 통합 통로 배선(파이프라인·페르소나·인허가 parcels + 면적 SSOT effectiveLandAreaSqm) 반영.
// v399: 시장분석 워크스페이스 체계화(시니어 통합 인사이트 카드·타겟 프로파일·6그룹 스토리라인·
//        보고서 다운로드 단일화·표↔차트 이원화 제거) 반영 — 구캐시 일괄 삭제.
// v401: region-frontend-fix.
// v402: 인구이동망 권역도(순이동 발산 코로플레스·MigrationRegionMap).
// v404: 사업성 개략수지 워크플로우(RoughScenarioPanel — 프로젝트 선택/수정 + 개략수지 생성 +
//        2차 실데이터 overrides 수정 + 월별 DCF) 반영 — 구캐시 일괄 삭제.
// v407: 투자분석 단일 세로 워크플로우 재배치(개략수지 base→투자수익성 요약→리스크 시뮬 + 보조
//        CashflowDcfPanel 접이식 강등·무목업 자동 재프리필/폴백 제거) 반영 — 구캐시 일괄 삭제.
// v410: 사업성·비용 얇은 L2 그룹 해체 → 투자 수익성·적산·공사비 관리를 프로젝트 섹션 직속 승격
//        (적산관리 발견성 개선). 개칭·승격된 nav가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v411: 적산·공사비 관리에 '예산-실적 집행' 탭 신설(§13 BudgetExecutionPanel — 기지출/미지출·집행률
//        실시간 추적). 신규 컴포넌트·탭이 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v413: 디자인시스템 v2 P0 기반정지(토큰 SSOT 단일화·Tailwind dark variant 정합·테마 부트스트랩·
//        셀프호스팅 폰트 실로드). 새 CSS/폰트가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v416: 사통맵 레이어 좌표앵커 근본수정(#271) — 공용앵커 resolveSelectionAnchor·경매401 인라인 안내.
//        지도 레이어 신코드가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v417: 회원 계정 시스템(#280 — forgot/reset-password·verify-email·account 신규 라우트) 반영.
//        신규 인증 화면·플로우가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v418: 수지 Excel 실배선·몬테카를로 백엔드 실엔진 교체(#294)+AI 라우트 nodejs 런타임(#295) 반영.
//        교체된 수지 위젯·라우트가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v419: 설계 스튜디오 임베드 레이아웃 컨테이너 쿼리 전환(#306) — 세로텍스트 붕괴·버튼잘림·
//        빈상태·부지지표 3중중복 봉합. 재배치된 레이아웃이 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v420: 설계 스튜디오 파이프라인 흐름 IA(#310) — dock 스테퍼↔중앙 L1→L5 흐름 시각화·
//        다음 단계 CTA·MetricBar 역할분리(상단=식별/하단=산출). 재배치가 stale 캐시에 가려지지 않도록 구캐시 삭제.
// v421: 설계 스튜디오 가독성·SSOT 5결함(#316 — AI의견 마크다운 렌더+전역 7표면·KPI 근거배지·
//        용도지역 무날조 기록) + IA 전면 재설계(#323 — 단일 스크롤·근거한도 패널·준비 대시보드·
//        레일 단일화·헤더오프셋 토큰). 대규모 레이아웃 재배치가 stale 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v422: 사통맵 라벨 시스템 공용화(#329 — bindSatongLabel+무레이어 .satong-tooltip으로 이중 흰박스 제거·
//        전역 라벨버짓/줌LOD·z계약 SSOT·칩/범례 코너도크 병합) + 보안(VWorld 키 하드코딩 제거·WMS 프록시
//        일원화). 새 CSS/프록시 라우트가 stale 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v423: 규제분석 워크플로우 정합(#333 — 자연녹지 실효FAR 80% SSOT 소비·법규링크 칩·필지구획도
//        다필지 parity·전문가패널 정직 사유) + 사통맵 선택 SSOT(#332 — healParcelPnu 키이중성 근치·
//        노후도 정직 세분화·레일 아이콘). 규제/사통맵 화면 재배선이 stale 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v424: 설계엔진 실효FAR SSOT 승격(#339 — DAG design 노드 ordinance 주입·far_basis/far_reliable
//        전파·rule_trace 근거 정직화·캐시 핑거프린트). 설계 근거표기 변경이 stale 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v425: 생성허브 6산출물 100%(#338 — 법규검토서/시장분양/설계검토서 등 문서 산출물 배선·완결자산
//        표면화·카드 정직화·가짜 단계진행 제거). 신규 다운로드 카드가 stale 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v426: 생성허브 후속로드맵 6건(#348 — 시장 렌더 ReportModel 일원화·감사 잡 전환·심의 게이트 기본off·
//        수지 차트 3종·제출번들 감사면·적산 CTA + registry 잡 IDOR 봉합). 신규 차트/잡 폴링 UI가
//        stale 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v427: 사통맵 지적타일 근본수정(#347 — WMS 1.3.0) + 인터랙션 P0(#351 — 클릭 단일팝오버·거리재기·
//        라벨 줌롤업·범례 컴팩트·레일 반응형·버블링 차단). 지적 WMS 요청 파라미터와 지도 UI가
//        stale 캐시로 남으면 수정 전 오류가 재현되므로 구캐시 일괄 삭제.
// v428: 사통맵 WS-C 필지 상세 패널(#356 — 클릭 통합정보+산출물 퍼널+좌표복사) + WS-B2 관리자키
//        폴백(#354 — web 키부재 시 api 타일 프록시 중계). 셸 UI·프록시 폴백이 stale 캐시로
//        남지 않도록 구캐시 일괄 삭제.
// v429: 사통맵 보강 4종(#358 — 로드뷰·면적재기·타일 자가진단·GeoJSON 내보내기) + 완성도100
//        캠페인(#359). 팝오버/칩 UI와 진단 프로브가 stale 캐시로 남지 않도록 구캐시 일괄 삭제.
// v430: 사통맵 정보 상시화·겹침 해소(#361 — 라벨 버짓 96/64/24·실거래 가격 pill·도크 가로
//        1줄·저줌 확대 안내·won() 자리올림 봉합). 라벨/칩 UI가 stale 캐시로 남지 않도록 삭제.
// v431: jootek 패리티 3종+키오류 페일오버(#364 — 전국 지적편집도·평당가 토글·베이스맵
//        스위처·INCORRECT_KEY 자동 재중계·자동진단·도크 겹침 해소). 프록시/칩 UI stale 방지 삭제.
// v432: 지적타일 최종 근본원인 봉합 — VWorld WMS 레이어명 오기 정정(lp_pa_cbnd_bubun/bonbun
//        소문자 정본·대소문자 정규화). 구캐시의 잘못된 레이어명 요청 잔존 방지 삭제.
// v433: VWorld A군 3종(#368 — 위성뷰 지적 선 스타일·측정 rail·KML 내보내기). UI stale 방지 삭제.
// v434: 배경지도 전역 미표시 근본봉합(#370 — VWorld tiletype 오기 gray→white 정본화 + WMTS
//        OWS ExceptionReport 파서 갭). ★구캐시 삭제 필수 — 구 번들은 존재하지 않는 tiletype
//        "gray"를 계속 요청해 회색 베이스맵에서 배경지도가 통째로 미표시된다(프록시가 레거시
//        별칭으로 흡수하지만, 캐시된 구 JS 자체를 걷어내야 완전 복구).
// v435: 주소검색 공용화(#373) 반영.
// v436: 디자인 정합 3종 라이브 반영 — #375 라운드 스케일 코드→DESIGN.md(B4 4단 수렴: 유틸
//        2,168곳 정의 1곳 수렴·임의값 178곳 토큰화 — 2xl 16→12px 등 전역 시각변경) ·
//        #376 사통맵 rail 좌중앙(줌 중첩 근본해소)+클릭팝업 위계 재작성(blur24·좌표 mono) ·
//        #378 베이스맵 스와치 실물 타일. ★구캐시 삭제 필수 — 구 CSS/JS가 남으면 라운드가
//        화면별로 섞여(12px vs 16px) 정합이 반쪽이 된다.
// v437: 사통맵 하단 도크 단일화(#380 — 스위처 섬 흡수·예약값 제거·코너 슬롯 레지스트리).
//        재배치된 도크 UI가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v438: 규제 오버레이 5종(#382 — zoning 플레이스홀더 잠금해제: 개발행위허가제한·지구단위·
//        상수원보호·교육환경보호·고도지구 + 지적선 z5 승격). 구캐시의 구 화이트리스트
//        프록시 JS가 남으면 신규 레이어 요청이 400으로 거부되므로 일괄 삭제 필수.
// v440: WS-D① 개발여력 히트맵(#387 — 실효·현황 용적률 표면화+선택필지 코로플레스·
//        renderable 불변식). 구캐시 JS는 capacity 레이어를 몰라 레일에 미노출 — 삭제 필수.
// v442: 사통맵 상세패널 I7 규제요약(#389 — 실효 FAR/BCR·현황·개발여력 인라인). 신규
//        인라인 규제 요약 UI가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
//        (v441=#390 분석 히스토리 뒤에 #389 프론트 머지됐으나 소유 세션 sw 누락 → 통합자 대행)
// v447: 네비 적산·시공비 최상위 섹션 승격(#403 — cost-mgmt 독립 섹션) + 상단 드롭다운 3개 절단
//        (slice 0,3) 봉합·전 섹션 스크롤(max-h+overflow). 재배치된 상단 네비/드롭다운이 stale
//        app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제(구 번들은 여전히 섹션당 3개만 렌더).
// v448: 다필지 파이프라인 절단 3건 근본수정(#405 — permits 구획도/등기/시뮬 12→1 등 분석·렌더
//        동일 SSOT 공용화). 구 번들이 절단된 목록을 렌더하지 않도록 구캐시 일괄 삭제.
// v449: 실효용적률 설계 전파 봉합(#408 — 설계엔진 실효FAR 리졸버 통일·우선순위 역전 수정·
//        정직 배지). 재배선된 설계 실효FAR 표기가 stale app-shell 캐시에 가려지지 않도록
//        구캐시 일괄 삭제.
// v450: 시니어 규제자문 풍성화(#412 — IRAC 법령근거 판단체인·실패모드·체크리스트 표면화).
//        확장된 SeniorVerdictCard가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v451: 조례 폴백 confirmed 승격 정직화(#422 — SSOT 게이트·잔존 서피스 봉합·globals.css +
//        SiteAnalysisDetail). 전역 CSS·부지분석 상세 재배선이 stale 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v452: 설계 해설 raw JSON 근원 차단·zone 초기값 경합 봉합(#428 — CadBimIntegrationPanel
//        정직 폴백·stale 배지·재생성 in-flight 가드, GenerativeDesignPanel lazy init).
//        구 번들이 raw JSON 해설·2R 오호출을 재생하지 않도록 구캐시 일괄 삭제.
// v453: 분양앱 SSOT 라벨 봉합(#431 — 세대 상태 unitStatus.ts·조직 직급 roleConfig 일원화).
//        ★구 번들의 실시간보드가 취소세대를 분양가능(초록)으로 위장하던 정합성 결함을 봉합했으므로
//        구캐시를 반드시 일괄 삭제한다(stale 번들이 위장 렌더를 재생하지 않도록).
// v454: 분양 현장앱 역할별 홈(#436 — FieldHome 기본 랜딩 대시보드·무목업 실데이터).
//        신설된 홈 셸/기본 진입 탭이 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v455: 현장앱 모바일 하단 5탭+전체메뉴 시트(#440 — FieldNav·IA SSOT·상단탭바 모바일 숨김).
//        구 번들의 모바일 21탭 가로스크롤이 재생되지 않도록 구캐시 일괄 삭제.
// v456: 현장앱 홈 히어로 네이비 카드 시각충실(#449 — 대형 분양률·진행바·3스탯).
// v457: 조직도 직속 지정 파이프라인+모바일 재설계(#452 — 내조직 카드·아코디언·행 액션시트·
//        배정 시트). 재설계된 OrgTree 가 stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
//        구 번들의 흰 히어로가 재생되지 않도록 구캐시 일괄 삭제.
// v458: 분양앱 로그인 복귀+앱 정체성 분리(#456 — ?next= 복귀 배선·현장앱 전용 manifest
//        start_url=/ko/sales/sites·목록페이지 fieldapp 이동). 로그인/가드/manifest 변경이
//        stale app-shell 캐시에 가려지지 않도록 구캐시 일괄 삭제.
// v460: 사통맵 필지선택 누수 봉합(#466 P0 — 연결 대상 전환 시 선택 잔류로 오염 프로젝트
//        생성·과금 발생) + design-audit 화면배관 봉합(#464 — AuditReportView S4/S7 형상·
//        permit 표면화). 과금에 직결되는 P0 수정이 stale app-shell 캐시에 가려지면
//        기존 사용자에게 수정이 도달하지 않으므로 구캐시 일괄 삭제.
// v461: design-audit 입력배선 복구(#468 — 조례 resolver 부활·규제구역 3분기 센티널·무음
//        폴백 근절). 프론트 변경 4종(AuditReportView data_gaps 렌더, DesignStudio·
//        CadBimIntegrationPanel 실효 FAR/BCR 배선, CostAndQuantityDashboard 15층 하드코딩
//        제거, kr-building-regulations 250% 날조 폴백 제거)이 stale 캐시에 가려지면
//        과대낙관 수치가 계속 표시되므로 구캐시 일괄 삭제.
// v462: 실거래 유형 다중 표시(#470 — 백엔드 10종 수집분 중 프론트가 apt만 쓰던 것을
//        6종 동시 렌더로. SatongMultiMap 마켓 이펙트·SatongMapShell transactions 컨트롤·
//        satong-map-layers 색상 SSOT·범례·절단 고지). 사용자 버그리포트("종류별 실거래를
//        지도에 표기 안 함") 대응이라 stale 캐시에 가려지면 여전히 아파트만 보이므로 삭제.
// v464: IA 재배치 UX 트랙B(#477 — 지도 상단화·집계 SSOT sticky·착지 지도셸 접기·
//        h1 중복 제거). 정보구조 재배치가 stale app-shell 캐시에 가려지면 기존 사용자에게
//        옛 레이아웃이 계속 노출되므로 구캐시 일괄 삭제.
// v465: 컨트롤·피드백 통합 UX 트랙C(#479 — 레일 확장·칩 비인터랙티브·useToast 호스트·
//        진행표시·소요문구·검색 combobox + 공유 UI toast). 인터랙션/피드백 배선이 stale
//        캐시에 가려지면 기존 사용자에게 옛 컨트롤이 계속 노출되므로 구캐시 일괄 삭제.
// v466: 등기 권리분석 전면 실패 복구(#482 — get_one 계약 파열 봉합·물건 선택 SSOT).
//        RegistryBulkButton·RegistryAnalysisWorkspaceClient 의 선택/호출 배선이 stale
//        캐시에 가려지면 기존 사용자에게 '분석 전면 실패'가 계속 재현되므로 구캐시 일괄 삭제.
// v468: 타일 상태 래치 오판 봉합(#499 — 타일 1개 실패로 '전체 실패' 배너가 뜨던 것을 비율
//        판정으로 교정·source-invariant). 배너 오판 로직이 stale 캐시에 가려지면 기존
//        사용자에게 거짓 전체실패 경고가 계속 표시되므로 구캐시 일괄 삭제.
// v469: 지배 제약 한 줄 + 높이 상한(#502 W1 — "무엇이 발목인가"를 한 줄로).
//        DominantConstraintBanner 신규 컴포넌트·SatongMapShell/satong-map-selection/
//        satong-map-layers/projectSync 배선이 stale app-shell 캐시에 가려지면 신규 배너가
//        기존 사용자에게 아예 노출되지 않으므로 구캐시 일괄 삭제.
// v470: 필지 경사도 온디맨드 표시(#503 W2 — 시공사·디벨로퍼 토공 판단). ParcelSlopeSection
//        신규 컴포넌트·SatongMapShell/satong-map-selection/projectSync 배선이 stale
//        app-shell 캐시에 가려지면 신규 섹션이 기존 사용자에게 노출되지 않으므로 구캐시 일괄 삭제.
// v471: 배치 미리보기 지도 오버레이(#506 W3 — 설계사 "어떻게 몇 동을 앉히나"). ParcelLayoutSection
//        신규 컴포넌트·SatongMultiMap layoutOverlay·satong-layout-overlay/site-layout 신설·
//        SatongMapShell 조회배선이 stale app-shell 캐시에 가려지면 신규 섹션이 기존 사용자에게
//        아예 노출되지 않으므로 구캐시 일괄 삭제.
// v472: 2열 레일 hover 전환 의도 지연(#510 — 사용자 지적 "팝오버로 가며 스치는 아이콘이
//        창을 뺏는다"). SatongMapShell 상호작용 로직만 바뀌어 **신규 파일이 없으므로**,
//        stale app-shell 캐시가 옛 번들을 계속 내주면 사용자는 고쳐진 동작을 영영 못 본다
//        (신규 컴포넌트 노출 문제가 아니라 **행위 교정**이라 오히려 캐시 무효화가 필수).
// v473: 매스 시드 인계(#512 W4 — 설계사 "지도에서 앉힌 대로 CAD가 시작"). 지도 배치 섹션의
//        "이 안으로 설계 시작" CTA·lib/satong-mass-seed 신설·설계 스튜디오의 "지도에서 고른 안"
//        카드와 미적용 고지가 stale app-shell 캐시에 가려지면 **신규 진입점이 아예 노출되지
//        않는다**. 게다가 인계 실패 시 사용자에게 사유를 알리는 배너도 함께 묻힌다.
// v474: 정북 일조 이격 밴드(#514 W3-b — 계획서 W3의 빠진 절반). 지도에 앰버 금지 띠가 새로
//        그려지고, 배치 대안 자체가 정북 이격을 반영해 **바뀐다**(밴드를 배치 제약으로 되먹임).
//        stale app-shell이면 사용자는 옛 배치(정북 미반영)를 계속 보게 되므로 반드시 무효화한다.
// v475: 종합분석 단계분할·변경원인 카드(#517) — 다른 세션 반영분(#518).
// v476: 지도 정보표시 근본수정(#516 W1 — 사용자 지적 "실거래가 안 나오고 인터페이스 효율이
//        떨어진다"). ★신규 UI 노출이 아니라 **계산 결과가 달라지는** 변경이라 캐시 무효화가
//        특히 중요하다: AI 시세가 좌표 미확인 거래를 더 이상 쓰지 않고(값이 바뀌거나 사라진다),
//        거리 집계에서 "1000m 날조"가 제거돼 반경 버킷 수치가 바뀌며, 규제 오버레이가
//        4레이어 청크로 부설된다. stale 번들이면 사용자는 옛 계산을 계속 본다.
//        ★v475는 동시 진행 세션(#518)이 선점 — 번호 충돌을 피해 v476으로 올린다.
// v477: AI 해석 비동기 잡(제출→폴링) 전환(#520 W2-e·#521). ★이력 주석이 누락돼 있어 뒤늦게
//        채운다 — #521은 제목이 "v476"인데 실제 상수는 v477로 올라갔다(동시 진행 세션이 v476을
//        선점한 탓). 번호는 **제목이 아니라 상수를 보고** 이어야 한다.
// v478: 자가검증(field_audit) 결과 화면 표면화 + AI 인사이트 카드 2단계 전환(#522).
// v479: 주변 실거래 표본 정직화(W1-b) — 위치 미확인·개략(동 단위) 그룹을 집계·라벨에서
//        분리. 시장분석 헤드라인/유형별 평균가·대화형 시장분석 통계·실거래 유형 칩 건수가
//        바뀌므로 앱셸 캐시를 무효화한다. ★채번 전 origin/main 재확인함(v478 확정).
//        ★기능 PR 과 같은 사이클에 묶었다 — 별도 sw PR 로 올리면 기능이 이미 배포된 뒤
//        중복 버스트가 된다(통합자 2026-08-02 안내).
//        캐시 무효화가 특히 중요한 이유 두 가지.
//        ① **신규 표시면이 생긴다** — 보고서에 "플랫폼 자체 점검 결과" 카드와 섹션별 방법론
//           각주가 처음 붙는다. stale 셸이면 사용자는 신빙성 고지가 **아예 없는** 화면을 계속
//           보는데, 고지 부재는 곧 "문제 없음"으로 읽히므로 미노출 자체가 오해를 만든다.
//        ② **요청 형태가 바뀐다** — AI 인사이트 카드가 종합분석을 1단계(해석 제외)로 부르고
//           해석은 별도 잡으로 폴링한다. 옛 번들은 여전히 해석까지 한 번에 요청해 엣지 컷오프에
//           걸리므로, 캐시를 무효화하지 않으면 그 카드는 **계속 실패한 채로 남는다**.
// v479: 위치 미확인 표본 "반경 N" 라벨 결함 봉합(#527) — 다른 세션 반영분.
// v480: 개발자용 코드 대신 사람 말 + 해결 절차 표면화(#528 W4-1).
//        ① **표시 문구가 바뀐다** — 특이부지 배지가 `NEEDS_OFFICIAL_SURVEY` 원문 대신
//           "공식 산림조사 필요(참고안 — 확정 아님)"로 나온다. stale 셸이면 사용자는 계속
//           개발자용 코드를 보게 되고, 이 변경의 목적 자체가 달성되지 않는다.
//        ② **신규 표시면이 생긴다** — "이 제약을 푸는 방법"(해결 절차·선행 요건·대안)이 처음
//           붙는다. 백엔드는 이 값을 이미 내려주고 있었는데 화면 소비처가 0건이었다.
//           옛 번들은 그 필드를 여전히 무시하므로 캐시를 비워야 실제로 보인다.
//        ★채번 주의: 직전 상수가 v478이 아니라 **v479**였다(#527이 선점). PR 제목이 아니라
//          `origin/main`의 실제 상수를 보고 이어야 한다 — 이번에도 그렇게 확인했다.
// v481: 비율 표기 정합(#530) + 다필지 매트릭스 게이트 라벨 SSOT 수렴(#532).
//        ① **표시 숫자가 바뀐다** — 법정/조례/실효·구조상한·§1-B 상한이 소수 1자리 고정으로
//           나온다("80%" → "80.0%"). 정수 반올림이면 실효 79.6%가 법정 80%와 같아 보여
//           보고서가 설명하려는 격차가 사라지므로, 옛 번들이 남으면 그 서사가 깨진 채 보인다.
//        ② **표시 문구가 바뀐다** — 다필지 매트릭스 게이트 배지가 원시 코드 대신 공용 라벨을
//           쓰고, 미분석 필지를 "가능"이 아니라 "판정 불가(미분석)"로 적는다. stale 셸이면
//           미분석 필지가 계속 '가능'으로 보이는데, 이건 과대 안심이라 특히 위험하다.
//        ★채번: 직전 상수 v480이 **이미 라이브에 배포된 상태**라 같은 번호로는 캐시가 비지
//          않는다. 배포된 값을 기준으로 올려야 한다(main 값이 아니라 라이브 값 기준).
const CACHE_NAME = "propai-v481-ratio-and-matrix";
const OFFLINE_URL = "/offline";

// ★API 캐시 정합(보안·정확성): 인증/실시간/머니패스/현장세션 응답은 절대 캐시하지 않는다.
//   네트워크 실패 시에도 옛 데이터를 '살아있는 값'처럼 돌려주면 오결제·권한혼동·옛 잔액
//   표시 등 위험이 있어, 이런 경로는 stale 캐시 폴백 없이 정직한 오프라인(503)만 반환한다.
//   (셸/정적 자산만 캐시 — API 는 기본 network-first, 민감경로는 no-store.)
const API_NO_STORE_PATTERNS = [
  /\/auth\b/,        // 로그인/토큰/세션
  /\/login\b/,
  /\/logout\b/,
  /\/token\b/,
  /\/secrets?\b/,    // 관리자 시크릿
  /\/sales(\b|-|\/)/, // 현장앱 전체(역할·세대선점·수납·수수료 등 실시간/머니패스)
                      //  ★하이픈 변형도 포함: /sales/ 뿐 아니라 /api/v1/sales-summary 같은 머니패스 롤업도 no-store.
  /\/billing\b/,     // 과금
  /\/payments?\b/,   // 수납·결제
  /\/commission\b/,  // 수수료
  /\/balance\b/,     // 잔액
  /\/me\b/,          // 내 계정/권한
];

// 요청 URL 이 민감(no-store) API 경로인지 판정.
function isNoStoreApi(pathname) {
  return API_NO_STORE_PATTERNS.some((re) => re.test(pathname));
}
const APP_SHELL_ASSETS = [
  "/",
  "/ko",
  "/en",
  "/zh-CN",
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/icon.svg",
  "/icon-maskable.svg",
  "/apple-touch-icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL_ASSETS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
    return;
  }

  if (event.data?.type === "SHOW_NOTIFICATION") {
    const payload = event.data.payload ?? {};

    event.waitUntil(
      self.registration.showNotification(payload.title ?? "PropAI", {
        body: payload.body ?? "Offline workspace is ready.",
        tag: payload.tag ?? "propai-pwa-runtime",
        data: {
          url: payload.url ?? "/ko/inspection",
        },
      }),
    );
  }
});

self.addEventListener("push", (event) => {
  const payload = event.data ? event.data.json() : {};
  const title = payload.title ?? "PropAI";

  event.waitUntil(
    self.registration.showNotification(title, {
      body: payload.body ?? "New field operation update is available.",
      tag: payload.tag ?? "propai-web-push",
      data: {
        url: payload.url ?? "/ko",
      },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  event.waitUntil(clients.openWindow(event.notification.data?.url ?? "/ko"));
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);

  // http(s)만 처리 — chrome-extension://, ws:// 등은 SW 캐시 대상 아님(put 에러 방지)
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(navigationNetworkFirst(request));
    return;
  }

  // ★RSC(React Server Component) — Next.js App Router 의 클라이언트 네비게이션(Link 클릭·
  //   prefetch)이 라우트 URL 로 보내는 데이터 요청. mode 가 'navigate' 가 아니라 아래 자산
  //   catch-all(staleWhileRevalidate)로 빠져 '옛 빌드의 RSC'가 캐시에서 반환되면, 그 RSC 가
  //   참조하는 청크 해시가 새 배포로 사라져 클라 네비게이션이 침묵 실패(=링크 클릭해도 이동
  //   안 함)한다. RSC 는 콘텐츠해시가 없는 '빌드별' 페이로드이므로 절대 캐시/stale 금지 →
  //   항상 네트워크(network-only). 헤더(RSC/Next-Router-*)·?_rsc·Accept 로 판별.
  if (isRscRequest(request, url)) {
    event.respondWith(networkOnlyNoStore(request));
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    // 민감 API(인증/현장/머니패스)는 캐시 금지 + stale 폴백 금지(정직한 오프라인 503).
    if (isNoStoreApi(url.pathname)) {
      event.respondWith(apiNoStore(request));
      return;
    }
    event.respondWith(apiNetworkFirst(request));
    return;
  }

  if (request.destination === "image") {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // JS/CSS/폰트/RSC 등 자산: stale-while-revalidate(즉시 표시 + 백그라운드 갱신).
  // ★cacheFirst(영구캐시)였던 것을 SWR로 변경 — 새 배포가 다음 로드에 자동 반영(자가치유).
  // 콘텐츠해시 청크는 캐시미스=항상 최신, 비해시 자산도 한 번 더 로드 시 갱신됨.
  event.respondWith(staleWhileRevalidate(request));
});

// 응답을 안전하게 캐시 — 클론을 즉시 떠서 본문 중복사용/스킴미지원 에러를 흡수.
function safePut(request, response) {
  try {
    if (!response || !response.ok || response.type === "opaque") return;
    const copy = response.clone();
    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
  } catch {
    /* clone/put 실패는 무해하게 무시 */
  }
}

// RSC 요청 판별 — Next.js App Router 는 클라 네비게이션/prefetch 시 라우트 URL 로 RSC
// 페이로드를 요청한다. 버전별로 시그니처가 조금씩 다르므로 여러 신호를 OR 로 넓게 잡는다:
//  - 헤더 RSC:1, Next-Router-Prefetch:1, Next-Router-State-Tree(존재)
//  - 쿼리 ?_rsc=...
//  - Accept 에 text/x-component
// (false-negative 는 stale 위험 잔존, false-positive 는 단지 네트워크 강제라 안전측 = 넓게)
function isRscRequest(request, url) {
  try {
    const h = request.headers;
    if (h.get("RSC") === "1") return true;
    if (h.get("Next-Router-Prefetch") === "1") return true;
    if (h.get("Next-Router-State-Tree")) return true;
    if (url.searchParams.has("_rsc")) return true;
    const accept = h.get("Accept") || "";
    if (accept.includes("text/x-component")) return true;
  } catch {
    /* 헤더 접근 실패는 무해 — 캐시 안 하는 방향이 안전 */
  }
  return false;
}

// network-only(무캐시) — RSC 등 '빌드별' 동적 페이로드용. 캐시에 넣지도, 캐시에서
// 꺼내지도 않는다. 실패 시 정직한 네트워크 오류(라우터가 하드네비 폴백/재시도).
async function networkOnlyNoStore(request) {
  try {
    return await fetch(request);
  } catch {
    return Response.error();
  }
}

async function navigationNetworkFirst(request) {
  try {
    // ★HTML 은 캐시에 저장하지 않는다 — 오프라인 폴백은 OFFLINE_URL 만 쓰므로 페이지 HTML
    //   put 은 사용처 없는 스테일 셸 축적이었다(배포 후 죽은 청크를 참조하는 구 HTML 이
    //   Cache Storage 에 남아, 향후 매칭 로직 변화 시 백지 사고의 원료가 됨). 항상 네트워크.
    return await fetch(request);
  } catch {
    return (await caches.match(OFFLINE_URL)) || Response.error();
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }

  try {
    const response = await fetch(request);
    safePut(request, response);
    return response;
  } catch {
    return (await caches.match(OFFLINE_URL)) || Response.error();
  }
}

// 민감 API(인증/현장/머니패스): 항상 네트워크. 응답을 캐시하지 않고(no-store),
// 네트워크 실패 시 옛 데이터를 돌려주지 않고 정직한 오프라인(503)만 반환한다.
// → 옛 잔액/권한/세대상태를 '살아있는 값'으로 오인하게 하는 위험을 원천 차단.
async function apiNoStore(request) {
  try {
    return await fetch(request);
  } catch {
    return new Response(
      JSON.stringify({ error: "오프라인 상태입니다", offline: true, stale: false }),
      {
        status: 503,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      },
    );
  }
}

async function apiNetworkFirst(request) {
  try {
    const response = await fetch(request);
    safePut(request, response);
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) {
      // 오프라인 캐시 폴백 — '옛 데이터'임을 헤더로 정직하게 표기한다(silent 위장 금지).
      // 응답 본문은 보존하되 X-PropAI-Stale 헤더로 신선도를 알린다.
      // ★향후 network-first 화면 stale 배지용 hook(현재 소비처 없음=backlog). 무해한 응답헤더라
      //   부착은 유지한다(나중에 그런 화면이 생기면 api-client 에서 이 헤더만 다시 감지하면 됨).
      const headers = new Headers(cached.headers);
      headers.set("X-PropAI-Stale", "1");
      return new Response(cached.body, {
        status: cached.status,
        statusText: cached.statusText,
        headers,
      });
    }

    return new Response(
      JSON.stringify({ error: "오프라인 상태입니다", offline: true, stale: false }),
      {
        status: 503,
        headers: { "Content-Type": "application/json; charset=utf-8" },
      },
    );
  }
}

async function staleWhileRevalidate(request) {
  const cached = await caches.match(request);

  const fetchPromise = fetch(request)
    .then((response) => {
      safePut(request, response);
      return response;
    })
    // ★버그픽스: 캐시가 없는 상태에서 네트워크까지 실패하면 이전 코드는 undefined 를
    //   반환해 respondWith(undefined) 로 요청이 '침묵사'했다(CSS/JS 로드 실패가 원인
    //   불명 백지로 위장). 캐시가 있으면 그것을, 없으면 정직한 네트워크 오류를 반환해
    //   브라우저가 실패를 정상 보고(재시도/개발자도구 관측 가능)하게 한다.
    .catch(() => cached || Response.error());

  return cached || fetchPromise;
}
