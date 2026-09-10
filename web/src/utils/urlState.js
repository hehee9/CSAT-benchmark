/**
 * @file urlState.js
 * @brief URL 쿼리 기반 대시보드 공유 상태 유틸리티
 */

const DEFAULT_EXAM = 'csat-2026'
const DEFAULT_MODE = 'default'
const DEFAULT_SCORE_BASIS = 'raw'
const VALID_MODES = new Set(['default', 'easy'])
const VALID_SCORE_BASES = new Set(['normalized', 'raw'])

/**
 * @brief URL 검색 문자열을 URLSearchParams로 변환
 * @param {string|undefined} search - 검색 문자열
 * @return {URLSearchParams} URL 파라미터
 */
function _getSearchParams(search) {
  if (search !== undefined) return new URLSearchParams(search)
  if (typeof window === 'undefined') return new URLSearchParams()
  return new URLSearchParams(window.location.search)
}

/**
 * @brief 허용된 열거형 값 추출
 * @param {string|null} value - 원본 값
 * @param {Set<string>} validSet - 허용 값 집합
 * @param {string} fallback - 기본값
 * @return {string} 검증된 값
 */
function _getEnumValue(value, validSet, fallback) {
  return value && validSet.has(value) ? value : fallback
}

/**
 * @brief 대시보드 초기 URL 상태 파싱
 * @param {string|undefined} search - 테스트용 검색 문자열
 * @return {{exam: string, mode: string, scoreBasis: string}} 공유할 상태
 */
export function getDashboardQueryState(search) {
  const params = _getSearchParams(search)

  return {
    exam: params.get('exam') || DEFAULT_EXAM,
    mode: _getEnumValue(params.get('mode'), VALID_MODES, DEFAULT_MODE),
    scoreBasis: _getEnumValue(params.get('scoreBasis'), VALID_SCORE_BASES, DEFAULT_SCORE_BASIS)
  }
}

/**
 * @brief 대시보드 공유 상태를 현재 URL에 저장
 * @param {{exam?: string, mode?: string, scoreBasis?: string}} state - 저장할 공유 상태
 * @return {string|null} 반영된 URL 또는 브라우저가 없으면 null
 */
export function replaceDashboardQueryState(state) {
  if (typeof window === 'undefined') return null

  const url = new URL(window.location.href)
  url.search = ''
  const values = {
    exam: state.exam || DEFAULT_EXAM,
    mode: _getEnumValue(state.mode, VALID_MODES, DEFAULT_MODE),
    scoreBasis: _getEnumValue(state.scoreBasis, VALID_SCORE_BASES, DEFAULT_SCORE_BASIS)
  }

  Object.entries(values).forEach(([key, value]) => {
    url.searchParams.set(key, value)
  })

  window.history.replaceState({}, '', url)
  return url.toString()
}
