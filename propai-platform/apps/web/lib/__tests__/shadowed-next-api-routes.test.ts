/**
 * ★프로덕션에서 **도달 불가한 Next 라우트**를 프론트가 부르는 것을 막는다.
 *
 * 【실장애 2026-08-17 · 선재 결함(2026-07-29 에 이미 티켓화돼 있었다)】
 * `4t8t.net/api/*` 는 nginx/프록시가 **백엔드(FastAPI)** 로 보낸다. 그래서
 * `apps/web/app/api/**\/route.ts` 로 정의한 Next 라우트는 프로덕션에서 **절대 실행되지 않고**
 * 백엔드가 `{"detail":"Not Found"}` 404 를 돌려준다.
 *
 *   실측: 4t8t.net/api/v1/tiles/vworld/wms → 200(백엔드가 응답)
 *         4t8t.net/api/health              → 404   ← Next 라우트인데 가려짐
 *         4t8t.net/tiles/vworld/wmts/...   → 200   ← `/api/` **밖**이라 살아 있음
 *
 * 살아 있는 지적·배경 타일이 `/tiles/*` 에 있어서 그것만 멀쩡했다. 반면 AVM 항공영상은
 * `/api/vworld/data` 를 불러 **404 를 조용히 삼켰다**(`onError` → "생략됩니다" 문구).
 * 오류가 사양처럼 보여 아무도 결함으로 보지 않았다.
 *
 * 【이 락이 잠그는 것】"그 한 건"이 아니라 **패턴**이다.
 * · 대상(라우트)은 `app/api/**\/route.ts` 에서 **파생**한다 — 새 Next api 라우트가 생기면 자동 편입.
 * · 소비처도 `app/`·`components/`·`lib/`·`hooks/` 전수에서 **파생**한다 — 손으로 고른 목록이 아니다.
 * ★파생의 축을 명시한다: **(라우트=파일 단위) × (소비처=파일 단위 전수 스캔)**.
 *   한 층 위가 목록형이면 파생이 무의미해지므로, 어느 쪽도 손으로 고르지 않는다.
 *
 * 【주석 면역】소스 스캔은 주석 처리 변이에 뚫린다(이 저장소에서 2회 실증). 그래서
 * `__stripCommentsForScan` 을 경유해 **실행되는 줄만** 본다.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

// ── 저장소 전수 스캔 테스트의 시간 상한 ──────────────────────────────────────
//  이 파일은 `it` 안에서 저장소의 **모든 소스 파일(약 941개)** 을 다시 읽는다. 그래서 실행
//  시간이 **검증 대상의 성질이 아니라 그때의 CPU 경합**에 좌우된다 — 전체 스위트를 돌리면
//  워커가 붙는 만큼 느려져 기본 10초를 넘고, 단독 실행은 항상 통과한다(실측: 실패는 전부
//  `Test timed out in 10000ms` 이고 비타임아웃 실패는 0건). CI 는 더 느릴 수 있다.
//  ★10초는 **정확성 경계가 아니라 벽시계**다. 늘려도 잡아내는 결함은 그대로다.
//  ★근본 처방은 941파일 읽기를 모듈 스코프로 호이스팅하는 것이고, 별건으로 남겼다.
vi.setConfig({ testTimeout: 60_000 });


const WEB_ROOT = join(__dirname, "..", "..");

/**
 * 실행되는 줄만 남긴다.
 *
 * ★`__stripCommentsForScan` 은 **블록 주석만** 지운다(줄 주석은 남는다). 이 저장소는
 *   "판정을 파서에게 넘겼다"고 선언해 놓고 **같은 함수의 다른 절반(줄 주석)** 을 손수
 *   정규식으로 남겨 배선 락 2개가 관통된 이력이 있다(CLAUDE.md §D20). 그래서 여기서
 *   줄 주석도 함께 지운다.
 * ★`https://` 의 `//` 를 주석으로 오인하면 **정상 코드를 삼켜 거짓 초록**이 된다 —
 *   앞에 `:` 가 붙지 않은 `//` 만 주석으로 본다.
 * ★한계(정직 고지): 문자열 리터럴 **안에** 들어 있는 `//`(예: `"a // b"`)는 여전히
 *   주석으로 오인될 수 있다. 이 스캐너의 판정은 "위반 있음"이 아니라 "위반 없음" 쪽으로
 *   기울므로(덜 본다), 위양성이 아니라 **위음성** 방향의 한계다.
 */
function executableSource(file: string): string {
  const noBlock = __stripCommentsForScan(readFileSync(file, "utf8"), file);
  return noBlock.replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const e of entries) {
    if (e === "node_modules" || e === ".next" || e === "dist") continue;
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

/**
 * 면제 — **왜 구멍이 아닌지**를 여기 적는다(면제 목록에 사유 없이 넣지 않는다).
 *
 * `/api/proxy/[...path]` 는 **로컬 개발 전용으로 의도된** 라우트다. 소비처 3곳을 실측했고
 * 전부 프로덕션에서는 이 경로로 가지 않는다:
 *   · `lib/land/desk-appraisal.ts:18-22`  — 호스트가 4t8t.net/propai.kr/*.pages.dev 면 `api.4t8t.net` 직행
 *   · `components/report/BankReadyReportBuilder.tsx:425` — `apiBaseUrl || "/api/proxy"`
 *   · `components/report/ReportDownloadMenu.tsx:52`      — `runtimeConfig.apiBaseUrl || "/api/proxy"`
 * 뒤 둘은 **`apiBaseUrl` 이 비었을 때만** 폴백한다. 프로덕션 158 컨테이너에는
 * `NEXT_PUBLIC_API_BASE_URL` 이 설정돼 있어(실측) 비지 않는다.
 *
 * ★그래서 이 면제는 "안전"이 아니라 **조건부**다 — 그 env 가 비면 이 세 곳은 404 를 맞는다.
 *   즉 여기 적힌 근거가 깨지는 순간 면제도 깨진다. env 가 사라지면 이 면제를 지워라.
 */
const EXEMPT_DEV_ONLY = ["/api/proxy"];

/** 프로덕션에서 백엔드에 가려지는 Next 라우트 경로를 **파일에서 파생**한다. */
function shadowedRoutePaths(): string[] {
  const apiDir = join(WEB_ROOT, "app", "api");
  return walk(apiDir)
    .filter((f) => /[\\/]route\.tsx?$/.test(f))
    .map((f) => {
      const rel = relative(apiDir, f).replace(/\\/g, "/").replace(/\/route\.tsx?$/, "");
      // 동적 세그먼트는 접두만 비교한다([...path] · [layer] 등)
      const firstDynamic = rel.split("/").findIndex((s) => s.startsWith("["));
      const segs = rel.split("/");
      return "/api/" + (firstDynamic === -1 ? rel : segs.slice(0, firstDynamic).join("/"));
    })
    .filter((p) => p !== "/api/")
    .filter((p) => !EXEMPT_DEV_ONLY.includes(p));
}

/** 소비처 전수 — 스캔 대상 파일도 **파생**한다(손으로 고르지 않는다). */
function scanTargets(): string[] {
  return ["app", "components", "lib", "hooks"]
    .flatMap((d) => walk(join(WEB_ROOT, d)))
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .filter((f) => !/\.(test|spec)\.tsx?$/.test(f))
    // 라우트 정의 자신은 소비처가 아니다.
    .filter((f) => !/[\\/]app[\\/]api[\\/].*[\\/]route\.tsx?$/.test(f));
}

describe("프로덕션에서 가려지는 Next /api 라우트를 프론트가 부르지 않는다", () => {
  const routes = shadowedRoutePaths();
  const files = scanTargets();

  it("전제: 스캔 대상이 실제로 존재한다(공허한 초록 방지)", () => {
    // ★대상이 0 개면 아래 "위반 0"은 공허한 참이 된다 — 하한을 먼저 단언한다.
    expect(routes.length, "app/api 라우트를 하나도 못 찾았다 — 조회기가 죽었다").toBeGreaterThan(0);
    expect(files.length, "스캔할 소스 파일을 못 찾았다 — 조회기가 죽었다").toBeGreaterThan(100);
  });

  it("★가려진 라우트를 fetch/src 로 부르는 실행 코드가 없다", () => {
    const violations: string[] = [];
    for (const file of files) {
      const src = executableSource(file);
      for (const route of routes) {
        // 문자열 리터럴 안에서 그 경로로 **시작**하는 URL 만 위반으로 본다.
        const re = new RegExp(`["'\`]${route.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:[/?"'\`]|$)`);
        if (re.test(src)) violations.push(`${relative(WEB_ROOT, file)} → ${route}`);
      }
    }
    expect(violations, `프로덕션에서 404 가 되는 경로를 부른다:\n${violations.join("\n")}`).toEqual([]);
  });

  it("대조군: 살아 있는 경로(/tiles/*)는 위반으로 잡히지 않는다", () => {
    // ★위양성도 결함이다. 정상 코드를 막으면 그것도 고쳐야 할 결함이다(이 저장소에서 2회 재발).
    // `/tiles/vworld/wms` 는 `/api/` 밖이라 살아 있고, 실제로 14곳이 쓴다.
    const live = files.filter((f) =>
      /["'`]\/tiles\/vworld\//.test(executableSource(f)),
    );
    expect(live.length, "대조군이 0 이면 이 테스트는 아무것도 구분하지 못한다").toBeGreaterThan(0);
    // 그 파일들이 위 규칙에 걸리지 않아야 한다 = 두 모집단이 실제로 갈린다.
    for (const f of live) {
      const src = executableSource(f);
      for (const route of routes) {
        const re = new RegExp(`["'\`]${route.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:[/?"'\`]|$)`);
        expect(re.test(src), `${relative(WEB_ROOT, f)} 가 대조군인데 위반으로 잡혔다`).toBe(false);
      }
    }
  });
});
