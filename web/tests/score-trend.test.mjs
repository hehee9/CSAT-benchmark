import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({
  root,
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true }
})

const {
  parseReleaseDate,
  buildTrendPoints,
  buildVendorStepLines,
  getFrontierModels,
  getMonthTicks
} = await server.ssrLoadModule('/src/utils/trendTransform.js')

const day = (value) => Date.UTC(...value.split('-').map((part, index) => Number(part) - (index === 1 ? 1 : 0)))

// 출시일 형식 검증
assert.equal(parseReleaseDate('2025-03-14'), day('2025-03-14'))
assert.equal(parseReleaseDate('2024-02-29'), day('2024-02-29'))
assert.equal(parseReleaseDate('2025-02-29'), null)
assert.equal(parseReleaseDate('2025-13-01'), null)
assert.equal(parseReleaseDate('2025-3-14'), null)
assert.equal(parseReleaseDate('2025-03-14T00:00:00Z'), null)
assert.equal(parseReleaseDate(''), null)
assert.equal(parseReleaseDate(null), null)
assert.equal(parseReleaseDate(20250314), null)

// 출시일 없는 모델 제외와 개발사 분류
const metadata = {
  'GPT-5.1 (high)': { releaseDate: '2025-11-12' },
  'GPT-5.4 (high)': { releaseDate: '2026-03-05' },
  'GPT-5.4 (none)': { releaseDate: '2026-03-05' },
  'GPT-5 mini (high)': { releaseDate: '2025-08-07' },
  'Claude Opus 4.5': { releaseDate: '2025-11-24' },
  'Claude Haiku 4.5': { releaseDate: '2025-10-15' },
  'Gemini 3 Pro (high)': { releaseDate: 'unknown' },
  'Mystery Model': { releaseDate: '2025-12-01' }
}
const scores = [
  { model: 'GPT-5.1 (high)', total: 300 },
  { model: 'GPT-5.4 (high)', total: 420 },
  { model: 'GPT-5.4 (none)', total: 250 },
  { model: 'GPT-5 mini (high)', total: 310 },
  { model: 'Claude Opus 4.5', total: 380 },
  { model: 'Claude Haiku 4.5', total: 200 },
  { model: 'Gemini 3 Pro (high)', total: 400 },
  { model: 'Gemini 3 Flash (high)', total: 350 },
  { model: 'Mystery Model', total: 100 }
]
const { points, excludedCount } = buildTrendPoints(scores, metadata)
assert.equal(excludedCount, 2)
assert.deepEqual(points.map(point => point.model), [
  'GPT-5 mini (high)',
  'Claude Haiku 4.5',
  'GPT-5.1 (high)',
  'Claude Opus 4.5',
  'Mystery Model',
  'GPT-5.4 (high)',
  'GPT-5.4 (none)'
])
assert.deepEqual(points.map(point => point.vendorId), ['openai', 'anthropic', 'openai', 'anthropic', 'other', 'openai', 'openai'])
assert.deepEqual(points[0], { model: 'GPT-5 mini (high)', vendorId: 'openai', releaseDate: '2025-08-07', time: day('2025-08-07'), score: 310 })
assert.deepEqual(buildTrendPoints([], metadata), { points: [], excludedCount: 0 })
assert.equal(buildTrendPoints([{ model: 'GPT-5.1 (high)', total: Number.NaN }], metadata).excludedCount, 1)

// 누적 최고 점수 계단선은 마지막 갱신 꼭짓점에서 끝남
const lines = buildVendorStepLines(points)
assert.deepEqual(Object.keys(lines).sort(), ['anthropic', 'openai', 'other'])
assert.deepEqual(lines.openai, [
  { time: day('2025-08-07'), score: 310 },
  { time: day('2026-03-05'), score: 420 }
])
assert.deepEqual(lines.anthropic, [
  { time: day('2025-10-15'), score: 200 },
  { time: day('2025-11-24'), score: 380 }
])
assert.deepEqual(lines.other, [
  { time: day('2025-12-01'), score: 100 }
])

// 같은 날짜는 최고 점수만 반영하고, 점수 하락은 계단선을 낮추지 않음
const sameDayPoints = [
  { model: 'A', vendorId: 'v', time: day('2025-01-01'), score: 50 },
  { model: 'B', vendorId: 'v', time: day('2025-02-01'), score: 40 },
  { model: 'C', vendorId: 'v', time: day('2025-02-01'), score: 70 },
  { model: 'D', vendorId: 'v', time: day('2025-03-01'), score: 70 },
  { model: 'E', vendorId: 'v', time: day('2025-04-01'), score: 60 }
]
assert.deepEqual(buildVendorStepLines(sameDayPoints).v, [
  { time: day('2025-01-01'), score: 50 },
  { time: day('2025-02-01'), score: 70 }
])
assert.deepEqual(buildVendorStepLines(sameDayPoints.slice(0, 1)).v, [
  { time: day('2025-01-01'), score: 50 }
])
assert.deepEqual(buildVendorStepLines([]), {})

// 최고 점수 갱신 모델
assert.deepEqual([...getFrontierModels(sameDayPoints)].sort(), ['A', 'C'])
const tiedPoints = [
  { model: 'X', vendorId: 'v', time: day('2025-01-01'), score: 80 },
  { model: 'Y', vendorId: 'v', time: day('2025-01-01'), score: 80 },
  { model: 'Z', vendorId: 'w', time: day('2025-01-01'), score: 10 }
]
assert.deepEqual([...getFrontierModels(tiedPoints)].sort(), ['X', 'Y', 'Z'])
assert.deepEqual([...getFrontierModels(points)].sort(), [
  'Claude Haiku 4.5',
  'Claude Opus 4.5',
  'GPT-5 mini (high)',
  'GPT-5.4 (high)',
  'Mystery Model'
])

// 월초 눈금
assert.deepEqual(getMonthTicks(day('2025-01-15'), day('2025-04-20'), 8), [
  day('2025-02-01'),
  day('2025-03-01'),
  day('2025-04-01')
])
assert.deepEqual(getMonthTicks(day('2025-01-01'), day('2025-03-01'), 8), [
  day('2025-01-01'),
  day('2025-02-01'),
  day('2025-03-01')
])
const yearTicks = getMonthTicks(day('2024-05-10'), day('2026-02-01'), 6)
assert.ok(yearTicks.length <= 6)
assert.deepEqual(yearTicks, [day('2024-09-01'), day('2025-01-01'), day('2025-05-01'), day('2025-09-01'), day('2026-01-01')])
assert.deepEqual(getMonthTicks(day('2025-01-10'), day('2025-01-20'), 8), [])
assert.deepEqual(getMonthTicks(Number.NaN, day('2025-01-20'), 8), [])

await server.close()
console.log('score-trend: release date and step line assertions passed')
