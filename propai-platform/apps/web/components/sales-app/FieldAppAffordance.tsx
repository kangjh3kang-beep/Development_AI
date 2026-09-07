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
 * ★변이 생존 설명(scripts/mutate_changed.py) — 구멍이 아닌 이유.
 *   ★수치를 값으로 박지 않는다(§28 휘발성) — 커밋마다 바뀐다. 지금 재려면:
 *     python3 scripts/mutate_changed.py --tests propai-platform/apps/web/components/sales-app/*.test.tsx
 *   ① `className` 문자열 변경 다수 — **표기**이지 계약이 아니다. 문구·스타일까지 단언하면
 *      다듬을 때마다 깨지는 취약한 락이 된다(이 저장소가 명시적으로 경계하는 형태).
 *   ② `typeof window === "undefined"` 의 문자열 변경 — **SSR 방어**라 jsdom 에서는 도달 불가.
 *      이 축은 여기서 잴 수 없다(미측정이지 무잠금이 아니다).
 *   ③ `"use client"` 변경 — 빌드 지시자라 vitest 가 태우지 않는다.
 *   ★반면 **설명할 수 없던 생존 둘**(설치 onClick 삭제 · 팝업 차단 폴백)은 그대로 두지 않고
 *     락을 추가했다 — 그것이 진짜 구멍이었다.
 */
export default function FieldAppAffordance() {
  const { standalone, inSeparateWindow } = useFieldAppShell();
  const { installState, requestInstall } = usePwaRuntime();

  // ★★가드를 **두 명제로 나눈다**(적대 리뷰 2026-09-07 BLOCKER).
  //   종전엔 `inAppShell`(standalone ‖ 별도 창) 하나로 **둘 다** 껐다. 그래서 팝업 안에서
  //   설치가 **원천 봉쇄**됐다 — 이 파일이 스스로 *"별도 창은 앱이 아니다"* 라고 쓰면서
  //   그 「앱이 아닌 상태」를 「앱 안」으로 취급한 자기모순이었다.
  //   ★iOS 에서 특히 나빴다: beforeinstallprompt 가 없어 보이는 단추가 「별도 창으로 열기」뿐인데,
  //     그것을 한 번 누르면 그 창에서 **유일한 설치 경로가 영구히 닫혔다.**
  //
  //   설치본으로 실행 중이면 더 설치할 것이 없다 — 여기서만 전부 끈다.
  if (standalone) return null;

  // 설치 권유는 **별도 창 안에서도 유효하다**(별도 창은 앱이 아니므로 설치가 여전히 개선이다).
  // iOS Safari 는 beforeinstallprompt 가 **없어** 여기가 항상 거짓이고,
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

  // ★이미 별도 창 안이면 「별도 창으로 열기」는 무의미하다 — 여기서만 끈다.
  //   (사용자가 신고한 «앱에 들어가도 버튼이 계속 뜬다» 가 정확히 이 자리다.)
  if (inSeparateWindow) return null;

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
