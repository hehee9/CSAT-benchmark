/**
 * @file ScoreTable.jsx
 * @brief 시험 정의에 맞춘 모델별 점수 테이블
 */

import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { toPng } from 'html-to-image'
import JSZip from 'jszip'
import { getModelColor } from '@/utils/colorUtils'
import {
  useExportImage,
  README_EXPORT_WIDTH,
  applyExportProfile,
  getExportFontEmbedCSS
} from '@/hooks/useExportImage'
import { useData } from '@/hooks/useData'
import { BenchmarkNote, ExportButton } from '@/components/common'
import { formatModelDisplayName } from '@/utils/modelMeta'

const MOBILE_BREAKPOINT = 768
const SUBJECT_I18N_KEYS = {
  '공통': 'subjects.common',
  '화작': 'subjects.hwajak',
  '언매': 'subjects.unmae',
  '확통': 'subjects.hwakton',
  '미적': 'subjects.mijeok',
  '기하': 'subjects.giha',
  '물리1': 'subjects.physics1',
  '물리2': 'subjects.physics2',
  '화학1': 'subjects.chemistry1',
  '화학2': 'subjects.chemistry2',
  '생명1': 'subjects.biology1',
  '생명2': 'subjects.biology2',
  '지구1': 'subjects.earthScience1',
  '지구2': 'subjects.earthScience2',
  '생활과윤리': 'subjects.lifeEthics',
  '윤리와사상': 'subjects.ethicsAndThought',
  '한국지리': 'subjects.koreanGeography',
  '세계지리': 'subjects.worldGeography',
  '동아시아사': 'subjects.eastAsianHistory',
  '세계사': 'subjects.worldHistory',
  '경제': 'subjects.economics',
  '정치와법': 'subjects.politicsAndLaw',
  '사회문화': 'subjects.society'
}

/**
 * @brief 점수 셀
 * @param {Object} props - 점수와 만점
 */
function ScoreCell({ score, maxScore, decimals = 1 }) {
  if (score == null) return <span>-</span>
  const isPerfect = maxScore > 0 && score >= maxScore
  const displayScore = Number.isInteger(score) ? score : score.toFixed(decimals)
  return <span className={`export-role-table-value ${isPerfect ? 'text-red-600 dark:text-red-400 font-bold' : ''}`}>{displayScore}</span>
}

/**
 * @brief 정렬 아이콘
 */
function SortIcon({ columnKey, sortConfig }) {
  if (sortConfig.key !== columnKey) return <span className="text-gray-300 dark:text-gray-600 ml-1">↕</span>
  return <span className="ml-1">{sortConfig.direction === 'desc' ? '↓' : '↑'}</span>
}

/**
 * @brief 긴 모델명 표시
 * @param {string} name - 모델명
 * @return {React.ReactNode} 표시용 모델명
 */
function _formatModelName(name) {
  const displayName = formatModelDisplayName(name)
  if (displayName.length <= 25) return displayName
  const parenIndex = displayName.indexOf('(')
  if (parenIndex > 0) {
    return <>{displayName.slice(0, parenIndex).trim()}<br /><span className="text-sm">{displayName.slice(parenIndex)}</span></>
  }
  return displayName
}

/**
 * @brief 점수 기준에 따른 그룹 점수 추출
 * @param {Object} detail - 그룹 상세 점수
 * @param {string} scoreBasis - normalized 또는 raw
 * @return {number} 그룹 점수
 */
function _getGroupScore(detail, scoreBasis) {
  return scoreBasis === 'raw' ? detail.rawTotal : detail.normalizedTotal
}

/**
 * @brief 점수 기준에 따른 그룹 만점 추출
 * @param {Object} detail - 그룹 상세 점수
 * @param {string} scoreBasis - normalized 또는 raw
 * @return {number} 그룹 만점
 */
function _getGroupMaxScore(detail, scoreBasis) {
  return scoreBasis === 'raw' ? detail.rawMaxScore : detail.normalizedMaxScore
}

/**
 * @brief 그룹명 번역
 * @param {Object} group - 그룹 상세 정보
 * @param {function} t - 번역 함수
 * @return {string} 화면에 표시할 그룹명
 */
function _getGroupLabel(group, t) {
  const translationKeys = {
    '국어': 'table.korean',
    '수학': 'table.math',
    '영어': 'table.english',
    '한국사': 'table.history',
    '탐구': 'table.exploration'
  }
  const key = translationKeys[group.group]
  return key ? t(key) : group.group
}

/**
 * @brief 데이터에 포함된 시험 그룹을 순서대로 추출
 * @param {Array} data - 점수 배열
 * @param {Object|null} exam - 시험 매니페스트
 * @return {Array} 그룹 상세 배열
 */
function _getGroups(data, exam) {
  const manifestSections = exam?.sections || []
  if (manifestSections.length > 0) {
    const groups = []
    const byGroup = new Map()
    manifestSections.forEach(section => {
      if (!byGroup.has(section.group)) {
        const detail = data[0]?.groupDetails?.find(item => item.group === section.group)
        const group = detail
          ? { ...detail, sections: [] }
          : { group: section.group, sections: [], normalizedMaxScore: 0, rawMaxScore: 0 }
        byGroup.set(section.group, group)
        groups.push(group)
      }
      byGroup.get(section.group).sections.push(section)
    })
    return groups
  }

  const groups = []
  const seen = new Set()
  data.forEach(row => {
    row.groupDetails?.forEach(detail => {
      if (!seen.has(detail.group)) {
        seen.add(detail.group)
        groups.push(detail)
      }
    })
  })
  return groups
}

/**
 * @brief 세부 열을 표시할 그룹인지 확인
 * @param {string} group - 그룹명
 * @return {boolean}
 */
function _hasDetailColumns(group) {
  return group === '국어' || group === '수학' || group === '탐구'
}

/**
 * @brief 매니페스트 섹션의 표 레이블 생성
 * @param {Object} section - 시험 섹션
 * @param {function} t - 번역 함수
 * @return {string}
 */
function _getSectionLabel(section, t) {
  const name = section.group === '탐구' ? section.subject : section.section
  return SUBJECT_I18N_KEYS[name] ? t(SUBJECT_I18N_KEYS[name]) : name
}

/**
 * @brief 모델별 점수 정렬값 추출
 * @param {Object} row - 모델 점수
 * @param {string} key - 정렬 키
 * @param {string} scoreBasis - 점수 기준
 * @return {number|string} 정렬값
 */
function _getSortValue(row, key, scoreBasis) {
  if (key === 'model') return row.model
  if (key === 'total') return row.total
  if (key.startsWith('group:')) {
    const detail = row.groupDetails?.find(item => item.group === key.slice(6))
    return detail ? _getGroupScore(detail, scoreBasis) : 0
  }
  if (key.startsWith('section:')) {
    const target = key.slice(8)
    return row.sectionScores?.find(section => section.target === target)?.score ?? 0
  }
  return 0
}

/**
 * @brief 모바일 카드 점수 항목
 */
function ScoreItem({ label, score, max }) {
  return (
    <div className="text-center p-2 bg-gray-50 dark:bg-gray-700 rounded">
      <div className="export-role-table-head text-xs text-gray-500 dark:text-gray-400">{label}</div>
      <div className={`export-role-table-value font-medium ${max > 0 && score >= max ? 'text-red-600 dark:text-red-400' : 'text-gray-800 dark:text-gray-200'}`}>
        {score != null ? (Number.isInteger(score) ? score : score.toFixed(1)) : '-'}
      </div>
    </div>
  )
}

/**
 * @brief 모바일 점수 카드 PNG 캡처
 * @param {HTMLElement} card - 캡처할 카드
 * @param {string} backgroundColor - 캡처 배경색
 * @return {Promise<string>} PNG 데이터 URL
 */
async function _captureScoreCard(card, backgroundColor) {
  const profileCleanup = applyExportProfile(card, 'scoreCard')
  try {
    await document.fonts.ready
    const fontEmbedCSS = await getExportFontEmbedCSS(card)
    return await toPng(card, {
      backgroundColor,
      pixelRatio: 2,
      fontEmbedCSS,
      preferredFontFormat: 'woff2',
      style: { padding: '16px' }
    })
  } finally {
    profileCleanup()
  }
}

/**
 * @brief 모바일 카드 뷰
 */
function CardView({ data, groups, maxScore, scoreBasis, hoveredModel, onModelHover, t, cardRefs }) {
  const groupLabel = group => ({
    '국어': t('table.korean'),
    '수학': t('table.math'),
    '영어': t('table.english'),
    '한국사': t('table.history'),
    '탐구': t('table.exploration')
  }[group] || group)
  return (
    <div className="space-y-3">
      {data.map((row, index) => {
        const isHovered = hoveredModel === row.model
        return (
          <div
            key={row.model}
            ref={cardRefs ? element => { cardRefs.current[index] = element } : undefined}
            className={`bg-white dark:bg-gray-800 rounded-lg p-4 border transition-all ${isHovered ? 'border-blue-400 dark:border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800' : 'border-gray-200 dark:border-gray-700'}`}
            onTouchStart={() => onModelHover?.(row.model)}
            onTouchEnd={() => onModelHover?.(null)}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: getModelColor(row.model) }} />
                <span className="export-role-table-model font-semibold text-gray-800 dark:text-gray-200">{_formatModelName(row.model)}</span>
              </div>
              <span className="export-role-table-head text-sm text-gray-400 dark:text-gray-500 shrink-0">#{index + 1}</span>
            </div>
            <div className="text-center mb-3 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg">
              <span className={`export-role-table-value text-3xl font-bold ${row.total >= maxScore ? 'text-red-600 dark:text-red-400' : 'text-gray-800 dark:text-gray-200'}`}>
                {row.total.toFixed(1)}
              </span>
              <span className="export-role-table-head text-sm text-gray-500 dark:text-gray-400 ml-1">/ {maxScore}</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
              {groups.map(group => (
                <ScoreItem
                  key={group.group}
                  label={groupLabel(group.group)}
                  score={_getGroupScore(row.groupDetails?.find(detail => detail.group === group.group) || group, scoreBasis)}
                  max={_getGroupMaxScore(group, scoreBasis)}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/**
 * @brief 점수 테이블 컴포넌트
 * @param {Object} props - 테이블 상태와 콜백
 */
export default function ScoreTable({ data, onRowClick, title, showDetail = false, onToggleDetail, maxScore = 450, hoveredModel, onModelHover, scoreBasis = 'normalized' }) {
  const { t } = useTranslation()
  const { exam } = useData()
  const [sortConfig, setSortConfig] = useState({ key: 'total', direction: 'desc' })
  const [isMobile, setIsMobile] = useState(false)
  const [showExportOptions, setShowExportOptions] = useState(false)
  const { ref, exportImage } = useExportImage({
    exportWidth: README_EXPORT_WIDTH,
    exportProfile: 'scoreTable'
  })
  const cardRefs = useRef([])
  const exportDropdownRef = useRef(null)

  useEffect(() => {
    const checkWidth = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    checkWidth()
    window.addEventListener('resize', checkWidth)
    return () => window.removeEventListener('resize', checkWidth)
  }, [])

  useEffect(() => {
    const handleClickOutside = event => {
      if (exportDropdownRef.current && !exportDropdownRef.current.contains(event.target)) setShowExportOptions(false)
    }
    if (showExportOptions) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showExportOptions])

  const groups = useMemo(() => _getGroups(data || [], exam), [data, exam])
  const sortedData = useMemo(() => [...(data || [])].sort((a, b) => {
    const aValue = _getSortValue(a, sortConfig.key, scoreBasis)
    const bValue = _getSortValue(b, sortConfig.key, scoreBasis)
    if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1
    if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1
    return 0
  }), [data, sortConfig, scoreBasis])

  function handleSort(key) {
    setSortConfig(prev => ({ key, direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc' }))
  }

  const exportMultipleImages = useCallback(async () => {
    setShowExportOptions(false)
    const backgroundColor = document.documentElement.classList.contains('dark') ? '#111827' : '#ffffff'
    for (let index = 0; index < cardRefs.current.length; index++) {
      const card = cardRefs.current[index]
      if (!card) continue
      const dataUrl = await _captureScoreCard(card, backgroundColor)
      const link = document.createElement('a')
      link.download = `${sortedData[index]?.model || `card_${index + 1}`}.png`
      link.href = dataUrl
      link.click()
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }, [sortedData])

  const exportAsZip = useCallback(async () => {
    setShowExportOptions(false)
    const backgroundColor = document.documentElement.classList.contains('dark') ? '#111827' : '#ffffff'
    const zip = new JSZip()
    for (let index = 0; index < cardRefs.current.length; index++) {
      const card = cardRefs.current[index]
      if (!card) continue
      const dataUrl = await _captureScoreCard(card, backgroundColor)
      zip.file(`${sortedData[index]?.model || `card_${index + 1}`}.png`, dataUrl.split(',')[1], { base64: true })
    }
    const blob = await zip.generateAsync({ type: 'blob' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${t('charts.scoreTable')}.zip`
    link.click()
    URL.revokeObjectURL(link.href)
  }, [sortedData, t])

  if (!data?.length) return <div className="flex items-center justify-center h-48 text-gray-500 dark:text-gray-400">{t('common.noData')}</div>

  return (
    <div ref={ref} className="w-full">
      <div className="flex items-start justify-between mb-4">
        {title && <h3 className="export-role-title text-xl font-semibold text-gray-800 dark:text-gray-200">{title}</h3>}
        <div ref={exportDropdownRef} className="flex items-start gap-2 relative">
          {onToggleDetail && (
            <button className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${showDetail ? 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300' : 'bg-blue-500 text-white hover:bg-blue-600'}`} onClick={onToggleDetail} data-export-hide="true">
              {showDetail ? t('table.hideDetail') : t('table.showDetail')}
            </button>
          )}
          <ExportButton onClick={() => setShowExportOptions(prev => !prev)} exportKey="score-table" />
          {showExportOptions && (
            <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg z-50" data-export-hide="true">
              <button className="w-full text-left px-4 py-3 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700" onClick={() => { setShowExportOptions(false); exportImage(`${t('charts.scoreTable')}.png`) }}>{t('export.singleImage')}</button>
              <button className="w-full text-left px-4 py-3 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 border-t border-gray-100 dark:border-gray-700" onClick={exportMultipleImages}>{t('export.individualImages')}</button>
              <button className="w-full text-left px-4 py-3 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 border-t border-gray-100 dark:border-gray-700" onClick={exportAsZip}>{t('export.zipBundle')}</button>
            </div>
          )}
        </div>
      </div>

      {isMobile ? (
        <CardView data={sortedData} groups={groups} maxScore={maxScore} scoreBasis={scoreBasis} hoveredModel={hoveredModel} onModelHover={onModelHover} t={t} cardRefs={cardRefs} />
      ) : (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-x-auto">
          <table className="w-full text-sm export-role-table">
            <thead className="bg-gray-50 dark:bg-gray-700">
              <tr>
                <th className="export-role-table-head px-3 py-2 text-left font-semibold text-gray-700 dark:text-gray-300 cursor-pointer" onClick={() => handleSort('model')}>{t('table.model')} <SortIcon columnKey="model" sortConfig={sortConfig} /></th>
                {groups.flatMap(group => [
                  <th key={`group-${group.group}`} className="export-role-table-head px-3 py-2 text-right font-semibold text-gray-700 dark:text-gray-300 cursor-pointer whitespace-nowrap" onClick={() => handleSort(`group:${group.group}`)}>
                    {_getGroupLabel(group, t)} <SortIcon columnKey={`group:${group.group}`} sortConfig={sortConfig} />
                  </th>,
                  ...(showDetail && _hasDetailColumns(group.group)
                    ? group.sections.map(section => (
                      <th key={`section-${section.target}`} className="export-role-table-head px-2 py-2 text-right text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-600 cursor-pointer whitespace-nowrap" onClick={() => handleSort(`section:${section.target}`)}>
                        {_getSectionLabel(section, t)} <SortIcon columnKey={`section:${section.target}`} sortConfig={sortConfig} />
                      </th>
                    ))
                    : [])
                ])}
                <th className="export-role-table-head px-3 py-2 text-right font-bold text-gray-700 dark:text-gray-300 cursor-pointer" onClick={() => handleSort('total')}>{t('table.total')} <SortIcon columnKey="total" sortConfig={sortConfig} /></th>
              </tr>
            </thead>
            <tbody>
              {sortedData.map(row => (
                <tr key={row.model} className={`border-t border-gray-100 dark:border-gray-700 transition-colors ${hoveredModel === row.model ? 'bg-blue-50 dark:bg-blue-900/30' : 'hover:bg-gray-50 dark:hover:bg-gray-700'} ${onRowClick ? 'cursor-pointer' : ''}`} onClick={() => onRowClick?.(row.model)} onMouseEnter={() => onModelHover?.(row.model)} onMouseLeave={() => onModelHover?.(null)}>
                  <td className="export-role-table-model px-3 py-2 text-gray-800 dark:text-gray-200"><span className="inline-block w-3 h-3 rounded-full mr-2" style={{ backgroundColor: getModelColor(row.model) }} />{formatModelDisplayName(row.model)}</td>
                  {groups.flatMap(group => {
                    const detail = row.groupDetails?.find(item => item.group === group.group)
                    return [
                      <td key={`group-${group.group}`} className="export-role-table-value px-3 py-2 text-right text-gray-800 dark:text-gray-200"><ScoreCell score={detail ? _getGroupScore(detail, scoreBasis) : null} maxScore={_getGroupMaxScore(group, scoreBasis)} /></td>,
                      ...(showDetail && _hasDetailColumns(group.group)
                        ? group.sections.map(section => (
                          <td key={`section-${section.target}`} className="export-role-table-value px-2 py-2 text-right text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50"><ScoreCell score={row.sectionScores?.find(item => item.target === section.target)?.score} maxScore={section.max_points ?? section.maxScore} decimals={0} /></td>
                        ))
                        : [])
                    ]
                  })}
                  <td className="export-role-table-value px-3 py-2 text-right font-bold text-gray-800 dark:text-gray-200"><ScoreCell score={row.total} maxScore={maxScore} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <BenchmarkNote modelNames={sortedData.map(row => row.model)} />
    </div>
  )
}
