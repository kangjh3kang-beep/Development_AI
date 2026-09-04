"""`operations/status` 정직 계약 — 없는 것을 지어내지 않는다.

★왜 (2026-08-16 프로덕션 대조 실험):
  종전 구현은 `project_id` 를 에코만 하고 **DB 조회 0** 인 채 상수를 돌려줬다. 성격이 전혀
  다른 두 프로젝트가 **바이트 단위로 같은 값**을 냈다:

      458d7c86…(역삼동 736 · 강남 상업지)        → 입주율 92.5 · 센서 45/48
      49b59c62…(산 1-1 외 1필지 · 147,074㎡ 임야) → 입주율 92.5 · 센서 45/48

  개발되지 않은 임야에 "입주율 92.5%"와 "IoT 센서 45개 온라인"이 붙었다.

★그리고 그 화면은 **뜨지 않았다** — 프론트가 `kpis` 를 배열로 가정해
  `TypeError: kpis.map is not a function` 으로 죽었다(프로덕션 콘솔 실측).
  **고장이 거짓말을 가리고 있었다** — 크래시만 고치면 그때부터 거짓 지표가 보인다.
  그래서 이 테스트는 **둘을 함께** 잠근다.
"""

import re
from pathlib import Path

_ROUTER = Path(__file__).resolve().parents[1] / "routers" / "projects.py"


def _source_without_comments() -> str:
    """주석·독스트링을 걷어낸 소스.

    ★소스 검사는 주석에 뚫린다(이 저장소에서 배선 락 38개가 그렇게 관통됐다).
      이 파일의 독스트링에도 `92.5` 가 등장하므로 **반드시** 벗기고 봐야 한다 —
      안 벗기면 이 테스트가 자기 근거 주석 때문에 위반을 신고하는 위양성이 된다.
    """
    src = _ROUTER.read_text(encoding="utf-8")
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    src = re.sub(r"(?m)#.*$", "", src)
    return src


def _handler_body() -> str:
    """`get_operations_status` 핸들러 본문만 잘라낸다(다른 핸들러 오염 방지)."""
    src = _source_without_comments()
    m = re.search(
        r"async def get_operations_status\((?:.|\n)*?(?=\n@router\.|\nasync def |\ndef |\Z)", src
    )
    assert m, "핸들러를 찾지 못했다 — 이름이 바뀌었으면 이 테스트를 함께 고쳐라"
    return m.group(0)


def test_대상_핸들러가_실재한다():
    """★공허진리 가드 — 핸들러가 사라져서 아래 단언들이 참이 되는 것을 막는다."""
    body = _handler_body()
    assert len(body) > 50, "핸들러 본문이 비었다 — 아래 '위반 0'이 공허해진다"


def test_지어낸_운영지표_상수를_돌려주지_않는다():
    """종전에 모든 프로젝트에 동일하게 나가던 그 값들이 소스에 남아 있으면 안 된다."""
    body = _handler_body()
    for fabricated in ("92.5", "iot_sensors_online", "iot_sensors_total", "tenant_satisfaction"):
        assert fabricated not in body, (
            f"지어낸 운영지표 `{fabricated}` 가 남아 있다 — 수집원이 없으면 값을 만들지 않는다"
        )


def test_수집원_부재를_정직하게_알린다():
    body = _handler_body()
    assert '"available"' in body, "수집원 유무를 소비처가 알 수 없다"
    assert '"reason"' in body, "왜 없는지 말하지 않으면 사용자는 고장으로 읽는다"


def test_프론트_계약대로_배열_3종을_준다():
    """★크래시의 구조적 원인 — 프론트는 배열을 가정하는데 백엔드가 dict/부재를 줬다.

    형태를 계약에 맞춰야 `.map` 크래시가 **구조적으로** 불가능해진다.
    """
    body = _handler_body()
    for key in ("kpis", "maintenance", "sensors"):
        assert re.search(rf'"{key}"\s*:\s*\[', body), (
            f"`{key}` 가 배열이 아니다 — 프론트가 `.map` 을 부르므로 TypeError 로 화면이 죽는다"
        )
