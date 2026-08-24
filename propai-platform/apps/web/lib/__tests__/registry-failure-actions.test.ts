/**
 * 실패를 **작업 목록**으로 — 예외 계층 제품화 계약.
 *
 * 100% 가 구조상 불가능한 세계(체인은 곱셈이다)에서 완성도를 가르는 것은
 * **남는 실패를 어떻게 다루는가**다. 성공률이 같아도 "분석 불가"는 막다른 길이고
 * "12건이 이 사유로 안 됐습니다 — 이렇게 하면 됩니다"는 작업 목록이다.
 *
 * ## 볼트 선례를 그대로 검증 항목으로 옮긴다 (2026-08-02 W3)
 *
 * 1. **"부실할수록 깨끗해 보이는 역선택"** — 분류가 실패를 못 세면 화면이 **오히려 깨끗해진다**.
 *    → 실패 건수는 분류와 **무관하게** 보존돼야 한다(합이 맞는지 단언).
 * 2. **"대체 지표도 같은 착시를 재생산한다 — 대체안에 원 결함의 실패 시나리오를 대입하라."**
 *    → 원 결함(폴백이 성공처럼 보임: `ai` 는 dict 인데 `generated:false`)을 이 새 분류기에
 *      그대로 넣어 본다.
 * 3. **빈 컨테이너 착시** — "실패 0"과 "아직 분석 안 함"은 다르다.
 */
import { describe, expect, it } from "vitest";

import {
  FAILURE_ACTION_INFO,
  failureAction,
  groupFailures,
  type BatchOutcome,
} from "@/lib/registry-analyze";

const 성공: BatchOutcome = { jibun: "가", result: { status: "ok", ai: { generated: true } } };
const 해석실패: BatchOutcome = {
  jibun: "내삼미동 448-2",
  result: { status: "ok", ai: { generated: false, failure_reason: "JSONDecodeError: Unterminated" } },
};
const 본문미확보: BatchOutcome = {
  jibun: "나",
  result: { status: "empty", message: "등기부 본문(갑구·을구)을 확보하지 못했습니다. 발급 PDF가 이미지 형식이면…" },
};
const 잔액부족: BatchOutcome = {
  jibun: "다",
  result: { status: "error", message: "하이픈 민원캐시 잔액이 부족합니다" },
};
const 번지없음: BatchOutcome = {
  jibun: "라",
  result: { status: "error", message: '"경기도 오산시 내삼미동" 에는 번지가 없어 등기부를 특정할 수 없습니다' },
};
const 요청실패: BatchOutcome = { jibun: "마", result: null };
const 사유없음: BatchOutcome = { jibun: "바", result: { status: "error" } };

describe("failureAction — 무엇을 할 수 있는가", () => {
  it("★원 결함 시나리오를 그대로 대입한다 — 폴백은 성공이 아니라 **해석 재시도** 대상이다", () => {
    // 볼트 교훈 2: 대체 지표에 원 결함을 대입해 본다.
    expect(failureAction(해석실패)).toBe("reinterpret");
    expect(FAILURE_ACTION_INFO.reinterpret.canRetry).toBe(true);
  });

  it("★사유마다 다른 조치로 갈린다(전부 unknown 으로 뭉개지지 않는다)", () => {
    const got = [본문미확보, 잔액부족, 번지없음, 요청실패, 해석실패].map(failureAction);
    expect(got).toEqual(["enter_manually", "recharge", "fix_jibun", "retry", "reinterpret"]);
    expect(new Set(got).size, "조치가 뭉개졌다 — 목록이 정보가 아니게 된다").toBe(5);
  });

  it("사유를 못 받으면 **지어내지 않고** unknown 이다", () => {
    expect(failureAction(사유없음)).toBe("unknown");
  });

  it("★재시도가 실제로 가능한 것만 canRetry 다(할 수 없는 일을 버튼으로 만들지 않는다)", () => {
    expect(FAILURE_ACTION_INFO.enter_manually.canRetry).toBe(false);
    expect(FAILURE_ACTION_INFO.fix_jibun.canRetry).toBe(false);
    expect(FAILURE_ACTION_INFO.recharge.canRetry).toBe(false);
  });

  it("★해석 재시도 안내가 **무과금을 단정하지 않는다**", () => {
    // 발급 재사용은 프로세스 단위·6시간이라 보장이 아니다.
    // 보장할 수 없는 것을 보장으로 말하면 그 자체가 거짓이 된다.
    const h = FAILURE_ACTION_INFO.reinterpret.hint;
    expect(h).toContain("남아 있으면");
    expect(h).not.toContain("무과금");
    expect(h).not.toContain("비용이 들지 않습니다");
  });

  it("모든 조치에 라벨과 안내가 있다(빈 안내는 막다른 길과 같다)", () => {
    for (const [k, v] of Object.entries(FAILURE_ACTION_INFO)) {
      expect(v.label.length, `${k} 라벨 없음`).toBeGreaterThan(1);
      expect(v.hint.length, `${k} 안내 없음`).toBeGreaterThan(10);
    }
  });
});

describe("groupFailures — 조치별로 묶는다", () => {
  const all = [성공, 해석실패, 해석실패, 본문미확보, 잔액부족, 요청실패];

  it("★성공 건은 들어오지 않는다", () => {
    const g = groupFailures(all);
    expect(g.flatMap((x) => x.items).some((x) => x.result?.ai?.generated)).toBe(false);
  });

  it("★★실패 건수가 분류와 무관하게 **보존**된다(부실할수록 깨끗해 보이는 역선택 방지)", () => {
    // 볼트 교훈 1: 분류가 실패를 못 세면 화면이 오히려 깨끗해진다.
    const g = groupFailures(all);
    const failed = all.length - all.filter((x) => x.result?.ai?.generated).length;
    expect(g.reduce((n, x) => n + x.count, 0), "묶는 과정에서 실패가 사라졌다").toBe(failed);
  });

  it("많은 순으로 정렬하고 대표 사유를 붙인다", () => {
    const g = groupFailures(all);
    expect(g[0].action).toBe("reinterpret");
    expect(g[0].count).toBe(2);
    expect(g[0].reason).toContain("JSONDecodeError");
  });

  it("★대조군 — 전부 성공이면 빈 배열(없는 작업을 만들지 않는다)", () => {
    expect(groupFailures([성공, 성공])).toEqual([]);
  });

  it("★'실패 0'과 '아직 분석 안 함'은 화면이 구분해야 한다 — 둘 다 빈 배열이다", () => {
    // 볼트 교훈 3(빈 컨테이너 착시): 이 함수만으로는 구분할 수 없다.
    // 그래서 화면은 **items 길이**를 함께 봐야 한다 — 그 사실을 여기 못 박는다.
    expect(groupFailures([])).toEqual([]);
    expect(groupFailures([성공])).toEqual([]);
  });
});

describe("배선 — 화면이 실제로 이 패널을 쓰고 재시도를 넘긴다", () => {
  const read = async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { __stripCommentsForScan } = await import("@/lib/source-invariant");
    const rel = "components/operations/RegistryAnalysisWorkspaceClient.tsx";
    return __stripCommentsForScan(fs.readFileSync(path.resolve(__dirname, "../..", rel), "utf8"), rel);
  };

  it("전제: 대상 파일을 읽었고 일괄 결과 블록이 있다(공허한 초록 방지)", async () => {
    const src = await read();
    expect(src.length).toBeGreaterThan(1000);
    expect(src).toMatch(/batchResults/);
  });

  it("★패널을 실제로 그린다", async () => {
    expect(await read()).toMatch(/<RegistryFailureActions\b/);
  });

  it("★★재시도를 실제로 넘긴다 — 이 한 줄이 빠지면 버튼이 아예 안 나온다", async () => {
    // 변이 감사에서 이 줄(`onRetry={…}`) 삭제가 **생존**했다. 패널은 잠겼는데
    // 페이지가 그것을 연결하는 부분이 무잠금이었다.
    expect(await read()).toMatch(/onRetry=\{/);
  });

  it("★재시도가 **행 id로 그 행을 되찾는다**(지번만으로 돌리면 대표값이 섞인다)", async () => {
    const src = await read();
    expect(src).toMatch(/rows\.find\(/);
    expect(src).toMatch(/b\.rowId/);
  });
});
