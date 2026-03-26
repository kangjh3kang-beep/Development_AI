// PropAI v30.0 - 한국어 포맷 유틸리티

/** 원화 포맷 (예: ₩1,234,567,890) */
export function formatKRW(value: number): string {
  return new Intl.NumberFormat('ko-KR', {
    style: 'currency',
    currency: 'KRW',
    maximumFractionDigits: 0,
  }).format(value);
}

/** 억 단위 포맷 (예: 12.3억) */
export function formatBillionKRW(value: number): string {
  const billion = value / 1_0000_0000;
  if (billion >= 1) {
    return `${billion.toFixed(1)}억`;
  }
  const man = value / 1_0000;
  return `${man.toFixed(0)}만`;
}

/** 면적 포맷 (㎡ → 평 변환 포함) */
export function formatArea(sqm: number, unit: 'sqm' | 'pyeong' = 'sqm'): string {
  if (unit === 'pyeong') {
    const pyeong = sqm / 3.3058;
    return `${pyeong.toFixed(1)}평`;
  }
  return `${sqm.toLocaleString('ko-KR')}㎡`;
}

/** 퍼센트 포맷 */
export function formatPercent(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/** 날짜 포맷 (ISO → 한국어) */
export function formatDate(iso: string, format: 'date' | 'datetime' = 'date'): string {
  const date = new Date(iso);
  if (format === 'datetime') {
    return new Intl.DateTimeFormat('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  }
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

/** 상대 시간 (예: 3분 전, 2시간 전) */
export function formatRelativeTime(iso: string): string {
  const now = Date.now();
  const diff = now - new Date(iso).getTime();
  const seconds = Math.floor(diff / 1000);

  if (seconds < 60) return '방금 전';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}일 전`;
  const months = Math.floor(days / 30);
  return `${months}개월 전`;
}
