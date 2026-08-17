import {
  cooldownRemainingSec,
  recordFailure,
  recordSuccess,
  shouldAttempt,
} from "@/lib/vworld-circuit-breaker";
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
 *   이 프록시는 `NEXT_PUBLIC_VWORLD_API_KEY`(브라우저에 노출되는 키)로 폴백하지 않는다 —
 *   폴백을 두면 서버 전용 키가 미설정일 때 조용히 같은 공개 키를 재사용해 "서버 전용 키
 *   분리" 의도가 무력화된다(순 보안이득 ≈ 0). `VWORLD_API_KEY` 미설정 시 503으로 정직 실패.
 *
 *   ★★★2026-08-17 **3차 정정 — 앞의 두 정정이 둘 다 틀렸다.**
 *   나는 "두 키가 같은 값이고 이미 브라우저 번들에 들어 있다"고 두 번 머지했다(#680·#682).
 *   **번들 실측 결과 키는 브라우저에 없다.**
 *
 *     web 이미지에 구워진 NEXT_PUBLIC_VWORLD_API_KEY  sha256 = e3b0c44298fc (= **빈 문자열**)
 *     브라우저 정적 청크에서 키 문자열 검색            **0 건**
 *       └ 조회기 생존 증명: 양성 대조 186/224 파일 · 음성 대조 0 건
 *
 *   ★내가 무엇을 잘못 쟀나(세 번 다 **대상**이 틀렸다):
 *     1차 — 저장소 `.env` 를 쟀다. 어디서도 실효값이 아니다.
 *     2차 — 런타임 env(158 컨테이너)를 쟀다. `NEXT_PUBLIC_*` 는 **빌드타임 인라인**이라
 *           런타임 env 는 클라이언트 번들과 무관하다.
 *     3차(정답) — **이미지에 구워진 값 + 실제 정적 청크**를 봤다.
 *   → `NEXT_PUBLIC_*` 의 노출 여부는 **런타임 env 가 아니라 빌드 산출물**로만 판정된다.
 *
 *   ★그래서 배관 자체를 걷어냈다 — 이 키를 읽는 **클라이언트 코드가 0개**인데
 *   `Dockerfile.web` 의 ARG/ENV 와 compose build arg 만 남아 있었다. 값이 비어 있어
 *   노출은 없었지만, **누가 .env 에 값을 넣는 순간 조용히 번들로 인라인되는 구조**였다.
 *   (부작용도 실재했다: 빈 값 탓에 종전 AvmVisionPanel 의 `if (!KEY) return null` 이 항상
 *    null 을 반환해 항공영상이 아예 렌더되지 않았다 — 배관이 있는데 값이 없어 생긴 결함.)
 *
 *   ★남는 사실: VWorld 키는 실효 기준 **하나**다(관리자 등록키 = 158 web 의 VWORLD_API_KEY,
 *   sha256[:12] 873a35b67f8a).
 *
 *   ★★2026-08-18 정밀화 — 종전 이 자리에 *"그 하나는 **서버 전용으로만 쓰이고** 브라우저엔
 *   없다 → 별도 공개키 발급도 **필요 없다**"* 라고 썼는데 **반대 방향으로 과잉정정**이었다.
 *   사실은 **층마다 다르다**(통합자 독립 재측정으로 교차확인):
 *
 *     저장소 `.env`              스테일 · 어디서도 실효값이 아니다
 *     ★런타임 env(158 web)       `VWORLD_API_KEY` 와 `NEXT_PUBLIC_VWORLD_API_KEY` 가
 *                                **같은 값**이다(둘 다 36자 · 873a35b67f8a) ← 여기가 취약
 *     빌드 산출물(정적 청크)     키 **없음** = 유출 없음(빌드 시 빈 값이 넘어갔다)
 *
 *   → 즉 **"2계약 붕괴"는 설정 층에서 사실**이고, **브라우저 유출로 이어지지 않았을 뿐**이다.
 *     "서버 전용으로만 쓰인다"는 부정확하다 — 같은 값이 **공개 이름(`NEXT_PUBLIC_*`)으로도
 *     런타임에 설정돼 있다.** 값이 같으므로 **어느 경로로든 하나가 노출되면 둘 다 노출**된다.
 *
 *   ★#684 가 없앤 것은 **build-arg 경로**다(Dockerfile ARG/ENV · compose build arg).
 *     **158 런타임 env 의 `NEXT_PUBLIC_VWORLD_API_KEY` 는 여전히 설정돼 있다**(실측 36자,
 *     `.env` 의 `env_file` 경유). 클라이언트가 그 값을 읽지 않으므로 지금은 무해하지만,
 *     **설정 층 중복은 남아 있다.**
 *   → 남은 조치(운영 판단): ①VWorld 콘솔에서 **키 2개 분리 발급** ②158 `.env` 에서
 *     `NEXT_PUBLIC_VWORLD_API_KEY` 제거(소비처 0). 긴급하지는 않다 — **유출은 없었다.**
 *   ※이 주석을 근거로 "키가 유출됐다"고 쓰지 마라(유출 근거는 번들 실측 = 0 건).
 *     동시에 "두 키가 다르다"고도 쓰지 마라(런타임 실측 = 같다). **둘 다 사실이다.**
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
//   ★_line은 '레이어'가 아니라 '스타일' 변형이다(2026-07-17 GetMap 매트릭스 라이브 채증:
//     LAYERS=_line → XML 오류 / LAYERS=채움+STYLES=_line → image/png). 레이어 화이트리스트엔
//     넣지 않고 아래 스타일 결정 로직에서 파생형으로만 허용한다.
// ★규제 오버레이 5종(2026-07-17 GetCapabilities+GetMap 매트릭스 채증 — api측과 동기 유지):
//   upisuq171 개발행위허가제한 · upisuq161 지구단위계획 · um710 상수원보호 ·
//   uo101 교육환경보호 · uq123 고도지구.
const ALLOWED_WMS_LAYERS_ORDER = ["lp_pa_cbnd_bubun", "lp_pa_cbnd_bonbun", "lt_c_uq111", "lt_c_upisuq171", "lt_c_upisuq161", "lt_c_um710", "lt_c_uo101", "lt_c_uq123"] as const;
const ALLOWED_WMS_LAYERS = new Set<string>(ALLOWED_WMS_LAYERS_ORDER);

function vworldKey(): string {
  // ★서버 전용 키만 사용(NEXT_PUBLIC_* 폴백 금지) — 파일 상단 독스트링 참조.
  return (process.env.VWORLD_API_KEY || "").trim();
}

/**
 * @param cacheSec 음성 캐시 초. **0 이면 `no-store`**.
 *   ★기본을 no-store 로 두지 않는다 — 오류를 no-store 로 돌려주면 팬/줌마다 전 타일이
 *   재요청되고, 그 폭주가 바로 차단기를 만들게 한 실장애의 구조다
 *   (`vworld-circuit-breaker.ts` 상단 참조). 호출자가 "폭주해도 되는 오류"인지 정해라.
 */
function jsonError(message: string, status: number, cacheSec = 0): Response {
  return new Response(JSON.stringify({ error: message, status }), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": cacheSec > 0 ? `public, max-age=${cacheSec}` : "no-store",
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

/** 릴레이 링크(158→168) 전용 차단기 키 — 상류(VWorld) 직접 경로와 **별개로** 센다. */
export const RELAY_BREAKER_KEY = "vworld-relay";

/**
 * api(168) 타일 프록시로 중계한다.
 *
 * ★2026-08-17: 릴레이가 **1순위 경로**가 되면서 이 함수도 차단기에 기록한다.
 *   종전엔 `recordSuccess`/`recordFailure` 를 **한 번도 호출하지 않았다** — 직접 경로가
 *   주 경로일 때는 그래도 됐지만, 릴레이가 주 경로가 되면 그 순간
 *   `vworld-circuit-breaker.ts` 가 **아무것도 보호하지 않는 죽은 코드**가 된다.
 *   그러면 #495 가 고친 "실패 폭주" 구조가 158→168 링크에서 그대로 재생산된다 —
 *   자해 대상만 VWorld 에서 우리 백엔드로 바뀔 뿐이다.
 *   → 차단기를 **삭제하지 않고 대상을 옮긴다**(별도 키).
 */
export async function relayViaApi(
  url: string,
  proxyTag: string,
  breakerKey: string | null = null,
): Promise<Response> {
  try {
    const resp = await fetch(url, { next: { revalidate: 60 * 60 * 24 } });
    // api측이 이미 web과 동일 계약(투명타일/503+code)으로 변환해 주므로 그대로 통과.
    if (breakerKey) {
      // 5xx 는 링크/백엔드 장애로 센다. 4xx 는 **요청 자체가 틀린 것**이라 링크 건강과 무관 —
      // 그걸 실패로 세면 잘못된 요청 몇 개가 정상 링크를 차단시킨다(위양성 차단).
      if (resp.status >= 500) recordFailure(breakerKey);
      else recordSuccess(breakerKey);
    }
    const body = await resp.arrayBuffer();
    return new Response(body, {
      status: resp.status,
      headers: {
        "Content-Type": resp.headers.get("content-type") ?? "application/octet-stream",
        "Cache-Control": resp.headers.get("cache-control") ?? "no-store",
      },
    });
  } catch (error) {
    if (breakerKey) recordFailure(breakerKey);
    console.error(`[${proxyTag}] api fallback failed`, { url, error: String(error) });
    // ★원인을 지어내지 마라(2026-08-17 실장애에서 실제로 사람을 오도했다).
    //   여기까지 온 것은 "api 릴레이로 가는 전송이 실패"했다는 사실뿐이다 — 키 상태는 **모른다**.
    //   종전 문구는 `VWORLD_API_KEY is not configured` 라고 **단정**했고, 그 문구가 화면
    //   진단 배너(SatongMultiMap 의 keyFault 분기)까지 올라가 "관리자 화면에 키를 등록하면
    //   복구된다"는 **없는 복구 경로**를 안내했다.
    // ★★2026-08-17 2차 정정 — 여기 있던 "상류(VWorld)가 web 서버 IP 를 차단했다"는 서술도
    //   **근거를 넘은 단정**이었다. 확증되는 것은 "158 출발지에서만 vworld 경로가 막혀 있다"
    //   까지다(158→VWorld 5/5 실패 · 168→VWorld 5/5 200 · DNS 동일). 실패 응답에는
    //   **헤더가 전혀 없어(Server/Date 없음) 응답 주체를 특정할 수 없다.**
    //   TCP·TLS 는 158 에서도 성공하고 그 뒤 HTTP 응답이 오지 않는다는 것까지가 관측이다.
    //   ※"VWorld 에 IP 차단 해제를 요청한다"는 **2026-07-29 에 이미 기각된 오진**이다
    //     (VWorld 에 IP 등록 기능 자체가 없다). 그 선택지를 되살리지 마라.
    //   → 관측된 사실만 말하고, 어느 경로가 끊겼는지 proxyTag 로 식별 가능하게 남긴다.
    // ★★2026-08-18 강등 — 회색 지도 대신 **투명타일 + 강등 헤더**.
    //   실장애(2026-08-16 17:58~17:59)에서 사용자는 이유 없이 회색 지도를 봤다. 근본은
    //   릴레이 목적지(168)의 **상류가 2분간 죽은 것**이었고(그쪽 5xx 183건, 배포 없이 회복)
    //   릴레이로는 우회할 대상이 없다 — 그때 할 수 있는 최선은 **정직하게 알리는 것**이다.
    //
    //   ★그런데 투명타일만 주면 `tileerror` 가 안 떠서 **배너조차 안 뜨는 무음 강등**이 된다.
    //     이 저장소가 세운 "무음 회색타일 금지" 계약을 반대편으로 깨는 것이다.
    //     그래서 강등 사유를 **헤더로 실어** 진단 프로브(fetch — 헤더를 읽을 수 있다)가
    //     배너를 띄우게 한다. `<img>` 는 헤더를 못 읽지만 지도는 안 회색이 되고,
    //     프로브는 강등을 정확히 본다 — 둘 다 만족한다.
    //   ★`X-VWorld-Breaker` 와 **다른 헤더**를 쓴다: 차단기 열림(상류 보호)과
    //     릴레이 도달 불가(대안 없음)는 사용자에게 다른 사실이다.
    return degradedTile(`relay-unreachable:${proxyTag}`);
  }
}

function upstreamError(message: string, upstreamStatus: number, detail: Record<string, string>): Response {
  console.error(`[vworld-wms-proxy] ${message} (upstream status=${upstreamStatus})`, detail);
  return jsonError(message, 503);
}

// ★음성 캐시: 오류를 no-store로 돌려주면 팬할 때마다 전 타일이 상류로 재요청된다.
//   상류가 죽었을 때 더 세게 두드리는 구조가 실제로 IP 차단을 유발했다.
//   짧은 TTL로 실패를 흡수해 폭주를 끊되, 회복은 지연되지 않을 만큼만 잡는다.
const NEGATIVE_CACHE_SEC = 30;
const BREAKER_KEY = "vworld-wms";

/**
 * 직접 경로(158→VWorld) **회복 탐색 간격**.
 *
 * ★왜 직접 경로를 지우지 않는가(2026-08-17 설계 결정):
 *   158 에서 VWorld 로 나가는 요청이 막혀 있어 릴레이를 1순위로 올린다. 그러나 직접 경로를
 *   **삭제하면** 두 가지를 잃는다:
 *     (1) **회복 경로** — 근본원인이 **미상**이라 회복 시점도 미상이다. 미상 원인은 미상
 *         시점에 사라진다. 직접 시도가 없으면 158 이 나아도 아무도 모르고, 복구는 사람이
 *         코드를 되돌려야만 일어난다(= 사실상 영구 우회).
 *     (2) **관측점** — 직접 시도가 158 egress 건강의 유일한 상시 프로브다. 원인이 미상인
 *         상태에서 유일한 진단 신호원을 끄는 것은 비싸다.
 *   → 그래서 **지우지 않고 저빈도로 낮춘다**. 5분에 1건이면 폭주가 아니고(실장애는 팬/줌마다
 *     수십 타일이 전부 실패한 것이었다), 회복은 최대 5분 안에 감지된다.
 * ★프로세스 로컬이다(차단기와 동일 전제). 인스턴스가 여러 개면 각자 5분에 1건씩 태운다.
 */
const DIRECT_RECOVERY_PROBE_MS = 5 * 60_000;
let lastDirectProbeAt = 0;

/**
 * 이번 요청을 **직접 경로**로 태울 것인가.
 * 릴레이 오리진이 없으면(폴백 불가) 직접이 유일 경로이므로 항상 true.
 *
 * ★WMS·WMTS 가 이 게이트를 **공유**한다(모듈 전역 `lastDirectProbeAt`). 둘 다 같은
 *   158→VWorld 경로를 재므로 프로브 1건이 양쪽 질문에 동시에 답한다 — 서비스마다
 *   따로 두면 같은 사실을 재느라 프로브가 2배가 된다.
 */
export function shouldProbeDirect(hasRelay: boolean, now: number = Date.now()): boolean {
  if (!hasRelay) return true;
  if (now - lastDirectProbeAt < DIRECT_RECOVERY_PROBE_MS) return false;
  lastDirectProbeAt = now;
  return true;
}

/** 테스트 전용 — 프로브 시각 초기화. */
export function __resetDirectProbeForTest(): void {
  lastDirectProbeAt = 0;
}

function breakerOpenTile(remainingSec: number): Response {
  // 차단 중에는 상류를 호출하지 않고 투명 타일로 즉시 응답한다(지도는 필지·오버레이 유지).
  return new Response(TRANSPARENT_PNG, {
    status: 200,
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": `public, max-age=${Math.max(5, Math.min(remainingSec, NEGATIVE_CACHE_SEC))}`,
      "X-VWorld-Breaker": "open",
    },
  });
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
 * 강등 사유를 실은 헤더 이름 — 진단 프로브가 이걸 보고 정직 배너를 띄운다.
 * ★`<img>` 는 헤더를 못 읽는다. 그래서 지도는 회색이 되지 않고(투명타일),
 *   헤더를 읽을 수 있는 **fetch 프로브**만 강등을 본다. 둘의 역할이 다르다.
 */
export const VWORLD_DEGRADED_HEADER = "X-VWorld-Degraded";

/**
 * 정직 강등 — 타일 자리는 **투명**으로 비우고, 강등 사실은 **헤더로 관측 가능**하게 남긴다.
 *
 * ★왜 503 JSON 이 아닌가: 503 이면 Leaflet 이 tileerror 로만 처리해 **지도 전체가 회색**이 된다.
 *   2026-08-16 실장애에서 사용자가 본 것이 그것이고, 이유를 알 수 없었다.
 * ★왜 그냥 투명타일이 아닌가: 그러면 `tileerror` 가 안 떠서 **배너조차 안 뜨는 무음 강등**이 된다.
 *   이 저장소의 "무음 회색타일 금지" 계약을 반대편으로 깨는 것이다.
 *   → 투명타일 **+ 헤더**. 지도는 살고, 강등은 숨지 않는다.
 * ★음성 캐시를 짧게 붙인다 — 강등 상태에서 팬/줌하면 전 타일이 재요청되는 폭주를 끊되,
 *   회복이 지연되지 않을 만큼만 잡는다.
 */
export function degradedTile(reason: string): Response {
  // ★★관측점 상실을 상쇄한다(통합자 지적 2026-08-18).
  //   강등을 200 으로 주면 **nginx 접근로그에서 사라진다** — 2026-08-16 실사용 장애가
  //   보였던 이유가 정확히 "5xx 라서 로그에 남았다" 였다. UX(회색지도 제거)를 택한 대가로
  //   그 관측점을 잃는다. 그래서 **서버 로그에 안정된 표식**을 남긴다:
  //   `[vworld-degraded]` 는 grep 앵커이고 reason 이 어느 경로인지 말한다.
  //   ※이것은 nginx 로그의 완전한 대체가 아니다(집계·시계열이 아니다). 지속 관측은
  //     api 쪽 `platform_events` 나 접근로그 설정이 담당해야 하며 그쪽은 이 PR 범위 밖이다.
  //     여기 적어 두는 이유는 **대가를 치렀다는 사실을 지우지 않기 위해서**다.
  console.warn(`[vworld-degraded] ${reason}`);
  return new Response(TRANSPARENT_PNG, {
    status: 200,
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": `public, max-age=${NEGATIVE_CACHE_SEC}`,
      [VWORLD_DEGRADED_HEADER]: reason,
    },
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
      return relayViaApi(`${origin}/api/v1/tiles/vworld/wms?${incoming.toString()}`, "vworld-wms-proxy", RELAY_BREAKER_KEY);
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
  // ★V1 선 스타일(위성뷰): 클라이언트 STYLES 토큰이 정확히 '각 canonical 레이어+_line'
  //   집합이면 선 스타일을 유지한다(그 외 임의 스타일은 canonical로 강제 — 스머글링 불변).
  const requestedStyles = new Set<string>();
  for (const [k, v] of incoming.entries()) {
    if (k.toLowerCase() !== "styles") continue;
    for (const token of v.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean)) {
      requestedStyles.add(token);
    }
  }
  const canonicalList = canonicalLayers.split(",");
  const lineStyleRequested =
    requestedStyles.size === canonicalList.length &&
    canonicalList.every((layer) => requestedStyles.has(`${layer}_line`));
  params.set(
    "STYLES",
    lineStyleRequested ? canonicalList.map((layer) => `${layer}_line`).join(",") : canonicalLayers,
  );
  params.set("key", key);
  params.set("domain", "www.4t8t.net");
  if (![...params.keys()].some((k) => k.toLowerCase() === "service")) params.set("SERVICE", "WMS");

  const targetUrl = `${VWORLD_WMS_BASE}?${params.toString()}`;
  const relayOrigin = vworldApiFallbackOrigin();
  const relayUrl = relayOrigin
    ? `${relayOrigin}/api/v1/tiles/vworld/wms?${incoming.toString()}`
    : null;

  // ★★2026-08-17 — **릴레이를 1순위로 승격**한다(A② 타일 경로 168 일원화).
  //   158 에서 VWorld 로 나가는 요청이 막혀 있다(5/5 실패 · 168 은 5/5 200 · 원인 미상).
  //   종전 구조는 매 요청마다 **먼저 직접을 때리고 실패한 뒤** 릴레이했다. 차단기가 5연속
  //   실패 후 그걸 줄여 주긴 하지만, 쿨다운(60s)마다 다시 열려 같은 실패를 반복한다.
  //   → 릴레이를 먼저 태우고, 직접은 **회복 탐색**으로만 남긴다(DIRECT_RECOVERY_PROBE_MS).
  //   ★"직접을 지우자"는 기각됐다 — 지우면 회복 경로와 158 관측점을 함께 잃는다.
  //     근거는 shouldProbeDirect 독스트링에 한 곳으로 모았다.
  if (relayUrl && !shouldProbeDirect(true)) {
    return relayViaApi(relayUrl, "vworld-wms-proxy(relay-primary)", RELAY_BREAKER_KEY);
  }

  // ★상류가 연속 실패 중이면 아예 호출하지 않는다 — 실패 요청 폭주가 실장애를 키웠다.
  //   다만 투명 타일로 끝내지 않고 **api(168) 타일 프록시로 릴레이**를 먼저 시도한다:
  //   이 서버(web)에서만 VWorld 경로가 막히고 api 서버는 정상인 상황이 실제로 발생했다.
  if (!shouldAttempt(BREAKER_KEY)) {
    if (relayUrl) {
      return relayViaApi(relayUrl, "vworld-wms-proxy(breaker-open)", RELAY_BREAKER_KEY);
    }
    return breakerOpenTile(cooldownRemainingSec(BREAKER_KEY));
  }
  try {
    const resp = await fetch(targetUrl, {
      headers: { Referer: "https://www.4t8t.net" },
      next: { revalidate: 60 * 60 * 24 },
    });
    if (!resp.ok) {
      recordFailure(BREAKER_KEY);
      // 키 오류뿐 아니라 '상류 자체가 응답을 못 주는' 경우도 api 릴레이로 구제한다.
      const origin = vworldApiFallbackOrigin();
      if (origin) {
        return relayViaApi(
          `${origin}/api/v1/tiles/vworld/wms?${incoming.toString()}`,
          "vworld-wms-proxy(upstream-error)",
          RELAY_BREAKER_KEY,
        );
      }
      return upstreamError("VWorld WMS upstream error", resp.status, { layers: canonicalLayers });
    }
    recordSuccess(BREAKER_KEY);
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
        if (isVWorldKeyFault(detail)) {
          const origin = vworldApiFallbackOrigin();
          if (origin) {
            console.warn(`[vworld-wms-proxy] local key fault (${detail.code}) → api fallback retry`);
            return relayViaApi(`${origin}/api/v1/tiles/vworld/wms?${incoming.toString()}`, "vworld-wms-proxy(key-fault)", RELAY_BREAKER_KEY);
          }
        }
        recordFailure(BREAKER_KEY);
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
    // ★네트워크 예외(상류 도달 불가·DNS·타임아웃)도 실패로 집계 — 이번 실장애가 이 경로였다.
    recordFailure(BREAKER_KEY);
    const origin = vworldApiFallbackOrigin();
    if (origin) {
      console.warn(`[vworld-wms-proxy] upstream unreachable → api relay`, { error: String(error).slice(0, 120) });
      return relayViaApi(
        `${origin}/api/v1/tiles/vworld/wms?${incoming.toString()}`,
        "vworld-wms-proxy(unreachable)",
        RELAY_BREAKER_KEY,
      );
    }
    // ★릴레이 오리진조차 없다 = 대안이 아예 없다. 그래도 **사용자에게는 회색 지도가 아니라
    //   정직 강등**을 준다(위 degradedTile 독스트링 참조). 운영자용 시끄러움은 바로 위
    //   `console.warn/error` 가 담당한다 — 화면을 회색으로 만드는 것이 관측성이 아니다.
    //   ★사유를 구분해 남긴다: 오리진 미설정은 **설정 결함**이라 처방이 다르다.
    return degradedTile("no-relay-origin:vworld-wms-proxy");
  }
}
