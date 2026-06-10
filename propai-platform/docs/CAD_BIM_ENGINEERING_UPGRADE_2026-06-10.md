# CAD/BIM 에디터 엔지니어링 업그레이드 계획 (2026-06-10)

## 1. 문제 진단 (실측 근거)

사용자 신고: **2D 편집화면이 패널에 가려 편집 공간이 없고 포인트 드래그/찍기 등 실질 편집이 안 됨**,
**3D BIM은 아무 오브젝트도 안 뜸**, **AI 포토리얼 렌더는 "요청 거부"**.

코드 정밀 감사 결과 근본원인:

### 2D (`components/design/CADEditor.tsx`)
1. **고정 캔버스**: Konva `Stage`가 `width=800 height=600` 고정 + `flex items-center justify-center`로 가운데 정렬 → 컨테이너를 채우지 못하고 한쪽으로 치우침, 드래그 좌표 불일치.
2. **패널이 캔버스를 덮음**: 좌(320px)·우(360px) HUD 글래스 패널이 z-index 없이 DOM 뒤순서라 캔버스 위를 덮음 → 중앙 편집영역이 거의 없음.
3. **도구 버튼이 죽어있음**: SELECT/POINT/POLY/DIM 버튼에 `onClick` 없음, `selectedTool` 상태 없음 → 클릭해도 무동작.
4. **드래그 라이브 갱신 없음**: `onDragEnd`만 있고 `onDragMove` 없음 → 끌어도 즉시 반응 없음, 면적/BCR/FAR 실시간 미갱신.

### 3D (`components/design/CadBimIntegrationPanel.tsx` + 백엔드)
1. **서버 의존 100%**: 3D는 백엔드 `bim/model.glb`(ifcopenshell→glTF)만 렌더. 파이프라인이 실패하면 빈 화면.
2. `pygltflib`가 `requirements.txt` 누락(`requirements.oracle.txt`에만) → 비-Oracle 환경 500.
3. **포토리얼 렌더**: `REPLICATE_API_TOKEN` 미설정/무효 시 거부. (선택 기능 — 키 없으면 정직 안내로 처리)

## 2. 경쟁/기술 리서치 결론 (Forma·TestFit·Hypar·Snaptrude·Delve)

핵심 채택 패턴:
- **결정론적 기하 커널 + NL 의도 파싱** (Hypar/TestFit): LLM은 자유문장→구조화 `DesignIntent`만, 기하는 결정론 함수가 생성. 할루시네이션·재현성·법규 하드캡 강제.
- **화면 3D는 클라이언트 절차생성이 단독 책임** (서버 IFC 무관 항상 렌더). 서버 ifcopenshell은 정식 IFC4 산출물·정밀 QTO용 비동기 경로로만.
- **드래그→면적 라이브 재계산** (Snaptrude): per-vertex 핸들 + shoelace 면적 + BCR/FAR 즉시 갱신.
- 2D: **Konva 유지**(올바른 선택), 3D: **Three/R3F 절차생성 메인**.

## 3. 차별화 기능 (한국형, 기존 자산 결합)

1. **법규 위반 실시간 빨강 하이라이트** — 드래그 중 BCR/FAR/높이 한도 초과 즉시 표시(법정 상한 개략 클라 힌트 + 백엔드 권위 검증).
2. **세대믹스 슬라이더 → 평면 재배치 → 수지 실시간** (unit_mix_optimizer + /v2/feasibility 결선).
3. **음성/NL "북측 일조 확보" → 매스 자동 후퇴** (DesignIntent 경로).
4. **일조권/조망 시뮬레이션** (태양궤적 raycasting, 세대별 분양가 차등 근거).
5. **종상향 잠재 듀얼뷰** (현행 vs 잠재 매스 병렬 생성).
6. **인허가 7개 개발방식 오버레이** (permits/ai-analysis 배지).
7. **Delve형 파레토 Top-3** (우선순위 가중 → 대안 + 실거래 기반 ROI).
8. **드래그 편집 → 은행제출 보고서/BIM 적산 자동 갱신**.

## 4. 구현 로드맵

| 단계 | 내용 | 상태 |
|------|------|------|
| **P1** | 2D 에디터 전면 리팩토링: 반응형 캔버스(ResizeObserver), 도구 상태머신(SELECT/POINT/POLY/DIM/DELETE), 라이브 드래그, 면적/BCR/FAR 실시간, 법규 빨강 하이라이트(기능①), 비-차폐 컴팩트 HUD | **이번 구현** |
| **P2** | 클라이언트 절차생성 3D(footprint+층수→슬래브/외벽/코어/창호, 서버 무관 항상 렌더). 서버 glb 도착 시 교체 | **이번 구현** |
| **P3** | 백엔드 견고화: pygltflib requirements.txt 추가, model.glb graceful fallback, 포토리얼=선택 처리 | **이번 구현** |
| P4 | 세대믹스 슬라이더 라이브 루프(기능②) | 다음 |
| P5 | NL/음성 의도파싱(기능③) | 다음 |
| P6 | 일조/조망·종상향 듀얼뷰·파레토(④⑤⑦) — 서버 비동기 | 다음 |

## 5. 타깃 아키텍처

```
CLIENT (브라우저, 항상 동작)
  [상태] Zustand 단일 SSOT (footprint·floors·core·units·intent)
  [2D] Konva: per-vertex/엣지 드래그 + 그리드/직각 스냅 + shoelace 면적 → BCR/FAR 라이브 + 법규 clamp/하이라이트
  [3D] Three/R3F 절차생성: 슬래브/외벽/코어/세대벽/창호 (InstancedMesh, Environment/autoRotate 금지)
  [NL] LLM=의도파싱 ONLY → DesignIntent → 결정론 커널
       │ 비동기(렌더 차단 안 함)            ▲ 결과 도착 시 교체/부착
SERVER (정밀·비동기)
  ifcopenshell→IFC4 정식 산출물 + 정밀 QTO(5D) / unit_mix(SLSQP) / feasibility(ROI) / permits / 법규 권위 검증
```
</content>
</invoke>
