import { create } from "zustand";
import { persist } from "zustand/middleware";
import { createAccountScopedStorage } from "@/lib/account-scoped-storage";

/**
 * 유료 AI 렌더(포토리얼·컨셉) 결과 보관 — 프로젝트별 영속.
 *
 * ## 왜 필요한가
 *
 * `photoreal_render` 는 **건당 3,000원**(외부 GPU 호출)인데 결과를 `setRenderImage`
 * (평범한 `useState`)로만 들고 있었다 — **새로고침 한 번에 사라진다.**
 * 등기 권리분석 리스트와 **같은 얼굴**이고, CLAUDE.md 「유료·비가역 산출물 규율」이
 * 예측한 것을 다른 도메인에서 실측한 사례다(*"유료 산출물은 영속한다"*).
 *
 * ## 용량 — 조용히 버리지 않는다
 *
 * 프로바이더에 따라 결과가 **URL** 이거나 **base64** 다. base64 는 수 MB 가 될 수 있고
 * localStorage 는 대략 5MB 다. 그래서:
 *  · 항목 수를 `MAX_ITEMS` 로 묶고(오래된 것부터 버린다)
 *  · 한 항목이 `MAX_INLINE_BYTES` 를 넘으면 **본문을 담지 않고 그 사실을 기록**한다
 *    (`omitted: "size"`). 화면은 "용량이 커서 보관하지 못했다"고 **말할 수 있어야 한다** —
 *    조용히 사라지면 사용자는 자기가 산 것이 어디 갔는지 알 수 없다.
 *
 * ★한계(정직 고지): 이것은 **브라우저 로컬** 보관이다. 기기를 바꾸면 남지 않는다.
 *   제대로 된 처방은 등기 PDF 처럼 **서버 보관 + 만료 URL** 이고, 그건 별건이다.
 */

/** 한 프로젝트에 보관할 최대 렌더 수. 넘으면 오래된 것부터 버린다. */
export const MAX_ITEMS = 8;
/** 한 항목에 인라인으로 담을 최대 바이트(대략). 넘으면 본문 대신 사유를 남긴다. */
export const MAX_INLINE_BYTES = 1_500_000;

export type PaidRender = {
  id: string;
  /** 저장 시각(ISO). */
  at: string;
  /** 프로바이더가 URL 을 준 경우. */
  imageUrl?: string | null;
  /** base64(data: 접두 포함 가능). 용량 초과면 비어 있고 `omitted` 가 채워진다. */
  imageBase64?: string | null;
  /** 본문을 담지 못한 사유. 비어 있으면 정상 보관. */
  omitted?: "size" | null;
  /** 과금액(원) — 얼마짜리인지 화면이 말할 수 있어야 한다. */
  chargedKrw?: number | null;
  label?: string | null;
};

export type ProjectKey = string | null | undefined;

type State = {
  byProject: Record<string, PaidRender[]>;
  add: (projectId: ProjectKey, item: Omit<PaidRender, "at" | "omitted">) => void;
  remove: (projectId: ProjectKey, id: string) => void;
  clear: (projectId: ProjectKey) => void;
};

/**
 * persist 이름 — **레거시 공유키 그대로**다. 실제 저장키는 `createAccountScopedStorage` 가
 * 읽기/쓰기 시점에 `__<uid>` 를 붙여 만든다(`propai-paid-renders__<userId>`).
 *
 * ★이름을 바꾸지 않는 이유: 이 값은 **레거시 원본을 읽는 주소**이기도 하다. 바꾸면 계정별
 *   키로 옮겨 가기 전의 유료 AI 렌더(포토리얼·컨셉) 결과이 **고아**가 된다 — 사용자가 이미 낸 돈이다.
 */
export const PAID_RENDER_STORE_KEY = "propai-paid-renders";

const KEY = (projectId: ProjectKey) => projectId || "_default";

/** 대략적인 바이트 수(문자열 길이 기반 — 정확한 인코딩 계산은 이 용도에 과하다). */
export function approxBytes(s: string | null | undefined): number {
  return s ? s.length : 0;
}

export const usePaidRenderStore = create<State>()(
  persist(
    (set) => ({
      byProject: {},

      add: (projectId, item) =>
        set((s) => {
          const k = KEY(projectId);
          const tooBig = approxBytes(item.imageBase64) > MAX_INLINE_BYTES;
          const entry: PaidRender = {
            ...item,
            // 용량 초과여도 **항목 자체는 남긴다** — "3,000원을 썼다"는 사실과 사유가 사라지면
            // 사용자는 자기가 산 것이 어디 갔는지 알 수 없다.
            imageBase64: tooBig ? null : (item.imageBase64 ?? null),
            omitted: tooBig ? "size" : null,
            at: new Date().toISOString(),
          };
          const next = [...(s.byProject[k] ?? []), entry].slice(-MAX_ITEMS);
          return { byProject: { ...s.byProject, [k]: next } };
        }),

      remove: (projectId, id) =>
        set((s) => {
          const k = KEY(projectId);
          const cur = s.byProject[k];
          if (!cur) return s;
          return { byProject: { ...s.byProject, [k]: cur.filter((x) => x.id !== id) } };
        }),

      clear: (projectId) =>
        set((s) => {
          const k = KEY(projectId);
          if (!s.byProject[k]) return s;
          const rest = { ...s.byProject };
          delete rest[k];
          return { byProject: rest };
        }),
    }),
    { name: PAID_RENDER_STORE_KEY, storage: createAccountScopedStorage<State>() },
  ),
);
