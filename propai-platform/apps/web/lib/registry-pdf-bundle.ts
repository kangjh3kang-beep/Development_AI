/**
 * 발급받은 등기부 PDF **일괄 다운로드** 묶음 조립.
 *
 * 【왜 서버 엔드포인트를 안 만드나】
 * PDF 는 비공개 버킷에 있고 화면은 **서명 URL** 을 이미 들고 있다(행마다 `pdf_url`).
 * 서명 URL 자체가 권한이므로, 브라우저가 직접 받아 묶으면 **새로 생기는 권한이 0** 이다.
 * 서버에 "URL 목록을 받아 대신 받아다 주는" 엔드포인트를 두면 SSRF·IDOR 표면이 새로
 * 생기고, 그 검증을 평생 지켜야 한다. 라이브에서 교차출처 수신이 되는 것을 실측했다
 * (2026-08-24: `type:"cors"` · `application/pdf` · 77,535바이트 수신).
 *
 * 【★조용한 탈락 금지 — 이 모듈이 존재하는 진짜 이유】
 * 같은 실측에서 **서명 URL 이 만료된 행이 섞여 있었다**(`InvalidJWT — "exp" claim
 * timestamp check failed`). 링크는 화면에 멀쩡히 `PDF ↗` 로 떠 있는데 누르면 죽는다.
 * 그냥 받아서 묶으면 **77건을 눌렀는데 41건짜리 ZIP** 이 조용히 나온다 — 이 저장소가
 * 반복해서 데인 형태다. 그래서 이 모듈은 건마다 **왜 빠졌는지**를 분류해 돌려준다.
 */

import { isSignedUrlExpired } from "@/lib/signed-url";
import { buildZip, safeFileName, uniqueName, type ZipEntry } from "@/lib/zip";

export type PdfSource = {
  /** 사람이 읽는 식별자(지번). 파일명과 보고 문구에 쓴다. */
  jibun: string;
  /** 발급 PDF 의 서명 URL. 없으면 이 건은 애초에 담을 것이 없다. */
  pdfUrl?: string | null;
};

export type BundleStatus =
  /** ZIP 에 담겼다. */
  | "included"
  /** 발급 자체가 안 됐거나 PDF 가 없다. */
  | "no_pdf"
  /** 서명 URL 이 만료됐다(30일). 파일이 아직 있어도 이 링크로는 못 받는다. */
  | "expired"
  /** 그 밖의 수신 실패(네트워크·서버 오류). */
  | "fetch_failed";

export type BundleItem = {
  jibun: string;
  status: BundleStatus;
  /** 사람이 읽는 사유. `included` 면 비어 있다. */
  detail?: string;
  /** ZIP 안의 파일명(`included` 일 때만). */
  fileName?: string;
  bytes?: number;
};

export type BundleResult = {
  /** 담긴 것이 하나도 없으면 **null** — 빈 ZIP 을 내려보내 성공처럼 보이게 하지 않는다. */
  zip: Uint8Array | null;
  items: BundleItem[];
  total: number;
  included: number;
};

/** 서명 URL 만료를 나타내는 신호. Supabase Storage 가 이 형태로 답한다. */
function looksExpired(status: number, body: string): boolean {
  if (status !== 400) return false;
  return /InvalidJWT|exp.{0,20}claim|expired/i.test(body);
}

export type FetchLike = (url: string) => Promise<{
  ok: boolean;
  status: number;
  text(): Promise<string>;
  arrayBuffer(): Promise<ArrayBuffer>;
}>;

/**
 * 소스 목록을 받아 ZIP 을 만든다. **건별 결과를 함께** 돌려준다.
 *
 * 한 건이 실패해도 나머지는 담는다 — 하나 때문에 전부 못 받는 것이 더 나쁘다.
 * 대신 무엇이 왜 빠졌는지는 남김없이 보고한다.
 */
export async function buildRegistryPdfBundle(
  sources: readonly PdfSource[],
  opts?: { fetchImpl?: FetchLike; nowMs?: number },
): Promise<BundleResult> {
  const doFetch: FetchLike =
    opts?.fetchImpl ?? ((url) => fetch(url) as unknown as ReturnType<FetchLike>);

  const now = opts?.nowMs ?? Date.now();
  const items: BundleItem[] = [];
  const entries: ZipEntry[] = [];
  const taken = new Set<string>();

  for (let i = 0; i < sources.length; i++) {
    const src = sources[i];
    const label = (src.jibun || "").trim() || `필지${i + 1}`;
    const url = (src.pdfUrl || "").trim();

    if (!url) {
      items.push({ jibun: label, status: "no_pdf", detail: "발급된 등기부 PDF 가 없습니다" });
      continue;
    }

    // ★만료는 **받아 보기 전에** 안다(토큰의 `exp`). 77필지면 헛요청 수십 건을 아끼고,
    //   무엇보다 "느리게 실패"가 아니라 즉시 사유가 된다.
    //   ★못 읽으면 만료로 몰지 않는다 — 그때는 종전대로 받아 보고 응답으로 판정한다.
    if (isSignedUrlExpired(url, now)) {
      items.push({
        jibun: label,
        status: "expired",
        detail: "발급 링크가 만료되었습니다(발급 후 30일) — 다시 발급해야 받을 수 있습니다",
      });
      continue;
    }

    try {
      const res = await doFetch(url);
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        if (looksExpired(res.status, body)) {
          items.push({
            jibun: label,
            status: "expired",
            detail: "발급 링크가 만료되었습니다(발급 후 30일) — 다시 발급해야 받을 수 있습니다",
          });
        } else {
          items.push({ jibun: label, status: "fetch_failed", detail: `내려받기 실패 (HTTP ${res.status})` });
        }
        continue;
      }
      const buf = new Uint8Array(await res.arrayBuffer());
      if (buf.length === 0) {
        items.push({ jibun: label, status: "fetch_failed", detail: "빈 파일을 받았습니다" });
        continue;
      }
      // 번호를 앞에 붙여 목록 순서를 파일 정렬로 보존한다(지번만으로는 뒤섞인다).
      const seq = String(i + 1).padStart(3, "0");
      const fileName = uniqueName(
        `${seq}_등기부_${safeFileName(label, `필지${i + 1}`)}.pdf`,
        taken,
      );
      entries.push({ name: fileName, data: buf });
      items.push({ jibun: label, status: "included", fileName, bytes: buf.length });
    } catch (e) {
      items.push({
        jibun: label,
        status: "fetch_failed",
        detail: e instanceof Error ? `내려받기 실패 — ${e.message}` : "내려받기 실패",
      });
    }
  }

  const included = entries.length;
  return {
    zip: included > 0 ? buildZip(entries) : null,
    items,
    total: sources.length,
    included,
  };
}

const STATUS_LABEL: Record<Exclude<BundleStatus, "included">, string> = {
  expired: "발급 링크 만료",
  no_pdf: "PDF 없음",
  fetch_failed: "내려받기 실패",
};

/**
 * 결과를 한 줄로. **빠진 건을 반드시 말한다** — "N건 받았습니다"만 쓰면
 * 사용자는 요청한 M건이 다 온 줄 안다.
 */
export function describeBundle(r: BundleResult): string {
  const head = `${r.total}건 중 ${r.included}건 담았습니다`;
  const counts = new Map<string, number>();
  for (const it of r.items) {
    if (it.status === "included") continue;
    const key = STATUS_LABEL[it.status];
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  if (counts.size === 0) return head;
  const tail = [...counts.entries()].map(([k, n]) => `${k} ${n}건`).join(" · ");
  return `${head} — 제외: ${tail}`;
}

/** 브라우저에 파일로 내려보낸다. 테스트 대상이 아니므로 최소한으로 둔다. */
export function saveBlob(bytes: Uint8Array, fileName: string): void {
  const buf = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buf).set(bytes);
  const url = URL.createObjectURL(new Blob([buf], { type: "application/zip" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(url);
}
