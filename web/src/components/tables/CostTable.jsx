/**
 * @file CostTable.jsx
 * @brief 모델별 비용 정보 테이블
 */

import { useState, useMemo, useEffect, Fragment } from 'react'
import { useTranslation } from 'react-i18next'
import { getModelColor, getShortModelName } from '@/utils/colorUtils'
import { useExportImage, README_EXPORT_WIDTH } from '@/hooks/useExportImage'
import { BenchmarkNote, ExportButton } from '@/components/common'
import { formatModelDisplayName } from '@/utils/modelMeta'
import { formatAnalysisMetricValue } from '@/utils/analysisMetrics'

/**
 * @brief 정렬 아이콘 컴포넌트
 */
function SortIcon({ columnKey, sortConfig }) {
  if (sortConfig.key !== columnKey) {
    return <span className="text-gray-300 dark:text-gray-600 ml-1">↕</span>
  }
  return (
    <span className="ml-1">
      {sortConfig.direction === 'desc' ? '↓' : '↑'}
    </span>
  )
}

/**
 * @brief 시도별 토큰 수를 화면용 문자열로 변환
 * @param {number|null} value - 토큰 수
 * @return {string} 토큰 수 또는 미상 표시
 */
function _formatAttemptTokens(value) {
  return value === null || value === undefined ? '-' : value.toLocaleString()
}

/**
 * @brief 시도별 비용 계산
 * @param {Object} row - 모델 비용 데이터
 * @param {Object} detail - 시도별 토큰 데이터
 * @return {number|null} 비용 또는 미상
 */
function _getAttemptCost(row, detail) {
  if (
    detail.input_tokens === null || detail.input_tokens === undefined ||
    detail.output_tokens === null || detail.output_tokens === undefined ||
    row.inputPrice === null || row.inputPrice === undefined ||
    row.outputPrice === null || row.outputPrice === undefined
  ) {
    return null
  }
  return (
    detail.input_tokens * (row.inputPrice / 1000000) +
    detail.output_tokens * (row.outputPrice / 1000000)
  )
}

/**
 * @brief 비용을 화면용 문자열로 변환
 * @param {number|null} value - 비용
 * @return {string} 비용 또는 미상 표시
 */
function _formatAttemptCost(value) {
  return value === null || value === undefined ? '-' : `$${value.toFixed(4)}`
}

/**
 * @brief 반복 실행의 시도별 토큰 상세 표시
 * @param {Object} props - 비용 데이터와 번역 함수
 */
function AttemptDetails({ data, t }) {
  const rows = data.filter(row => row.attemptDetails?.length)
  if (!rows.length) return null

  return (
    <div className="mt-4 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">{t('cost.attemptDetails')}</h4>
      <div className="overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead className="bg-gray-50 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
            <tr>
              <th className="px-2 py-1 text-left">{t('table.model')}</th>
              <th className="px-2 py-1 text-right">{t('cost.attempt')}</th>
              <th className="px-2 py-1 text-right">{t('table.inputTokens')}</th>
              <th className="px-2 py-1 text-right">{t('table.outputTokens')}</th>
              <th className="px-2 py-1 text-right">{t('token.total')}</th>
              <th className="px-2 py-1 text-right">{t('cost.attemptCost')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.flatMap(row => row.attemptDetails.map(detail => (
              <tr key={`${row.model}-${detail.attempt}`} className="border-t border-gray-100 dark:border-gray-700">
                <td className="px-2 py-1 text-gray-700 dark:text-gray-300">{formatModelDisplayName(row.model)}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{detail.attempt}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{_formatAttemptTokens(detail.input_tokens)}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{_formatAttemptTokens(detail.output_tokens)}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{_formatAttemptTokens(detail.total_tokens)}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{_formatAttemptCost(_getAttemptCost(row, detail))}</td>
              </tr>
            ))) }
            {rows.map(row => row.attemptTotals && (
              <tr key={`${row.model}-total`} className="border-t border-gray-200 dark:border-gray-600 font-semibold">
                <td className="px-2 py-1 text-gray-700 dark:text-gray-300">{formatModelDisplayName(row.model)}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{t('cost.attemptTotal')}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{_formatAttemptTokens(row.attemptTotals.input_tokens)}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{_formatAttemptTokens(row.attemptTotals.output_tokens)}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{_formatAttemptTokens(row.attemptTotals.total_tokens)}</td>
                <td className="px-2 py-1 text-right text-gray-600 dark:text-gray-400">{_formatAttemptCost(_getAttemptCost(row, row.attemptTotals))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/**
 * @brief 비용 테이블 컴포넌트
 * @param {Object} props - { data, title }
 * @param {Array} props.data - getCostData() 결과
 * @param {string} props.title - 테이블 제목
 */
export default function CostTable({ data, title, showDetail = false, onToggleDetail }) {
  const { t, i18n } = useTranslation()
  const locale = i18n.language === 'en' ? 'en-US' : 'ko-KR'
  const [sortConfig, setSortConfig] = useState({
    key: 'efficiency',
    direction: 'desc'
  })
  const [showHiddenModels, setShowHiddenModels] = useState(false)
  const { ref, exportImage, isExporting } = useExportImage({
    exportWidth: README_EXPORT_WIDTH,
    exportProfile: 'costTable'
  })
  const isRepeatedRun = data?.some(row => row.attempts > 1)

  // 모바일 감지
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const sortedData = useMemo(() => {
    if (!data?.length) return []
    return [...data].sort((a, b) => {
      const aVal = a[sortConfig.key] ?? 0
      const bVal = b[sortConfig.key] ?? 0
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1
      return 0
    })
  }, [data, sortConfig])

  /** @brief 토큰 정보 유무로 모델 분리 */
  const { withTokens, withoutTokens } = useMemo(() => {
    const withTokens = isRepeatedRun
      ? sortedData.filter(row => row.inputTokens !== null || row.outputTokens !== null)
      : sortedData.filter(row => row.inputTokens > 0 || row.outputTokens > 0)
    const withoutTokens = isRepeatedRun
      ? sortedData.filter(row => row.inputTokens === null && row.outputTokens === null)
      : sortedData.filter(row => row.inputTokens <= 0 && row.outputTokens <= 0)
    return { withTokens, withoutTokens }
  }, [isRepeatedRun, sortedData])

  function handleSort(key) {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }))
  }

  if (!data?.length) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500 dark:text-gray-400">
        {t('common.noCostData')}
      </div>
    )
  }

  const detailControl = isRepeatedRun && (
    <button
      type="button"
      className="mt-3 px-3 py-1.5 text-sm rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
      onClick={onToggleDetail}
      aria-expanded={showDetail}
      data-export-hide="true"
    >
      {showDetail ? t('cost.hideDetail') : t('cost.showDetail')}
    </button>
  )

  // 모바일: 전치 테이블 (모델을 열로, 항목을 행으로)
  if (isMobile) {
    const displayData = withTokens // 토큰 정보 있는 모델만 표시

    const rows = [
      { key: 'inputPrice', label: t('table.inputPrice'), format: (v) => isRepeatedRun ? (v == null ? '-' : `$${v.toFixed(2)}`) : (v ? `$${v.toFixed(2)}` : '-') },
      { key: 'outputPrice', label: t('table.outputPrice'), format: (v) => isRepeatedRun ? (v == null ? '-' : `$${v.toFixed(2)}`) : (v ? `$${v.toFixed(2)}` : '-') },
      { key: 'inputTokens', label: isRepeatedRun ? t('table.inputTokensAverage') : t('table.inputTokens'), format: (v) => isRepeatedRun ? (v == null ? '-' : `${(v / 1000).toFixed(1)}K`) : (v > 0 ? `${(v / 1000).toFixed(1)}K` : '-') },
      { key: 'outputTokens', label: isRepeatedRun ? t('table.outputTokensAverage') : t('table.outputTokens'), format: (v) => isRepeatedRun ? (v == null ? '-' : `${(v / 1000).toFixed(1)}K`) : (v > 0 ? `${(v / 1000).toFixed(1)}K` : '-') },
      { key: 'totalCost', label: isRepeatedRun ? t('table.averageCost') : t('table.totalCost'), format: (v) => isRepeatedRun ? (v == null ? '-' : `$${v.toFixed(4)}`) : (v > 0 ? `$${v.toFixed(4)}` : '-') },
      { key: 'estimatedSeconds', label: t('analysis.estimatedTime'), format: (v) => formatAnalysisMetricValue('time', v, locale) },
      { key: 'score', label: t('table.score'), format: (v) => v?.toFixed(1) ?? '-' },
      { key: 'efficiency', label: t('table.efficiency'), format: (v) => v > 0 ? v.toFixed(1) : '-', bold: true }
    ]

    return (
      <div ref={ref} className="w-full">
        <div className="flex items-start justify-between mb-4">
          {title && (
            <h3 className="export-role-title text-lg font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
          )}
          <ExportButton
            onClick={() => exportImage(`${t('export.costAnalysis')}.png`)}
            exportKey="cost-table"
          />
        </div>
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-x-auto">
          <table className="export-role-table-value min-w-max text-sm">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="px-3 py-2 text-left font-semibold text-gray-700 dark:text-gray-300 sticky left-0 bg-gray-50 dark:bg-gray-700 z-10">
                  {t('table.model')}
                </th>
                {displayData.map(d => (
                  <th key={d.model} className="px-3 py-2 text-center font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
                    <div className="flex items-center justify-center gap-1">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: getModelColor(d.model) }}
                      />
                      <span className="truncate max-w-[80px]">{getShortModelName(d.model)}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.key} className="border-t border-gray-100 dark:border-gray-700">
                  <td className="px-3 py-2 text-gray-600 dark:text-gray-400 font-medium whitespace-nowrap sticky left-0 bg-white dark:bg-gray-800 z-10">
                    {row.label}
                  </td>
                  {displayData.map(d => (
                    <td
                      key={d.model}
                      className={`px-3 py-2 text-center whitespace-nowrap ${
                        row.bold
                          ? 'font-bold text-blue-600 dark:text-blue-400'
                          : 'text-gray-600 dark:text-gray-400'
                      }`}
                    >
                      {row.format(d[row.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          * {t('cost.efficiencyFormula')}
        </p>
        {detailControl}
        {showDetail && <AttemptDetails data={sortedData} t={t} />}
        <BenchmarkNote className="mt-2 text-sm text-gray-500 dark:text-gray-400" modelNames={displayData.map(row => row.model)} />
      </div>
    )
  }

  // 데스크톱: 기존 테이블
  const columns = [
    { key: 'model', label: t('table.model'), align: 'left' },
    { key: 'inputPrice', label: t('table.inputPrice'), align: 'right' },
    { key: 'outputPrice', label: t('table.outputPrice'), align: 'right' },
    { key: 'inputTokens', label: isRepeatedRun ? t('table.inputTokensAverage') : t('table.inputTokens'), align: 'right' },
    { key: 'outputTokens', label: isRepeatedRun ? t('table.outputTokensAverage') : t('table.outputTokens'), align: 'right' },
    { key: 'totalCost', label: isRepeatedRun ? t('table.averageCost') : t('table.totalCost'), align: 'right' },
    { key: 'estimatedSeconds', label: t('analysis.estimatedTime'), align: 'right' },
    { key: 'score', label: t('table.score'), align: 'right' },
    { key: 'efficiency', label: t('table.efficiency'), align: 'right', bold: true }
  ]

  return (
    <div ref={ref} className="w-full">
      <div className="flex items-start justify-between mb-4">
        {title && (
          <h3 className="export-role-title text-xl font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
        )}
        <div className="flex items-start gap-2">
          <span className="hidden text-base text-gray-400 mt-8" data-export-show="true">Github/hehee9</span>
          <ExportButton
            onClick={() => exportImage(`${t('export.costAnalysis')}.png`)}
            exportKey="cost-table"
          />
        </div>
      </div>
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-x-auto">
        <table className="export-role-table-value w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-700">
            <tr>
              {columns.map(col => (
                <th
                  key={col.key}
                  className={`export-role-table-head px-3 py-2 font-semibold text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors ${isExporting ? 'whitespace-normal' : 'whitespace-nowrap'} ${
                    col.align === 'right' ? 'text-right' : 'text-left'
                  } ${col.bold ? 'font-bold' : ''}`}
                  onClick={() => handleSort(col.key)}
                >
                  {col.label}
                  <SortIcon columnKey={col.key} sortConfig={sortConfig} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* 토큰 정보 있는 모델 (항상 표시) */}
            {withTokens.map(row => (
              <tr
                key={row.model}
                className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                <td className="px-3 py-2 text-gray-800 dark:text-gray-200">
                  <span
                    className="inline-block w-3 h-3 rounded-full mr-2"
                    style={{ backgroundColor: getModelColor(row.model) }}
                  />
                  {formatModelDisplayName(row.model)}
                </td>
                <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                  {isRepeatedRun
                    ? (row.inputPrice == null ? '-' : `$${row.inputPrice.toFixed(2)}`)
                    : `$${row.inputPrice?.toFixed(2) ?? '-'}`}
                </td>
                <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                  {isRepeatedRun
                    ? (row.outputPrice == null ? '-' : `$${row.outputPrice.toFixed(2)}`)
                    : `$${row.outputPrice?.toFixed(2) ?? '-'}`}
                </td>
                <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-500">
                  {isRepeatedRun
                    ? (row.inputTokens == null ? '-' : `${(row.inputTokens / 1000).toFixed(1)}K`)
                    : (row.inputTokens > 0 ? `${(row.inputTokens / 1000).toFixed(1)}K` : '-')}
                </td>
                <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-500">
                  {isRepeatedRun
                    ? (row.outputTokens == null ? '-' : `${(row.outputTokens / 1000).toFixed(1)}K`)
                    : (row.outputTokens > 0 ? `${(row.outputTokens / 1000).toFixed(1)}K` : '-')}
                </td>
                <td className="px-3 py-2 text-right font-medium text-gray-800 dark:text-gray-200">
                  {isRepeatedRun
                    ? (row.totalCost == null ? '-' : `$${row.totalCost.toFixed(4)}`)
                    : (row.totalCost > 0 ? `$${row.totalCost.toFixed(4)}` : '-')}
                </td>
                <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                  {formatAnalysisMetricValue('time', row.estimatedSeconds, locale)}
                </td>
                <td className="px-3 py-2 text-right text-gray-800 dark:text-gray-200">
                  {row.score?.toFixed(1) ?? '-'}
                </td>
                <td className="px-3 py-2 text-right font-bold text-blue-600 dark:text-blue-400">
                  {row.efficiency > 0
                    ? row.efficiency.toFixed(1)
                    : '-'}
                </td>
              </tr>
            ))}

            {/* 토큰 정보 없는 모델 (접기/펼치기) */}
            {withoutTokens.length > 0 && (
              <Fragment>
                <tr
                  className="border-t border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
                  onClick={() => setShowHiddenModels(prev => !prev)}
                >
                  <td colSpan={columns.length} className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">
                    <span className="mr-2">{showHiddenModels ? '▼' : '▶'}</span>
                    {t('cost.noTokenInfo')} ({withoutTokens.length})
                  </td>
                </tr>
                {showHiddenModels && withoutTokens.map(row => (
                  <tr
                    key={row.model}
                    className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors bg-gray-50/50 dark:bg-gray-800/50"
                  >
                    <td className="px-3 py-2 text-gray-800 dark:text-gray-200">
                      <span
                        className="inline-block w-3 h-3 rounded-full mr-2"
                        style={{ backgroundColor: getModelColor(row.model) }}
                      />
                      {formatModelDisplayName(row.model)}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                      {isRepeatedRun
                        ? (row.inputPrice == null ? '-' : `$${row.inputPrice.toFixed(2)}`)
                        : `$${row.inputPrice?.toFixed(2) ?? '-'}`}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                      {isRepeatedRun
                        ? (row.outputPrice == null ? '-' : `$${row.outputPrice.toFixed(2)}`)
                        : `$${row.outputPrice?.toFixed(2) ?? '-'}`}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-500">-</td>
                    <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-500">-</td>
                    <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-500">-</td>
                    <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-500">-</td>
                    <td className="px-3 py-2 text-right text-gray-800 dark:text-gray-200">
                      {row.score?.toFixed(1) ?? '-'}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-gray-400 dark:text-gray-500">
                      -
                    </td>
                  </tr>
                ))}
              </Fragment>
            )}
          </tbody>
        </table>
      </div>

      <p className="export-role-note mt-2 text-xs text-gray-500 dark:text-gray-400">
        * {t('cost.efficiencyFormula')}
      </p>
      {detailControl}
      {showDetail && <AttemptDetails data={sortedData} t={t} />}
      <BenchmarkNote className="mt-2 text-sm text-gray-500 dark:text-gray-400" modelNames={sortedData.map(row => row.model)} />
    </div>
  )
}
