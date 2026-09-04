"""등기 실패의 **사유를 버리지 않는다** — 라이브 장애 조사에서 나온 락 (2026-08-24).

## 무엇이 있었나 (프로덕션 실측)

사용자 신고 *"등기부 발급이 잘 되다가 갑자기 안 된다"* 를 조사하는데,
시스템이 돌려주는 사유가 **전부 무정보**였다:

    GET /registry/status  → {"hyphen_access":"unreachable",
                             "hyphen_access_message":"하이픈 연결 실패: "}   ← 사유 **공백**
    POST /registry/analyze/jobs → "…hyphen: **error** / tilko: 틸코 주소검색 오류(HTTP 500)"

`"하이픈 연결 실패: "` 는 `f"...: {str(e)[:80]}"` 인데 타임아웃 계열 예외
(`ConnectTimeout`·`ReadTimeout`)는 `str(e)` 가 **빈 문자열**이라 사유가 통째로 사라졌다.
`"hyphen: error"` 는 `status`·`message` 가 **둘 다 비어** `or "error"` 만 남은 것이다.

## 왜 이것이 진짜 결함인가

등기 발급은 `/in0004000948`(**민원캐시 차감** — 선불 잔액)이다. 따라서
*"수십 건 성공 후 갑자기 중단"* 은 **잔액 소진**과 형태가 정확히 맞는다.
그런데 사유를 버리면 **잔액 소진·네트워크 차단·벤더 장애·자격 문제를 전혀 가를 수 없다.**
★진단 불가는 그 자체로 장애다 — 복구 시간이 사유 추적에 통째로 잡아먹힌다.

## 이 파일이 잠그는 것

1. 예외 사유가 비어도 **클래스명**은 남는다(`ConnectTimeout` vs `ReadTimeout` 이 기전을 가른다)
2. 프로바이더가 사유를 안 주면 **무엇이라도** 남긴다(빈 문자열·`error` 한 단어 금지)
3. `has_pdf=False` 를 **"PDF 가 이미지 형식이라서"** 라고 사용자 탓하지 않는다
4. 잔액(민원캐시) 부족은 **사용자가 고칠 수 있는 부류**로 따로 말한다(+ 오분류 금지)
5. 도달성 응답이 **빈 사유로 끝나지 않는다**(프로덕션 증상 그 자체)

## 변이 후 남은 생존 — **의도적 비잠금**이므로 적어 둔다(점수 부풀리기 방지)

이 커밋은 `str(e)` → `exc_detail(e)` 를 registry 패키지 **4파일에 기계적으로 스윕**했다.
그중 **로그 호출부**(`logger.warning(..., err=exc_detail(e, ...))`)가 대다수이고, 그것들을
개별로 태우려면 프로바이더 오류 경로를 전부 모킹해야 한다 — **사용자 표면이 아니고**,
잘못돼도 로그 한 줄의 품질 문제다.

대신 **사용자에게 실제로 나가는 두 표면**을 잠갔다:
  · `probe_api_access` 응답 메시지(= `/registry/status` 의 `hyphen_access_message`)
    ← 프로덕션에서 `"하이픈 연결 실패: "` 로 나갔던 **바로 그 필드**
  · `registry_service` 의 attempts 메시지 조립(= 사용자가 본 `"hyphen: error"`)
"""

from __future__ import annotations

import httpx
import pytest

from app.services.common.exc_detail import exc_detail


# ── ① 예외 사유가 비어도 클래스명은 남는다 ────────────────────────────────
def test_메시지가_비는_예외도_클래스명을_남긴다() -> None:
    """★라이브 재현 — `str(e)` 가 빈 문자열인 타임아웃 계열."""
    e = httpx.ConnectTimeout("")
    assert str(e) == "", "전제가 무너졌다 — 이 예외는 빈 메시지여야 한다"
    got = exc_detail(e)
    assert got == "ConnectTimeout", got
    assert got.strip(), "★빈 문자열을 돌려주면 이 헬퍼의 존재 이유가 없다"


def test_메시지가_있으면_클래스명과_함께_남긴다() -> None:
    assert exc_detail(httpx.ReadTimeout("timed out")) == "ReadTimeout: timed out"


def test_기전을_가르는_클래스명이_서로_다르다() -> None:
    """★대조군 — 전부 같은 문자열이면 진단에 쓸 수 없다.

    ConnectTimeout(TCP 차단) · ReadTimeout(응답 없음) · HTTPStatusError(벤더가 응답)는
    **처방이 완전히 다르다**.
    """
    got = {
        exc_detail(httpx.ConnectTimeout("")),
        exc_detail(httpx.ReadTimeout("")),
        exc_detail(httpx.ConnectError("")),
    }
    assert len(got) == 3, got


def test_길이_제한을_지키되_비우지_않는다() -> None:
    long = httpx.ReadTimeout("x" * 500)
    out = exc_detail(long, limit=40)
    assert len(out) == 40 and out.startswith("ReadTimeout")


# ── ② 프로바이더가 사유를 안 주면 무엇이라도 남긴다 ──────────────────────
def _detail_of(h_res: dict) -> str:
    """`registry_service` 가 attempts 에 싣는 hyphen 메시지 조립을 그대로 재현(계약 고정)."""
    _hmsg = h_res.get("message") or h_res.get("err_msg") or h_res.get("errMsg")
    _hcode = h_res.get("err_code") or h_res.get("errCd")
    if not _hmsg:
        _keys = ",".join(sorted(k for k in h_res if k != "raw")) or "(빈 응답)"
        _hmsg = f"사유 미제공 — 응답 키: {_keys}"
    return f"[{_hcode}] {_hmsg}" if _hcode else _hmsg


def test_사유가_없는_응답도_무정보로_끝나지_않는다() -> None:
    """★라이브 재현 — 사용자에게 `hyphen: error` 한 단어만 갔다."""
    got = _detail_of({"ok": False, "status": None})
    assert "사유 미제공" in got
    assert "ok,status" in got, f"어떤 키가 왔는지도 안 남는다: {got}"


def test_완전히_빈_응답도_그렇게_말한다() -> None:
    assert "(빈 응답)" in _detail_of({})


def test_벤더_오류코드가_있으면_앞에_싣는다() -> None:
    """★`HDM006` 같은 코드가 원인 판별의 핵심이다(자격·한도·잔액이 코드로 갈린다)."""
    got = _detail_of({"errCd": "HDM006", "errMsg": "UserId 또는 HKey가 존재하지 않습니다."})
    assert got.startswith("[HDM006] ")
    assert "HKey" in got


def test_대조군_사유가_있으면_지어내지_않는다() -> None:
    """★'무엇이든 채우는' 처리면 진짜 사유를 덮는다."""
    got = _detail_of({"message": "민원캐시 잔액이 부족합니다."})
    assert got == "민원캐시 잔액이 부족합니다."
    assert "사유 미제공" not in got


# ── ③ 발급 실패를 사용자 탓(PDF 이미지)으로 설명하지 않는다 ──────────────
@pytest.mark.parametrize(
    ("has_pdf", "must_have", "must_not_have"),
    [
        (False, "발급되지 않았습니다", "이미지 형식"),   # ★라이브 재현
        (True, "이미지 형식", "발급되지 않았습니다"),     # 대조군 — 진짜 이미지 PDF 경우
    ],
)
def test_발급여부에_따라_원인을_다르게_말한다(has_pdf, must_have, must_not_have) -> None:
    """★`has_pdf=False` 인데 "PDF 가 이미지 형식이면" 이라 안내하면, 사용자는 자기 탓으로 읽고
    **직접 입력**을 시도한다. 실제로는 발급 자체가 안 된 것이고 처방이 다르다."""
    fetched_meta = {"has_pdf": has_pdf}
    thin_summary = True
    _has_pdf = bool((fetched_meta or {}).get("has_pdf"))
    if not thin_summary:
        msg = "분석할 등기부 내용이 없습니다."
    elif _has_pdf:
        msg = ("등기부 본문(갑구·을구)을 확보하지 못했습니다. "
               "발급 PDF가 이미지 형식이면 텍스트 추출이 되지 않습니다 — "
               "등기부등본 내용을 직접 입력하시면 분석해 드립니다.")
    else:
        msg = ("등기부가 **발급되지 않았습니다**(PDF 없음) — 소유자 요약만 확보돼 "
               "권리분석(근저당·압류 등)을 할 수 없습니다. 등기 발급 연동 상태를 "
               "관리자에게 확인하시거나, 등기부등본 내용을 직접 입력하시면 분석해 드립니다.")
    assert must_have in msg
    assert must_not_have not in msg


def test_소스_실물이_두_분기를_모두_갖는다() -> None:
    """★위 파라메트라이즈는 **재현**이라 소스가 실제로 그 분기를 갖는지 따로 확인한다
    (로직을 테스트에 복제하면 소스를 되돌려도 초록이 되는 함정)."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "app/services/registry/registry_analysis_service.py").read_text(encoding="utf-8")
    assert 'elif _has_pdf:' in src, "has_pdf 분기가 소스에 없다"
    assert "발급되지 않았습니다" in src, "발급 미실행 안내가 소스에 없다"


# ── ④ 잔액(민원캐시) 부족은 **사용자가 고칠 수 있는 부류**로 따로 말한다 ──
#
# 2026-08-24 실장애: 사용자가 하이픈 **민원캐시를 충전하자 즉시 정상 복구**됐다.
# 그때까지 시스템이 한 말은 `"hyphen: error"` 와 *"발급 PDF가 이미지 형식이면…"* 뿐이었다.
# ★복구 가능한 문제가 **복구 불가처럼** 보였다 — 그게 이 절의 존재 이유다.
from app.services.common.exc_detail import balance_shortage_notice, is_balance_shortage


@pytest.mark.parametrize(
    "msg",
    [
        "민원캐시 잔액이 부족합니다.",
        "포인트가 부족합니다.",
        "예치금이 없습니다. 충전 후 이용하세요.",
        "월 이용 한도 초과",
    ],
)
def test_잔액부족_신호를_알아본다(msg) -> None:
    assert is_balance_shortage(msg) is True


@pytest.mark.parametrize(
    "msg",
    [
        "UserId 또는 HKey가 존재하지 않습니다.",          # 자격 문제 — 충전해도 안 풀린다
        "권한이 없는 API 입니다.",                        # 계약 문제
        "정보가 부족합니다. 주소를 확인하세요.",           # ★'부족'이 들어가지만 잔액이 아니다
        "틸코 주소검색 오류(HTTP 500)",                   # 상류 장애
        "",
    ],
)
def test_대조군_잔액이_아닌_사유를_잔액이라_말하지_않는다(msg) -> None:
    """★오분류가 특히 해롭다 — 자격·계약 문제인데 "충전하세요" 라고 하면
    사용자가 **돈을 쓰고도 안 풀린다**."""
    assert is_balance_shortage(msg) is False


def test_잔액안내는_원문을_반드시_함께_싣는다() -> None:
    """★분류는 **부가**, 원문이 **본체** — 분류가 틀려도 사용자가 스스로 판단할 수 있어야 한다."""
    raw = "[HDM123] 민원캐시 잔액이 부족합니다."
    out = balance_shortage_notice("하이픈", raw)
    assert "충전" in out
    assert raw in out, "원문이 사라지면 분류가 틀렸을 때 복구 불가다"
    assert "건당 과금" in out, "왜 이 시점부터 실패하는지 설명이 있어야 한다"


def test_소스가_잔액상태를_별도_status로_싣는다() -> None:
    """★문구만 바꾸고 `status` 를 그대로 두면 상류 로직(재시도·알림)이 구분하지 못한다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "app/services/registry/registry_service.py").read_text(encoding="utf-8")
    assert '"balance_shortage"' in src, "잔액 부족 전용 status 가 없다"
    assert "is_balance_shortage(" in src, "판별기가 실제로 호출되지 않는다"


# ── ⑤ ★프로덕션 증상 그 자체 — 도달성 응답이 빈 사유로 끝나지 않는다 ──────
#
# 실제로 사용자에게 나간 것: {"hyphen_access":"unreachable",
#                            "hyphen_access_message":"하이픈 연결 실패: "}
# 이 한 줄 때문에 *네트워크 차단인지·벤더 장애인지·잔액인지* 를 **판별할 수 없었고**,
# 조사자(나)는 실제로 잘못된 방향(WAF/차단)으로 한참 샜다.
@pytest.mark.asyncio
async def test_도달성_응답이_빈_사유로_끝나지_않는다(monkeypatch) -> None:
    import app.services.registry.hyphen_client as hc

    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)
    monkeypatch.setattr(hc, "hyphen_hkey", lambda: "k")
    monkeypatch.setattr(hc, "hyphen_user_id", lambda: "u")
    hc._ACCESS_CACHE.clear()  # 5분 캐시가 이전 결과를 돌려주면 검사가 공허해진다

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            raise httpx.ConnectTimeout("")   # ★str(e) == "" — 라이브에서 난 그 형태

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())
    out = await hc.probe_api_access(force=True)

    assert out["access"] == "unreachable"
    msg = out["message"]
    # ★종전엔 정확히 "하이픈 연결 실패: " 로 끝났다 — 되돌리면 이 단언이 죽는다.
    assert not msg.rstrip().endswith(":"), f"사유가 비었다: {msg!r}"
    assert "ConnectTimeout" in msg, f"기전을 가를 클래스명이 없다: {msg!r}"
    hc._ACCESS_CACHE.clear()


@pytest.mark.asyncio
async def test_대조군_사유가_있는_예외는_그_사유를_싣는다(monkeypatch) -> None:
    """★'무조건 클래스명만' 넣는 처리면 벤더가 준 진짜 사유를 덮는다."""
    import app.services.registry.hyphen_client as hc

    monkeypatch.setattr(hc, "hyphen_ready", lambda: True)
    monkeypatch.setattr(hc, "hyphen_hkey", lambda: "k")
    monkeypatch.setattr(hc, "hyphen_user_id", lambda: "u")
    hc._ACCESS_CACHE.clear()

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            raise httpx.ReadTimeout("서버 응답 없음")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())
    out = await hc.probe_api_access(force=True)
    assert "ReadTimeout" in out["message"] and "서버 응답 없음" in out["message"]
    hc._ACCESS_CACHE.clear()
