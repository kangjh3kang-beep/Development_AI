/**
 * 외부에서 **실행 코드를 받아오는 호스트**의 전수 계약.
 *
 * ## 왜 생겼나 (2026-08-22)
 *
 * 사통맵·경공매 지도 세 파일이 `unpkg.com` 에서 Leaflet 을 런타임에 받아왔다.
 * 같은 로더가 **3벌 복붙**돼 있었고 `integrity`(SRI) 도 `crossorigin` 도 없었으며,
 * 프론트엔드에는 CSP 도 없다. 즉 **그 호스트에서 도착한 바이트가 그대로 실행**됐다.
 * 로그인 토큰이 `localStorage` 에 있고 그 지도는 대부분의 분석 화면에서 돈다.
 *
 * Leaflet 은 이제 번들에서 온다(`lib/leaflet-loader.ts`). 남은 것은 **번들로 옮길 수 없는
 * 벤더 SDK** 뿐이고, 이 파일이 그 목록을 **닫아 둔다.**
 *
 * ## 이 파일이 잠그는 것
 *
 * ① **파생 전수** — 사람이 센 목록이 아니라 소스에서 외부 URL 대입을 긁어 **스스로 모은다.**
 *    새 CDN 이 어디에 생기든 자동으로 이 검사에 걸린다(목록형이면 새 항목이 감시망 밖이다).
 * ② **여러 표기를 함께 본다** — `.src=` 하나만 보면 놓친다. 실제로 이번에 두 번 놓쳤다:
 *    `//t1.daumcdn.net`(프로토콜 상대 URL)과 `workerSrc`(대입 이름이 다름).
 * ③ **주석·문자열에 안 뚫린다** — `__stripCommentsForScan` 을 거쳐 실행되는 줄만 본다.
 *    (이 파일 자신의 주석에 `unpkg.com` 이 여러 번 나오는데, 그게 위반으로 잡히면 안 된다.)
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const WEB_ROOT = join(__dirname, "..", "..");
const SCAN_DIRS = ["components", "lib", "app", "hooks"];

/**
 * 실행 코드를 **외부에서 받아오는** 것이 허용된 호스트 — 사유를 반드시 적는다.
 *
 * ★이미지·지도 타일 같은 **데이터**는 여기 대상이 아니다. 이 목록은
 *   "이 호스트가 보낸 것이 우리 페이지에서 **실행**된다"는 뜻이다.
 */
const ALLOWED_EXECUTABLE_HOSTS: Record<string, string> = {
  "dapi.kakao.com":
    "카카오맵 SDK — 카카오가 자사 오리진 로드를 요구해 번들로 옮길 수 없다. " +
    "로더는 lib/kakao-map.ts 하나뿐이고 onerror·재시도 리셋을 갖췄다.",
  "t1.daumcdn.net":
    "다음 우편번호 서비스 — 벤더가 자사 배포만 지원해 번들 불가. " +
    "★버전 없는 가변 채널(prod/postcode.v2.js)이라 이 목록에서 가장 약한 고리다.",
  "unpkg.com":
    "pdf.js 워커(components/collaboration/PdfDocViewer.tsx) — pdfjs-dist 는 이미 번들 " +
    "의존성이라 워커를 동일 오리진으로 옮길 수 있다. 다만 빌드 산출물 복사와 배포 설정이 " +
    "함께 필요해 **별건으로 남겼다**. ★이 항목이 사라지는 것이 목표다(늘리지 마라).",
};

/**
 * 실행 코드를 외부에서 받아오는 대입 표기.
 *
 * ★**줄 단위로 보면 놓친다.** 실측: `PdfDocViewer` 의 `workerSrc` 대입은
 *   `=` · `process.env.… ??` · URL 이 **세 줄에 나뉘어** 있어서 줄 단위 정규식이 통과시켰다.
 *   (이 파일 주석에 *"한 가지만 보면 놓친다"* 라고 써 놓고 같은 실수를 했다.)
 *   그래서 파일 전체를 대상으로 하되 `;` 를 만나면 멈춰 **문장 경계**를 넘지 않는다.
 */
const EXTERNAL_ASSIGN =
  /\.(src|href|workerSrc)\s*=(?:[^;]{0,300}?)(?:https?:)?\/\/([a-z0-9.-]+\.[a-z]{2,})/gi;

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const e of entries) {
    if (e === "node_modules" || e === ".next") continue;
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(p)) out.push(p);
  }
  return out;
}

type Hit = { file: string; host: string; line: number };

function collectExternalLoads(): Hit[] {
  const hits: Hit[] = [];
  for (const d of SCAN_DIRS) {
    for (const abs of walk(join(WEB_ROOT, d))) {
      // ★주석·문자열 변이에 뚫리지 않도록 실행되는 줄만 본다.
      const rel = relative(WEB_ROOT, abs);
      const code = __stripCommentsForScan(readFileSync(abs, "utf-8"), rel);
      EXTERNAL_ASSIGN.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = EXTERNAL_ASSIGN.exec(code)) !== null) {
        // 줄 번호는 매치 위치로 되짚는다(여러 줄 대입을 통째로 잡기 때문).
        const line = code.slice(0, m.index).split("\n").length;
        hits.push({ file: rel, host: m[2].toLowerCase(), line });
      }
    }
  }
  return hits;
}

describe("외부 실행코드 호스트 — 파생 전수 계약", () => {
  const hits = collectExternalLoads();

  it("★전제: 스캐너가 실제로 무언가를 집는다 — 공허한 초록 방지", () => {
    // 이 단언이 **위반 단언보다 먼저** 와야 한다. 스캐너가 고장 나 0건을 돌려주면
    // 아래 "허용목록 밖 0건"은 **저절로 참**이 되어 아무것도 잠그지 않는다.
    expect(
      hits.length,
      "외부 로드를 하나도 못 찾았다 — 정규식·경로·주석 스트리퍼가 고장 났다(0건은 부재가 아니다)",
    ).toBeGreaterThan(0);
  });

  it("★양성 대조: 알려진 벤더 SDK 를 실제로 집는다", () => {
    // 스캐너가 "무언가"를 집는 것만으로는 부족하다 — **아는 것을 집는지** 확인한다.
    const hosts = new Set(hits.map((h) => h.host));
    expect(hosts, "카카오맵 SDK 로드를 못 집었다 — 스캐너가 대상을 비껴간다").toContain(
      "dapi.kakao.com",
    );
  });

  it("★허용목록 밖 호스트에서 실행코드를 받지 않는다", () => {
    const offenders = hits.filter((h) => !(h.host in ALLOWED_EXECUTABLE_HOSTS));
    expect(
      offenders.map((h) => `${h.file}:${h.line} → ${h.host}`),
      "허용되지 않은 외부 호스트에서 실행코드를 받는다 — SRI·CSP 가 없으므로 그 바이트가 그대로 실행된다",
    ).toEqual([]);
  });

  it("★죽은 허용항목을 남기지 않는다 — 목록이 실제와 어긋나면 다음 사람이 오독한다", () => {
    const live = new Set(hits.map((h) => h.host));
    for (const host of Object.keys(ALLOWED_EXECUTABLE_HOSTS)) {
      expect(
        live.has(host),
        `${host} 는 더는 외부에서 로드되지 않는다 — ALLOWED_EXECUTABLE_HOSTS 에서 지워라`,
      ).toBe(true);
    }
  });

  it("★허용 사유가 비어 있지 않다 — 부채를 뭉뚱그리지 않는다", () => {
    for (const [host, reason] of Object.entries(ALLOWED_EXECUTABLE_HOSTS)) {
      expect(reason.length, `${host} 의 사유가 너무 짧다`).toBeGreaterThan(30);
    }
  });

  it("★Leaflet 은 번들에서 온다 — CDN 회귀 방지(이 PR 이 되돌려지면 여기서 걸린다)", () => {
    const leafletHits = hits.filter((h) => /leaflet/i.test(h.file) || h.host === "unpkg.com");
    const cdnLeaflet = leafletHits.filter((h) => h.host === "unpkg.com" && /leaflet/i.test(h.file));
    expect(cdnLeaflet, "Leaflet 이 다시 CDN 에서 로드된다").toEqual([]);

    // 양성 짝 — 번들 경로가 실제로 존재하는지(부재 단언 혼자 두지 않는다).
    const loaderRel = join("lib", "leaflet-loader.ts");
    const loader = __stripCommentsForScan(
      readFileSync(join(WEB_ROOT, loaderRel), "utf-8"),
      loaderRel,
    );
    expect(loader, "공용 로더가 번들 import 를 쓰지 않는다").toContain('import("leaflet")');
    expect(loader, "공용 로더가 window.L 을 채우지 않으면 소비처 36곳이 깨진다").toContain(
      "window.L =",
    );
  });
});
