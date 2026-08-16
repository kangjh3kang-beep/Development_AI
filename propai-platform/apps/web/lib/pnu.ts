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
  // 이미 그 지번이 주소에 들어 있으면 중복 표기하지 않는다.
  if (addr && new RegExp(`(^|\\s)${jibun.replace(/[-]/g, "\\-")}(\\s|$)`).test(addr)) return addr;
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
