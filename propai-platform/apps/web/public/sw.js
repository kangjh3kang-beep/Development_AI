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
// v481: 비율 표기 정직화(#530 W4-2) + 다필지 매트릭스 게이트 배지 수렴(#532 W4 R1 MED).
//        ① 비율에서 **0과 '미확보'를 구분**하고 반올림이 격차를 지우지 않게 한다
//           (formatters.ts·ComprehensiveAnalysisPanel) — 옛 번들은 둘을 같은 "0%"로 그린다.
//        ② 다필지 속성 매트릭스의 게이트 배지가 중복 라벨맵 2호로 수렴(MultiParcelAttributeMatrix).
//        표시 로직이 바뀌는 변경이라 stale app-shell 캐시가 남으면 옛 표기가 그대로 보인다.
//        ★채번: origin/main 실제 상수가 v480이라 v481로 이었다(제목 아닌 상수 기준·직전 관례 유지).
// v482: 프로젝트 전환 시 옛 분석이 화면에 남던 결함 봉합(#537 — 대상 판정 키를 프로젝트+주소로).
//        useAnalysisTargetGuard/analysis-target 신설 + ComprehensiveAnalysisPanel 배선.
//        ★이 수정은 **옛 화면 상태를 버리게** 만드는 것이라, 정작 stale app-shell 캐시가
//        남으면 옛 번들이 그대로 옛 분석을 붙들고 있어 수정이 무력화된다(캐시가 캐시 결함을 가림).
//        ★채번: origin/main 실제 상수가 v481 이라 v482. PR 생성 전 보드에 v482 claim 선점
//          (v463·v481 채번 충돌 재발 방지 — 통합자 신규 관행).
// v483: §1-B 비율 표기 정직성(#541) — 원시 float 병존 제거·**0과 미확보를 같은 기호로
//        쓰던 것** 봉합. #530(v481)이 같은 계열을 한 번 고쳤는데 §1-B 소비처가 남아 있었다.
//        ★표시 정직화는 stale 캐시가 남으면 **여전히 거짓을 보여주는 상태**가 유지된다
//        (기능은 "없는 것"이 되지만 정직화는 "거짓이 계속되는 것"이라 범프 누락이 더 나쁘다).
//        ★채번: origin/main 실제 상수 v482 확인 → v483. PR 생성 前 보드 claim 선점(관행 2회차).
// v484: 관점(페르소나)별 스토리라인(#543) — 종합분석 보고서가 설계사/디벨로퍼/시공사/금융
//        관점에 따라 **섹션 순서와 요약문**을 바꾼다. 새 파일(lib/analysis-persona.ts)과 패널
//        구조 변경이 함께 들어가므로 stale 번들이 남으면 토글은 보이는데 순서가 안 바뀌는
//        **반쪽 상태**가 된다(기능 부재보다 나쁘다 — 눌러도 안 되는 버튼으로 보인다).
//        ★채번: 라이브 sw.js 실측 v483 + origin/main 상수 v483 대조 → v484. 원격 브랜치
//        chore/sw-v48* 선점 없음 확인(제목이 아니라 상수와 라이브 값 기준).
// v485: 개발가능성 등급 문구 수렴(#548) — **원시 enum 이 새던 프론트 4곳**을 zoning-ssot 로
//        일원화(LandIntelligencePanel·ProjectAnalysisSummary·SiteInitiator + 백엔드 2맵).
//        ★사용자에게 NEEDS_OFFICIAL_SURVEY 같은 코드가 그대로 보이던 것을 사람 말로 바꾸는
//        변경이라, stale app-shell 캐시가 남으면 **옛 번들이 계속 원시 enum 을 노출**한다.
//        #549(변이 생존 구멍 봉합·게이트 상향 무검증/라우터 무테스트)도 같은 배포에 포함.
//        ★채번: origin/main 실제 상수 v484 확인 → v485. PR 생성 前 보드 claim 선점(관행 3회차).
// v486: 비율 표기 **전역 스윕**(#551) — 정수 반올림·깨진 표기·부호 오표기 봉합.
//        formatters + 소비처 4곳(site-analysis page·ChangeForecastCard·SatongMapShell·
//        FairPriceSuggestCard). ★#530(v481 §비율)·#541(v483 §1-B)에 이은 **3차이자 전역**
//        — 같은 결함이 소비처별로 흩어져 있었고 이번에 전수로 쓸었다.
//        표시 정직화는 stale 캐시가 남으면 **거짓이 계속 보이는** 상태가 유지된다.
//        #552(R3 적대검증 — 가짜 골든 정직화·근원 불변식)도 같은 배포 구간(백엔드).
//        ★채번: origin/main 실제 상수 v485 확인 → v486. PR 생성 前 보드 claim 선점(4회차).
// v487: 면적·금액 **0 정책 확정**(#555) — 원장량은 "미확보"라고 말하고, 빠진 필지를 숨기지
//        않는다(formatters + comprehensive_analysis_service). ★비율에서 세운 "0과 미확보를
//        같은 기호로 쓰지 않는다"(#530 v481 → #541 v483 → #551 v486)를 **면적·금액 계열로
//        확장**한 건이다. 표시 정직화라 stale 캐시가 남으면 거짓이 계속 보인다.
//        ★채번: origin/main 실제 상수 v486 확인 → v487. PR 생성 前 보드 claim 선점(5회차).
// v488: 대상 판정 가드 경화(#559 R3 MEDIUM) — **키 충돌 반증분**·재실행 경합·추적 이탈.
//        #537(v482)이 세운 "대상 판정 키=프로젝트+주소"를 적대검증으로 다시 때린 결과다.
//        ★가드가 stale 번들에 남으면 경화 이전 판정이 계속 돌아 옛 분석이 다시 샌다
//        (가드 성격의 수정은 캐시가 곧 무력화 수단이다).
//        ★채번: origin/main 실제 상수 v487 확인 → v488. PR 생성 前 보드 claim 선점(6회차).
// v489: ①마스킹 지번(#558) — 가려진 지번으로 **지오코딩하지 않고**, 표본 0 의 침묵을 없앤다
//        ②모바일 IA P0(#561) — 주소 입력이 지도 위로, 플로팅 버튼이 네비 아래로.
//        ★#558 은 "표본 0 을 침묵으로 두지 않는다"는 이 저장소의 반복 원칙(무날조·정직 고지)의
//        지오코딩 입력단 적용이고, #561 은 모바일 레이아웃이라 **둘 다 화면이 실제로 바뀐다**
//        — stale app-shell 캐시가 남으면 옛 배치·옛 침묵이 그대로 보인다.
//        ★채번: origin/main 실제 상수 v488 확인 → v489. PR 생성 前 보드 claim 선점(7회차).
// v490: ★프로덕션 회귀 **긴급 봉합**(#563) — #561(v489 모바일 IA P0)이 넣은 max-h 에 하한이
//        없어 감산 388px 고정으로 **대화 영역이 사라지던** 회귀. AIAssistant·SatongMapShell.
//        ★회귀 봉합은 stale 캐시가 남으면 **깨진 화면이 그대로 유지**된다 — 사용자가 이미
//        피해를 보고 있는 상태라 범프 누락의 비용이 가장 크다(기능 미노출·정직화 지연과 다름).
//        ★채번: origin/main 실제 상수 v489 확인 → v490. PR 생성 前 보드 claim 선점(8회차).
// v491: #558 후속(#564) — ①승격이 만들던 **존재하지 않는 주소** 제거(첫 행의 동 + 다른 행의
//        지번을 짝지어 무관한 필지에 핀이 찍히고 "위치 개략"이라 말했다) → 실재 3튜플만
//        후보로 두는 결정론적 선택. ②★라이브 적발 — 공시지가·면적을 **둘 다 입력하면**
//        PNU 해석을 건너뛰어 주변 실거래를 **조회조차 안 하고** 사유도 없이 침묵했다
//        (사용자가 정보를 더 줄수록 분석이 줄어드는 역설) → 게이트에 거래사례 미수신 조건 추가.
//        프론트 변경: DeskAppraisalModal 포매터 정본 수렴 · comparable-sample 문구/로케일 ·
//        source-invariant JSX 주석 처리(여러 줄 주석으로 배선 락이 뚫리던 것).
//        ★채번: origin/main 실제 상수 v490 확인 → v491. PR 생성 前 보드 claim 선점(9회차).
// v492: 모바일 IA P1(#566) — 접기를 **대상 유무에 종속**시켜 유일한 주소 진입 경로를 접지
//        않는다(SatongMapShell). #561(v489 P0)·#563(v490 회귀봉합)에 이은 모바일 IA 3번째.
//        ★레이아웃/접힘 상태 변경이라 stale 캐시가 남으면 **옛 접힘 규칙이 그대로 돌아**
//        사용자가 주소 입력에 도달하지 못할 수 있다(진입 경로 차단 = 기능 상실과 동급).
//        ★채번: origin/main 실제 상수 v491 확인 → v492. PR 생성 前 보드 claim 선점(9회차).
// v493: 모바일 IA P2(#570) — 44px 터치 타깃을 파일 전체에 채우고 **전수 불변식으로 잠근다**
//        (ParcelLayoutSection·ParcelSlopeSection·SatongMapShell·satong-map-z).
//        ★터치 영역 변경이라 stale 캐시가 남으면 **옛 터치 타깃이 그대로** — 모바일에서
//        누르기 어려운 상태가 유지된다(접근성 회귀 지속).
//        모바일 IA 계열 4번째 범프: #561(v489 P0)·#563(v490 회귀봉합)·#566(v492 P1)·#570(v493 P2).
//        ★채번: origin/main 실제 상수 v492 확인 → v493. PR 생성 前 보드 claim 선점(10회차).
// v494: ①층위 사다리 계약(#573) — ContextHeader 승격이 **데스크톱 네비를 덮던 회귀** 봉합
//        (WorkspaceNavBar·satong-map-z) ②토지 실거래 지분거래 카운트(#571·백엔드).
//        ★#573 은 z-index 층위 회귀라 stale 캐시가 남으면 **네비가 계속 가려진다** —
//        모바일 IA 계열(#561·#563·#566·#570)에 이은 5번째 레이아웃 범프.
//        ★채번: origin/main 실제 상수 v493 확인 → v494. PR 생성 前 보드 claim 선점(11회차).
// v495: ①층위 사다리 후속(#575) — 회귀망을 **렌더 기반으로 되돌리고** 모달 칸 추가
//        (AuctionWorkspace·AIAssistant·WorkspaceNavBar·OnboardingWizard·DeskAppraisalModal·
//         LandShareModal·satong-map-z 등 프론트 7파일) ②동 단위 토지 실거래 통계(#574·백엔드).
//        ★층위 회귀는 stale 캐시가 남으면 **가려짐이 그대로** — 레이아웃 계열 6번째 범프.
//        ★채번: origin/main 실제 상수 v494 확인 → v495. PR 생성 前 보드 claim 선점(12회차).
// v496: ①층위 계약 후속 5단계(#579) — 모달 칸을 파생값으로 고정하고 소비처를 수렴시킨다
//        (analysis/page·CadBimIntegrationPanel·DesignWorkspace·LandScheduleClient·
//         SatongMapShell·lib/satong-map-z 6파일) ②MOLIT 429 가드(#578·백엔드).
//        ★층위는 stale 셸이 남으면 **가려짐이 그대로** — 레이아웃 계열 7번째 연속 대행.
//        ★채번: origin/main 실제 상수 v495 확인 → v496. PR 생성 前 보드 claim 선점(13회차).
// v497: ①전체화면 조건 배선을 렌더로 잠금(#588·CadBimIntegrationPanel) ②지목 구성 고지(#589)
//        ③등기 하이픈 조회 주소 후보 확장(산 필지 정규화 폴백·백엔드).
//        ★정직 고지 계열이 섞여 있다 — 비해시 자산이 스테일하면 옛 표기가 한 번 더 보인다.
//        ★채번: origin/main 실제 상수 v496 확인 → v497. PR 생성 前 보드 claim 선점(14회차).
// v498: 주소 후보 드롭다운이 sticky ContextHeader(600)에 가리던 회귀 봉합(#597) —
//        본문 팝오버 칸 `contentPopover: 650` 신설 + SatongMapShell·GlobalAddressSearch 승격.
//        ★이 범프가 필요한 이유: v497 이 **#597 보다 먼저** 머지돼(규율 E-20 이 경고하는 경합)
//          위 3파일이 캐시로 가려진다 — `<v497커밋>..origin/main` 실측으로 확인하고 채번했다.
// v499: 지적도가 '안 보이는 것'과 '오류'를 가른다(#614) — 실측 임계 + 상류 재시도.
//        프론트 런타임은 `SatongMultiMap.tsx` 44줄(줌 임계·상태 구분)이라 **렌더에 닿는다**.
//        ★채번: origin/main 실제 상수 v498 확인 → v499. PR 생성 前 보드 claim 선점(15회차).
//        ★경합 방향 확인: 기능 PR(#614 `fdd2fa09`)이 **먼저** 머지된 뒤 이 범프를 올린다.
//          반대 순서였다면 그 기능이 캐시로 가려진다(규율 E-22 가 경고하는 그것).
// v501: 간편 분양성 조사(#619) — 지번 1개로 시세·계획시설·입지·분양사례.
//        프론트 런타임 4파일이 렌더에 닿는다: `quick-survey/page.tsx`(신규 라우트) ·
//        `QuickSalesSurveyClient.tsx`(신규) · `DashboardHome.tsx` · `lib/navigation/route-registry.ts`.
//        ★신규 **라우트와 네비 레지스트리**가 함께 바뀌었다 — 구 번들은 이 경로를 아예 모르므로
//          캐시가 남으면 진입점이 보이지 않는다(기능이 있어도 도달 불가).
//        ★채번: origin/main 실제 상수 v500 확인 → v501. PR 생성 前 보드 claim 선점(16회차).
//        ★경합 방향: 기능 PR(#619 `3b1c8997`)이 **먼저** 머지된 뒤 이 범프를 올린다.
// v503: 토지필지 종합분석 P0~P2(#633·#636) — **신규 라우트** /ko/registry-analysis/quote 와
//        견적·권리분석·매입전략 패널 신설. 신규 라우트는 앱셸 캐시가 스테일하면 진입 자체가
//        막힐 수 있어(라우트 매니페스트 불일치) 이 계열은 범프를 동반한다.
//        ★#636 은 전역 과금결함(캐시 히트마다 발급료 재청구)도 봉합했다 — 백엔드 건이라
//        범프와 무관하지만, 같은 배포에 함께 실린다.
//        ★채번: origin/main 실제 상수 v502 확인 → v503. PR 생성 前 보드 claim 선점(15회차).
// v504: 운영화면 정직 표기(#642) + 지적도 실측 임계 z18→z17·호미곶 거짓 안내 교정(#635).
//        #642 는 신규 라우트가 아니라 **기존 화면의 렌더 경로 교체**(배열 접지 + 문구)라
//        앱셸이 스테일하면 옛 번들이 계속 크래시한다 → 범프 동반.
//        ★채번: origin/main 실제 상수 v503 확인 → v504. ★v503 때 세 세션이 1분 안에 동시
//        채번해 PR 2건이 충돌했다 — 이번엔 **기능 PR 머지 前** 보드 선점으로 창을 없앴다.
// v505: 과금 재전송 안전(`Idempotency-Key`) + **#644 의 밀린 범프**.
//        ①`RegistryBulkButton` 이 등기 일괄조회에 재전송 안전 키를 붙인다(백엔드 멱등 배선과 짝).
//        ②★#644(정책표 통로 일원화 — 도시개발이 "매도청구"로 오표시되던 건)는 프론트
//          `DevelopmentScenarioCard` 를 바꿨는데 **범프 없이 머지됐다**(실측: 머지 후에도
//          origin/main 상수가 v504). 앱셸이 스테일한 재방문자는 옛 번들을 계속 보므로
//          그 봉합이 **캐시에 가려진다** — CLAUDE.md E22 가 경고한 형태 그대로다.
//          이 범프가 ①과 ②를 함께 실어 보낸다.
//        ★채번: origin/main 실제 상수 v504 확인 → v505.
// v506: CAD 패널 비율 표기 수렴(#647) — 건폐율·용적률이 `toFixed(0)` 로 반올림돼
//        실효 79.6% 가 "80%" 가 되어 **바로 옆 법정 80% 와 같아 보이던** 것을
//        formatPercent(소수 1자리·null→"미확보")로 일원화. 표시 문자열이 바뀌므로 범프.
//        ★채번: 범프 커밋을 **CACHE_NAME 대조로 특정**(3bddbeb0=v505 · acdf9b6c=v504 ·
//        c18898ba=v503). `git log -1 -- sw.js` 는 기능 커밋도 집어 두 세대 전을 가리켰다.
//        그 기준으로 재면 "60파일 밀림", 올바른 기준으로는 실제 델타 **2파일**이다.
// ★★2026-08-16 — 이 값은 **빌드가 치환한다**(Dockerfile.web). 손으로 올리지 마라.
//
//   왜: 종전에는 배포마다 사람이 이 문자열을 올렸고, 그 결과
//     ① **범프 전용 PR 이 85개** 쌓였다(각각 CI 약 16분 + 채번 조율. 세 세션이 1분 안에
//        같은 번호를 채번한 사고도 났다)
//     ② **순서 결함(E-22)** 이 상시 존재했다 — 범프가 기능 PR 보다 먼저 머지되면 그 기능이
//        캐시에 가려진다. 바로 위 v506 주석이 그 사고를 적고 있다(#644 가 범프 없이 머지돼
//        DevelopmentScenarioCard 봉합이 재방문자에게 안 갔다)
//     ③ 그래서 **자동배포를 켤 수 없었다**(머지마다 배포되면 ②가 상시화된다)
//   빌드가 만들면 **순서라는 것이 존재하지 않게 되어** ②가 원리적으로 사라진다.
//
//   형식: propai-v<seq 6자리>-<shortsha>   예) propai-vXXXXXX-XXXXXXXX
//   ★예시를 **실재하지 않는 형태**로 둔다. 종전엔 여기에 당시 실제 sha 를 적었는데,
//     그 값이 패턴 매칭(`grep -oE 'propai-v[0-9a-z-]+' | head -1`)에 먼저 걸려
//     다른 세션이 **주석의 예시를 배포된 상수로 착각**했다(2026-08-17: "#658 고장·
//     사용자에게 수정이 안 닿는다"는 오보로 이어질 뻔했다).
//     상태를 잴 때는 반드시 줄 시작 앵커를 줘라: grep -m1 '^const CACHE_NAME'
//     · seq = `git rev-list --count HEAD` (단조 증가) — **정렬 가능성**을 위해 제로패딩한다.
//       ★정직 고지: 레거시 이름(propai-v504-…)은 자릿수가 달라 **단순 문자열 정렬에서 신규
//         이름 뒤로 간다**(‘5’>‘0’). 경계는 1회성이고, 순서를 쓰는 분석은 숫자를 파싱해야 한다.
//     · shortsha = 어느 커밋이 나갔는지 **정확히** 식별. 사람이 읽는 “무엇이 나갔나”는
//       `git merge-base --is-ancestor` + 커밋 메시지가 더 정확히 답한다(드리프트도 없다).
//
//   ★아래 값은 **로컬 개발 전용**이다. 이 문자열이 프로덕션에 나가면 그건 치환 실패이고,
//     Dockerfile.web 이 그 경우 **빌드를 죽인다**(조용히 같은 캐시명이 나가면 지금보다 나쁘다 —
//     캐시가 영원히 무효화되지 않는다).
const CACHE_NAME = "propai-vdev-local";
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
