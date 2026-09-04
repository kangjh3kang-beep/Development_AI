/**
 * 필드 라벨·단위 SSOT 계약 잠금.
 *
 * ★사용자 지적 2건을 회귀락으로 고정한다:
 *   ①원시 키(effective_far.zone_mix[*].area_sqm)를 화면에 내보내지 않는다
 *   ②"변화율 33%" 대신 실제 단위 증감(−1개 / −23,632㎡)을 보여준다
 */

import { describe, expect, it } from "vitest";
import {
  fieldMeta,
  formatDelta,
  formatFieldValue,
  normalizeFieldKey,
} from "@/lib/analysis-field-labels";

describe("normalizeFieldKey", () => {
  it("배열 인덱스를 [*]로 정규화한다(백엔드 _normalize_key와 동일 규칙)", () => {
    expect(normalizeFieldKey("effective_far.zone_mix[0].area_sqm")).toBe(
      "effective_far.zone_mix[*].area_sqm",
    );
    expect(normalizeFieldKey("a[0].b[12].c")).toBe("a[*].b[*].c");
  });
});

describe("fieldMeta", () => {
  it("★라이브 오표기 키들이 전부 한국어 라벨을 갖는다", () => {
    // 프로덕션 화면에 원시 키로 노출됐던 실제 4건.
    expect(fieldMeta("effective_far.parcel_count")?.label).toBe("선택 필지 수");
    expect(fieldMeta("effective_far.zone_mix[*].area_sqm")?.label).toBe("용도지역별 면적");
    expect(fieldMeta("land_area_sqm")?.label).toBe("대지면적");
    expect(fieldMeta("location.education.school_count")?.label).toBe("반경 내 학교");
  });

  it("인덱스가 붙은 원본 키도 정규화 후 매칭된다", () => {
    expect(fieldMeta("effective_far.zone_mix[3].area_sqm")?.label).toBe("용도지역별 면적");
  });

  it("★미등재 키는 이름을 지어내지 않고 null을 낸다(날조 금지)", () => {
    expect(fieldMeta("sd_gate.ratio")).toBeNull();
    expect(fieldMeta("완전히_모르는_키")).toBeNull();
  });
});

describe("formatFieldValue", () => {
  it("천단위 구분과 단위를 붙인다", () => {
    expect(formatFieldValue(152826, fieldMeta("land_area_sqm"))).toBe("152,826㎡");
    expect(formatFieldValue(2, fieldMeta("effective_far.parcel_count"))).toBe("2개");
    expect(formatFieldValue(1, fieldMeta("location.education.school_count"))).toBe("1곳");
  });

  it("비율은 소수 1자리로 고정한다(부동소수 지터 노출 방지)", () => {
    expect(formatFieldValue(80.00000000001, fieldMeta("effective_far.effective_far_pct"))).toBe("80.0%");
  });

  it("면적·개수는 정수로 절사한다", () => {
    expect(formatFieldValue(152826.4, fieldMeta("land_area_sqm"))).toBe("152,826㎡");
  });

  it("수치가 아니면 그대로 문자열화한다", () => {
    expect(formatFieldValue("보전관리지역", null)).toBe("보전관리지역");
    expect(formatFieldValue(null, null)).toBe("-");
  });
});

describe("formatDelta", () => {
  it("★변화율이 아니라 실제 단위 증감을 낸다", () => {
    expect(formatDelta(176458, 152826, fieldMeta("land_area_sqm"))).toBe("−23,632㎡");
    expect(formatDelta(3, 2, fieldMeta("effective_far.parcel_count"))).toBe("−1개");
    expect(formatDelta(5, 1, fieldMeta("location.education.school_count"))).toBe("−4곳");
  });

  it("증가는 + 부호를 붙인다", () => {
    expect(formatDelta(2, 3, fieldMeta("effective_far.parcel_count"))).toBe("+1개");
  });

  it("차이가 없거나 수치가 아니면 증감을 만들지 않는다", () => {
    expect(formatDelta(2, 2, fieldMeta("effective_far.parcel_count"))).toBeNull();
    expect(formatDelta("a", "b", null)).toBeNull();
    expect(formatDelta(Infinity, 1, null)).toBeNull();
  });

  it("★퍼센트 문자열을 절대 만들지 않는다(종전 '변화율 33%' 근절)", () => {
    const outputs = [
      formatDelta(3, 2, fieldMeta("effective_far.parcel_count")),
      formatDelta(176458, 152826, fieldMeta("land_area_sqm")),
      formatDelta(5, 1, fieldMeta("location.education.school_count")),
    ];
    for (const o of outputs) {
      expect(o).not.toBeNull();
      expect(o).not.toContain("변화율");
    }
  });
});
