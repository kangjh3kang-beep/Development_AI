// PropAI v30.0 - 검증 유틸리티

/** 이메일 유효성 검증 */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/** PNU (필지고유번호) 19자리 검증 */
export function isValidPNU(pnu: string): boolean {
  return /^\d{19}$/.test(pnu);
}

/** 한국 전화번호 검증 */
export function isValidPhoneKR(phone: string): boolean {
  return /^01[016789]-?\d{3,4}-?\d{4}$/.test(phone);
}

/** Ethereum 주소 검증 */
export function isValidEthAddress(address: string): boolean {
  return /^0x[0-9a-fA-F]{40}$/.test(address);
}

/** 위도 범위 검증 */
export function isValidLatitude(lat: number): boolean {
  return lat >= -90 && lat <= 90;
}

/** 경도 범위 검증 */
export function isValidLongitude(lng: number): boolean {
  return lng >= -180 && lng <= 180;
}

/** 한국 좌표 범위 검증 (대략적) */
export function isInKoreaBounds(lat: number, lng: number): boolean {
  return lat >= 33.0 && lat <= 38.6 && lng >= 124.6 && lng <= 131.9;
}
