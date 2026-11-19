import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true }
})

try {
  const { MODEL_COLORS, VENDORS, getVendor, getModelColor, groupModelsByVendor, getSortedVendors } =
    await server.ssrLoadModule('/src/utils/colorUtils.js')
  const models = ['Jev 1.13', 'typesafe/jev-1.13', 'JEV 1.13', 'TypeSafe']
  for (const model of models) {
    assert.equal(getVendor(model).id, 'typesafe')
    assert.equal(getVendor(model).name, 'TypeSafe')
    assert.equal(getVendor(model).color, '#F386A1')
    assert.equal(getModelColor(model), '#F386A1')
  }
  const existing = ['GPT', 'Gemini', 'Claude', 'Mistral', 'Grok', 'DeepSeek', 'EXAONE',
    'Solar', 'Kimi', 'GLM', 'Qwen', 'Kanana', 'MiniMax', 'Motif', 'Muse Spark']
  for (const [index, model] of existing.entries()) {
    assert.equal(getVendor(model).id, VENDORS[index].id)
    assert.equal(getModelColor(model), VENDORS[index].color)
  }
  const raonModels = ['Raon-1 mini preview', 'KRAFTON/Raon-1-mini-preview']
  for (const model of raonModels) {
    assert.equal(getVendor(model).id, 'krafton')
    assert.equal(getVendor(model).name, 'KRAFTON')
    assert.equal(getVendor(model).color, '#F9423A')
    assert.equal(getModelColor(model), '#F9423A')
  }
  const midmModels = ['Mi:dm K 3.0 Pro', 'kt/midm-k-3.0-pro']
  for (const model of midmModels) {
    assert.equal(getVendor(model).id, 'kt')
    assert.equal(getVendor(model).name, 'KT')
    assert.equal(getVendor(model).color, '#E4002B')
    assert.equal(getModelColor(model), '#E4002B')
  }
  assert.equal(getVendor('Unknown').id, 'other')
  assert.equal(getModelColor('Unknown'), MODEL_COLORS.default)
  const groups = groupModelsByVendor([...models, ...raonModels, ...midmModels, 'GPT', 'Unknown'])
  assert.deepEqual(new Set(groups.typesafe), new Set(models))
  assert.deepEqual(new Set(groups.krafton), new Set(raonModels))
  assert.deepEqual(new Set(groups.kt), new Set(midmModels))
  assert.deepEqual(groups.other, ['Unknown'])
  assert.equal(getSortedVendors(groups)[0].id, 'typesafe')
} finally {
  await server.close()
}
console.log('model-colors: TypeSafe/KRAFTON/KT classification, colors, grouping, and existing vendors passed')
