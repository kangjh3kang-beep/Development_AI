/**
 * Phase 1-H — 소셜 푸시 등록(과설계 금지·실패 무해).
 *
 * 백엔드 계약: POST /api/v1/social/push/register {token, platform:web|ios|android} → {registered,platform}
 * sw.js(public/sw.js)는 이미 'push' 핸들러(showNotification)를 보유한다.
 *
 * 정책:
 *   - 환경이 지원하고 권한이 허용된 경우에만 토큰을 등록한다.
 *   - FCM 미구성 환경에서는 PushManager 구독 endpoint(웹푸시 토큰)를 폴백으로 등록한다.
 *     (백엔드가 FCM 키 미설정 시 graceful skip 하므로, 실패해도 채팅 기능엔 무해)
 *   - 권한 거부/미지원/구독 실패는 조용히 무시(채팅·친구 기능과 독립).
 */
import { apiClient } from "@/lib/api-client";

let registered = false;

/**
 * 앱 진입 시 1회 호출. 권한 요청 + 가능 환경에서 토큰 등록.
 * 어떤 단계든 실패하면 조용히 종료한다(반환값 없음, throw 없음).
 */
export async function registerSocialPush(): Promise<void> {
  if (registered) return;
  if (typeof window === "undefined") return;
  try {
    if (!("serviceWorker" in navigator) || !("Notification" in window)) return;

    // 권한 — 이미 거부면 중단(재요청 안 함).
    let perm = Notification.permission;
    if (perm === "default") {
      perm = await Notification.requestPermission();
    }
    if (perm !== "granted") return;

    const reg = await navigator.serviceWorker.ready;

    // 웹푸시 endpoint(VAPID 키 없이 구독 가능한 환경 한정). 실패 시 토큰 없이 진행.
    let token = "";
    try {
      if (reg.pushManager) {
        const existing = await reg.pushManager.getSubscription();
        if (existing) token = existing.endpoint;
      }
    } catch {
      token = "";
    }

    // endpoint 미확보 시: FCM 토큰 부재 환경. 등록 생략(백엔드 graceful) — 과설계 회피.
    if (!token) return;

    await apiClient.post<{ registered: boolean; platform: string }>("/social/push/register", {
      body: { token, platform: "web" },
    });
    registered = true;
  } catch {
    // 무해: 푸시 미지원/거부/네트워크 실패는 채팅 핵심기능과 독립.
  }
}
