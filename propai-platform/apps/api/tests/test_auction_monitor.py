"""경공매 모니터링 매칭 엔진 단위테스트 — 무목업·외부 실호출 금지(픽스처/직접 호출만).

검증 범위:
  1) detect_columns: 다양한 헤더명(PNU/지번/주소/소재지/도로명주소)에서 표준필드 감지.
  2) parse_watchlist_excel: xlsx/csv 파싱, 컬럼 자동감지, 미인식행 스킵, PNU 정규화,
     빈 파일/미인식 헤더 → ValueError(정직).
  3) normalize_address / address_matches: 정규화 후 부분일치(괄호/공백/구분자 무시).
  4) point_in_polygon: shapely point-in-polygon(더미 좌표·GeoJSON Polygon).
"""

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.auction.monitor import (  # noqa: E402
    address_matches,
    detect_columns,
    normalize_address,
    parse_watchlist_excel,
    point_in_polygon,
)


def _xlsx_bytes(headers, rows):
    """openpyxl로 메모리 xlsx 생성(픽스처)."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── 1) 컬럼 자동감지 ──
class TestDetectColumns:
    def test_pnu_헤더_감지(self):
        d = detect_columns(["PNU", "비고"])
        assert d["pnu"] == "PNU"
        assert d["label"] == "비고"

    def test_다양한_주소헤더_감지(self):
        assert detect_columns(["소재지"])["address"] == "소재지"
        assert detect_columns(["지번주소"])["address"] == "지번주소"
        assert detect_columns(["도로명주소"])["address"] == "도로명주소"
        assert detect_columns(["토지 소재지"])["address"] == "토지 소재지"

    def test_고유번호_pnu별칭(self):
        assert detect_columns(["토지고유번호"])["pnu"] == "토지고유번호"

    def test_미인식_헤더(self):
        d = detect_columns(["금액", "면적"])
        assert d["pnu"] is None and d["address"] is None


# ── 2) Excel/CSV 파싱 ──
class TestParseWatchlist:
    def test_pnu컬럼_xlsx_파싱(self):
        raw = _xlsx_bytes(
            ["PNU", "물건명"],
            [["1111010100100010000", "역삼동 토지"], ["2222020200200020000", "분당 상가"]],
        )
        res = parse_watchlist_excel(raw, "watch.xlsx")
        assert res["parsed_count"] == 2
        assert res["detected_columns"]["pnu"] == "PNU"
        assert res["rows"][0]["pnu"] == "1111010100100010000"
        assert res["rows"][0]["label"] == "역삼동 토지"

    def test_주소컬럼_csv_파싱(self):
        csv = "소재지,비고\n서울시 강남구 역삼동 100,A\n,빈주소\n".encode()
        res = parse_watchlist_excel(csv, "list.csv")
        assert res["detected_columns"]["address"] == "소재지"
        # 빈 주소·빈 PNU 행은 스킵.
        assert res["parsed_count"] == 1
        assert res["skipped_rows"] == 1
        assert res["rows"][0]["address"] == "서울시 강남구 역삼동 100"

    def test_pnu_하이픈_정규화(self):
        raw = _xlsx_bytes(["PNU"], [["1111-0101-001-0001-0000"]])
        res = parse_watchlist_excel(raw, "x.xlsx")
        assert res["rows"][0]["pnu"] == "1111010100100010000"

    def test_주소컬럼에_pnu값_보조인식(self):
        # 헤더는 주소지만 값이 19자리 → PNU로 보조 인식.
        raw = _xlsx_bytes(["소재지"], [["1111010100100010000"]])
        res = parse_watchlist_excel(raw, "x.xlsx")
        assert res["rows"][0]["pnu"] == "1111010100100010000"

    def test_미인식_헤더_에러(self):
        raw = _xlsx_bytes(["금액", "면적"], [["100", "50"]])
        with pytest.raises(ValueError):
            parse_watchlist_excel(raw, "x.xlsx")

    def test_빈파일_에러(self):
        with pytest.raises(ValueError):
            parse_watchlist_excel(b"", "x.xlsx")


# ── 3) 주소 매칭 ──
class TestAddressMatch:
    def test_정규화_공백구분자_제거(self):
        assert normalize_address("서울시 강남구 역삼동 100") == "서울시강남구역삼동100"
        assert normalize_address("역삼동 100 (대) 200㎡") == "역삼동100200㎡"

    def test_부분일치(self):
        assert address_matches("강남구 역삼동 100", "서울시 강남구 역삼동 100번지")
        assert address_matches("서울시 강남구 역삼동 100-1", "강남구 역삼동 100-1")

    def test_불일치(self):
        assert not address_matches("강남구 역삼동", "분당구 정자동")

    def test_짧은주소_매칭안함(self):
        assert not address_matches("동", "강남구 역삼동")

    def test_빈값_매칭안함(self):
        assert not address_matches("", "강남구")
        assert not address_matches("강남구", None)


# ── 4) point-in-polygon ──
class TestPointInPolygon:
    POLY = {
        "type": "Polygon",
        "coordinates": [[[127.0, 37.0], [127.1, 37.0], [127.1, 37.1], [127.0, 37.1], [127.0, 37.0]]],
    }

    def test_내부점(self):
        # (lat, lon) = (37.05, 127.05) → 내부.
        assert point_in_polygon(37.05, 127.05, self.POLY) is True

    def test_외부점(self):
        assert point_in_polygon(38.0, 128.0, self.POLY) is False

    def test_잘못된_geojson(self):
        assert point_in_polygon(37.05, 127.05, {"type": "Bogus"}) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
