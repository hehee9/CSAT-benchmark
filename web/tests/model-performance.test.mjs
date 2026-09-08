import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import {
  refreshModelPerformance,
  selectThroughput
} from '../scripts/refresh-model-performance.mjs'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({
  root,
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true }
})
const { getCostData } = await server.ssrLoadModule('/src/utils/dataTransform.js')
const { loadModelPerformance } = await server.ssrLoadModule('/src/utils/dataLoader.js')

const exam = {
  id: 'performance-test',
  title: '처리량 시험',
  sections: [
    { target: '국어/공통', subject: '국어', section: '공통', group: '국어', kind: 'common', max_points: 76 },
    { target: '국어/화작', subject: '국어', section: '화작', group: '국어', kind: 'elective', max_points: 24 }
  ]
}

const data = exam.sections.map(section => ({
  subject: section.subject,
  section: section.section,
  model_name: '시험 모델',
  score: section.max_points,
  total_points: section.max_points,
  total_questions: 1,
  price: { input: 1, output: 2 },
  results: []
}))
const score = [{ model: '시험 모델', total: 100, scoreBasis: 'normalized', exam }]
const performance = {
  updatedAt: '2026-09-08T00:00:00.000Z',
  models: {
    '시험 모델': {
      modelId: 'openai/test-model',
      tokensPerSecond: 30,
      providers: ['OpenAI'],
      selection: { strategy: 'official', provider: 'OpenAI', tag: 'openai' }
    }
  }
}

const total = getCostData(
  data,
  score,
  { '시험 모델': { total_input_tokens: 1000, total_output_tokens: 300 } },
  [],
  { exam, modelPerformance: performance }
)[0]
assert.equal(total.totalTokens, 1300)
assert.equal(total.estimatedSeconds, 10)
assert.equal(total.tokensPerSecond, 30)
assert.equal(total.provider, 'OpenAI')
assert.ok(Math.abs(total.totalCost - 0.0016) < 1e-12)

const repeated = getCostData(
  data,
  score,
  { '시험 모델': { attempts: 3, total_input_tokens: 100, total_output_tokens: 90 } },
  [],
  { exam, modelPerformance: performance }
)[0]
assert.equal(repeated.totalTokens, 190)
assert.equal(repeated.estimatedSeconds, 3)

const completeFiltered = getCostData(
  data,
  score,
  {
    '시험 모델': {
      sections: {
        '국어-공통': { input_tokens: 100, output_tokens: 10 },
        '국어-화작': { input_tokens: 200, output_tokens: 20 }
      }
    }
  },
  ['국어'],
  { exam, modelPerformance: performance }
)[0]
assert.equal(completeFiltered.totalTokens, 330)
assert.equal(completeFiltered.estimatedSeconds, 1)

const partialFiltered = getCostData(
  data,
  score,
  { '시험 모델': { sections: { '국어-공통': { input_tokens: 100, output_tokens: 10 } } } },
  ['국어'],
  { exam, modelPerformance: performance }
)[0]
assert.equal(partialFiltered.totalTokens, null)
assert.equal(partialFiltered.estimatedSeconds, null)
assert.ok(Math.abs(partialFiltered.totalCost - 0.00012) < 1e-12)

const partialTokenField = getCostData(
  data,
  score,
  {
    '시험 모델': {
      sections: {
        '국어-공통': { input_tokens: 100, output_tokens: 10 },
        '국어-화작': { input_tokens: 200 }
      }
    }
  },
  ['국어'],
  { exam, modelPerformance: performance }
)[0]
assert.equal(partialTokenField.totalTokens, null)
assert.equal(partialTokenField.estimatedSeconds, null)

const outputOnly = getCostData(
  data,
  score,
  { '시험 모델': { sections: {
    '국어-공통': { output_tokens: 10 },
    '국어-화작': { output_tokens: 20 }
  } } },
  ['국어'],
  { exam, modelPerformance: performance }
)[0]
assert.equal(outputOnly.totalTokens, null)
assert.equal(outputOnly.estimatedSeconds, 1)

const missingPerformance = getCostData(
  data,
  score,
  { '시험 모델': { total_input_tokens: 10, total_output_tokens: 20 } },
  [],
  { exam }
)[0]
assert.equal(missingPerformance.totalTokens, 30)
assert.equal(missingPerformance.estimatedSeconds, null)
assert.equal(missingPerformance.tokensPerSecond, null)

const official = selectThroughput([
  { provider_name: 'OpenAI', tag: 'openai/flex', throughput_last_30m: { p50: 5 } },
  { provider_name: 'OpenAI', tag: 'openai', throughput_last_30m: { p50: 40 } },
  { provider_name: 'OpenAI', tag: 'openai/fast', throughput_last_30m: { p50: 100 } },
  { provider_name: 'Azure', tag: 'azure', throughput_last_30m: { p50: 20 } }
], { modelId: 'openai/test-model', officialProvider: 'OpenAI' })
assert.equal(official.tokensPerSecond, 40)
assert.equal(official.selection.strategy, 'official')
assert.equal(official.selection.tag, 'openai')

const fallback = selectThroughput([
  { provider_name: 'A', tag: 'a/us', throughput_last_30m: { p50: 10 } },
  { provider_name: 'A', tag: 'a/eu', throughput_last_30m: { p50: 20 } },
  { provider_name: 'B', tag: 'b', throughput_last_30m: { p50: 40 } },
  { provider_name: 'B', tag: 'b/region', throughput_last_30m: { p50: 60 } },
  { provider_name: 'B', tag: 'b/flex', throughput_last_30m: { p50: 999 } }
], { modelId: 'publisher/test-model', officialProvider: 'Publisher' })
assert.equal(fallback.tokensPerSecond, 32.5)
assert.equal(fallback.selection.strategy, 'provider-median')

const originalFetch = globalThis.fetch
globalThis.fetch = async () => {
  throw new Error('network unavailable')
}
assert.deepEqual(await loadModelPerformance(), { updatedAt: null, models: {} })
globalThis.fetch = originalFetch

const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), 'model-performance-'))
const mapPath = path.join(temporaryDirectory, 'map.json')
const outputPath = path.join(temporaryDirectory, 'performance.json')
const previousSnapshot = {
  schema_version: 1,
  updatedAt: '2026-09-07T00:00:00.000Z',
  models: {}
}
await writeFile(mapPath, JSON.stringify({
  schema_version: 1,
  models: { '시험 모델': { modelId: 'openai/test-model', officialProvider: 'OpenAI' } }
}))
await writeFile(outputPath, JSON.stringify(previousSnapshot))
const failedRefresh = await refreshModelPerformance({
  mapPath,
  outputPath,
  apiKey: 'test-key',
  fetchImpl: async () => { throw new Error('network unavailable') }
})
assert.equal(failedRefresh.refreshed, false)
assert.equal(JSON.parse(await readFile(outputPath, 'utf8')).updatedAt, previousSnapshot.updatedAt)
await rm(temporaryDirectory, { recursive: true, force: true })

await server.close()
console.log('model-performance assertions passed')
