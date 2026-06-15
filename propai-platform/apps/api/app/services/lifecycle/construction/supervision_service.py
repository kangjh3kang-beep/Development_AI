from typing import Dict
from datetime import datetime
import structlog

logger = structlog.get_logger()

class SupervisionService:
    """AI 감리 + EVM 공정 관리 (PMBOK 7th)"""

    def calculate_evm(self, bac_krw: float, pv_krw: float, ev_pct: float, ac_krw: float) -> dict:
        """EV=BAC*pct, SV=EV-PV, CV=EV-AC, CPI=EV/AC"""
        ev = bac_krw * ev_pct / 100
        sv = ev - pv_krw
        cv = ev - ac_krw
        cpi = ev / ac_krw if ac_krw > 0 else 1.0
        spi = ev / pv_krw if pv_krw > 0 else 1.0
        eac = bac_krw / cpi if cpi > 0 else bac_krw
        etc = eac - ac_krw
        schedule_status = "정상" if abs(spi - 1.0) < 0.05 else ("앞서감" if spi > 1.0 else "지연")
        cost_status = "정상" if abs(cpi - 1.0) < 0.05 else ("절감" if cpi > 1.0 else "초과")
        return {
            "bac_krw": int(bac_krw), "pv_krw": int(pv_krw), "ev_krw": int(ev), "ac_krw": int(ac_krw),
            "sv_krw": int(sv), "cv_krw": int(cv), "spi": round(spi, 4), "cpi": round(cpi, 4),
            "eac_krw": int(eac), "etc_krw": int(etc),
            "schedule_status": schedule_status, "cost_status": cost_status,
            "method": "EVM (PMBOK 7th Edition)"
        }

    def analyze_photo_for_progress(self, image_path: str) -> dict:
        try:
            import cv2
            import numpy as np
            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            progress = min(float(np.sum(edges > 0)) / (img.shape[0] * img.shape[1]) * 1000, 100)
            return {"estimated_progress_pct": round(progress, 1), "analysis_method": "OpenCV Edge Detection"}
        except Exception as e:
            return {"estimated_progress_pct": 0.0, "error": str(e)}
