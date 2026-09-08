/**
 * @file heatmapTransform.js
 * @brief 히트맵 및 시험 정의 기반 레이더 차트 데이터 변환
 */

import { getSubjectFilterGroups, SCORE_BASIS } from './dataTransform'

/**
 * @brief all_results.json 데이터를 히트맵용 형식으로 변환
 * @param {Array} data - all_results.json 전체 데이터
 * @param {string} subject - 과목명
 * @param {string} section - 섹션명
 * @return {Object} { questionNumber: { modelName: { isCorrect, points } } }
 */
export function transformToHeatmapData(data, subject, section) {
  const filtered = data.filter(d => d.subject === subject && d.section === section)
  const heatmap = {}

  filtered.forEach(entry => {
    if (!entry.results) return

    entry.results.forEach(result => {
      const qNum = result.question_number
      if (!heatmap[qNum]) heatmap[qNum] = {}
      heatmap[qNum][entry.model_name] = {
        isCorrect: result.is_correct,
        points: result.points,
        extractedAnswer: result.extracted_answer,
        correctAnswer: result.correct_answer,
        answerStatus: result.answer_status || (result.extracted_answer === -1 ? 'no_answer' : 'answered'),
        providerStopReason: result.provider_stop_reason || null
      }
    })
  })

  return heatmap
}

/**
 * @brief 히트맵 데이터에서 문항 번호 목록 추출
 * @param {Object} heatmapData - transformToHeatmapData 결과
 * @return {number[]} 정렬된 문항 번호 배열
 */
export function getQuestionNumbers(heatmapData) {
  return Object.keys(heatmapData)
    .map(Number)
    .sort((a, b) => a - b)
}

/**
 * @brief 레이더 차트 그룹 메타데이터 생성
 * @param {Array} overallScores - 종합 점수 배열
 * @param {Object|null} exam - 시험 정의
 * @param {string} scoreBasis - 점수 기준
 * @return {Array} 그룹 메타데이터
 */
function _getRadarGroups(overallScores, exam, scoreBasis) {
  if (exam) {
    return getSubjectFilterGroups(exam).map(group => ({
      group: group.group,
      nameKey: group.group,
      maxScore: group.maxScores[scoreBasis]
    }))
  }

  const details = overallScores[0]?.groupDetails || []
  if (details.length > 0) {
    return details.map(detail => ({
      group: detail.group,
      nameKey: detail.group,
      maxScore: scoreBasis === SCORE_BASIS.RAW ? detail.rawMaxScore : detail.normalizedMaxScore
    }))
  }

  return [
    { group: '국어', nameKey: 'subjects.korean', maxScore: scoreBasis === SCORE_BASIS.RAW ? 124 : 100 },
    { group: '수학', nameKey: 'subjects.math', maxScore: scoreBasis === SCORE_BASIS.RAW ? 152 : 100 },
    { group: '영어', nameKey: 'subjects.english', maxScore: 100 },
    { group: '한국사', nameKey: 'subjects.history', maxScore: 50 },
    { group: '탐구', nameKey: 'subjects.exploration', maxScore: scoreBasis === SCORE_BASIS.RAW ? 200 : 100 }
  ]
}

/**
 * @brief 레이더 차트용 데이터 변환
 * @param {Array} overallScores - calculateAllModelScores 결과
 * @param {string[]} selectedModels - 선택된 모델명 배열
 * @param {function} t - 번역 함수
 * @param {Object} options - { exam, scoreBasis }
 * @return {Array} 그룹별 모델 점수 백분율
 */
export function transformToRadarData(overallScores, selectedModels, t, options = {}) {
  const scoreBasis = options.scoreBasis ?? overallScores[0]?.scoreBasis ?? SCORE_BASIS.NORMALIZED
  const exam = options.exam ?? overallScores[0]?.exam ?? null
  const groups = _getRadarGroups(overallScores, exam, scoreBasis)

  return groups.map(({ group, nameKey, maxScore }) => {
    const translatedNameKey = {
      국어: 'subjects.korean',
      수학: 'subjects.math',
      영어: 'subjects.english',
      한국사: 'subjects.history',
      탐구: 'subjects.exploration'
    }[group] || nameKey
    const row = {
      subject: t ? t(translatedNameKey) : translatedNameKey,
      group,
      maxScore
    }

    selectedModels.forEach(modelName => {
      const modelScore = overallScores.find(score => score.model === modelName)
      const detail = modelScore?.groupDetails?.find(item => item.group === group)
      const field = {
        국어: 'korean',
        수학: 'math',
        영어: 'english',
        한국사: 'history',
        탐구: 'exploration'
      }[group]
      const rawScore = detail
        ? (scoreBasis === SCORE_BASIS.RAW ? detail.rawTotal : detail.normalizedTotal)
        : (modelScore?.[field] ?? 0)
      row[modelName] = maxScore > 0 ? (rawScore / maxScore) * 100 : 0
    })

    return row
  })
}

/**
 * @brief 모델별 정답 수 계산
 * @param {Object} heatmapData - transformToHeatmapData 결과
 * @param {string} modelName - 모델명
 * @return {Object} { correct, total, accuracy }
 */
export function calculateModelAccuracy(heatmapData, modelName) {
  const questions = Object.keys(heatmapData)
  let correct = 0
  let total = 0

  questions.forEach(qNum => {
    const cell = heatmapData[qNum]?.[modelName]
    if (cell === undefined) return
    total++
    if (cell.isCorrect) correct++
  })

  return {
    correct,
    total,
    accuracy: total > 0 ? (correct / total) * 100 : 0
  }
}
