"use client";

/**
 * Phase 1-A — 현장 진입(2차비번) 모달.
 * 비번 입력 → POST /sales/sites/{id}/enter → site_token(8h) sessionStorage 저장 → 워크스페이스 이동.
 * 에러 계약(2026-09-09 개정): 403(멤버 아님)·401(비번 불일치/남은시도)·429(잠김/대기분)·
 *   400(이 현장은 비번이 필요한데 안 보냄 — **실패 카운트를 쓰지 않는다**).
 * ★**409(비번 미설정)는 더 이상 발생하지 않는다** — 비번이 없으면 승인된 멤버십으로 진입한다.
 *   아래 `friendlyError` 의 409 분기는 **옛 서버·캐시된 배포**를 위해서만 남겨 둔다.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { storeSiteToken } from "@/lib/salesApi";
import { useModalFocus } from "@/hooks/useModalFocus";
import { DISMISS_Z, useDismissible } from "@/lib/satong-dismiss";
import type { Locale } from "@/i18n/config";

export interface EnterResponse {
  site_token: string;
  token_type: string;
  expires_in: number;
  site_id: string;
  role: string;
  role_label?: string;
  features: string[];
  /** 어떤 인증으로 들어왔나 — `membership`(승인) vs `password`(2차 비번).
   *  ★종전엔 서버만 알고 화면은 **선언조차 안 했다**(소비처 0건). */
  auth?: "membership" | "password";
}

interface Props {
  locale: Locale;
  siteId: string;
  siteName: string;
  open: boolean;
  onClose: () => void;
  /** 진입 성공 시 호출(메타 전달). 미지정 시 워크스페이스로 라우팅. */
  onEntered?: (res: EnterResponse) => void;
  /** 이 현장에 2차 비밀번호가 **설정돼 있나**(`GET /sales/my-sites`·`/role` 의 `password_set`).
   *
   * ★`true` 면 **자동 시도를 하지 않는다**(2026-09-09 리뷰 C1). 모르면(`undefined`) 시도한다 —
   *   서버가 카운터 **앞에서** 400 으로 막으므로 잠금은 소진되지 않지만, 아는 경우에는
   *   애초에 두드리지 않는 것이 옳다(네트워크 왕복·서버 로그도 사건이다).
   */
  passwordSet?: boolean;
}

export default function SiteEnterModal({ locale, siteId, siteName, open, onClose, onEntered, passwordSet }: Props) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // ★★모달이 열리면 **비번 없이 먼저 시도**한다(2026-09-09).
  //   라이브 14현장 중 **11현장이 비번 미설정**이라, 승인된 멤버는 아무것도 입력할 필요가 없다.
  //   비번이 설정된 현장(실측 3곳)에서는 이 시도가 조용히 실패하고 입력창이 그대로 남는다
  //   — 사용자는 아무 오류도 보지 않는다(`silent`).
  const autoTried = useRef("");

  // ESC 로 닫기 — 열려 있는 동안만 등록한다(닫힌 모달이 ESC 를 가로채지 않게).
  // ★비밀번호를 입력하던 중 ESC 를 누르면 입력은 사라진다. 이 모달은 열릴 때마다 입력을
  //   초기화하므로(위 effect) 종전에도 보존되지 않던 값이고, 새로 잃는 것은 없다.
  useDismissible(DISMISS_Z.appModal, open, onClose);

  // ★포커스 생명주기(초기 포커스·Tab 트랩·복귀) — ESC 와 **별개 계약**이다.
  //   이 표면의 첫 포커스 가능 요소는 위 `inputRef` 비밀번호 입력창 **자신**이라
  //   훅의 초기 포커스와 저자 의도가 일치한다(빼앗는 회귀가 아니다).
  useModalFocus(bodyRef, open);

  // ★비번은 **선택**이다(2026-09-09). 서버가 «이 현장에 비번이 설정돼 있나» 로 판정한다 —
  //   라이브 14현장 중 11현장이 미설정이라 종전엔 멤버여도 409 로 진입이 막혀 있었다.
  //   그래서 «비었으면 보내지 마라» 는 클라 검사를 **뺀다**(그 검사가 곧 차단이었다).
  //
  // ★★종전에는 `submitRef.current = submit` 을 **렌더 중**에 대입했다(React 가 금지한다 —
  //   리뷰 MINOR 1). ref 가 필요했던 이유는 «effect 의존에 `submit` 을 넣으면 매 렌더
  //   재실행» 이었는데, 그건 `submit` 이 `password` 를 닫고 있었기 때문이다.
  //   **자동 시도는 비번을 절대 보내지 않는다** — 그래서 비번을 인자로 받는 `enter` 로
  //   분리하면 의존이 `password` 에서 풀리고 ref 자체가 필요 없어진다.
  const enter = useCallback(async (pw: string, opts?: { silent?: boolean }) => {
    setBusy(true);
    setErr("");
    try {
      const res = await apiClient.post<EnterResponse>(
        `/sales/sites/${siteId}/enter`,
        { body: pw ? { password: pw } : {} },
      );
      storeSiteToken(siteId, res.site_token, res.expires_in, {
        role: res.role,
        features: res.features,
        // ★어떤 인증으로 들어왔는지 **보관한다** — 종전엔 응답에만 있고 소비처 0건이라
        //   «오늘 몇 명이 비번으로 들어왔나» 를 화면에서도 셀 수 없었다(리뷰 M4).
        auth: res.auth,
      });
      if (onEntered) onEntered(res);
      else router.push(`/${locale}/sales/sites/${siteId}/workspace`);
    } catch (e) {
      // ★자동 시도(모달이 열리자마자)는 **조용히 실패**한다 — 비번이 필요한 현장이면
      //   사용자가 아직 아무것도 안 했는데 빨간 오류가 뜨면 안 된다.
      if (!opts?.silent) setErr(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }, [siteId, locale, onEntered, router]);

  const submit = () => enter(password);

  useEffect(() => {
    if (!open) return;
    setPassword("");
    setErr("");
    setTimeout(() => inputRef.current?.focus(), 50);
    // ★비번이 **설정된 것으로 알려진** 현장에는 노크하지 않는다(리뷰 C1).
    //   `undefined`(모름)와 `false` 는 시도한다 — 시도해야 알 수 있는 경우다.
    if (passwordSet !== true && autoTried.current !== siteId) {
      autoTried.current = siteId;
      void enter("", { silent: true });
    }
  }, [open, siteId, passwordSet, enter]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="현장 진입"
    >
      <div
        ref={bodyRef}
        className="w-full max-w-sm overflow-hidden rounded-t-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-md)] sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 모달 헤더 — accent 글로우 띠로 진입(보안) 행위임을 시각화 */}
        <div className="relative overflow-hidden border-b border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-[var(--accent-soft)] blur-2xl"
          />
          <div className="relative flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-[color:color-mix(in_srgb,var(--accent-strong)_30%,transparent)] bg-[var(--accent-soft)] text-[var(--accent-strong)]">
              <LockKeyhole className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              <span className="cc-label">SECURE ENTRY</span>
              <h2 className="text-base font-black leading-tight text-[var(--text-primary)]">현장 진입</h2>
            </div>
          </div>
        </div>

        <div className="p-5">
          <p className="mb-4 text-xs leading-relaxed text-[var(--text-secondary)]">
            {passwordSet === false ? (
              <>
                <b className="text-[var(--text-primary)]">{siteName}</b> 현장은 <b className="text-[var(--text-primary)]">승인된 멤버십으로 진입</b>합니다.
                2차 비밀번호는 설정돼 있지 않습니다.
              </>
            ) : (
              <>
                <b className="text-[var(--text-primary)]">{siteName}</b> 현장의 2차 비밀번호를 입력하세요.
              </>
            )}
          </p>

          <input
            ref={inputRef}
            type="password"
            inputMode="text"
            autoComplete="off"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
            placeholder="현장 비밀번호"
            className="w-full rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 py-3.5 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-strong)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
          />

          {err && (
            <p className="mt-2 rounded-lg bg-[color:color-mix(in_srgb,var(--status-error)_12%,transparent)] px-2.5 py-2 text-xs font-semibold text-[var(--status-error)]">
              {err}
            </p>
          )}

          <div className="mt-4 flex gap-2">
            <button
              onClick={onClose}
              disabled={busy}
              className="flex-1 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-3.5 text-sm font-bold text-[var(--text-secondary)] transition hover:text-[var(--text-primary)] active:scale-95 disabled:opacity-50"
            >
              취소
            </button>
            <button
              onClick={() => void submit()}
              disabled={busy}
              className="flex-[2] rounded-xl bg-[var(--accent-strong)] px-4 py-3.5 text-sm font-black text-white shadow-[var(--shadow-sm)] transition hover:opacity-90 active:scale-95 disabled:opacity-50"
            >
              {busy ? "확인 중…" : "진입 →"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** 백엔드 에러 계약(403/401/409/429/400)을 사용자 친화 메시지로 변환. */
function friendlyError(e: unknown): string {
  if (e instanceof ApiClientError) {
    const detail = (e.payload as { detail?: string } | null)?.detail;
    switch (e.status) {
      case 403:
        return "이 현장의 멤버가 아닙니다. 현장 관리자에게 권한을 요청하세요.";
      case 401:
        return typeof detail === "string" && detail ? detail : "비밀번호가 일치하지 않습니다.";
      case 409:
        // ★도달 불가(2026-09-09) — 서버가 더는 409 를 내지 않는다. 옛 배포가 살아 있는
        //   동안의 안전망으로만 남긴다. 이 분기가 보이면 **백엔드가 옛 판**이라는 뜻이다.
        return "현장 비밀번호가 아직 설정되지 않았습니다. 현장 관리자(시행/대행 본부장↑)에게 설정을 요청하세요.";
      case 429:
        return typeof detail === "string" && detail
          ? detail
          : "비밀번호를 여러 번 틀려 일시적으로 잠겼습니다. 잠시 후 다시 시도하세요.";
      case 400:
        // ★서버가 사유를 실어 준다(«이 현장은 2차 비밀번호가 필요합니다»). 우리가 지어낸
        //   «너무 짧다» 는 틀린 안내가 될 수 있으므로 **서버 문구를 우선**한다.
        return typeof detail === "string" && detail
          ? detail
          : "비밀번호가 너무 짧거나 비어 있습니다.";
      default:
        if (typeof detail === "string" && detail) return detail;
    }
  }
  return "진입에 실패했습니다. 잠시 후 다시 시도하세요.";
}
