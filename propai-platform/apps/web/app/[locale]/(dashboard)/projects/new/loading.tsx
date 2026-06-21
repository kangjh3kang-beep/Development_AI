// ★성능(체감 로딩): 라우트 전환 즉시 스켈레톤을 띄운다. loading.tsx가 없으면 Next.js가
//   RSC+청크 로드가 끝날 때까지 빈 화면으로 블로킹해 '프로젝트 생성 누르면 한참 멈춤'처럼 보인다.
//   이 스켈레톤은 클릭 즉시 떠서 체감 로딩시간을 크게 줄인다(실제 페이지 준비되면 자동 교체).
//   순수 표현(데이터/기능 0)·서버 컴포넌트.
export default function NewProjectLoading() {
  return (
    <div className="flex flex-col gap-10 pb-20 max-w-3xl mx-auto mt-4 animate-pulse" aria-busy="true">
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <span className="cc-meta">NEW PROJECT · INTAKE CONSOLE</span>
          <span className="cc-live"><i />READY</span>
        </div>
        <div className="h-10 w-56 rounded-lg bg-[var(--surface-soft)]" />
        <div className="h-4 w-80 rounded bg-[var(--surface-soft)]" />
      </div>
      <section className="cc-bracketed cc-panel">
        <div className="space-y-5">
          <div className="h-5 w-40 rounded bg-[var(--surface-soft)]" />
          <div className="h-12 w-full rounded-xl bg-[var(--surface-soft)]" />
          <div className="h-5 w-32 rounded bg-[var(--surface-soft)]" />
          <div className="h-24 w-full rounded-xl bg-[var(--surface-soft)]" />
          <div className="h-12 w-full rounded-xl bg-[var(--surface-soft)]" />
        </div>
      </section>
      <span className="sr-only">새 프로젝트 화면을 불러오는 중…</span>
    </div>
  );
}
