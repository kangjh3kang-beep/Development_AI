/**
 * LLM 서비스 라벨 SSOT 계약.
 *
 * 왜: 같은 엔드포인트(`/billing/token-usage`)를 쓰는 두 화면이 라벨표를 **각자 선언**해
 * 키 집합이 갈렸고, **마이페이지 사용량(일반 사용자)** 이 서비스명을 영문 raw 로 보여 줬다.
 * 라이브 실측 2026-08-26: service 값 11종 중 그 표는 **1종만** 덮었고,
 * 토큰 가중 **63.3%** 가 raw 로 렌더됐다.
 *
 * ★이 파일이 잠그는 것은 "라벨이 예쁜가"가 아니라 **"표가 갈리지 않는가"** 다.
 *   그래서 ①백엔드 소스에서 **파생**하고 ②배선을 **렌더 경로가 아닌 소스**로 확인하되
 *   주석을 걷어내고 본다.
 */

import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  LLM_SERVICE_LABELS,
  OBSERVED_LLM_SERVICES,
  llmServiceLabel,
} from "../llm-service-labels";

const WEB = path.resolve(__dirname, "../..");
const API = path.resolve(WEB, "../api");

/** `.py` 전수 수집 — ★목록형이 아니라 **파생형**. 새 파일이 자동으로 들어온다. */
function pythonFiles(dir: string, out: string[] = []): string[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    // ★테스트 경로는 제외한다 — 픽스처의 가짜 service 값까지 라벨을 요구하면 위양성이다.
    if (e.isDirectory()) {
      if (e.name === "tests" || e.name === "node_modules" || e.name === "__pycache__") continue;
      pythonFiles(path.join(dir, e.name), out);
    } else if (e.name.endsWith(".py")) {
      out.push(path.join(dir, e.name));
    }
  }
  return out;
}

/** 프로덕션 소스의 `service="..."` / `service='...'` 리터럴 전수. */
function derivedServiceLiterals(): Set<string> {
  const re = /service=["']([a-z][a-z0-9_]*)["']/g;
  const found = new Set<string>();
  for (const f of pythonFiles(API)) {
    const src = fs.readFileSync(f, "utf-8");
    for (const m of src.matchAll(re)) found.add(m[1]);
  }
  return found;
}

describe("LLM 서비스 라벨 SSOT", () => {
  it("★파생기가 살아 있다 — 백엔드에서 리터럴을 실제로 뽑는다", () => {
    const lits = derivedServiceLiterals();
    // 대조군: 반드시 있어야 할 것. 없으면 경로/정규식이 죽은 것이지 "리터럴이 없는" 게 아니다.
    expect(lits.has("verifier"), "파생기 사망 — API 소스를 읽지 못했다").toBe(true);
    expect(lits.size).toBeGreaterThanOrEqual(10);
  });

  it("백엔드 소스 리터럴이 **전부** 라벨을 갖는다", () => {
    const missing = [...derivedServiceLiterals()].filter((s) => !(s in LLM_SERVICE_LABELS)).sort();
    expect(
      missing,
      `백엔드에 새 service 리터럴이 생겼는데 라벨이 없다 → 화면에 영문 raw 가 나간다: ${missing.join(", ")}`,
    ).toEqual([]);
  });

  it("라이브에서 관측된 값이 **전부** 라벨을 갖는다", () => {
    // ★소스 파생은 **하한**이다 — avm·cost·feasibility·market·site_analysis 는
    //   변수로 전달돼 리터럴에 없다. 그래서 관측 집합을 따로 둔다.
    const missing = OBSERVED_LLM_SERVICES.filter((s) => !(s in LLM_SERVICE_LABELS));
    expect(missing, `관측값에 라벨이 없다: ${missing.join(", ")}`).toEqual([]);
  });

  it("★관측 집합이 소스 파생의 부분집합이 아니다 — 둘 다 필요하다는 증명", () => {
    // 이 단언이 깨지면 관측 집합은 장식이 되고, 소스 파생만으로 충분해진다.
    // 그때는 이 테스트를 지우는 게 맞다(지금은 아니다).
    const lits = derivedServiceLiterals();
    const onlyObserved = OBSERVED_LLM_SERVICES.filter((s) => !lits.has(s));
    expect(onlyObserved.length, "관측 전용 값이 사라졌다면 관측 집합을 재측정하라").toBeGreaterThan(0);
  });

  describe("llmServiceLabel", () => {
    it("아는 값은 한글 라벨을 준다", () => {
      expect(llmServiceLabel("site_analysis")).toBe("부지 분석");
      expect(llmServiceLabel("market")).toBe("시장 분석");
    });

    it("★모르는 값은 raw 를 그대로 두지 않고 읽을 수 있게 만든다", () => {
      const out = llmServiceLabel("brand_new_service");
      expect(out).not.toBe("brand_new_service"); // 종전 `?? k` 동작
      expect(out).toBe("Brand New Service");
    });

    it("빈 값은 미분류", () => {
      expect(llmServiceLabel("")).toBe("미분류");
      expect(llmServiceLabel("   ")).toBe("미분류");
    });
  });

  describe("배선 — 두 화면이 SSOT 를 쓰고, 자기 표를 다시 만들지 않는다", () => {
    const screens = [
      "components/mypage/UsageClient.tsx",
      "components/settings/AiTokenUsageDashboard.tsx",
    ];

    it.each(screens)("%s 가 llmServiceLabel 을 호출한다", (rel) => {
      const src = fs.readFileSync(path.join(WEB, rel), "utf-8");
      // 주석에 적어 두고 배선했다고 착각하는 것을 막는다.
      const code = src
        .split("\n")
        .filter((l) => !l.trim().startsWith("//") && !l.trim().startsWith("*"))
        .join("\n");
      expect(code).toContain("llmServiceLabel(");
      // 대조군: 이 조회기가 살아 있는가(반드시 있는 형제 토큰).
      expect(code, "조회기 사망 — 파일을 제대로 읽지 못했다").toContain("import");
    });

    it.each(screens)("%s 가 자기만의 SERVICE_LABELS 표를 선언하지 않는다", (rel) => {
      const src = fs.readFileSync(path.join(WEB, rel), "utf-8");
      expect(
        /const\s+SERVICE_LABELS\s*(:|=)/.test(src),
        "화면이 다시 자기 표를 만들면 SSOT 가 무의미해진다",
      ).toBe(false);
    });
  });
});
