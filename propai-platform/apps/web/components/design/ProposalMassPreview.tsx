'use client';

import { Canvas } from "@react-three/fiber";
import { CameraControls, Grid } from "@react-three/drei";
import { ProceduralBuilding } from "./ProceduralBuilding";

type Props = {
  width: number;
  depth: number;
  floors: number;
  floorHeight?: number;
};

// 설계안 개략 매스 3D 프리뷰 — 추정 치수 기반, 정밀 BIM 아님.
// frameloop="demand" 로 무한 렌더루프 방지. autoRotate/HDR/Environment 사용 금지.
export function ProposalMassPreview({ width, depth, floors, floorHeight = 3 }: Props) {
  const totalH = floors * floorHeight;
  // 아이소뷰: 건물이 화면에 잘 들어오는 카메라 위치
  const camX = width * 1.2;
  const camY = totalH * 1.2;
  const camZ = depth * 1.8;

  return (
    <div className="h-64 w-full rounded-lg overflow-hidden border border-[var(--line)]">
      {/* frameloop="demand"+autoRotate/HDR 없음(과거 메인스레드 점유 사고 회피). dpr 상한으로 고DPI 부하 캡.
          그림자는 개략 매스에 불필요해 비활성(Canvas shadows 미설정). */}
      <Canvas
        frameloop="demand"
        dpr={[1, 1.5]}
        camera={{ position: [camX, camY, camZ], fov: 45 }}
      >
        <ambientLight intensity={0.7} />
        <directionalLight position={[10, 20, 10]} intensity={0.8} />
        <Grid
          infiniteGrid
          fadeDistance={50}
          cellColor="#334155"
          sectionColor="#2dd4bf"
          cellSize={1}
          sectionSize={5}
          fadeStrength={1}
        />
        <ProceduralBuilding
          width={width}
          depth={depth}
          floors={floors}
          floorHeight={floorHeight}
        />
        <CameraControls />
      </Canvas>
    </div>
  );
}
