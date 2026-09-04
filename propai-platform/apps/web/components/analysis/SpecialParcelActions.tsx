/**
 * SpecialParcelActions — "그래서 뭘 해야 하나"를 백엔드가 준 근거로만 보여준다.
 *
 * ## 왜 만들었나
 *
 * 종합분석 보고서의 특이부지 카드는 지금까지 원시 코드(`NEEDS_OFFICIAL_SURVEY`)와 한 줄
 * 고지만 보여줬다. 그런데 백엔드는 **구체적인 다음 절차를 이미 다 내려주고 있었다** —
 * `resolution_paths`(해결 경로)·`permit_prerequisites`(선행 요건)·`alternatives`(대안).
 * 이 필드들의 프론트 소비처는 **0건**이었다(고아 핸드오프).
 *
 * ## 절대 규칙 — 문장을 지어내지 않는다
 *
 * 여기서 "산림조사서를 발급받으세요" 같은 조언을 **프론트가 쓰지 않는다.** 필지 유형마다
 * 해결 경로가 다르고(임야=산지전용허가, 맹지=진입도로 확보), 같은 코드라도 도메인이 다르면
 * 정반대 조언이 된다. 그래서 이 컴포넌트는 **백엔드 필드를 그대로 렌더**하고, 그 필드가
 * 비어 있으면 조언을 만들어내는 대신 **"안내 문구가 제공되지 않았습니다"** 를 표기한다.
 * (회귀락이 이걸 잠근다 — 백엔드 필드를 비우면 화면에서 조언이 사라져야 한다.)
 */

"use client";

import { ListChecks } from "lucide-react";

/** 백엔드 special_parcel.factors[] 중 이 컴포넌트가 읽는 부분만. */
export interface SpecialParcelFactor {
  category?: string | null;
  developability?: string | null;
  /** 해결 경로 — "산지전용허가 + 대체산림자원조성비 납부" 등. */
  resolution_paths?: string[] | null;
  /** 선행 요건 — "산림조사서·평균경사도조사서 작성" 등. */
  permit_prerequisites?: string[] | null;
  /** 대안 — "기준 초과 구역 제외(부분개발)" 등. */
  alternatives?: string[] | null;
}

function cleanList(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => String(x ?? "").trim()).filter((x) => x !== "");
}

function Group({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-[10px] font-bold text-[var(--text-secondary)]">{title}</p>
      <ul className="mt-0.5 space-y-0.5">
        {items.map((t, i) => (
          <li key={`${title}:${i}`} className="text-[10px] text-[var(--text-secondary)] leading-relaxed">
            · {t}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * 특이요인별 '다음 행동'. 요인이 없거나 백엔드가 근거를 안 주면 그 사실을 정직하게 밝힌다.
 */
export function SpecialParcelActions({ factors }: { factors?: SpecialParcelFactor[] | null }) {
  const list = Array.isArray(factors) ? factors : [];
  if (list.length === 0) return null;

  const blocks = list.map((f) => ({
    category: String(f?.category ?? "").trim(),
    paths: cleanList(f?.resolution_paths),
    prereqs: cleanList(f?.permit_prerequisites),
    alts: cleanList(f?.alternatives),
  }));

  // 어느 요인에도 근거가 없으면 컴포넌트 자체를 렌더하지 않는다(빈 상자 금지).
  if (blocks.every((b) => b.paths.length + b.prereqs.length + b.alts.length === 0)) return null;

  return (
    <div className="mt-3 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <div className="flex items-center gap-1.5">
        <ListChecks className="size-3.5 text-[var(--text-secondary)]" aria-hidden />
        <h4 className="text-[11px] font-bold text-[var(--text-primary)]">이 제약을 푸는 방법</h4>
      </div>
      <div className="mt-2 space-y-3">
        {blocks.map((b, i) => {
          const empty = b.paths.length + b.prereqs.length + b.alts.length === 0;
          return (
            <div key={`${b.category}:${i}`} className="space-y-1">
              {b.category && (
                <p className="text-[10px] font-bold text-[var(--text-primary)]">{b.category}</p>
              )}
              {empty ? (
                // ★조언을 지어내지 않는다 — 근거가 없으면 없다고 말한다.
                <p className="text-[10px] text-[var(--text-hint)]">
                  이 항목은 해결 절차 안내가 제공되지 않았습니다(관할 지자체 확인 필요).
                </p>
              ) : (
                <>
                  <Group title="필요한 절차" items={b.paths} />
                  <Group title="미리 준비할 것" items={b.prereqs} />
                  <Group title="대안" items={b.alts} />
                </>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[10px] text-[var(--text-hint)] leading-relaxed">
        위 절차는 분석이 확인한 법령·기준에서 나온 것이며, 실제 인허가 요건은 관할 지자체
        확인이 필요합니다.
      </p>
    </div>
  );
}
