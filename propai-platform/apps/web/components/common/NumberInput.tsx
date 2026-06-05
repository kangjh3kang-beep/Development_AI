"use client";

/**
 * 공용 숫자 입력 — 천단위 쉼표를 자동 표시(금액·수량·면적 등).
 * 내부 값은 number|null, 화면 표시는 쉼표 포맷. type=number 대체용.
 *
 * 사용:
 *   <NumberInput value={amount} onChange={(n) => setAmount(n)} className="..." />
 * 연도·율(%)·좌표 등 쉼표가 부적절한 필드에는 사용하지 말 것.
 */

import { useEffect, useRef, useState } from "react";
import { withCommas, parseCommaNumber } from "@/lib/formatters";

type Props = {
  value: number | null | undefined;
  onChange: (value: number | null) => void;
  allowDecimal?: boolean;        // 소수 허용(면적 등)
  className?: string;
  placeholder?: string;
  title?: string;
  disabled?: boolean;
  id?: string;
  suffix?: string;               // 표시용 접미(원/㎡ 등) — 외부 래핑 권장, 여기선 미사용
};

export function NumberInput({
  value, onChange, allowDecimal = false, className, placeholder, title, disabled, id,
}: Props) {
  const [text, setText] = useState<string>(withCommas(value ?? "", allowDecimal));
  const focused = useRef(false);

  // 외부 값 변경 시(미포커스) 표시 동기화
  useEffect(() => {
    if (!focused.current) setText(withCommas(value ?? "", allowDecimal));
  }, [value, allowDecimal]);

  return (
    <input
      id={id}
      inputMode={allowDecimal ? "decimal" : "numeric"}
      className={className}
      placeholder={placeholder}
      title={title ?? (value != null ? withCommas(value, allowDecimal) : undefined)}
      disabled={disabled}
      value={text}
      onFocus={() => { focused.current = true; }}
      onBlur={() => { focused.current = false; setText(withCommas(value ?? "", allowDecimal)); }}
      onChange={(e) => {
        const raw = e.target.value;
        setText(withCommas(raw, allowDecimal));   // 입력 즉시 쉼표 표시
        onChange(parseCommaNumber(raw, allowDecimal));
      }}
    />
  );
}
