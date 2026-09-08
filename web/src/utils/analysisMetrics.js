/**
 * @file analysisMetrics.js
 * @brief 상세 분석 산점도 지표 정의 및 값 변환
 */

/**
 * @brief 상세 분석에서 선택할 수 있는 지표
 */
export const ANALYSIS_METRICS = Object.freeze({
  score: Object.freeze({
    id: 'score',
    field: 'score',
    scale: 'linear',
    direction: 'higher',
    labelKey: 'analysis.metrics.score',
    unitKey: 'analysis.units.points'
  }),
  cost: Object.freeze({
    id: 'cost',
    field: 'totalCost',
    scale: 'log',
    direction: 'lower',
    labelKey: 'analysis.metrics.cost',
    unitKey: 'analysis.units.dollars'
  }),
  tokens: Object.freeze({
    id: 'tokens',
    field: 'totalTokens',
    scale: 'log',
    direction: 'lower',
    labelKey: 'analysis.metrics.tokens',
    unitKey: 'analysis.units.tokens'
  }),
  time: Object.freeze({
    id: 'time',
    field: 'estimatedSeconds',
    scale: 'log',
    direction: 'lower',
    labelKey: 'analysis.metrics.time',
    unitKey: 'analysis.units.hours'
  })
})

/** @brief 상세 분석 지표 식별자 목록 */
export const ANALYSIS_METRIC_IDS = Object.freeze(Object.keys(ANALYSIS_METRICS))

/** @brief 상세 분석 지표 기본 선택값 */
export const DEFAULT_ANALYSIS_X = 'cost'
export const DEFAULT_ANALYSIS_Y = 'score'

/**
 * @brief 상세 분석 지표 식별자 검증
 * @param {string} metric - 지표 식별자
 * @return {boolean} 허용된 지표 여부
 */
export function isAnalysisMetric(metric) {
  return Object.hasOwn(ANALYSIS_METRICS, metric)
}

/**
 * @brief 상세 분석 지표 정의 반환
 * @param {string} metric - 지표 식별자
 * @return {Object} 지표 정의
 */
export function getAnalysisMetric(metric) {
  return ANALYSIS_METRICS[metric]
}

/**
 * @brief 지표의 로그 축 여부 반환
 * @param {string} metric - 지표 식별자
 * @return {boolean} 로그 축 여부
 */
export function isAnalysisMetricLog(metric) {
  return getAnalysisMetric(metric).scale === 'log'
}

/**
 * @brief 비용·토큰·시간의 방향성 반환
 * @param {string} metric - 지표 식별자
 * @return {'higher'|'lower'} 유리한 방향
 */
export function getAnalysisMetricDirection(metric) {
  return getAnalysisMetric(metric).direction
}

/**
 * @brief 비용 분석 행에서 선택 지표 값 추출
 * @param {Object} row - getCostData() 결과 행
 * @param {string} metric - 지표 식별자
 * @return {number|null} 유효한 지표 값 또는 미상
 */
export function getAnalysisMetricValue(row, metric) {
  const value = row[getAnalysisMetric(metric).field]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * @brief 선택한 두 축에서 그릴 수 있는 행만 선택
 * @param {Array} rows - getCostData() 결과 행
 * @param {string} xMetric - X축 지표
 * @param {string} yMetric - Y축 지표
 * @return {Array} xValue·yValue를 포함한 유효 행
 */
export function getAnalysisPoints(rows, xMetric, yMetric) {
  return rows.flatMap(row => {
    const xValue = getAnalysisMetricValue(row, xMetric)
    const yValue = getAnalysisMetricValue(row, yMetric)
    const hasInvalidLogValue = (isAnalysisMetricLog(xMetric) && !(xValue > 0)) ||
      (isAnalysisMetricLog(yMetric) && !(yValue > 0))

    if (xValue === null || yValue === null || hasInvalidLogValue) return []
    return [{ ...row, xValue, yValue }]
  })
}

/**
 * @brief 지표 값을 현지화된 문자열로 변환
 * @param {string} metric - 지표 식별자
 * @param {number|null} value - 지표 값
 * @param {string} locale - 숫자 표시 언어
 * @return {string} 숫자 문자열(비용은 달러 기호 포함)
 */
export function formatAnalysisMetricValue(metric, value, locale = 'ko-KR') {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'

  if (metric === 'cost') {
    return `$${value.toLocaleString(locale, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`
  }

  if (metric === 'tokens') {
    return `${value.toLocaleString(locale, { maximumFractionDigits: 0 })}`
  }

  if (metric === 'time') {
    const totalMinutes = Math.round(value / 60)
    const hours = Math.floor(totalMinutes / 60)
    const minutes = totalMinutes % 60
    return locale.startsWith('ko') ? `${hours}시간 ${minutes}분` : `${hours}h ${minutes}m`
  }

  return `${value.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`
}
