import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({
  root,
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true }
})

const { calculateOverallScore } = await server.ssrLoadModule('/src/utils/dataTransform.js')
const { transformToChoiceData } = await server.ssrLoadModule('/src/utils/choiceTransform.js')
const { transformToHeatmapData } = await server.ssrLoadModule('/src/utils/heatmapTransform.js')
const { loadBenchmarkCatalog } = await server.ssrLoadModule('/src/utils/dataLoader.js')
const { formatModelDisplayName } = await server.ssrLoadModule('/src/utils/modelMeta.js')

const normalizedExam = {
  id: 'answer-test',
  title: '정답 변환 시험',
  sections: [
    {
      target: '탐구/과목1',
      subject: '과목1',
      section: '탐구',
      group: '탐구',
      kind: 'subject',
      max_points: 50
    }
  ]
}
const normalizedData = [{
  subject: '과목1',
  section: '탐구',
  model_name: '시험 모델',
  score: 25,
  total_points: 50,
  total_questions: 1,
  results: []
}]

const normalizedScore = calculateOverallScore(normalizedData, '시험 모델', { exam: normalizedExam })
const rawScore = calculateOverallScore(normalizedData, '시험 모델', {
  exam: normalizedExam,
  scoreBasis: 'raw'
})
assert.equal(normalizedScore.scoreBasis, 'normalized')
assert.equal(normalizedScore.total, 50)
assert.equal(normalizedScore.maxScore, 100)
assert.equal(rawScore.scoreBasis, 'raw')
assert.equal(rawScore.total, 25)
assert.equal(rawScore.maxScore, 50)

const rawAnswer = {
  subject: '국어',
  section: '공통',
  model_name: '모델 A',
  results: [{
    question_number: 1,
    extracted_answer: 3,
    correct_answer: [2, 3],
    is_correct: true,
    points: 2
  }]
}
const heatmap = transformToHeatmapData([rawAnswer], '국어', '공통')
assert.deepEqual(heatmap[1]['모델 A'].correctAnswer, [2, 3])
assert.equal(heatmap[1]['모델 A'].extractedAnswer, 3)

const choiceRows = transformToChoiceData({
  1: {
    '모델 A': { answerStatus: 'answered', extractedAnswer: 2, correctAnswer: [2, 3] },
    '모델 B': { answerStatus: 'answered', extractedAnswer: 3, correctAnswer: [2, 3] },
    '모델 C': { answerStatus: 'answered', extractedAnswer: 1, correctAnswer: [2, 3] },
    '모델 D': { answerStatus: 'answered', extractedAnswer: -1, correctAnswer: [2, 3] }
  }
}, ['모델 A', '모델 B', '모델 C', '모델 D'], '국어', '공통')
assert.equal(choiceRows.length, 1)
const { choice1Pct, choice2Pct, choice3Pct, choice4Pct, choice5Pct, ...choiceCounts } = choiceRows[0]
assert.deepEqual(choiceCounts, {
  question: 1,
  correctAnswer: [2, 3],
  totalModels: 3,
  choice1: 1,
  choice2: 1,
  choice3: 1,
  choice4: 0,
  choice5: 0,
})
assert.ok(Math.abs(choice1Pct - 100 / 3) < 1e-12)
assert.ok(Math.abs(choice2Pct - 100 / 3) < 1e-12)
assert.ok(Math.abs(choice3Pct - 100 / 3) < 1e-12)
assert.equal(choice4Pct, 0)
assert.equal(choice5Pct, 0)

assert.equal(
  formatModelDisplayName('DeepSeek V4.1 Flash (High)'),
  'DeepSeek V4.1 Flash (high)'
)

const originalFetch = globalThis.fetch
globalThis.fetch = async () => ({
  ok: true,
  json: async () => ({
    schema_version: 1,
    default_exam: 'older',
    exams: [
      { id: 'missing', exam_month: null, publish: true },
      { id: 'older', exam_month: '2025-11', publish: true },
      { id: 'newer', exam_month: '2026-11', publish: true },
      { id: 'hidden', exam_month: '2027-01', publish: false },
      { id: 'also-missing', publish: true }
    ]
  })
})
try {
  const catalog = await loadBenchmarkCatalog()
  assert.deepEqual(catalog.exams.map(exam => exam.id), ['newer', 'older', 'missing', 'also-missing'])
  assert.equal(catalog.default_exam, 'older')
} finally {
  globalThis.fetch = originalFetch
}

const [ko, en] = await Promise.all([
  readFile(new URL('../src/locales/ko.json', import.meta.url), 'utf8'),
  readFile(new URL('../src/locales/en.json', import.meta.url), 'utf8')
])
assert.equal(JSON.parse(ko).header.normalized, '450점 환산')
assert.equal(JSON.parse(en).header.normalized, '450-point scale')
assert.equal(JSON.parse(ko).charts.modelCompare, '모델 비교 (과목별 450점 환산 점수)')
assert.equal(JSON.parse(en).charts.modelCompare, 'Model Comparison (450-point Scale by Subject)')

await server.close()
console.log('dashboard-regressions: defaults, catalog, display names, scores, and multi-answer transforms passed')
