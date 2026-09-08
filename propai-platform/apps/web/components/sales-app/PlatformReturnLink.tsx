"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { useFieldAppShell } from "@/lib/field-app-shell";

/**
 * 현장앱 목록 화면의 **플랫폼 복귀로** — 단, **같은 탭으로 들어온 사람에게만**.
 *
 * ## 왜 조건부인가 (사용자 지시 그대로)
 *
 * > *"새창앱에서는 메인플랫폼으로 이동하지 않아도 되지만 현재는 메인플랫폼에서 분양앱을
 * >   누르면 새창이 아닌 같은 창에서 이동하면서 … 번거러움이 발생하고 있어"*
 *
 * 근본 처방은 `FieldAppLaunchLink`(진입을 새 창으로)다. 그러면 원래 창이 남으므로
 * **복귀로가 필요 없다.** 이 링크는 그 처방이 **닿지 못하는 모집단**만 위한 것이다 —
 * 북마크·주소 직접 입력·팝업 차단으로 **같은 탭에** 현장앱이 뜬 경우.
 *
 * | 모집단 | 복귀로 | 왜 |
 * |---|---|---|
 * | 설치본(`standalone`) | **안 낸다** | manifest `scope=/ko/sales` 밖으로 나가면 무슨 일이 나는지 **미측정**(실기기 부재)이다. 모르는 동작에 사용자를 태우지 않는다 |
 * | 별도 창(`inSeparateWindow`) | **안 낸다** | 그 창에서 플랫폼으로 가면 `window.name` 이 `propai-field-app` 으로 **남는다**(e2e 크로미움 실측). 플랫폼을 보여 주는 창이 계속 「현장앱 창」으로 판정돼 어포던스가 틀린 답을 낸다 |
 * | 일반 탭 | **낸다** | 여기만 갇힌다 |
 *
 * ## 왜 깊이 0(목록)에 두는가
 *
 * 탈출 가능성이 **깊이별로 뒤집혀 있었다**(2026-09-08 전수 조사):
 * 깊이 1(워크스페이스)에는 목록으로 돌아가는 링크가 **있고**, 깊이 0(목록)에는 **없다**.
 * 보통 막다른 곳은 가장 깊은 화면인데 여기서는 **가장 얕은 화면이 종단**이라,
 * 사용자가 목록까지 올라오는 데 성공해도 거기서 갈 곳이 없었다.
 */
export default function PlatformReturnLink({ locale }: { locale: string }) {
  const { standalone, inSeparateWindow } = useFieldAppShell();

  // ★두 축을 **각각** 본다(하나로 뭉치지 않는다). 형제 `FieldAppAffordance` 가
  //   두 축을 하나(`inAppShell`)로 뭉쳤다가 iOS 의 유일한 설치 경로를 막은 전례가 있다.
  if (standalone) return null;
  if (inSeparateWindow) return null;

  return (
    <Link
      href={`/${locale}`}
      className="inline-flex min-h-[40px] items-center gap-1.5 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 text-xs font-black text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] active:scale-95"
    >
      <ArrowLeft className="size-4" aria-hidden /> 플랫폼으로
    </Link>
  );
}
