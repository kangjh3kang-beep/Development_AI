/**
 * 전주기 모듈 — 다크 섹션 + 넘버링 4행(Part A A4 넘버링 리스트).
 * 각 행: 앰버 넘버 + 대형 항목명 + 우측 설명.
 */
const modules = [
  {
    idx: "01",
    title: "지도 사전검토",
    desc: "지적·용도지역·공시지가·실거래·경공매 레이어를 한 지도에서.",
  },
  {
    idx: "02",
    title: "토지확보",
    desc: "등기·토지조서·동의율·등기 변동 모니터링 자동화.",
  },
  {
    idx: "03",
    title: "AI 수지분석",
    desc: "실거래 연동 시나리오·민감도 분석.",
  },
  {
    idx: "04",
    title: "설계·법규 검토",
    desc: "AI 설계안과 법규 자동 검토, 인허가 로드맵.",
  },
] as const;

export function ModulesSection() {
  return (
    <section className="mkt-section mkt-section--ink">
      <div className="mkt-container">
        <span className="mkt-label-pill">
          <span className="mkt-glyph">✦</span>
          전주기 모듈
        </span>

        <div className="mt-10">
          {modules.map((m) => (
            <div key={m.idx} className="mkt-num-row">
              <span className="mkt-num-row__idx">{m.idx}</span>
              <h3 className="mkt-num-row__title">{m.title}</h3>
              <p className="mkt-num-row__desc">{m.desc}</p>
            </div>
          ))}
          {/* 마지막 행 하단 구분선 */}
          <div style={{ borderTop: "1px solid rgba(255,255,255,0.14)" }} />
        </div>
      </div>
    </section>
  );
}
