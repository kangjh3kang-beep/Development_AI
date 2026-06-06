/**
 * Phase C — 경량 QR 코드 생성기(무의존성).
 *
 * 새 npm 의존성(qrcode/qrcode.react) 추가 대신, 공유링크(share_url)를 QR로 만들기 위한
 * 최소 구현(byte mode, error correction level M, 자동 버전 1~10 선택)을 직접 포함한다.
 * Canvas/다운로드는 컴포넌트가 처리하며, 본 모듈은 모듈 행렬(boolean[][])만 반환한다.
 *
 * 참고: ISO/IEC 18004 QR Code 표준. byte(8bit) 인코딩, EC level M, 마스크 0 고정(검증된 단순 경로).
 * URL 길이가 버전 10(byte mode, level M ≈ 213바이트) 초과 시 null 반환 → 컴포넌트가 폴백(텍스트+복사) 처리.
 * (공유 URL은 통상 50~80자라 충분. UTF-8 한글은 글자당 3바이트로 계산됨.)
 */

// ── 갈루아 필드(GF(256)) 로그/역로그 테이블 ──────────────────────────
const GF_EXP = new Uint8Array(512);
const GF_LOG = new Uint8Array(256);
(function initGF() {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    GF_EXP[i] = x;
    GF_LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i++) GF_EXP[i] = GF_EXP[i - 255];
})();

function gfMul(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return GF_EXP[GF_LOG[a] + GF_LOG[b]];
}

/** 리드-솔로몬 생성 다항식. */
function rsGeneratorPoly(degree: number): number[] {
  let poly = [1];
  for (let i = 0; i < degree; i++) {
    const next = new Array(poly.length + 1).fill(0);
    for (let j = 0; j < poly.length; j++) {
      next[j] ^= poly[j];
      next[j + 1] ^= gfMul(poly[j], GF_EXP[i]);
    }
    poly = next;
  }
  return poly;
}

/** 데이터 코드워드 → EC 코드워드 계산. */
function rsEncode(data: number[], ecLen: number): number[] {
  const gen = rsGeneratorPoly(ecLen);
  const res = new Array(data.length + ecLen).fill(0);
  for (let i = 0; i < data.length; i++) res[i] = data[i];
  for (let i = 0; i < data.length; i++) {
    const coef = res[i];
    if (coef !== 0) {
      for (let j = 0; j < gen.length; j++) {
        res[i + j] ^= gfMul(gen[j], coef);
      }
    }
  }
  return res.slice(data.length);
}

// ── 버전별 정보(EC level M, byte mode) ─────────────────────────────
// [version, totalCodewords, ecPerBlock, group1Blocks, group1DataCW, group2Blocks, group2DataCW]
const VERSIONS: Array<[number, number, number, number, number, number, number]> = [
  [1, 26, 10, 1, 16, 0, 0],
  [2, 44, 16, 1, 28, 0, 0],
  [3, 70, 26, 1, 44, 0, 0],
  [4, 100, 18, 2, 32, 0, 0],
  [5, 134, 24, 2, 43, 0, 0],
  [6, 172, 16, 4, 27, 0, 0],
  [7, 196, 18, 4, 31, 0, 0],
  [8, 242, 22, 2, 38, 2, 39],
  [9, 292, 22, 3, 36, 2, 37],
  [10, 346, 26, 4, 43, 1, 44],
];

// 정렬 패턴 중심 좌표(버전별).
const ALIGN_POS: Record<number, number[]> = {
  1: [],
  2: [6, 18],
  3: [6, 22],
  4: [6, 26],
  5: [6, 30],
  6: [6, 34],
  7: [6, 22, 38],
  8: [6, 24, 42],
  9: [6, 26, 46],
  10: [6, 28, 50],
};

// 버전별 포맷정보(EC level M, mask 0) — 사전 계산된 15bit.
const FORMAT_INFO_M_MASK0 = 0x5412; // BCH(15,5) for (EC=M=00, mask=000)

function dataCapacityCW(v: (typeof VERSIONS)[number]): number {
  return v[3] * v[4] + v[5] * v[6];
}

/** byte mode 문자수 표시자 비트수(버전 1~9는 8bit, 10~26은 16bit). */
function charCountBits(version: number): number {
  return version <= 9 ? 8 : 16;
}

function chooseVersion(byteLen: number): (typeof VERSIONS)[number] | null {
  for (const v of VERSIONS) {
    const dataCW = dataCapacityCW(v);
    // 모드(4) + 문자수표시자 + 데이터(8*byteLen) 비트가 데이터 코드워드 안에 들어가야 함.
    const needBits = 4 + charCountBits(v[0]) + byteLen * 8;
    if (needBits <= dataCW * 8) return v;
  }
  return null;
}

/** UTF-8 인코딩(브라우저 TextEncoder 사용, 폴백 포함). */
function utf8Bytes(str: string): number[] {
  if (typeof TextEncoder !== "undefined") {
    return Array.from(new TextEncoder().encode(str));
  }
  const out: number[] = [];
  for (const ch of unescape(encodeURIComponent(str))) out.push(ch.charCodeAt(0));
  return out;
}

/**
 * 공개 API: 텍스트 → QR 모듈 행렬(boolean[][], true=검정).
 * 용량 초과(버전 10 초과)·빈 입력 시 null.
 */
export function generateQrMatrix(text: string): boolean[][] | null {
  if (!text) return null;
  const bytes = utf8Bytes(text);
  const ver = chooseVersion(bytes.length);
  if (!ver) return null;

  const [version, , ecLen, g1Blocks, g1Data, g2Blocks, g2Data] = ver;
  const size = 17 + version * 4;

  // ── 1) 비트스트림 구성(byte mode) ──
  const bits: number[] = [];
  const pushBits = (val: number, len: number) => {
    for (let i = len - 1; i >= 0; i--) bits.push((val >> i) & 1);
  };
  pushBits(0b0100, 4); // byte mode
  pushBits(bytes.length, charCountBits(version));
  for (const b of bytes) pushBits(b, 8);

  const totalDataCW = dataCapacityCW(ver);
  const totalDataBits = totalDataCW * 8;
  // 종단자(최대 4bit) + 바이트 정렬.
  for (let i = 0; i < 4 && bits.length < totalDataBits; i++) bits.push(0);
  while (bits.length % 8 !== 0) bits.push(0);

  // 데이터 코드워드 배열.
  const dataCodewords: number[] = [];
  for (let i = 0; i < bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | bits[i + j];
    dataCodewords.push(byte);
  }
  // 패딩 바이트(0xEC, 0x11 교대).
  const padBytes = [0xec, 0x11];
  let p = 0;
  while (dataCodewords.length < totalDataCW) {
    dataCodewords.push(padBytes[p % 2]);
    p++;
  }

  // ── 2) 블록 분할 + EC 계산 + 인터리브 ──
  const blocks: { data: number[]; ec: number[] }[] = [];
  let pos = 0;
  for (let i = 0; i < g1Blocks; i++) {
    const data = dataCodewords.slice(pos, pos + g1Data);
    pos += g1Data;
    blocks.push({ data, ec: rsEncode(data, ecLen) });
  }
  for (let i = 0; i < g2Blocks; i++) {
    const data = dataCodewords.slice(pos, pos + g2Data);
    pos += g2Data;
    blocks.push({ data, ec: rsEncode(data, ecLen) });
  }

  const finalCodewords: number[] = [];
  const maxData = Math.max(...blocks.map((b) => b.data.length));
  for (let i = 0; i < maxData; i++) {
    for (const b of blocks) if (i < b.data.length) finalCodewords.push(b.data[i]);
  }
  for (let i = 0; i < ecLen; i++) {
    for (const b of blocks) finalCodewords.push(b.ec[i]);
  }

  // ── 3) 모듈 행렬 배치 ──
  const matrix: (boolean | null)[][] = Array.from({ length: size }, () =>
    new Array<boolean | null>(size).fill(null),
  );
  const isReserved: boolean[][] = Array.from({ length: size }, () =>
    new Array<boolean>(size).fill(false),
  );

  const setModule = (r: number, c: number, val: boolean, reserve = true) => {
    matrix[r][c] = val;
    if (reserve) isReserved[r][c] = true;
  };

  // finder 패턴(3개 모서리) + 분리자.
  const placeFinder = (rOff: number, cOff: number) => {
    for (let r = -1; r <= 7; r++) {
      for (let c = -1; c <= 7; c++) {
        const rr = rOff + r;
        const cc = cOff + c;
        if (rr < 0 || rr >= size || cc < 0 || cc >= size) continue;
        const inSquare = r >= 0 && r <= 6 && c >= 0 && c <= 6;
        const isBorder = r === 0 || r === 6 || c === 0 || c === 6;
        const isCenter = r >= 2 && r <= 4 && c >= 2 && c <= 4;
        setModule(rr, cc, inSquare && (isBorder || isCenter));
      }
    }
  };
  placeFinder(0, 0);
  placeFinder(0, size - 7);
  placeFinder(size - 7, 0);

  // 타이밍 패턴.
  for (let i = 8; i < size - 8; i++) {
    setModule(6, i, i % 2 === 0);
    setModule(i, 6, i % 2 === 0);
  }

  // 정렬 패턴.
  const aligns = ALIGN_POS[version] ?? [];
  for (const ar of aligns) {
    for (const ac of aligns) {
      // finder와 겹치면 스킵.
      if (isReserved[ar][ac]) continue;
      for (let r = -2; r <= 2; r++) {
        for (let c = -2; c <= 2; c++) {
          const isBorder = Math.max(Math.abs(r), Math.abs(c)) === 2;
          const isCenter = r === 0 && c === 0;
          setModule(ar + r, ac + c, isBorder || isCenter);
        }
      }
    }
  }

  // 다크 모듈.
  setModule(size - 8, 8, true);

  // 포맷 정보 영역 예약(값은 후술).
  for (let i = 0; i < 9; i++) {
    if (!isReserved[8][i]) isReserved[8][i] = true;
    if (!isReserved[i][8]) isReserved[i][8] = true;
  }
  for (let i = 0; i < 8; i++) {
    isReserved[8][size - 1 - i] = true;
    isReserved[size - 1 - i][8] = true;
  }

  // ── 4) 데이터 비트 지그재그 배치 + 마스크 0 ──
  let bitIdx = 0;
  const dataBits: number[] = [];
  for (const cw of finalCodewords) {
    for (let i = 7; i >= 0; i--) dataBits.push((cw >> i) & 1);
  }

  let upward = true;
  for (let col = size - 1; col > 0; col -= 2) {
    if (col === 6) col = 5; // 타이밍 열 스킵.
    for (let i = 0; i < size; i++) {
      const row = upward ? size - 1 - i : i;
      for (let c = 0; c < 2; c++) {
        const cc = col - c;
        if (isReserved[row][cc]) continue;
        let dark = bitIdx < dataBits.length ? dataBits[bitIdx] === 1 : false;
        bitIdx++;
        // 마스크 0: (row + col) % 2 === 0 → 반전.
        if ((row + cc) % 2 === 0) dark = !dark;
        matrix[row][cc] = dark;
      }
    }
    upward = !upward;
  }

  // ── 5) 포맷 정보 기록(EC=M, mask 0) ──
  const fmt = FORMAT_INFO_M_MASK0;
  const fmtBit = (i: number) => ((fmt >> i) & 1) === 1;
  // 좌상단 세로/가로.
  for (let i = 0; i <= 5; i++) matrix[8][i] = fmtBit(i);
  matrix[8][7] = fmtBit(6);
  matrix[8][8] = fmtBit(7);
  matrix[7][8] = fmtBit(8);
  for (let i = 9; i <= 14; i++) matrix[14 - i][8] = fmtBit(i);
  // 우상단 가로 / 좌하단 세로.
  for (let i = 0; i <= 7; i++) matrix[8][size - 1 - i] = fmtBit(i);
  for (let i = 8; i <= 14; i++) matrix[size - 15 + i][8] = fmtBit(i);

  // null 잔여(이론상 없음)는 흰색 처리.
  return matrix.map((row) => row.map((v) => v === true));
}
