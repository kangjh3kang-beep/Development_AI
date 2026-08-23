import { addressRegionMismatch } from "@/store/useProjectContextStore";

/**
 * 선택 필지 묶음의 **무결성 판정** — "이게 하나의 개발 부지인가".
 *
 * 왜 필요한가(쉬운 설명):
 * 화면은 고른 필지들의 면적을 더해 "통합 대지면적 5,781㎡"라고 말한다. 그런데 그 필지들이
 * 서로 **15.86km 떨어져** 있으면 그건 하나의 부지가 아니다 — 그 합계로 연면적·공사비를
 * 계산하면 존재하지 않는 사업을 계산하는 것이다. 그런데도 시스템은 그 사실을 말하지 않았다.
 *
 * ★라이브 실측(2026-08-23) — 프로덕션 스냅샷 54건 중:
 *   · `4f8a6db5` : 제천 성내리 3필지 + 제천 모산동 3필지 = **15.86km** 떨어진 "통합 5,781㎡"
 *   · `458d7c86` : 역삼동 + 포항 호미곶 + 의정부 = **290km**
 *   · `ad66982a` : `siteAnalysis.address` 가 **사람 이름**(`◀ 전성결`), 필지 4행이 소유자명
 *     → 토지조서 엑셀의 **소유자 컬럼이 주소로 읽혔다**
 *
 * ★**막지 않는다 — 고지한다.** 원거리 필지를 한 프로젝트에 담는 것은 *후보지 비교*라는
 *   정당한 워크플로우일 수 있다(290km 건이 그렇게 보인다). 차단하면 정상 사용을 막는다.
 *   틀린 것은 선택이 아니라 **그것을 "통합 부지"라고 부르는 화면**이다.
 *
 * ★판정은 **세 신호를 함께** 본다 — 단일 신호는 반드시 뚫린다(실증):
 *   ① 행정구역(`addressRegionMismatch`) — 이것만으로는 **주소가 아닌 값**을 못 잡는다
 *      (`◀ 전성결` 은 토큰 추출 실패 → 보수적으로 '일치' 반환)
 *   ② 주소 형태 검증 — ①의 사각을 메운다
 *   ③ 좌표 거리 — 사람에게 보여줄 **크기**(몇 km 떨어졌나)를 만든다. 판정의 주 근거는
 *      아니다(좌표가 아예 없는 프로젝트가 실재한다 — `ad66982a` 는 13필지 전부 무좌표).
 *
 *   ★내가 손으로 만든 스캔 두 개가 각각 반대 방향으로 틀렸다: 좌표만 보면 무좌표를 놓치고,
 *     시군구만 보면 같은 시(제천) 안의 15.86km 를 놓친다. 그래서 셋을 합친다.
 *     ①은 **기존 프로덕션 헬퍼를 그대로 재사용**한다 — 실측으로 진짜 오염 5/5 적발,
 *     정상 3/3 통과(`경기도 용인시` vs `용인시` 표기 차이도 정확히 '일치'로 본다).
 */

export type IntegrityParcel = {
  address?: string | null;
  lat?: number | null;
  lon?: number | null;
  areaSqm?: number | null;
};

export type SelectionVerdict =
  /** 하나의 부지로 볼 수 있다(또는 단일 필지) — 통합 계산이 의미를 가진다. */
  | "single_site"
  /** 서로 다른 지역이 섞였다 — 통합 부지가 아니다(후보지 비교로 보인다). */
  | "multi_region"
  /** 주소가 아닌 값이 섞였다 — 데이터가 깨졌다(엑셀 소유자 컬럼 오인식 등). */
  | "malformed";

export type SelectionIntegrity = {
  verdict: SelectionVerdict;
  /** 지역 군의 대표 주소들(2개 이상이면 혼합). */
  regionGroups: string[];
  /** 주소 형태가 아닌 행(소유자명 등)의 원문. */
  malformedRows: string[];
  /** 좌표를 가진 필지 간 최대 거리(km). 좌표가 2개 미만이면 null — **미상이지 0이 아니다**. */
  spreadKm: number | null;
};

/** 행정구역 접미(동·리·가·로·길·면·읍) 뒤에 번지가 오거나, 광역시도로 시작하면 주소로 본다. */
const SIDO_PREFIX = [
  "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
  "경기", "강원", "충청", "충북", "충남", "전라", "전북", "전남",
  "경상", "경북", "경남", "제주",
];
const JIBUN_RE = /(동|리|가|로|길|면|읍)\s*(산\s*)?\d/;

/**
 * 주소 형태인가 — `addressRegionMismatch` 의 **사각을 메우는** 검사.
 *
 * ★그 헬퍼는 토큰을 못 뽑으면 보수적으로 '일치'(false)를 반환한다. 정상 동기화를 막지
 *   않으려는 올바른 설계지만, 그래서 `◀ 전성결` 같은 값이 **조용히 통과**한다.
 *   여기서 그 값을 따로 잡는다.
 */
export function looksLikeAddress(value: string | null | undefined): boolean {
  const s = (value ?? "").trim();
  if (!s) return false;
  // ★`◀` 는 실측한 오인식 행의 접두다(토지조서 엑셀 소유자 컬럼). 화살표류는 주소에 없다.
  if (/^[◀▶◁▷←→]/.test(s)) return false;
  if (JIBUN_RE.test(s)) return true;
  return SIDO_PREFIX.some((p) => s.startsWith(p));
}

/** 두 좌표 사이 거리(m) — haversine. */
function distanceM(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const R = 6371000;
  const p1 = (aLat * Math.PI) / 180;
  const p2 = (bLat * Math.PI) / 180;
  const dp = ((bLat - aLat) * Math.PI) / 180;
  const dl = ((bLon - aLon) * Math.PI) / 180;
  const x =
    Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

/**
 * 선택 묶음을 판정한다. 필지가 2개 미만이면 항상 `single_site`(비교할 대상이 없다).
 *
 * ★`malformed` 가 `multi_region` 보다 **우선**한다: 주소가 아닌 값이 섞여 있으면 지역
 *   비교 자체가 의미를 잃는다(깨진 데이터 위에서 "몇 개 지역인가"를 세면 그 수도 거짓이다).
 */
export function classifySelection(
  parcels: readonly IntegrityParcel[] | null | undefined,
): SelectionIntegrity {
  const list = (parcels ?? []).filter(Boolean);

  const malformedRows = list
    .map((p) => (p.address ?? "").trim())
    .filter((a) => a.length > 0 && !looksLikeAddress(a));

  // 좌표 확산 — 판정 근거가 아니라 **사람에게 보여줄 크기**.
  const pts = list
    .filter(
      (p): p is IntegrityParcel & { lat: number; lon: number } =>
        typeof p.lat === "number" &&
        Number.isFinite(p.lat) &&
        typeof p.lon === "number" &&
        Number.isFinite(p.lon),
    )
    .map((p) => [p.lat, p.lon] as const);
  let spreadKm: number | null = null;
  if (pts.length >= 2) {
    let max = 0;
    for (let i = 0; i < pts.length; i += 1) {
      for (let j = i + 1; j < pts.length; j += 1) {
        const d = distanceM(pts[i][0], pts[i][1], pts[j][0], pts[j][1]);
        if (d > max) max = d;
      }
    }
    spreadKm = Math.round((max / 1000) * 100) / 100;
  }

  // 지역 군 — 주소 형태인 것만 대상(깨진 값으로 군을 만들지 않는다).
  const addrs = list
    .map((p) => (p.address ?? "").trim())
    .filter((a) => looksLikeAddress(a));
  const regionGroups: string[] = [];
  for (const a of addrs) {
    if (!regionGroups.some((rep) => !addressRegionMismatch(rep, a))) {
      regionGroups.push(a);
    }
  }

  let verdict: SelectionVerdict = "single_site";
  if (list.length >= 2) {
    if (malformedRows.length > 0) verdict = "malformed";
    else if (regionGroups.length > 1) verdict = "multi_region";
  } else if (malformedRows.length > 0) {
    // 단일 필지라도 그 값이 주소가 아니면 깨진 것이다.
    verdict = "malformed";
  }

  return { verdict, regionGroups, malformedRows, spreadKm };
}

/**
 * 사용자에게 보여줄 고지 문구 — **사실 + 무엇이 무효인가 + 복구 방법**.
 *
 * ★문구는 **평문**이다. 마크다운(`**강조**`)을 쓰면 화면에 별표가 **그대로 글자로 나온다** —
 *   실제로 그렇게 내보냈고 라이브 화면에서야 발견했다(테스트는 `toContain` 으로 별표를
 *   **피해서** 단언해 못 잡았다). 강조가 필요하면 렌더 쪽에서 `<b>` 로 한다.
 * 정상(`single_site`)이면 `null`(고지하지 않는다 — 남발은 무시로 이어진다).
 */
export function selectionIntegrityNotice(
  integrity: SelectionIntegrity,
): { tone: "warn" | "bad"; title: string; detail: string } | null {
  if (integrity.verdict === "malformed") {
    const sample = integrity.malformedRows.slice(0, 3).join(" · ");
    return {
      tone: "bad",
      title: "주소가 아닌 값이 필지 목록에 있습니다",
      detail:
        `${integrity.malformedRows.length}건(${sample}${integrity.malformedRows.length > 3 ? " 외" : ""}) — ` +
        "엑셀의 소유자 칸이 주소로 읽혔을 수 있습니다. 통합 대지면적과 용도지역 판정은 " +
        "이 상태에서 신뢰할 수 없습니다. 해당 행을 지우고 지번을 다시 지정하세요.",
    };
  }
  if (integrity.verdict === "multi_region") {
    const where = integrity.spreadKm != null ? `최대 ${integrity.spreadKm}km 떨어져 ` : "";
    return {
      tone: "warn",
      title: "하나의 개발 부지가 아닙니다",
      detail:
        `선택한 필지가 ${integrity.regionGroups.length}개 지역에 ${where}있습니다. ` +
        "합계 면적은 보여 주지만 통합 대지면적이 아니며, 이 값으로 계산한 연면적·사업비는 " +
        "성립하지 않습니다. 후보지 비교라면 그대로 두어도 되고, 한 부지를 분석하려면 " +
        "'필지 선택/변경'에서 한 지역만 남기세요.",
    };
  }
  return null;
}
