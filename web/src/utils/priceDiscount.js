/**
 * @file priceDiscount.js
 * @brief 기간 한정 할인 단가 정규화와 적용 기간 판정
 */

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/**
 * @brief 백만 토큰당 단가로 쓸 수 있는 값인지 확인
 * @param {*} value - 검사할 값
 * @return {boolean} 0 이상 유한수 여부
 */
function _isPriceValue(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

/**
 * @brief 실제로 존재하는 YYYY-MM-DD 날짜인지 확인
 * @param {*} value - 검사할 값
 * @return {boolean} 유효한 날짜 문자열 여부
 */
function _isIsoDate(value) {
  if (typeof value !== 'string' || !ISO_DATE_PATTERN.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}

/**
 * @brief 날짜를 브라우저 현지 기준 YYYY-MM-DD 문자열로 변환
 * @param {Date} date - 변환할 시각
 * @return {string} 현지 날짜 문자열
 */
function _toLocalIsoDate(date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/**
 * @brief 결과 데이터의 할인 정보를 검증해 정규화
 * @param {*} discount - price.discount 원본 값
 * @return {Object|null} { input, output, start, end } 또는 무효 시 null
 */
export function normalizePriceDiscount(discount) {
  if (!discount || typeof discount !== 'object') return null
  const { input, output, start, end } = discount
  if (!_isPriceValue(input) || !_isPriceValue(output)) return null
  if (!_isIsoDate(start) || !_isIsoDate(end) || start > end) return null
  return { input, output, start, end }
}

/**
 * @brief 오늘이 할인 기간(시작·종료일 포함)에 속할 때만 할인 정보 반환
 * @param {Object|null} discount - normalizePriceDiscount() 결과
 * @param {Date} now - 기준 시각 (기본값: 현재)
 * @return {Object|null} 적용 중인 할인 또는 null
 */
export function getActivePriceDiscount(discount, now = new Date()) {
  if (!discount) return null
  const today = _toLocalIsoDate(now)
  return discount.start <= today && today <= discount.end ? discount : null
}

/**
 * @brief 할인 종료일을 월/일 형식으로 변환
 * @param {string} end - YYYY-MM-DD 종료일
 * @return {string} 예: '11/30'
 */
export function formatDiscountEndDate(end) {
  const [, month, day] = end.split('-').map(Number)
  return `${month}/${day}`
}
