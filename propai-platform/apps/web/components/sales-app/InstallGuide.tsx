"use client";

/**
 * Phase C — 앱 설치 안내(PWA install + iOS Safari "홈 화면에 추가").
 *
 * 기존 PWA 런타임(components/pwa/PwaRuntimeProvider usePwaRuntime)을 재사용한다:
 *   - Android/Chrome 등 beforeinstallprompt 가능 환경 → requestInstall()(네이티브 설치 프롬프트).
 *   - iOS Safari(beforeinstallprompt 미지원) → 공유→홈화면 추가 단계 안내(텍스트 단계).
 *   - 이미 설치(standalone)면 안내 숨김.
 *
 * 정직성: 미지원 환경 폴백(단계 안내), 설치 강요 없음. 모바일 우선·다크·토큰색.
 */
import { useMemo, useState } from "react";
import { usePwaRuntime } from "@/components/pwa/PwaRuntimeProvider";

function isIos(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  const iOSDevice = /iPad|iPhone|iPod/.test(ua);
  // iPadOS 13+ 는 Mac UA로 위장 → touch 지원 + Mac 으로 추가 판정.
  const iPadOS = /Macintosh/.test(ua) && typeof document !== "undefined" && "ontouchend" in document;
  return iOSDevice || iPadOS;
}

export default function InstallGuide() {
  const { installState, standalone, requestInstall } = usePwaRuntime();
  const [iosOpen, setIosOpen] = useState(false);
  const ios = useMemo(() => isIos(), []);

  // 이미 설치(앱 실행 중)면 안내 불필요.
  if (standalone) {
    return (
      <div className="rounded-xl border border-emerald-400/30 bg-emerald-500/5 px-4 py-3 text-sm font-bold text-emerald-300">
        ✓ 앱으로 실행 중입니다. 홈 화면 아이콘으로 빠르게 접속할 수 있어요.
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="flex items-center gap-2">
        <span className="text-lg">📲</span>
        <p className="text-sm font-black text-[var(--text-primary)]">홈 화면에 앱 추가</p>
      </div>
      <p className="text-xs text-[var(--text-secondary)]">
        홈 화면에 추가하면 주소 입력 없이 한 번에 접속하고, 푸시 알림을 받을 수 있어요.
      </p>

      {/* Android/Chrome 등 네이티브 설치 프롬프트 가능 */}
      {installState === "available" && !ios && (
        <button
          onClick={() => void requestInstall()}
          className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-white transition hover:opacity-90"
        >
          앱 설치하기
        </button>
      )}

      {/* iOS Safari — 공유→홈화면 추가 단계 안내 */}
      {ios && (
        <div className="space-y-2">
          <button
            onClick={() => setIosOpen((v) => !v)}
            className="w-full rounded-lg border border-[var(--accent-strong)] px-4 py-2.5 text-sm font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-soft)]"
          >
            {iosOpen ? "닫기" : "아이폰(Safari) 설치 방법 보기"}
          </button>
          {iosOpen && (
            <ol className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs text-[var(--text-secondary)]">
              <li className="flex gap-2">
                <span className="font-black text-[var(--accent-strong)]">1</span>
                <span>
                  사파리(Safari) 하단의 <span className="font-bold text-[var(--text-primary)]">공유 버튼</span>
                  <span className="mx-1 rounded bg-[var(--surface-soft)] px-1.5 py-0.5 text-[var(--text-primary)]">⬆️</span>
                  을 누릅니다.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="font-black text-[var(--accent-strong)]">2</span>
                <span>
                  메뉴를 내려 <span className="font-bold text-[var(--text-primary)]">&lsquo;홈 화면에 추가&rsquo;</span>
                  <span className="mx-1 rounded bg-[var(--surface-soft)] px-1.5 py-0.5 text-[var(--text-primary)]">➕</span>
                  를 선택합니다.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="font-black text-[var(--accent-strong)]">3</span>
                <span>
                  오른쪽 위 <span className="font-bold text-[var(--text-primary)]">&lsquo;추가&rsquo;</span>를 누르면 홈
                  화면에 아이콘이 생깁니다.
                </span>
              </li>
              <li className="pt-1 text-[10px] text-[var(--text-hint)]">
                ⓘ 크롬·다른 브라우저가 아닌 <b>Safari</b>에서만 추가됩니다. 추가 후 아이콘으로 실행하세요.
              </li>
            </ol>
          )}
        </div>
      )}

      {/* 그 외(데스크톱/미지원) — 안내만 */}
      {!ios && installState !== "available" && (
        <p className="text-[11px] text-[var(--text-hint)]">
          ⓘ 이 브라우저는 자동 설치를 지원하지 않습니다. 모바일(안드로이드 Chrome / 아이폰 Safari)에서 접속하면 홈
          화면에 추가할 수 있어요.
        </p>
      )}
    </div>
  );
}
