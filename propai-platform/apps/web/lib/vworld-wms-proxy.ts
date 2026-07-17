import { classifyVWorldXmlException, extractVWorldXmlExceptionDetail, isVWorldKeyFault } from "@/lib/vworld-xml-exception";

/**
 * VWorld WMS 프록시 — 연속지적도(LP_PA_CBND_*) WMS 타일을 프론트 서버 경유로 부설한다.
 *
 * ★보안(WP-M5): 종전엔 SatongMultiMap 이 `L.tileLayer.wms("https://api.vworld.kr/req/wms", {key})`
 *   로 브라우저에서 직결하며 API 키를 프론트 번들에 하드코딩(폴백 문자열)했다. 여기서는 이
 *   리터럴 하드코딩을 제거하고 서버 전용 키(`VWORLD_API_KEY`, Node 프로세스에서만 읽힘)를
 *   경유해 지적 WMS를 부설한다.
 *
 * ★PR#329 R1 리뷰(HIGH) 반영 — 보안 주장 범위 축소(정직 고지):
 *   이 프록시는 `NEXT_PUBLIC_VWORLD_API_KEY`(공개·도메인 제한 키, `lib/vworld-client.ts`·
 *   `AvmVisionPanel.tsx`가 브라우저에서 직접 사용)로 폴백하지 않는다 — 폴백을 두면 서버
 *   전용 키가 미설정일 때 조용히 같은 공개 키를 재사용해 "서버 전용 키 분리" 의도가
 *   무력화된다(순 보안이득 ≈ 0). `VWORLD_API_KEY` 미설정 시 503으로 정직하게 실패한다.
 *   ※"키가 어디에도 남지 않는다"는 과대 주장이 아니다 — VWorld 키는 두 계약으로 나뉜다:
 *     (1) 공개(도메인 제한) 키 `NEXT_PUBLIC_VWORLD_API_KEY` = 브라우저 직접 호출 허용
 *         경로(별도 정책, 이 프록시와 무관 — Referer/도메인 제한이 보호 기제).
 *     (2) 서버 전용 키 `VWORLD_API_KEY` = 이 프록시가 Node 런타임에서만 사용, 브라우저
 *         번들·네트워크 응답 어디에도 값이 포함되지 않는다.
 *   본 프록시가 없애는 것은 "리터럴 하드코딩된 키 문자열"이지, VWorld 키 개념 전체가
 *   아니다.
 *
 * WMTS 프록시(vworld-wmts-proxy.ts)와 동일한 오류 계약을 따른다:
 *   · 4xx/5xx  → 503 JSON({error,status}) (무음 회색타일 금지)
 *   · 200+XML  → classifyVWorldXmlException 으로 분류(coverage=투명PNG · auth=503 승격)
 *   · 그 외 200+비이미지 → 503 JSON
 */

const VWORLD_WMS_BASE = "https://api.vworld.kr/req/wms";

// 프록시가 허용하는 WMS 레이어(오픈 프록시 남용 방지) — 연속지적도 + 용도지역.
//   ★용도지역(LT_C_UQ111)은 2026-07-17부터 허용: '용도지역' 레이어의 별도 컨트롤
//     (land-use-wide — 전국 지적편집도 오버레이)로 도입. 지적 토글과는 여전히 분리
//     (WP-M5의 '함께 부설 금지' 원칙 유지 — 소비 컨트롤이 다르다).
//   ★api측 프록시(app/routers/vworld_tiles.py ALLOWED_WMS_LAYERS)와 동기 유지할 것.
//   배열(순서 보존) + Set(조회용) 이원 유지 — 화이트리스트 재구성 시 결정적 순서가 필요하다.
//   ★레이어명 정본(2026-07-17 GetCapabilities 라이브 채증): WMS는 소문자만 인식하며
//     연속지적도는 lp_pa_cbnd_bubun(부번)·lp_pa_cbnd_bonbun(본번)이다 — 종전
//     LP_PA_CBND_BUDB/BONB는 데이터 API명(LP_PA_CBND_BUBUN)을 잘못 축약한 실존하지 않는
//     이름(도입 PR#329부터의 오기, LayerNotDefined 근본원인). 비교는 소문자 정규화.
const ALLOWED_WMS_LAYERS_ORDER = [
  "lp_pa_cbnd_bubun",
  "lp_pa_cbnd_bonbun",
  "lp_pa_cbnd_bubun_line", // V1: 선 전용(위성뷰 가독 — VWorld 공식 프로토타입 채증)
  "lp_pa_cbnd_bonbun_line",
  "lt_c_uq111",
] as const;
const ALLOWED_WMS_LAYERS = new Set<string>(ALLOWED_WMS_LAYERS_ORDER);

function vworldKey(): string {
  // ★서버 전용 키만 사용(NEXT_PUBLIC_* 폴백 금지) — 파일 상단 독스트링 참조.
  return (process.env.VWORLD_API_KEY || "").trim();
}

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ error: message, status }), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

/**
 * ★WS-B2(관리자 키 web 미배선 봉합): 로컬 서버키 부재 시 api 타일 프록시로 중계할 오리진.
 *   관리자 화면(platform_secrets) 키는 load_into_env()로 apps/api에만 주입되므로, web에
 *   키가 없으면 api(/api/v1/tiles/vworld/*)가 자기(관리자 반영된) 키로 대신 프록시한다.
 *   NEXT_PUBLIC_API_BASE_URL 이 명시된 경우에만 폴백(미설정이면 기존 정직 503 유지 —
 *   Docker 내부 DNS 추측 중계는 web/api 분리 호스트 배포에서 오배선이 된다).
 */
export function vworldApiFallbackOrigin(): string | null {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!raw) return null;
  return raw.replace(/\/+$/, "").replace(/\/api\/v[12]$/, "");
}

export async function relayViaApi(url: string, proxyTag: string): Promise<Response> {
  try {
    const resp = await fetch(url, { next: { revalidate: 60 * 60 * 24 } });
    // api측이 이미 web과 동일 계약(투명타일/503+code)으로 변환해 주므로 그대로 통과.
    const body = await resp.arrayBuffer();
    return new Response(body, {
      status: resp.status,
      headers: {
        "Content-Type": resp.headers.get("content-type") ?? "application/octet-stream",
        "Cache-Control": resp.headers.get("cache-control") ?? "no-store",
      },
    });
  } catch (error) {
    console.error(`[${proxyTag}] api fallback failed`, { url, error: String(error) });
    return jsonError("VWORLD_API_KEY is not configured (api fallback failed)", 503);
  }
}

function upstreamError(message: string, upstreamStatus: number, detail: Record<string, string>): Response {
  console.error(`[vworld-wms-proxy] ${message} (upstream status=${upstreamStatus})`, detail);
  return jsonError(message, 503);
}

// 투명 1x1 PNG — 200+XML(분류상 coverage=정상 무제공영역)을 타일 자리에 흡수해 지도
// 전체가 회색이 되지 않게. ★Buffer는 Node 런타임 전제 — 이 프록시를 Edge 런타임으로
// 전환하면 Buffer가 없어 깨진다(전환 시 base64→Uint8Array로 교체 필요, 지금은 금지).
const TRANSPARENT_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

function transparentTile(): Response {
  return new Response(TRANSPARENT_PNG, {
    status: 200,
    headers: { "Content-Type": "image/png", "Cache-Control": "public, max-age=3600" },
  });
}

/**
 * Leaflet WMS(`L.tileLayer.wms`)가 조립한 GetMap 쿼리를 받아 VWorld 로 중계한다.
 * @param incoming Leaflet 이 보낸 원본 쿼리(BBOX·WIDTH·HEIGHT·SRS·LAYERS·FORMAT 등). key/domain 없음.
 */
export async function proxyVWorldWms(incoming: URLSearchParams): Promise<Response> {
  const key = vworldKey();
  if (!key) {
    // ★WS-B2: 서버키 부재 → api 타일 프록시로 폴백(관리자 등록 키가 api에는 반영됨).
    //   api측이 레이어 화이트리스트·XML 분류를 동일 계약으로 수행한다. 폴백 오리진도
    //   없으면 기존 정직 503([MAP-006] 평문 금지 — 오류는 항상 JSON).
    const origin = vworldApiFallbackOrigin();
    if (origin) {
      return relayViaApi(`${origin}/api/v1/tiles/vworld/wms?${incoming.toString()}`, "vworld-wms-proxy");
    }
    return jsonError("VWORLD_API_KEY is not configured", 503);
  }

  // ★스머글링 방지(PR#329 R1 리뷰 MEDIUM1, 재현 완료 — `?LAYERS=허용&LAYERS=차단`
  //   중복키·`?layers=차단&LAYERS=허용` 대소문자 변형 둘 다 우회 가능했다):
  //   URLSearchParams#get()은 '첫 값'만 보고, 이후 `new URLSearchParams(incoming)`이
  //   원본을 그대로 복제해 상류로 전달하므로, 검증은 통과해도 미검증 값이 함께
  //   상류에 도달했다. entries() 전수 스캔으로 LAYERS 의 모든 대소문자·중복 변형을
  //   모아 검증한다 — 하나라도 화이트리스트 밖이면 요청 전체를 거부한다.
  const requestedLayers = new Set<string>();
  for (const [k, v] of incoming.entries()) {
    if (k.toLowerCase() !== "layers") continue;
    for (const token of v.split(",").map((s) => s.trim()).filter(Boolean)) {
      requestedLayers.add(token.toLowerCase()); // VWorld WMS는 소문자만 인식 — 대문자 유입 정규화
    }
  }
  if (requestedLayers.size === 0 || ![...requestedLayers].every((layer) => ALLOWED_WMS_LAYERS.has(layer))) {
    return jsonError("Unsupported WMS layer", 400);
  }
  const canonicalLayers = ALLOWED_WMS_LAYERS_ORDER.filter((layer) => requestedLayers.has(layer)).join(",");

  // ★검증 후에도 클라이언트가 보낸 LAYERS/STYLES(대소문자 전 변형)는 전부 버리고,
  //   검증된 canonicalLayers 로만 재구성한다 — "상류로 나가는 값 = 화이트리스트 값"을
  //   구조적으로 강제한다(부분 스머글링 여지 제거). key·domain 은 서버측에서 주입.
  const params = new URLSearchParams();
  for (const [k, v] of incoming.entries()) {
    const lower = k.toLowerCase();
    if (lower === "layers" || lower === "styles") continue; // 아래에서 canonical 값으로 재설정
    params.append(k, v);
  }
  params.set("LAYERS", canonicalLayers);
  params.set("STYLES", canonicalLayers);
  params.set("key", key);
  params.set("domain", "www.4t8t.net");
  if (![...params.keys()].some((k) => k.toLowerCase() === "service")) params.set("SERVICE", "WMS");

  const targetUrl = `${VWORLD_WMS_BASE}?${params.toString()}`;
  try {
    const resp = await fetch(targetUrl, {
      headers: { Referer: "https://www.4t8t.net" },
      next: { revalidate: 60 * 60 * 24 },
    });
    if (!resp.ok) {
      return upstreamError("VWorld WMS upstream error", resp.status, { layers: canonicalLayers });
    }
    const contentType = (resp.headers.get("content-type") ?? "").trim();
    if (contentType && !contentType.toLowerCase().startsWith("image/")) {
      if (contentType.toLowerCase().includes("xml")) {
        // ★MEDIUM2: content-type만으로 무조건 투명타일 처리하지 않는다 — VWorld는 인증/권한
        //   오류도 200+XML로 반환하므로 본문을 읽어 분류한다(classifyVWorldXmlException).
        const bodyText = await resp.text();
        const kind = classifyVWorldXmlException(bodyText);
        if (kind === "coverage") {
          console.warn(`[vworld-wms-proxy] 200 + XML(coverage) → transparent tile`, {
            layers: canonicalLayers,
            contentType,
          });
          return transparentTile();
        }
        // auth/불명 — 무음 흡수 금지, 503으로 승격해 관측 가능하게 한다.
        // ★2026-07-17: ServiceException code를 표면화한다 — 종전 "(auth/unknown)" 뭉뚱그림
        //   탓에 실제 원인 INVALID_RANGE(WMS VERSION 파라미터 오류)가 "키 미설정"으로
        //   오독됐다. code로 INVALID_KEY/UNREGISTERED_DOMAIN/INVALID_RANGE를 즉시 구분한다.
        const detail = extractVWorldXmlExceptionDetail(bodyText);
        // ★키-오류 페일오버(2026-07-17 프로드 INCORRECT_KEY): 로컬 서버키가 '키 자체 무효'로
        //   거부되면 api(관리자 등록 키·#354 통로)로 1회 재중계 — 관리자 화면 키 등록만으로
        //   web 재빌드 없이 복구된다. 파라미터 오류(INVALID_RANGE 등)는 재시도 무의미라 제외.
        if (isVWorldKeyFault(detail.code)) {
          const origin = vworldApiFallbackOrigin();
          if (origin) {
            console.warn(`[vworld-wms-proxy] local key fault (${detail.code}) → api fallback retry`);
            return relayViaApi(`${origin}/api/v1/tiles/vworld/wms?${incoming.toString()}`, "vworld-wms-proxy(key-fault)");
          }
        }
        return upstreamError(
          `VWorld WMS returned an XML exception (${detail.code ?? "auth/unknown"})`,
          resp.status,
          {
            layers: canonicalLayers,
            contentType,
            code: detail.code ?? "",
            message: detail.message ?? "",
            bodySnippet: bodyText.slice(0, 200),
          },
        );
      }
      return upstreamError("VWorld WMS returned a non-image body", resp.status, {
        layers: canonicalLayers,
        contentType,
      });
    }
    const buf = await resp.arrayBuffer();
    return new Response(buf, {
      status: 200,
      headers: {
        "Content-Type": contentType || "image/png",
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
      },
    });
  } catch (error) {
    return jsonError(`VWorld WMS proxy failed: ${String(error)}`, 502);
  }
}
