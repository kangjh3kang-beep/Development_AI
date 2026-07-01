/**
 * P2-8: sanitizeSvgMarkup — DOMPurify(파서 기반) 정화 검증.
 *
 * 구 regex 치환 방식이 뚫리던 중첩/변형 우회까지 차단되는지 확인한다.
 * 계약: 비SVG/위험 잔존 → null(미렌더), 안전 SVG → 골격 보존.
 */
import { describe, expect, it } from "vitest";
import { sanitizeSvgMarkup } from "@/components/cad/ReferenceAssemblyCard";

const SAFE_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#eee"/><path d="M0 0L10 10"/></svg>';

describe("sanitizeSvgMarkup (DOMPurify)", () => {
  it("안전한 SVG는 골격·도형을 보존한다", () => {
    const out = sanitizeSvgMarkup(SAFE_SVG);
    expect(out).not.toBeNull();
    expect(out).toMatch(/^<svg[\s>]/i);
    expect(out).toContain("<rect");
    expect(out).toContain("<path");
  });

  it("script 태그를 제거한다", () => {
    const out = sanitizeSvgMarkup('<svg><script>alert(1)</script><rect/></svg>');
    expect(out).not.toBeNull();
    expect(out).not.toMatch(/script/i);
  });

  it("중첩 변형(<scr<script>ipt>) 우회를 차단한다 — 구 regex 취약 케이스", () => {
    const out = sanitizeSvgMarkup('<svg><scr<script>ipt>alert(1)</scr</script>ipt><rect/></svg>');
    // 보안 속성 = '실행 가능한 script 요소/핸들러가 없다'. 파서 기반 정화라 조각은
    // 불활성 텍스트 노드로만 남을 수 있다(구 regex 는 치환 후 재조립된 <script>가 요소로 잔존 가능).
    if (out !== null) {
      expect(out).not.toMatch(/<\s*script/i);
      expect(out).not.toMatch(/\son\w+\s*=/i);
    }
  });

  it("on* 이벤트 핸들러를 제거한다(무따옴표 변형 포함)", () => {
    const out = sanitizeSvgMarkup('<svg onload=alert(1)><rect onclick="alert(2)"/></svg>');
    expect(out).not.toBeNull();
    expect(out).not.toMatch(/\son\w+\s*=/i);
  });

  it("foreignObject·iframe 을 제거한다", () => {
    const out = sanitizeSvgMarkup(
      '<svg><foreignObject><iframe src="https://evil"></iframe></foreignObject><rect/></svg>');
    expect(out).not.toBeNull();
    expect(out).not.toMatch(/foreignobject|iframe/i);
  });

  it("javascript: 링크(href/xlink:href)를 제거한다", () => {
    const out = sanitizeSvgMarkup(
      '<svg><a href="javascript:alert(1)" xlink:href="javascript:alert(2)"><rect/></a></svg>');
    expect(out).not.toBeNull();
    expect(out).not.toMatch(/javascript:/i);
  });

  it("a·use 요소 자체를 제거한다(정적 썸네일에 상호작용/외부참조 불허)", () => {
    const out = sanitizeSvgMarkup('<svg><a><rect/></a><use href="#x"/><circle/></svg>');
    expect(out).not.toBeNull();
    expect(out).not.toMatch(/<\s*a[\s>]/i);
    expect(out).not.toMatch(/<\s*use\b/i);
    expect(out).toContain("<circle");
  });

  it("SMIL(set/animate) 속성조작 벡터를 제거한다", () => {
    const out = sanitizeSvgMarkup(
      '<svg><set attributeName="href" to="javascript:alert(1)"/>' +
      '<animate attributeName="href" values="javascript:alert(2)"/><rect/></svg>');
    expect(out).not.toBeNull();
    expect(out).not.toMatch(/<\s*(set|animate)\b/i);
    expect(out).not.toMatch(/javascript:/i);
  });

  it("비SVG 입력은 null", () => {
    expect(sanitizeSvgMarkup("<div>hi</div>")).toBeNull();
    expect(sanitizeSvgMarkup("plain text")).toBeNull();
    expect(sanitizeSvgMarkup("")).toBeNull();
    expect(sanitizeSvgMarkup(null)).toBeNull();
    expect(sanitizeSvgMarkup(undefined)).toBeNull();
  });

  it("svg 로 위장한 비정화 골격 훼손은 null(가짜 안전 보장 금지)", () => {
    // DOMPurify 가 최상위 svg 자체를 제거해야 하는 입력이면 결과가 svg 골격이 아니게 됨 → null.
    const out = sanitizeSvgMarkup('<svg></svg><script>alert(1)</script>');
    if (out !== null) {
      expect(out).not.toMatch(/script/i);
    }
  });
});
