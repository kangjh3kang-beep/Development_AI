"""PNU → 행정구역 코드 어댑터 (순수 함수).

PNU(필지고유번호, 19자리) 구조:
    시군구코드(5) + 법정동코드(5) + 대지구분(1: 0=대지/1=산/2=블록) + 본번(4) + 부번(4)

건축HUB 계열 API(sigunguCd/bjdongCd/bun/ji 파라미터)에 PNU를 그대로 넘길 수 없어
이 모듈에서 슬라이싱을 일원화한다. 슬라이싱 규약은
``app/services/external_api/building_registry_service.py``(get_building_by_pnu)와 동일.

원칙: 유효하지 않은 입력은 가짜 코드를 만들지 않고 정직하게 None을 반환한다.
"""

from typing import Any

__all__ = ["pnu_to_bcode", "pnu_to_full_parcel"]

# PNU 슬라이싱 경계 (building_registry_service.py 규약과 동일)
_SIGUNGU_LEN = 5      # 시군구코드: pnu[:5]
_BCODE_LEN = 10       # 시군구(5) + 법정동(5)
_PNU_FULL_LEN = 19    # 시군구(5)+법정동(5)+대지구분(1)+본번(4)+부번(4)


def pnu_to_bcode(pnu: str | None) -> tuple[str, str] | None:
    """PNU에서 (시군구코드 5자리, 법정동코드 5자리)를 추출한다.

    건축HUB 주택·건축인허가 API의 sigunguCd/bjdongCd 파라미터용.

    Args:
        pnu: 필지고유번호 (최소 앞 10자리가 숫자여야 함)

    Returns:
        (sigungu_cd, bjdong_cd) 튜플. 유효하지 않으면 None (가짜 코드 생성 금지).
    """
    if not pnu or not isinstance(pnu, str):
        return None
    pnu = pnu.strip()
    if len(pnu) < _BCODE_LEN or not pnu[:_BCODE_LEN].isdigit():
        return None
    return pnu[:_SIGUNGU_LEN], pnu[_SIGUNGU_LEN:_BCODE_LEN]


def pnu_to_full_parcel(pnu: str | None) -> dict[str, Any] | None:
    """PNU(19자리)에서 시군구·법정동·산여부·본번·부번을 모두 추출한다.

    슬라이싱 규약은 building_registry_service.get_building_by_pnu와 동일:
    sigungu=pnu[:5], bjdong=pnu[5:10], 대지구분=pnu[10], bun=pnu[11:15], ji=pnu[15:19].

    Args:
        pnu: 필지고유번호 19자리 (전부 숫자)

    Returns:
        {sigungu_cd, bjdong_cd, plat_gb_cd, is_san, bun, ji} dict.
        19자리 숫자가 아니면 None (가짜 코드 생성 금지).
    """
    if not pnu or not isinstance(pnu, str):
        return None
    pnu = pnu.strip()
    if len(pnu) < _PNU_FULL_LEN or not pnu[:_PNU_FULL_LEN].isdigit():
        return None
    plat_gb_cd = pnu[_BCODE_LEN]  # 0=대지, 1=산, 2=블록
    return {
        "sigungu_cd": pnu[:_SIGUNGU_LEN],
        "bjdong_cd": pnu[_SIGUNGU_LEN:_BCODE_LEN],
        "plat_gb_cd": plat_gb_cd,
        "is_san": plat_gb_cd == "1",
        "bun": pnu[11:15],
        "ji": pnu[15:19],
    }
