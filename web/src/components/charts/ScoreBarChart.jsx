/**
 * @file ScoreBarChart.jsx
 * @brief 모델별 점수 가로 막대 차트 컴포넌트
 */

import { useState, useEffect } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Rectangle,
  CartesianGrid,
  LabelList
} from 'recharts'
import { useTranslation } from 'react-i18next'
import { getModelColor, getShortModelName, CHART_COLORS, lightenColor } from '@/utils/colorUtils'
import { useTheme } from '@/hooks/useTheme'
import { useData } from '@/hooks/useData'
import { useExportImage, README_EXPORT_WIDTH } from '@/hooks/useExportImage'
import { useBarChartExportLayout } from '@/hooks/useBarChartExportLayout'
import { BenchmarkNote, ExportButton } from '@/components/common'
import { formatModelDisplayName, getModelFlags } from '@/utils/modelMeta'

const MAX_LINE_LENGTH = 21
const MAX_LINES = 3
const MOBILE_WRAP_THRESHOLD = 17
const EXPORT_AXIS_FONT_SIZE = 24
const EXPORT_MODEL_FONT_SIZE = 22
const EXPORT_VALUE_FONT_SIZE = 22
const EXPORT_X_AXIS_ANGLE = -60
const EXPORT_X_AXIS_HEIGHT = 460
const EXPORT_X_AXIS_LABEL_OFFSET = 16
const EXPORT_MOBILE_LABEL_LINE_HEIGHT = 32
const EXPORT_LEFT_MARGIN = 100
const EXPORT_RIGHT_MARGIN = 30
const EXPORT_VALUE_LABEL_GAP = 4
const EXPORT_VALUE_CHAR_WIDTH_FACTOR = 0.6
const EXPORT_BEST_WORST_BAR_SIZE = 44
const EXPORT_BEST_WORST_BAR_GAP = 8
const EXPORT_BEST_WORST_GROUP_SLOT = 122
const EXPORT_Y_AXIS_WIDTH = 60
const EXPORT_CHART_HEIGHT = 830

/**
 * @brief 보기 모드 정의
 */
const VIEW_MODES = [
  { key: 'average', labelKey: 'charts.viewModes.average' },
  { key: 'bestWorst', labelKey: 'charts.viewModes.bestWorst' },
  { key: 'withImage', labelKey: 'charts.viewModes.withImage' },
  { key: 'withoutImage', labelKey: 'charts.viewModes.withoutImage' }
]

/**
 * @brief 긴 텍스트를 중간 공백에서 줄바꿈 (모바일용)
 * @param {string} text - 분할할 텍스트
 * @param {number} threshold - 줄바꿈 적용 기준 길이
 * @return {Array<string>} 분할된 줄 배열
 */
function _wrapAtMiddle(text, threshold = MOBILE_WRAP_THRESHOLD) {
  if (text.length < threshold) return [text]

  const middle = Math.floor(text.length / 2)

  // 중간에서 가장 가까운 공백 찾기
  let leftSpace = text.lastIndexOf(' ', middle)
  let rightSpace = text.indexOf(' ', middle)

  // 유효한 공백이 없으면 줄바꿈 안 함
  if (leftSpace <= 0 && rightSpace < 0) return [text]

  // 중간에 더 가까운 공백 선택
  let breakPoint
  if (leftSpace <= 0) {
    breakPoint = rightSpace
  } else if (rightSpace < 0) {
    breakPoint = leftSpace
  } else {
    breakPoint = (middle - leftSpace <= rightSpace - middle) ? leftSpace : rightSpace
  }

  return [
    text.slice(0, breakPoint).trim(),
    text.slice(breakPoint).trim()
  ]
}

/**
 * @brief 텍스트를 최대 길이 기준으로 여러 줄로 분할 (최대 3줄)
 * @param {string} text - 분할할 텍스트
 * @param {number} maxLen - 줄당 최대 길이
 * @return {Array<string>} 분할된 줄 배열
 */
function _wrapText(text, maxLen) {
  if (text.length <= maxLen) return [text]

  const lines = []
  let remaining = text

  while (remaining.length > 0 && lines.length < MAX_LINES) {
    if (remaining.length <= maxLen || lines.length === MAX_LINES - 1) {
      lines.push(remaining)
      break
    }

    // 우선순위: 1. 콤마+공백 뒤, 2. 여는괄호 앞, 3. 일반 공백
    let breakPoint = -1

    // 1. 콤마+공백 뒤
    const commaIdx = remaining.lastIndexOf(', ', maxLen - 1)
    if (commaIdx > 0) {
      breakPoint = commaIdx + 1
    }

    // 2. 여는괄호 앞
    if (breakPoint <= 0) {
      const parenIdx = remaining.lastIndexOf(' (', maxLen - 1)
      if (parenIdx > 0) {
        breakPoint = parenIdx
      }
    }

    // 3. 일반 공백
    if (breakPoint <= 0) {
      breakPoint = remaining.lastIndexOf(' ', maxLen)
    }
    if (breakPoint <= 0) {
      breakPoint = maxLen
    }

    lines.push(remaining.slice(0, breakPoint).trim())
    remaining = remaining.slice(breakPoint).trim()
  }

  return lines
}

/**
 * @brief 빗금 패턴 SVG defs (비표준 설정 모델용)
 * @param {{ darkMode: boolean }} props
 */
function HatchPatternDefs({ darkMode }) {
  const strokeColor = darkMode ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.25)'
  const checkerLight = darkMode ? 'rgba(255,255,255,0.20)' : 'rgba(255,255,255,0.24)'
  const checkerDark = darkMode ? 'rgba(0,0,0,0.16)' : 'rgba(0,0,0,0.08)'
  const shadowRgb = darkMode ? '255,255,255' : '0,0,0'
  const shadowAlpha = darkMode ? 0.15 : 0.2
  return (
    <defs>
      <pattern
        id="hatch-nonstandard"
        patternUnits="userSpaceOnUse"
        width="6"
        height="6"
        patternTransform="rotate(45)"
      >
        <line x1="0" y1="0" x2="0" y2="6" stroke={strokeColor} strokeWidth="2" />
      </pattern>
      <pattern
        id="web-service-no-tools-checker"
        patternUnits="userSpaceOnUse"
        width="16"
        height="16"
      >
        <rect x="0" y="0" width="8" height="8" fill={checkerLight} />
        <rect x="8" y="8" width="8" height="8" fill={checkerLight} />
        <rect x="8" y="0" width="8" height="8" fill={checkerDark} />
        <rect x="0" y="8" width="8" height="8" fill={checkerDark} />
      </pattern>
      {/* noVision용 내부 그림자 그라데이션 (좌, 우, 상, 하) */}
      <linearGradient id="shadow-left" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stopColor={`rgba(${shadowRgb},${shadowAlpha})`} />
        <stop offset="100%" stopColor={`rgba(${shadowRgb},0)`} />
      </linearGradient>
      <linearGradient id="shadow-right" x1="1" y1="0" x2="0" y2="0">
        <stop offset="0%" stopColor={`rgba(${shadowRgb},${shadowAlpha})`} />
        <stop offset="100%" stopColor={`rgba(${shadowRgb},0)`} />
      </linearGradient>
      <linearGradient id="shadow-top" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={`rgba(${shadowRgb},${shadowAlpha})`} />
        <stop offset="100%" stopColor={`rgba(${shadowRgb},0)`} />
      </linearGradient>
      <linearGradient id="shadow-bottom" x1="0" y1="1" x2="0" y2="0">
        <stop offset="0%" stopColor={`rgba(${shadowRgb},${shadowAlpha})`} />
        <stop offset="100%" stopColor={`rgba(${shadowRgb},0)`} />
      </linearGradient>
      <filter id="post-exam-cutoff-glow" x="-8%" y="-24%" width="116%" height="148%">
        <feGaussianBlur stdDeviation="1.35" />
      </filter>
    </defs>
  )
}

/**
 * @brief 모델 플래그를 반영한 막대 렌더링 헬퍼
 * @param {Object} props - Recharts shape props (x, y, width, height, payload)
 * @param {Object} options - { hoveredModel, radius, colorOverride, modelMetadata, examMonth }
 * @return {JSX.Element} SVG <g> 또는 <Rectangle>
 */
/**
 * @brief noVision 모델용 내부 그림자 오버레이
 */
function _InnerShadowOverlay({ x, y, width, height }) {
  const depth = Math.min(8, width * 0.25)
  return (
    <>
      <rect x={x} y={y} width={depth} height={height} fill="url(#shadow-left)" />
      <rect x={x + width - depth} y={y} width={depth} height={height} fill="url(#shadow-right)" />
      <rect x={x} y={y} width={width} height={depth} fill="url(#shadow-top)" />
      <rect x={x} y={y + height - depth} width={width} height={depth} fill="url(#shadow-bottom)" />
    </>
  )
}

/**
 * @brief 지식 컷오프가 수능 이후인 모델용 모델 색상 그림자
 */
function _PostExamKnowledgeCutoffGlow({ x, y, width, height, radius, color }) {
  return (
    <Rectangle
      x={x - 0.5}
      y={y - 0.5}
      width={width + 1}
      height={height + 1}
      fill={color}
      opacity={0.9}
      radius={radius}
      filter="url(#post-exam-cutoff-glow)"
    />
  )
}

/**
 * @brief 도구 차단 웹 서비스 환경 모델용 체크무늬 오버레이
 */
function _WebServiceNoToolsChecker({ x, y, width, height, radius }) {
  return (
    <Rectangle
      x={x}
      y={y}
      width={width}
      height={height}
      fill="url(#web-service-no-tools-checker)"
      radius={radius}
    />
  )
}

function _renderBar(props, { hoveredModel, radius = [4, 4, 0, 0], colorOverride, modelMetadata = {}, examMonth = null }) {
  const { x, y, width, height, payload } = props
  const color = colorOverride || payload.color || getModelColor(payload.model)
  const isHovered = hoveredModel === payload.model
  const hasHover = hoveredModel !== null
  const opacity = hasHover ? (isHovered ? 1 : 0.3) : 1

  const flags = getModelFlags(payload.model, modelMetadata, examMonth)
  const transitionStyle = { transition: 'opacity 0.15s ease-in-out' }

  if (flags.noVision || flags.nonStandard || flags.postExamKnowledgeCutoff || flags.webServiceNoTools) {
    return (
      <g style={transitionStyle} opacity={opacity}>
        {flags.postExamKnowledgeCutoff && (
          <_PostExamKnowledgeCutoffGlow x={x} y={y} width={width} height={height} radius={radius} color={color} />
        )}
        <Rectangle x={x} y={y} width={width} height={height} fill={color} radius={radius} />
        {flags.noVision && <_InnerShadowOverlay x={x} y={y} width={width} height={height} />}
        {flags.nonStandard && (
          <Rectangle x={x} y={y} width={width} height={height} fill="url(#hatch-nonstandard)" radius={radius} />
        )}
        {flags.webServiceNoTools && (
          <_WebServiceNoToolsChecker x={x} y={y} width={width} height={height} radius={radius} />
        )}
      </g>
    )
  }

  return (
    <Rectangle
      x={x} y={y} width={width} height={height}
      fill={color} radius={radius} opacity={opacity}
      style={transitionStyle}
    />
  )
}

/**
 * @brief 커스텀 Y축 틱 컴포넌트 생성 함수
 * @param {string} hoveredModel - 현재 호버된 모델명
 * @param {function} onModelHover - 모델 호버 콜백
 * @param {boolean} darkMode - 다크모드 여부
 * @param {boolean} isMobile - 모바일 여부
 * @return {function} Recharts tick 렌더 함수
 */
function createCustomYAxisTick(hoveredModel, onModelHover, darkMode, isMobile, exportMode = false) {
  const defaultColor = darkMode ? '#d1d5db' : '#374151'
  const hoverColor = darkMode ? '#60a5fa' : '#1d4ed8'

  return function CustomYAxisTick({ x, y, payload }) {
    // 모바일에서는 짧은 모델명 사용 + 17자 이상 시 중간 공백에서 줄바꿈
    const displayName = isMobile ? getShortModelName(payload.value) : formatModelDisplayName(payload.value)
    const lines = isMobile ? _wrapAtMiddle(displayName) : _wrapText(displayName, MAX_LINE_LENGTH)
    const fontSize = exportMode ? EXPORT_MODEL_FONT_SIZE : 12
    const lineHeight = exportMode ? EXPORT_MOBILE_LABEL_LINE_HEIGHT : 14
    const startY = -((lines.length - 1) * lineHeight) / 2 + 3
    const isHovered = hoveredModel === payload.value
    const hasHover = hoveredModel !== null

    return (
      <g
        style={{ cursor: 'pointer' }}
        onMouseEnter={() => onModelHover?.(payload.value)}
        onMouseLeave={() => onModelHover?.(null)}
      >
        {/* 투명한 호버 영역 (텍스트보다 넓게) */}
        <rect
          x={x - 145}
          y={y - 20}
          width={150}
          height={40}
          fill="transparent"
        />
        <text
          className="export-role-model-label"
          x={x}
          y={y}
          textAnchor="end"
          fontSize={fontSize}
          fill={isHovered ? hoverColor : defaultColor}
          fontWeight={isHovered ? 600 : 400}
          style={{
            ...(exportMode ? { fontSize: `${fontSize}px` } : {}),
            opacity: hasHover ? (isHovered ? 1 : 0.5) : 1,
            transition: 'opacity 0.15s ease-in-out'
          }}
        >
          {lines.map((line, i) => (
            <tspan key={i} x={x} dy={i === 0 ? startY : lineHeight}>
              {line}
            </tspan>
          ))}
        </text>
      </g>
    )
  }
}

/**
 * @brief 내보내기용 세로 막대 차트 X축 모델명 틱 생성
 * @param {string} tickColor - 틱 글자 색상
 * @return {function} Recharts 틱 렌더 함수
 */
function createExportXAxisTick(tickColor) {
  return function ExportXAxisTick({ x, y, payload }) {
    return (
      <g transform={`translate(${x},${y + EXPORT_X_AXIS_LABEL_OFFSET})`}>
        <text
          className="export-role-model-label"
          textAnchor="end"
          dominantBaseline="central"
          transform={`rotate(${EXPORT_X_AXIS_ANGLE})`}
          fill={tickColor}
          fontSize={EXPORT_MODEL_FONT_SIZE}
          style={{ fontSize: `${EXPORT_MODEL_FONT_SIZE}px` }}
        >
          {formatModelDisplayName(payload.value)}
        </text>
      </g>
    )
  }
}

/**
 * @brief 내보내기 숫자 레이블이 모델 칸을 넘지 않도록 표시 폭 계산
 * @param {string} label - 표시할 숫자 레이블
 * @param {number} modelCount - 표시할 모델 수
 * @return {number} SVG 숫자 레이블 표시 폭
 */
function _getExportValueTextLength(label, modelCount) {
  const slotWidth = (README_EXPORT_WIDTH - EXPORT_LEFT_MARGIN - EXPORT_RIGHT_MARGIN) / modelCount
  const availableWidth = Math.max(1, slotWidth - EXPORT_VALUE_LABEL_GAP * 2)
  const estimatedWidth = label.length * EXPORT_VALUE_FONT_SIZE * EXPORT_VALUE_CHAR_WIDTH_FACTOR
  return Math.min(estimatedWidth, availableWidth)
}

/**
 * @brief 점수 차트 내보내기 숫자 레이블 렌더러
 * @param {Object} props - Recharts LabelList 속성
 * @param {function} formatter - 숫자 표시 형식 함수
 * @param {number} modelCount - 표시할 모델 수
 * @param {string} fill - 글자 색상
 * @return {JSX.Element|null} 숫자 레이블
 */
function ExportScoreLabel({ x, y, width, value, formatter, modelCount, fill }) {
  if (value === undefined || value === null) return null

  const label = formatter(value)
  const textLength = _getExportValueTextLength(label, modelCount)

  return (
    <text
      className="export-role-value"
      x={x + width / 2}
      y={y - 8}
      textAnchor="middle"
      fill={fill}
      fontSize={EXPORT_VALUE_FONT_SIZE}
      fontWeight="500"
      textLength={textLength}
      lengthAdjust="spacingAndGlyphs"
      style={{ fontSize: `${EXPORT_VALUE_FONT_SIZE}px` }}
    >
      {label}
    </text>
  )
}

/**
 * @brief bestWorst 내보내기용 최고·최저 점수 한 줄 렌더링
 * @param {Object} props - Recharts LabelList 속성
 * @param {Object[]} data - 모델별 최고·최저 점수 데이터
 * @param {function} formatter - 숫자 표시 형식 함수
 * @param {string} fill - 글자 색상
 * @return {JSX.Element|null} 한 줄 숫자 레이블
 */
function ExportBestWorstScoreLabels({ x, y, width, value, index, data, formatter, fill }) {
  if (value === undefined || value === null) return null

  const bestLabel = formatter(value)
  const worstLabel = formatter(data[index].worst)
  const longestLabelLength = Math.max(bestLabel.length, worstLabel.length)
  const availableLabelWidth = width + EXPORT_BEST_WORST_BAR_GAP - EXPORT_VALUE_LABEL_GAP
  const fontSize = Math.min(
    EXPORT_VALUE_FONT_SIZE,
    availableLabelWidth / (longestLabelLength * EXPORT_VALUE_CHAR_WIDTH_FACTOR)
  )
  const labelY = y - 8
  const labelStyle = { '--export-value-size': `${fontSize}px` }

  return (
    <g>
      <text
        className="export-role-value"
        x={x + width / 2}
        y={labelY}
        textAnchor="middle"
        fill={fill}
        fontSize={fontSize}
        fontWeight="500"
        style={labelStyle}
      >
        {bestLabel}
      </text>
      <text
        className="export-role-value"
        x={x + width / 2 + width + EXPORT_BEST_WORST_BAR_GAP}
        y={labelY}
        textAnchor="middle"
        fill={fill}
        fontSize={fontSize}
        fontWeight="500"
        style={labelStyle}
      >
        {worstLabel}
      </text>
    </g>
  )
}

/**
 * @brief 커스텀 툴팁 컴포넌트
 * @param {Object} props - { active, payload, t }
 */
function CustomTooltip({ active, payload, t }) {
  if (!active || !payload?.length) return null

  const data = payload[0].payload
  const displayScore = Number.isInteger(data.score)
    ? data.score
    : parseFloat(data.score.toFixed(3))
  const accuracy = data.totalPoints > 0
    ? ((data.score / data.totalPoints) * 100).toFixed(1)
    : 0

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3">
      <p className="font-semibold text-gray-800 dark:text-gray-200 mb-1">{formatModelDisplayName(data.model)}</p>
      <p className="text-sm text-gray-600 dark:text-gray-400">
        {t('tooltip.score')}: <span className="font-medium">{displayScore}</span> / {data.totalPoints}{t('tooltip.points')}
      </p>
      <p className="text-sm text-gray-600 dark:text-gray-400">
        {t('tooltip.accuracy')}: <span className="font-medium">{accuracy}%</span>
      </p>
      {data.correctCount !== undefined && (
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t('tooltip.correctCount')}: <span className="font-medium">{data.correctCount}</span> / {data.totalQuestions}{t('tooltip.totalQuestions')}
        </p>
      )}
    </div>
  )
}

/**
 * @brief 점수 막대 차트 컴포넌트
 * @param {Object} props - { data, maxScore, title, height, hoveredModel, onModelHover, viewMode, onViewModeChange }
 * @param {Array} props.data - [{ model, score, totalPoints, correctCount?, totalQuestions? }]
 *                             bestWorst 모드: [{ model, best, worst }]
 *                             이미지 모드: [{ model, rate, score, maxScore }]
 * @param {number} props.maxScore - 차트 Y축 최대값 (기본: 데이터에서 자동 계산)
 * @param {string} props.title - 차트 제목
 * @param {number} props.height - 차트 높이 (기본: 400)
 * @param {string} props.hoveredModel - 현재 호버된 모델명
 * @param {function} props.onModelHover - 모델 호버 콜백
 * @param {string} props.viewMode - 보기 모드 ('average' | 'bestWorst' | 'withImage' | 'withoutImage')
 * @param {function} props.onViewModeChange - 보기 모드 변경 콜백
 * @param {boolean} props.showViewModeButtons - 보기 모드 버튼 표시 여부
 * @param {boolean} props.allowBestWorst - 최고/최저 보기 모드 허용 여부
 */
export default function ScoreBarChart({
  data,
  maxScore,
  title,
  subtitle,
  height = 400,
  hoveredModel,
  onModelHover,
  viewMode = 'average',
  onViewModeChange,
  showViewModeButtons = false,
  allowBestWorst = true,
  modelMetadata = {}
}) {
  const { t } = useTranslation()
  const { isDark: darkMode } = useTheme()
  const { exam } = useData()
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  const {
    prepareExport,
    xAxisHeight: exportXAxisHeight,
    chartHeight: exportChartHeight
  } = useBarChartExportLayout({
    enabled: !isMobile,
    baseXAxisHeight: EXPORT_X_AXIS_HEIGHT,
    baseChartHeight: EXPORT_CHART_HEIGHT
  })
  const exportWidth = !isMobile && viewMode === 'bestWorst'
    ? Math.max(
      README_EXPORT_WIDTH,
      (data?.length ?? 0) * EXPORT_BEST_WORST_GROUP_SLOT
        + EXPORT_LEFT_MARGIN
        + EXPORT_RIGHT_MARGIN
        + EXPORT_Y_AXIS_WIDTH
    )
    : README_EXPORT_WIDTH
  const { ref, exportImage, isExporting } = useExportImage({
    exportWidth,
    prepareExport,
    exportProfile: 'overviewScore'
  })
  const [showLabels, setShowLabels] = useState(true)
  const examMonth = exam?.exam_month

  // 모바일 감지
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  if (!data?.length) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500 dark:text-gray-400">
        {t('common.noData')}
      </div>
    )
  }

  // 최대 점수 계산 (전달되지 않은 경우)
  const computedMaxScore = maxScore ?? Math.max(...data.map(d => d.totalPoints || d.score))

  // 다크모드용 색상
  const cursorColor = darkMode ? 'rgba(55, 65, 81, 0.5)' : '#f3f4f6'
  const axisColor = darkMode ? '#4b5563' : '#e5e7eb'
  const tickColor = darkMode ? '#9ca3af' : '#6b7280'
  const xTickColor = darkMode ? '#d1d5db' : '#374151'

  // 모바일: 가로 막대 차트
  if (isMobile) {
    const dynamicHeight = Math.max(height, data.length * (isExporting ? 64 : 40) + (isExporting ? 100 : 60))

    return (
      <div ref={ref} className="w-full">
        <div className="flex items-start justify-between mb-4">
          <div>
            {title && (
              <h3 className="export-role-title text-lg font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
            )}
            {subtitle && (
              <p className="export-role-subtitle text-sm text-gray-500 dark:text-gray-400 mt-1">{subtitle}</p>
            )}
          </div>
          <ExportButton
            onClick={() => exportImage(`${subtitle || t('common.all')}.png`)}
            exportKey="overview-score-chart"
          />
        </div>
        <ResponsiveContainer width="100%" height={dynamicHeight}>
          <BarChart
            key={data.map(d => d.model).join(',')}
            data={data}
            layout="vertical"
            margin={{ top: 10, right: 30, left: 5, bottom: 10 }}
            onMouseMove={(state) => {
              if (state?.activeTooltipIndex !== undefined) {
                const model = data[state.activeTooltipIndex]?.model
                if (model && model !== hoveredModel) {
                  onModelHover?.(model)
                }
              }
            }}
            onMouseLeave={() => onModelHover?.(null)}
          >
            <XAxis
              type="number"
              domain={[0, computedMaxScore]}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              tick={{ ...(isExporting ? { fontSize: EXPORT_AXIS_FONT_SIZE } : {}), fill: tickColor, className: 'export-role-axis-value' }}
            />
            <YAxis
              type="category"
              dataKey="model"
              tickLine={false}
              axisLine={false}
              width={isExporting ? 220 : 100}
              tick={createCustomYAxisTick(hoveredModel, onModelHover, darkMode, true, isExporting)}
            />
            <Tooltip content={<CustomTooltip t={t} />} cursor={{ fill: cursorColor }} />
            <ReferenceLine
              x={computedMaxScore}
              stroke={CHART_COLORS.perfect}
              strokeDasharray="3 3"
              strokeWidth={2}
            />
            <HatchPatternDefs darkMode={darkMode} />
            <Bar
              dataKey="score"
              barSize={24}
              shape={(props) => _renderBar(props, { hoveredModel, radius: [0, 4, 4, 0], modelMetadata, examMonth })}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  // 데스크톱: 세로 막대 차트 (TokenUsageChart 스타일)
  // 모델 수에 따른 레이블 글자 크기 (적을수록 크게)
  const labelFontSize = data.length <= 15 ? 12 : 10
  const desktopChartMargin = {
    top: isExporting && viewMode === 'bestWorst' ? 70 : 30,
    right: 30,
    left: isExporting ? EXPORT_LEFT_MARGIN : 20,
    bottom: isExporting ? 20 : 100
  }
  const desktopXAxisHeight = isExporting ? exportXAxisHeight : 100
  const desktopChartHeight = isExporting ? exportChartHeight : 600

  return (
    <div ref={ref} className="w-full">
      <div className="flex items-start justify-between mb-2">
        <div>
          {title && (
            <h3 className="export-role-title text-xl font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
          )}
          {subtitle && (
            <p className="export-role-subtitle text-base text-gray-500 dark:text-gray-400 mt-1">{subtitle}</p>
          )}
        </div>
        <div className="flex items-start gap-2">
          <span className="export-role-watermark hidden text-base text-gray-400 mt-8" data-export-show="true">Github/hehee9</span>
          <ExportButton
            onClick={() => exportImage(`${subtitle || t('common.all')}.png`)}
            exportKey="overview-score-chart"
          />
        </div>
      </div>
      {/* 보기 모드 버튼 + 레이블 표시 토글 */}
      <div className="flex items-center gap-2 mb-4 flex-wrap" data-export-hide="true">
        {showViewModeButtons && (
          <div className="flex gap-1 mr-2">
            {VIEW_MODES.filter(mode => allowBestWorst || mode.key !== 'bestWorst').map(mode => (
              <button
                key={mode.key}
                onClick={() => onViewModeChange?.(mode.key)}
                className={`px-3 py-1 text-xs rounded transition-colors ${
                  viewMode === mode.key
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                {t(mode.labelKey)}
              </button>
            ))}
          </div>
        )}
        {viewMode !== 'withImage' && viewMode !== 'withoutImage' && (
          <button
            onClick={() => setShowLabels(!showLabels)}
            className={`px-2 py-1 text-xs rounded transition-colors ${
              showLabels
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
          >
            {t('charts.showScores')}
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={desktopChartHeight}>
        {viewMode === 'bestWorst' ? (
          /* 최고/최저 모드: 모델당 두 개 막대 */
          <BarChart
            key={`bestWorst-${data.map(d => d.model).join(',')}`}
            data={data}
            barGap={isExporting ? EXPORT_BEST_WORST_BAR_GAP : undefined}
            margin={desktopChartMargin}
            onMouseMove={(state) => {
              if (state?.activeTooltipIndex !== undefined) {
                const model = data[state.activeTooltipIndex]?.model
                if (model && model !== hoveredModel) {
                  onModelHover?.(model)
                }
              }
            }}
            onMouseLeave={() => onModelHover?.(null)}
          >
            <XAxis
              dataKey="model"
              tickFormatter={(value) => formatModelDisplayName(value)}
              angle={isExporting ? EXPORT_X_AXIS_ANGLE : -45}
              textAnchor="end"
              interval={0}
              tick={isExporting ? createExportXAxisTick(xTickColor) : { fontSize: 11, fill: xTickColor }}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              height={desktopXAxisHeight}
            />
            <YAxis
              domain={[0, computedMaxScore]}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              tick={{ ...(isExporting ? { fontSize: EXPORT_AXIS_FONT_SIZE } : {}), fill: tickColor, className: 'export-role-axis-value' }}
            />
            <CartesianGrid
              horizontal={true}
              vertical={false}
              stroke={axisColor}
              strokeDasharray="3 3"
            />
            <ReferenceLine
              y={computedMaxScore}
              stroke={darkMode ? '#6b7280' : '#9ca3af'}
              strokeDasharray="3 3"
              strokeWidth={1.5}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload
                return (
                  <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3">
                    <p className="font-semibold text-gray-800 dark:text-gray-200 mb-1">{d.model}</p>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t('charts.bestScore')}: <span className="font-medium">{d.best?.toFixed(1)}</span>{t('tooltip.points')}
                    </p>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t('charts.worstScore')}: <span className="font-medium">{d.worst?.toFixed(1)}</span>{t('tooltip.points')}
                    </p>
                  </div>
                )
              }}
              cursor={{ fill: cursorColor }}
            />
            <HatchPatternDefs darkMode={darkMode} />
            <Bar
              dataKey="best"
              name={t('charts.bestScore')}
              barSize={isExporting ? EXPORT_BEST_WORST_BAR_SIZE : undefined}
              isAnimationActive={false}
              shape={(props) => _renderBar(props, { hoveredModel, modelMetadata, examMonth })}
            >
              {showLabels && (
                <LabelList
                  dataKey="best"
                  position="top"
                  className="export-role-value"
                  formatter={(v) => v?.toFixed(1)}
                  content={isExporting ? (props) => (
                    <ExportBestWorstScoreLabels
                      {...props}
                      data={data}
                      formatter={(v) => v?.toFixed(1)}
                      fill={xTickColor}
                    />
                  ) : undefined}
                  style={{ fontSize: isExporting ? EXPORT_VALUE_FONT_SIZE : 9, fill: xTickColor, fontWeight: 500 }}
                />
              )}
            </Bar>
            <Bar
              dataKey="worst"
              name={t('charts.worstScore')}
              barSize={isExporting ? EXPORT_BEST_WORST_BAR_SIZE : undefined}
              isAnimationActive={false}
              shape={(props) => {
                const baseColor = props.payload.color || getModelColor(props.payload.model)
                return _renderBar(props, { hoveredModel, colorOverride: lightenColor(baseColor, 0.5), modelMetadata, examMonth })
              }}
            >
              {showLabels && !isExporting && (
                <LabelList
                  dataKey="worst"
                  position="top"
                  formatter={(v) => v?.toFixed(1)}
                  style={{ fontSize: 9, fill: xTickColor, fontWeight: 500 }}
                />
              )}
            </Bar>
          </BarChart>
        ) : (viewMode === 'withImage' || viewMode === 'withoutImage') ? (
          /* 이미지 O/X 모드: 득점률(%) 표시 */
          <BarChart
            key={`image-${viewMode}-${data.map(d => d.model).join(',')}`}
            data={data}
            margin={desktopChartMargin}
            onMouseMove={(state) => {
              if (state?.activeTooltipIndex !== undefined) {
                const model = data[state.activeTooltipIndex]?.model
                if (model && model !== hoveredModel) {
                  onModelHover?.(model)
                }
              }
            }}
            onMouseLeave={() => onModelHover?.(null)}
          >
            <XAxis
              dataKey="model"
              tickFormatter={(value) => formatModelDisplayName(value)}
              angle={isExporting ? EXPORT_X_AXIS_ANGLE : -45}
              textAnchor="end"
              interval={0}
              tick={isExporting ? createExportXAxisTick(xTickColor) : { fontSize: 11, fill: xTickColor }}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              height={desktopXAxisHeight}
            />
            <YAxis
              domain={[0, 100]}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              tick={{ ...(isExporting ? { fontSize: EXPORT_AXIS_FONT_SIZE } : {}), fill: tickColor, className: 'export-role-axis-value' }}
              tickFormatter={(v) => `${v}%`}
            />
            <CartesianGrid
              horizontal={true}
              vertical={false}
              stroke={axisColor}
              strokeDasharray="3 3"
            />
            <ReferenceLine
              y={100}
              stroke={darkMode ? '#6b7280' : '#9ca3af'}
              strokeDasharray="3 3"
              strokeWidth={1.5}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload
                return (
                  <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3">
                    <p className="font-semibold text-gray-800 dark:text-gray-200 mb-1">{d.model}</p>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t('charts.accuracy')}: <span className="font-medium">{d.rate?.toFixed(1)}%</span>
                    </p>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {t('tooltip.score')}: <span className="font-medium">{d.score?.toFixed(1)}</span> / {d.maxScore}{t('tooltip.points')}
                    </p>
                  </div>
                )
              }}
              cursor={{ fill: cursorColor }}
            />
            <HatchPatternDefs darkMode={darkMode} />
            <Bar
              dataKey="rate"
              isAnimationActive={false}
              shape={(props) => _renderBar(props, { hoveredModel, modelMetadata, examMonth })}
            >
                <LabelList
                  dataKey="rate"
                  position="top"
                  className="export-role-value"
                  formatter={(v) => `${v?.toFixed(1)}%`}
                  content={isExporting ? (props) => (
                    <ExportScoreLabel
                      {...props}
                      formatter={(v) => `${v?.toFixed(1)}%`}
                      modelCount={data.length}
                      fill={xTickColor}
                    />
                  ) : undefined}
                  style={{ fontSize: isExporting ? EXPORT_VALUE_FONT_SIZE : labelFontSize, fill: xTickColor, fontWeight: 500 }}
                />
            </Bar>
          </BarChart>
        ) : (
          /* 기본(평균) 모드 */
          <BarChart
            key={data.map(d => d.model).join(',')}
            data={data}
            margin={desktopChartMargin}
            onMouseMove={(state) => {
              if (state?.activeTooltipIndex !== undefined) {
                const model = data[state.activeTooltipIndex]?.model
                if (model && model !== hoveredModel) {
                  onModelHover?.(model)
                }
              }
            }}
            onMouseLeave={() => onModelHover?.(null)}
          >
            <XAxis
              dataKey="model"
              tickFormatter={(value) => formatModelDisplayName(value)}
              angle={isExporting ? EXPORT_X_AXIS_ANGLE : -45}
              textAnchor="end"
              interval={0}
              tick={isExporting ? createExportXAxisTick(xTickColor) : { fontSize: 11, fill: xTickColor }}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              height={desktopXAxisHeight}
            />
            <YAxis
              domain={[0, computedMaxScore]}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
              tick={{ ...(isExporting ? { fontSize: EXPORT_AXIS_FONT_SIZE } : {}), fill: tickColor, className: 'export-role-axis-value' }}
            />
            <CartesianGrid
              horizontal={true}
              vertical={false}
              stroke={axisColor}
              strokeDasharray="3 3"
            />
            <Tooltip content={<CustomTooltip t={t} />} cursor={{ fill: cursorColor }} />
            <HatchPatternDefs darkMode={darkMode} />
            <Bar
              dataKey="score"
              isAnimationActive={false}
              shape={(props) => _renderBar(props, { hoveredModel, modelMetadata, examMonth })}
            >
              {showLabels && (
                <LabelList
                  dataKey="score"
                  position="top"
                  className="export-role-value"
                  formatter={(v) => v.toFixed(1)}
                  content={isExporting ? (props) => (
                    <ExportScoreLabel
                      {...props}
                      formatter={(v) => v.toFixed(1)}
                      modelCount={data.length}
                      fill={xTickColor}
                    />
                  ) : undefined}
                  style={{ fontSize: isExporting ? EXPORT_VALUE_FONT_SIZE : labelFontSize, fill: xTickColor, fontWeight: 500 }}
                />
              )}
            </Bar>
          </BarChart>
        )}
      </ResponsiveContainer>
      <BenchmarkNote modelNames={data.map(item => item.model)} modelMetadata={modelMetadata} />
    </div>
  )
}
