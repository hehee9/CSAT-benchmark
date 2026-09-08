/**
 * @file TokenUsageChart.jsx
 * @brief 모델별 토큰 사용량 스택 바 차트
 */

import { useMemo, useState, useCallback, useEffect } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  LabelList,
  Cell,
  CartesianGrid
} from 'recharts'
import { useTranslation } from 'react-i18next'
import { getModelColor, getShortModelName } from '@/utils/colorUtils'
import { useTheme } from '@/hooks/useTheme'
import { useData } from '@/hooks/useData'
import { useExportImage, README_EXPORT_WIDTH } from '@/hooks/useExportImage'
import { useBarChartExportLayout } from '@/hooks/useBarChartExportLayout'
import { BenchmarkNote, ExportButton } from '@/components/common'
import { formatModelDisplayName, getModelFlags } from '@/utils/modelMeta'

const EXPORT_AXIS_FONT_SIZE = 24
const EXPORT_MODEL_FONT_SIZE = 26
const EXPORT_VALUE_FONT_SIZE = 22
const EXPORT_X_AXIS_ANGLE = -60
const EXPORT_X_AXIS_HEIGHT = 460
const EXPORT_X_AXIS_LABEL_OFFSET = 16
const EXPORT_LEFT_MARGIN = 100
const EXPORT_RIGHT_MARGIN = 30
const EXPORT_VALUE_LABEL_GAP = 4
const EXPORT_VALUE_CHAR_WIDTH_FACTOR = 0.6
const EXPORT_CHART_HEIGHT = 830

/**
 * @brief 깔끔한 틱 간격 계산 (100K, 200K, 500K, 1M 등)
 * @param {number} max - 데이터 최댓값
 * @param {number} tickCount - 원하는 틱 개수 (기본: 4)
 * @return {Object} { max, interval, ticks }
 */
function _getNiceTokenTicks(max, tickCount = 4) {
  if (max <= 0) return { max: 500000, interval: 100000, ticks: [0, 100000, 200000, 300000, 400000, 500000] }

  const rawInterval = max / tickCount
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawInterval)))
  const residual = rawInterval / magnitude

  // 깔끔한 간격: 1, 2, 5, 10 배수
  let niceInterval
  if (residual <= 1.5) niceInterval = 1 * magnitude
  else if (residual <= 3) niceInterval = 2 * magnitude
  else if (residual <= 7) niceInterval = 5 * magnitude
  else niceInterval = 10 * magnitude

  const niceMax = Math.ceil(max / niceInterval) * niceInterval

  const ticks = []
  for (let i = 0; i <= niceMax; i += niceInterval) {
    ticks.push(i)
  }

  return { max: niceMax, interval: niceInterval, ticks }
}

/**
 * @brief 토큰 사용량을 합산하고 현대 형식의 미상 값을 보존
 * @param {Array} values - 합산할 토큰 값
 * @param {boolean} preserveUnknown - null·undefined를 미상으로 보존할지 여부
 * @return {number|null} 합계 또는 미상
 */
function _sumTokenValues(values, preserveUnknown) {
  if (!preserveUnknown) return values.reduce((sum, value) => sum + (value || 0), 0)
  if (values.length === 0 || values.some(value => value === null || value === undefined)) return null
  return values.reduce((sum, value) => sum + value, 0)
}

/**
 * @brief 커스텀 툴팁 컴포넌트
 * @param {Object} props - { active, payload, t }
 */
function CustomTooltip({ active, payload, t }) {
  if (!active || !payload?.length) return null

  const data = payload[0].payload

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3">
      <p className="font-semibold text-gray-800 dark:text-gray-200 mb-2">{formatModelDisplayName(data.model)}</p>
      <div className="space-y-1 text-sm">
        <p className="text-gray-600 dark:text-gray-400">
          {t('cost.inputTokensShort')}: <span className="font-medium">{data.inputTokens.toLocaleString()}</span> {t('cost.tokens')}
        </p>
        <p className="text-gray-600 dark:text-gray-400">
          {t('cost.outputTokensShort')}: <span className="font-medium">{data.outputTokens.toLocaleString()}</span> {t('cost.tokens')}
        </p>
        <hr className="border-gray-200 dark:border-gray-700 my-1" />
        <p className="text-gray-700 dark:text-gray-300">
          {t('token.total')}: <span className="font-medium">{data.total.toLocaleString()}</span> {t('cost.tokens')}
        </p>
      </div>
    </div>
  )
}

/**
 * @brief 레이블 모드 옵션 (번역 키)
 */
const LABEL_MODES = [
  { id: 'total', labelKey: 'token.total' },
  { id: 'split', labelKey: 'token.inputOutput' },
  { id: 'outputRatio', labelKey: 'token.outputRatio' },
  { id: 'none', labelKey: 'token.hidden' }
]

function TokenKnowledgeCutoffGlowDefs({ darkMode }) {
  const checkerLight = darkMode ? 'rgba(255,255,255,0.20)' : 'rgba(255,255,255,0.24)'
  const checkerDark = darkMode ? 'rgba(0,0,0,0.16)' : 'rgba(0,0,0,0.08)'

  return (
    <defs>
      <filter id="token-post-exam-cutoff-glow" x="-8%" y="-24%" width="116%" height="148%">
        <feGaussianBlur stdDeviation="1.35" />
      </filter>
      <pattern
        id="token-web-service-no-tools-checker"
        patternUnits="userSpaceOnUse"
        width="16"
        height="16"
      >
        <rect x="0" y="0" width="8" height="8" fill={checkerLight} />
        <rect x="8" y="8" width="8" height="8" fill={checkerLight} />
        <rect x="8" y="0" width="8" height="8" fill={checkerDark} />
        <rect x="0" y="8" width="8" height="8" fill={checkerDark} />
      </pattern>
    </defs>
  )
}

function TokenBarShape(props) {
  const { x, y, width, height, fill, fillOpacity, payload, modelMetadata = {}, examMonth = null } = props
  if (!Number.isFinite(x) || !Number.isFinite(y) || width <= 0 || height <= 0) return null

  const color = fill || getModelColor(payload.model)
  const flags = getModelFlags(payload.model, modelMetadata, examMonth)

  return (
    <g>
      {flags.postExamKnowledgeCutoff && (
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          opacity={0.9}
          filter="url(#token-post-exam-cutoff-glow)"
        />
      )}
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={color}
        fillOpacity={fillOpacity}
      />
      {flags.webServiceNoTools && (
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          fill="url(#token-web-service-no-tools-checker)"
        />
      )}
    </g>
  )
}

function formatOutputRatioLabel(entry) {
  if (!Number.isFinite(entry?.outputRatio)) return '-'
  return `${Math.round(entry.outputRatio * 100)}%`
}

function getTokenLabel(entry, mode) {
  if (!entry || mode === 'none') return null

  if (mode === 'total') {
    const totalK = Math.round(entry.total / 1000)
    return `${totalK.toLocaleString()}K`
  }

  if (mode === 'outputRatio') {
    return formatOutputRatioLabel(entry)
  }

  const inputK = Math.round(entry.inputTokens / 1000)
  const outputK = Math.round(entry.outputTokens / 1000)
  return `${inputK.toLocaleString()}K + ${outputK.toLocaleString()}K`
}

/**
 * @brief 내보내기 숫자 레이블의 글자 크기 계산
 * @param {string} label - 표시할 숫자 레이블
 * @param {number} modelCount - 표시할 모델 수
 * @return {number} 내보내기 숫자 레이블 글자 크기
 */
function _getExportValueFontSize(label, modelCount) {
  const slotWidth = (README_EXPORT_WIDTH - EXPORT_LEFT_MARGIN - EXPORT_RIGHT_MARGIN) / modelCount
  const availableWidth = Math.max(1, slotWidth - EXPORT_VALUE_LABEL_GAP)
  const estimatedWidth = label.length * EXPORT_VALUE_FONT_SIZE * EXPORT_VALUE_CHAR_WIDTH_FACTOR
  return estimatedWidth > availableWidth
    ? EXPORT_VALUE_FONT_SIZE * availableWidth / estimatedWidth
    : EXPORT_VALUE_FONT_SIZE
}

/**
 * @brief 커스텀 레이블 렌더러
 * @param {Object} props - Recharts LabelList props
 * @param {string} mode - 'total' | 'split' | 'outputRatio' | 'none'
 * @param {boolean} darkMode - 다크모드 여부
 */
function CustomLabel({ x, y, width, index, mode, chartData, darkMode, exportMode = false }) {
  if (mode === 'none' || index === undefined || !chartData[index]) return null

  const entry = chartData[index]
  const label = getTokenLabel(entry, mode)
  if (!label) return null
  const fontSize = exportMode ? _getExportValueFontSize(label, chartData.length) : 11

  return (
    <text
      className="export-role-value"
      x={x + width / 2}
      y={y - 8}
      textAnchor="middle"
      fill={darkMode ? '#d1d5db' : '#374151'}
      fontSize={fontSize}
      fontWeight="500"
      style={{ ...(exportMode ? { '--export-value-size': `${fontSize}px` } : {}) }}
    >
      {label}
    </text>
  )
}

function CustomMobileLabel({ x, y, width, height, index, mode, chartData, darkMode, exportMode = false }) {
  if (mode === 'none' || index === undefined || !chartData[index]) return null

  const entry = chartData[index]
  const label = getTokenLabel(entry, mode)
  if (!label) return null
  const fontSize = exportMode ? EXPORT_VALUE_FONT_SIZE : 9

  return (
    <text
      className="export-role-value"
      x={x + width + 6}
      y={y + height / 2 + 4}
      textAnchor="start"
      fill={darkMode ? '#d1d5db' : '#374151'}
      fontSize={fontSize}
      fontWeight="500"
      style={{ ...(exportMode ? { fontSize: `${fontSize}px` } : {}) }}
    >
      {label}
    </text>
  )
}

/**
 * @brief 내보내기용 세로 막대 차트 X축 틱 생성
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
 * @brief 모델별 토큰 사용량 스택 바 차트 컴포넌트
 * @param {Object} props - { data, models, subjectFilter, height, title }
 * @param {Object} props.data - tokenUsage 객체 ({ modelName: { total_input_tokens, total_output_tokens, sections, ... } })
 * @param {Array} props.models - 표시할 모델 목록 (null이면 전체)
 * @param {Array} props.subjectFilter - 과목 필터 배열 (빈 배열이면 전체)
 * @param {number} props.height - 차트 높이 (기본: 600)
 * @param {string} props.title - 차트 제목
 */
export default function TokenUsageChart({
  data,
  models = null,
  subjectFilter = [],
  height = 600,
  title,
  modelMetadata = {},
  sectionKeysByModel = {}
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
  const { ref, exportImage, isExporting } = useExportImage({
    exportWidth: README_EXPORT_WIDTH,
    prepareExport,
    exportProfile: 'tokenUsage'
  })
  const [labelMode, setLabelMode] = useState('total')
  const examMonth = exam?.exam_month

  // 모바일 감지
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const renderLabelModeButtons = () => (
    <div className="flex items-center gap-1 mb-4" data-export-hide="true">
      {LABEL_MODES.map(mode => (
        <button
          key={mode.id}
          onClick={() => setLabelMode(mode.id)}
          className={`px-2 py-1 text-xs rounded transition-colors ${
            labelMode === mode.id
              ? 'bg-blue-500 text-white'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
          }`}
        >
          {t(mode.labelKey)}
        </button>
      ))}
    </div>
  )

  // 데이터 변환 및 정렬
  const chartData = useMemo(() => {
    if (!data || typeof data !== 'object') return []

    return Object.entries(data)
      .filter(([model]) => !models || models.includes(model)) // 모델 필터링
      .map(([model, usage]) => {
        let inputTokens, outputTokens, total
        const preserveUnknown = usage.attempts > 1

        if (subjectFilter.length > 0) {
          // 과목 필터 활성화: sections 데이터 필수
          if (!usage.sections) return null // sections 데이터 없으면 제외

          // 선택된 과목들의 토큰만 합산
          const selectedKeys = sectionKeysByModel[model] || Object.keys(usage.sections).filter(sectionKey =>
            subjectFilter.some(subject => sectionKey.startsWith(`${subject}-`) || sectionKey === subject)
          )
          inputTokens = _sumTokenValues(
            selectedKeys.map(sectionKey => usage.sections[sectionKey]?.input_tokens),
            preserveUnknown
          )
          outputTokens = _sumTokenValues(
            selectedKeys.map(sectionKey => usage.sections[sectionKey]?.output_tokens),
            preserveUnknown
          )

          total = inputTokens === null || outputTokens === null
            ? null
            : inputTokens + outputTokens
          if (total <= 0) return null // 해당 과목 데이터 없음
        } else {
          // 전체 토큰 (필터 없음)
          inputTokens = preserveUnknown ? usage.total_input_tokens : (usage.total_input_tokens || 0)
          outputTokens = preserveUnknown ? usage.total_output_tokens : (usage.total_output_tokens || 0)
          if (preserveUnknown) {
            total = usage.total_tokens
            if (inputTokens === null || inputTokens === undefined || outputTokens === null || outputTokens === undefined || total === null || total === undefined) return null
          } else {
            if (Number.isFinite(usage.total_tokens) && usage.total_tokens <= 0) return null
            total = usage.total_tokens || inputTokens + outputTokens
          }
        }

        const outputRatio = inputTokens > 0 ? outputTokens / inputTokens : Infinity

        return { model, inputTokens, outputTokens, total, outputRatio }
      })
      .filter(entry => entry && entry.total > 0)
      .sort((a, b) => {
        if (labelMode === 'outputRatio') {
          if (a.outputRatio !== b.outputRatio) return a.outputRatio - b.outputRatio
        }
        if (a.total !== b.total) return a.total - b.total
        return a.model.localeCompare(b.model)
      })
  }, [data, models, subjectFilter, sectionKeysByModel, labelMode])

  // Y축 최대값 및 틱 계산
  const maxTotal = chartData.length ? Math.max(...chartData.map(d => d.total)) : 0
  const yMax = Math.ceil(maxTotal / 500000) * 500000 || 500000 // 500K 단위로 올림

  // Y축 틱 생성 (900K 간격)
  const yTicks = useMemo(() => {
    const ticks = []
    for (let i = 0; i <= yMax; i += 900000) {
      ticks.push(i)
    }
    return ticks
  }, [yMax])

  // 레이블 렌더러 메모이제이션
  const renderLabel = useCallback((props) => (
    <CustomLabel {...props} mode={labelMode} chartData={chartData} darkMode={darkMode} exportMode={isExporting} />
  ), [labelMode, chartData, darkMode, isExporting])
  const renderMobileLabel = useCallback((props) => (
    <CustomMobileLabel {...props} mode={labelMode} chartData={chartData} darkMode={darkMode} exportMode={isExporting} />
  ), [labelMode, chartData, darkMode, isExporting])
  const renderTokenBarShape = useCallback((props) => (
    <TokenBarShape {...props} modelMetadata={modelMetadata} examMonth={examMonth} darkMode={darkMode} />
  ), [modelMetadata, examMonth, darkMode])

  // 다크모드용 색상
  const axisColor = darkMode ? '#4b5563' : '#e5e7eb'
  const tickColor = darkMode ? '#9ca3af' : '#6b7280'
  const xTickColor = darkMode ? '#d1d5db' : '#374151'
  const cursorColor = darkMode ? 'rgba(55, 65, 81, 0.5)' : '#f3f4f6'

  // 데이터 없음 처리 (모든 훅 호출 후)
  if (!chartData.length) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500 dark:text-gray-400">
        {t('common.noData')}
      </div>
    )
  }

  // 모바일: 가로 막대 차트 (ScoreBarChart 스타일)
  if (isMobile) {
    const mobileHeight = Math.max(300, chartData.length * (isExporting ? 64 : 45) + (isExporting ? 100 : 80))

    // 모바일용 X축 틱 계산 (동적)
    const { max: xMax, ticks: xTicks } = _getNiceTokenTicks(maxTotal)

    return (
      <div ref={ref} className="w-full">
        <div className="flex items-start justify-between mb-4">
          {title && (
            <h3 className="export-role-title text-lg font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
          )}
          <ExportButton
            onClick={() => exportImage(`${t('export.tokenUsage')}.png`)}
            exportKey="token-usage"
          />
        </div>
        {renderLabelModeButtons()}
        <ResponsiveContainer width="100%" height={mobileHeight}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 10, right: 50, left: 5, bottom: 10 }}
          >
            <XAxis
              type="number"
              domain={[0, xMax]}
              ticks={xTicks}
              tickFormatter={(v) => `${(v / 1000).toLocaleString()}K`}
              tick={{ fontSize: 10, fill: tickColor, className: 'export-role-axis-value' }}
              tickLine={false}
              axisLine={{ stroke: axisColor }}
            />
            <YAxis
              type="category"
              dataKey="model"
              width={isExporting ? 220 : 100}
              tickLine={false}
              axisLine={false}
              tick={({ x, y, payload }) => (
                <text
                  className="export-role-model-label"
                  x={x}
                  y={y}
                  dy={4}
                  textAnchor="end"
                  fontSize={10}
                  fill={xTickColor}
                >
                  {getShortModelName(payload.value)}
                </text>
              )}
            />
            <CartesianGrid
              horizontal={false}
              vertical={true}
              stroke={axisColor}
              strokeDasharray="3 3"
            />
            <Tooltip content={<CustomTooltip t={t} />} cursor={{ fill: cursorColor }} />
            <TokenKnowledgeCutoffGlowDefs darkMode={darkMode} />
            {/* 출력 토큰 (좌측, 진한 색) */}
            <Bar
              dataKey="outputTokens"
              stackId="tokens"
              name={t('cost.outputTokensShort')}
              isAnimationActive={false}
              barSize={20}
              shape={renderTokenBarShape}
            >
              {chartData.map((entry, index) => (
                <Cell
                  key={`output-${index}`}
                  fill={getModelColor(entry.model)}
                  fillOpacity={0.9}
                />
              ))}
            </Bar>
            {/* 입력 토큰 (우측, 연한 색) */}
            <Bar
              dataKey="inputTokens"
              stackId="tokens"
              name={t('cost.inputTokensShort')}
              isAnimationActive={false}
              barSize={20}
              shape={renderTokenBarShape}
            >
              {chartData.map((entry, index) => (
                <Cell
                  key={`input-${index}`}
                  fill={getModelColor(entry.model)}
                  fillOpacity={0.5}
                />
              ))}
              <LabelList
                dataKey="total"
                position="right"
                className="export-role-value"
                content={renderMobileLabel}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <BenchmarkNote modelNames={chartData.map(entry => entry.model)} modelMetadata={modelMetadata} />
      </div>
    )
  }

  // 데스크톱: 기존 차트
  return (
    <div ref={ref} className="w-full">
      <div className="flex items-start justify-between mb-2">
        {title && (
          <h3 className="export-role-title text-xl font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
        )}
        <div className="flex items-start gap-2">
          <span className="export-role-watermark hidden text-base text-gray-400 mt-8" data-export-show="true">Github/hehee9</span>
          <ExportButton
            onClick={() => exportImage(`${t('export.tokenUsage')}.png`)}
            exportKey="token-usage"
          />
        </div>
      </div>
      {renderLabelModeButtons()}
      <ResponsiveContainer width="100%" height={isExporting ? exportChartHeight : height}>
        <BarChart
          data={chartData}
          margin={{ top: 30, right: EXPORT_RIGHT_MARGIN, left: isExporting ? EXPORT_LEFT_MARGIN : 20, bottom: isExporting ? 20 : 100 }}
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
            height={isExporting ? exportXAxisHeight : 100}
          />
          <YAxis
            tickFormatter={(v) => `${(v / 1000).toLocaleString()}K`}
            tick={{ fontSize: isExporting ? EXPORT_AXIS_FONT_SIZE : 11, fill: tickColor, className: 'export-role-axis-value' }}
            tickLine={false}
            axisLine={{ stroke: axisColor }}
            domain={[0, yMax]}
            ticks={yTicks}
          />
          <CartesianGrid
            horizontal={true}
            vertical={false}
            stroke={axisColor}
            strokeDasharray="3 3"
          />
          <Tooltip content={<CustomTooltip t={t} />} cursor={{ fill: cursorColor }} />
          <TokenKnowledgeCutoffGlowDefs darkMode={darkMode} />
          {/* 출력 토큰 (하단, 진한 색) */}
          <Bar
            dataKey="outputTokens"
            stackId="tokens"
            name={t('cost.outputTokensShort')}
            isAnimationActive={false}
            shape={renderTokenBarShape}
          >
            {chartData.map((entry, index) => (
              <Cell
                key={`output-${index}`}
                fill={getModelColor(entry.model)}
                fillOpacity={0.9}
              />
            ))}
          </Bar>
          {/* 입력 토큰 (상단, 연한 색) */}
          <Bar
            dataKey="inputTokens"
            stackId="tokens"
            name={t('cost.inputTokensShort')}
            isAnimationActive={false}
            shape={renderTokenBarShape}
          >
            {chartData.map((entry, index) => (
              <Cell
                key={`input-${index}`}
                fill={getModelColor(entry.model)}
                fillOpacity={0.5}
              />
            ))}
            <LabelList
              dataKey="total"
              position="top"
              className="export-role-value"
              content={renderLabel}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <BenchmarkNote modelNames={chartData.map(entry => entry.model)} modelMetadata={modelMetadata} />
    </div>
  )
}
