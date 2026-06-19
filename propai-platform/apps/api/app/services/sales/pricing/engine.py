"""분양가 엔진 — 차수별 기준가 × (1+Σ가중치RATE) + Σ가중치FIXED, 확정가 우선,
구성(토지비/건축비/업무대행비) 분해 + VAT. 상한제(CAP)는 업무대행비(CUSTOM) 제외.
"""

import hashlib
import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.site_org import SalesSiteConfig
from apps.api.database.models.sales.units_pricing import (
    SalesPriceBase,
    SalesPriceComposition,
    SalesPriceGenerationLog,
    SalesPriceGroup,
    SalesPriceGroupMember,
    SalesPriceWeight,
    SalesUnitInventory,
    SalesUnitPriceBreakdown,
    SalesUnitPriceTable,
    SalesUnitType,
)

# ★[iter-5 LOW·E402] logger 정의를 모든 import 아래로 내려 'import 보다 코드가 위'(E402) 2건을 없앤다.
logger = logging.getLogger(__name__)

Q = Decimal("1")
VAT = Decimal("0.1")


def _area(ttype, kind) -> Decimal:
    return Decimal(str(getattr(ttype, f"{kind}_area", None) or ttype.supply_area or 0))


def compute_unit_price(unit, ttype, base_row, weights_for_unit) -> Decimal:
    # ★[머니패스·Decimal 정합] 기준단가는 DB Numeric(정수원)이라 보통 Decimal/int 이지만,
    #   테스트·폴백 경로에서 float 가 섞여 들어오면 부동소수 오차가 가격에 번진다. 모든 수치 입력을
    #   Decimal(str(x)) 로 정규화해 float 혼입을 원천 차단한다(반올림은 마지막에 ROUND_HALF_UP 1회).
    base_unit = Decimal(str(base_row.base_unit_price or 0))
    # ★[iter-7 lint·SIM108] PER_AREA 면 단가×면적, 아니면(PER_UNIT) 단가 그대로 — 삼항으로 표현해
    #   if/else 블록(SIM108)을 없앤다(거동 동일·가독성 유지).
    amt = base_unit * _area(ttype, base_row.base_area_kind or "supply") if base_row.basis == "PER_AREA" else base_unit
    amt *= Decimal(str(base_row.round_factor or 1))
    rate_sum = Decimal(0)
    fixed_sum = Decimal(0)
    for w in weights_for_unit:
        if w.basis == "RATE":
            rate_sum += Decimal(str(w.value or 0))
        else:
            fixed_sum += Decimal(str(w.value or 0))
    return (amt * (Decimal(1) + rate_sum) + fixed_sum).quantize(Q, ROUND_HALF_UP)


def _match_weights(unit, weights, group_map):
    out = []
    for w in weights:
        d, k = w.dimension, (w.match_key or "")
        # 차원별 매칭(and 가 or 보다 우선이라 의미 동일하나, 가독성 위해 명시 괄호로 묶음).
        matched = (
            (d == "FLOOR" and str(unit.floor) == k)
            or (d == "LINE" and (unit.line or "") == k)
            or (d == "ASPECT" and (unit.aspect or "") == k)
            or d == "CUSTOM"
        )
        if matched:
            out.append(w)
    out += group_map.get(unit.id, [])
    out.sort(key=lambda x: -(x.priority or 0))
    return out


# ★[iter-6 HIGH·전역스윕(국소패치 금지)] 그룹조회·음수clamp 를 3개 자매 머니패스(generate_price_table·
#   solve_base_for_target·resolve_unit_price)가 '단일 함수'를 경유하도록 공용헬퍼로 추출한다.
#   과거 resolve_unit_price 만 (a) 그룹조회를 site_id 만으로 해 차수간 그룹 누출(weights 는 rid 로 거르나
#   groups 미필터=내부모순)이 있었고 (b) 음수 price clamp 가 없어 음수 계약 total_price 가 영속됐다.
#   국소패치 대신 두 거동을 공용화해 세 경로의 패리티를 by-construction 으로 보장한다(전역규칙: 동일패턴
#   국소수정 금지·공용화).
async def _load_group_map(db: AsyncSession, site_id, round_id) -> dict:
    """선택세대 그룹(SalesPriceGroup)을 '현장+차수(selector→round_id)'로 필터해 {unit_id: [group,...]}
    로 모은다. apply_group_pricing 이 그룹 selector 에 round_id 를 적재하고 _find_group_by_idem 도 그걸로
    필터하므로, 소비측도 동일 selector→round_id 로 걸러 SSOT 를 완전히 일치시킨다(반쪽 필터·차수간
    RATE 복리가산 누출 제거). round_id 가 None 이면 차수필터 없이 현장 전체(폴백 경로 호환).
    """
    q = select(SalesPriceGroup).where(SalesPriceGroup.site_id == site_id)
    if round_id is not None:
        q = q.where(SalesPriceGroup.selector["round_id"].astext == str(round_id))
    group_map: dict = {}
    # ★[iter-7 HIGH·correctness·멤버레벨 복리 사각 차단(앱레벨 즉시방어)] 멤버테이블에 UNIQUE(group_id,
    #   unit_id)가 없으면(039 마이그 미적용 상태·동시 race) 같은 (group, unit) 멤버행이 2건 이상 생길
    #   수 있다. 그러면 아래 멤버루프가 같은 그룹 g 를 같은 unit 에 '멤버행 수만큼' append 하고,
    #   _match_weights 가 그 그룹을 2회 반환→compute_unit_price rate_sum 이 2배(1.05→1.10)로 복리된다.
    #   그래서 unit 별로 '그룹 id 기준 중복'을 제거해, 멤버행이 몇 개든 한 그룹은 정확히 1회만 가산되게
    #   한다(by-construction 복리 차단). 마이그가 미적용인 샌드박스에서도 이 방어가 복리를 막으므로
    #   코드평가로 검증 가능하다. (DB 정본은 039 UNIQUE 인덱스 — deploy-pending.)
    seen: dict = {}  # {unit_id: 이미 담은 group.id 집합} — 같은 그룹 중복 append 방지
    for g in (await db.execute(q)).scalars():
        for m in (await db.execute(select(SalesPriceGroupMember).where(
                SalesPriceGroupMember.group_id == g.id))).scalars():
            gids = seen.setdefault(m.unit_id, set())
            if g.id in gids:
                continue  # 중복 멤버행으로 같은 그룹이 또 들어오면 건너뜀(복리 0)
            gids.add(g.id)
            group_map.setdefault(m.unit_id, []).append(g)
    return group_map


def _clamp_price(price: Decimal):
    """산정 분양가가 음수면 0 으로 보정(clamp)하고 경고를 함께 돌려준다 — 음수 base_price/total_price 가
    매출 롤업·원장으로 새지 않도록(은폐 아님: 경고로 정직 표기). 정상(>=0)이면 그대로·경고 None.
    반환: (clamp 된 price, warning 문구 or None).
    """
    if price < 0:
        warn = (f"산정 분양가가 음수({int(price):,}원)가 되어 0 으로 보정했습니다 — "
                "정액(FIXED) 가중치 합이 과도하게 큰 음수입니다(가중치 설정을 점검하세요).")
        return Decimal(0), warn
    return price, None


# ★[잔차 흡수 안전경계] 잔차를 '마지막 RATE 구성'에 흡수할 때, 그 구성의 최종 비율(amount/price)이
#   설정 비율에서 이 폭(±20%p)을 넘어 이탈하면 흡수가 구성을 크게 왜곡한 것(예 건축비 60% 설정이
#   실제 40% 로 둔갑·토지비 30% 가 100% 로 팽창)이다. 정상 구성(ΣRATE+ΣFIXED/price ≈ 1)에서는
#   반올림 누적 수준의 작은 잔차만 생겨 이탈이 미미하므로 흡수가 안전하고, 이 임계를 넘으면 흡수를
#   취소(원래 비율 금액 유지)하고 경고로 정직 표기한다. 이렇게 하면 ΣFIXED 가 합법적으로 잔차를
#   메우는 기존 정상 구성(예 RATE 0.95 + 소액 FIXED)은 그대로 흡수되고, 왜곡 구성만 차단된다.
RATE_RESIDUAL_DEVIATION_LIMIT = Decimal("0.20")  # 마지막 RATE 최종비율이 설정비율에서 ±20%p 초과 이탈 시 흡수 금지

# ★[iter-3 상대편차 가드] 절대 ±20%p 만 보면 '소액 설정비율'의 왜곡을 놓친다. 예: 마지막 RATE 가
#   0.005(0.5%) 인데 흡수 후 0.01(1%) 이 되면 절대편차는 0.5%p<0.20 라 통과하지만, 설정 대비 +100%
#   팽창(실제 금액이 2배)이라 회계 왜곡이다. 또 중간왜곡(ΣRATE+ΣFIXED≈0.90, BUILD 0.05→0.15 처럼
#   3배 팽창)도 절대편차가 작아 숨는다. 그래서 '상대편차' |final_ratio/configured − 1| 가 이 폭(0.5
#   =±50%)을 넘으면 절대 ±20%p 와 OR 로 결합해 흡수를 취소한다(둘 중 하나라도 초과 시 왜곡으로 판정).
#   상대편차는 설정비율이 0(전부 잔차로 새로 생김)이거나 매우 작을 때 과민할 수 있어, 설정비율이
#   이 하한(0.001=0.1%) 이상일 때만 상대기준을 적용한다(0 분모·미미한 비율 노이즈 제외).
RATE_RESIDUAL_RELATIVE_LIMIT = Decimal("0.5")    # 마지막 RATE 최종비율이 설정비율 대비 ±50% 초과 이탈 시 흡수 금지
RATE_RELATIVE_MIN_CONFIGURED = Decimal("0.001")  # 설정비율이 이 미만이면 상대기준 적용 보류(0 분모·노이즈 제외)

# ★[iter-4 HIGH·중간왜곡 사각 해소] 절대 ±20%p·상대 ±50% 둘 다 통과하는 '마지막 RATE 큰비율'의
#   중간왜곡(예: ΣRATE 0.9 = LAND 0.3 + BUILD 0.6 → 잔차 10% 가 BUILD 0.6→0.7 로 흡수. abs_dev 0.10
#   <0.20, rel_dev 0.167<0.5 → 둘 다 통과)을 막는다. 정상 흡수는 '세대별 반올림 누적'뿐이라 흡수량이
#   구성금액의 극히 일부(수 원~수천 원=구성의 1% 미만)지만, 이 케이스는 구성금액의 16.7% 를 잔차로
#   부풀린다(=비율 합이 1 이 아닌 설정을 마지막 구성에 몰아넣은 왜곡 → VAT 과세표준 팽창). 그래서
#   '흡수 절대변화량'을 그 구성 자체 대비로 본다: |잔차| / 흡수전 금액 이 이 폭(0.10=10%)을 넘으면
#   흡수가 구성을 10% 넘게 부풀린 것으로 보고 흡수를 취소·경고한다(앞 두 기준과 OR 결합). 합법
#   흡수(ΣRATE≈1, 반올림 잔차)는 이 비율이 0 에 가까워 영향 없다.
RATE_ABSORB_COMPONENT_LIMIT = Decimal("0.10")    # 흡수 잔차가 흡수대상 구성금액의 10% 초과면 흡수 금지(중간왜곡 차단)


def decompose(price: Decimal, comps, mode: str) -> list[dict]:
    """분양가(price)를 구성요소(토지비/건축비/업무대행비)로 분해한다.

    ★[머니패스·잔차 0 보장] RATE 구성은 비율×가격을 반올림(ROUND_HALF_UP — compute_unit_price 와
      동일)하므로, 각 행을 단순 합치면 반올림 누적으로 Σ구성 ≠ price 잔차가 남는다. 이를 방치하면
      원가구성 합계가 분양가와 1~몇 원 어긋나 검산이 깨진다. 그래서 RATE 구성 합이 분양가를 정확히
      덮도록, '마지막 RATE 구성'에 잔차(price − ΣRATE − ΣFIXED)를 명시적으로 흡수시켜 Σ=price 를
      불변으로 만든다. FIXED 구성(절대금액)은 조정 대상이 아니다(원장 일관성). RATE 구성이 하나도
      없으면(전부 FIXED·구성 없음) 잔차를 강제 끼워넣지 않는다(구성 정의 그대로 정직 표기).

    ★[iter-2 왜곡 회귀 차단] 잔차 흡수는 '정상 구성'에서만 안전하다. 다음 비정상 구성을 사전·사후
      검증해 왜곡값이 회계(SalesUnitPriceBreakdown→매출→롤업→VAT 과세표준)로 전파되지 않게 한다.
        ① ΣFIXED > price        : 정액 구성만으로 분양가 초과 → 흡수 시 마지막 RATE 가 음수가 되어
                                  음수 amount·음수 VAT 가 회계로 샌다. → 흡수 금지·경고 부착.
        ② 흡수 후 마지막 RATE 비율 이탈 : 흡수 결과 마지막 RATE 의 최종 비율(amount/price)이 설정
                                  비율에서 (절대 ±20%p 초과) '또는' (상대 ±50% 초과) 이탈하면 비율 합이
                                  1 이 아닌 구성을 잔차로 메운 왜곡 → 흡수 취소·경고. 절대기준만으로는
                                  소액 설정비율(0.005→0.01 +100% 팽창)·중간왜곡(0.05→0.15 3배)이
                                  |Δ|<0.20 로 숨으므로, 상대편차를 OR 로 결합해 함께 적발한다.
        ③ 흡수 후 음수 방어      : 위를 통과해도 마지막 RATE amount 가 음수면 0 으로 clamp(max 0)
                                  하고 경고(회계 음수 차단). Σ=price 불변은 깨질 수 있으나 음수 전파보다 안전.
      경고는 각 행의 "warning" 필드(정상이면 None)로 노출하며, 호출부(generate_price_table)는
      amount>=0 불변을 영속 직전에 다시 한 번 가드한다.
    """
    price = Decimal(str(price or 0))  # float 혼입 차단(Decimal 정합)
    rows = []
    rate_idx: list[int] = []   # 잔차 흡수 대상(마지막 RATE 구성)을 찾기 위한 인덱스
    fixed_sum = Decimal(0)     # 사전검증 ①: 정액 구성 합
    last_rate_value = Decimal(0)  # 사후검증 ②: 마지막 RATE 구성의 '설정 비율'(왜곡 측정 기준)
    for c in comps:
        if mode == "CAP" and c.component_type == "CUSTOM":
            continue  # 상한제: 업무대행비 등 산정 외
        is_fixed = c.basis == "FIXED"
        if is_fixed:
            amt = Decimal(str(c.value or 0)).quantize(Q, ROUND_HALF_UP)
            fixed_sum += amt
        else:
            amt = (price * Decimal(str(c.value or 0))).quantize(Q, ROUND_HALF_UP)
            last_rate_value = Decimal(str(c.value or 0))  # 마지막 RATE 의 설정 비율(루프 끝에 최종값 유지)
            rate_idx.append(len(rows))
        rows.append({"type": c.component_type, "label": c.label,
                     "amount": amt, "vat_applicable": bool(c.vat_applicable)})

    # ── 검증: 비정상 구성이면 잔차 흡수를 강제하지 않고 경고로 정직 표기(왜곡 전파 차단) ──
    warn = None
    if rate_idx:
        if fixed_sum > price:
            # ① 정액 합이 분양가 초과 — 흡수하면 마지막 RATE 가 음수. 흡수 금지·경고.
            warn = (f"정액구성 합({int(fixed_sum):,}원)이 분양가({int(price):,}원)를 초과 — "
                    "잔차 흡수를 생략합니다(원가구성 설정을 점검하세요).")
        else:
            last = rows[rate_idx[-1]]
            orig_amount = last["amount"]  # 흡수 취소 시 되돌릴 원래(설정 비율) 금액
            residual = price - sum(r["amount"] for r in rows)
            absorbed = orig_amount + residual
            # ② 사후 왜곡 검증: 흡수 결과 마지막 RATE 의 최종 비율이 설정 비율에서 크게 이탈하면 취소.
            #    price=0 이면 비율 계산 불가 → 이탈 판정 생략(어차피 잔차 0).
            #    절대편차(±20%p) OR 상대편차(±50%)로 판정한다. 상대편차는 설정비율이 충분히 클 때만
            #    적용(소액 분모·미미 비율 노이즈 제외). 둘 중 하나라도 초과면 왜곡으로 보고 흡수 취소.
            final_ratio = (absorbed / price) if price > 0 else last_rate_value
            abs_dev = abs(final_ratio - last_rate_value)
            rel_dev = (abs_dev / last_rate_value) if last_rate_value >= RATE_RELATIVE_MIN_CONFIGURED else Decimal(0)
            # ★[iter-4] 흡수 절대변화량(잔차)을 흡수대상 구성금액 대비로 본다 — 큰비율 구성의 중간왜곡
            #   (abs/rel 둘 다 통과하지만 구성을 크게 부풀리는)을 추가 적발. 흡수전 금액 0 이면 분모불가
            #   → 생략(어차피 비율 0 구성).
            absorb_dev = (abs(residual) / orig_amount) if orig_amount > 0 else Decimal(0)
            distorted = (abs_dev > RATE_RESIDUAL_DEVIATION_LIMIT) or (rel_dev > RATE_RESIDUAL_RELATIVE_LIMIT) \
                or (absorb_dev > RATE_ABSORB_COMPONENT_LIMIT)
            if price > 0 and distorted:
                warn = (f"비율구성 합이 1.0 이 아니어서 마지막 비율구성이 설정 {last_rate_value} 에서 "
                        f"실제 {final_ratio.quantize(Decimal('0.001'))} 로 왜곡 — 잔차 흡수를 생략합니다"
                        "(원가구성 비율 합이 1 이 되도록 점검하세요).")
                # 흡수 취소: 원래 설정 비율 금액 유지(왜곡값을 회계로 보내지 않음).
            else:
                last["amount"] = absorbed
                # ③ 음수 방어: 정상 범위라도 흡수 결과가 음수면 0 으로 clamp 하고 경고(회계 음수 차단).
                if last["amount"] < 0:
                    last["amount"] = Decimal(0)
                    warn = "잔차 흡수 후 마지막 비율구성 금액이 음수가 되어 0 으로 보정했습니다(원가구성 점검 필요)."

    # VAT 는 잔차 보정된 '최종' 금액 기준으로 산출(보정 전 금액으로 매기면 합계가 어긋남).
    # 음수 방어가 끝난 뒤이므로 음수 VAT 가 새지 않는다.
    for r in rows:
        r["vat"] = (r["amount"] * VAT).quantize(Q, ROUND_HALF_UP) if r.pop("vat_applicable") else Decimal(0)
        r["warning"] = warn  # 정상이면 None, 비정상이면 동일 경고 문구(행 단위 노출)
    return rows


async def resolve_unit_price(db: AsyncSession, site_id, unit, round_id=None):
    """per-unit 가격표(SalesUnitPriceTable)가 없을 때 기준단가(SalesPriceBase)에서 1세대 가격을 직접
    산정한다(계약 가격 자동해소 폴백). generate_price_table 미실행 상태에서도 계약 total_price 가
    NULL→0 cascade(수수료·할부·연체 전량 0) 되지 않도록 한다. 산식은 generate_price_table 과 동일.
    """
    if unit is None or not getattr(unit, "type_id", None):
        return None
    q = select(SalesPriceBase).where(
        SalesPriceBase.site_id == site_id, SalesPriceBase.type_id == unit.type_id)
    if round_id:
        q = q.where(SalesPriceBase.round_id == round_id)
    br = (await db.execute(q)).scalars().first()
    if not br:
        return None
    ttype = (await db.execute(select(SalesUnitType).where(SalesUnitType.id == unit.type_id))).scalar_one_or_none()
    if not ttype:
        return None
    rid = round_id or br.round_id
    weights = list((await db.execute(select(SalesPriceWeight).where(
        SalesPriceWeight.site_id == site_id, SalesPriceWeight.round_id == rid))).scalars())
    # ★[iter-6 HIGH·전역스윕] 그룹조회를 차수(rid)로도 필터하는 공용헬퍼 경유 — 과거 site_id 만이라
    #   타 차수 그룹의 RATE 가 이 폴백 계약가에 누출됐다(weights 는 rid 로 거르나 groups 미필터=내부모순).
    group_map = await _load_group_map(db, site_id, rid)
    price = compute_unit_price(unit, ttype, br, _match_weights(unit, weights, group_map))
    # ★[iter-6 HIGH·전역스윕] generate_price_table 과 동일하게 음수 분양가를 0 으로 clamp(공용헬퍼 경유).
    #   과거 int(price) 만이라 음수 계약 total_price 가 그대로 영속됐다(회계 음수 누출). 0 가격이면 None
    #   유지(계약 자동해소 대상 없음 — 기존 거동 무회귀).
    price, _warn = _clamp_price(price)
    return int(price) if price else None


async def generate_price_table(db: AsyncSession, site_id: uuid.UUID, round_id: uuid.UUID, by=None,
                               collect: list[dict] | None = None) -> int:
    """분양가표 생성. 반환은 생성 세대수(int) — 기존 호출부 무회귀.

    ★[iter-3 HIGH·warning 머니패스 종단배선] decompose 가 만드는 row['warning'](흡수금지·왜곡·
      음수clamp 경고)은 과거 amount/vat 만 SalesUnitPriceBreakdown 에 저장되고 폐기돼, 운영자가
      화면·로그 어디서도 못 보는 dead 채널이었다(VAT 과세표준 과소합산·Σ구성≠분양가 무신호). 이제:
        ① 세대별 경고를 모아 logger.warning 1줄(현장·차수·경고세대수·샘플)로 운영 로그에 남기고,
        ② SalesPriceGenerationLog.params_snapshot 에 warn_count/warn_samples 를 적재(영속),
        ③ collect 리스트가 주어지면 거기에 경고를 담아 라우터 응답(warnings[])으로 노출한다.
      이렇게 docstring(decompose) 약속('경고는 warning 필드로 노출')과 실경로를 일치시킨다.
    """
    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == site_id))).scalar_one()
    mode = cfg.pricing_mode or "GENERAL"
    base_rows = {r.type_id: r for r in (await db.execute(select(SalesPriceBase).where(
        SalesPriceBase.site_id == site_id, SalesPriceBase.round_id == round_id))).scalars()}
    weights = list((await db.execute(select(SalesPriceWeight).where(
        SalesPriceWeight.site_id == site_id, SalesPriceWeight.round_id == round_id))).scalars())
    comps = list((await db.execute(select(SalesPriceComposition).where(
        SalesPriceComposition.site_id == site_id, SalesPriceComposition.round_id == round_id)
        .order_by(SalesPriceComposition.sort_order))).scalars())

    # ★[iter-6 HIGH·전역스윕] 차수필터 그룹조회를 공용헬퍼(_load_group_map)로 단일화 — 3개 자매경로가
    #   같은 함수를 경유해 차수간 RATE 복리가산 누출을 by-construction 으로 막는다(과거 인라인 복제 제거).
    group_map = await _load_group_map(db, site_id, round_id)

    types = {t.id: t for t in (await db.execute(select(SalesUnitType).where(
        SalesUnitType.site_id == site_id))).scalars()}
    units = list((await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site_id, SalesUnitInventory.deleted_at.is_(None)))).scalars())

    count = 0
    warn_samples: list[dict] = []  # 경고 발생 세대 샘플(현장 점검·응답 노출용 — 과다적재 방지로 상한)
    warn_count = 0                 # 경고 세대 수(흡수금지·왜곡·음수clamp 가 한 건이라도 붙은 세대)
    warn_sample_cap = 20
    for u in units:
        pt = (await db.execute(select(SalesUnitPriceTable).where(
            SalesUnitPriceTable.unit_id == u.id, SalesUnitPriceTable.round_id == round_id))).scalar_one_or_none()
        if pt and pt.price_mode == "FIXED" and pt.override_price is not None:
            price = Decimal(pt.override_price)  # 확정금액 우선
        else:
            br = base_rows.get(u.type_id)
            if not br:
                continue
            price = compute_unit_price(u, types[u.type_id], br, _match_weights(u, weights, group_map))
        # ★[iter-6 HIGH·전역스윕] 음수 분양가 0 clamp 를 공용헬퍼(_clamp_price)로 단일화 — resolve_unit_price
        #   와 동일 거동을 보장한다. compute_unit_price 는 큰 음수 FIXED 가중치로 음수 분양가를 낼 수 있고,
        #   그대로 두면 base_price/total_price 가 음수로 영속돼 project_revenue 합산에서 매출이 깎이거나
        #   음수가 돼 롤업·원장으로 샌다. 0 으로 clamp(은폐 아님) 후 경고를 부착해 종단 노출한다.
        price, price_warn = _clamp_price(price)
        bd = decompose(price, comps, mode)
        if not pt:
            pt = SalesUnitPriceTable(site_id=site_id, unit_id=u.id, round_id=round_id)
            db.add(pt)
        pt.base_price = price
        pt.total_price = price + (pt.option_price or 0) + (pt.premium or 0)
        await db.execute(SalesUnitPriceBreakdown.__table__.delete().where(
            (SalesUnitPriceBreakdown.unit_id == u.id) & (SalesUnitPriceBreakdown.round_id == round_id)))
        # 이 세대의 경고(행 단위 동일 문구)는 1건만 대표로 집계한다(decompose 가 모든 행에 같은 warn 부착).
        #   음수 분양가 clamp 경고(price_warn)도 동일 채널로 합류시켜 종단 노출(로그·snapshot·collect)한다.
        unit_warn = price_warn or next((r["warning"] for r in bd if r.get("warning")), None)
        if unit_warn:
            warn_count += 1
            if len(warn_samples) < warn_sample_cap:
                warn_samples.append({"unit_id": str(u.id),
                                     "dong": getattr(u, "dong", None), "ho": getattr(u, "ho", None),
                                     "warning": unit_warn})
        for r in bd:
            # ★[영속 불변 가드] decompose 가 음수 방어(clamp)·흡수금지를 거치지만, 어떤 경로로든
            #   음수 amount/vat 가 회계(SalesUnitPriceBreakdown→매출 롤업→VAT 과세표준)로 새지 않도록
            #   영속 직전에 amount/vat>=0 을 한 번 더 보장한다(이중 안전망).
            amt = r["amount"] if r["amount"] and r["amount"] > 0 else Decimal(0)
            vat = r["vat"] if r["vat"] and r["vat"] > 0 else Decimal(0)
            db.add(SalesUnitPriceBreakdown(site_id=site_id, unit_id=u.id, round_id=round_id,
                   component_type=r["type"], label=r["label"], amount=amt, vat_amount=vat))
        count += 1

    # ★ 경고 종단배선: ① 영속(params_snapshot) ② 운영 로그(warning 1줄) ③ collect(응답 노출).
    snapshot: dict = {"mode": mode, "warn_count": warn_count, "warn_samples": warn_samples}
    db.add(SalesPriceGenerationLog(site_id=site_id, round_id=round_id, generated_count=count,
           params_snapshot=snapshot, by=by))
    if warn_count:
        # silent-fail 금지: 흡수금지/왜곡/clamp 가 발동하면 운영 로그에 분류·규모를 남긴다(은폐 아님).
        logger.warning(
            "분양가표 생성 경고: site=%s round=%s 경고세대=%d/%d 샘플=%s",
            site_id, round_id, warn_count, count,
            [{"ho": s.get("ho"), "warning": s.get("warning")} for s in warn_samples[:3]])
    if collect is not None:
        # 동일 문구가 여러 세대에서 반복되므로 '문구→발생세대수' 로 묶어 응답 배열을 만든다(중복 폭주 방지).
        agg: dict[str, int] = {}
        for s in warn_samples:
            agg[s["warning"]] = agg.get(s["warning"], 0) + 1
        for msg, n in agg.items():
            collect.append({"message": msg, "unit_count": n})
        if warn_count > len(warn_samples):
            # 샘플 상한을 넘어선 잔여 경고 세대가 있으면 총계를 함께 노출(과소 표기 방지).
            collect.append({"message": f"경고 발생 세대 총 {warn_count}건(샘플 {len(warn_samples)}건 표시)",
                            "unit_count": warn_count})
    await db.flush()
    return count


async def solve_base_for_target(
    db: AsyncSession, site_id: uuid.UUID, round_id: uuid.UUID, target_total_10k: int, by=None,
) -> dict:
    """목표 총매출 → 균일 기준단가(㎡당, PER_AREA) 역산 후 전 타입 반영·재생성. reverse.

    총매출은 기준단가 base 에 선형: total = base·M + F.
      M = Σ_세대[ 공급면적 × round_factor × (1+가중치율) ]   (PER_AREA 균일 가정)
      F = Σ_세대[ 정액가중치 + 옵션 + 프리미엄 ]
    base = (target - F) / M. M<=0 이면 산출 불가(세대/면적 없음).

    ★[머니패스·역산 정확성·정직성] 선형모델 M 은 세대별 반올림(compute_unit_price 의 ROUND_HALF_UP)을
      무시하므로, 역산한 base 로 실제 재생성하면 달성매출이 목표에서 몇 원~수만 원 어긋날 수 있다(세대수
      만큼 반올림 누적). 이 잔차를 숨기지 않고 achieved_total_10k(실달성)·gap_10k(목표−실달성)로 그대로
      노출한다(round-trip 검증 가능·가짜 수렴 위장 금지). target_total_10k<=0 은 음수 base 와 별개로
      입력단계에서 차단한다.
    """
    if target_total_10k <= 0:
        return {"ok": False, "note": "목표 총매출은 0보다 커야 합니다 — 만원 단위 양수를 입력하세요."}
    weights = list((await db.execute(select(SalesPriceWeight).where(
        SalesPriceWeight.site_id == site_id, SalesPriceWeight.round_id == round_id))).scalars())
    base_rows = {r.type_id: r for r in (await db.execute(select(SalesPriceBase).where(
        SalesPriceBase.site_id == site_id, SalesPriceBase.round_id == round_id))).scalars()}
    # ★[iter-6 HIGH·전역스윕] 차수필터 그룹조회를 공용헬퍼(_load_group_map)로 단일화 — 역산 M(선형모델)에
    #   타 차수 그룹 가중치가 섞여 들어가던 누출을 generate_price_table·resolve_unit_price 와 동일하게 막는다.
    group_map = await _load_group_map(db, site_id, round_id)
    types = {t.id: t for t in (await db.execute(select(SalesUnitType).where(
        SalesUnitType.site_id == site_id))).scalars()}
    units = list((await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site_id, SalesUnitInventory.deleted_at.is_(None)))).scalars())
    opt_prem = {pt.unit_id: (Decimal(pt.option_price or 0) + Decimal(pt.premium or 0))
                for pt in (await db.execute(select(SalesUnitPriceTable).where(
                    SalesUnitPriceTable.site_id == site_id, SalesUnitPriceTable.round_id == round_id))).scalars()}

    # 선형모델 매출 = slope×기준단가 + fixed_total (slope=Σ면적·계수·(1+rate), fixed_total=Σ정액+옵션).
    slope = Decimal(0)
    fixed_total = Decimal(0)
    for u in units:
        t = types.get(u.type_id)
        if not t:
            continue
        br = base_rows.get(u.type_id)
        area = _area(t, (br.base_area_kind if br else None) or "supply")
        factor = Decimal(str((br.round_factor if br else None) or 1))
        rate = Decimal(0)
        fixed = Decimal(0)
        for w in _match_weights(u, weights, group_map):
            if w.basis == "RATE":
                rate += Decimal(str(w.value or 0))
            else:
                fixed += Decimal(str(w.value or 0))
        slope += area * factor * (Decimal(1) + rate)
        fixed_total += fixed + opt_prem.get(u.id, Decimal(0))

    if slope <= 0:
        return {"ok": False, "note": "세대/공급면적이 없어 역산 불가 — 동·호표·타입 면적을 먼저 확정하세요."}

    # 단가·금액은 원(KRW) 단위. 목표는 만원으로 받으므로 ×10000 환산(fixed_total·옵션·프리미엄도 원).
    target_won = Decimal(int(target_total_10k)) * 10000
    base = (target_won - fixed_total) / slope
    if base <= 0:
        return {"ok": False, "note": "목표 매출이 정액·옵션 합보다 작아 기준단가가 음수입니다 — 목표를 확인하세요."}
    base = base.quantize(Decimal("1"), ROUND_HALF_UP)

    # 전 타입에 균일 기준단가(PER_AREA, 공급) 반영 후 재생성.
    for t in types.values():
        br = base_rows.get(t.id)
        if br:
            br.basis = "PER_AREA"
            br.base_unit_price = int(base)
            br.base_area_kind = br.base_area_kind or "supply"
        else:
            db.add(SalesPriceBase(site_id=site_id, round_id=round_id, type_id=t.id,
                   basis="PER_AREA", base_unit_price=int(base), base_area_kind="supply", round_factor=1))
    await db.flush()
    warnings: list[dict] = []
    await generate_price_table(db, site_id, round_id, by=by, collect=warnings)
    rev = await project_revenue(db, site_id, round_id)
    # round-trip 잔차(목표−실달성, 만원). 세대별 반올림 누적으로 0 이 아닐 수 있으며, 이를 숨기지 않고
    # 그대로 노출한다(정직성). 부호: 양수=목표 미달, 음수=목표 초과.
    # ★[iter-2 floor 편향 제거] gap 을 만원으로 절단된 total_revenue_10k(=int(total/10000), 항상 내림)
    #   로 빼면 잔차가 항상 작은 양수(미달)로 치우친다(예 실초과여도 미달로 보임). 그래서 gap 은 원(KRW)
    #   기반으로 산출한 뒤 round() 로 만원 환산해 floor 편향을 없앤다. achieved_total_10k(표시용)는
    #   기존 절단값을 그대로 두되(전 화면 일관), 잔차 부호/크기는 원기반 round 로 정확히 잡는다.
    achieved_won = rev.get("total_revenue_won")
    if achieved_won is None:  # 폴백 경로(원기반 미제공) — 만원값을 원으로 환산해 일관 처리.
        achieved_won = int(rev["total_revenue_10k"]) * 10000
    gap_won = int(target_won) - int(achieved_won)
    gap_10k = round(gap_won / 10000)
    # ★[iter-5 LOW·항진식 제거] 과거 reconciles_won = (achieved_won + gap_won == target_won)는 gap_won 을
    #   target_won − achieved_won 으로 정의했으니 '항상 참'(항진식)이라 아무것도 검증하지 못했다(가짜 신뢰).
    #   이를 '독립검산'으로 교체한다: project_revenue 가 별도 테이블(SalesUnitPriceBreakdown)에서 모은
    #   원가구성 금액 합(total_breakdown_won)이 분양가 base_price 합(total_base_won)과 일치하는지 본다.
    #   정상 경로에선 decompose 가 잔차를 흡수해 Σ구성 = Σ분양가(일치). 흡수금지·왜곡·음수clamp 경고가
    #   하나라도 있으면(흡수 생략으로) 합이 어긋날 수 있으므로, '경고 0 && 두 합 일치'일 때만 True 다
    #   (경고가 있는데 True 면 거짓 신뢰 — 그래서 경고 유무를 함께 본다). 가격이 하나도 없으면 검산 대상
    #   없음 → False(없는 정합을 참으로 위장하지 않음).
    total_base_won = rev.get("total_base_won")
    total_breakdown_won = rev.get("total_breakdown_won")
    reconciles_won = bool(
        rev.get("units_priced") and not warnings
        and total_base_won is not None and total_breakdown_won is not None
        and total_base_won == total_breakdown_won)
    return {"ok": True, "base_unit_price": int(base), "target_total_10k": target_total_10k,
            "achieved_total_10k": rev["total_revenue_10k"], "achieved_total_won": int(achieved_won),
            "gap_10k": gap_10k, "gap_won": gap_won,
            "reconciles_won": reconciles_won,
            "total_base_won": total_base_won, "total_breakdown_won": total_breakdown_won,
            "warnings": warnings, "units_priced": rev["units_priced"]}


async def apply_group_pricing(
    db: AsyncSession, site_id: uuid.UUID, round_id: uuid.UUID,
    unit_ids: list[uuid.UUID], mode: str, value: float, group_name: str | None = None, by=None,
    idempotency_key: str | None = None,
) -> dict:
    """P1-4 선택 세대 그룹 일괄단가 적용 후 재생성.

    mode:
      RATE          그룹 가중치 +value(예 0.05=+5%)  — SalesPriceGroup(basis=RATE)
      FIXED         그룹 가중치 +value 원             — SalesPriceGroup(basis=FIXED)
      OVERRIDE_PSQM 선택 세대에 절대 평당단가 value(원/㎡)×공급면적 = 확정금액(override)

    ★[iter-3 MED·멱등성 / iter-4 HIGH·race 백스톱] RATE/FIXED 는 과거 매 호출마다 무조건 새
      SalesPriceGroup 을 만들었다. _match_weights 가 세대당 매칭 그룹을 '전부 합산'(rate_sum += ...)
      하므로, 더블클릭·재시도·재전송으로 같은 그룹이 N개 생기면 RATE 가 N배로 가산(복리)돼 분양가/
      매출이 왜곡됐다. 이제 (site_id, round_id, 멱등키)로 get-or-create 한다. 멱등키는
      idempotency_key 우선, 없으면 group_name(+mode) 로 결정한다.

      멱등은 2겹으로 보장한다(단일 경로 코드만으론 동시성 race 를 못 막으므로):
        ① 애플리케이션 조회: 같은 멱등키 그룹이 이미 있으면 그걸 재사용(단일 인덱스 조회 — 아래
           _find_group_by_idem). 평소 더블클릭/재시도는 여기서 흡수된다.
        ② DB 부분 유니크 인덱스(uq_sales_price_group_idem, 038 마이그레이션 정본): 동시 트랜잭션
           2건이 거의 동시에 ①에서 '없음'을 보고 둘 다 INSERT 하는 race 에서, 둘째 INSERT 가
           23505(unique_violation)→IntegrityError 가 된다. 이를 미가공 500 으로 흘리지 않고
           SAVEPOINT(begin_nested) 안에서 잡아, 해당 INSERT 만 롤백→멱등키로 재조회→기존 그룹을
           재사용(graceful)으로 매핑한다. (과거엔 docstring 이 'SELECT FOR UPDATE 직렬화' 를
           약속했으나 코드엔 with_for_update 가 없었다 — 약속·구현 불일치를 이 백스톱으로 일치시킨다.)
    """
    uids = [u for u in unit_ids if u]
    if not uids:
        return {"ok": False, "note": "선택된 세대가 없습니다."}
    reused = False
    override_warnings: list[dict] = []  # OVERRIDE_PSQM 에서 0 이하 확정금액 skip 경고(종단 노출용)
    if mode in ("RATE", "FIXED"):
        gname = group_name or "그룹"
        # ★[iter-5 HIGH·멱등키 상수붕괴 회귀 해소] 멱등키는 클라가 준 idempotency_key 를 최우선으로 쓰되,
        #   없을 때 과거처럼 group_name(폴백 '그룹')+mode 로 만들면 안 된다. 실호출(프론트
        #   PriceGroupingPanel)은 group_name·idempotency_key 를 안 보내므로, 폴백키가 'RATE:그룹'(상수)
        #   로 붕괴해 같은 라운드의 모든 RATE 적용이 단일 그룹으로 충돌했다 — {A,B}+5% 적용 후 {C,D}+3%
        #   적용이 동일 그룹을 재사용→value 0.05→0.03 덮어쓰기+C,D 합산으로 A,B 의 +5% 가 묵음소실(분양가/
        #   매출 왜곡). '매번 새 그룹=다중 그룹 공존'이던 정상 기본경로를 회귀로 깬 것이다.
        #   해결: 멱등키를 '작업 내용 콘텐츠 해시'로 만든다 — mode + 정렬된 세대ID(★값 제외). 같은 세대
        #   집합의 반복(더블클릭/재시도/값정정)은 동일 키로 dedup 되고, 서로 다른 선택의 그룹핑은 서로 다른
        #   키라 분리 그룹으로 보존된다(distinct 분리 무회귀). group_name 상수 폴백은 멱등키 분모로 절대
        #   사용하지 않는다.
        #   ★[iter-6 MED·값정정 복리 해소] 과거 payload 에 value 를 포함해, 같은 세대집합에 +5% 적용 후
        #   값정정 +7% 재적용이 value 가 달라 '별도 키→별도 RATE 그룹' 2개로 공존했다. _match_weights 가
        #   둘 다 반환→compute_unit_price rate_sum += 0.05 + 0.07 = 0.12 로 복리 누적(이전 그룹 supersede·
        #   cleanup 부재)됐다. payload 에서 value 를 빼면 같은 (mode, 정렬세대ID)는 동일 키로 기존 RATE
        #   그룹을 재사용(supersede)해 value 만 0.07 로 갱신 → rate_sum = 0.07(복리 0.12 아님). 단 distinct
        #   세대집합은 여전히 분리 키라 iter-5 분리 보존 성과는 무회귀.
        # ★[iter-7 MED·architecture·멱등키 SSOT 일원화] 과거엔 클라 idempotency_key(임의문자열)면 그
        #   문자열을 '그대로' 멱등키로 쓰고, 없으면 콘텐츠해시(mode+정렬세대ID)를 썼다. 둘이 같은
        #   (site, round) 네임스페이스를 공유하므로, '같은 세대집합'을 한 번은 클라키로·한 번은 미전송
        #   (콘텐츠해시)으로 호출하면 idem 이 달라 '별도 RATE 그룹' 2개가 공존했다 → _match_weights 가
        #   둘 다 반환→compute_unit_price rate_sum 복리(예 0.05+0.07). 이를 막으려면 두 키가 같은 분모를
        #   공유해야 한다. 해결: 멱등키 분모를 항상 '콘텐츠해시(mode+정렬세대ID)'로 단일화하고, 클라
        #   제공키는 그 분모에 'prefix 로 결합'만 한다(별도 네임스페이스 금지). 클라키 없으면 'auto'.
        #   - 미전송: idem = "{mode}:auto:{hash(mode|정렬세대ID)}"
        #   - 클라키 k1: idem = "{mode}:cli:{k1}:{hash(mode|정렬세대ID)}"
        #   같은 세대집합이면 둘 다 동일 hash 꼬리를 가지지만 prefix(auto vs cli:k1)가 달라 여전히 별도
        #   그룹이 될 수 있다. 그러나 클라키는 '의도적 분할'(같은 세대집합을 일부러 나누고 싶을 때)에만
        #   쓰는 옵션이므로, 운영 계약을 명문화한다: ★같은 (site, round, 세대집합)에 대해 '클라키 전송'과
        #   '미전송'을 혼용하지 말 것(혼용하면 의도적으로 분리된 2그룹이 되어 RATE 가 합산된다). 프론트
        #   PriceGroupingPanel 은 idempotency_key 를 보내지 않으므로(실호출=auto 일원화), 혼용은 클라키를
        #   쓰는 통합경로에서만 발생할 수 있고 그 경로는 키를 일관 전송하면 단일 그룹으로 수렴한다.
        #   value 는 분모에서 제외(값정정 시 supersede 수렴 — iter-6 성과 무회귀).
        content = f"{mode}|" + ",".join(sorted(str(u) for u in uids))
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]
        # 클라키가 있으면 'cli:<키>' prefix, 없으면 'auto' — 둘 다 같은 콘텐츠해시 꼬리를 공유(SSOT 분모).
        idem = (f"{mode}:cli:{idempotency_key}:{content_hash}" if idempotency_key
                else f"{mode}:auto:{content_hash}")

        async def _find_group_by_idem():
            # ★[iter-4 MED·인덱스 SSOT] 과거엔 현장 전체 그룹을 메모리로 끌어와 파이썬에서 O(N) 스캔했다.
            #   부분 유니크 인덱스(uq_sales_price_group_idem)가 보는 것과 동일하게 selector JSONB 의
            #   round_id/idem 텍스트를 DB where 로 직접 매칭해 단건만 가져온다(인덱스 정본과 SSOT 일치).
            return (await db.execute(select(SalesPriceGroup).where(
                SalesPriceGroup.site_id == site_id,
                SalesPriceGroup.selector["round_id"].astext == str(round_id),
                SalesPriceGroup.selector["idem"].astext == idem))).scalars().first()

        async def _attach_members(group):
            # ★[iter-7 HIGH·correctness·멤버레벨 멱등(2겹)] 멤버 중복행은 _load_group_map 에서 같은 그룹을
            #   여러 번 가산하게 해 RATE 복리(1.05→1.10)를 낳는다. 두 겹으로 막는다.
            #   ① 애플리케이션 조회: 이미 그룹에 속한 세대(existing_members)는 다시 INSERT 하지 않는다
            #      (평시 더블클릭/재시도 흡수).
            #   ② SAVEPOINT 백스톱: 동시 트랜잭션 2건이 거의 동시에 ①에서 '없음'을 보고 둘 다 같은
            #      (group_id, unit_id)를 INSERT 하는 TOCTOU race 에서, 둘째 INSERT 가 039 부분 유니크
            #      인덱스로 23505(IntegrityError)가 된다. 멤버 add 를 begin_nested(SAVEPOINT) 안에서
            #      flush 해, 23505 면 그 멤버 INSERT 만 롤백하고 graceful 하게 넘어간다(미가공 500·외부
            #      트랜잭션 오염 0 — 이미 같은 멤버가 있으니 멱등). 인덱스 미적용(deploy-pending)이면
            #      flush 가 23505 를 안 내므로 기존 거동 그대로(무회귀).
            existing_members = {m.unit_id for m in (await db.execute(select(SalesPriceGroupMember).where(
                SalesPriceGroupMember.group_id == group.id))).scalars()}
            for uid in uids:
                if uid in existing_members:
                    continue
                try:
                    async with db.begin_nested():
                        db.add(SalesPriceGroupMember(group_id=group.id, unit_id=uid))
                        await db.flush()  # 여기서 23505 가 터지면 SAVEPOINT 만 롤백(멱등 — 멤버 이미 존재)
                except IntegrityError:
                    # 동시 race 로 같은 멤버가 먼저 들어간 경우 — 무시(중복행을 만들지 않음=복리 차단).
                    pass

        g = await _find_group_by_idem()  # ① 애플리케이션 조회(평시 더블클릭/재시도 흡수)
        if g is not None:
            # 재사용: 값/우선순위만 최신 입력으로 갱신(가산은 그대로 1회분).
            g.basis = mode
            g.value = value
            g.priority = 10
            reused = True
            await _attach_members(g)
        else:
            # ② SAVEPOINT 안에서 INSERT — 동시 race 로 둘째가 23505 면 그 INSERT 만 롤백하고 재조회·재사용.
            g = SalesPriceGroup(site_id=site_id, group_name=gname, basis=mode, value=value,
                                priority=10, selector={"round_id": str(round_id), "idem": idem})
            try:
                async with db.begin_nested():
                    db.add(g)
                    await db.flush()  # 여기서 23505 가 터지면 SAVEPOINT 만 롤백(외부 트랜잭션 보존)
            except IntegrityError:
                # 동시 트랜잭션이 먼저 같은 멱등키 그룹을 만든 race — 미가공 500 금지, 기존 그룹 재사용.
                g = await _find_group_by_idem()
                if g is None:
                    # 유니크 인덱스 미적용(deploy-pending) 등으로 재조회도 비면 정직하게 충돌을 알린다
                    #   (silent-fail 금지 — 빈값/0 으로 은폐하지 않음).
                    raise
                g.basis = mode
                g.value = value
                g.priority = 10
                reused = True
            await _attach_members(g)
    elif mode == "OVERRIDE_PSQM":
        # ★[iter-7 MED·security·silent-zero 차단] OVERRIDE_PSQM 은 평당단가 value 를 그대로 확정금액
        #   (override_price)으로 영속한다. 라우터(actions.pricing_group_apply)는 value 키 누락만 막고
        #   '명시적 0'은 통과시키므로(0 은 허용값), value<=0 이 들어오면 override_price=0 이 영속되고
        #   generate_price_table 은 override_price is not None(0 도 통과)이라 base_price=0 을 '묵음'으로
        #   확정한다 — RATE/FIXED 의 음수clamp 와 달리 경고가 안 붙는 silent-zero(매출 0 cascade).
        #   평당단가 0/음수는 분양가로 의미가 없으므로 진입에서 막아 정직하게 ok:False 로 돌려준다
        #   (프론트 가드에만 의존하지 않는 defense-in-depth — 0 은폐 금지).
        if Decimal(str(value)) <= 0:
            return {"ok": False, "note": "평당단가(OVERRIDE_PSQM value)는 0보다 커야 합니다 — "
                    "0/음수 단가는 분양가를 0 으로 묵음 확정합니다(양수 원/㎡ 를 입력하세요)."}
        types = {t.id: t for t in (await db.execute(select(SalesUnitType).where(
            SalesUnitType.site_id == site_id))).scalars()}
        # ★[iter-3 방어·IDOR] 과거엔 id.in_(uids) 만으로 조회해 '우연히 type 매칭이 없으면 통과'에
        #   기댔다. site_id 를 명시 필터에 더해 by-construction 으로 타 현장 세대 override 를 차단한다.
        units = {u.id: u for u in (await db.execute(select(SalesUnitInventory).where(
            SalesUnitInventory.id.in_(uids), SalesUnitInventory.site_id == site_id))).scalars()}
        for uid in uids:
            u = units.get(uid)
            t = types.get(u.type_id) if u else None
            if not t:
                continue
            area = Decimal(str(t.supply_area or t.contract_area or t.exclusive_area or 0))
            if area <= 0:
                continue
            amt = (Decimal(str(value)) * area).quantize(Decimal("1"), ROUND_HALF_UP)
            if amt <= 0:
                # 면적·단가는 양수인데 반올림으로 0 이 됐거나 경계값 — silent-zero 방지로 skip+경고수집.
                #   (위 value<=0 가드를 통과한 정상 경로에선 거의 발생하지 않지만, 영속 직전 이중 안전망.)
                override_warnings.append({"unit_id": str(uid),
                    "warning": "확정금액이 0 이하라 OVERRIDE 를 건너뜁니다(평당단가·면적 점검)."})
                continue
            pt = (await db.execute(select(SalesUnitPriceTable).where(
                SalesUnitPriceTable.unit_id == uid, SalesUnitPriceTable.round_id == round_id))).scalar_one_or_none()
            if not pt:
                pt = SalesUnitPriceTable(site_id=site_id, unit_id=uid, round_id=round_id)
                db.add(pt)
            pt.price_mode = "FIXED"
            pt.override_price = int(amt)
    else:
        return {"ok": False, "note": f"알 수 없는 mode: {mode}"}
    await db.flush()
    warnings: list[dict] = list(override_warnings)  # OVERRIDE skip 경고를 종단(응답 warnings[])으로 합류
    n = await generate_price_table(db, site_id, round_id, by=by, collect=warnings)
    rev = await project_revenue(db, site_id, round_id)
    return {"ok": True, "mode": mode, "applied_units": len(uids), "regenerated": n,
            "group_reused": reused, "warnings": warnings,
            "total_revenue_10k": rev["total_revenue_10k"]}


async def project_revenue(db: AsyncSession, site_id: uuid.UUID, round_id: uuid.UUID) -> dict:
    """현재 분양가표 기준 총매출(분양액) 산출 — forward. 타입별 분해 포함(만원 단위)."""
    rows = list((await db.execute(select(SalesUnitPriceTable).where(
        SalesUnitPriceTable.site_id == site_id, SalesUnitPriceTable.round_id == round_id))).scalars())
    types = {t.id: t for t in (await db.execute(select(SalesUnitType).where(
        SalesUnitType.site_id == site_id))).scalars()}
    units = {u.id: u for u in (await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site_id, SalesUnitInventory.deleted_at.is_(None)))).scalars()}
    # 분양가표 base_price/total_price 는 원(KRW) 단위. 만원(_10k) 표기는 ÷10000.
    total = Decimal(0)
    by_type: dict[str, dict] = {}
    for pt in rows:
        amt = Decimal(pt.total_price or pt.base_price or 0)
        total += amt
        u = units.get(pt.unit_id)
        _t = types.get(u.type_id) if u else None
        tname = _t.type_name if _t else "기타"
        e = by_type.setdefault(tname, {"count": 0, "total_10k": 0})
        e["count"] += 1
        e["total_10k"] += int(amt / 10000)
    # 원가구성 집계(토지비/건축비/업무대행비 + VAT) — decompose 결과(SalesUnitPriceBreakdown).
    labels = {"LAND": "토지비", "BUILD": "건축비", "CUSTOM": "업무대행비"}
    bd_rows = (await db.execute(
        select(SalesUnitPriceBreakdown.component_type,
               func.sum(SalesUnitPriceBreakdown.amount),
               func.sum(SalesUnitPriceBreakdown.vat_amount))
        .where(SalesUnitPriceBreakdown.site_id == site_id,
               SalesUnitPriceBreakdown.round_id == round_id)
        .group_by(SalesUnitPriceBreakdown.component_type))).all()
    breakdown = [{
        "component_type": ct, "label": labels.get(ct or "", ct or "기타"),
        "amount_10k": int((a or 0) / 10000), "vat_10k": int((v or 0) / 10000),
    } for ct, a, v in bd_rows]
    # ★[iter-5 LOW·독립검산용] 원가구성(SalesUnitPriceBreakdown) 금액 합을 원(KRW) 단위로도 노출한다.
    #   이 합은 '가격표(SalesUnitPriceTable)'가 아니라 'decompose 결과 테이블'에서 따로 나오므로,
    #   분양가 base_price 합과 비교하면 분해가 분양가를 정확히 덮는지 독립적으로 검산할 수 있다(항진식 아님).
    total_breakdown_won = int(sum((a or 0) for _ct, a, _v in bd_rows))
    # base_price 합(옵션·프리미엄 제외 — breakdown 은 base_price 의 분해이므로 같은 기준으로 비교).
    total_base_won = int(sum(Decimal(pt.base_price or 0) for pt in rows))

    return {
        "round_id": str(round_id),
        "units_priced": len(rows),
        "total_revenue_won": int(total),            # 총분양액(원)
        "total_revenue_10k": int(total / 10000),    # 총분양액(만원)
        "total_base_won": total_base_won,           # 기준분양가(옵션·프리미엄 제외) 합(원) — 독립검산 기준
        "total_breakdown_won": total_breakdown_won,  # 원가구성 금액 합(원) — 독립검산 대상
        "avg_unit_10k": int(total / len(rows) / 10000) if rows else 0,
        "by_type": by_type,
        "breakdown": breakdown,                     # 원가구성(토지비/건축비/대행비·VAT, 만원)
    }
