/**
 * 모달 ESC 해제 계약 (2026-08-18).
 *
 * ## 증상
 *
 * `aria-modal="true"` 를 선언하는 표면 13개(파일 11개) 중 **ESC 로 닫히는 것은 4개뿐**이었고,
 * 그 4개는 각자 `window` 에 keydown 을 걸고 있었다(실측 착수 시점):
 *   · ESC 없음 9개 — 문서뷰어·동의·입력해소·현장진입·현장비밀번호·고객카드·조직도 2종·경매 상세
 *   · 각자 리스너 4개 — 경매 라이트박스 · 삭제확인(입력 onKeyDown) · G2B 상세 · 현장앱 전체메뉴
 * 각자 리스너는 두 표면이 함께 열려 있을 때 **같은 keydown 에 둘 다 닫는다** — 사용자는 한 번
 * 눌렀는데 두 개가 사라진다(사통맵에서 이미 실측·`lib/satong-dismiss.ts` 참조).
 *
 * ## 이 파일이 잠그는 것
 *
 * ① **파생 전수** — 소스에서 `aria-modal` 선언을 긁어 표면을 스스로 모은다. 사람이 센 목록이
 *    아니므로 **새 모달이 생기면 자동으로 감시망에 들어온다**(면제는 사유와 함께 아래에 적는다).
 * ② **런타임** — 소스 검사만으로는 "주석 처리 + 임포트 유지" 변이에 뚫린다(이 저장소 2회 실증).
 *    그래서 실제 컴포넌트 2개를 겹쳐 렌더하고 ESC 를 진짜로 눌러 **위 하나만** 닫히는지 태운다.
 *
 * ## 범위 (정직 — 하지 않은 것)
 *
 * 이번 계약은 **ESC 만** 다룬다. 포커스 트랩·초기 포커스·포커스 복귀는 폼 표면(비밀번호·동의)에서
 * 회귀 위험이 커서 다음 단계로 미뤘고, 아래 `it.todo` 로 초록 안에 **보이게** 남긴다.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDeleteModal } from "@/components/common/ConfirmDeleteModal";
import ConsentModal from "@/components/desk/ConsentModal";
import { FieldMenuSheet } from "@/components/sales-app/FieldNav";
import { visibleTabs } from "@/components/sales-app/roleConfig";
import { DISMISS_Z, __dismissibleSnapshot } from "@/lib/satong-dismiss";
import { __stripCommentsForScan } from "@/lib/source-invariant";

/** apps/web 절대경로. 모듈 최상단에서 한 번만 평가한다(테스트가 cwd 를 바꾸면 흔들린다). */
const WEB_ROOT = process.cwd();

/**
 * 면제 — **왜 구멍이 아닌지**를 여기 적는다. 사유 없이 이름만 넣지 않는다.
 * (지금은 비어 있다. 비어 있는 것 자체가 "전부 배선됐다"는 뜻이다.)
 */
const EXEMPT: Record<string, string> = {};

/** 등록으로 인정하는 호출 — 훅(권장) 또는 조정기 직접 호출. */
const REGISTER_CALL = /\b(useDismissible|registerDismissible)\s*\(/g;
const ARIA_MODAL = /aria-modal/g;

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
    else if (/\.tsx$/.test(p) && !/\.test\.tsx$/.test(p) && !p.includes("__tests__")) out.push(p);
  }
  return out;
}

/**
 * 실행되는 줄만 남긴다 — 주석 속 문자열이 검사를 속이지 못하게.
 * `__stripCommentsForScan` 은 TypeScript 파서 기반이라 블록 주석·JSDoc·줄 주석을 모두 지운다
 * (2026-08-07 R3 에서 줄 주석까지 파서 간극으로 편입됐다 — 손수 정규식이 아니다).
 */
function executable(file: string): string {
  return __stripCommentsForScan(readFileSync(file, "utf8"), file);
}

type Surface = { file: string; declared: number; registered: number };

/** 소스에서 모달 표면을 **파생으로** 모은다(사람이 센 목록 금지). */
function collectSurfaces(): Surface[] {
  const files = [...walk(join(WEB_ROOT, "components")), ...walk(join(WEB_ROOT, "app"))];
  const out: Surface[] = [];
  for (const f of files) {
    const src = executable(f);
    const declared = (src.match(ARIA_MODAL) ?? []).length;
    if (declared === 0) continue;
    out.push({
      file: relative(WEB_ROOT, f).replace(/\\/g, "/"),
      declared,
      registered: (src.match(REGISTER_CALL) ?? []).length,
    });
  }
  return out.sort((a, b) => a.file.localeCompare(b.file));
}

describe("모달 ESC 해제 계약 — 소스 파생 전수", () => {
  it("전제: 표면을 실제로 모았다(공허 진리 가드)", () => {
    // ★"위반 0"이 "대상 0"이어서 참이 되는 일을 막는다. 착수 시점 실측은 파일 11 · 선언 13.
    const surfaces = collectSurfaces();
    expect(surfaces.length, "aria-modal 표면을 못 찾았다 — 스캐너가 죽었는지 먼저 의심하라").toBeGreaterThanOrEqual(10);
    const declared = surfaces.reduce((n, s) => n + s.declared, 0);
    expect(declared, "선언 총량이 줄었다 — 표면이 사라졌거나 스캐너가 덜 본다").toBeGreaterThanOrEqual(13);
  });

  it("대조군: 주석 속 선언은 세지 않는다(소스 검사가 주석에 뚫리지 않는가)", () => {
    // 이 대조가 없으면 위 수집이 "주석까지 세는" 것인지 알 수 없다.
    const commented = `// <div aria-modal="true" />\n/* aria-modal */\nconst x = 1;\n`;
    expect((__stripCommentsForScan(commented, "x.tsx").match(ARIA_MODAL) ?? []).length).toBe(0);
    // 양성대조 — 실행되는 줄의 선언은 그대로 센다(스캐너가 전부 삼키지 않는다).
    expect((__stripCommentsForScan(`<div aria-modal="true" />`, "x.tsx").match(ARIA_MODAL) ?? []).length).toBe(1);
  });

  it("★모든 모달 표면이 ESC 조정기에 등록한다(면제는 사유와 함께)", () => {
    const surfaces = collectSurfaces();
    const violations = surfaces
      .filter((s) => !EXEMPT[s.file])
      .filter((s) => s.registered < s.declared)
      .map((s) => `${s.file}: aria-modal ${s.declared}개 · 등록 ${s.registered}개`);
    expect(
      violations,
      `ESC 로 닫히지 않는 모달이 있다. useDismissible(DISMISS_Z.…, open, close) 로 등록하거나,\n` +
        `구멍이 아니라면 이 파일의 EXEMPT 에 **사유와 함께** 넣어라.\n` + violations.join("\n"),
    ).toEqual([]);
  });

  it("면제 목록의 항목은 실재하는 파일이어야 한다(죽은 면제 방지)", () => {
    const files = new Set(collectSurfaces().map((s) => s.file));
    for (const [f, reason] of Object.entries(EXEMPT)) {
      expect(files.has(f), `면제에 적힌 ${f} 가 더는 모달 표면이 아니다 — 면제를 지워라`).toBe(true);
      expect(reason.length, `면제 사유가 비었다: ${f}`).toBeGreaterThan(10);
    }
  });
});

describe("모달 ESC 해제 계약 — 런타임(겹친 모달)", () => {
  afterEach(() => {
    expect(__dismissibleSnapshot().count, "등록이 새고 있다 — 언마운트 정리가 빠졌다").toBe(0);
  });

  it("전제: 두 표면의 해제 칸이 **실제로 다른 값**이다", () => {
    // ★같은 값이면 배선을 끊어도 결과가 같아 잠금이 되지 않는다(픽스처가 두 모집단을 갈라야 한다).
    expect(DISMISS_Z.nestedOverModal).toBeGreaterThan(DISMISS_Z.appModal);
  });

  it("★ESC 1회 = **위에 겹친 확인창만** 닫힌다 — 아래 모달은 살아남는다", () => {
    const closeBase = vi.fn(); // ConsentModal(appModal)
    const closeTop = vi.fn(); // ConfirmDeleteModal(nestedOverModal)
    const view = render(
      <>
        <ConsentModal onConfirm={() => {}} onCancel={closeBase} />
        <ConfirmDeleteModal open name="대상" onConfirm={() => {}} onCancel={closeTop} />
      </>,
    );

    // 공허 진리 가드 — 두 표면이 정말 등록됐는지 먼저 본다(안 열렸는데 "위반 0"이면 무의미).
    expect(__dismissibleSnapshot().count, "두 모달이 조정기에 등록되지 않았다").toBe(2);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(closeTop, "위에 겹친 확인창이 안 닫혔다").toHaveBeenCalledTimes(1);
    expect(closeBase, "★아래 모달까지 같이 닫혔다 — 종전 결함(ESC 한 번에 둘 다) 그대로다").not.toHaveBeenCalled();

    view.unmount();
  });

  it("다음 ESC 가 아래 모달을 닫는다(단계적 해제)", () => {
    const closeBase = vi.fn();
    const view = render(<ConsentModal onConfirm={() => {}} onCancel={closeBase} />);
    expect(__dismissibleSnapshot().count).toBe(1);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(closeBase).toHaveBeenCalledTimes(1);

    view.unmount();
  });

  it("닫힌 모달은 ESC 를 먹지 않는다(음성대조)", () => {
    // open=false 인데 등록돼 있으면, 보이지도 않는 모달이 ESC 를 삼켜 위 표면이 안 닫힌다.
    const closeTop = vi.fn();
    const view = render(<ConfirmDeleteModal open={false} name="대상" onConfirm={() => {}} onCancel={closeTop} />);
    expect(__dismissibleSnapshot().count, "닫힌 모달이 등록돼 있다").toBe(0);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(closeTop).not.toHaveBeenCalled();
    view.unmount();
  });

  it("★★이관 회귀: 전체메뉴 시트 위에 모달이 열리면 **모달이 먼저** 닫힌다", () => {
    // 종전 FieldNav 는 자기 window 리스너로 ESC 를 받았다 — 같은 keydown 에 시트와 모달이
    // **함께** 닫혔다. 이관 후에는 시트가 낮은 칸(navSheet)이라 차례를 양보한다.
    const closeSheet = vi.fn();
    const closeModal = vi.fn();
    const tabs = visibleTabs(["dashboard", "units", "customers"]);
    const view = render(
      <>
        <FieldMenuSheet open tabs={tabs} activeTab="home" onNavigate={() => {}} onClose={closeSheet} />
        <ConsentModal onConfirm={() => {}} onCancel={closeModal} />
      </>,
    );
    expect(__dismissibleSnapshot().count, "시트와 모달이 함께 등록돼 있어야 한다").toBe(2);
    // 픽스처가 두 모집단을 실제로 가르는지 확인 — 같은 값이면 배선을 끊어도 결과가 같다.
    expect(__dismissibleSnapshot().zs).toEqual([DISMISS_Z.navSheet, DISMISS_Z.appModal]);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(closeModal, "모달이 안 닫혔다").toHaveBeenCalledTimes(1);
    expect(closeSheet, "★시트까지 같이 닫혔다 — 이관 전 결함 그대로다").not.toHaveBeenCalled();

    view.unmount();
  });

  it("ESC 가 아닌 키는 무시한다(판별력 대조군)", () => {
    const closeBase = vi.fn();
    const view = render(<ConsentModal onConfirm={() => {}} onCancel={closeBase} />);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(closeBase, "아무 키에나 닫히면 이 계약은 판별력이 없다").not.toHaveBeenCalled();
    view.unmount();
  });
});

describe("모달 접근성 — 다음 단계(미구현 부채)", () => {
  // ★부채는 커밋 메시지가 아니라 여기 남긴다 — 초록 안에 보여야 다음 사람이 안다.
  //   착수 시점 실측: 포커스 트랩·초기 포커스·포커스 복귀는 11개 표면 **전부 0/11**.
  it.todo("모든 모달이 열릴 때 내부 첫 요소로 포커스를 옮긴다(초기 포커스)");
  it.todo("모든 모달이 Tab/Shift+Tab 을 모달 안에 가둔다(포커스 트랩)");
  it.todo("모달이 닫히면 열기 전 눌렀던 요소로 포커스가 돌아간다(포커스 복귀)");
});
