"use client";

/**
 * 입력요약 칸 — **읽기 → 「수정」 → 입력 → 「저장」** 패턴.
 *
 * ## 왜 이 패턴인가 (2026-09-07 사용자 제안)
 *
 * > *"각 필드별로 수정 및 입력버튼을 통해 입력하고 저장 및 완료로 완성되도록 하면
 * >  가독성과 직관력이 높아지지 않을까?"*
 *
 * 항상 열린 입력창은 ①요약을 **읽을 때** 시선이 분산되고 ②실수로 값을 바꿔도
 * 알아채기 어렵다(개략수지는 재계산 비용이 있는 화면이다). 명시적 «수정 → 저장»은
 * **의도한 변경만** 통과시키고, 저장된 칸은 배지로 **직접입력임을 계속 말한다.**
 *
 * ★값의 출처를 화면이 계속 말해야 한다 — 이 저장소는 *"「모름」을 유효값으로 표현하면
 *   관측이 된다"* 는 사고를 이미 겪었다. 여기서는 그 짝이다: **자동 산출값과 사용자가
 *   넣은 값이 같은 얼굴을 하면 안 된다.**
 */

import { Check, Pencil, RotateCcw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface EditableTileProps {
  label: string;
  /** 자동 산출된 표시값(사람이 읽는 형태). */
  autoText: string | null;
  /** 사용자가 저장한 값. null 이면 자동값을 쓴다. */
  value: number | null;
  /** 저장 시 호출. null 이면 **되돌리기**(자동값으로 복귀). */
  onSave: (v: number | null) => void;
  /** 입력 단위 표기(㎡·평·개월 등). */
  unit?: string;
  /** 소수 허용 여부. */
  step?: string;
  hint?: string;
  accent?: boolean;
}

export function EditableTile({
  label, autoText, value, onSave, unit, step = "1", hint, accent,
}: EditableTileProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const isOverridden = value != null;
  const shown = isOverridden ? `${value.toLocaleString()}${unit ?? ""}` : (autoText ?? "—");

  const begin = () => {
    setDraft(value != null ? String(value) : "");
    setError(null);
    setEditing(true);
  };

  const commit = () => {
    const raw = draft.trim();
    if (raw === "") {
      // ★빈 값은 «0» 이 아니라 **«자동값으로 되돌리기»** 다.
      //   「없음」을 0 으로 표현하면 0원/0㎡ 가 확정치처럼 그려진다.
      onSave(null);
      setEditing(false);
      return;
    }
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) {
      setError("0보다 큰 숫자를 입력하세요");
      return;
    }
    onSave(n);
    setEditing(false);
  };

  const cancel = () => { setEditing(false); setError(null); };

  return (
    <div className={`sa-di-tile${accent ? " sa-di-tile--accent" : ""}`}>
      <span className="sa-di-tile__label flex items-center justify-between gap-1">
        <span>
          {label}
          {isOverridden && (
            // ★출처를 계속 말한다 — 자동값과 직접입력이 같은 얼굴이면 안 된다.
            <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] font-bold text-amber-800">
              직접입력
            </span>
          )}
        </span>
        {!editing && (
          <span className="flex items-center gap-0.5">
            {isOverridden && (
              <button
                type="button"
                aria-label={`${label} 자동값으로 되돌리기`}
                title="자동 산출값으로 되돌리기"
                className="opacity-60 hover:opacity-100"
                onClick={() => onSave(null)}
              >
                <RotateCcw className="size-3" aria-hidden />
              </button>
            )}
            <button
              type="button"
              aria-label={`${label} 수정`}
              className="opacity-60 hover:opacity-100"
              onClick={begin}
            >
              <Pencil className="size-3" aria-hidden />
            </button>
          </span>
        )}
      </span>

      {editing ? (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1">
            <input
              ref={inputRef}
              type="number"
              step={step}
              inputMode="decimal"
              aria-label={`${label} 입력${unit ? ` (${unit})` : ""}`}
              className="sa-di-tile__value w-full min-w-0 rounded border border-slate-300 bg-white px-1 dark:bg-slate-800"
              value={draft}
              placeholder={autoText ?? ""}
              onChange={(e) => { setDraft(e.target.value); setError(null); }}
              onKeyDown={(e) => {
                if (e.key === "Enter") { e.preventDefault(); commit(); }
                if (e.key === "Escape") { e.preventDefault(); cancel(); }
              }}
            />
            <button type="button" aria-label={`${label} 저장`} onClick={commit}
              className="rounded bg-emerald-600 p-1 text-white hover:bg-emerald-700">
              <Check className="size-3" aria-hidden />
            </button>
            <button type="button" aria-label={`${label} 취소`} onClick={cancel}
              className="rounded border border-slate-300 p-1 hover:bg-slate-100">
              <X className="size-3" aria-hidden />
            </button>
          </div>
          {/* ★사유를 말한다 — 조용히 안 받으면 사용자는 왜 안 되는지 모른다. */}
          {error && <span className="text-[10px] font-bold text-rose-600">{error}</span>}
          {!error && hint && <span className="text-[10px] opacity-70">{hint}</span>}
          <span className="text-[10px] opacity-60">비우고 저장하면 자동값으로 되돌립니다</span>
        </div>
      ) : (
        <span className="sa-di-tile__value">{shown}</span>
      )}
    </div>
  );
}
