/**
 * ★★**배선 락** — 두 패널이 실제로 앱에 **붙어 있는가**.
 *
 * 【왜 · 2026-09-09 적대 리뷰 A-2】
 * 백엔드는 `test_module_is_registered_on_the_sales_router` 로 `include_router` 인자를 잠갔는데
 * **프론트에는 대응하는 배선 락이 없었다.** 실측:
 *
 *     &lt;DiscoverSitesPanel /&gt;  →  &lt;&gt;&lt;/&gt;   (SiteListClient.tsx)
 *         Tests 12 passed   ::VERDICT=SURVIVED
 *
 * 패널을 앱에서 **통째로 떼어내도** 패널 자신의 락 8건은 전부 초록이다 —
 * 그 락들은 패널을 **직접 렌더**하기 때문이다. 저장소 메모리의
 * «변이를 함수 안에만 넣으면 5/5 CAUGHT 인데 배선은 무잠금» 이 그대로 재현됐다.
 *
 * 【축】 부모 컴포넌트를 **렌더**하는 것이 가장 강하지만, `SiteListClient`·`SiteWorkspaceClient`
 * 는 next/navigation·다수 API·탭 상태를 끌고 와 락이 무거워진다(무거우면 안 쓴다).
 * 그래서 **JSX 사용 지점**을 소스에서 파생해 본다 — 「임포트했다」가 아니라
 * **「`&lt;Panel ...&gt;` 로 실제로 그린다」** 를 요구한다.
 * ★임포트만 남기고 렌더를 지우는 변이가 이 축의 진짜 시험이고, 그것이 이 락의 존재 이유다.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "../../..");

function source(rel: string): string {
  return readFileSync(path.join(ROOT, rel), "utf8");
}

/** 주석을 걷어낸 **실행 줄**만 — 주석 처리된 JSX 에 뚫리지 않게. */
function codeOnly(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((l) => l.replace(/\/\/.*$/, ""))
    .join("\n");
}

const MOUNTS: Array<{ panel: string; host: string; why: string }> = [
  {
    panel: "DiscoverSitesPanel",
    host: "components/sales-app/SiteListClient.tsx",
    why: "「등록 안 된 현장」이 안 붙으면 신청 자체가 화면에 없다",
  },
  {
    panel: "JoinRequestsPanel",
    host: "components/sales-app/SiteWorkspaceClient.tsx",
    why: "승인 화면이 안 붙으면 신청은 되는데 **아무도 결정할 수 없다**",
  },
];

describe("배선 — 패널이 앱에 실제로 붙어 있는가", () => {
  it("대조군: 호스트 파일을 읽고 있다(조회기 생존)", () => {
    for (const { host } of MOUNTS) {
      const src = codeOnly(source(host));
      // 반드시 있어야 할 것 — 없으면 경로가 틀렸거나 파일이 비었다.
      expect(src, `${host} 를 못 읽는다`).toContain("export default function");
    }
  });

  it.each(MOUNTS)("★$panel 이 $host 에서 **렌더**된다", ({ panel, host, why }) => {
    const src = codeOnly(source(host));
    expect(src, `${panel} 를 임포트하지 않는다 — ${why}`).toContain(
      `@/components/sales-app/${panel}`,
    );
    // ★「임포트했다」가 아니라 **「그린다」**. 임포트만 남기고 JSX 를 지우는 변이를 잡는다.
    expect(
      new RegExp(`<${panel}[\\s/>]`).test(src),
      `${panel} 를 임포트만 하고 그리지 않는다 — ${why}`,
    ).toBe(true);
  });

  it.each(MOUNTS)("★★$panel 이 **상수 거짓 게이트 뒤에 숨지 않는다**", ({ panel, host }) => {
    // ★2026-09-09 R2 리뷰 J-4: 앞 판의 축은 «`<Panel` 텍스트가 있는가» 뿐이라
    //   `{false && <Panel/>}` 로 **안 그리게 만들어도 초록**이었다(::VERDICT=SURVIVED).
    //   존재를 잠그면 행위는 안 잠긴다 — 그 형태를 여기서 직접 막는다.
    //   ★기계 변이는 「삭제」 축만 만들므로 이 형태는 도구가 영원히 못 낸다(손으로 넣어야 한다).
    const src = codeOnly(source(host));
    const idx = src.indexOf(`<${panel}`);
    expect(idx, `${panel} 을 그리는 자리를 못 찾았다`).toBeGreaterThan(-1);

    // 그 JSX 바로 앞 120자에 상수 거짓 게이트가 있으면 렌더되지 않는다.
    const before = src.slice(Math.max(0, idx - 120), idx);
    for (const dead of ["false &&", "false&&", "null &&", "0 &&"]) {
      expect(before.includes(dead), `${panel} 이 \`${dead}\` 뒤에 숨어 렌더되지 않는다`).toBe(false);
    }
  });

  it("★승인 패널은 **사유를 사람 말로 옮기는 공용 모듈**을 쓴다", () => {
    // 형제 문(JobMarketPanel)이 쓰는 그것을 새 문도 쓴다 — 번역표가 두 벌이 되면 하나가 낡는다.
    const src = codeOnly(source("components/sales-app/JoinRequestsPanel.tsx"));
    expect(src).toContain("@/lib/sales-app/membership-reason");
    expect(src).toContain("membershipNote(");
    // ★그 사유가 **어디서 오는지**까지 — 응답을 안 읽으면 유령 상태가 그대로 남는다.
    expect(src).toContain("membership_reason");
    expect(src).toContain("membership_linked");
  });
});
