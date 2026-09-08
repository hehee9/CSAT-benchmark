/**
 * @file ChoiceSelectionChart.jsx
 * @brief 문항별 선지 선택률 차트 컴포넌트
 */

import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LabelList
} from 'recharts'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/hooks/useTheme'
import { useExportImage, README_EXPORT_WIDTH } from '@/hooks/useExportImage'
import { BenchmarkNote, ExportButton } from '@/components/common'

/**
 * @brief 선택률에 따른 색상 강도 계산
 * @param {number} percentage - 선택률 (0-100)
 * @param {boolean} isCorrect - 정답 여부
 * @param {boolean} darkMode - 다크모드 여부
 * @return {string} HSL 색상 문자열
 */
function _getChoiceColor(percentage, isCorrect, darkMode = false) {
  const baseHue = isCorrect ? 120 : 0  // 초록 or 빨강
  const saturation = darkMode ? 60 : 50
  // 라이트: 선택률 0% = 85%, 100% = 40%
  // 다크: 선택률 0% = 25%, 100% = 50%
  const lightness = darkMode
    ? 25 + (percentage / 100) * 25
    : 85 - (percentage / 100) * 45
  return `hsl(${baseHue}, ${saturation}%, ${lightness}%)`
}

/**
 * @brief 커스텀 Bar Shape 컴포넌트 생성 함수 (색상 동적 적용)
 * @param {boolean} darkMode - 다크모드 여부
 * @return {function} Recharts Bar shape 함수
 */
function createCustomBar(darkMode) {
  return function CustomBar(props) {
    const { x, y, width, height, payload, dataKey } = props
    const choiceNum = parseInt(dataKey.replace('choice', '').replace('Pct', ''))
    const isCorrect = payload.correctAnswer === choiceNum
    const percentage = payload[dataKey] || 0
    const fill = _getChoiceColor(percentage, isCorrect, darkMode)

    return <rect x={x} y={y} width={width} height={height} fill={fill} />
  }
}

/**
 * @brief 커스텀 툴팁 컴포넌트
 * @param {Object} props - { active, payload, label, t }
 */
function CustomTooltip({ active, payload, label, t }) {
  if (!active || !payload?.length) return null
  const item = payload[0]?.payload
  if (!item) return null

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3">
      <p className="font-semibold mb-2 text-gray-800 dark:text-gray-200">
        {t('choice.questionNum', { num: label })} ({t('choice.correctAnswer', { answer: item.correctAnswer })})
      </p>
      <div className="space-y-1 text-sm">
        {[1, 2, 3, 4, 5].map(i => {
          const pct = item[`choice${i}Pct`]
          const count = item[`choice${i}`]
          const isCorrect = item.correctAnswer === i
          return (
            <div key={i} className={isCorrect ? 'text-green-600 dark:text-green-400 font-medium' : 'text-gray-600 dark:text-gray-400'}>
              {i}: {pct.toFixed(1)}% ({t('choice.modelCount', { count })}) {isCorrect && '✓'}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * @brief 문항별 선지 선택률 차트 컴포넌트 (세로 레이아웃)
 * @param {Object} props - { data, title }
 * @param {Array} props.data - transformToChoiceData 결과
 * @param {string} props.title - 차트 제목
 */
export default function ChoiceSelectionChart({ data, title }) {
  const { t } = useTranslation()
  const { isDark: darkMode } = useTheme()
  const { ref, exportImage, isExporting } = useExportImage({
    exportWidth: README_EXPORT_WIDTH,
    exportProfile: 'choiceSelection'
  })

  // 모바일 감지
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
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

  // 문항 수에 따른 동적 높이 (각 문항당 80px로 증가)
  const chartHeight = Math.max(400, data.length * (isExporting ? 150 : 80) + 100)

  // 다크모드용 색상
  const gridColor = darkMode ? '#374151' : '#e5e7eb'
  const tickColor = darkMode ? '#9ca3af' : '#6b7280'
  const labelColor = darkMode ? '#d1d5db' : '#374151'
  const cursorColor = darkMode ? 'rgba(55, 65, 81, 0.5)' : '#f3f4f6'

  // CustomBar 생성
  const CustomBarShape = createCustomBar(darkMode)

  return (
    <div ref={ref} className="w-full">
      <div className="flex items-start justify-between mb-4">
        {title && (
          <h3 className="export-role-title text-xl font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
        )}
        <div className="flex items-start gap-2">
          <span className="export-role-watermark hidden text-base text-gray-400 mt-8" data-export-show="true">Github/hehee9</span>
          <ExportButton
            onClick={() => exportImage(`${t('export.choiceRate')}.png`)}
            exportKey="choice-selection"
          />
        </div>
      </div>

      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 20, right: isExporting ? 80 : 30, left: isMobile ? 10 : 60, bottom: 20 }}
          barCategoryGap="20%"
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={gridColor} />
          <XAxis
            type="number"
            domain={[0, 100]}
            tickFormatter={(v) => `${v}%`}
            tick={{ fontSize: isExporting ? 24 : 16, fill: tickColor, className: 'export-role-axis-value' }}
            axisLine={{ stroke: gridColor }}
            tickLine={{ stroke: gridColor }}
          />
          <YAxis
            type="category"
            dataKey="question"
            tickFormatter={(v) => `${v}`}
            width={isExporting ? 80 : 50}
            tick={{ fontSize: isExporting ? 24 : 16, fill: tickColor, className: 'export-role-axis-label' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip t={t} />} cursor={{ fill: cursorColor }} />
          {/* 5개의 Bar - 각 선지별 */}
          <Bar dataKey="choice1Pct" name="1" shape={CustomBarShape} barSize={isExporting ? 20 : 10} isAnimationActive={false}>
            <LabelList className="export-role-value" dataKey="choice1Pct" position="right" formatter={(v) => v > 0 ? `${v.toFixed(0)}` : ''} style={{ fontSize: isExporting ? 24 : 10, fill: labelColor }} />
          </Bar>
          <Bar dataKey="choice2Pct" name="2" shape={CustomBarShape} barSize={isExporting ? 20 : 10} isAnimationActive={false}>
            <LabelList className="export-role-value" dataKey="choice2Pct" position="right" formatter={(v) => v > 0 ? `${v.toFixed(0)}` : ''} style={{ fontSize: isExporting ? 24 : 10, fill: labelColor }} />
          </Bar>
          <Bar dataKey="choice3Pct" name="3" shape={CustomBarShape} barSize={isExporting ? 20 : 10} isAnimationActive={false}>
            <LabelList className="export-role-value" dataKey="choice3Pct" position="right" formatter={(v) => v > 0 ? `${v.toFixed(0)}` : ''} style={{ fontSize: isExporting ? 24 : 10, fill: labelColor }} />
          </Bar>
          <Bar dataKey="choice4Pct" name="4" shape={CustomBarShape} barSize={isExporting ? 20 : 10} isAnimationActive={false}>
            <LabelList className="export-role-value" dataKey="choice4Pct" position="right" formatter={(v) => v > 0 ? `${v.toFixed(0)}` : ''} style={{ fontSize: isExporting ? 24 : 10, fill: labelColor }} />
          </Bar>
          <Bar dataKey="choice5Pct" name="5" shape={CustomBarShape} barSize={isExporting ? 20 : 10} isAnimationActive={false}>
            <LabelList className="export-role-value" dataKey="choice5Pct" position="right" formatter={(v) => v > 0 ? `${v.toFixed(0)}` : ''} style={{ fontSize: isExporting ? 24 : 10, fill: labelColor }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* 범례 */}
      <div className="export-role-legend flex flex-wrap gap-4 mt-4 text-sm text-gray-600 dark:text-gray-400">
        <div className="flex items-center gap-1">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: darkMode ? 'hsl(120, 60%, 40%)' : 'hsl(120, 50%, 50%)' }} />
          <span>{t('choice.legend.correct')}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: darkMode ? 'hsl(0, 60%, 40%)' : 'hsl(0, 50%, 75%)' }} />
          <span>{t('choice.legend.incorrect')}</span>
        </div>
      </div>
      <BenchmarkNote />
    </div>
  )
}
