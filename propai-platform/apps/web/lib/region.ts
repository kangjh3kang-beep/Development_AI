/**
 * regionFromAddress — 주소 문자열에서 매스 백본 조회용 region 키(시군구)를 도출.
 *
 * mass_templates.region은 시군구 라벨로 시드된다(신도시 PNU를 해당 시군구 라벨로 수집).
 * 따라서 조회도 같은 규칙으로 시군구를 뽑아야 매칭된다. 광역/특별시 자체는 표본이 이질적이라
 * 제외하고 구 > 시 > 군 순으로 가장 구체적인 자치구역을 고른다.
 * 매칭 실패 시 undefined(임의 추정 금지 — 조회를 건너뛰어 graceful).
 *
 * ★SSOT: 백엔드 app/services/mass_backbone/region_util.py(region_from_address)와 **동일 규칙**을 유지한다.
 *   저장(collect가 대장 주소로 시군구 정규화)과 조회(여기, site.address로 시군구)가 같은 규칙이어야
 *   `WHERE region = :region` 정확 일치로 매칭된다(규칙 변경 시 양쪽 함께 수정).
 */
export function regionFromAddress(address?: string | null): string | undefined {
  const s = (address || "").trim();
  if (!s) return undefined;
  // 구 우선(서울 자치구·시 산하 구). 구 뒤에 경계(공백/끝/숫자)가 와야 동·번지 한글과 안 섞임.
  const gu = s.match(/([가-힣]+구)(?:\s|$|\d)/);
  if (gu) return gu[1];
  // 시(단, '특별시/광역시' 자체는 너무 광역이라 제외 — 산하 구가 없을 때만 여기 도달).
  const allSi = s.match(/[가-힣]+시/g);
  if (allSi) {
    const real = allSi.find((t) => !/(특별시|광역시)$/.test(t));
    if (real) return real;
  }
  // 군
  const gun = s.match(/([가-힣]+군)(?:\s|$|\d)/);
  if (gun) return gun[1];
  return undefined;
}
