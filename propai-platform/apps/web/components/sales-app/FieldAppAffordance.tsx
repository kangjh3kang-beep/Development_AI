"use client";

/**
 * 현장앱 셸 헤더의 **앱 어포던스** 단추 하나(DESIGN.md B3.3).
 *
 * ## 왜 컴포넌트로 꺼냈나
 *
 * 종전엔 `SiteWorkspaceClient` 헤더에 **인라인**으로 박혀 있었고 조건이 하나도 없어
 * **앱 안에서도 계속 떴다**(2026-09-07 사용자 신고). 인라인인 채로는 락이 그 셸 전체를
 * 렌더해야 해서 *"검사는 있는데 대상이 없어 통과"* 하기 쉽다 — **판정을 꺼내 직접 태운다.**
 *
 * ## 무엇을 내는가 (세 갈래)
 *
 *   이미 앱 안(standalone 또는 별도 창)   → **아무것도 내지 않는다**
 *   설치 프롬프트가 가능한 환경           → 「앱 설치」 (설치본만이 진짜 앱이다)
 *   그 밖                                  → 「별도 창으로 열기」
 *
 * ★라벨이 「앱으로 열기」가 아닌 이유: `window.open` 은 앱이 아니다. 현대 브라우저는 팝업에서
 *   `location=no` 를 무시해 **주소창이 남는다**(2026-09-07 라이브 실측 — 사용자 스크린샷).
 *   종전 주석은 *"브라우저 크롬 없는 팝업(주소창 숨김)"* 이라 단언했으나 거짓이었다.
 *   **라벨은 실제로 일어나는 일을 말한다.**
 */

import { AppWindow } from "lucide-react";
import { usePwaRuntime } from "@/components/pwa/PwaRuntimeProvider";
import { FIELD_APP_WINDOW_NAME, useFieldAppShell } from "@/lib/field-app-shell";

/*
 * ★변이 생존 설명(2026-09-07 · scripts/mutate_changed.py 45변이 · 생존 28) — 구멍이 아닌 이유.
 *   ① `className` 문자열 변경 다수 — **표기**이지 계약이 아니다. 문구·스타일까지 단언하면
 *      다듬을 때마다 깨지는 취약한 락이 된다(이 저장소가 명시적으로 경계하는 형태).
 *   ② `typeof window === "undefined"` 의 문자열 변경 — **SSR 방어**라 jsdom 에서는 도달 불가.
 *      이 축은 여기서 잴 수 없다(미측정이지 무잠금이 아니다).
 *   ③ `"use client"` 변경 — 빌드 지시자라 vitest 가 태우지 않는다.
 *   ★반면 **설명할 수 없던 생존 둘**(설치 onClick 삭제 · 팝업 차단 폴백)은 그대로 두지 않고
 *     락을 추가했다 — 그것이 진짜 구멍이었다.
 */
export default function FieldAppAffordance() {
  const { inAppShell } = useFieldAppShell();
  const { installState, requestInstall } = usePwaRuntime();

  // ★이미 앱 안이면 어느 쪽도 노출하지 않는다 — 형제 InstallGuide 와 **같은 판별자**다.
  if (inAppShell) return null;

  // 네이티브 설치 프롬프트가 가능한 환경에서만 설치를 먼저 권한다.
  // iOS Safari 는 beforeinstallprompt 가 **없어** 여기서 항상 거짓이고,
  // 수동 안내(공유→홈 화면 추가)는 InstallGuide 가 단계별로 낸다(플랫폼 분기 — MDN).
  if (installState === "available") {
    return (
      <button
        onClick={() => void requestInstall()}
        className="inline-flex min-h-[40px] items-center gap-1 rounded-lg border border-[var(--accent-strong)] bg-[var(--accent-soft)] px-3.5 text-xs font-black text-[var(--accent-strong)] transition hover:opacity-90 active:scale-95"
      >
        <AppWindow className="size-4" aria-hidden /> 앱 설치
      </button>
    );
  }

  return (
    <button
      onClick={() => {
        if (typeof window === "undefined") return;
        const w = Math.min(1440, window.screen.availWidth - 40);
        const h = Math.min(960, window.screen.availHeight - 40);
        const left = Math.max(0, Math.round((window.screen.availWidth - w) / 2));
        const top = Math.max(0, Math.round((window.screen.availHeight - h) / 2));
        // ★`location=no` 를 넣지 않는다 — 현대 브라우저가 무시하므로 **지키지 못할 약속**이다.
        const feat = `popup=yes,width=${w},height=${h},left=${left},top=${top},menubar=no,toolbar=no,status=no,resizable=yes,scrollbars=yes`;
        const win = window.open(window.location.href, FIELD_APP_WINDOW_NAME, feat);
        // 팝업 차단되면 새 탭 폴백(기능 보존).
        if (!win) window.open(window.location.href, "_blank", "noopener,noreferrer");
        else win.focus();
      }}
      className="inline-flex min-h-[40px] items-center gap-1 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 text-xs font-black text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] active:scale-95"
    >
      <AppWindow className="size-4" aria-hidden /> 별도 창으로 열기
    </button>
  );
}
