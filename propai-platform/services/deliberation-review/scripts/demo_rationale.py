"""설명가능성 산출 샘플 — 실 청운동 유사 입력으로 rationale 동반 확인(키 불필요, 결정론)."""
import json
from datetime import date

from app.services.land.remaining_capacity import remaining_capacity
from app.services.land.upzoning import multipath_scenarios, upzoning_signals

PNU = "1111010100100010000"  # 서울 종로(11)
AS_OF = date(2026, 6, 1)

rc = remaining_capacity("제1종일반주거지역", 15622.0, 50551.0, pnu=PNU, as_of=AS_OF)
print("=== 잔여 개발용량 rationale ===")
print(json.dumps(rc["rationale"], ensure_ascii=False, indent=2))

sig = upzoning_signals(["제1종일반주거지역", "역세권", "최고고도지구"])
mp = multipath_scenarios("제1종일반주거지역", 15622.0, sig, pnu=PNU, as_of=AS_OF)
seo = next(p for p in mp["pathways"] if p["pathway"] == "역세권 활성화")
print("\n=== 종상향 역세권활성화 경로 rationale ===")
print(json.dumps(seo["rationale"], ensure_ascii=False, indent=2))
