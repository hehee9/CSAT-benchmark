import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {
  discoverPublishedModelNames
} from '../scripts/copy-data.mjs'
import {
  matchModelNames,
  refreshModelPerformance
} from '../scripts/refresh-model-performance.mjs'

const temporaryDirectory = await mkdtemp(path.join(os.tmpdir(), 'model-performance-matching-'))

/** @description 임시 공개 자료 JSON 기록 */
async function _writeJson(filePath, payload) {
  await mkdir(path.dirname(filePath), { recursive: true })
  await writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`)
}

const catalog = [
  { id: 'deepseek/deepseek-v4.1-flash', name: 'DeepSeek: DeepSeek V4.1 Flash' },
  { id: 'vendor/arbitrary-model-2026', name: 'Vendor: Arbitrary Model 2026' },
  { id: 'google/gemini-3-flash-preview', name: 'Google: Gemini 3 Flash Preview' },
  { id: 'google/gemini-3.1-pro-preview', name: 'Google: Gemini 3.1 Pro Preview' },
  { id: 'vendor/alpha-2025-09', name: 'Vendor: Alpha 2025-09' },
  { id: 'vendor/alpha-pro', name: 'Vendor: Alpha Pro' },
  { id: 'vendor/alpha-lite', name: 'Vendor: Alpha Lite' },
  { id: 'first/shared-model', name: 'First: Shared Model' },
  { id: 'second/shared-model', name: 'Second: Shared Model' },
  { id: 'vendor/service-model:free', name: 'Vendor: Service Model (free)' }
]

const mapPayload = {
  schema_version: 1,
  models: {
    'GPT-4o': { modelId: 'openai/gpt-4o-2024-11-20', officialProvider: 'OpenAI' },
    'Muse Spark 1.3 (high)': { modelId: 'meta/muse-spark-1.3-contributor', officialProvider: 'Meta' },
    'Muse Spark 1.3 (minimal)': { modelId: 'meta/muse-spark-1.3-contributor', officialProvider: 'Meta' },
    'Qwen3.5 397B (Non-Thinking)': { modelId: 'qwen/qwen3.5-397b-a17b', officialProvider: 'Alibaba' },
    'Qwen3.5 397B (Thinking)': { modelId: 'qwen/qwen3.5-397b-a17b', officialProvider: 'Alibaba' }
  }
}

const matching = matchModelNames([
  'DeepSeek V4.1 Flash (High)',
  'DeepSeek V4.1 Flash (high)',
  'Arbitrary Model 2026',
  'Gemini 3 Flash',
  'Gemini 3.1 Pro',
  'Alpha 2025-09',
  'Alpha Pro',
  'Alpha Lite',
  'Alpha',
  'Shared Model',
  'Service Model',
  'GPT-4o',
  'Muse Spark 1.3 (high)',
  'Muse Spark 1.3 (minimal)',
  'Qwen3.5 397B (Non-Thinking)',
  'Qwen3.5 397B (Thinking)'
], mapPayload, catalog)

assert.equal(matching.models['DeepSeek V4.1 Flash (High)'].modelId, 'deepseek/deepseek-v4.1-flash')
assert.equal(matching.models['DeepSeek V4.1 Flash (high)'].modelId, 'deepseek/deepseek-v4.1-flash')
assert.equal(matching.models['Arbitrary Model 2026'].modelId, 'vendor/arbitrary-model-2026')
assert.equal(matching.models['Gemini 3 Flash'].modelId, 'google/gemini-3-flash-preview')
assert.equal(matching.models['Gemini 3.1 Pro'].modelId, 'google/gemini-3.1-pro-preview')
assert.equal(matching.models['Alpha 2025-09'].modelId, 'vendor/alpha-2025-09')
assert.equal(matching.models['Alpha Pro'].modelId, 'vendor/alpha-pro')
assert.equal(matching.models['Alpha Lite'].modelId, 'vendor/alpha-lite')
assert.equal(matching.models['GPT-4o'].modelId, 'openai/gpt-4o-2024-11-20')
assert.equal(matching.models['Muse Spark 1.3 (high)'].modelId, 'meta/muse-spark-1.3-contributor')
assert.equal(matching.models['Qwen3.5 397B (Thinking)'].modelId, 'qwen/qwen3.5-397b-a17b')
assert.equal(matching.models.Alpha, null)
assert.equal(matching.models['Service Model'], null)
assert.equal(matching.models['Shared Model'], null)
assert.deepEqual(matching.diagnostics.unmatched, ['Alpha', 'Service Model'])
assert.deepEqual(matching.diagnostics.ambiguous, [{
  modelName: 'Shared Model',
  candidates: ['first/shared-model', 'second/shared-model']
}])

const fixtureRepo = path.join(temporaryDirectory, 'repo')
const fixtureCatalogDir = path.join(fixtureRepo, 'benchmarks')
const fixturePublishedDir = path.join(fixtureRepo, 'published')
const modernResults = [{ model_name: 'Modern Model' }, { model_name: 'Shared Model' }, { model_name: 'Modern Model' }]
await _writeJson(path.join(fixtureCatalogDir, 'modern.json'), {
  schema_version: 1,
  id: 'modern',
  publish: true,
  status: 'ready',
  modes: [{ id: 'default', public_results: 'unused-results.json', public_token_usage: 'unused-token.json' }]
})
await _writeJson(path.join(fixturePublishedDir, 'modern', 'default', 'results.json'), modernResults)
await _writeJson(path.join(fixturePublishedDir, 'modern', 'default', 'token_usage.json'), {})
await _writeJson(path.join(fixturePublishedDir, 'modern', 'default', 'questions_metadata.json'), {})

await _writeJson(path.join(fixtureCatalogDir, 'legacy.json'), {
  schema_version: 1,
  id: 'legacy',
  publish: true,
  status: 'ready',
  modes: [{ id: 'default', public_results: 'legacy-results.json', public_token_usage: 'legacy-token.json' }]
})
await _writeJson(path.join(fixtureRepo, 'legacy-results.json'), [{ model_name: 'Legacy Model' }])
await _writeJson(path.join(fixtureRepo, 'legacy-token.json'), {})

await _writeJson(path.join(fixtureCatalogDir, 'hidden.json'), {
  schema_version: 1,
  id: 'hidden',
  publish: false,
  status: 'ready',
  modes: [{ id: 'default' }]
})
await _writeJson(path.join(fixturePublishedDir, 'hidden', 'default', 'results.json'), [{ model_name: 'Hidden Model' }])

await _writeJson(path.join(fixtureCatalogDir, 'preparing.json'), {
  schema_version: 1,
  id: 'preparing',
  publish: true,
  status: 'preparation',
  modes: [{ id: 'default' }]
})

assert.deepEqual(await discoverPublishedModelNames({
  repoRoot: fixtureRepo,
  catalogDir: fixtureCatalogDir,
  publishedDir: fixturePublishedDir
}), ['Legacy Model', 'Modern Model', 'Shared Model'])

const refreshRepo = path.join(temporaryDirectory, 'refresh-repo')
const refreshCatalogDir = path.join(refreshRepo, 'benchmarks')
const refreshPublishedDir = path.join(refreshRepo, 'published')
await _writeJson(path.join(refreshCatalogDir, 'refresh.json'), {
  schema_version: 1,
  id: 'refresh',
  publish: true,
  status: 'ready',
  modes: [{ id: 'default' }]
})
await _writeJson(path.join(refreshPublishedDir, 'refresh', 'default', 'results.json'), [
  { model_name: 'DeepSeek V4.1 Flash (High)' },
  { model_name: 'DeepSeek V4.1 Flash (high)' },
  { model_name: 'Arbitrary Model 2026' }
])
await _writeJson(path.join(refreshPublishedDir, 'refresh', 'default', 'token_usage.json'), {})
await _writeJson(path.join(refreshPublishedDir, 'refresh', 'default', 'questions_metadata.json'), {})

const outputPath = path.join(temporaryDirectory, 'performance.json')
const calls = []
await _writeJson(path.join(temporaryDirectory, 'map.json'), { schema_version: 1, models: {} })
const refreshResult = await refreshModelPerformance({
  mapPath: path.join(temporaryDirectory, 'map.json'),
  outputPath,
  apiKey: 'test-key',
  repoRoot: refreshRepo,
  catalogDir: refreshCatalogDir,
  publishedDir: refreshPublishedDir,
  fetchImpl: async (url) => {
    calls.push(url)
    if (url.endsWith('/models')) return { ok: true, json: async () => ({ data: catalog }) }
    if (url.endsWith('/deepseek/deepseek-v4.1-flash/endpoints')) {
      return { ok: true, json: async () => ({ data: { endpoints: [
        { provider_name: 'DeepSeek', tag: 'deepseek', throughput_last_30m: { p50: 40 } }
      ] } }) }
    }
    if (url.endsWith('/vendor/arbitrary-model-2026/endpoints')) {
      return { ok: true, json: async () => ({ data: { endpoints: [
        { provider_name: 'Vendor', tag: 'vendor', throughput_last_30m: { p50: 20 } }
      ] } }) }
    }
    throw new Error(`unexpected request: ${url}`)
  },
  now: new Date('2026-09-10T00:00:00.000Z')
})

assert.equal(refreshResult.refreshed, true)
assert.equal(refreshResult.snapshot.models['DeepSeek V4.1 Flash (High)'].tokensPerSecond, 40)
assert.equal(refreshResult.snapshot.models['DeepSeek V4.1 Flash (high)'].modelId, 'deepseek/deepseek-v4.1-flash')
assert.equal(refreshResult.snapshot.models['Arbitrary Model 2026'].tokensPerSecond, 20)
assert.equal(calls.filter(url => url.endsWith('/deepseek/deepseek-v4.1-flash/endpoints')).length, 1)
assert.equal(calls.filter(url => url.endsWith('/models')).length, 1)
assert.deepEqual(refreshResult.matching, { unmatched: [], ambiguous: [] })
assert.deepEqual(JSON.parse(await readFile(outputPath, 'utf8')), refreshResult.snapshot)

await rm(temporaryDirectory, { recursive: true, force: true })
console.log('model-performance matching assertions passed')
