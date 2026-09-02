/**
 * PNU(필지 고유번호) 유틸 — **필지의 정체성은 주소가 아니라 PNU 다.**
 *
 * ## 왜 생겼나 (2026-08-17 프로덕션 버그)
 *
 * `발급 전 비용 견적·선별` 화면에서 "현재 프로젝트 필지 불러오기 **(77)**" 를 눌렀는데
 * 목록에 **1건**만 들어왔다. 그 1건의 라벨은 지번이 없는 **동 단위 주소**였다
 * (`경기도 오산시 내삼미동`).
 *
 * 원인: 불러오기가 **주소로 중복제거**했다.
 *
 *     const existing = new Set(prev.map((r) => r.address));
 *     if (!p.address || existing.has(p.address)) continue;   // ← 77필지가 같은 동이면 1건만 남는다
 *
 * ★같은 함수가 React key 는 이미 `p.pnu || p.address` 로 잡고 있었다 — **정체성이 PNU 라는 걸
 *   알면서 중복제거만 주소로 했다.** 저장소의 다른 곳들도 `pnu || address` 를 쓴다
 *   (`GlobalAddressSearch`·`satong-map-selection`·`MultiParcelAttributeMatrix`).
 *   즉 이 파일 하나가 기준선에서 이탈해 있었다.
 *
 * ★그리고 중복제거만 고치면 목록에 **똑같은 라벨 77줄**이 뜬다. 사용자가 어느 필지를 고르는지
 *   알 수 없으므로 **PNU 에서 지번을 파생해 라벨을 구분 가능하게** 만든다.
 *
 * ## PNU 구조(19자리)
 *
 *     [0..10)  법정동코드 10자리
 *     [10]     1=일반, 2=산
 *     [11..15) 본번 4자리
 *     [15..19) 부번 4자리
 */

/** PNU 가 19자리 숫자 형식인가. */
export function isValidPnu(pnu: string | null | undefined): boolean {
  return typeof pnu === "string" && /^\d{19}$/.test(pnu);
}

/**
 * PNU → 지번 문자열(`산12-3` · `123` · `123-4`). 형식이 아니면 `null`.
 * ★본번이 0이면 지번을 만들 수 없다(무날조 — 없는 값을 지어내지 않는다).
 */
export function jibunFromPnu(pnu: string | null | undefined): string | null {
  if (!isValidPnu(pnu)) return null;
  const s = pnu as string;
  const mountain = s[10] === "2";
  const bon = Number(s.slice(11, 15));
  const bu = Number(s.slice(15, 19));
  if (!bon) return null;
  return `${mountain ? "산" : ""}${bon}${bu ? `-${bu}` : ""}`;
}

/**
 * 화면에 보여줄 필지 라벨. 주소에 지번이 이미 있으면 그대로 두고, 없으면 PNU 에서 파생해 붙인다.
 * ★동 단위 주소만 받은 목록이 **전부 같은 글자**로 보이던 것을 막는다.
 */
export function parcelDisplayAddress(
  address: string | null | undefined,
  pnu?: string | null,
): string {
  const addr = (address || "").trim();
  const jibun = jibunFromPnu(pnu);
  if (!jibun) return addr;
  // ★주소가 **이미 지번으로 끝나면** 아무것도 덧붙이지 않는다.
  //   종전엔 정규식으로 "그 지번 문자열이 들어 있나" 를 봤는데 두 군데서 틀렸다:
  //     ① `산1-1` 은 `1-1` 앞이 공백이 아니라 못 알아보고 `… 산1-1 1-1` 을 만들었다.
  //     ② PNU 가 가리키는 지번과 주소의 지번이 **다를** 때 `… 114-1 467-1` 같은
  //        서로 모순되는 라벨을 만들었다(어느 쪽이 맞는지 화면이 말하지 못한다).
  //   주소에 지번이 있으면 그 주소가 이미 필지를 특정한다 — 그대로 둔다.
  if (addressHasJibun(addr)) return addr;
  return addr ? `${addr} ${jibun}` : jibun;
}

/**
 * 필지 중복제거 키 — **PNU 우선**, 없을 때만 주소로 떨어진다.
 *
 * ★주소만 쓰면 같은 동의 필지가 전부 1건으로 접힌다(이 파일이 생긴 이유).
 * ★PNU 도 주소도 없으면 `null` — 호출부가 "키 없음"을 **중복으로 취급하지 않도록** 한다
 *   (키 없는 행을 하나로 접으면 데이터 손실이다).
 */
export function parcelDedupKey(
  p: { pnu?: string | null; address?: string | null },
): string | null {
  // ★PNU 칸에 **PNU 가 아닌 것**이 들어앉는 일이 실재한다 — 라이브 실측(2026-09-02):
  //   프로젝트 20건 292필지 중 5건이 `'◀ 전성결'`(성명) · `'store-rep-용인시 …'`(합성 id).
  //   생산자는 `satong-map-selection.ts` 의 `` `store-rep-${address}` `` 라 **주소가 같으면 값도 같다.**
  //   유효성을 안 보면 그 가짜가 곧 **정체성**이 되어, 같은 동의 필지가 다시 한 건으로 접힌다
  //   (이 파일이 생긴 바로 그 버그). 검증은 `normalizePnu` 한 곳에서만 한다 — 구현 두 벌 금지.
  const pnu = normalizePnu(p.pnu == null ? "" : String(p.pnu));
  if (pnu) return `pnu:${pnu}`;
  const addr = (p.address || "").trim().replace(/\s+/g, " ");
  return addr ? `addr:${addr}` : null;
}

/**
 * **프로젝트 SSOT 필지**의 정체성 키 — 유효 PNU 가 있으면 그것, 없으면 **인덱스를 섞는다.**
 *
 * ★왜 주소로 떨어뜨리지 않나: 프로젝트 필지는 SSOT 가 **이미 서로 다른 필지**임을 보장한다.
 *   그런데 주소가 동 단위로 같으면(`경기도 오산시 내삼미동` ×77) 주소 폴백이 전부 한 건으로
 *   접는다 — 신고된 "필지 불러오기 (77) 인데 목록에 1건" 이 그것이다. 인덱스를 섞어 막는다.
 *   대가: 불러오기를 두 번 누르면 PNU 없는 행이 중복될 수 있다 — 그건 **화면에 보이고 지울 수
 *   있는** 문제이고, 조용히 사라지는 것보다 낫다(무음 손실 금지).
 *
 * ★★이 규칙이 함수인 이유: 종전에는 패널에 **인라인**으로 있었고 테스트는 그 규칙을
 *   **재구현**해서 검사했다(`p.pnu ? … : …`). 그래서 «가짜 PNU 는 truthy 라 인덱스 탈출구를
 *   건너뛴다» 는 결함이 **양쪽에 똑같이** 있었고 테스트는 초록이었다.
 *   구현이 두 벌이면 한쪽만 고쳐진다 — 이 파일이 반복해서 배운 것이다.
 */
export function projectParcelIdentityKey(
  p: { pnu?: string | null; address?: string | null },
  index: number,
): string {
  const pnu = normalizePnu(p.pnu == null ? "" : String(p.pnu));
  if (pnu) return `pnu:${pnu}`;
  return `project-idx:${index}:${(p.address || "").trim()}`;
}

/**
 * "이 값이 **진짜 PNU 인가**" 의 단일 판정 — 19자리 숫자만 통과, 아니면 `null`.
 *
 * ## 왜 생겼나 (2026-08-20 프로덕션 버그 — 같은 증상 6번째)
 *
 * `selectionToSiteAnalysisPatch` 가 `pnu: parcel.pnu || parcel.id` 로 저장했다.
 * `parcel.id` 는 PNU 가 없을 때 **주소를 정규화한 합성 문자열**이라, PNU 칸에
 * `"경기도 오산시 내삼미동"` 같은 **가짜 PNU** 가 들어앉았다. 그 결과:
 *
 *   ① `jibunFromPnu` 가 형식 불일치로 `null` → 지번 파생이 전 화면에서 무동작
 *   ② `healParcelPnu(기존, 경계응답)` 이 "기존이 있으니 보존" 으로 판단 →
 *      경계 API 가 돌려준 **진짜 PNU 를 영원히 버린다**
 *   ③ 경계 요청 본문에 그 가짜 PNU 가 실려 나간다 — 라이브 실측(2026-08-20):
 *      `{"pnu":"경기도 오산시 내삼미동"}` → 서버가 그대로 echo 하고
 *      `jibun:null · area_sqm:0 · zone_type:null · age_status:"lookup_failed"`.
 *      즉 **필지 보강 전체가 조용히 죽는다**(표시만의 문제가 아니다).
 *
 * 그래서 "PNU 자리에 PNU 가 아닌 것이 들어오면 **없는 것으로 본다**" 를 한 곳에 둔다.
 * 가짜를 지우는 것이지 없는 값을 지어내지 않는다(무날조).
 */
export function normalizePnu(value: string | null | undefined): string | null {
  const s = typeof value === "string" ? value.trim() : "";
  return isValidPnu(s) ? s : null;
}

/**
 * PNU → **법정동코드 10자리**(`bcode`). 유효한 19자리가 아니면 `null`.
 *
 * ## 왜 공용인가 (2026-09-02 — 같은 식이 **12벌** 있었다)
 *
 * `pnu.length >= 10 ? pnu.slice(0, 10) : ""` 가 `GlobalAddressSearch`(6) ·
 * `PersonaPanel` · `node-body-builders` · `MarketInsightsWorkspaceClient`(가드 **없음**) 등에
 * 흩어져 있었다. 길이 10 은 **PNU 를 판정하지 못한다** — 라이브 실측(292필지) 오염값
 * `'store-rep-용인시 수지구 신봉동 56-1'`(26자)이 그 가드를 통과해 `.slice(0,10)` 이
 * **`"store-rep-"` 를 법정동코드로 만들었다.** 백엔드는 `bcode[:5]` = `"store"` 를
 * `lawd_cd` 로 쓴다 — **없는 법정동으로 조회가 나간다.**
 *
 * ★`>= 10` 이 아니라 **`isValidPnu`(19자리 숫자)** 로 판정한다. 구현은 여기 한 벌뿐이다.
 */
export function bcodeFromPnu(pnu: string | null | undefined): string | null {
  const valid = normalizePnu(pnu);
  return valid ? valid.slice(0, 10) : null;
}

/**
 * 한 토큰이 **지번(번지) 표기**인가 — `123` · `123-4` · `산12-3` · `114-1번지`.
 *
 * ★이 저장소의 **단일 판정**이다. 종전엔 같은 질문을 두 곳이 각자 답했고 규칙이 어긋나 있었다:
 *   `store/useProjectContextStore.extractAddressTokens` 는 `(번지)?` 를 인정했는데
 *   `addressHasJibun` 은 빼먹어, `…114-1번지` 를 **지번 없음**으로 오판했다.
 *   구현이 두 벌이면 한쪽만 고쳐진다 — 그래서 `extractAddressTokens` 가 이 함수를 쓴다.
 */
export function isJibunToken(token: string | null | undefined): boolean {
  return /^산?\d+(-\d+)?(번지)?$/.test((token || "").trim());
}

/**
 * 주소 문자열이 **필지를 특정할 수 있는가**(끝에 번지/지번이 붙어 있는가).
 *
 * ★이 판정이 없으면 **날조가 일어난다.** 라이브 실측(2026-08-20):
 *   `/zoning/parcel-boundaries` 에 `{"address":"경기도 오산시 내삼미동"}`(동 단위)만 보내면
 *   서버는 **임의의 한 필지**(`114-1`)로 수렴시켜 돌려준다. 77필지가 전부 같은 동이면
 *   77행이 전부 `114-1` 이라는 **조용한 오답**이 된다(전부 같은 라벨보다 더 나쁘다).
 *   `/zoning/parcels-info` 는 같은 입력에 `status:"ambiguous"` +
 *   "번지 없이 동·읍·면 단위만 입력 — 동 대표지점 1필지로 수렴" 이라고 **스스로 거절**한다.
 *
 * 그러므로 지번이 없는 주소는 **필지 식별자로 쓰지 않는다**.
 * ※ 도로명 주소의 건물번호(`테헤란로 123`)도 참이 된다 — 그쪽도 "임의 수렴" 위험이 없는
 *   건물 단위 식별자라 이 용도(수렴 위험 판정)에는 맞다.
 *
 * ## 이 가드를 **어디에** 걸었나(적용 범위 = 결함이 사는 범위)
 *
 *  걸었다  — 저장된 여러 행을 **자동·일괄**로 해석하는 곳:
 *            `RegistryAnalysisWorkspaceClient` 의 지오코딩 폴백,
 *            `SatongMultiMap` 의 경계 일괄 조회, `lib/parcel-jibun-heal`.
 *            여기서는 한 번의 오해석이 **모든 행에 같은 오답**으로 번진다.
 *  안 걸었다 — 사용자가 **직접 입력해 1건을 검색**하는 곳(`GlobalAddressSearch`·
 *            `SatongMapShell` 의 주소 검색). 사용자가 동 이름을 치고 그 동의 대표 지점을
 *            보는 것은 의도된 동작이고, 결과가 1건이라 "전부 같은 오답" 이 성립하지 않는다.
 *            여기까지 막으면 정상 워크플로우를 깨는 **위양성**이다.
 */
export function addressHasJibun(address: string | null | undefined): boolean {
  // ★후행 괄호절을 걷어내고 본다. `서울특별시 강남구 역삼동 736-19 (역삼동)` 처럼 **도로명주소
  //   표준 표기**(법정동·건물명 병기)는 등기·건축물대장에서 복사해 붙이면 일상적으로 들어온다.
  //   이걸 못 보면 지번이 **있는데도** "미확인" 으로 몰려 지오코딩·경계보강에서 제외되고,
  //   결국 PNU 를 영영 못 얻는다(#694 가 고치려던 증상의 재발). 라이브 확인:
  //   `…736-19 (역삼동)` → parcel-boundaries ok(188㎡·일반상업), `…114-1번지` → geocode ok.
  //   `114-1(대)` 처럼 공백 없이 붙는 표기도 같이 처리하려고 반복 제거한다.
  //   ★반복 횟수를 **유한하게** 묶는다. `for(;;)` 로 두면 `text` 갱신이 한 줄만 빠져도
  //   (사람 실수든 변이든) 조건이 영원히 참이라 **무한 루프**가 된다 — 실제로 변이 검증이
  //   그 한 줄로 두 번 매달렸다. 괄호절이 4겹 넘게 붙는 주소는 없다.
  let text = (address || "").trim();
  for (let round = 0; round < 4 && text; round += 1) {
    const stripped = text.replace(/\s*\([^()]*\)\s*$/, "").trim();
    if (stripped === text) break;
    text = stripped;
  }
  const tokens = text.split(/\s+/).filter(Boolean);
  return isJibunToken(tokens[tokens.length - 1]);
}

/**
 * 이 필지가 화면에서 **다른 필지와 구분 가능한가**(지번을 확보했는가).
 * 거짓이면 화면은 그 사실을 **정직하게 말해야** 한다 — 조용히 동 이름만 77번 찍지 말 것.
 */
export function parcelJibunResolved(
  parcel: { pnu?: string | null; address?: string | null },
): boolean {
  return !!jibunFromPnu(parcel.pnu) || addressHasJibun(parcel.address);
}

/**
 * 필지 **짧은 라벨**(목록·지도 마커·클릭메뉴 공용) — PNU 로 지번을 파생한 **뒤에** 줄인다.
 *
 * ★순서가 핵심이다. 먼저 줄이면(`address.split(/\s+/).slice(-2)`) 동 단위 주소는
 *   `"오산시 내삼미동"` 이 되고 지번을 붙일 자리가 사라진다 — 실제로 사통맵 목록·지도 라벨이
 *   그렇게 인라인 구현돼 있어서, 상류(백엔드)를 고쳐도 이 화면들만 계속 같은 글자를 찍었다.
 *   줄이는 구현은 **여기 한 곳**뿐이다 — 종전 `lib/satong-click-menu.shortJibunLabel` 은
 *   PNU 를 모르는 별도 구현이라 지웠다(구현이 두 벌이면 한쪽만 고쳐진다).
 */
export function parcelShortLabel(
  address: string | null | undefined,
  pnu?: string | null,
  fallback = "필지",
): string {
  const full = parcelDisplayAddress(address, pnu).trim();
  const tokens = full.split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return fallback;
  return tokens.slice(-2).join(" ");
}

/**
 * **소재지(동)와 지번(번지)이 분리된 양식**을 하나의 완전한 지번주소로 결합한다.
 *
 * ## 왜 여기 있나 (2026-08-20 — 이번 결함의 **진짜 상류**)
 *
 * 엑셀 토지조서는 `소재지 | 지번` 을 **다른 칸**에 쓰는 양식이 흔하다. 백엔드
 * `/zoning/parse-parcels` 는 그 원본을 정직하게 나눠 돌려준다(라이브 실측 2026-08-20:
 * `소재지=경기도 오산시 내삼미동` + `지번=467-1` → `address="경기도 오산시 내삼미동"` ·
 * `jibun="467-1"` · `pnu="4137011000104670001"`).
 *
 * 그런데 사통맵의 엑셀 유입부가 `parcel.address || parcel.jibun` 로 받았다 — `||` 라서
 * **소재지가 있으면 지번은 평가조차 되지 않는다.** `467-1` 은 화면에 닿기도 전에 증발했고,
 * 저장 타입(`SatongSelectionParcel`·`ParcelData`)에 지번 칸이 아예 없어 되살릴 수도 없었다.
 * 그게 "77행이 전부 동 이름" 의 발원지다.
 *
 * ★이 결합은 **이미 이 저장소에 있었다** — `GlobalAddressSearch` 가 2026-06-17(`daa76bc0`)에
 *   같은 버그를 고치며 만들었다. 그런데 13일 뒤 새로 생긴 사통맵 유입부가 **그 목록에 없어서**
 *   같은 결함을 그대로 재도입했다. 사람이 센 형제 목록이 상한이었다는 증거이자,
 *   이 함수를 공용으로 뽑는 이유다(구현 두 벌 금지).
 *
 * 없는 값을 지어내지 않는다 — 지번이 없으면 주소를 그대로 돌려준다.
 *
 * ## 중복 판정은 **부분문자열이 아니라 `addressHasJibun`** 이다
 *
 * 처음엔 `!addr.includes(jb)` 였다. 그런데 법정동 이름에 숫자가 들어가는 `○가` 계열
 * (`을지로1가`·`충무로2가`·`종로3가`·`대청동1가` …)에서 **본번이 한 자리면 그 숫자가
 * 동 이름 안에 이미 있다**고 오판해 지번을 버린다:
 *
 *     joinAddressJibun("서울특별시 중구 을지로1가", "1")  →  "…을지로1가"   ← 지번 소실
 *
 * 즉 **이 PR 이 없애려는 바로 그 증상**이 형제 모집단에 그대로 남는다.
 * 판정을 `addressHasJibun`(주소가 **지번으로 끝나는가**)으로 바꾸면 `을지로1가` 는
 * 마지막 토큰이 지번 토큰이 아니므로 정상 결합된다. 중복 방지·모순 라벨 방지는 그대로다
 * (`… 114-1` + `114-1` → 그대로, `… 114-1` + `467-1` → 그대로).
 *
 * ★이 PR 이 내내 말한 "구현이 두 벌이면 한쪽만 고쳐진다" 를 **자기 자신에게** 적용한 수정이다 —
 *   `parcelDisplayAddress` 는 이미 `addressHasJibun` 을 쓰는데 여기만 별도 규칙이었다.
 */
export function joinAddressJibun(
  address: string | null | undefined,
  jibun: string | null | undefined,
  fallback = "",
): string {
  const addr = (address || "").trim();
  const jb = (jibun || "").trim();
  if (jb && addr && !addressHasJibun(addr)) return `${addr} ${jb}`;
  return addr || jb || fallback;
}
