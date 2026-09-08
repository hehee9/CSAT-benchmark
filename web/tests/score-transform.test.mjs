import assert from 'node:assert/strict'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({
  root,
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true }
})
const {
  calculateAllModelScores,
  calculateOverallScore,
  getCostData,
  getFilteredTotal,
  getMaxScore,
  getSubjectFilterGroups
} = await server.ssrLoadModule('/src/utils/dataTransform.js')
const { transformToRadarData } = await server.ssrLoadModule('/src/utils/heatmapTransform.js')
const { addHoveredModelRadarData } = await server.ssrLoadModule('/src/utils/radarTransform.js')

const currentData = JSON.parse(fs.readFileSync(new URL('../../all_results.json', import.meta.url), 'utf8'))
const currentModel = currentData[0].model_name

assert.equal(getMaxScore(), 450)
assert.equal(getMaxScore([], { scoreBasis: 'raw' }), 626)
assert.equal(calculateOverallScore(currentData, currentModel).maxScore, 450)
assert.equal(calculateOverallScore(currentData, currentModel, { scoreBasis: 'raw' }).maxScore, 626)

const baseSections = [
  { target: '국어/공통', subject: '국어', section: '공통', group: '국어', kind: 'common', questions: 1, max_points: 76 },
  { target: '국어/화작', subject: '국어', section: '화작', group: '국어', kind: 'elective', questions: 1, max_points: 24 },
  { target: '국어/언매', subject: '국어', section: '언매', group: '국어', kind: 'elective', questions: 1, max_points: 24 },
  { target: '수학/공통', subject: '수학', section: '공통', group: '수학', kind: 'common', questions: 1, max_points: 74 },
  { target: '수학/확통', subject: '수학', section: '확통', group: '수학', kind: 'elective', questions: 1, max_points: 26 },
  { target: '수학/미적', subject: '수학', section: '미적', group: '수학', kind: 'elective', questions: 1, max_points: 26 },
  { target: '수학/기하', subject: '수학', section: '기하', group: '수학', kind: 'elective', questions: 1, max_points: 26 },
  { target: '영어/영어', subject: '영어', section: '영어', group: '영어', kind: 'subject', questions: 1, max_points: 100 },
  { target: '한국사/한국사', subject: '한국사', section: '한국사', group: '한국사', kind: 'subject', questions: 1, max_points: 50 }
]

function makeExam(explorationCount) {
  const explorations = Array.from({ length: explorationCount }, (_, index) => ({
    target: `탐구/과목${index + 1}`,
    subject: `과목${index + 1}`,
    section: '탐구',
    group: '탐구',
    kind: 'subject',
    questions: 1,
    max_points: 50
  }))
  return { id: `test-${explorationCount}`, title: '시험', sections: [...baseSections, ...explorations] }
}

function makeData(exam, values = {}) {
  return exam.sections.map(section => ({
    subject: section.subject,
    section: section.section,
    model_name: '시험 모델',
    score: values[section.target] ?? section.max_points,
    total_points: section.max_points,
    total_questions: section.questions,
    price: { input: 1, output: 2 },
    results: []
  }))
}

for (const count of [4, 17]) {
  const exam = makeExam(count)
  const data = makeData(exam)
  const normalized = calculateOverallScore(data, '시험 모델', { exam })
  const raw = calculateOverallScore(data, '시험 모델', { exam, scoreBasis: 'raw' })
  assert.equal(normalized.maxScore, 450)
  assert.equal(normalized.total, 450)
  assert.equal(raw.maxScore, 426 + count * 50)
  assert.equal(raw.total, 426 + count * 50)
  assert.equal(getMaxScore([], { exam, scoreBasis: 'raw' }), 426 + count * 50)
  assert.equal(getMaxScore([`탐구/과목1`], { exam }), 100)
  assert.equal(getMaxScore([`탐구/과목1`], { exam, scoreBasis: 'raw' }), 50)
  assert.equal(getFilteredTotal(normalized, ['탐구/과목1'], { exam }), 100)
  assert.equal(getFilteredTotal(raw, ['탐구/과목1'], { exam, scoreBasis: 'raw' }), 50)
  assert.equal(getSubjectFilterGroups(exam).find(group => group.group === '탐구').children.length, count)
}

const currentExam = makeExam(2)
const zeroScoreData = makeData(currentExam, {
  '국어/화작': 0,
  '국어/언매': 24
})
const zeroScore = calculateOverallScore(zeroScoreData, '시험 모델', { exam: currentExam })
assert.equal(zeroScore.korean, 88)
const partialData = zeroScoreData.filter(row => row.subject !== '국어' || row.section !== '언매')
const partialScore = calculateOverallScore(partialData, '시험 모델', { exam: currentExam })
assert.equal(partialScore.korean, 76)
assert.equal(partialScore.sectionScores.find(section => section.target === '국어/화작').available, true)
assert.equal(partialScore.sectionScores.find(section => section.target === '국어/언매').available, false)

const seventeenExam = makeExam(17)
const missingExplorationTarget = '탐구/과목17'
const missingExplorationData = makeData(seventeenExam).filter(row =>
  row.subject !== '과목17'
)
const missingExplorationScore = calculateOverallScore(missingExplorationData, '시험 모델', { exam: seventeenExam })
assert.equal(missingExplorationScore.maxScore, 450)
assert.equal(missingExplorationScore.explorationDetail.average, (16 * 50) / 17)
assert.equal(missingExplorationScore.exploration, (16 * 50 / 17) * 2)
const missingSelection = calculateOverallScore(missingExplorationData, '시험 모델', {
  exam: seventeenExam,
  subjectFilter: [missingExplorationTarget]
})
assert.equal(missingSelection.total, 0)
assert.equal(missingSelection.maxScore, 100)

const radarScore = calculateOverallScore(makeData(seventeenExam), '시험 모델', {
  exam: seventeenExam,
  scoreBasis: 'raw'
})
const rawRadar = transformToRadarData([radarScore], [], value => value, {
  exam: seventeenExam,
  scoreBasis: 'raw'
})
const rawExploration = rawRadar.find(row => row.group === '탐구')
assert.equal(rawExploration.maxScore, 850)
const hoveredRawRadar = addHoveredModelRadarData(rawRadar, '시험 모델', [], [radarScore], 'raw')
assert.equal(hoveredRawRadar.find(row => row.group === '탐구')['시험 모델'], 100)

const duplicateFilterScore = calculateOverallScore(makeData(makeExam(2)), '시험 모델', { exam: makeExam(2) })
assert.equal(getFilteredTotal(duplicateFilterScore, ['국어', '국어/화작']), 100)
assert.equal(getMaxScore(['국어', '국어/화작'], { exam: currentExam }), 100)
assert.equal(getMaxScore(['국어', '국어-화작'], { exam: currentExam, scoreBasis: 'raw' }), 124)

const costData = getCostData(
  makeData(currentExam),
  calculateAllModelScores(makeData(currentExam), ['시험 모델'], [], { exam: currentExam, scoreBasis: 'raw' }),
  {
    '시험 모델': {
      total_input_tokens: 300,
      total_output_tokens: 100,
      sections: { '국어-공통': { input_tokens: 10, output_tokens: 20 } },
      attempts: [{ total_input_tokens: 300, total_output_tokens: 100 }],
      attempt_totals: [{ total_input_tokens: 300, total_output_tokens: 100 }]
    }
  },
  [],
  { exam: currentExam, scoreBasis: 'raw' }
)
assert.equal(costData[0].maxScore, 526)
assert.equal(costData[0].inputTokens, 300)
assert.equal(costData[0].outputTokens, 100)
assert.equal(costData[0].tokenUsage.attempt_totals.length, 1)
assert.equal(costData[0].totalCost, 0.0005)

const filteredCost = getCostData(
  makeData(currentExam),
  calculateAllModelScores(makeData(currentExam), ['시험 모델'], [], { exam: currentExam }),
  {
    '시험 모델': {
      sections: {
        '국어-공통': { input_tokens: 10, output_tokens: 10 },
        '국어-화작': { input_tokens: 20, output_tokens: 20 },
        '국어-언매': { input_tokens: 30, output_tokens: 30 },
        '영어-공통': { input_tokens: 40, output_tokens: 40 }
      }
    }
  },
  ['국어', '국어-화작'],
  { exam: currentExam }
)
assert.equal(filteredCost[0].inputTokens, 60)
assert.equal(filteredCost[0].outputTokens, 60)
assert.equal(filteredCost[0].maxScore, 100)

const englishCost = getCostData(
  makeData(currentExam),
  calculateAllModelScores(makeData(currentExam), ['시험 모델'], [], { exam: currentExam }),
  {
    '시험 모델': {
      sections: { '영어-공통': { input_tokens: 40, output_tokens: 40 } }
    }
  },
  ['영어'],
  { exam: currentExam }
)
assert.equal(englishCost[0].inputTokens, 40)
assert.equal(englishCost[0].outputTokens, 40)

const mismatchedBasisCost = getCostData(
  makeData(currentExam),
  calculateAllModelScores(makeData(currentExam), ['시험 모델'], [], { exam: currentExam }),
  {},
  [],
  { exam: currentExam, scoreBasis: 'raw' }
)
assert.equal(mismatchedBasisCost[0].score, 526)

await server.close()
console.log('score-transform: dynamic score and radar assertions passed')
