/**
 * 최소 ZIP 작성기(무압축·store 전용).
 *
 * 【왜 라이브러리를 안 쓰나】
 * 담을 것이 **PDF** 뿐이다. PDF 는 이미 내부적으로 압축돼 있어 deflate 를 걸어도 거의 줄지
 * 않는다. store 전용이면 압축 코드가 통째로 필요 없고, 의존성 추가 없이 **순수 함수**로
 * 끝난다 — 순수 함수라 픽스처 하나로 바이트 단위까지 잠글 수 있다.
 *
 * 【범위 — 정직 고지】
 * · store(무압축)만 지원한다. deflate·암호화·ZIP64 는 없다.
 * · 따라서 **개별 파일 4GB · 전체 4GB · 65,535개** 를 넘으면 만들지 않고 던진다
 *   (ZIP64 없이 그 이상을 쓰면 조용히 깨진 아카이브가 나온다 — 그건 침묵 실패다).
 * · 파일명은 UTF-8 로 쓰고 general purpose flag bit 11 을 세운다(한글 지번 파일명).
 */

/** CRC-32(IEEE 802.3) 테이블 — 최초 호출에서 한 번만 만든다. */
let CRC_TABLE: Uint32Array | null = null;
function crcTable(): Uint32Array {
  if (CRC_TABLE) return CRC_TABLE;
  const t = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[i] = c >>> 0;
  }
  CRC_TABLE = t;
  return t;
}

export function crc32(data: Uint8Array): number {
  const t = crcTable();
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) c = t[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export type ZipEntry = {
  /** 아카이브 안의 파일명. 경로 구분자·상위 참조는 호출측에서 걸러 온다. */
  name: string;
  data: Uint8Array;
};

/** 32비트 상한 — 넘으면 ZIP64 가 필요하고, 우리는 지원하지 않는다. */
const MAX_U32 = 0xffffffff;
const MAX_ENTRIES = 0xffff;

/**
 * 엔트리들을 store 방식 ZIP 한 덩어리로 만든다.
 *
 * 상한을 넘으면 **던진다** — 조용히 잘린 아카이브를 돌려주지 않는다.
 */
export function buildZip(entries: readonly ZipEntry[]): Uint8Array {
  if (entries.length > MAX_ENTRIES) {
    throw new RangeError(`ZIP 항목이 ${MAX_ENTRIES}개를 넘습니다(${entries.length}개) — 나눠서 받으세요.`);
  }
  const enc = new TextEncoder();
  const locals: Uint8Array[] = [];
  const centrals: Uint8Array[] = [];
  let offset = 0;

  for (const e of entries) {
    const name = enc.encode(e.name);
    const size = e.data.length;
    if (size > MAX_U32 || offset > MAX_U32) {
      throw new RangeError(`ZIP 크기가 4GB 상한을 넘습니다(${e.name}) — 나눠서 받으세요.`);
    }
    const crc = crc32(e.data);

    // Local file header (30바이트 고정부 + 파일명)
    const lh = new Uint8Array(30 + name.length);
    const lv = new DataView(lh.buffer);
    lv.setUint32(0, 0x04034b50, true); // signature
    lv.setUint16(4, 20, true); // version needed (2.0)
    lv.setUint16(6, 0x0800, true); // flag: bit 11 = 파일명 UTF-8
    lv.setUint16(8, 0, true); // method 0 = store
    lv.setUint16(10, 0, true); // mod time — 고정값(재현 가능한 산출물)
    lv.setUint16(12, 0x21, true); // mod date — 1980-01-01
    lv.setUint32(14, crc, true);
    lv.setUint32(18, size, true); // compressed
    lv.setUint32(22, size, true); // uncompressed
    lv.setUint16(26, name.length, true);
    lv.setUint16(28, 0, true); // extra length
    lh.set(name, 30);

    // Central directory header (46바이트 고정부 + 파일명)
    const ch = new Uint8Array(46 + name.length);
    const cv = new DataView(ch.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true); // version made by
    cv.setUint16(6, 20, true); // version needed
    cv.setUint16(8, 0x0800, true);
    cv.setUint16(10, 0, true);
    cv.setUint16(12, 0, true);
    cv.setUint16(14, 0x21, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, size, true);
    cv.setUint32(24, size, true);
    cv.setUint16(28, name.length, true);
    cv.setUint16(30, 0, true); // extra
    cv.setUint16(32, 0, true); // comment
    cv.setUint16(34, 0, true); // disk number
    cv.setUint16(36, 0, true); // internal attrs
    cv.setUint32(38, 0, true); // external attrs
    cv.setUint32(42, offset, true); // local header offset
    ch.set(name, 46);

    locals.push(lh, e.data);
    centrals.push(ch);
    offset += lh.length + size;
  }

  const centralSize = centrals.reduce((n, c) => n + c.length, 0);
  const eocd = new Uint8Array(22);
  const ev = new DataView(eocd.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(4, 0, true); // disk
  ev.setUint16(6, 0, true); // disk with central dir
  ev.setUint16(8, entries.length, true);
  ev.setUint16(10, entries.length, true);
  ev.setUint32(12, centralSize, true);
  ev.setUint32(16, offset, true); // central dir offset
  ev.setUint16(20, 0, true); // comment length

  const total = offset + centralSize + eocd.length;
  const out = new Uint8Array(total);
  let at = 0;
  for (const part of [...locals, ...centrals, eocd]) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

/**
 * 파일명으로 쓸 수 없는 문자를 지운다. 경로 구분자·상위 참조를 **반드시** 없앤다 —
 * 그대로 두면 아카이브를 푸는 쪽에서 엉뚱한 경로에 쓰인다(zip slip).
 */
export function safeFileName(raw: string, fallback: string): string {
  const cleaned = raw
    .replace(/[/\\]/g, "_")
    .replace(/\.{2,}/g, "_")
    // 제어문자 + 윈도 금지문자만 지운다.
    // ★`[ -<>…]` 처럼 쓰면 공백~`<` 가 **범위**로 해석돼 **숫자까지 지워진다**(지번 소실).
    .replace(/[\x00-\x1f<>:"|?*]/g, "")
    .trim()
    .slice(0, 100);
  return cleaned || fallback;
}

/** 같은 이름이 이미 있으면 `_2`, `_3` … 을 붙인다(덮어쓰기·중복 엔트리 방지). */
export function uniqueName(name: string, taken: Set<string>): string {
  if (!taken.has(name)) {
    taken.add(name);
    return name;
  }
  const dot = name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot) : "";
  for (let i = 2; ; i++) {
    const candidate = `${stem}_${i}${ext}`;
    if (!taken.has(candidate)) {
      taken.add(candidate);
      return candidate;
    }
  }
}
