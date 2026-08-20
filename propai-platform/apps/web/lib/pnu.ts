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
  if (p.pnu && String(p.pnu).trim()) return `pnu:${String(p.pnu).trim()}`;
  const addr = (p.address || "").trim().replace(/\s+/g, " ");
  return addr ? `addr:${addr}` : null;
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
  const tokens = (address || "").trim().split(/\s+/).filter(Boolean);
  const last = tokens[tokens.length - 1] ?? "";
  return /^산?\d+(-\d+)?$/.test(last);
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
