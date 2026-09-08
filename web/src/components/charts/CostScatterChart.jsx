/**
 * @file CostScatterChart.jsx
 * @brief 상세 분석 지표 산점도 차트 컴포넌트
 */

import { useEffect, useMemo, useState } from 'react'
import {
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'
import { useTranslation } from 'react-i18next'
import { getModelColor } from '@/utils/colorUtils'
import { useTheme } from '@/hooks/useTheme'
import { useExportImage, README_EXPORT_WIDTH } from '@/hooks/useExportImage'
import { BenchmarkNote, ExportButton } from '@/components/common'
import { formatModelDisplayName } from '@/utils/modelMeta'
import {
  ANALYSIS_METRIC_IDS,
  DEFAULT_ANALYSIS_X,
  DEFAULT_ANALYSIS_Y,
  formatAnalysisMetricValue,
  getAnalysisMetric,
  getAnalysisMetricDirection,
  getAnalysisPoints,
  isAnalysisMetricLog
} from '@/utils/analysisMetrics'

const COST_POINT_RADIUS = 7
const EXPORT_LABEL_GAP = 6
const EXPORT_LABEL_BOUNDARY_PADDING = 4
const EXPORT_LABEL_COLLISION_PADDING = 2
const EXPORT_LABEL_POINT_PADDING = 3
const EXPORT_LABEL_DEFAULT_ANGLE = -90
const EXPORT_LABEL_COARSE_STEP = 2
const EXPORT_LABEL_FINE_STEP = 0.1
const EXPORT_LABEL_FINE_RANGE = 2
const EXPORT_LABEL_MAX_PASSES = 3

/**
 * @brief 각도를 0~360도 범위로 정규화
 * @param {number} angle - 각도
 * @return {number} 정규화된 각도
 */
function _normalizeAngle(angle) {
  return ((angle % 360) + 360) % 360
}

/**
 * @brief 두 각도 사이의 최소 차이 계산
 * @param {number} first - 첫 번째 각도
 * @param {number} second - 두 번째 각도
 * @return {number} 0~180도 범위의 각도 차이
 */
function _getAngleDifference(first, second) {
  const difference = Math.abs(_normalizeAngle(first) - _normalizeAngle(second))
  return Math.min(difference, 360 - difference)
}

/**
 * @brief 기본 위쪽 위치에서 떨어진 최소 각도 계산
 * @param {number} angle - 검사할 각도
 * @return {number} 0~180도 범위의 각도 차이
 */
function _getDefaultAngleDistance(angle) {
  return _getAngleDifference(angle, EXPORT_LABEL_DEFAULT_ANGLE)
}

/**
 * @brief 두 사각형의 겹치는 면적 계산
 * @param {Object} first - 첫 번째 사각형
 * @param {Object} second - 두 번째 사각형
 * @param {number} padding - 첫 번째 사각형에 적용할 안전 여백
 * @return {number} 겹치는 면적
 */
function _getBoxOverlapArea(first, second, padding = 0) {
  const overlapWidth = Math.max(
    0,
    Math.min(first.right + padding, second.right) - Math.max(first.left - padding, second.left)
  )
  const overlapHeight = Math.max(
    0,
    Math.min(first.bottom + padding, second.bottom) - Math.max(first.top - padding, second.top)
  )
  return overlapWidth * overlapHeight
}

/**
 * @brief 차트 경계를 벗어난 라벨 면적 계산
 * @param {Object} box - 라벨 사각형
 * @param {Object} bounds - 차트 경계
 * @return {number} 경계 밖 면적
 */
function _getBoundaryOverflowArea(box, bounds) {
  const boxArea = Math.max(0, box.right - box.left) * Math.max(0, box.bottom - box.top)
  const insideWidth = Math.max(0, Math.min(box.right, bounds.right) - Math.max(box.left, bounds.left))
  const insideHeight = Math.max(0, Math.min(box.bottom, bounds.bottom) - Math.max(box.top, bounds.top))
  return Math.max(0, boxArea - insideWidth * insideHeight)
}

/**
 * @brief 원 중심과 글자 사각형 사이의 최단거리 계산
 * @param {number} distance - 원 중심에서 글자 중심까지의 거리
 * @param {number} cosine - 배치 각도의 코사인
 * @param {number} sine - 배치 각도의 사인
 * @param {number} halfWidth - 글자 너비의 절반
 * @param {number} halfHeight - 글자 높이의 절반
 * @return {number} 원 중심과 글자 경계 사이의 최단거리
 */
function _getPointToLabelDistance(distance, cosine, sine, halfWidth, halfHeight) {
  const outsideX = Math.max(Math.abs(cosine * distance) - halfWidth, 0)
  const outsideY = Math.max(Math.abs(sine * distance) - halfHeight, 0)
  return Math.hypot(outsideX, outsideY)
}

/**
 * @brief 고정 경계 간격을 유지하는 라벨 중심거리 계산
 * @param {number} angle - 배치 각도
 * @param {number} halfWidth - 글자 너비의 절반
 * @param {number} halfHeight - 글자 높이의 절반
 * @return {number} 원 중심과 글자 중심 사이의 거리
 */
function _getFixedGapCenterDistance(angle, halfWidth, halfHeight) {
  const radians = angle * Math.PI / 180
  const cosine = Math.cos(radians)
  const sine = Math.sin(radians)
  const targetDistance = COST_POINT_RADIUS + EXPORT_LABEL_GAP
  let low = 0
  let high = halfWidth + halfHeight + targetDistance

  while (_getPointToLabelDistance(high, cosine, sine, halfWidth, halfHeight) < targetDistance) {
    high *= 2
  }

  for (let iteration = 0; iteration < 24; iteration += 1) {
    const middle = (low + high) / 2
    const distance = _getPointToLabelDistance(middle, cosine, sine, halfWidth, halfHeight)
    if (distance < targetDistance) low = middle
    else high = middle
  }

  return high
}

/**
 * @brief 지정한 각도의 라벨 좌표와 경계 상자 계산
 * @param {Object} record - 라벨 측정 정보
 * @param {number} angle - 배치 각도
 * @return {Object} 라벨 배치 정보
 */
function _getLabelPlacement(record, angle) {
  const halfWidth = record.width / 2
  const halfHeight = record.height / 2
  const radians = angle * Math.PI / 180
  const distance = _getFixedGapCenterDistance(angle, halfWidth, halfHeight)
  const centerX = record.pointX + Math.cos(radians) * distance
  const centerY = record.pointY + Math.sin(radians) * distance

  return {
    angle: _normalizeAngle(angle),
    x: centerX - record.anchorOffsetX,
    y: centerY - record.anchorOffsetY,
    box: {
      left: centerX - halfWidth,
      right: centerX + halfWidth,
      top: centerY - halfHeight,
      bottom: centerY + halfHeight
    }
  }
}

/**
 * @brief 각도별 라벨 배치를 캐시해 반환
 * @param {Object} record - 라벨 측정 정보
 * @param {number} angle - 배치 각도
 * @return {Object} 캐시된 라벨 배치
 */
function _getCachedLabelPlacement(record, angle) {
  const cacheKey = Math.round(angle * 10) / 10
  const cachedPlacement = record.placementCache.get(cacheKey)
  if (cachedPlacement) return cachedPlacement

  const placement = _getLabelPlacement(record, angle)
  record.placementCache.set(cacheKey, placement)
  return placement
}

/**
 * @brief 라벨 후보의 경계·충돌·각도 점수 계산
 * @param {Object} record - 현재 라벨
 * @param {Object} placement - 검사할 배치
 * @param {Object[]} records - 전체 라벨 목록
 * @param {Object} bounds - 차트 경계
 * @return {Object} 후보 비교 점수
 */
function _getPlacementScore(record, placement, records, bounds) {
  let collisionOverlap = 0

  records.forEach(other => {
    if (other === record) return

    collisionOverlap += _getBoxOverlapArea(
      placement.box,
      other.placement.box,
      EXPORT_LABEL_COLLISION_PADDING
    )
    collisionOverlap += _getBoxOverlapArea(placement.box, other.pointBox)
  })

  return {
    boundaryOverflow: _getBoundaryOverflowArea(placement.box, bounds),
    collisionOverlap,
    angleDistance: _getDefaultAngleDistance(placement.angle),
    angleOrder: placement.angle
  }
}

/**
 * @brief 두 라벨 배치 점수를 우선순위대로 비교
 * @param {Object} first - 첫 번째 점수
 * @param {Object} second - 두 번째 점수
 * @return {number} 첫 번째 점수가 좋으면 음수
 */
function _comparePlacementScores(first, second) {
  const keys = ['boundaryOverflow', 'collisionOverlap', 'angleDistance', 'angleOrder']
  for (const key of keys) {
    const difference = first[key] - second[key]
    if (Math.abs(difference) > 0.0001) return difference
  }
  return 0
}

/**
 * @brief 전체 후보에서 가장 좋은 라벨 배치 탐색
 * @param {Object} record - 현재 라벨
 * @param {Object[]} records - 전체 라벨 목록
 * @param {Object} bounds - 차트 경계
 * @return {Object} 선택된 라벨 배치
 */
function _findBestLabelPlacement(record, records, bounds) {
  let bestPlacement = null
  let bestScore = null

  record.coarsePlacements.forEach(placement => {
    const score = _getPlacementScore(record, placement, records, bounds)
    if (!bestScore || _comparePlacementScores(score, bestScore) < 0) {
      bestPlacement = placement
      bestScore = score
    }
  })

  const coarseAngle = bestPlacement.angle
  const fineSteps = Math.round(EXPORT_LABEL_FINE_RANGE / EXPORT_LABEL_FINE_STEP)
  for (let step = -fineSteps; step <= fineSteps; step += 1) {
    const angle = coarseAngle + step * EXPORT_LABEL_FINE_STEP
    const placement = _getCachedLabelPlacement(record, angle)
    const score = _getPlacementScore(record, placement, records, bounds)
    if (_comparePlacementScores(score, bestScore) < 0) {
      bestPlacement = placement
      bestScore = score
    }
  }

  return bestPlacement
}

/**
 * @brief 모든 라벨의 주변 모델 밀도를 한 번 계산
 * @param {Object[]} records - 전체 라벨 목록
 * @return {Map<Object, number>} 라벨별 주변 모델 수
 */
function _getLabelDensities(records) {
  const densities = new Map(records.map(record => [record, 0]))
  records.forEach((record, index) => {
    records.slice(index + 1).forEach(other => {
      const distance = Math.hypot(record.pointX - other.pointX, record.pointY - other.pointY)
      const threshold = Math.max(record.width, other.width) / 2 + 48
      if (distance < threshold) {
        densities.set(record, densities.get(record) + 1)
        densities.set(other, densities.get(other) + 1)
      }
    })
  })
  return densities
}

/**
 * @brief 상세 분석 산점도 라벨을 360도 재배치
 * @param {HTMLElement} rootElement - 이미지 내보내기 루트
 * @return {function|undefined} 원래 좌표 복원 함수
 */
function _prepareCostScatterLabels(rootElement) {
  const labelElements = Array.from(rootElement.querySelectorAll('[data-cost-scatter-label="true"]'))
  if (!labelElements.length) return undefined

  const svg = labelElements[0].closest('svg')
  const viewBox = svg?.viewBox?.baseVal
  const width = viewBox?.width || svg?.width?.baseVal?.value
  const height = viewBox?.height || svg?.height?.baseVal?.value
  if (!svg || !width || !height) return undefined

  const bounds = {
    left: (viewBox?.x || 0) + EXPORT_LABEL_BOUNDARY_PADDING,
    right: (viewBox?.x || 0) + width - EXPORT_LABEL_BOUNDARY_PADDING,
    top: (viewBox?.y || 0) + EXPORT_LABEL_BOUNDARY_PADDING,
    bottom: (viewBox?.y || 0) + height - EXPORT_LABEL_BOUNDARY_PADDING
  }

  const originalDisplays = labelElements.map(element => element.style.display)
  labelElements.forEach(element => {
    element.style.display = 'block'
  })

  let records = []
  const originalSvgState = {
    width: svg.getAttribute('width'),
    height: svg.getAttribute('height'),
    viewBox: svg.getAttribute('viewBox'),
    style: svg.style.cssText
  }
  const responsiveContainer = svg.closest('.recharts-responsive-container')
  const chartWrapper = svg.closest('.recharts-wrapper')
  const originalResponsiveMarginBottom = responsiveContainer?.style.marginBottom
  const originalWrapperOverflow = chartWrapper?.style.overflow
  const restoreLabels = () => {
    records.forEach((record, index) => {
      if (record.originalX === null) record.element.removeAttribute('x')
      else record.element.setAttribute('x', record.originalX)
      if (record.originalY === null) record.element.removeAttribute('y')
      else record.element.setAttribute('y', record.originalY)
      if (record.originalTextAnchor === null) record.element.removeAttribute('text-anchor')
      else record.element.setAttribute('text-anchor', record.originalTextAnchor)
      record.element.style.display = originalDisplays[index]
    })
    labelElements.slice(records.length).forEach((element, index) => {
      element.style.display = originalDisplays[records.length + index]
    })
    if (originalSvgState.width === null) svg.removeAttribute('width')
    else svg.setAttribute('width', originalSvgState.width)
    if (originalSvgState.height === null) svg.removeAttribute('height')
    else svg.setAttribute('height', originalSvgState.height)
    if (originalSvgState.viewBox === null) svg.removeAttribute('viewBox')
    else svg.setAttribute('viewBox', originalSvgState.viewBox)
    svg.style.cssText = originalSvgState.style
    if (responsiveContainer) responsiveContainer.style.marginBottom = originalResponsiveMarginBottom
    if (chartWrapper) chartWrapper.style.overflow = originalWrapperOverflow
  }

  try {
    records = labelElements.map((element, index) => {
      const originalX = element.getAttribute('x')
      const originalY = element.getAttribute('y')
      const pointX = Number(element.dataset.pointX)
      const pointY = Number(element.dataset.pointY)
      const anchorX = Number(originalX)
      const anchorY = Number(originalY)
      const box = element.getBBox()
      const pointRadius = COST_POINT_RADIUS + EXPORT_LABEL_POINT_PADDING

      return {
        element,
        index,
        originalX,
        originalY,
        originalTextAnchor: element.getAttribute('text-anchor'),
        pointX,
        pointY,
        width: box.width,
        height: box.height,
        anchorOffsetX: box.x + box.width / 2 - anchorX,
        anchorOffsetY: box.y + box.height / 2 - anchorY,
        pointBox: {
          left: pointX - pointRadius,
          right: pointX + pointRadius,
          top: pointY - pointRadius,
          bottom: pointY + pointRadius
        },
        placementCache: new Map(),
        coarsePlacements: [],
        placement: null
      }
    })

    const hasInvalidRecord = records.some(record => !(
      Number.isFinite(record.pointX) &&
      Number.isFinite(record.pointY) &&
      Number.isFinite(record.width) && record.width > 0 &&
      Number.isFinite(record.height) && record.height > 0
    ))
    if (hasInvalidRecord) {
      restoreLabels()
      return undefined
    }

    const labelPadding = Math.max(...records.map(record => record.width))
    bounds.left -= labelPadding
    bounds.right += labelPadding
    bounds.top -= labelPadding
    bounds.bottom += labelPadding

    records.forEach(record => {
      for (let angle = 0; angle < 360; angle += EXPORT_LABEL_COARSE_STEP) {
        record.coarsePlacements.push(_getCachedLabelPlacement(record, angle))
      }
      record.placement = _getCachedLabelPlacement(record, EXPORT_LABEL_DEFAULT_ANGLE)
    })

    const densities = _getLabelDensities(records)
    const optimizationOrder = [...records].sort((first, second) => {
      const densityDifference = densities.get(second) - densities.get(first)
      return densityDifference || first.index - second.index
    })

    for (let pass = 0; pass < EXPORT_LABEL_MAX_PASSES; pass += 1) {
      let changed = false
      optimizationOrder.forEach(record => {
        const placement = _findBestLabelPlacement(record, records, bounds)
        if (_getAngleDifference(placement.angle, record.placement.angle) > 0.05) {
          changed = true
        }
        record.placement = placement
      })
      if (!changed) break
    }

    const left = Math.min(viewBox?.x || 0, ...records.map(record => record.placement.box.left - EXPORT_LABEL_BOUNDARY_PADDING))
    const top = Math.min(viewBox?.y || 0, ...records.map(record => record.placement.box.top - EXPORT_LABEL_BOUNDARY_PADDING))
    const right = Math.max((viewBox?.x || 0) + width, ...records.map(record => record.placement.box.right + EXPORT_LABEL_BOUNDARY_PADDING))
    const bottom = Math.max((viewBox?.y || 0) + height, ...records.map(record => record.placement.box.bottom + EXPORT_LABEL_BOUNDARY_PADDING))
    const expandedWidth = right - left
    const expandedHeight = bottom - top
    if (expandedWidth > width || expandedHeight > height) {
      svg.setAttribute('width', String(expandedWidth))
      svg.setAttribute('height', String(expandedHeight))
      svg.setAttribute('viewBox', `${left} ${top} ${expandedWidth} ${expandedHeight}`)
      svg.style.width = `${expandedWidth}px`
      svg.style.height = `${expandedHeight}px`
      svg.style.overflow = 'visible'
      if (chartWrapper) chartWrapper.style.overflow = 'visible'
      if (responsiveContainer && expandedHeight > height) {
        responsiveContainer.style.marginBottom = `${expandedHeight - height}px`
      }

    }

    records.forEach(record => {
      record.element.setAttribute('x', String(record.placement.x))
      record.element.setAttribute('y', String(record.placement.y))
    })

    return restoreLabels
  } catch (error) {
    restoreLabels()
    throw error
  }
}

/**
 * @brief 지표 표시명 반환
 * @param {string} metric - 지표 식별자
 * @param {Function} t - 번역 함수
 * @return {string} 표시명
 */
function _getMetricLabel(metric, t) {
  return t(getAnalysisMetric(metric).labelKey)
}

/**
 * @brief 지표 단위 반환
 * @param {string} metric - 지표 식별자
 * @param {Function} t - 번역 함수
 * @return {string} 표시 단위
 */
function _getMetricUnit(metric, t) {
  return t(getAnalysisMetric(metric).unitKey)
}

/**
 * @brief 축 눈금용 지표 값 문자열 변환
 * @param {string} metric - 지표 식별자
 * @param {number} value - 지표 값
 * @param {string} locale - 숫자 표시 언어
 * @return {string} 눈금 문자열
 */
function _formatAxisTick(metric, value, locale) {
  if (metric === 'score') return value.toLocaleString(locale)
  if (metric === 'cost') return `$${Number(value.toPrecision(12))}`
  if (metric === 'time') return Number((value / 3600).toPrecision(12)).toLocaleString(locale, { maximumFractionDigits: 6 })
  if (metric === 'tokens') {
    if (value >= 1000000) return `${(value / 1000000).toLocaleString(locale, { maximumFractionDigits: 1 })}M`
    if (value >= 1000) return `${(value / 1000).toLocaleString(locale, { maximumFractionDigits: 1 })}K`
    return value.toLocaleString(locale, { maximumFractionDigits: 0 })
  }

  return formatAnalysisMetricValue(metric, value, locale)
}

/**
 * @brief 선형 축 눈금과 범위 계산
 * @param {number[]} values - 지표 값 목록
 * @param {number} preferredMax - 우선 사용할 최댓값
 * @return {Object} 선형 범위와 눈금
 */
function _getLinearRange(values, preferredMax) {
  const dataMin = Math.min(...values)
  const max = Math.max(...values, preferredMax)
  const rawInterval = (max - dataMin || 50) / 5
  const magnitude = 10 ** Math.floor(Math.log10(rawInterval))
  const residual = rawInterval / magnitude
  const interval = residual <= 1.5
    ? magnitude
    : residual <= 3
      ? 2 * magnitude
      : residual <= 7
        ? 5 * magnitude
        : 10 * magnitude
  const min = Math.max(0, Math.min(Math.floor(dataMin / interval) * interval, max - interval))
  const ticks = [min]
  for (let tick = min + interval; tick < max; tick += interval) ticks.push(tick)

  return { min, max, ticks }
}

/**
 * @brief 로그 축 범위와 주요 눈금 계산
 * @param {number[]} values - 양수 지표 값 목록
 * @return {Object} 로그 범위와 눈금
 */
function _getLogRange(values) {
  const lowerValue = Math.min(...values) * 0.9
  const upperValue = Math.max(...values) * 1.1
  const lowerMagnitude = 10 ** Math.floor(Math.log10(lowerValue))
  const upperMagnitude = 10 ** Math.floor(Math.log10(upperValue))
  const min = [5, 2, 1].find(value => value <= lowerValue / lowerMagnitude) * lowerMagnitude
  const max = [1, 2, 5, 10].find(value => value >= upperValue / upperMagnitude) * upperMagnitude
  const ticks = [min]
  for (let exponent = Math.ceil(Math.log10(min)); exponent <= Math.floor(Math.log10(max)); exponent += 1) {
    const tick = 10 ** exponent
    if (tick > min && tick < max) ticks.push(tick)
  }
  ticks.push(max)
  return { min, max, ticks }
}

/**
 * @brief 지표 축 범위 계산
 * @param {string} metric - 지표 식별자
 * @param {number[]} values - 지표 값 목록
 * @param {number} maxScore - 점수 만점
 * @return {Object} 축 범위와 눈금
 */
function _getAxisRange(metric, values, maxScore) {
  if (metric === 'time') {
    const range = _getLogRange(values.map(value => value / 3600))
    return { min: range.min * 3600, max: range.max * 3600, ticks: range.ticks.map(value => value * 3600) }
  }
  return isAnalysisMetricLog(metric)
    ? _getLogRange(values)
    : _getLinearRange(values, maxScore)
}

/**
 * @brief 축 중앙값 계산
 * @param {string} metric - 지표 식별자
 * @param {Object} range - 축 범위
 * @return {number} 4분면 기준값
 */
function _getAxisMidpoint(metric, range) {
  return isAnalysisMetricLog(metric)
    ? Math.sqrt(range.min * range.max)
    : (range.min + range.max) / 2
}

/**
 * @brief 지표 방향에 따른 4분면 배경색 결정
 * @param {string} xMetric - X축 지표
 * @param {string} yMetric - Y축 지표
 * @param {boolean} xLow - X축 낮은 영역 여부
 * @param {boolean} yLow - Y축 낮은 영역 여부
 * @param {boolean} darkMode - 다크모드 여부
 * @return {Object} 배경색과 투명도
 */
function _getQuadrantStyle(xMetric, yMetric, xLow, yLow, darkMode) {
  const xGood = xLow === (getAnalysisMetricDirection(xMetric) === 'lower')
  const yGood = yLow === (getAnalysisMetricDirection(yMetric) === 'lower')
  const favorableCount = Number(xGood) + Number(yGood)

  if (favorableCount === 2) {
    return { fill: darkMode ? '#22c55e' : '#bbf7d0', fillOpacity: darkMode ? 0.4 : 0.5 }
  }
  if (favorableCount === 0) {
    return { fill: darkMode ? '#ef4444' : '#fecaca', fillOpacity: darkMode ? 0.4 : 0.5 }
  }
  return { fill: 'transparent', fillOpacity: 0 }
}

/**
 * @brief 커스텀 툴팁 컴포넌트
 * @param {Object} props - 툴팁 표시 정보
 */
function CustomTooltip({ active, payload, t, isRepeatedRun, locale }) {
  if (!active || !payload?.length) return null

  const data = payload[0].payload

  return (
    <div className="w-max whitespace-nowrap bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3">
      <p className="font-semibold text-gray-800 dark:text-gray-200 mb-2">{formatModelDisplayName(data.model)}</p>
      <div className="space-y-1 text-sm">
        <p className="text-gray-600 dark:text-gray-400">
          {t('table.score')}: <span className="font-medium">{formatAnalysisMetricValue('score', data.score, locale)}</span> {t('common.points')}
        </p>
        <p className="text-gray-600 dark:text-gray-400">
          {t(isRepeatedRun ? 'table.averageCost' : 'cost.testCost')}: <span className="font-medium">{formatAnalysisMetricValue('cost', data.totalCost, locale)}</span>
        </p>
        <p className="text-gray-600 dark:text-gray-400">
          {t('token.total')}: <span className="font-medium">{formatAnalysisMetricValue('tokens', data.totalTokens, locale)}</span> {t('cost.tokens')}
        </p>
        <p className="text-gray-600 dark:text-gray-400">
          {t('analysis.estimatedTime')}: <span className="font-medium">{formatAnalysisMetricValue('time', data.estimatedSeconds, locale)}</span>
        </p>
        <p className="text-gray-700 dark:text-gray-300">
          {t('table.efficiency')}: <span className="font-medium">{data.efficiency?.toLocaleString(locale, { maximumFractionDigits: 1 }) ?? '-'}</span>{t('common.points')}
        </p>
      </div>
    </div>
  )
}

/**
 * @brief 처리량 산정 기준 도움말
 * @param {Object} props - 지표 데이터와 번역 함수
 */
function PerformanceHelp({ modelPerformance, t, locale }) {
  const updatedAt = modelPerformance?.updatedAt
  const formattedUpdatedAt = updatedAt
    ? new Date(updatedAt).toLocaleString(locale)
    : t('analysis.help.unavailable')

  return (
    <details className="mt-3 text-sm text-gray-500 dark:text-gray-400" data-export-hide="true">
      <summary className="cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200">
        {t('analysis.help.title')}
      </summary>
      <div className="mt-2 space-y-1 pl-4">
        <p>{t('analysis.help.method')}</p>
        <p>{t('analysis.help.selection')}</p>
        <p>{t('analysis.help.updated')}: {formattedUpdatedAt}</p>
      </div>
    </details>
  )
}

/**
 * @brief 상세 분석 산점도 차트
 * @param {Object} props - 차트와 지표 선택 상태
 * @param {Array} props.data - getCostData() 결과
 * @param {number} props.height - 차트 높이
 * @param {number} props.maxScore - 점수 만점
 * @param {boolean} props.isRepeatedRun - 반복 실행 여부
 * @param {Object|null} props.modelPerformance - 처리량 스냅샷
 * @param {string} props.xMetric - X축 지표
 * @param {string} props.yMetric - Y축 지표
 * @param {Function} props.onXMetricChange - X축 지표 변경 콜백
 * @param {Function} props.onYMetricChange - Y축 지표 변경 콜백
 */
export default function CostScatterChart({
  data = [],
  height = 800,
  maxScore = 450,
  isRepeatedRun = false,
  modelPerformance = null,
  xMetric = DEFAULT_ANALYSIS_X,
  yMetric = DEFAULT_ANALYSIS_Y,
  onXMetricChange,
  onYMetricChange
}) {
  const { t, i18n } = useTranslation()
  const { isDark: darkMode } = useTheme()
  const locale = i18n.language === 'en' ? 'en-US' : 'ko-KR'
  const resolvedXMetric = xMetric
  const resolvedYMetric = yMetric
  const { ref, exportImage, isExporting } = useExportImage({
    exportWidth: README_EXPORT_WIDTH,
    exportProfile: 'costScatter',
    prepareExport: _prepareCostScatterLabels
  })

  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const validData = useMemo(
    () => getAnalysisPoints(data, resolvedXMetric, resolvedYMetric),
    [data, resolvedXMetric, resolvedYMetric]
  )
  const chartHeight = isMobile ? 280 : height
  const axisColor = darkMode ? '#4b5563' : '#e5e7eb'
  const tickColor = darkMode ? '#9ca3af' : '#6b7280'
  const referenceLineColor = darkMode ? '#6b7280' : '#9ca3af'
  const xLabel = _getMetricLabel(resolvedXMetric, t, isRepeatedRun)
  const yLabel = _getMetricLabel(resolvedYMetric, t, isRepeatedRun)
  const xUnit = _getMetricUnit(resolvedXMetric, t)
  const yUnit = _getMetricUnit(resolvedYMetric, t)

  const xValues = validData.map(row => row.xValue)
  const yValues = validData.map(row => row.yValue)
  const xRange = validData.length ? _getAxisRange(resolvedXMetric, xValues, maxScore) : null
  const yRange = validData.length ? _getAxisRange(resolvedYMetric, yValues, maxScore) : null
  const xMidpoint = xRange ? _getAxisMidpoint(resolvedXMetric, xRange) : null
  const yMidpoint = yRange ? _getAxisMidpoint(resolvedYMetric, yRange) : null

  const metricOptions = ANALYSIS_METRIC_IDS.map(metric => ({
    id: metric,
    label: _getMetricLabel(metric, t, isRepeatedRun)
  }))

  return (
    <div ref={ref} className="w-full">
      <div className="flex items-start justify-between gap-3 mb-4">
        <h3 className={`export-role-title flex flex-wrap items-center gap-2 text-xl text-gray-800 dark:text-gray-200 ${isExporting ? 'font-semibold' : 'font-normal'}`}>
          <span data-export-hide="true">
            <label htmlFor="analysis-y-metric" className="sr-only">{t('analysis.yAxis')}</label>
            <select
              id="analysis-y-metric"
              value={resolvedYMetric}
              onChange={event => onYMetricChange(event.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-lg font-normal"
            >
              {metricOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
            </select>
          </span>
          <span className="hidden export-role-title" data-export-show="true">{yLabel}</span>
          <span aria-hidden="true">vs</span>
          <span data-export-hide="true">
            <label htmlFor="analysis-x-metric" className="sr-only">{t('analysis.xAxis')}</label>
            <select
              id="analysis-x-metric"
              value={resolvedXMetric}
              onChange={event => onXMetricChange(event.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-lg font-normal"
            >
              {metricOptions.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
            </select>
          </span>
          <span className="hidden export-role-title" data-export-show="true">{xLabel}</span>
        </h3>
        <div className="flex items-start gap-2">
          <span className="export-role-watermark hidden text-base text-gray-400 mt-8" data-export-show="true">Github/hehee9</span>
          <ExportButton
            onClick={() => exportImage(`${t('export.costAnalysis')}.png`)}
            exportKey="cost-scatter"
          />
        </div>
      </div>

      {validData.length > 0 && (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <ScatterChart
            key={`${darkMode ? 'dark' : 'light'}-${resolvedXMetric}-${resolvedYMetric}`}
            margin={isExporting ? { top: 20, right: 30, left: 36, bottom: 34 } : { top: 20, right: 30, left: 20, bottom: 20 }}
          >
            {darkMode && (
              <ReferenceArea x1={xRange.min} x2={xRange.max} y1={yRange.min} y2={yRange.max} fill="#182130" fillOpacity={1} />
            )}
            {[
              { xLow: true, x1: xRange.min, x2: xMidpoint },
              { xLow: false, x1: xMidpoint, x2: xRange.max }
            ].flatMap(xSegment => [
              { yLow: true, y1: yRange.min, y2: yMidpoint },
              { yLow: false, y1: yMidpoint, y2: yRange.max }
            ].map(ySegment => {
              const style = _getQuadrantStyle(resolvedXMetric, resolvedYMetric, xSegment.xLow, ySegment.yLow, darkMode)
              return (
                <ReferenceArea
                  key={`${xSegment.xLow}-${ySegment.yLow}`}
                  x1={xSegment.x1}
                  x2={xSegment.x2}
                  y1={ySegment.y1}
                  y2={ySegment.y2}
                  fill={style.fill}
                  fillOpacity={style.fillOpacity}
                />
              )
            }))}
            <XAxis
              type="number"
              dataKey="xValue"
              name={xLabel}
              scale={isAnalysisMetricLog(resolvedXMetric) ? 'log' : 'linear'}
              domain={[xRange.min, xRange.max]}
              ticks={xRange.ticks}
              interval={0}
              tickFormatter={value => _formatAxisTick(resolvedXMetric, value, locale)}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              tick={{ fill: tickColor, fontSize: isExporting ? 22 : 16 }}
              height={isExporting ? 58 : 30}
              label={{ value: `${xLabel} (${xUnit})`, position: 'bottom', offset: 0, fill: tickColor, fontSize: isExporting ? 22 : 16, className: 'export-role-axis-label' }}
            />
            <YAxis
              type="number"
              dataKey="yValue"
              name={yLabel}
              scale={isAnalysisMetricLog(resolvedYMetric) ? 'log' : 'linear'}
              domain={[yRange.min, yRange.max]}
              ticks={yRange.ticks}
              interval={0}
              tickFormatter={value => _formatAxisTick(resolvedYMetric, value, locale)}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              tick={{ fill: tickColor, fontSize: isExporting ? 22 : 16 }}
              width={isExporting ? 110 : 60}
              label={{ value: `${yLabel} (${yUnit})`, angle: -90, position: 'insideLeft', fill: tickColor, fontSize: isExporting ? 22 : 16, className: 'export-role-axis-label' }}
            />
            <Tooltip
              content={(
                <CustomTooltip
                  t={t}
                  isRepeatedRun={isRepeatedRun}
                  locale={locale}
                />
              )}
            />
            <ReferenceLine x={xMidpoint} stroke={referenceLineColor} strokeWidth={1} />
            <ReferenceLine y={yMidpoint} stroke={referenceLineColor} strokeWidth={1} />
            <Scatter
              data={validData}
              isAnimationActive={!isExporting}
              shape={({ cx, cy, payload }) => {
                const label = formatModelDisplayName(payload.model)
                return (
                  <g>
                    <circle
                      cx={cx}
                      cy={cy}
                      r={COST_POINT_RADIUS}
                      fill={getModelColor(payload.model)}
                      stroke={darkMode ? '#ffffff' : '#000000'}
                      strokeWidth={0.6}
                    />
                    <text
                      className="hidden export-role-model-label"
                      x={cx}
                      y={cy - 16}
                      textAnchor="middle"
                      fill={darkMode ? '#d1d5db' : '#374151'}
                      fontSize={isExporting ? 24 : 11}
                      fontWeight="500"
                      data-export-show="true"
                      data-cost-scatter-label="true"
                      data-point-x={cx}
                      data-point-y={cy}
                    >
                      {label}
                    </text>
                  </g>
                )
              }}
            />
          </ScatterChart>
        </ResponsiveContainer>
      )}

      {!data?.length && (
        <div className="flex items-center justify-center h-48 text-gray-500 dark:text-gray-400">
          {t('common.noData')}
        </div>
      )}
      {data?.length > 0 && !validData.length && (
        <div className="flex items-center justify-center h-48 text-gray-500 dark:text-gray-400">
          {t('analysis.noDataForAxes')}
        </div>
      )}

      <PerformanceHelp modelPerformance={modelPerformance} t={t} locale={locale} />
      {validData.length > 0 && <BenchmarkNote modelNames={validData.map(item => item.model)} />}
    </div>
  )
}
