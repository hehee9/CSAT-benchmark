/**
 * @file QuestionHeatmap.jsx
 * @brief 문항별 정답/오답 히트맵 컴포넌트
 */

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getModelColor, getHeatmapColor } from '@/utils/colorUtils'
import { useTheme } from '@/hooks/useTheme'
import { getQuestionNumbers, calculateModelAccuracy } from '@/utils/heatmapTransform'
import { useExportImage, README_EXPORT_WIDTH } from '@/hooks/useExportImage'
import { BenchmarkNote, ExportButton } from '@/components/common'
import { formatModelDisplayName } from '@/utils/modelMeta'

/**
 * @brief 문항별 정답률 계산
 * @param {Object} data - 히트맵 데이터
 * @param {Array<string>} models - 모델 목록
 * @param {number} questionNumber - 문항 번호
 * @return {number} 정답률 (0-100)
 */
function _calculateQuestionAccuracy(data, models, questionNumber) {
  let correct = 0
  let total = 0
  models.forEach(model => {
    const cell = data[questionNumber]?.[model]
    if (cell !== undefined) {
      total++
      if (cell.isCorrect) correct++
    }
  })
  return total > 0 ? (correct / total) * 100 : 0
}

/**
 * @brief 정답률에 따른 그라데이션 배경색 반환
 * @param {number} accuracy - 정답률 (0-100)
 * @param {boolean} darkMode - 다크모드 여부
 * @return {string} HSL 색상 문자열
 */
function _getAccuracyColor(accuracy, darkMode) {
  // 0% = 빨강(hue 0), 100% = 초록(hue 120)
  // 자연스러운 그라데이션: 빨강 → 주황 → 노랑 → 연두 → 초록
  const hue = (accuracy / 100) * 120
  const lightness = darkMode ? 40 : 70
  return `hsl(${hue}, 50%, ${lightness}%)`
}

/** @description Check whether a heatmap cell represents a refused response */
function _isRefusalCell(cell) {
  return cell?.answerStatus === 'refusal' || cell?.extractedAnswer === -2
}

/**
 * @brief 정답 선지 표시 문자열 생성
 * @param {number|number[]|null} correctAnswer - 공식 정답 또는 복수 정답
 * @return {number|string|null} 화면에 표시할 정답
 */
function _formatCorrectAnswer(correctAnswer) {
  return Array.isArray(correctAnswer) ? correctAnswer.join(', ') : correctAnswer
}

/** @description Format an answer value for compact heatmap cells */
function _formatAnswer(cell, t) {
  if (_isRefusalCell(cell)) return t('heatmap.refusalShort')
  if (cell?.extractedAnswer === -1) return '-'
  return cell?.extractedAnswer ?? '-'
}

/**
 * @brief 문항별 정답/오답 히트맵 컴포넌트
 * @param {Object} props - { data, models, title, subjectName, modelMetadata }
 * @param {Object} props.data - { questionNumber: { modelName: { isCorrect, points } } }
 * @param {Array<string>} props.models - 표시할 모델 목록
 * @param {string} props.title - 차트 제목
 * @param {string} props.subjectName - 내보내기 파일명용 과목명
 */
export default function QuestionHeatmap({ data, models, title, subjectName, modelMetadata = {} }) {
  const { t } = useTranslation()
  const { isDark: darkMode } = useTheme()
  const [showAnswerNumbers, setShowAnswerNumbers] = useState(false)
  const questions = useMemo(() => getQuestionNumbers(data), [data])
  const { ref, exportImage, isExporting } = useExportImage({
    exportWidth: README_EXPORT_WIDTH,
    exportProfile: 'questionHeatmap'
  })

  if (!data || !models?.length || !questions.length) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500 dark:text-gray-400">
        {t('common.noData')}
      </div>
    )
  }

  const modelColumnStyle = {
    width: isExporting ? 260 : 144,
    minWidth: isExporting ? 260 : 144
  }
  const questionColumnStyle = {
    width: isExporting ? 44 : 32,
    minWidth: isExporting ? 44 : 32
  }
  const summaryColumnStyle = {
    width: isExporting ? 140 : 80,
    minWidth: isExporting ? 140 : 80
  }

  return (
    <div ref={ref} className="w-full">
      <div className="flex items-start justify-between mb-4">
        {title && (
          <h3 className="export-role-title text-xl font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
        )}
        <div className="flex items-start gap-2">
          <span className="export-role-watermark hidden text-base text-gray-400 mt-8" data-export-show="true">Github/hehee9</span>
          <button
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              showAnswerNumbers
                ? 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                : 'bg-blue-500 text-white hover:bg-blue-600'
            }`}
            onClick={() => setShowAnswerNumbers(!showAnswerNumbers)}
            data-export-hide="true"
          >
            {showAnswerNumbers ? t('heatmap.showOX') : t('heatmap.showAnswer')}
          </button>
          <ExportButton
            onClick={() => exportImage(`${t('export.heatmap')}_${subjectName || t('common.all')}.png`)}
            exportKey="question-heatmap"
          />
        </div>
      </div>
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-x-auto">
        <div className="min-w-max">
          {/* 헤더 행 */}
          <div className="flex border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700">
            <div
              className="export-role-table-head w-36 p-2 font-semibold text-sm text-gray-700 dark:text-gray-300 shrink-0"
              style={modelColumnStyle}
            >
              {t('table.model')}
            </div>
            {questions.map(q => (
              <div
                key={q}
                className="export-role-table-head w-8 p-1 text-center text-xs font-medium text-gray-600 dark:text-gray-400 shrink-0"
                style={questionColumnStyle}
              >
                {q}
              </div>
            ))}
            <div
              className="export-role-table-head w-20 p-2 text-center font-semibold text-sm text-gray-700 dark:text-gray-300 shrink-0"
              style={summaryColumnStyle}
            >
              {t('heatmap.correctCount')}
            </div>
          </div>

          {/* 데이터 행 */}
          {models.map(model => {
            const accuracy = calculateModelAccuracy(data, model)
            return (
              <div
                key={model}
                className="flex items-center border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                <div
                  className={`export-role-table-model w-36 p-2 text-xs shrink-0 text-gray-800 dark:text-gray-200 ${isExporting ? 'whitespace-normal break-words' : 'truncate'}`}
                  style={{
                    ...modelColumnStyle,
                    borderLeft: `3px solid ${getModelColor(model)}`
                  }}
                  title={formatModelDisplayName(model)}
                >
                  {formatModelDisplayName(model)}
                </div>
                {questions.map(q => {
                  const cell = data[q]?.[model]
                  const isRefusal = _isRefusalCell(cell)
                  const bgColor = isRefusal
                    ? (darkMode ? '#581c87' : '#d8b4fe')
                    : getHeatmapColor(cell?.isCorrect, cell?.points, darkMode)
                  const cellTitle = cell?.isCorrect === undefined
                    ? `${formatModelDisplayName(model)} - ${t('heatmap.question')} ${q}: ${t('common.noData')}`
                    : isRefusal
                    ? `${formatModelDisplayName(model)} - ${t('heatmap.question')} ${q}: ${t('heatmap.refusal')} (${cell.points}${t('common.points')}) - ${t('heatmap.answer')}: ${_formatCorrectAnswer(cell.correctAnswer)}`
                    : cell?.isCorrect
                    ? `${formatModelDisplayName(model)} - ${t('heatmap.question')} ${q}: ${t('heatmap.correct')} (${cell.points}${t('common.points')}) - ${t('heatmap.yourAnswer')}: ${cell.extractedAnswer}`
                    : `${formatModelDisplayName(model)} - ${t('heatmap.question')} ${q}: ${t('heatmap.incorrect')} (${cell.points}${t('common.points')}) - ${t('heatmap.yourAnswer')}: ${cell.extractedAnswer}, ${t('heatmap.answer')}: ${_formatCorrectAnswer(cell.correctAnswer)}`
                  return (
                    <div
                      key={q}
                      className="export-role-table-value w-8 h-8 flex items-center justify-center text-xs shrink-0 border-r border-gray-50 dark:border-gray-700"
                      style={{ ...questionColumnStyle, backgroundColor: bgColor }}
                      title={cellTitle}
                    >
                      {showAnswerNumbers ? (
                        // 답 번호 모드: 숫자 표시
                        <span className={`export-role-value font-bold text-xs ${darkMode ? 'text-gray-100' : 'text-gray-800'}`}>
                          {_formatAnswer(cell, t)}
                        </span>
                      ) : (
                        // O/X 모드
                        <>
                          {isRefusal && (
                            <span className={`export-role-value font-bold text-xs ${darkMode ? 'text-gray-100' : 'text-purple-900'}`}>
                              {t('heatmap.refusalShort')}
                            </span>
                          )}
                          {cell?.isCorrect === true && (
                            <span className={`export-role-value font-bold ${darkMode ? 'text-gray-100' : 'text-gray-800'}`}>○</span>
                          )}
                          {cell?.isCorrect === false && !isRefusal && (
                            <span className={`export-role-value font-bold ${darkMode ? 'text-gray-100' : 'text-gray-800'}`}>✕</span>
                          )}
                        </>
                      )}
                    </div>
                  )
                })}
                <div
                  className="export-role-table-value w-20 p-2 text-center text-sm font-medium shrink-0 text-gray-800 dark:text-gray-200"
                  style={summaryColumnStyle}
                >
                  {accuracy.correct}/{accuracy.total}
                  <span className="export-role-value text-gray-400 dark:text-gray-500 text-xs ml-1">
                    ({accuracy.accuracy.toFixed(0)}%)
                  </span>
                </div>
              </div>
            )
          })}

          {/* 문항별 정답률 행 */}
          <div className="flex items-center border-t-2 border-gray-300 dark:border-gray-600">
            <div
              className="export-role-table-head w-36 p-2 text-xs font-semibold text-gray-700 dark:text-gray-300 shrink-0 bg-gray-100 dark:bg-gray-700"
              style={modelColumnStyle}
            >
              {t('heatmap.accuracy')}
            </div>
            {questions.map(q => {
              const qAccuracy = _calculateQuestionAccuracy(data, models, q)
              return (
                <div
                  key={q}
                  className="export-role-table-value w-8 h-8 flex items-center justify-center text-xs shrink-0"
                  style={{ ...questionColumnStyle, backgroundColor: _getAccuracyColor(qAccuracy, darkMode) }}
                  title={`${t('heatmap.question')} ${q} ${t('heatmap.accuracy')}: ${qAccuracy.toFixed(0)}%`}
                >
                  <span className={`export-role-value font-medium text-xs ${darkMode ? 'text-gray-100' : 'text-gray-800'}`}>
                    {qAccuracy.toFixed(0)}%
                  </span>
                </div>
              )
            })}
            <div
              className="w-20 shrink-0 bg-gray-100 dark:bg-gray-700"
              style={summaryColumnStyle}
            />
          </div>
        </div>
      </div>

      {/* 범례 */}
      <div className="export-role-legend flex flex-wrap gap-4 mt-4 text-sm text-gray-600 dark:text-gray-400">
        <div className="flex items-center gap-1">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: darkMode ? '#16a34a' : '#22c55e' }} />
          <span>{t('heatmap.legend.correctHigh')}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: darkMode ? '#166534' : '#86efac' }} />
          <span>{t('heatmap.legend.correctLow')}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: darkMode ? '#dc2626' : '#ef4444' }} />
          <span>{t('heatmap.legend.incorrectHigh')}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: darkMode ? '#991b1b' : '#fca5a5' }} />
          <span>{t('heatmap.legend.incorrectLow')}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: darkMode ? '#581c87' : '#d8b4fe' }} />
          <span>{t('heatmap.legend.refusal')}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-4 rounded" style={{ backgroundColor: darkMode ? '#374151' : '#f0f0f0' }} />
          <span>{t('common.noData')}</span>
        </div>
      </div>
      <BenchmarkNote modelNames={models} modelMetadata={modelMetadata} />
    </div>
  )
}
