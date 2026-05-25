# PropAI v61.0 -- IDE 빌드 프롬프트 Part 2
# AI CAD 건축설계 자동화 시스템 완전 구현
# (Part 1 완료 후 실행) | ASCII 100% | 2026-03-30

================================================================================
[IDE 입력 프롬프트 -- Part 2: AI CAD 건축설계 시스템]
================================================================================

## PROMPT:

Part 1에서 생성된 PropAI v61.0 프로젝트에 AI CAD 건축설계 자동화 시스템을
완전히 구현해 주세요. 아래 명세를 그대로 구현하세요.

---

## MODULE A: 도면 생성 서비스 핵심 엔진

### A-1: 공통 유틸리티 + 도면 요소 모델

```python
# propai/apps/api/app/services/cad/drawing_elements.py
"""CAD 도면 요소 모델 -- 점/선/폴리선/원/텍스트/치수/해칭"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import uuid, math

def _id(): return str(uuid.uuid4())[:8]

@dataclass
class Pt:
    x: float; y: float
    def d(self): return {"x": self.x, "y": self.y}

@dataclass
class DrawElem:
    id:        str   = field(default_factory=_id)
    type:      str   = "line"
    layer:     str   = "A-WALL"
    color:     Optional[str]  = None
    lw:        Optional[float]= None
    pts:       List[Dict]     = field(default_factory=list)
    text:      Optional[str]  = None
    h:         Optional[float]= None
    rot:       float          = 0.0
    cx:        Optional[float]= None
    cy:        Optional[float]= None
    r:         Optional[float]= None
    hatch:     Optional[str]  = None
    dim_val:   Optional[float]= None
    props:     Dict[str,Any]  = field(default_factory=dict)

    def to_dict(self):
        return {k:v for k,v in asdict(self).items() if v is not None}

# 표준 레이어 정의 (KS A ISO 13567)
LAYERS = {
    "A-WALL":  {"c":"#000000","w":0.50,"d":"외벽/내벽"},
    "A-DOOR":  {"c":"#0000FF","w":0.35,"d":"문"},
    "A-WIND":  {"c":"#0000AA","w":0.25,"d":"창호"},
    "A-COLS":  {"c":"#111111","w":0.70,"d":"기둥"},
    "A-BEAM":  {"c":"#333333","w":0.50,"d":"보"},
    "A-STRS":  {"c":"#666666","w":0.35,"d":"계단"},
    "A-ELEV":  {"c":"#888888","w":0.25,"d":"승강기"},
    "A-PARK":  {"c":"#AAAAAA","w":0.18,"d":"주차선"},
    "A-ROOF":  {"c":"#000000","w":0.25,"d":"지붕"},
    "A-DIMS":  {"c":"#FF0000","w":0.18,"d":"치수선"},
    "A-TEXT":  {"c":"#000000","w":0.18,"d":"문자"},
    "A-ANNO":  {"c":"#005500","w":0.18,"d":"주석"},
    "A-SITE":  {"c":"#008800","w":0.50,"d":"대지경계"},
    "A-ROAD":  {"c":"#CCCCCC","w":0.35,"d":"도로"},
    "A-SETB":  {"c":"#FF8800","w":0.18,"d":"건축선"},
    "A-TREE":  {"c":"#00AA00","w":0.25,"d":"수목"},
    "A-HATC":  {"c":"#AAAAAA","w":0.13,"d":"해칭"},
    "A-CONC":  {"c":"#888888","w":0.13,"d":"콘크리트"},
    "A-GLAS":  {"c":"#AADDFF","w":0.13,"d":"유리"},
    "A-NORT":  {"c":"#000000","w":0.35,"d":"방위"},
    "A-SCAL":  {"c":"#000000","w":0.18,"d":"스케일바"},
    "A-TITL":  {"c":"#000000","w":0.35,"d":"도면표제"},
}

# 세대 유형 치수 (전용면적 m2)
UNIT_DIMS = {
    "39A": {"w":6.0,"d":8.5,"area":39.2},
    "49A": {"w":7.0,"d":9.0,"area":48.8},
    "59A": {"w":8.0,"d":9.5,"area":59.2},
    "74A": {"w":9.0,"d":10.0,"area":74.1},
    "84A": {"w":9.5,"d":10.5,"area":84.0},
    "84B": {"w":8.5,"d":11.5,"area":84.3},
    "114A":{"w":11.0,"d":12.0,"area":114.2},
}

def dist(a: Dict, b: Dict) -> float:
    return math.sqrt((a["x"]-b["x"])**2 + (a["y"]-b["y"])**2)

def make_line(x1,y1,x2,y2,layer="A-WALL") -> DrawElem:
    return DrawElem(type="line", layer=layer,
                    pts=[{"x":x1,"y":y1},{"x":x2,"y":y2}])

def make_rect(x,y,w,h,layer="A-WALL") -> DrawElem:
    return DrawElem(type="rect", layer=layer,
                    pts=[{"x":x,"y":y},{"x":x+w,"y":y+h}])

def make_text(x,y,text,height=0.3,layer="A-TEXT") -> DrawElem:
    return DrawElem(type="text", layer=layer, text=text,
                    h=height, pts=[{"x":x,"y":y}])

def make_dim(x1,y1,x2,y2) -> DrawElem:
    d = dist({"x":x1,"y":y1},{"x":x2,"y":y2})
    return DrawElem(type="dim_linear", layer="A-DIMS",
                    pts=[{"x":x1,"y":y1},{"x":x2,"y":y2}],
                    dim_val=round(d,3))

def make_circle(cx,cy,r,layer="A-COLS") -> DrawElem:
    return DrawElem(type="circle", layer=layer,
                    cx=cx, cy=cy, r=r,
                    pts=[{"x":cx,"y":cy}])
```

### A-2: 배치도 생성기

```python
# propai/apps/api/app/services/cad/generators/site_plan.py
"""배치도 자동 생성 -- 대지경계/건물배치/이격거리/방위/치수/스케일바"""
import svgwrite, math
from typing import List, Dict, Optional
from app.services.cad.drawing_elements import make_line, make_text, make_dim

class SitePlanGenerator:

    def generate(self, params: dict) -> str:
        """
        params:
          site_polygon: [{x,y}...] 대지 폴리곤 (반시계방향, m)
          site_area: float (m2)
          building_polygon: [{x,y}...] 건물 외곽
          building_area: float (m2)
          roads: [{side,width}...]
          max_bcr: float (%)
          setback_road: float (m)
          setback_side: float (m)
          project_name: str
          north_angle: float (도)
        """
        p = params
        site_poly = p.get("site_polygon", [
            {"x":0,"y":0},{"x":30,"y":0},
            {"x":30,"y":25},{"x":0,"y":25}
        ])
        bldg_poly = p.get("building_polygon", [
            {"x":3,"y":3},{"x":27,"y":3},
            {"x":27,"y":22},{"x":3,"y":22}
        ])
        site_area  = p.get("site_area", 750.0)
        bldg_area  = p.get("building_area", 480.0)
        max_bcr    = p.get("max_bcr", 60.0)
        project_name = p.get("project_name", "")
        north_angle  = p.get("north_angle", 0.0)

        cw, ch = 1200, 900
        bbox = self._bbox(site_poly)
        sw, sh = bbox["max_x"]-bbox["min_x"], bbox["max_y"]-bbox["min_y"]
        sf = min((cw-200)/sw, (ch-200)/sh)

        def tx(x): return 100 + (x-bbox["min_x"])*sf
        def ty(y): return ch-100 - (y-bbox["min_y"])*sf

        dwg = svgwrite.Drawing(size=(f"{cw}px",f"{ch}px"))
        dwg.add(dwg.style("text{font-family:'Malgun Gothic','Arial',sans-serif;}"))

        # 1. 대지 배경
        pts = [(tx(v["x"]),ty(v["y"])) for v in site_poly]
        dwg.add(dwg.polygon(pts, stroke="#000",stroke_width="3",
            fill="#FFFDE7",fill_opacity="0.5"))

        # 2. 건축선 (점선)
        sb = p.get("setback_road", 2.0)
        if sb > 0:
            sx0 = tx(bbox["min_x"]+sb*0.5)
            sx1 = tx(bbox["max_x"]-sb*0.5)
            sb_y = ty(bbox["min_y"]+sb)
            dwg.add(dwg.line(start=(sx0,sb_y),end=(sx1,sb_y),
                stroke="#FF6600",stroke_width="1.5",
                stroke_dasharray="10,5"))
            dwg.add(dwg.text(f"건축선(이격{sb:.1f}m)",
                insert=(sx0,sb_y-5),font_size="10px",fill="#FF6600"))

        # 3. 건물
        bpts = [(tx(v["x"]),ty(v["y"])) for v in bldg_poly]
        dwg.add(dwg.polygon(bpts, stroke="#1A237E",stroke_width="4",
            fill="#BBDEFB",fill_opacity="0.8"))

        # 4. 이격 치수
        bb_bbox = self._bbox(bldg_poly)
        # 남측 이격
        d_s = bb_bbox["min_y"]-bbox["min_y"]
        if d_s > 0.2:
            cx = (bb_bbox["min_x"]+bb_bbox["max_x"])/2
            self._dim_arrow(dwg,tx(cx),ty(bbox["min_y"]),
                            tx(cx),ty(bb_bbox["min_y"]),
                            f"{d_s:.1f}m","V")
        # 동측 이격
        d_e = bbox["max_x"]-bb_bbox["max_x"]
        if d_e > 0.2:
            cy = (bb_bbox["min_y"]+bb_bbox["max_y"])/2
            self._dim_arrow(dwg,tx(bb_bbox["max_x"]),ty(cy),
                            tx(bbox["max_x"]),ty(cy),
                            f"{d_e:.1f}m","H")

        # 5. 대지 치수
        mid_x = (tx(bbox["min_x"])+tx(bbox["max_x"]))/2
        self._dim_arrow(dwg,tx(bbox["min_x"]),ty(bbox["min_y"])+45,
                        tx(bbox["max_x"]),ty(bbox["min_y"])+45,
                        f"{sw:.1f}m","H",color="#CC0000")
        mid_y = (ty(bbox["min_y"])+ty(bbox["max_y"]))/2
        self._dim_arrow(dwg,tx(bbox["min_x"])-45,ty(bbox["min_y"]),
                        tx(bbox["min_x"])-45,ty(bbox["max_y"]),
                        f"{sh:.1f}m","V",color="#CC0000")

        # 6. 방위 표시
        self._north_arrow(dwg, cw-80, 70, north_angle)

        # 7. 스케일바
        self._scale_bar(dwg, 100, ch-50, sf, 200)

        # 8. 건폐율 정보
        actual_bcr = bldg_area/site_area*100
        color = "#CC0000" if actual_bcr > max_bcr else "#000000"
        for i,(line) in enumerate([
            f"대지면적: {site_area:,.1f} m²",
            f"건축면적: {bldg_area:,.1f} m²",
            f"건폐율: {actual_bcr:.1f}% / {max_bcr:.0f}%",
        ]):
            dwg.add(dwg.text(line, insert=(cw-280,30+i*16),
                font_size="10px",
                fill=("#CC0000" if i==2 and actual_bcr>max_bcr else "#000000")))

        # 9. 표제란
        self._title_block(dwg, project_name, "배치도", "B-01", 200, cw, ch)

        return dwg.tostring()

    def _bbox(self, poly):
        xs = [v["x"] for v in poly]; ys = [v["y"] for v in poly]
        return {"min_x":min(xs),"max_x":max(xs),"min_y":min(ys),"max_y":max(ys)}

    def _dim_arrow(self, dwg, x1, y1, x2, y2, text, orient, color="#FF0000"):
        dwg.add(dwg.line(start=(x1,y1),end=(x2,y2),
            stroke=color,stroke_width="0.8"))
        for px,py in [(x1,y1),(x2,y2)]:
            dwg.add(dwg.circle(center=(px,py),r=2,fill=color))
        mx,my = (x1+x2)/2,(y1+y2)/2
        off = (-15 if orient=="H" else 0)
        dwg.add(dwg.text(text,insert=(mx+(0 if orient=="H" else 15),
            my+off if orient=="H" else my),
            font_size="9px",fill=color,text_anchor="middle"))

    def _north_arrow(self, dwg, cx, cy, angle_deg):
        r = 22
        ang = math.radians(angle_deg)
        tx = cx + r*math.sin(ang); ty = cy - r*math.cos(ang)
        dwg.add(dwg.circle(center=(cx,cy),r=r+4,
            stroke="#000",stroke_width=1,fill="white"))
        dwg.add(dwg.line(start=(cx,cy),end=(tx,ty),
            stroke="black",stroke_width=3))
        dwg.add(dwg.text("N",insert=(tx-4,ty-5),
            font_size="12px",font_weight="bold",fill="black"))

    def _scale_bar(self, dwg, x, y, sf, scale):
        bar = 10*sf
        dwg.add(dwg.rect(insert=(x,y),size=(bar,5),fill="black"))
        dwg.add(dwg.rect(insert=(x+bar/2,y),size=(bar/2,5),
            fill="white",stroke="black",stroke_width="1"))
        dwg.add(dwg.text("0",insert=(x,y+14),font_size="9px"))
        dwg.add(dwg.text("10m",insert=(x+bar,y+14),font_size="9px"))
        dwg.add(dwg.text(f"S=1:{scale}",insert=(x,y+24),
            font_size="9px",fill="#555"))

    def _title_block(self, dwg, proj, title, code, scale, cw, ch):
        tbx = cw-300
        dwg.add(dwg.rect(insert=(tbx,ch-80),size=(290,74),
            stroke="#000",stroke_width="1",fill="white"))
        for i,(lbl,val) in enumerate([
            ("공사명",proj),("도면명",title),
            ("도면번호",code),("축척",f"1:{scale}")
        ]):
            dwg.add(dwg.text(f"{lbl}: {val}",
                insert=(tbx+8,ch-80+14+i*17),font_size="11px"))
```

### A-3: 전층 평면도 생성기

```python
# propai/apps/api/app/services/cad/generators/floor_plan.py
"""
층별 평면도 자동 생성
지하주차장 / 1층(로비+상가) / 기준층(주거세대) / 옥탑 전층
"""
import svgwrite
from app.services.cad.drawing_elements import UNIT_DIMS

class FloorPlanGenerator:

    def generate(self, params: dict) -> str:
        ft = params.get("floor_type","standard_unit")
        dispatch = {
            "basement_parking": self._basement,
            "ground_lobby":     self._ground,
            "standard_unit":    self._standard,
            "rooftop":          self._rooftop,
        }
        return dispatch.get(ft, self._standard)(params)

    def _common_setup(self, params, cw=1400, ch=1000):
        fw = params.get("floor_width", 40.0)
        fd = params.get("floor_depth", 16.0)
        sf = min((cw-200)/fw, (ch-200)/fd)
        dwg = svgwrite.Drawing(size=(f"{cw}px",f"{ch}px"))
        dwg.add(dwg.style("text{font-family:'Malgun Gothic','Arial',sans-serif;}"))
        def tx(x): return 100+x*sf
        def ty(y): return ch-100-y*sf
        return dwg, sf, tx, ty, fw, fd

    def _outer_wall(self, dwg, tx, ty, sf, fw, fd, wt=0.20):
        dwg.add(dwg.rect(insert=(tx(0),ty(fd)),size=(fw*sf,fd*sf),
            stroke="#000",stroke_width="3",fill="none"))
        w = wt*sf
        dwg.add(dwg.rect(insert=(tx(0)+w,ty(fd)+w),
            size=(fw*sf-w*2,fd*sf-w*2),
            stroke="#000",stroke_width="1.5",fill="none"))

    def _core(self, dwg, tx, ty, sf, cx, cy, cw_m=5.0, cd_m=5.0):
        dwg.add(dwg.rect(insert=(tx(cx),ty(cy+cd_m)),
            size=(cw_m*sf,cd_m*sf),
            stroke="#333",stroke_width="2",fill="#CCCCCC"))
        ev_w = cw_m*0.4
        dwg.add(dwg.rect(insert=(tx(cx),ty(cy+cd_m)),
            size=(ev_w*sf,cd_m*sf),
            stroke="#555",stroke_width="1",fill="#AAAAAA"))
        for txt,px in [("EV",cx+ev_w/2),("계단",cx+ev_w+(cw_m-ev_w)/2)]:
            dwg.add(dwg.text(txt,insert=(tx(px),ty(cy+cd_m/2)+4),
                font_size="8px",text_anchor="middle",fill="white",font_weight="bold"))

    def _dims_and_title(self, dwg, params, sf, tx, ty, fw, fd, cw, ch):
        # 전체 폭/깊이 치수
        for (x1,y1,x2,y2,text) in [
            (0,-1.5,fw,-1.5,f"{fw:.1f}m"),
            (-1.5,0,-1.5,fd,f"{fd:.1f}m"),
        ]:
            px1,py1,px2,py2 = tx(x1),ty(y1),tx(x2),ty(y2)
            dwg.add(dwg.line(start=(px1,py1),end=(px2,py2),
                stroke="#FF0000",stroke_width="1"))
            mx,my = (px1+px2)/2,(py1+py2)/2
            dwg.add(dwg.text(text,insert=(mx,my+4) if y1==y2 else (mx+15,my),
                font_size="10px",fill="#FF0000",text_anchor="middle"))
        # 층 표시
        level = params.get("floor_level","기준층")
        dwg.add(dwg.text(f"[ {level} 평면도 ]",
            insert=(cw/2,28),font_size="18px",font_weight="bold",
            text_anchor="middle"))
        # 스케일바
        bar = 10*sf
        dwg.add(dwg.rect(insert=(100,ch-40),size=(bar,5),fill="black"))
        dwg.add(dwg.text("10m",insert=(100+bar,ch-38),font_size="9px"))
        scale = params.get("scale",100)
        dwg.add(dwg.text(f"S=1:{scale}",insert=(100,ch-28),
            font_size="9px",fill="#555"))
        # 표제
        proj = params.get("project_name","")
        tbx = cw-280
        dwg.add(dwg.rect(insert=(tbx,ch-75),size=(270,70),
            stroke="#000",stroke_width="1",fill="white"))
        for i,(l,v) in enumerate([("공사명",proj),("도면명",f"{level} 평면도"),
                                    ("축척",f"1:{scale}")]):
            dwg.add(dwg.text(f"{l}: {v}",insert=(tbx+8,ch-75+14+i*20),
                font_size="11px"))

    def _basement(self, params: dict) -> str:
        cw, ch = 1400, 1000
        dwg, sf, tx, ty, fw, fd = self._common_setup(params, cw, ch)
        wt = 0.20
        self._outer_wall(dwg, tx, ty, sf, fw, fd)
        # 주차 구획
        pw, pd, aisle = 2.5, 5.0, 6.0
        y = wt+0.3; count = 0
        while y + pd < fd - wt - 0.3:
            x = wt+0.3
            while x + pw < fw - wt - 0.3:
                dwg.add(dwg.rect(insert=(tx(x)+1,ty(y+pd)+1),
                    size=(pw*sf-2,pd*sf-2),
                    stroke="#888",stroke_width="1",fill="#F5F5F5"))
                count += 1
                dwg.add(dwg.text(f"P{count:02d}",
                    insert=(tx(x+pw/2),ty(y+pd/2)+4),
                    font_size="7px",text_anchor="middle",fill="#666"))
                x += pw
            # 통로
            ay = y + pd
            dwg.add(dwg.rect(insert=(tx(wt+0.3),ty(ay+aisle)),
                size=((fw-wt*2-0.6)*sf,aisle*sf),
                fill="#EEEEEE",stroke="none"))
            dwg.add(dwg.line(
                start=(tx(wt+0.3),ty(ay+aisle/2)),
                end=(tx(fw-wt-0.3),ty(ay+aisle/2)),
                stroke="#AAAAAA",stroke_width="1",stroke_dasharray="10,5"))
            y += pd + aisle
        # 경사로
        ramp_w = params.get("ramp_width", 5.5)
        rx = fw - wt - ramp_w - 0.3
        dwg.add(dwg.rect(insert=(tx(rx),ty(wt+0.3+8)),
            size=(ramp_w*sf,8*sf),
            stroke="#FF6600",stroke_width="2",fill="#FFE0B2"))
        dwg.add(dwg.text(f"경사로 W={ramp_w:.1f}m",
            insert=(tx(rx+ramp_w/2),ty(wt+0.3+4)),
            font_size="9px",text_anchor="middle",fill="#FF6600",font_weight="bold"))
        # 장애인주차
        dx = wt+0.3
        dwg.add(dwg.rect(insert=(tx(dx),ty(fd-wt-5.3)),
            size=(7.0*sf,5.0*sf),
            stroke="#0044CC",stroke_width="2",fill="#E3F2FD"))
        dwg.add(dwg.text("장애인주차 2대",
            insert=(tx(dx+3.5),ty(fd-wt-2.5)),
            font_size="8px",text_anchor="middle",fill="#0044CC"))
        # 코어
        cx = fw/2-2.5
        self._core(dwg,tx,ty,sf,cx,fd/2-2.5)
        dwg.add(dwg.text(f"주차 {count}대 (계획)",
            insert=(tx(1),ty(fd-wt-0.3)),
            font_size="12px",font_weight="bold"))
        self._dims_and_title(dwg,params,sf,tx,ty,fw,fd,cw,ch)
        return dwg.tostring()

    def _ground(self, params: dict) -> str:
        cw, ch = 1400, 1000
        dwg, sf, tx, ty, fw, fd = self._common_setup(params, cw, ch)
        wt = 0.20
        self._outer_wall(dwg, tx, ty, sf, fw, fd)
        # 로비
        lw = params.get("lobby_width", 10.0)
        dwg.add(dwg.rect(insert=(tx(wt),ty(wt+fd/3)),
            size=(lw*sf,(fd/3)*sf),
            stroke="#1A237E",stroke_width="2",fill="#E3F2FD"))
        dwg.add(dwg.text("로 비",
            insert=(tx(wt+lw/2),ty(wt+fd/6)),
            font_size="14px",font_weight="bold",
            text_anchor="middle",fill="#1A237E"))
        # 자동문
        dwg.add(dwg.rect(insert=(tx(wt+lw/2-1.5),ty(wt)),
            size=(3.0*sf,0.18*sf),stroke="#000",fill="#AAAAAA"))
        dwg.add(dwg.text("자동문 3.0m",
            insert=(tx(wt+lw/2),ty(wt-0.3)),
            font_size="8px",text_anchor="middle",fill="#333"))
        # 상가
        comm_units = params.get("commercial_units", 2)
        comm_w = (fw-wt*2-lw)/comm_units
        for i in range(comm_units):
            cx = wt+lw+i*comm_w
            dwg.add(dwg.rect(insert=(tx(cx),ty(wt+fd*0.6)),
                size=(comm_w*sf,(fd*0.4)*sf),
                stroke="#555",stroke_width="1.5",fill="#FFF9C4"))
            dwg.add(dwg.text(f"상가 {i+1}",
                insert=(tx(cx+comm_w/2),ty(wt+fd*0.3)),
                font_size="11px",text_anchor="middle",fill="#555"))
        # 관리실
        mx = fw-wt-3.0
        dwg.add(dwg.rect(insert=(tx(mx),ty(wt+fd*0.5)),
            size=(2.5*sf,2.0*sf),stroke="#666",fill="#F3E5F5"))
        dwg.add(dwg.text("관리실",insert=(tx(mx+1.25),ty(wt+fd*0.4)),
            font_size="9px",text_anchor="middle"))
        # 코어
        self._core(dwg,tx,ty,sf,fw/2-2.5,fd/2-2.5)
        self._dims_and_title(dwg,params,sf,tx,ty,fw,fd,cw,ch)
        return dwg.tostring()

    def _standard(self, params: dict) -> str:
        cw, ch = 1400, 1000
        dwg, sf, tx, ty, fw, fd = self._common_setup(params, cw, ch)
        wt = 0.20
        corr_w = params.get("corridor_width", 1.8)
        self._outer_wall(dwg, tx, ty, sf, fw, fd)
        # 중앙 복도
        corr_y = fd/2-corr_w/2
        dwg.add(dwg.rect(insert=(tx(wt),ty(corr_y+corr_w)),
            size=((fw-wt*2)*sf,corr_w*sf),
            stroke="#AAAAAA",stroke_width="1",fill="#EEEEEE"))
        dwg.add(dwg.text(f"복도 {corr_w:.1f}m",
            insert=(tx(fw/2),ty(corr_y+corr_w/2)+4),
            font_size="9px",text_anchor="middle",fill="#888"))
        # 세대 배치
        unit_mix = params.get("unit_mix",[{"type":"84A","count":4}])
        x_pos = wt+0.3
        for um in unit_mix:
            udim = UNIT_DIMS.get(um["type"],{"w":9.5,"d":5.5,"area":84.0})
            uw, count = udim["w"], um.get("count",2)
            for _ in range(count):
                if x_pos + uw > fw-wt:
                    break
                # 북측 세대
                y_n = corr_y+corr_w
                ud_n = fd-y_n-wt-0.3
                dwg.add(dwg.rect(insert=(tx(x_pos),ty(y_n+ud_n)),
                    size=(uw*sf,ud_n*sf),
                    stroke="#1A237E",stroke_width="1.5",fill="white"))
                dwg.add(dwg.text(f"Type {um['type']}",
                    insert=(tx(x_pos+uw/2),ty(y_n+ud_n/2)+4),
                    font_size="9px",text_anchor="middle",fill="#1A237E",
                    font_weight="bold"))
                dwg.add(dwg.text(f"{udim['area']}m2",
                    insert=(tx(x_pos+uw/2),ty(y_n+ud_n/2)-8),
                    font_size="8px",text_anchor="middle",fill="#555"))
                # 남측 세대
                ud_s = corr_y-wt
                if ud_s > 1.0:
                    dwg.add(dwg.rect(insert=(tx(x_pos),ty(wt+ud_s)),
                        size=(uw*sf,ud_s*sf),
                        stroke="#1A237E",stroke_width="1.5",fill="white"))
                # 세대문
                door_x = x_pos+uw/2-0.45
                dwg.add(dwg.rect(insert=(tx(door_x),ty(corr_y+corr_w)),
                    size=(0.9*sf,0.12*sf),fill="#4169E1"))
                x_pos += uw
        # 코어
        self._core(dwg,tx,ty,sf,fw/2-2.5,corr_y+corr_w/2-2.5)
        self._dims_and_title(dwg,params,sf,tx,ty,fw,fd,cw,ch)
        return dwg.tostring()

    def _rooftop(self, params: dict) -> str:
        cw, ch = 800, 600
        dwg, sf, tx, ty, fw, fd = self._common_setup(params, cw, ch)
        wt = 0.20
        self._outer_wall(dwg, tx, ty, sf, fw, fd)
        # 계단실 옥탑
        dwg.add(dwg.rect(insert=(tx(wt+0.5),ty(wt+0.5+3.5)),
            size=(2.5*sf,3.5*sf),stroke="#333",fill="#E0E0E0"))
        dwg.add(dwg.text("계단실",insert=(tx(wt+1.75),ty(wt+2.25)),
            font_size="9px",text_anchor="middle"))
        # 기계실
        mw = min(5.0,fw-wt*2-3.5)
        md = min(4.0,fd-wt*2-1.0)
        dwg.add(dwg.rect(insert=(tx(wt+3.5),ty(wt+0.5+md)),
            size=(mw*sf,md*sf),stroke="#666",fill="#F5F5F5"))
        dwg.add(dwg.text("기계실",insert=(tx(wt+3.5+mw/2),ty(wt+0.5+md/2)+4),
            font_size="10px",text_anchor="middle",fill="#666"))
        self._dims_and_title(dwg,params,sf,tx,ty,fw,fd,cw,ch)
        return dwg.tostring()
```

### A-4: 입면도 생성기 (4방향)

```python
# propai/apps/api/app/services/cad/generators/elevation.py
"""4방향 입면도 자동 생성 (동/서/남/북)"""
import svgwrite, math

FACADE = {
    "PC_PANEL": ("#E8EAF6","#90A4AE","#CFD8DC"),
    "BRICK":    ("#EFEBE9","#A1887F","#D7CCC8"),
    "GLASS":    ("#B3E5FC","#29B6F6","#81D4FA"),
    "GFRC":     ("#F5F5F5","#BDBDBD","#E0E0E0"),
}

class ElevationGenerator:

    def generate(self, params: dict) -> str:
        direction = params.get("direction","S")
        bw = params.get("building_width", 40.0)
        fc = params.get("floor_count", 15)
        fh = params.get("floor_height", 2.90)
        bf = params.get("basement_floors", 2)
        bfh = 2.80
        mat = params.get("facade_material","PC_PANEL")
        proj = params.get("project_name","")
        scale = params.get("scale", 200)

        cw, ch = 1400, 900
        total_h = fc*fh + bf*bfh
        sf = min((cw-200)/bw, (ch-200)/total_h)

        dwg = svgwrite.Drawing(size=(f"{cw}px",f"{ch}px"))
        dwg.add(dwg.style("text{font-family:'Malgun Gothic','Arial',sans-serif;}"))

        def tx(x): return 100+x*sf
        def ty(y): return ch-100-y*sf

        fs, ff, ft = FACADE.get(mat, FACADE["PC_PANEL"])

        # GL선
        dwg.add(dwg.line(start=(tx(-1),ty(0)),end=(tx(bw+1),ty(0)),
            stroke="#000",stroke_width="3"))
        dwg.add(dwg.text("G.L.",insert=(tx(-1.5),ty(0)+5),
            font_size="10px",font_weight="bold"))

        # 지하층
        bh_total = bf*bfh
        dwg.add(dwg.rect(insert=(tx(0),ty(0)),
            size=(bw*sf,bh_total*sf),
            stroke="#000",stroke_width="2",fill="#ECEFF1"))
        for f in range(bf):
            y_f = -(f+1)*bfh
            dwg.add(dwg.line(start=(tx(0),ty(y_f)),end=(tx(bw),ty(y_f)),
                stroke="#AAA",stroke_width="0.8",stroke_dasharray="5,3"))
            dwg.add(dwg.text(f"B{f+1}F",insert=(tx(-0.8),ty(y_f+bfh/2)+4),
                font_size="9px",text_anchor="end",fill="#666"))

        # 지상 외벽
        above_h = fc*fh
        dwg.add(dwg.rect(insert=(tx(0),ty(above_h)),
            size=(bw*sf,above_h*sf),
            stroke="#000",stroke_width="3",fill=fs))

        # 층선
        for f in range(fc+1):
            y_f = f*fh
            lw = "2" if f==0 else "0.8"
            dwg.add(dwg.line(start=(tx(0),ty(y_f)),end=(tx(bw),ty(y_f)),
                stroke="#AAA",stroke_width=lw,
                stroke_dasharray=("none" if f==0 else "4,2")))
            if f < fc:
                dwg.add(dwg.text(f"{f+1}F",
                    insert=(tx(-0.8),ty(f*fh+fh/2)+4),
                    font_size="9px",text_anchor="end",fill="#555"))

        # 창호 자동 배치
        wc = max(2, int(bw/4.0))
        ww = bw*0.35/wc
        sp = bw/wc
        for f in range(1, fc):
            for w in range(wc):
                wx = sp*w+(sp-ww)/2
                wz_b = f*fh+fh*0.2
                wz_t = f*fh+fh*0.75
                wpx = [(tx(wx),ty(wz_b)),(tx(wx+ww),ty(wz_b)),
                       (tx(wx+ww),ty(wz_t)),(tx(wx),ty(wz_t))]
                dwg.add(dwg.polygon(wpx,fill="#B3E5FC",fill_opacity="0.8",
                    stroke="#29B6F6",stroke_width="1.5"))
                dwg.add(dwg.line(start=(tx(wx+ww/2),ty(wz_b)),
                    end=(tx(wx+ww/2),ty(wz_t)),
                    stroke="#29B6F6",stroke_width="0.8"))

        # 1층 입구
        ex = bw/2-2.0
        dwg.add(dwg.rect(insert=(tx(ex),ty(fh)),
            size=(4.0*sf,fh*sf),
            stroke="#1A237E",stroke_width="2",fill="#E3F2FD"))
        dwg.add(dwg.text("ENTRANCE",insert=(tx(ex+2.0),ty(fh*0.5)+4),
            font_size="9px",text_anchor="middle",fill="#1A237E"))

        # 발코니 (S/E/W측)
        if direction in ["S","E","W"]:
            for f in range(2, fc):
                bd = 1.3
                for w in range(wc):
                    wx = sp*w
                    wy = f*fh
                    dwg.add(dwg.rect(
                        insert=(tx(wx+sp*0.1),ty(wy+bd*0.25)),
                        size=((sp*0.8)*sf,(bd*0.25)*sf),
                        stroke="#666",stroke_width="1",
                        fill="#ECEFF1",fill_opacity="0.8"))

        # 파라펫 + 옥탑
        pht = 1.2
        roof_y = fc*fh
        dwg.add(dwg.rect(insert=(tx(0),ty(roof_y+pht)),
            size=(bw*sf,pht*sf),
            stroke="#000",stroke_width="2",fill="#ECEFF1"))
        stw = 3.0; stx = bw/2-stw/2; sth = 3.5
        dwg.add(dwg.rect(insert=(tx(stx),ty(roof_y+pht+sth)),
            size=(stw*sf,sth*sf),
            stroke="#555",stroke_width="2",fill="#CFD8DC"))
        dwg.add(dwg.text("옥탑",insert=(tx(stx+stw/2),ty(roof_y+pht+sth/2)+4),
            font_size="9px",text_anchor="middle",fill="#555"))

        # 높이 치수 (우측)
        rx = bw+1.5
        dwg.add(dwg.line(start=(tx(rx),ty(0)),end=(tx(rx),ty(above_h)),
            stroke="#FF0000",stroke_width="1"))
        dwg.add(dwg.text(f"H={above_h:.1f}m",
            insert=(tx(rx)+12,ty(above_h/2)+4),
            font_size="10px",fill="#FF0000"))

        # 방향/제목
        dir_nm = {"E":"동측","W":"서측","S":"남측","N":"북측"}
        title = f"[ {dir_nm.get(direction,direction)}측 입면도 ]"
        dwg.add(dwg.text(title,insert=(cw/2,28),
            font_size="18px",font_weight="bold",text_anchor="middle"))
        # 스케일바
        bar = 10*sf
        dwg.add(dwg.rect(insert=(100,ch-40),size=(bar,5),fill="black"))
        dwg.add(dwg.text("10m",insert=(100+bar,ch-38),font_size="9px"))
        dwg.add(dwg.text(f"S=1:{scale}",insert=(100,ch-28),
            font_size="9px",fill="#555"))
        # 표제
        dir_code = {"E":"E","W":"W","S":"S","N":"N"}
        code = f"B-03-{dir_code.get(direction,'S')}"
        tbx = cw-280
        dwg.add(dwg.rect(insert=(tbx,ch-75),size=(270,70),
            stroke="#000",stroke_width="1",fill="white"))
        for i,(l,v) in enumerate([("공사명",proj),
            ("도면명",f"{dir_nm.get(direction)}측 입면도"),("도면번호",code)]):
            dwg.add(dwg.text(f"{l}: {v}",insert=(tbx+8,ch-75+14+i*20),
                font_size="11px"))

        return dwg.tostring()
```

### A-5: 단면도 생성기

```python
# propai/apps/api/app/services/cad/generators/section.py
"""종단면도/횡단면도 자동 생성 -- 구조체 해칭 + 층고 + 실명"""
import svgwrite

class SectionGenerator:

    def generate(self, params: dict) -> str:
        sec_type = params.get("section_type","longitudinal")
        cut_len  = params.get("cut_length", 40.0)
        fc       = params.get("floor_count", 15)
        fh       = params.get("floor_height", 2.90)
        bf       = params.get("basement_floors", 2)
        bfh      = 2.80
        st       = params.get("slab_thickness", 0.20)
        wt       = params.get("wall_thickness", 0.20)
        rooms    = params.get("rooms",[
            {"name":"거실","width":4.5},{"name":"주방","width":3.0},
            {"name":"침실1","width":3.0},{"name":"욕실","width":2.0}
        ])
        proj  = params.get("project_name","")
        scale = params.get("scale",100)

        cw, ch = 1400, 1000
        total_h = fc*fh + bf*bfh + 1.5
        sf = min((cw-200)/cut_len, (ch-200)/total_h)
        dwg = svgwrite.Drawing(size=(f"{cw}px",f"{ch}px"))
        dwg.add(dwg.style("text{font-family:'Malgun Gothic','Arial',sans-serif;}"))
        dwg.add(self._patterns(dwg))

        def tx(x): return 100+x*sf
        def ty(y): return ch-100-y*sf

        bh_total = bf*bfh
        found_t = 0.5

        # 지반 배경
        dwg.add(dwg.rect(insert=(tx(0),ty(-bh_total-found_t)),
            size=(cut_len*sf,(bh_total+found_t)*sf),
            fill="url(#earth-h)"))

        # 기초
        dwg.add(dwg.rect(insert=(tx(0),ty(-bh_total)),
            size=(cut_len*sf,found_t*sf),
            stroke="#000",stroke_width="2",
            fill="url(#conc-h)"))
        dwg.add(dwg.text("매트기초 t=500",
            insert=(tx(cut_len/2),ty(-bh_total+found_t/2)+4),
            font_size="9px",text_anchor="middle",fill="#333"))

        # 지하층
        for f in range(bf):
            y_b = -(bf-f)*bfh
            y_t = y_b+bfh
            # 슬래브
            dwg.add(dwg.rect(insert=(tx(0),ty(y_b+st)),
                size=(cut_len*sf,st*sf),
                stroke="#000",stroke_width="1",fill="url(#conc-h)"))
            # 실명
            dwg.add(dwg.text(f"B{bf-f}F 주차장",
                insert=(tx(cut_len/2),ty((y_b+y_t)/2)+4),
                font_size="10px",text_anchor="middle",fill="#333"))
            if f < bf-1:
                dwg.add(dwg.line(start=(tx(0),ty(y_t)),end=(tx(cut_len),ty(y_t)),
                    stroke="#AAA",stroke_width="1",stroke_dasharray="5,3"))
            dwg.add(dwg.text(f"B{bf-f}F",insert=(tx(-0.8),ty((y_b+y_t)/2)+4),
                font_size="9px",text_anchor="end",fill="#555"))

        # 지상층
        for f in range(fc):
            y_b, y_t = f*fh, (f+1)*fh
            # 슬래브
            dwg.add(dwg.rect(insert=(tx(0),ty(y_b+st)),
                size=(cut_len*sf,st*sf),
                stroke="#000",stroke_width="1",fill="url(#conc-h)"))
            # 단열재 (1층/최상층)
            if f == 0 or f == fc-1:
                dwg.add(dwg.rect(insert=(tx(0),ty(y_b+st+0.07)),
                    size=(cut_len*sf,0.06*sf),fill="url(#insul-h)"))
            # 실 구획
            x_cur = wt
            for room in rooms:
                rw = room["width"]
                if f == fc//2:
                    dwg.add(dwg.text(room["name"],
                        insert=(tx(x_cur+rw/2),ty((y_b+y_t)/2)+4),
                        font_size="10px",text_anchor="middle",
                        fill="#1A237E",font_weight="bold"))
                if x_cur > wt:
                    dwg.add(dwg.rect(insert=(tx(x_cur),ty(y_t-st)),
                        size=(wt*sf,(fh-st*2)*sf),
                        fill="url(#conc-h)",stroke="#555",stroke_width="0.5"))
                x_cur += rw
            # 층고 치수 (우측)
            rx = cut_len+1.0
            for yy in [y_b,y_t]:
                dwg.add(dwg.line(start=(tx(rx),ty(yy)),end=(tx(rx+0.8),ty(yy)),
                    stroke="#FF0000",stroke_width="0.8"))
            dwg.add(dwg.text(f"CH={fh-st*2:.2f}m",
                insert=(tx(rx+1.0),ty((y_b+y_t)/2)+4),
                font_size="8px",fill="#FF0000"))
            dwg.add(dwg.text(f"{f+1}F",insert=(tx(-0.8),ty((y_b+y_t)/2)+4),
                font_size="9px",text_anchor="end",fill="#555"))

        # 파라펫+지붕
        ry = fc*fh
        dwg.add(dwg.rect(insert=(tx(0),ty(ry+1.2)),
            size=(cut_len*sf,1.2*sf),stroke="#000",stroke_width="2",
            fill="url(#conc-h)"))
        dwg.add(dwg.rect(insert=(tx(0),ty(ry+1.2+0.07)),
            size=(cut_len*sf,0.06*sf),fill="#FFF176"))

        # GL선
        dwg.add(dwg.line(start=(tx(-1),ty(0)),end=(tx(cut_len+2),ty(0)),
            stroke="#000",stroke_width="3"))
        dwg.add(dwg.text("G.L.",insert=(tx(-1.5),ty(0)+5),
            font_size="10px",font_weight="bold"))

        # 전체 높이
        above = fc*fh
        dwg.add(dwg.line(start=(tx(-2),ty(0)),end=(tx(-2),ty(above)),
            stroke="#0000FF",stroke_width="1"))
        dwg.add(dwg.text(f"H={above:.1f}m",
            insert=(tx(-2)-22,ty(above/2)+4),font_size="10px",fill="#0000FF",
            transform=f"rotate(-90,{tx(-2)-22},{ty(above/2)})"))

        # 제목/스케일
        sname = "종단면도" if sec_type=="longitudinal" else "횡단면도"
        code  = "B-04-L" if sec_type=="longitudinal" else "B-04-T"
        dwg.add(dwg.text(f"[ {sname} ]",insert=(cw/2,28),
            font_size="18px",font_weight="bold",text_anchor="middle"))
        bar = 5*sf
        dwg.add(dwg.rect(insert=(100,ch-40),size=(bar,5),fill="black"))
        dwg.add(dwg.text("5m",insert=(100+bar,ch-38),font_size="9px"))
        dwg.add(dwg.text(f"S=1:{scale}",insert=(100,ch-28),
            font_size="9px",fill="#555"))
        tbx = cw-280
        dwg.add(dwg.rect(insert=(tbx,ch-75),size=(270,70),
            stroke="#000",stroke_width="1",fill="white"))
        for i,(l,v) in enumerate([("공사명",proj),("도면명",sname),
            ("도면번호",code)]):
            dwg.add(dwg.text(f"{l}: {v}",insert=(tbx+8,ch-75+14+i*20),
                font_size="11px"))
        return dwg.tostring()

    def _patterns(self, dwg):
        defs = dwg.defs
        # 콘크리트 (사선)
        p1 = dwg.pattern(id="conc-h",x=0,y=0,width=4,height=4,
            patternUnits="userSpaceOnUse")
        p1.add(dwg.line(start=(0,4),end=(4,0),stroke="#888",stroke_width="0.5"))
        defs.add(p1)
        # 단열재 (노랑)
        p2 = dwg.pattern(id="insul-h",x=0,y=0,width=8,height=4,
            patternUnits="userSpaceOnUse")
        p2.add(dwg.rect(insert=(0,0),size=(8,4),fill="#FFEB3B",fill_opacity="0.4"))
        defs.add(p2)
        # 지반 (갈색)
        p3 = dwg.pattern(id="earth-h",x=0,y=0,width=6,height=6,
            patternUnits="userSpaceOnUse")
        p3.add(dwg.rect(insert=(0,0),size=(6,6),fill="#BCAAA4"))
        p3.add(dwg.line(start=(0,6),end=(6,0),stroke="#8D6E63",stroke_width="1"))
        defs.add(p3)
        return defs
```

### A-6: 조감도 + 일영 시뮬레이션 생성기

```python
# propai/apps/api/app/services/cad/generators/perspective_shadow.py
"""아이소메트릭 조감도 + 일조/일영 시뮬레이션"""
import svgwrite, math

class PerspectiveGenerator:

    COS30 = math.cos(math.radians(30))
    SIN30 = math.sin(math.radians(30))

    def iso(self, x, y, z, cx, cy, sc):
        px = cx + (x-y)*self.COS30*sc
        py = cy - (x+y)*self.SIN30*sc - z*sc
        return (px, py)

    def generate(self, params: dict) -> str:
        bw = params.get("building_w", 40.0)
        bd = params.get("building_d", 16.0)
        fc = params.get("floor_count", 15)
        fh = params.get("floor_height", 2.90)
        bf = params.get("basement_floors", 2)
        bh = fc*fh + bf*2.8
        mat = params.get("facade_material","PC_PANEL")
        proj = params.get("project_name","")

        cw, ch = 1200, 900
        sc = min(cw/(bw+bd)/2.5, ch/(bh+bd)/2.5)
        sc = max(4, min(sc, 12))
        cx, cy = cw//2, ch//2+60

        dwg = svgwrite.Drawing(size=(f"{cw}px",f"{ch}px"))
        dwg.add(dwg.style("text{font-family:'Malgun Gothic','Arial',sans-serif;}"))

        FACS = {"PC_PANEL":("#E8EAF6","#90A4AE","#CFD8DC"),
                "BRICK":("#EFEBE9","#A1887F","#D7CCC8"),
                "GLASS":("#B3E5FC","#29B6F6","#81D4FA")}
        fs,ff,ft = FACS.get(mat,FACS["PC_PANEL"])

        def p3(x,y,z): return self.iso(x,y,z,cx,cy,sc)

        # 지면
        gpts = [p3(-2,-2,0),p3(bw+2,-2,0),p3(bw+2,bd+2,0),p3(-2,bd+2,0)]
        dwg.add(dwg.polygon(gpts,fill="#C8E6C9",stroke="#A5D6A7",stroke_width="1"))

        # 우측면
        rface = [p3(bw,0,0),p3(bw,bd,0),p3(bw,bd,bh),p3(bw,0,bh)]
        dwg.add(dwg.polygon(rface,fill=fs,stroke="#333",stroke_width="2"))

        # 정면
        fface = [p3(0,0,0),p3(bw,0,0),p3(bw,0,bh),p3(0,0,bh)]
        dwg.add(dwg.polygon(fface,fill=ff,stroke="#333",stroke_width="2"))

        # 층선
        for f in range(1,fc):
            y_fl = f*fh
            dwg.add(dwg.line(start=p3(0,0,y_fl),end=p3(bw,0,y_fl),
                stroke="#AAA",stroke_width="0.8",stroke_dasharray="4,2"))

        # 창호
        wc = max(2,int(bw/4.0))
        ww = bw*0.35/wc; sp = bw/wc
        for f in range(1,fc):
            for w in range(wc):
                wx = sp*w+(sp-ww)/2
                wz_b = f*fh+fh*0.2
                wz_t = f*fh+fh*0.75
                wpx = [p3(wx,0,wz_b),p3(wx+ww,0,wz_b),
                       p3(wx+ww,0,wz_t),p3(wx,0,wz_t)]
                dwg.add(dwg.polygon(wpx,fill="#B3E5FC",fill_opacity="0.8",
                    stroke="#29B6F6",stroke_width="1"))

        # 지붕
        roof = [p3(0,0,bh),p3(bw,0,bh),p3(bw,bd,bh),p3(0,bd,bh)]
        dwg.add(dwg.polygon(roof,fill=ft,stroke="#333",stroke_width="2"))

        # 나무
        for (tx2,ty2) in [(1,bd/2),(bw/3,bd+1),(2*bw/3,bd+1)]:
            cp = p3(tx2,ty2,2)
            dwg.add(dwg.circle(center=cp,r=sc*0.8,
                fill="#66BB6A",fill_opacity="0.8",
                stroke="#388E3C",stroke_width="1"))

        # 치수/제목
        dim1 = p3(bw+1,-1,0)
        dwg.add(dwg.text(f"W={bw:.0f}m",insert=(dim1[0],dim1[1]),
            font_size="10px",fill="#333"))
        dim2 = p3(bw+1,0,bh/2)
        dwg.add(dwg.text(f"H={bh:.0f}m",insert=(dim2[0]+5,dim2[1]),
            font_size="10px",fill="#333"))
        dwg.add(dwg.text("[ 동남측 조감도 ]",insert=(cw/2,28),
            font_size="18px",font_weight="bold",text_anchor="middle"))
        dwg.add(dwg.text(proj,insert=(cw/2,48),
            font_size="12px",text_anchor="middle",fill="#555"))

        return dwg.tostring()


class ShadowSimulator:
    """일조/일영 시뮬레이션 (건축법 제61조)"""

    SUMMER_DECL =  23.45
    WINTER_DECL = -23.45

    def sun_position(self, lat, hour, decl):
        L = math.radians(lat)
        D = math.radians(decl)
        H = math.radians((hour-12)*15)
        sin_alt = math.sin(L)*math.sin(D)+math.cos(L)*math.cos(D)*math.cos(H)
        alt = math.asin(max(-1,min(1,sin_alt)))
        cos_az_n = math.sin(D)-math.sin(L)*math.sin(alt)
        cos_az_d = math.cos(L)*math.cos(alt)
        if abs(cos_az_d) < 1e-10:
            az = 0.0
        else:
            cos_az = max(-1,min(1,cos_az_n/cos_az_d))
            az = math.acos(cos_az)
            if hour > 12: az = 2*math.pi-az
        return math.degrees(alt), math.degrees(az), alt, az

    def shadow_poly(self, sun_alt_r, sun_az_r, bw, bd, bh):
        if math.degrees(sun_alt_r) <= 0: return []
        sl = bh/math.tan(sun_alt_r)
        sdx = -math.sin(sun_az_r)*sl
        sdy = -math.cos(sun_az_r)*sl
        corners = [(0,0),(bw,0),(bw,bd),(0,bd)]
        return [{"x":c[0]+sdx,"y":c[1]+sdy} for c in corners] + \
               [{"x":c[0],"y":c[1]} for c in corners]

    def generate(self, params: dict) -> str:
        lat   = params.get("latitude", 37.5)
        bw    = params.get("building_w", 40.0)
        bd    = params.get("building_d", 16.0)
        bh    = params.get("building_h", 45.0)
        season= params.get("analysis_date","winter")
        slots = params.get("time_slots",["09:00","10:00","12:00","14:00","15:00"])
        proj  = params.get("project_name","")

        decl = self.SUMMER_DECL if season=="summer" else self.WINTER_DECL
        date_str = "하지 (6월 21일)" if season=="summer" else "동지 (12월 21일)"

        cw, ch = 1200, 900
        sf = min((cw-200)/80,(ch-200)/60)

        dwg = svgwrite.Drawing(size=(f"{cw}px",f"{ch}px"))
        dwg.add(dwg.style("text{font-family:'Malgun Gothic','Arial',sans-serif;}"))

        def tx(x): return cw//2+x*sf
        def ty(y): return ch//2-y*sf

        # 배경 대지
        dwg.add(dwg.rect(insert=(tx(-40),ty(30)),size=(80*sf,60*sf),
            fill="#E8F5E9",stroke="#4CAF50",stroke_width="1"))

        # 건물
        dwg.add(dwg.rect(insert=(tx(-bw/2),ty(bd/2)),
            size=(bw*sf,bd*sf),
            fill="#1565C0",fill_opacity="0.8",
            stroke="#0D47A1",stroke_width="2"))

        # 시간대별 그림자
        clrs = ["#9E9E9E","#757575","#616161","#424242","#212121"]
        alp  = [0.15,0.20,0.25,0.20,0.15]
        results = []

        for i,ts in enumerate(slots):
            h,m = map(int,ts.split(":"))
            hour = h+m/60.0
            alt_d,az_d,alt_r,az_r = self.sun_position(lat, hour, decl)
            spoly = self.shadow_poly(alt_r,az_r,bw,bd,bh)
            if spoly:
                pts = [(tx(pt["x"]-bw/2),ty(pt["y"]-bd/2)) for pt in spoly]
                dwg.add(dwg.polygon(pts,fill=clrs[i%5],
                    fill_opacity=str(alp[i%5]),
                    stroke=clrs[i%5],stroke_width="0.5"))
                dwg.add(dwg.text(ts,insert=(pts[0][0]+5,pts[0][1]+5),
                    font_size="9px",fill=clrs[i%5]))
                # 일영 면적 (삼각분할)
                n = len(spoly)
                area = abs(sum(
                    spoly[j]["x"]*spoly[(j+1)%n]["y"] -
                    spoly[(j+1)%n]["x"]*spoly[j]["y"]
                    for j in range(n)
                )/2)
                results.append({
                    "time":ts,"altitude":round(alt_d,1),
                    "azimuth":round(az_d,1),
                    "shadow_area":round(area,1),
                    "ok": alt_d > 4.0
                })

        # 방위
        dwg.add(dwg.line(start=(cw-70,50),end=(cw-70,30),
            stroke="black",stroke_width="2"))
        dwg.add(dwg.text("N",insert=(cw-74,26),
            font_size="14px",font_weight="bold"))

        # 제목
        dwg.add(dwg.text(f"일영 시뮬레이션 -- {date_str}",
            insert=(cw//2,28),font_size="16px",font_weight="bold",
            text_anchor="middle"))
        dwg.add(dwg.text(f"위도 {lat}N | 건물높이 {bh:.1f}m",
            insert=(cw//2,46),font_size="11px",
            text_anchor="middle",fill="#555"))

        # 분석표
        for i,r in enumerate(results):
            ok_str = "준수" if r["ok"] else "검토"
            col = "#2E7D32" if r["ok"] else "#C62828"
            dwg.add(dwg.text(
                f"{r['time']} | 고도 {r['altitude']}° | "
                f"그림자 {r['shadow_area']}m² | {ok_str}",
                insert=(100,ch-110+i*18),font_size="10px",fill=col))

        return dwg.tostring()
```

---

## MODULE B: FastAPI 설계도면 엔드포인트

```python
# propai/apps/api/app/api/v1/endpoints/design_drawing.py
"""AI 건축설계도면 자동화 API -- 전체 도면 세트 자동생성/편집/저장/DXF출력"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.base import Drawing, DesignStage, PermitDocumentSet, DesignAlternative
from app.services.cad.generators.site_plan import SitePlanGenerator
from app.services.cad.generators.floor_plan import FloorPlanGenerator
from app.services.cad.generators.elevation import ElevationGenerator
from app.services.cad.generators.section import SectionGenerator
from app.services.cad.generators.perspective_shadow import (
    PerspectiveGenerator, ShadowSimulator
)
from app.services.design.alternative_selector import DesignAlternativeSelector
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import ezdxf, io, json, os

router = APIRouter(prefix="/api/v1/design", tags=["AI CAD 건축설계"])

# ---- 전체 도면 세트 자동 생성 ----
class DrawingSetRequest(BaseModel):
    project_id: int
    site_polygon: List[dict] = Field(
        default=[{"x":0,"y":0},{"x":30,"y":0},
                 {"x":30,"y":25},{"x":0,"y":25}])
    site_area: float = 750.0
    building_w: float = 26.0
    building_d: float = 14.0
    floor_count: int = 15
    basement_floors: int = 2
    floor_height: float = 2.90
    max_bcr: float = 60.0
    max_far: float = 250.0
    unit_mix: List[dict] = [{"type":"84A","count":4}]
    core_count: int = 2
    facade_material: str = "PC_PANEL"
    project_name: str = ""
    latitude: float = 37.5
    north_angle: float = 0.0
    stage: int = 1   # 1=계획 2=기본 3=인허가

@router.post("/{project_id}/generate-full-set")
async def generate_full_set(
    project_id: int,
    req: DrawingSetRequest,
    db: AsyncSession = Depends(get_db)
):
    """Stage별 전체 도면 세트 자동 생성"""
    req.project_id = project_id
    building_h = req.floor_count*req.floor_height + req.basement_floors*2.8
    building_polygon = [
        {"x":2.0,"y":2.0},
        {"x":2.0+req.building_w,"y":2.0},
        {"x":2.0+req.building_w,"y":2.0+req.building_d},
        {"x":2.0,"y":2.0+req.building_d},
    ]

    site_gen  = SitePlanGenerator()
    fp_gen    = FloorPlanGenerator()
    el_gen    = ElevationGenerator()
    sec_gen   = SectionGenerator()
    persp_gen = PerspectiveGenerator()
    shad_sim  = ShadowSimulator()

    generated: Dict[str,str] = {}

    common = {
        "floor_width":  req.building_w,
        "floor_depth":  req.building_d,
        "floor_count":  req.floor_count,
        "floor_height": req.floor_height,
        "basement_floors": req.basement_floors,
        "facade_material": req.facade_material,
        "project_name": req.project_name,
    }

    # B-01 배치도
    generated["B-01"] = site_gen.generate({
        "site_polygon": req.site_polygon,
        "site_area":    req.site_area,
        "building_polygon": building_polygon,
        "building_area": req.building_w*req.building_d,
        "max_bcr": req.max_bcr,
        "project_name": req.project_name,
        "north_angle": req.north_angle,
    })

    # B-02: 지하 + 전층 평면도
    for b in range(req.basement_floors, 0, -1):
        generated[f"B-02-B{b}"] = fp_gen.generate({
            **common,
            "floor_level": f"B{b}F",
            "floor_type": "basement_parking",
            "parking_rows": 3,
            "parking_cols": int(req.building_w/2.5),
            "ramp_width": 5.5,
        })

    generated["B-02-01"] = fp_gen.generate({
        **common,"floor_level":"1F","floor_type":"ground_lobby",
        "lobby_width":10.0,"commercial_units":2,
    })
    generated["B-02-STD"] = fp_gen.generate({
        **common,"floor_level":"기준층","floor_type":"standard_unit",
        "unit_mix": req.unit_mix,"corridor_width":1.8,
    })
    generated["B-02-TOP"] = fp_gen.generate({
        **common,"floor_level":f"{req.floor_count}F","floor_type":"standard_unit",
        "unit_mix": req.unit_mix,
    })

    if req.stage >= 2:
        generated["B-02-RF"] = fp_gen.generate({
            **common,"floor_level":"RF","floor_type":"rooftop",
            "floor_width": req.building_w/3,
            "floor_depth": req.building_d/3,
        })

        # B-03: 4방향 입면도
        for direction in ["S","N","E","W"]:
            bw_el = req.building_w if direction in ["S","N"] else req.building_d
            generated[f"B-03-{direction}"] = el_gen.generate({
                **common,"direction":direction,"building_width":bw_el,
            })

        # B-04: 단면도
        generated["B-04-L"] = sec_gen.generate({
            **common,"section_type":"longitudinal","cut_length":req.building_w,
            "rooms":[{"name":"거실","width":4.5},{"name":"주방","width":3.0},
                     {"name":"침실","width":3.0},{"name":"욕실","width":2.0}],
        })
        generated["B-04-T"] = sec_gen.generate({
            **common,"section_type":"transverse","cut_length":req.building_d,
            "rooms":[{"name":"침실1","width":3.5},{"name":"복도","width":1.8},
                     {"name":"침실2","width":3.5}],
        })

    # C-01: 조감도
    generated["C-01-SE"] = persp_gen.generate({
        "building_w":req.building_w,"building_d":req.building_d,
        "building_h":building_h,"floor_count":req.floor_count,
        "facade_material":req.facade_material,
        "project_name":req.project_name,
    })

    # C-04: 일영 시뮬레이션 (하지/동지)
    for season,code in [("summer","C-04-S"),("winter","C-04-W")]:
        generated[code] = shad_sim.generate({
            "latitude":req.latitude,"building_w":req.building_w,
            "building_d":req.building_d,"building_h":building_h,
            "analysis_date":season,"project_name":req.project_name,
        })

    # DB 저장
    _CODE_MAP = {
        "B-01":"배치도","B-02":"평면도","B-03":"입면도",
        "B-04":"단면도","C-01":"조감도","C-04":"일영분석",
    }
    for code, svg in generated.items():
        drw_type = next((v for k,v in _CODE_MAP.items() if code.startswith(k)), "도면")
        db.add(Drawing(
            project_id=project_id,
            drawing_code=code,
            drawing_type=drw_type,
            drawing_name=f"{drw_type} ({code})",
            svg_content=svg,
            ai_generated=True,
            generation_params={
                "building_w":req.building_w,
                "building_d":req.building_d,
                "floor_count":req.floor_count,
            }
        ))
    await db.commit()

    return {
        "status":"OK",
        "drawing_count": len(generated),
        "drawing_codes": list(generated.keys()),
        "stage": req.stage,
    }

# ---- 개별 도면 SVG 반환 ----
@router.get("/{project_id}/drawings/{drawing_code}/svg")
async def get_drawing_svg(
    project_id: int, drawing_code: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Drawing).where(
        Drawing.project_id==project_id,
        Drawing.drawing_code==drawing_code,
        Drawing.is_latest==True
    )
    drw = (await db.execute(stmt)).scalar_one_or_none()
    if not drw:
        raise HTTPException(404, f"도면 {drawing_code} 없음")
    return Response(content=drw.svg_content, media_type="image/svg+xml")

# ---- CAD 요소 저장 (편집기에서 호출) ----
class CADSaveRequest(BaseModel):
    drawing_code: str
    elements: List[dict] = []
    layers: List[dict] = []

@router.post("/{project_id}/drawings/save")
async def save_drawing(
    project_id: int,
    req: CADSaveRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Drawing).where(
        Drawing.project_id==project_id,
        Drawing.drawing_code==req.drawing_code,
        Drawing.is_latest==True
    )
    drw = (await db.execute(stmt)).scalar_one_or_none()
    if drw:
        drw.vector_data = {"elements":req.elements,"layers":req.layers}
        drw.updated_at = datetime.utcnow()
    else:
        drw = Drawing(
            project_id=project_id,
            drawing_code=req.drawing_code,
            drawing_type="편집",
            drawing_name="CAD 편집 도면",
            vector_data={"elements":req.elements,"layers":req.layers},
            ai_generated=False,
        )
        db.add(drw)
    await db.commit()
    return {"status":"saved","element_count":len(req.elements)}

# ---- DXF 내보내기 ----
@router.post("/{project_id}/drawings/export-dxf")
async def export_dxf(project_id: int, data: dict):
    elements = data.get("elements",[])
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # 레이어 생성
    for layer_name in set(el.get("layer","A-WALL") for el in elements):
        if layer_name not in doc.layers:
            doc.layers.new(layer_name)

    for el in elements:
        pts   = el.get("pts",[]) or el.get("points",[])
        layer = el.get("layer","A-WALL")
        etype = el.get("type","line")
        dxf_attr = {"layer": layer}

        if etype in ["line"] and len(pts) >= 2:
            for i in range(len(pts)-1):
                msp.add_line((pts[i]["x"],pts[i]["y"]),
                              (pts[i+1]["x"],pts[i+1]["y"]),
                              dxfattribs=dxf_attr)

        elif etype == "polyline" and len(pts) >= 2:
            pl_pts = [(pt["x"],pt["y"]) for pt in pts]
            msp.add_lwpolyline(pl_pts, dxfattribs=dxf_attr)

        elif etype == "rect" and len(pts) >= 2:
            x1,y1 = pts[0]["x"],pts[0]["y"]
            x2,y2 = pts[1]["x"],pts[1]["y"]
            msp.add_lwpolyline(
                [(x1,y1),(x2,y1),(x2,y2),(x1,y2)],
                close=True, dxfattribs=dxf_attr)

        elif etype == "circle":
            cx = el.get("cx") or (pts[0]["x"] if pts else 0)
            cy = el.get("cy") or (pts[0]["y"] if pts else 0)
            r  = el.get("r", 1.0)
            msp.add_circle((cx,cy), r, dxfattribs=dxf_attr)

        elif etype == "text" and pts:
            msp.add_text(
                el.get("text",""),
                dxfattribs={**dxf_attr,
                            "height":el.get("h",0.3),
                            "rotation":el.get("rot",0)}
            ).set_placement((pts[0]["x"],pts[0]["y"]))

    buf = io.BytesIO()
    doc.write(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/dxf",
        headers={"Content-Disposition":
                 f"attachment; filename=drawing_{project_id}.dxf"}
    )

# ---- 설계 대안 몬테카를로 선정 ----
class AltSelectionRequest(BaseModel):
    alternatives: List[dict]
    iterations: int = 5000

@router.post("/{project_id}/select-alternative")
async def select_alternative(
    project_id: int,
    req: AltSelectionRequest,
    db: AsyncSession = Depends(get_db)
):
    from app.services.design.alternative_selector import DesignAlternativeSelector
    selector = DesignAlternativeSelector()
    result = selector.simulate(req.alternatives, req.iterations)
    # DB 저장
    for r in result["results"]:
        db.add(DesignAlternative(
            project_id=project_id,
            alt_no=r["alt_no"],
            alt_name=r.get("alt_name",""),
            ai_score=r["mean_score"],
            mc_win_rate=r["win_rate_pct"],
            is_selected=r.get("selected",False),
            selection_reason=r.get("basis","")
        ))
    await db.commit()
    return result

# ---- 인허가 도서 현황 ----
@router.get("/{project_id}/permit-docs")
async def get_permit_docs(project_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(PermitDocumentSet).where(
        PermitDocumentSet.project_id==project_id
    ).order_by(PermitDocumentSet.doc_code)
    docs = (await db.execute(stmt)).scalars().all()
    drawings = (await db.execute(
        select(Drawing).where(Drawing.project_id==project_id)
    )).scalars().all()
    drawing_codes = {d.drawing_code for d in drawings}
    total = len(docs)
    completed = sum(1 for d in docs if d.drawing_code in drawing_codes
                    or d.is_completed)
    return {
        "total": total,
        "completed": completed,
        "completion_pct": round(completed/total*100 if total else 0,1),
        "docs": [
            {"code":d.doc_code,"name":d.doc_name,
             "category":d.doc_category,"required":d.is_required,
             "completed": d.drawing_code in drawing_codes or d.is_completed}
            for d in docs
        ]
    }
```

### B-1: 설계 대안 선정 서비스

```python
# propai/apps/api/app/services/design/alternative_selector.py
"""
다기준 의사결정(MCDM) + 몬테카를로 시뮬레이션으로 최적 설계 대안 선정
기준: 수익성(40%) + 법규(30%) + 설계품질(20%) + ESG(10%)
"""
import numpy as np
from typing import List, Dict

class DesignAlternativeSelector:

    WEIGHTS = {"profit":0.40,"legal":0.30,"design":0.20,"esg":0.10}

    def simulate(self, alternatives: List[dict], iterations: int = 5000) -> dict:
        rng = np.random.default_rng(42)
        n = len(alternatives)
        scores = [[] for _ in range(n)]

        for _ in range(iterations):
            for i, alt in enumerate(alternatives):
                p = max(0,min(100, rng.normal(alt.get("profit_score",70),5)))
                l = max(0,min(100, rng.normal(alt.get("legal_score",85),3)))
                d = max(0,min(100, rng.normal(alt.get("design_score",70),4)))
                e = max(0,min(100, rng.normal(alt.get("esg_score",60),4)))
                s = (p*self.WEIGHTS["profit"] + l*self.WEIGHTS["legal"] +
                     d*self.WEIGHTS["design"] + e*self.WEIGHTS["esg"])
                scores[i].append(s)

        arrays = [np.array(s) for s in scores]
        results = []
        for i, alt in enumerate(alternatives):
            s = arrays[i]
            wins = sum(1 for j in range(iterations)
                      if all(s[j] >= arrays[k][j]
                             for k in range(n) if k != i))
            results.append({
                "alt_no":    i+1,
                "alt_name":  alt.get("alt_name", f"대안{i+1}"),
                "mean_score": round(float(np.mean(s)),2),
                "p10_score":  round(float(np.percentile(s,10)),2),
                "p90_score":  round(float(np.percentile(s,90)),2),
                "std_score":  round(float(np.std(s)),2),
                "win_rate_pct": round(wins/iterations*100,1),
                "selected": False,
            })

        best = max(results, key=lambda x: x["mean_score"])
        best["selected"] = True
        best["basis"] = (
            f"평균점수 {best['mean_score']}점 최고, "
            f"승률 {best['win_rate_pct']}% -- 만장일치 선정"
        )

        return {
            "results": results,
            "selected_alt": best["alt_no"],
            "iterations": iterations,
            "weights": self.WEIGHTS,
        }
```

---

## MODULE C: 인허가 도서 목록 시드

```python
# propai/apps/api/app/seeds/permit_docs_seed.py
"""건축법 시행규칙 제6조 인허가 도서 목록"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import PermitDocumentSet

PERMIT_DOCS = [
    # A: 건축계획서
    ("A-01","A","건축개요서",True),
    ("A-02","A","면적산출표",True),
    ("A-03","A","주차산출표",True),
    ("A-04","A","조경면적산출표",True),
    ("A-05","A","일조일영분석표",True),
    # B: 설계도면
    ("B-01","B","배치도",True),
    ("B-02-B3","B","B3층 평면도",True),
    ("B-02-B2","B","B2층 평면도",True),
    ("B-02-B1","B","B1층 평면도",True),
    ("B-02-01","B","1층 평면도",True),
    ("B-02-STD","B","기준층 평면도",True),
    ("B-02-TOP","B","최상층 평면도",True),
    ("B-02-RF","B","옥탑층 평면도",False),
    ("B-03-E","B","동측 입면도",True),
    ("B-03-W","B","서측 입면도",True),
    ("B-03-S","B","남측 입면도",True),
    ("B-03-N","B","북측 입면도",True),
    ("B-04-L","B","종단면도",True),
    ("B-04-T","B","횡단면도",True),
    ("B-05","B","단면상세도",True),
    ("B-06-01","B","기초구조도",True),
    ("B-06-02","B","골조구조도",True),
    ("B-07-01","B","기계설비계통도",True),
    ("B-07-02","B","전기설비계통도",True),
    ("B-07-03","B","소방설비계통도",True),
    # C: 3D
    ("C-01-SE","C","동남측 조감도",True),
    ("C-01-NE","C","동북측 조감도",False),
    ("C-02-F","C","정면 투시도",True),
    ("C-04-S","C","하지 일영시뮬레이션",True),
    ("C-04-W","C","동지 일영시뮬레이션",True),
    # D~G
    ("D-01","D","지반조사보고서 개요도",True),
    ("E-01","E","에너지절약설계검토서",True),
    ("E-02","E","단열재시방서",True),
    ("E-03","E","EPI검토서",True),
    ("F-01","F","소방시설설치계획표",True),
    ("F-02","F","소방동선배치도",True),
    ("G-01","G","장애인편의시설설치계획표",True),
]

async def seed_permit_docs(db: AsyncSession):
    for code,cat,name,req in PERMIT_DOCS:
        db.add(PermitDocumentSet(
            project_id=0,  # 프로젝트별로 복사 사용
            doc_code=code, doc_category=cat,
            doc_name=name, is_required=req
        ))
```

---

## STEP: Part 2 실행 검증

```bash
# 도면 생성 API 테스트
curl -X POST http://localhost:8000/api/v1/design/1/generate-full-set \
  -H "Content-Type: application/json" \
  -d '{
    "project_id":1,
    "site_area":750.0,
    "building_w":26.0,
    "building_d":14.0,
    "floor_count":15,
    "basement_floors":2,
    "max_bcr":60,
    "max_far":250,
    "unit_mix":[{"type":"84A","count":4}],
    "facade_material":"PC_PANEL",
    "project_name":"테스트 프로젝트",
    "latitude":37.5,
    "stage":2
  }'
# 예상: {"status":"OK","drawing_count":16,...}

# SVG 확인
curl http://localhost:8000/api/v1/design/1/drawings/B-01/svg > B-01.svg

# DXF 내보내기
curl -X POST http://localhost:8000/api/v1/design/1/drawings/export-dxf \
  -H "Content-Type: application/json" \
  -d '{"elements":[{"type":"line","layer":"A-WALL","pts":[{"x":0,"y":0},{"x":10,"y":0}]}]}' \
  -o drawing.dxf

# 인허가 도서 현황
curl http://localhost:8000/api/v1/design/1/permit-docs
```

---

## [Part 2 완료 -- Part 3 (AI BIM 공사비 자동산출)로 진행]
================================================================================
