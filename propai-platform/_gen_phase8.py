import os

BASE = "/home/kangjh3kang/My_Projects/Development_AI/propai-platform/apps/api"
SQ = chr(39)

def w(path, content):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] Created: {path}")

count = 0

# ==== File 1: db_utils.py ====
content = '''\"\"\"PostGIS + TimescaleDB 유틸리티.\"\"\"
import math
from typing import Optional


class PostGISHelper:
    \"\"\"PostGIS 공간 쿼리 래퍼 (인메모리 폴백).\"\"\"

    @staticmethod
    def st_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        \"\"\"두 좌표 간 거리(km) — Haversine.\"\"\"
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
'''
print("test:", content[:50])
