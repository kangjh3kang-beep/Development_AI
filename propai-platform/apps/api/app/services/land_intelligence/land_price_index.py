"""지가변동률 기반 시점수정 — 공시기준일(1/1)→가격시점 누적 변동계수.

공시지가기준법의 '시점수정'은 표준지 공시기준일부터 가격시점까지 지가변동률을 누적 적용.
한국부동산원 R-ONE 지가변동률(시도별 연간) 근사 테이블을 사용(고정 1.02 대체).
실시간 API 연동 시 _ANNUAL_RATE를 동적 갱신하면 됨.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# 시도별 연간 지가변동률(근사, R-ONE 최근추세 기반). 실데이터 연동 시 대체.
_ANNUAL_RATE: dict[str, float] = {
    "서울": 0.025, "경기": 0.022, "인천": 0.020,
    "부산": 0.012, "대구": 0.008, "대전": 0.015, "광주": 0.012,
    "울산": 0.010, "세종": 0.018, "강원": 0.012, "충북": 0.013,
    "충남": 0.013, "전북": 0.010, "전남": 0.010, "경북": 0.009,
    "경남": 0.010, "제주": 0.012,
}
_DEFAULT_RATE = 0.018  # 전국 평균 근사


#: 주소 앞에 붙는 **비주소 잡음** — 우편번호 접두만 벗긴다.
#:
#: ★★독립 리뷰 R2 MEDIUM-1 정정: 종전 판은 `\([^)]{1,20}\)` · `\[[^\]]{1,20}\]` 로 **임의의**
#:   괄호/대괄호 라벨을 벗기면서 독스트링에 *"이 목록은 **닫혀 있다**"* 고 썼다 — **거짓 면역
#:   주장**이었다(§C-11). 그리고 실제로 **시도를 품은 라벨까지 벗겨** 회귀를 냈다(실측):
#:       '(주)오케이 서울특별시 강남구' 서울 → ''    '[경기도] 성남시 분당구' 경기 → ''
#:       '(서울) 강남구 역삼동'        서울 → ''    '(광주광역시) 북구'      광주 → ''
#:   11개 형태 중 **9개 회귀**. `대한민국|한국` 을 경계 없이 벗긴 것도 위험했다
#:   (`한국은행 서울특별시…` 의 앞 두 글자만 잘려 나갔다).
#:
#: ⇒ 지금은 **우편번호 접두 하나만** 벗긴다 — 그 형태는 시도를 품을 수 없어 안전하다.
#:   괄호 라벨·국가명은 **건드리지 않는다**(정본이 `startswith` 인 이유를 존중한다).
#:   그래서 `(주)오케이 서울…` 은 여전히 해석되지 않는다 — **그것은 이 PR 이 좁힌 범위이고
#:   base 대비 회귀다.** 아래 `xfail` 로 초록 안에 드러낸다(숨기지 않는다).
_ADDR_POSTAL_PREFIX = re.compile(r"^\s*(?:\(\s*우\s*\)\s*)?\d{5,6}\s+(?=\S)")


def _strip_address_prefix_noise(address: str) -> str:
    """우편번호 접두만 제거한다(그 이상은 벗기지 않는다)."""
    a = (address or "").strip()
    return _ADDR_POSTAL_PREFIX.sub("", a, count=1).strip()


def _sido_of(address: str) -> str:
    """주소 → 시도 **축약키**(해석 실패 시 빈 문자열). 정본 해석기에 위임한다.

    ★왜 위임인가(2026-09-08 · 실측):
      종전 구현은 축약키(`"전남"`)를 주소에 **부분문자열**로 찾았는데, 정식 행정구역명
      `"전라남도"` 에는 그 축약형이 **연속으로 없다**(한글은 음절 단위 — `전라남도` 안에
      `전남` 이라는 연속열이 없다). 정식 시도 **17개 전수 실측: 5개 실패** —
      충청북도 · 충청남도 · 전라남도 · 경상북도 · 경상남도.
      (전북·강원·제주는 **특별자치도 개칭** 덕에 우연히 축약형을 포함해 통과했다.)

    ★그리고 그 실패는 조용하지 않았다 — `""` 를 받은 `reb_client.rate_series_from_rows` 가
      **fail-open** 으로 전국 시계열을 돌려주고, 그것이 「R-ONE 지가변동률 **실데이터**」로
      라벨링됐다. 라이브 확증: `경상남도`→1.047 과 `zzz없는지역`→1.047 이 **같은 값**이었다
      (반면 축약형 `경남` 은 판정 거부로 `None`). ⇒ **정식 명칭이 「존재하지 않는 지역」과
      바이트 동일하게 처리됐다.**

    ★**새로 만들지 않고 정본을 쓴다**(§29 — 없는 것을 만드는 것과 있는 것을 안 쓴 것은
      처방이 다르다). `tax/regional_tax_data.sido_short_or_empty` 는 같은 입력 전수에서
      **0/17 실패**이고, 그 모듈은 이미 단련돼 있다:
        · 후보 순회를 **정렬 튜플**로 고정 — `frozenset` 순회가 `PYTHONHASHSEED` 마다
          **다른 답**을 내던 CRITICAL 을 봉합한 자리다
        · `"광주시"`(광주광역시 ↔ 경기도 광주시) 같은 **모호 접두는 판정하지 않는다**
      그 독스트링이 이미 *"해석기는 **한 자리**에 둔다"* 고 선언했는데 이 모듈이 미이관이었다.
    """
    from app.services.tax.regional_tax_data import sido_short_or_empty

    short = sido_short_or_empty(address)
    if not short:
        # ★독립 리뷰 적발(MEDIUM-1 · 2026-09-08): 정본은 `addr.startswith(시도명)` 이라
        #   **주소 맨 앞**에서만 인정한다. 종전 구현은 부분문자열이라 **접두 잡음을 견뎠는데**
        #   위임으로 바꾸며 그 계열이 회귀했다(실측):
        #       "(우)13561 경기도 성남시"  경기 → ''    "대한민국 경기도 성남시"  경기 → ''
        #       "[본점] 서울특별시 강남구"  서울 → ''
        #   ★내 «전수 대조» 는 **정식 시도명을 0번 위치에만** 놓고 태워서 이 계열을
        #     **원리적으로 볼 수 없었다**(모집단이 결함의 축과 달랐다).
        #   ⇒ 부분문자열로 되돌리지 않는다(정본이 피한 모호성 함정으로 돌아간다).
        #     대신 **경계 있는 접두 잡음만** 벗기고 다시 정본에 묻는다.
        short = sido_short_or_empty(_strip_address_prefix_noise(address))
    # 정본은 17개 시도 전부를 축약키로 돌려준다. 이 모듈의 근사표에 없는 키는 «미해석» 으로 본다
    # (모름을 유효값으로 표현하지 않는다 — 그 표현이 fail-open 을 먹였다).
    # ★현재는 **도달 불가 방어**다(독립 리뷰 LOW-1): `_ANNUAL_RATE`(17) 와 정본의
    #   `KNOWN_SIDO_SHORT`(17) 가 **완전 동일**해 이 `else` 가지가 실행되지 않는다(차집합 양방향 0).
    #   그래서 이 줄을 지우는 변이는 **생존한다 — 구멍이 아니라 도달 불가다.**
    #   두 표가 갈리는 순간 살아나고, 그 괴리는 `test_every_official_sido_name_resolves` 의
    #   `assert got in _ANNUAL_RATE` 가 잡는다(정본에 시도가 추가되면 빨개진다).
    return short if short in _ANNUAL_RATE else ""


def _lookup_rate(address: str) -> tuple[float, str]:
    """주소 → (연 지가변동률, 사유). 해석 실패면 전국 평균이고 **그렇다고 말한다**.

    ★형제 결함이었다(§D-20 — 처방 범위 = 결함 범위): `_sido_of` 만 고치고 여기를 두면
      5개 시도가 여전히 `_DEFAULT_RATE` 로 떨어진다. 실측 과대폭(연 변동률 기준):
      충북·충남 **+38%** · 전남·경남 **+80%** · 경북 **+100%**.
    """
    sido = _sido_of(address)
    if sido:
        rate = _ANNUAL_RATE[sido]
        return rate, f"{sido} 연 지가변동률 {rate*100:.1f}% 적용"
    # ★해석하지 못했다는 사실을 사유에 남긴다 — 「전국 평균」과 「지역을 못 읽었다」는 다른 말이다.
    return _DEFAULT_RATE, (
        f"주소에서 시·도를 해석하지 못해 전국 평균 지가변동률 {_DEFAULT_RATE*100:.1f}% 적용"
    )


async def time_adjust_factor_async(address: str = "", base_year: int = 2025) -> dict[str, Any]:
    """R-ONE 지가변동률 실데이터로 시점수정(가용 시), 실패 시 근사 테이블 폴백."""
    try:
        from app.services.external_api.reb_client import (
            cumulative_factor_from_rows,
            fetch_land_price_changes,
            rate_series_scope,
            reb_ready,
        )
        if reb_ready():
            rows = await fetch_land_price_changes(months=24)
            if rows:
                sido = _sido_of(address)
                f = cumulative_factor_from_rows(rows, sido)
                # sane-range(24개월 누적 ±30% 이내)만 채택, 벗어나면 근사 폴백
                if f and 0.7 < f < 1.3:
                    # ★★독립 리뷰 적발(HIGH-2 · 2026-09-08): 계획서가 «전국 폴백이면 「실데이터」로
                    #   단정하지 않는다» 고 선언해 놓고 **코드가 따라가지 않았다**. 수정 전후 모두
                    #   경남이 «R-ONE 지가변동률 실데이터» 라벨로 1.04x 를 받아 채택 단가에 곱해졌다
                    #   — 혼합이 전국으로 좁아졌을 뿐 «확신 있는 답» 은 그대로였다(§F-24).
                    #   ⇒ `rate_series_scope` 를 **실제로 읽어** 어느 범위에서 나왔는지 말한다.
                    scope = rate_series_scope(rows, sido)
                    if sido and scope == sido:
                        label = f"R-ONE 지가변동률 실데이터({sido}) 최근 24개월 누적 시점수정 {f}"
                        source = "R-ONE"
                    else:
                        # 요청 지역이 아니라 더 넓은 범위에서 나왔다 — 그 사실을 말한다.
                        label = (
                            f"R-ONE 지가변동률 {scope} 범위 누적 시점수정 {f}"
                            f"(요청 지역{f' {sido}' if sido else ''}의 시계열이 없어 {scope} 값을 적용 — "
                            f"해당 지역 실데이터가 아닙니다)"
                        )
                        # ★★`source` 는 **"R-ONE" 그대로** 둔다(독립 리뷰 R2 MEDIUM-3).
                        #   프론트가 `source === "R-ONE"` **정확일치**로 렌더 여부를 정하므로
                        #   (`DeskAppraisalReportClient.tsx:571-573`), 동적 문자열로 바꾸면
                        #   **그 줄이 화면에서 통째로 사라진다** — 「고쳤는데 안 보이는」 형태다.
                        #   ⇒ 정직성은 **표시 문구와 분리된 `scope`** 가 나른다(기계 판독 축).
                        source = "R-ONE"
                    return {"factor": f, "annual_rate": None, "elapsed_years": None,
                            "rationale": label, "source": source, "scope": scope}
    except Exception:  # noqa: BLE001
        pass
    out = time_adjust_factor(address, base_year)
    out["source"] = "근사테이블"
    return out


def time_adjust_factor(address: str = "", base_year: int = 2025, now: datetime | None = None) -> dict[str, Any]:
    """공시기준일(base_year-01-01)→가격시점 지가변동률 누적 시점수정계수."""
    rate, rationale = _lookup_rate(address)
    cur = now or datetime.now()
    base = date(base_year, 1, 1)
    elapsed_yrs = max(0.0, (cur.date() - base).days / 365.25)
    factor = (1 + rate) ** elapsed_yrs
    return {
        "factor": round(factor, 4),
        "annual_rate": rate,
        "elapsed_years": round(elapsed_yrs, 2),
        "rationale": f"{rationale} × 경과 {elapsed_yrs:.2f}년 → 시점수정 {factor:.4f}",
    }


async def monthly_rate_series_async(
    address: str = "", months: int = 24,
) -> tuple[list[tuple[str, float]], str]:
    """월별 지가변동률 시계열 `[(YYYYMM, 변동률%), …]` + **출처 라벨**.

    ## 왜 이 함수가 필요한가 (2026-09-07 실측)

    `land_dong_stats.land_market_stats(rate_series=…)` 는 **거래별 시점수정을 이미
    구현**해 두었는데, 그 인자를 넘기는 **소비처가 0건**이었다(`git grep rate_series`
    → 정의 파일 밖 0). 그래서 라이브 응답이 항상 `"time_adjusted": false` 였다.

    ★그리고 **비대칭**이 있었다 — 공시지가기준법(방법1)은 R-ONE 이 없으면
    `time_adjust_factor` 의 **근사테이블로 폴백**해 시점수정을 하는데, 시장통계(방법2)는
    폴백이 없어 **통째로 꺼졌다.** 두 방법을 나란히 놓고 비교하면서 한쪽만 시점을
    맞춘 셈이다.

    ★★근사 폴백은 **월별 변동을 모른다** — 연율을 12로 나눠 균등 배분한다. 그건
    «각 달이 실제로 얼마나 움직였는가» 가 아니라 «평균적으로 이만큼» 이다. 그래서
    **출처 라벨을 함께 돌려주고**, 소비처가 그것을 표면까지 싣게 한다(무음 승격 금지).

    Returns:
        (시계열, 출처) — 시계열이 비면 소비처는 시점수정을 **하지 않는다**(지어내지 않음).
    """
    from datetime import UTC, datetime

    try:
        from app.services.external_api.reb_client import (
            fetch_land_price_changes,
            rate_series_from_rows,
            reb_ready,
        )
        if reb_ready():
            rows = await fetch_land_price_changes(months=months)
            if rows:
                series = rate_series_from_rows(rows, _sido_of(address))
                if series:
                    return series, "R-ONE 지가변동률(실데이터)"
    except Exception:  # noqa: BLE001 — 외부 실패는 근사 폴백(무중단)
        pass

    # ── 근사 폴백 — 연율을 균등 배분한다. ★«월별 실제 변동»이 아님을 라벨이 말한다.
    annual, _why = _lookup_rate(address)
    if not annual:
        return [], "지가변동률 미확보 — 시점수정 미적용"
    monthly_pct = (annual / 12.0) * 100.0
    now = datetime.now(UTC)
    y, mo = now.year, now.month
    out: list[tuple[str, float]] = []
    for _ in range(months):
        out.append((f"{y:04d}{mo:02d}", monthly_pct))
        mo -= 1
        if mo == 0:
            mo = 12
            y -= 1
    out.reverse()
    return out, f"근사테이블(연 {annual * 100:.1f}% 균등배분 — 월별 실제 변동 아님)"
