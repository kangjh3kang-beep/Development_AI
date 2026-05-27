import { create } from 'zustand';

export type GenerationTemplateType = 'residential' | 'logistics' | 'eco-office';

export interface GenerationProgressStep {
  stepId: string;
  name: string;
  status: 'idle' | 'running' | 'completed' | 'failed';
  progress: number;
  logMessage?: string;
}

export interface GenerationResults {
  cadFloorPlanUrl: string;
  ifcFileUrl: string;
  totalVolumeM3: number;
  totalAreaSqm: number;
  elementCount: number;
  ifcVersion: string;
  totalCarbon: number;
  embodiedCarbon: number;
  operationalCarbon: number;
  estimatedCost: number;
  feasibilityScore: number;
  reductionTips: string[];
}

interface GenerationState {
  currentTemplate: GenerationTemplateType;
  inputs: Record<string, any>;
  isGenerating: boolean;
  status: 'idle' | 'running' | 'success' | 'error';
  steps: GenerationProgressStep[];
  results: GenerationResults | null;
  errorMessage: string;
  
  setTemplate: (template: GenerationTemplateType, defaultArea?: string) => void;
  setInputValue: (key: string, value: any) => void;
  resetStore: () => void;
  startGeneration: (projectId: string, areaSqm: number, floors: number, useLive: boolean) => Promise<void>;
}

const TEMPLATE_DEFAULT_INPUTS: Record<GenerationTemplateType, Record<string, any>> = {
  residential: {
    targetUnits: '120',
    parkingRatio: '1.2',
    targetEfficiency: '75',
    structureType: 'RC',
    style: 'modern',
  },
  logistics: {
    dockCount: '24',
    clearHeight: '10',
    floorLoad: '5',
    rampType: 'spiral',
    structureType: 'SRC',
  },
  'eco-office': {
    pvRatio: '35',
    insulationGrade: '1',
    leedTarget: 'gold',
    structureType: 'SC',
  },
};

const STEPS_BY_TEMPLATE: Record<GenerationTemplateType, string[]> = {
  residential: [
    '지적 경계 및 도로 조건 파싱 (Cadastral & Site Boundary Parsing)',
    '일조권 및 정북사선 법적 제한선 연산 (Sunlight & Boundary Regulations Solver)',
    '단위세대 및 평면 조합 레이아웃 설계 (Floor-Plan Combination Layout Engine)',
    '3D BIM IFC 벽체/구획 합성 (IFC Wall & Room BIM Synthesis)',
    '내재 탄소 배출량 & 수지분석 수렴 (LCA Carbon & ROI Synthesis)'
  ],
  logistics: [
    '화물차량 반경 및 하역 도크 배치 기획 (Logistics Vehicle Clearance & Dock Layout Planner)',
    '중하중 전용 스팬 가설 & 기둥 그리드 연산 (Heavy-Load Column Grid Solver)',
    '소방 방재 격리벽 및 최적 피난 동선 시뮬레이션 (Firewall & Evacuation Route Simulator)',
    '3D 물류 설비 결선 & BIM IFC 합성 (Logistics Facility IFC BIM Synthesis)',
    '냉동 설비 보강 및 에너지 소비 효율 수지 도출 (Logistics Energy Cost Optimizer)'
  ],
  'eco-office': [
    '연간 기후 기상 일조량 공공 데이터 로드 (Public Solar Radiation DB Ingestion)',
    '태양광 발전 패널 설치 한계 면적 모델링 (PV Solar Panel Boundary Modeler)',
    '자재 전수명주기 LCA 저탄소 시멘트 대체율 최적화 (Low-Carbon LCA Material Optimizer)',
    '친환경 기계 설비 연동 & 3D BIM IFC 합성 (Green Mech/Elec System BIM Synthesis)',
    'LEED 및 G-SEED 예비 인증 스코어보드 산출 (LEED Certification Scoreboard Analysis)'
  ]
};

export const useGenerationStore = create<GenerationState>((set, get) => ({
  currentTemplate: 'residential',
  inputs: { ...TEMPLATE_DEFAULT_INPUTS.residential },
  isGenerating: false,
  status: 'idle',
  steps: [],
  results: null,
  errorMessage: '',

  setTemplate: (template, defaultArea) => {
    set({
      currentTemplate: template,
      inputs: {
        ...TEMPLATE_DEFAULT_INPUTS[template],
        ...(defaultArea ? { areaSqm: defaultArea } : {}),
      },
      status: 'idle',
      steps: [],
      results: null,
      errorMessage: '',
    });
  },

  setInputValue: (key, value) => {
    set((state) => ({
      inputs: {
        ...state.inputs,
        [key]: value,
      },
    }));
  },

  resetStore: () => {
    const template = get().currentTemplate;
    set({
      inputs: { ...TEMPLATE_DEFAULT_INPUTS[template] },
      isGenerating: false,
      status: 'idle',
      steps: [],
      results: null,
      errorMessage: '',
    });
  },

  startGeneration: async (projectId, areaSqm, floors, useLive) => {
    const { currentTemplate, inputs } = get();
    const stepNames = STEPS_BY_TEMPLATE[currentTemplate];
    
    // Initialize steps
    const initialSteps: GenerationProgressStep[] = stepNames.map((name, i) => ({
      stepId: `step-${i}`,
      name,
      status: i === 0 ? 'running' : 'idle',
      progress: i === 0 ? 10 : 0,
      logMessage: i === 0 ? 'Engine loaded. Initiating dynamic telemetry analysis...' : undefined,
    }));

    set({
      isGenerating: true,
      status: 'running',
      steps: initialSteps,
      results: null,
      errorMessage: '',
    });

    try {
      // Simulate pipeline progression with incremental logs
      for (let i = 0; i < stepNames.length; i++) {
        // Step activation / run
        set((state) => {
          const nextSteps = [...state.steps];
          nextSteps[i] = {
            ...nextSteps[i],
            status: 'running',
            progress: 30,
            logMessage: `[RUNNING] Active computing thread dispatched for: ${stepNames[i]}`,
          };
          return { steps: nextSteps };
        });

        await new Promise((resolve) => setTimeout(resolve, 600));

        set((state) => {
          const nextSteps = [...state.steps];
          nextSteps[i] = {
            ...nextSteps[i],
            progress: 70,
            logMessage: `[PROCESSING] Compiling parameters... Area: ${areaSqm} sqm, Floors: ${floors} EA.`,
          };
          return { steps: nextSteps };
        });

        await new Promise((resolve) => setTimeout(resolve, 600));

        // Step completion
        set((state) => {
          const nextSteps = [...state.steps];
          nextSteps[i] = {
            ...nextSteps[i],
            status: 'completed',
            progress: 100,
            logMessage: `[SUCCESS] Compiled successfully. Ready for next dependency wiring.`,
          };
          if (i + 1 < nextSteps.length) {
            nextSteps[i + 1] = {
              ...nextSteps[i + 1],
              status: 'running',
              progress: 10,
              logMessage: `[INITIATIED] Pre-loading dependent pipeline step...`,
            };
          }
          return { steps: nextSteps };
        });
      }

      // Calculate dynamic results using parameter weights
      const structureCoef = 
        inputs.structureType === 'RC' ? 1.0 :
        inputs.structureType === 'SRC' ? 1.15 : 1.25;

      const styleCoef = 
        inputs.style === 'modern' ? 1.0 :
        inputs.style === 'minimal' ? 0.95 : 1.1;

      let estimatedCost = 0;
      let totalCarbon = 0;
      let embodiedCarbon = 0;
      let operationalCarbon = 0;
      let feasibilityScore = 80;
      let reductionTips: string[] = [];

      const totalArea = areaSqm * floors;

      if (currentTemplate === 'residential') {
        const units = Number(inputs.targetUnits) || 100;
        const efficiency = Number(inputs.targetEfficiency) || 75;
        
        estimatedCost = totalArea * 2200000 * structureCoef * styleCoef;
        embodiedCarbon = totalArea * 450 * structureCoef;
        operationalCarbon = totalArea * 200 * (1 - efficiency / 200);
        totalCarbon = embodiedCarbon + operationalCarbon;
        
        feasibilityScore = Math.min(100, Math.max(50, 85 + (efficiency * 0.15) - (units * 0.05)));
        reductionTips = [
          '고성능 외단열 및 고효율 창호 설계 적용 시 에너지 효율 12% 추가 상승 가능',
          '저탄소 철근 및 저탄소 시멘트 콘크리트 사양 결선 시 내재 탄소 15% 저감 가능',
          '주차 램프 배치 대안 적용을 통해 지하 토목 공사비의 약 8% 절감 가능',
        ];
      } else if (currentTemplate === 'logistics') {
        const docks = Number(inputs.dockCount) || 20;
        const load = Number(inputs.floorLoad) || 5;
        const rampMultiplier = inputs.rampType === 'spiral' ? 1.12 : 1.02;

        estimatedCost = totalArea * 1800000 * (1 + load * 0.04) * rampMultiplier * structureCoef;
        embodiedCarbon = totalArea * 500 * (1 + load * 0.02) * structureCoef;
        operationalCarbon = totalArea * 150 * (inputs.rampType === 'spiral' ? 1.05 : 1.0);
        totalCarbon = embodiedCarbon + operationalCarbon;

        feasibilityScore = Math.min(100, Math.max(50, 78 + (docks * 0.25) - (load * 0.4)));
        reductionTips = [
          '물류창고 내부 LED 센서 조명 전면 결선으로 운영 전력 20% 절감 가능',
          '도크 에어쉘 터널 밀폐 사양 적용을 통해 저온 보관 열손실 15% 방지',
          '강섬유 보강 콘크리트(SFRC) 토양 슬래브 적용 시 강재 량 단축으로 LCA 8% 저감',
        ];
      } else { // eco-office
        const pv = Number(inputs.pvRatio) || 30;
        const grade = Number(inputs.insulationGrade) || 1;
        const leedBonus = inputs.leedTarget === 'platinum' ? 9 : inputs.leedTarget === 'gold' ? 6 : 3;

        estimatedCost = totalArea * 2600000 * (1 + (11 - pv)/150) * (1.1 - grade * 0.02) * structureCoef;
        embodiedCarbon = totalArea * 400 * structureCoef;
        operationalCarbon = totalArea * 250 * (1 - pv / 120) * (0.85 + grade * 0.05);
        totalCarbon = embodiedCarbon + operationalCarbon;

        feasibilityScore = Math.min(100, Math.max(50, 80 + (pv * 0.2) - (grade * 1.5) + leedBonus));
        reductionTips = [
          '건물 전면 BIPV(건물일체형 태양광) 패널 결선을 통해 신재생 분담률 5% 추가 획득',
          '지열 히트펌프 냉난방 시스템 연동 시 화석연료 대체율 25% 달성 가능',
          '친환경 바닥재 및 천장재 조달 사양으로 실내 공기질 확보 및 탄소포집자재 결선',
        ];
      }

      set({
        status: 'success',
        results: {
          cadFloorPlanUrl: currentTemplate === 'residential' 
            ? 'https://via.placeholder.com/600x400?text=Residential+AI+Floor+Plan'
            : currentTemplate === 'logistics'
            ? 'https://via.placeholder.com/600x400?text=Logistics+Dock+Layout'
            : 'https://via.placeholder.com/600x400?text=Eco-Office+Solar+Irradiance+Map',
          ifcFileUrl: `https://mock-storage.propai.io/ifc/${projectId}-auto-synthesized.ifc`,
          totalVolumeM3: totalArea * 3.3,
          totalAreaSqm: totalArea,
          elementCount: floors * (currentTemplate === 'logistics' ? 80 : 160),
          ifcVersion: 'IFC4_ADD2',
          totalCarbon: Math.round(totalCarbon),
          embodiedCarbon: Math.round(embodiedCarbon),
          operationalCarbon: Math.round(operationalCarbon),
          estimatedCost: Math.round(estimatedCost),
          feasibilityScore: Math.round(feasibilityScore),
          reductionTips,
        },
      });

    } catch (err: any) {
      set({
        status: 'error',
        errorMessage: err.message || 'Generation failed.',
      });
      // Mark active steps as failed
      set((state) => ({
        steps: state.steps.map(step => 
          step.status === 'running' ? { ...step, status: 'failed', logMessage: 'Thread aborted.' } : step
        )
      }));
    } finally {
      set({ isGenerating: false });
    }
  }
}));
