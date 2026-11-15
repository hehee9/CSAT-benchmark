/**
 * @file ScoreTrendChart.jsx
 * @brief 출시일 기준 개발사별(또는 개발사·요금제별) 성적 변화 추이 차트 컴포넌트
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  XAxis,
  YAxis
} from 'recharts'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/hooks/useTheme'
import { BenchmarkNote, NoWebSearchBadge } from '@/components/common'
import { VENDORS, darkenColor, lightenColor } from '@/utils/colorUtils'
import { formatModelDisplayName } from '@/utils/modelMeta'
import { buildTierTrendSeries, buildTrendPoints, buildVendorStepLines, getFrontierModels, getMonthTicks } from '@/utils/trendTransform'

const DAY_MS = 24 * 60 * 60 * 1000
const SCORE_TICK_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500]
const LIGHT_SURFACE = '#ffffff'
const DARK_SURFACE = '#1f2937'
const MIN_LIGHT_CONTRAST = 2.2
const MIN_DARK_CONTRAST = 3
const CHART_MARGIN_TOP = 10
const X_AXIS_HEIGHT = 30
const MOUSE_HIT_RADIUS = 10
const TOUCH_HIT_RADIUS = 22
const MOUSE_LINE_HIT_RADIUS = 7
const TOUCH_LINE_HIT_RADIUS = 18
const LINE_TIE_EPSILON = 0.5
const TOOLTIP_GAP = 12
const FREE_LINE_DASH = '6 4'

/**
 * @brief HEX 색상의 상대 휘도 계산
 * @param {string} hex - HEX 색상 코드
 * @return {number} 0~1 상대 휘도
 */
function _getLuminance(hex) {
  const channels = [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16) / 255)
  const [r, g, b] = channels.map(value => (value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/**
 * @brief 두 색상의 명암비 계산
 * @param {string} first - 첫 번째 HEX 색상
 * @param {string} second - 두 번째 HEX 색상
 * @return {number} 명암비
 */
function _getContrast(first, second) {
  const [high, low] = [_getLuminance(first), _getLuminance(second)].sort((a, b) => b - a)
  return (high + 0.05) / (low + 0.05)
}

/**
 * @brief 차트 배경에서 식별 가능한 개발사 색상 반환
 * @param {string} color - 개발사 브랜드 색상
 * @param {boolean} darkMode - 다크모드 여부
 * @return {string} 같은 색조를 유지하며 명암만 보정한 색상
 */
function _getReadableColor(color, darkMode) {
  const surface = darkMode ? DARK_SURFACE : LIGHT_SURFACE
  const minContrast = darkMode ? MIN_DARK_CONTRAST : MIN_LIGHT_CONTRAST
  let adjusted = color
  for (let factor = 0.1; factor < 1 && _getContrast(adjusted, surface) < minContrast; factor += 0.1) {
    adjusted = darkMode ? lightenColor(color, factor) : darkenColor(color, factor)
  }
  return adjusted
}

/**
 * @brief 0부터 만점까지의 점수 눈금 계산
 * @param {number} maxScore - 만점
 * @param {number} maxIntervals - 최대 구간 수
 * @return {number[]} 점수 눈금
 */
function _getScoreTicks(maxScore, maxIntervals) {
  const step = SCORE_TICK_STEPS.find(candidate => maxScore / candidate <= maxIntervals) ?? maxScore
  const ticks = []
  for (let tick = 0; tick < maxScore; tick += step) ticks.push(tick)
  if (maxScore - ticks[ticks.length - 1] <= step / 2 && ticks.length > 1) ticks.pop()
  ticks.push(maxScore)
  return ticks
}

/**
 * @brief 점수 표시 문자열 변환
 * @param {number} score - 점수
 * @param {string} locale - 표시 언어
 * @return {string} 점수 문자열
 */
function _formatScore(score, locale) {
  return score.toLocaleString(locale, { maximumFractionDigits: 1 })
}

/**
 * @brief 묶음 기준에 따라 추이 계열 목록 생성
 * @param {'vendor'|'vendorTier'} grouping - 계열 묶음 기준
 * @param {Array} scores - calculateAllModelScores 결과
 * @param {Object} modelMetadata - 모델별 메타데이터
 * @return {{series: Array<{key: string, vendorId: string, tier: ('free'|'paid'|null), points: Array<Object>, stepLine: Array<Object>, frontierModels: Set<string>}>, excludedCount: number, unclassifiedCount: number}} 계열과 제외 모델 수
 *
 * 개발사 기준은 개발사마다 계열 하나, 개발사·요금제 기준은 무료와 유료가 모두 있는 개발사마다 계열 두 개를 만든다.
 */
function _buildTrendSeries(grouping, scores, modelMetadata) {
  if (grouping === 'vendorTier') {
    const { series, excludedCount, unclassifiedCount } = buildTierTrendSeries(scores, modelMetadata)
    return {
      series: series.map(item => ({ ...item, key: `${item.vendorId}:${item.tier}` })),
      excludedCount,
      unclassifiedCount
    }
  }

  const { points, excludedCount } = buildTrendPoints(scores, modelMetadata)
  const stepLines = buildVendorStepLines(points)
  const frontierModels = getFrontierModels(points)
  const series = Object.keys(stepLines).map(vendorId => ({
    key: vendorId,
    vendorId,
    tier: null,
    points: points.filter(point => point.vendorId === vendorId),
    stepLine: stepLines[vendorId],
    frontierModels
  }))
  return { series, excludedCount, unclassifiedCount: 0 }
}

/**
 * @brief 포인터에서 가장 가까운 마커와 같은 위치에 겹친 마커 묶음 탐색
 * @param {Array<{x: number, y: number, point: Object}>} markers - 화면 좌표를 계산한 마커 목록
 * @param {number} pointerX - 차트 영역 기준 포인터 X 좌표
 * @param {number} pointerY - 차트 영역 기준 포인터 Y 좌표
 * @param {number} hitRadius - 마커 인식 반경
 * @param {number} overlapRadius - 같은 위치로 묶을 마커 간 거리
 * @return {{x: number, y: number, points: Array<Object>, key: string}|null} 호버 대상, 없으면 null
 */
function _findHoveredMarkers(markers, pointerX, pointerY, hitRadius, overlapRadius) {
  let nearest = null
  let nearestDistance = Infinity
  markers.forEach(marker => {
    const distance = Math.hypot(marker.x - pointerX, marker.y - pointerY)
    if (distance <= hitRadius && distance < nearestDistance) {
      nearest = marker
      nearestDistance = distance
    }
  })
  if (!nearest) return null

  const group = markers
    .filter(marker => Math.hypot(marker.x - nearest.x, marker.y - nearest.y) <= overlapRadius)
    .sort((a, b) => b.point.score - a.point.score || a.point.time - b.point.time)
  return {
    x: nearest.x,
    y: nearest.y,
    points: group.map(marker => marker.point),
    key: group.map(marker => marker.point.model).join('\n')
  }
}

/**
 * @brief 점에서 선분까지의 최단 거리와 선분 위 가장 가까운 점 계산
 * @param {number} pointerX - 점 X 좌표
 * @param {number} pointerY - 점 Y 좌표
 * @param {{x1: number, y1: number, x2: number, y2: number}} segment - 선분
 * @return {{x: number, y: number, distance: number}} 가장 가까운 점과 거리
 */
function _projectOntoSegment(pointerX, pointerY, { x1, y1, x2, y2 }) {
  const dx = x2 - x1
  const dy = y2 - y1
  const lengthSquared = dx * dx + dy * dy
  const ratio = lengthSquared === 0 ? 0 : Math.min(Math.max(((pointerX - x1) * dx + (pointerY - y1) * dy) / lengthSquared, 0), 1)
  const x = x1 + ratio * dx
  const y = y1 + ratio * dy
  return { x, y, distance: Math.hypot(pointerX - x, pointerY - y) }
}

/**
 * @brief 포인터에서 가장 가까운 계단선 구간의 기록 모델 탐색
 * @param {Array<{x1: number, y1: number, x2: number, y2: number, seriesKey: string, points: Array<Object>}>} segments - 화면 좌표 계단선 구간
 * @param {number} pointerX - 차트 영역 기준 포인터 X 좌표
 * @param {number} pointerY - 차트 영역 기준 포인터 Y 좌표
 * @param {number} hitRadius - 선 인식 반경
 * @return {{x: number, y: number, points: Array<Object>, seriesKeys: string[], key: string}|null} 호버 대상, 없으면 null
 *
 * 거리가 같은 다른 계열 선은 함께 묶고, 같은 계열 안에서는 가장 가까운 구간 하나만 쓴다.
 */
function _findHoveredLine(segments, pointerX, pointerY, hitRadius) {
  const hits = segments
    .map(segment => ({ segment, ..._projectOntoSegment(pointerX, pointerY, segment) }))
    .filter(hit => hit.distance <= hitRadius)
    .sort((a, b) => a.distance - b.distance)
  if (!hits.length) return null

  const nearest = hits[0]
  const tiedBySeries = new Map()
  hits.forEach(hit => {
    if (hit.distance - nearest.distance <= LINE_TIE_EPSILON && !tiedBySeries.has(hit.segment.seriesKey)) {
      tiedBySeries.set(hit.segment.seriesKey, hit)
    }
  })
  const points = Array.from(tiedBySeries.values())
    .flatMap(hit => hit.segment.points)
    .sort((a, b) => b.score - a.score || a.time - b.time)
  return {
    x: nearest.x,
    y: nearest.y,
    points,
    seriesKeys: Array.from(tiedBySeries.keys()),
    key: points.map(point => point.model).join('\n')
  }
}

/**
 * @brief 두 호버 상태가 같은 대상·같은 위치인지 확인
 * @param {Object|null} previous - 이전 호버 상태
 * @param {Object|null} next - 새 호버 상태
 * @return {boolean} 갱신이 필요 없으면 true
 */
function _isSameHover(previous, next) {
  if (previous === next) return true
  if (!previous || !next) return false
  return previous.key === next.key && Math.hypot(previous.x - next.x, previous.y - next.y) < 1
}

/**
 * @brief 호버한 마커의 툴팁 내용
 * @param {Object} props - 마커 모델 목록과 표시 정보
 */
function _TrendTooltipContent({ points, t, locale, vendorById, dateFormatter }) {
  return (
    <div className="divide-y divide-gray-200 dark:divide-gray-700">
      {points.map(point => {
        const vendor = vendorById.get(point.vendorId)
        return (
          <div key={point.model} className="py-2 first:pt-0 last:pb-0">
            <p className="font-semibold text-gray-800 dark:text-gray-200 mb-1.5">{formatModelDisplayName(point.model)}</p>
            <div className="space-y-0.5 text-sm text-gray-600 dark:text-gray-400">
              <p className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: vendor?.displayColor }} />
                {t('trend.developer')}: <span className="font-medium text-gray-700 dark:text-gray-300">{vendor?.name}</span>
              </p>
              <p>
                {t('trend.releaseDate')}: <span className="font-medium text-gray-700 dark:text-gray-300">{dateFormatter.format(point.time)}</span>
              </p>
              {point.tier && (
                <p>
                  {t('trend.plan')}: <span className="font-medium text-gray-700 dark:text-gray-300">{t(point.tier === 'free' ? 'trend.tierFree' : 'trend.tierPaid')}</span>
                </p>
              )}
              <p>
                {t('table.score')}: <span className="font-medium text-gray-700 dark:text-gray-300">{_formatScore(point.score, locale)}</span> {t('common.points')}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/**
 * @brief 요금제별 선 모양 범례 (유료 실선·채운 점, 무료 점선·빈 점)
 * @param {Object} props - 번역 함수, 숨긴 요금제 집합과 전환 함수
 */
function _TierLineLegend({ t, hiddenTiers, onToggle }) {
  const items = [
    { tier: 'paid', label: t('trend.tierPaid'), dash: undefined, filled: true },
    { tier: 'free', label: t('trend.tierFree'), dash: FREE_LINE_DASH, filled: false }
  ]
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 mb-3 text-xs md:text-sm text-gray-600 dark:text-gray-300" aria-label={t('trend.lineStyleLegend')}>
      {items.map(item => {
        const isHidden = hiddenTiers.has(item.tier)
        return (
          <li key={item.tier}>
            <button
              type="button"
              onClick={() => onToggle(item.tier)}
              aria-pressed={!isHidden}
              className={`flex items-center gap-1.5 px-1.5 md:px-2 py-1 rounded-md text-xs md:text-sm transition-colors hover:bg-gray-100 dark:hover:bg-gray-700 ${isHidden ? 'text-gray-400 dark:text-gray-500' : 'text-gray-700 dark:text-gray-300'}`}
            >
              <svg width="34" height="12" viewBox="0 0 34 12" aria-hidden="true" className="shrink-0">
                <line x1="1" y1="6" x2="33" y2="6" stroke="currentColor" strokeWidth="2" strokeDasharray={item.dash} />
                <circle cx="17" cy="6" r="4" stroke="currentColor" strokeWidth="1.6" className={item.filled ? 'fill-current' : 'fill-white dark:fill-gray-800'} />
              </svg>
              <span className={isHidden ? 'line-through' : ''}>{item.label}</span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

/**
 * @brief 개발사 다중 선택 팝오버
 * @param {Object} props - 개발사 목록과 선택 상태
 */
function VendorSelector({ vendors, hiddenVendorIds, onToggle, onSelectAll, onSelectNone, t }) {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef(null)
  const selectedCount = vendors.length - vendors.filter(vendor => hiddenVendorIds.has(vendor.id)).length

  useEffect(() => {
    if (!isOpen) return undefined
    const handlePointerDown = (event) => {
      if (!containerRef.current?.contains(event.target)) setIsOpen(false)
    }
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setIsOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('touchstart', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('touchstart', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setIsOpen(open => !open)}
        aria-expanded={isOpen}
        aria-haspopup="true"
        className="flex items-center gap-1.5 min-h-[36px] px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
      >
        <span className="tabular-nums">{t('trend.vendorSelection', { total: vendors.length, selected: selectedCount })}</span>
        <svg className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 z-30 mt-1 w-64 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg">
          <div className="flex justify-between gap-2 px-3 py-2 border-b border-gray-200 dark:border-gray-700 text-sm">
            <button type="button" onClick={onSelectAll} className="text-blue-600 dark:text-blue-400 hover:underline">
              {t('trend.selectAll')}
            </button>
            <button type="button" onClick={onSelectNone} className="text-gray-500 dark:text-gray-400 hover:underline">
              {t('trend.selectNone')}
            </button>
          </div>
          <ul className="max-h-72 overflow-y-auto py-1">
            {vendors.map(vendor => (
              <li key={vendor.id}>
                <label className="flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700">
                  <input
                    type="checkbox"
                    checked={!hiddenVendorIds.has(vendor.id)}
                    onChange={() => onToggle(vendor.id)}
                    className="w-4 h-4 accent-blue-500"
                  />
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: vendor.displayColor }} />
                  <span className="flex-1 truncate">{vendor.name}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">{vendor.modelCount}</span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/**
 * @brief 출시일 기준 성적 변화 추이 차트
 * @param {Object} props - 차트 데이터와 표시 정보
 * @param {Array} props.scores - 모델 필터를 적용한 calculateAllModelScores 결과
 * @param {Object} props.modelMetadata - 모델별 메타데이터 (releaseDate, accessTier 포함)
 * @param {number} props.maxScore - 현재 시험·과목 필터의 만점
 * @param {string|null} props.subtitle - 선택한 과목 필터 설명
 * @param {number} props.height - 데스크톱 차트 높이
 * @param {'vendor'|'vendorTier'} props.grouping - 계열 묶음 기준 (개발사, 또는 개발사·요금제)
 * @param {string} [props.title] - 차트 제목 (기본: 개발사별 추이 제목)
 * @param {string} [props.emptyMessage] - 표시할 계열이 없을 때의 안내
 */
export default function ScoreTrendChart({
  scores = [],
  modelMetadata = {},
  maxScore = 450,
  subtitle = null,
  height = 560,
  grouping = 'vendor',
  title,
  emptyMessage
}) {
  const { t, i18n } = useTranslation()
  const { isDark: darkMode } = useTheme()
  const locale = i18n.language === 'en' ? 'en-US' : 'ko-KR'
  const [hiddenVendorIds, setHiddenVendorIds] = useState(() => new Set())
  const [hiddenTiers, setHiddenTiers] = useState(() => new Set())
  const [focusedVendorId, setFocusedVendorId] = useState(null)
  const [hoveredMarkers, setHoveredMarkers] = useState(null)
  const chartAreaRef = useRef(null)
  const tooltipRef = useRef(null)

  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768)
      setHoveredMarkers(null)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const { series, excludedCount, unclassifiedCount } = useMemo(
    () => _buildTrendSeries(grouping, scores, modelMetadata),
    [grouping, scores, modelMetadata]
  )
  /** @brief 계열 정보를 붙인 출시일 오름차순 좌표 */
  const points = useMemo(() => series
    .flatMap(item => item.points.map(point => ({
      ...point,
      seriesKey: item.key,
      tier: item.tier,
      isFrontier: item.frontierModels.has(point.model)
    })))
    .sort((a, b) => a.time - b.time), [series])
  const minTime = points.length ? points[0].time : 0
  const maxTime = points.length ? points[points.length - 1].time : 0

  const vendors = useMemo(() => {
    const statsById = new Map()
    points.forEach(point => {
      const stats = statsById.get(point.vendorId) ?? { modelCount: 0, bestScore: -Infinity }
      stats.modelCount += 1
      stats.bestScore = Math.max(stats.bestScore, point.score)
      statsById.set(point.vendorId, stats)
    })
    return VENDORS
      .filter(vendor => statsById.has(vendor.id))
      .map(vendor => ({
        id: vendor.id,
        name: vendor.id === 'other' ? t('trend.otherVendor') : vendor.name,
        displayColor: _getReadableColor(vendor.color, darkMode),
        ...statsById.get(vendor.id)
      }))
      .sort((a, b) => b.bestScore - a.bestScore)
  }, [points, t, darkMode])
  const vendorById = useMemo(() => new Map(vendors.map(vendor => [vendor.id, vendor])), [vendors])
  const visibleVendors = vendors.filter(vendor => !hiddenVendorIds.has(vendor.id))
  const visibleSeries = visibleVendors
    .flatMap(vendor => series.filter(item => item.vendorId === vendor.id))
    .filter(item => item.tier === null || !hiddenTiers.has(item.tier))
  const visibleModels = points
    .filter(point => !hiddenVendorIds.has(point.vendorId) && (point.tier === null || !hiddenTiers.has(point.tier)))
    .map(point => point.model)

  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' }),
    [locale]
  )
  const monthFormatter = useMemo(
    () => new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'short', timeZone: 'UTC' }),
    [locale]
  )

  const timePadding = Math.max((maxTime - minTime) * 0.03, 10 * DAY_MS)
  const xDomain = [minTime - timePadding, maxTime + timePadding]
  const xTicks = getMonthTicks(xDomain[0], xDomain[1], isMobile ? 4 : 8)
  const yTicks = _getScoreTicks(maxScore, isMobile ? 5 : 9)
  const chartHeight = isMobile ? 300 : height
  const gridColor = darkMode ? '#374151' : '#f0f0f0'
  const axisColor = darkMode ? '#4b5563' : '#e5e7eb'
  const tickColor = darkMode ? '#9ca3af' : '#6b7280'
  const markerStroke = darkMode ? DARK_SURFACE : LIGHT_SURFACE
  const yAxisWidth = isMobile ? 36 : 48
  const marginRight = isMobile ? 8 : 20
  const markerRadius = isMobile ? 4.5 : 5.5
  const markerPoints = points.filter(point => (
    !hiddenVendorIds.has(point.vendorId) && (point.tier === null || !hiddenTiers.has(point.tier)) && point.isFrontier
  ))
  const hoveredModels = new Set(hoveredMarkers?.points.map(point => point.model))
  const lineSeriesKeys = hoveredMarkers?.seriesKeys ?? null

  /**
   * @brief 차트 영역 기준 화면 좌표 변환 함수 생성
   * @param {number} width - 차트 영역 너비
   * @return {function(number, number): {x: number, y: number}} 시각·점수를 화면 좌표로 바꾸는 함수
   */
  const _getPlotProjector = (width) => {
    const plotWidth = width - yAxisWidth - marginRight
    const plotHeight = chartHeight - CHART_MARGIN_TOP - X_AXIS_HEIGHT
    return (time, score) => ({
      x: yAxisWidth + (time - xDomain[0]) / (xDomain[1] - xDomain[0]) * plotWidth,
      y: CHART_MARGIN_TOP + (1 - score / maxScore) * plotHeight
    })
  }

  /**
   * @brief 표시 중인 계단선을 기록 모델이 붙은 수평·수직 구간으로 분해
   * @param {function(number, number): {x: number, y: number}} toPixel - 화면 좌표 변환 함수
   * @return {Array<{x1: number, y1: number, x2: number, y2: number, seriesKey: string, points: Array<Object>}>} 계단선 구간
   *
   * 수평 구간은 시작 꼭짓점의 기록 모델, 수직 구간은 그 단계를 만든 모델에 속한다.
   */
  const _projectLineSegments = (toPixel) => visibleSeries.flatMap(item => {
    const vertices = item.stepLine
    const pixels = vertices.map(vertex => toPixel(vertex.time, vertex.score))
    const recordPoints = vertices.map(vertex => markerPoints.filter(point => (
      point.seriesKey === item.key && point.time === vertex.time && point.score === vertex.score
    )))
    return pixels.slice(1).flatMap((end, index) => {
      const start = pixels[index]
      return [
        { seriesKey: item.key, x1: start.x, y1: start.y, x2: end.x, y2: start.y, points: recordPoints[index] },
        { seriesKey: item.key, x1: end.x, y1: start.y, x2: end.x, y2: end.y, points: recordPoints[index + 1] }
      ]
    })
  })

  /**
   * @brief 포인터 아래 마커 또는 계단선으로 호버 상태 갱신 (마커 우선)
   * @param {PointerEvent} event - 차트 영역 포인터 이벤트
   */
  const handleChartPointer = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect()
    const isMouse = event.pointerType === 'mouse'
    const pointerX = event.clientX - bounds.left
    const pointerY = event.clientY - bounds.top
    const toPixel = _getPlotProjector(bounds.width)
    const next = _findHoveredMarkers(
      markerPoints.map(point => ({ point, ...toPixel(point.time, point.score) })),
      pointerX,
      pointerY,
      isMouse ? MOUSE_HIT_RADIUS : TOUCH_HIT_RADIUS,
      markerRadius * 2
    ) ?? _findHoveredLine(_projectLineSegments(toPixel), pointerX, pointerY, isMouse ? MOUSE_LINE_HIT_RADIUS : TOUCH_LINE_HIT_RADIUS)
    setHoveredMarkers(previous => (_isSameHover(previous, next) ? previous : next))
  }

  /**
   * @brief 마우스가 차트를 벗어나면 툴팁 숨김 (터치는 다음 탭까지 유지)
   * @param {PointerEvent} event - 포인터 이벤트
   */
  const handleChartPointerLeave = (event) => {
    if (event.pointerType === 'mouse') setHoveredMarkers(null)
  }

  // 차트 밖을 탭하면 터치 툴팁 닫기 (마커 재렌더링으로 target이 분리돼도 디스패치 시점 경로로 판정)
  useEffect(() => {
    if (!hoveredMarkers) return undefined
    const handlePointerDown = (event) => {
      if (!event.composedPath().includes(chartAreaRef.current)) setHoveredMarkers(null)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [hoveredMarkers])

  // 마커를 가리지 않고 차트 영역 안에 들어오도록 툴팁 위치 결정
  useLayoutEffect(() => {
    const tooltip = tooltipRef.current
    if (!hoveredMarkers || !tooltip) return
    const areaWidth = chartAreaRef.current.clientWidth
    const { offsetWidth: width, offsetHeight: height } = tooltip
    const { x, y } = hoveredMarkers
    let left = x - width / 2
    let top = y - TOOLTIP_GAP - height >= 0 ? y - TOOLTIP_GAP - height : y + TOOLTIP_GAP
    if (x + TOOLTIP_GAP + width <= areaWidth || x - TOOLTIP_GAP - width >= 0) {
      left = x + TOOLTIP_GAP + width <= areaWidth ? x + TOOLTIP_GAP : x - TOOLTIP_GAP - width
      top = Math.min(Math.max(y - height / 2, 0), chartHeight - height)
    }
    left = Math.min(Math.max(left, 0), areaWidth - width)
    tooltip.style.left = `${left}px`
    tooltip.style.top = `${top}px`
  }, [hoveredMarkers, chartHeight, locale])

  /**
   * @brief 개발사 표시 여부 전환
   * @param {string} vendorId - 개발사 ID
   */
  const handleToggleVendor = (vendorId) => {
    setHiddenVendorIds(previous => {
      const next = new Set(previous)
      if (next.has(vendorId)) next.delete(vendorId)
      else next.add(vendorId)
      return next
    })
  }

  /**
   * @brief 요금제 계열 표시 여부 전환
   * @param {'free'|'paid'} tier - 요금제 계열
   */
  const handleToggleTier = (tier) => {
    setHoveredMarkers(null)
    setHiddenTiers(previous => {
      const next = new Set(previous)
      if (next.has(tier)) next.delete(tier)
      else next.add(tier)
      return next
    })
  }

  /**
   * @brief 범례로 강조한 개발사 또는 호버한 계단선 계열 외에 흐리게 표시할지 확인
   * @param {{vendorId: string, key: string}} item - 계열
   * @return {boolean} 흐리게 표시해야 하면 true
   */
  const _isDimmed = (item) => {
    if (focusedVendorId !== null && !hiddenVendorIds.has(focusedVendorId)) return focusedVendorId !== item.vendorId
    return lineSeriesKeys !== null && !lineSeriesKeys.includes(item.key)
  }

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1.5">
            <h3 className="text-xl font-semibold text-gray-800 dark:text-gray-200">
              {title ?? t('trend.title')}
              <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">({t('charts.maxPoints', { max: maxScore })})</span>
            </h3>
            <NoWebSearchBadge />
          </div>
          {subtitle && <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>}
        </div>
        {vendors.length > 0 && (
          <VendorSelector
            vendors={vendors}
            hiddenVendorIds={hiddenVendorIds}
            onToggle={handleToggleVendor}
            onSelectAll={() => setHiddenVendorIds(new Set())}
            onSelectNone={() => setHiddenVendorIds(new Set(vendors.map(vendor => vendor.id)))}
            t={t}
          />
        )}
      </div>

      {vendors.length > 0 && (
        <ul
          className="flex flex-wrap gap-x-0.5 md:gap-x-1 gap-y-0.5 md:gap-y-1 mb-3 -mx-1"
          aria-label={t('trend.legendLabel')}
        >
          {vendors.map(vendor => {
            const isHidden = hiddenVendorIds.has(vendor.id)
            return (
              <li key={vendor.id}>
                <button
                  type="button"
                  onClick={() => handleToggleVendor(vendor.id)}
                  onPointerEnter={event => event.pointerType === 'mouse' && !isHidden && setFocusedVendorId(vendor.id)}
                  onPointerLeave={() => setFocusedVendorId(null)}
                  onFocus={event => event.currentTarget.matches(':focus-visible') && !isHidden && setFocusedVendorId(vendor.id)}
                  onBlur={() => setFocusedVendorId(null)}
                  aria-pressed={!isHidden}
                  className={`flex items-center gap-1.5 px-1.5 md:px-2 py-1 rounded-md text-xs md:text-sm transition-colors hover:bg-gray-100 dark:hover:bg-gray-700 ${isHidden ? 'text-gray-400 dark:text-gray-500' : 'text-gray-700 dark:text-gray-300'}`}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0 border-2"
                    style={{ borderColor: vendor.displayColor, backgroundColor: isHidden ? 'transparent' : vendor.displayColor }}
                  />
                  <span className={isHidden ? 'line-through' : ''}>{vendor.name}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {grouping === 'vendorTier' && series.length > 0 && <_TierLineLegend t={t} hiddenTiers={hiddenTiers} onToggle={handleToggleTier} />}

      {series.length > 0 ? (
        <div
          ref={chartAreaRef}
          className="relative"
          onPointerMove={handleChartPointer}
          onPointerDown={handleChartPointer}
          onPointerLeave={handleChartPointerLeave}
        >
        <ResponsiveContainer width="100%" height={chartHeight}>
          <ComposedChart margin={{ top: CHART_MARGIN_TOP, right: marginRight, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={gridColor} />
            <XAxis
              type="number"
              dataKey="time"
              scale="time"
              domain={xDomain}
              ticks={xTicks}
              interval={0}
              allowDataOverflow
              tickFormatter={value => monthFormatter.format(value)}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              tick={{ fill: tickColor, fontSize: isMobile ? 11 : 13 }}
              height={X_AXIS_HEIGHT}
            />
            <YAxis
              type="number"
              domain={[0, maxScore]}
              ticks={yTicks}
              interval={0}
              allowDataOverflow
              tickFormatter={value => _formatScore(value, locale)}
              tickLine={false}
              axisLine={false}
              tick={{ fill: tickColor, fontSize: isMobile ? 11 : 13 }}
              width={yAxisWidth}
            />
            {visibleSeries.filter(item => item.stepLine.length > 1).map(item => (
              <Line
                key={`line-${item.key}`}
                data={item.stepLine}
                dataKey="score"
                type="stepAfter"
                stroke={vendorById.get(item.vendorId).displayColor}
                strokeDasharray={item.tier === 'free' ? FREE_LINE_DASH : undefined}
                strokeWidth={lineSeriesKeys?.includes(item.key) ? 3.5 : 2}
                strokeOpacity={_isDimmed(item) ? 0.12 : 0.9}
                dot={false}
                activeDot={false}
                isAnimationActive={false}
                tooltipType="none"
                legendType="none"
              />
            ))}
            {visibleSeries.map(item => {
              const color = vendorById.get(item.vendorId).displayColor
              const isHollow = item.tier === 'free'
              return (
                <Scatter
                  key={`points-${item.key}`}
                  data={markerPoints.filter(point => point.seriesKey === item.key)}
                  dataKey="score"
                  isAnimationActive={false}
                  shape={({ cx, cy, payload }) => {
                    const dimmed = _isDimmed(item)
                    return (
                      <g>
                        {hoveredModels.has(payload.model) && (
                          <circle cx={cx} cy={cy} r={markerRadius + 4} fill="none" stroke={color} strokeWidth={2} strokeOpacity={0.5} />
                        )}
                        <circle
                          cx={cx}
                          cy={cy}
                          r={markerRadius}
                          fill={isHollow ? markerStroke : color}
                          fillOpacity={dimmed ? 0.1 : 1}
                          stroke={isHollow ? color : markerStroke}
                          strokeOpacity={dimmed ? 0.2 : 1}
                          strokeWidth={isHollow ? 2 : 1.2}
                        />
                      </g>
                    )
                  }}
                />
              )
            })}
          </ComposedChart>
        </ResponsiveContainer>
        {hoveredMarkers && (
          <div
            ref={tooltipRef}
            role="tooltip"
            className="pointer-events-none absolute z-20 w-max max-w-[min(18rem,100%)] bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3"
          >
            <_TrendTooltipContent points={hoveredMarkers.points} t={t} locale={locale} vendorById={vendorById} dateFormatter={dateFormatter} />
          </div>
        )}
        </div>
      ) : (
        <div className="flex items-center justify-center h-48 text-gray-500 dark:text-gray-400">
          {emptyMessage ?? t('trend.noReleaseDates')}
        </div>
      )}

      {excludedCount > 0 && (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{t('trend.excludedModels', { count: excludedCount })}</p>
      )}
      {unclassifiedCount > 0 && (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{t('trend.unclassifiedModels', { count: unclassifiedCount })}</p>
      )}
      {visibleModels.length > 0 && <BenchmarkNote modelNames={visibleModels} />}
    </div>
  )
}
