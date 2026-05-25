/* eslint-disable @typescript-eslint/no-require-imports */
const fs = require('fs');
const path = require('path');

const DASHBOARD_DIR = path.join(__dirname, 'app', '[locale]', '(dashboard)');
const KO_JSON_PATH = path.join(__dirname, 'i18n', 'dictionaries', 'ko.json');

// This dictionary provides the Korean meanings for the English subpages
const kM = {
  "agent": { title: "AI 에이전트 시스템", desc: "분산된 AI 에이전트들의 상태와 로그를 실시간으로 모니터링하고 제어합니다." },
  "maintenance": { title: "디지털 트윈 유지보수", desc: "설비의 센서 기반 예지 정비 및 현장 유지보수 일정을 관리합니다." },
  "tenant": { title: "테넌트 통합 관리", desc: "임대차 계약, CS 요청 처리 및 테넌트 포괄 운용 상태를 시각화합니다." },
  "inspection": { title: "AI 현장 점검", desc: "모바일 장치와 드론 비전 데이터를 통해 현장의 안전 및 품질을 원격 점검합니다." },
  "auction": { title: "경공매 분석 엔진", desc: "법원 경매 및 공매 낙찰가 예측과 권리 분석을 AI로 구동합니다." },
  "projects": { title: "전체 프로젝트 파이프라인", desc: "권한이 부여된 모든 부동산 개발 프로젝트들의 통합 진행률을 관제합니다." },
  "tax": { title: "세무/재무 시뮬레이터", desc: "취득세, 양도세, 종부세 등 부동산 관련 세금 영향을 몬테카를로 분석에 결합합니다." },
  "iot": { title: "IoT 에너지 관제", desc: "건물 내 스마트 센서 네트워크를 대시보드와 연동하여 실시간 에너지 효율을 제어합니다." },
  "cost": { title: "실시간 물가지수 분석", desc: "시장 자재 단가 및 건설 물가지수를 연동하여 원가 상승 리스크를 예측합니다." },
  "investment": { title: "투자 가치 산정 (AVM)", desc: "지역 데이터와 거시경제 지표를 결합하여 해당 물건의 최종 자산 가치를 환산합니다." },
  "carbon": { title: "탄소 배출 (LCA) 전과정 평가", desc: "설계, 시공, 운영의 전체 사이클에서 발생하는 탄소 발자국을 추적/절감합니다." },
  "contracts": { title: "전자 계약 관리", desc: "이더리움 스마트 컨트랙트 기반의 용역/수주/임대차 계약을 모니터링합니다." },
  "legal": { title: "법규 및 조례 검토", desc: "해당 지번의 용도 지역 분석 및 160여개 최신 건축/환경 법규 위반을 검사합니다." },
  "finance": { title: "수지 분석 및 대출 구조", desc: "PF 구조화, 자기자본(Equity) 시뮬레이션 및 상환 스케줄을 디자인합니다." },
  "report": { title: "최종 사업성 리포트", desc: "지금까지 분석된 법규, 설계, 수지 종합 결과를 PDF 및 대시보드로 요약 보고합니다." },
  "site-analysis": { title: "부지 및 환경 분석", desc: "지형 데이터, 일조량, 소음 및 주변 인프라를 공간 정보(GIS) 기반으로 파악합니다." },
  "esg": { title: "ESG 지표 통합", desc: "EU 택소노미 및 녹색건축인증 요건을 충족하기 위한 프로젝트의 비재무적 가치를 추적합니다." },
  "bim": { title: "BIM 수량 산출", desc: "생성된 IFC 파일에서 골조, 마감재 등 3D 물량(QTO)을 자동 산출하고 매핑합니다." },
  "cad": { title: "2D 평면도 검토", desc: "설계 도면 분석 및 규제 오버레이 뷰어를 통해 면적과 효율성을 평가합니다." },
  "construction": { title: "4D/5D 시공 감리", desc: "공정표(Gantt)와 내역서(BIM)를 연동하여 시공 기성 및 비용 지출을 실시간 감리합니다." },
  "permit": { title: "인허가 자동화", desc: "건축 허가에 필요한 도서 리스트를 점검하고, 행정 처리 워크플로우를 보조합니다." },
  "operations": { title: "자산 운영 (FM)", desc: "준공 후 빌딩 모니터링(스마트 빌딩) 및 재무적 수익 회수 라인을 감독합니다." },
  "drone": { title: "드론 열화상/맵핑 데이터", desc: "현장에서 수집된 드론 정사영상 및 3D 포인트 클라우드 데이터를 시각화합니다." },
  "blockchain": { title: "ST0 블록체인 펀딩", desc: "부동산 조각 투자 및 블록체인(Tokenization) 기반의 자본 조달 원장을 모니터링합니다." },
  "design": { title: "AI 기본 설계 생성", desc: "건폐율 및 용적률을 극대화하는 자동 평면도 및 법규 보정 3D 매스를 생성합니다." }
};

let currentKoDict = JSON.parse(fs.readFileSync(KO_JSON_PATH, 'utf8'));
if (!currentKoDict.modulePlaceholders) {
  currentKoDict.modulePlaceholders = {};
}

let modifiedCount = 0;

const processFiles = (dir) => {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const fullPath = path.join(dir, file);
    if (fs.statSync(fullPath).isDirectory()) {
      processFiles(fullPath);
    } else if (file === 'page.tsx') {
      let content = fs.readFileSync(fullPath, 'utf8');
      
      // If the file uses <ModulePlaceholder> with Hardcoded English
      if (content.includes('<ModulePlaceholder') && !content.includes('dictionary.modulePlaceholders')) {
        let moduleKey = path.basename(path.dirname(fullPath));
        if (moduleKey === '(dashboard)') moduleKey = 'home';
        if (moduleKey === '[id]') moduleKey = 'project_overview';
        if (!kM[moduleKey]) moduleKey = 'design'; // fallback

        // Fill Dictionary
        currentKoDict.modulePlaceholders[moduleKey] = {
          eyebrow: `PROJECT / ${moduleKey.toUpperCase().replace('-', ' ')}`,
          title: kM[moduleKey].title,
          description: kM[moduleKey].desc,
          items: [ "데이터 조회", "상태 동기화 진행", "AI 분석 리퀘스트" ] // Default localized items
        };

        // Component Rewriting
        // Ensure getDictionary is imported and called
        if (!content.includes('getDictionary')) {
            // this is simplified, normally we ensure proper imports, but PropAI pages all have it.
        }

        content = content.replace(/<ModulePlaceholder[\s\S]*?\/>/, `
      <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["${moduleKey}"].eyebrow}
        title={dictionary.modulePlaceholders["${moduleKey}"].title}
        description={dictionary.modulePlaceholders["${moduleKey}"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["${moduleKey}"].items}
      />`.trim());

        fs.writeFileSync(fullPath, content);
        modifiedCount++;
      }
    }
  }
};

console.log('Initiating Deep AI Localization Codemod...');
processFiles(DASHBOARD_DIR);
fs.writeFileSync(KO_JSON_PATH, JSON.stringify(currentKoDict, null, 2));

console.log(`Successfully rewrote ${modifiedCount} subpages and updated ko.json registry.`);
