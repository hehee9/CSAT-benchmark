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
  ANALYSIS_METRIC_IDS,
  DEFAULT_ANALYSIS_X,
  DEFAULT_ANALYSIS_Y,
  getAnalysisMetricValue,
  getAnalysisPoints,
  isAnalysisMetricLog
} = await server.ssrLoadModule('/src/utils/analysisMetrics.js')
const {
  getDashboardQueryState,
  replaceDashboardQueryState
} = await server.ssrLoadModule('/src/utils/urlState.js')

assert.deepEqual(ANALYSIS_METRIC_IDS, ['score', 'cost', 'tokens', 'time'])
assert.equal(DEFAULT_ANALYSIS_X, 'cost')
assert.equal(DEFAULT_ANALYSIS_Y, 'score')
assert.equal(isAnalysisMetricLog('score'), false)
assert.equal(isAnalysisMetricLog('cost'), true)
assert.equal(isAnalysisMetricLog('tokens'), true)
assert.equal(isAnalysisMetricLog('time'), true)

const completeRow = {
  model: '완전한 모델',
  score: 0,
  totalCost: 0.25,
  totalTokens: 1000,
  estimatedSeconds: 20
}

for (const xMetric of ANALYSIS_METRIC_IDS) {
  for (const yMetric of ANALYSIS_METRIC_IDS) {
    const points = getAnalysisPoints([completeRow], xMetric, yMetric)
    assert.equal(points.length, 1, `${xMetric}/${yMetric} 조합이 유효하지 않음`)
    assert.equal(points[0].xValue, completeRow[xMetric === 'score' ? 'score' : xMetric === 'cost' ? 'totalCost' : xMetric === 'tokens' ? 'totalTokens' : 'estimatedSeconds'])
    assert.equal(points[0].yValue, completeRow[yMetric === 'score' ? 'score' : yMetric === 'cost' ? 'totalCost' : yMetric === 'tokens' ? 'totalTokens' : 'estimatedSeconds'])
  }
}

assert.equal(getAnalysisMetricValue(completeRow, 'score'), 0)
assert.deepEqual(
  getAnalysisPoints([{ ...completeRow, totalCost: 0 }, { ...completeRow, totalTokens: 0 }, { ...completeRow, estimatedSeconds: null }], 'score', 'score').length,
  3
)
assert.equal(getAnalysisPoints([{ ...completeRow, totalCost: 0 }], 'cost', 'score').length, 0)
assert.equal(getAnalysisPoints([{ ...completeRow, totalTokens: null }], 'tokens', 'score').length, 0)
assert.equal(getAnalysisPoints([{ ...completeRow, estimatedSeconds: 0 }], 'time', 'score').length, 0)
assert.equal(getAnalysisPoints([{ ...completeRow, totalCost: null }], 'score', 'cost').length, 0)

const previousWindow = globalThis.window
globalThis.window = {
  location: {
    href: 'https://example.test/dashboard?exam=csat-2026&mode=easy&scoreBasis=raw&lang=en&theme=dark&tab=cost&analysisX=tokens#cost',
    get search() {
      return new URL(this.href).search
    }
  },
  history: {
    replaceState(_state, _title, url) {
      globalThis.window.location.href = String(url)
    }
  }
}

assert.deepEqual(
  getDashboardQueryState('?exam=csat-2026&mode=easy&scoreBasis=raw&lang=en&theme=dark&tab=cost&analysisX=tokens'),
  { exam: 'csat-2026', mode: 'easy', scoreBasis: 'raw' }
)
assert.deepEqual(
  getDashboardQueryState('?lang=en&theme=dark&tab=cost&analysisX=tokens'),
  { exam: 'csat-2026', mode: 'default', scoreBasis: 'raw' }
)
assert.deepEqual(
  getDashboardQueryState('?scoreBasis=normalized'),
  { exam: 'csat-2026', mode: 'default', scoreBasis: 'normalized' }
)

const replacedUrl = replaceDashboardQueryState({
  exam: 'csat-2026',
  mode: 'easy',
  scoreBasis: 'raw',
  tab: 'cost',
  analysisX: 'tokens'
})
const replaced = new URL(replacedUrl)
assert.equal(replaced.pathname, '/dashboard')
assert.equal(replaced.hash, '#cost')
assert.deepEqual([...replaced.searchParams.keys()], ['exam', 'mode', 'scoreBasis'])
const roundTripped = getDashboardQueryState(new URL(replacedUrl).search)
assert.deepEqual(roundTripped, { exam: 'csat-2026', mode: 'easy', scoreBasis: 'raw' })

globalThis.window = previousWindow
await server.close()
console.log('analysis-metrics: URL and metric assertions passed')
