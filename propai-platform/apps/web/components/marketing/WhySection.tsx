/**
 * Why — paper 섹션. H2 + 검증된 스탯 카드 3장 + 실사진 그리드.
 *
 * ★ 스탯 수치는 전부 코드베이스에서 파생 검증한 값만 사용(무근거 수치 0):
 *   • 12 = 지도 데이터 레이어(components/precheck/SatongMapShell.tsx LAYERS 배열)
 *   • 9  = AI 리포트/산출물 종수(components/dashboard/DashboardHome.tsx creationProducts)
 *   • 3  = 보고서 출력 포맷(apps/api/app/services/report/{pdf,docx,pptx}_renderer.py)
 *
 * ★2026-08-28 교정 — 위 «무근거 수치 0» 은 **선언이었고 락이 없었다.** 재보니 셋 중 **둘이 틀렸다**:
 *   · 11 → 실제 LAYERS **12** 개
 *   · 6  → 실제 creationProducts **9** 개(생성 허브 9번째 카드가 들어왔다)
 *   그리고 위 경로 자체가 틀렸다(`page.tsx` 가 아니라 `DashboardHome.tsx`).
 *   ★**선언은 스스로를 검증하지 않는다.** 이제
 *   `apps/api/tests/test_ui_capability_claims_are_backed_by_code.py` 가 이 세 수를
 *   **배열에서 파생해** 잠근다 — 배열이 늘면 이 파일이 빨개진다.
 */
const stats = [
  {
    value: "12",
    unit: "종",
    label: "지도 데이터 레이어",
    desc: "지적·용도지역·공시지가·실거래·경공매·POI까지 한 지도에서 겹쳐 봅니다.",
  },
  {
    value: "9",
    unit: "종",
    label: "AI 리포트",
    desc: "후보지 진단서·사업성·시장·인허가·설계·건축개요를 산출물 단위로 생성합니다.",
  },
  {
    value: "3",
    unit: "포맷",
    label: "보고서 출력",
    desc: "PDF·DOCX·PPTX로 내보내 그대로 심의·보고 자료로 씁니다.",
  },
] as const;

const shots = [
  { src: "/landing/why-1.webp", alt: "지도 기반 후보지 사전검토 화면" },
  { src: "/landing/why-2.webp", alt: "AI 수지분석 리포트 화면" },
  { src: "/landing/why-3.webp", alt: "설계·법규 검토 화면" },
] as const;

export function WhySection() {
  return (
    <section className="mkt-section mkt-section--paper">
      <div className="mkt-container flex flex-col gap-14">
        <div className="flex flex-col gap-6">
          <span className="mkt-label-pill">
            <span className="mkt-glyph">✦</span>왜 사통팔땅
          </span>
          <h2 className="mkt-h2" style={{ maxWidth: "18ch" }}>
            한 달 걸리는 검토를
            <br />
            하루 만에.
          </h2>
          <p className="mkt-body-l" style={{ maxWidth: "52ch" }}>
            흩어진 공공데이터와 반복 작업을 자동화해, 사전검토부터 보고서까지 한 흐름으로 끝냅니다.
          </p>
        </div>

        {/* 검증된 스탯 3장 */}
        <div className="grid gap-4 md:grid-cols-3">
          {stats.map((s) => (
            <div key={s.label} className="mkt-card" style={{ padding: "28px 26px" }}>
              <div className="flex items-baseline gap-1">
                <span
                  className="mkt-num"
                  style={{ fontSize: "clamp(44px, 5vw, 64px)", fontWeight: 600, color: "var(--mkt-ink)" }}
                >
                  {s.value}
                </span>
                <span
                  className="mkt-num"
                  style={{ fontSize: 20, fontWeight: 600, color: "var(--mkt-accent-deep)" }}
                >
                  {s.unit}
                </span>
              </div>
              <h3
                style={{
                  marginTop: 10,
                  fontFamily: "var(--mkt-font-sans)",
                  fontWeight: 600,
                  fontSize: 18,
                  color: "var(--mkt-ink)",
                }}
              >
                {s.label}
              </h3>
              <p style={{ marginTop: 8, fontSize: 14, lineHeight: 1.6, color: "var(--mkt-graphite)" }}>
                {s.desc}
              </p>
            </div>
          ))}
        </div>

        {/* 실사진 그리드 */}
        <div className="grid gap-4 md:grid-cols-3">
          {shots.map((shot) => (
            <div key={shot.src} className="mkt-img-frame" style={{ aspectRatio: "3 / 2" }}>
              {/* 이미 최적화된 webp 정적 자산 — 플랫폼 실화면 캡처 */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={shot.src} alt={shot.alt} width={1264} height={848} loading="lazy" decoding="async" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
