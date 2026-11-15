import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true }
})

try {
  const {
    getLatestVersionModelNames,
    isLatestVersionModel,
    isLegacyModel,
    isFreeModel,
    applyQuickFilters
  } = await server.ssrLoadModule('/src/utils/modelFilters.js')

  const metadata = {
    'GPT-5.1 (high)': { productLine: 'GPT', releaseDate: '2025-11-12', accessTier: 'paid' },
    'GPT-5.4 (high)': { productLine: 'GPT', releaseDate: '2026-03-05', accessTier: 'free' },
    'GPT-5.4 (none)': { productLine: 'GPT', releaseDate: '2026-03-05', accessTier: 'free' },
    'Claude Opus 4.5': { productLine: 'Claude', releaseDate: '2025-11-24', accessTier: 'paid' },
    'Standalone Older': { releaseDate: '2020-01-01', accessTier: 'free' },
    'Standalone Newer': { releaseDate: '2026-01-01', accessTier: 'paid' },
    'Undated GPT': { productLine: 'GPT', accessTier: 'paid' },
    'Unknown Tier': { productLine: 'Unknown', releaseDate: '2026-01-01' },
    'Paid Tier': { productLine: 'Paid', releaseDate: '2026-01-01', accessTier: 'paid' }
  }

  const latestNames = getLatestVersionModelNames(metadata)
  assert.ok(latestNames.has('GPT-5.4 (high)'))
  assert.ok(latestNames.has('GPT-5.4 (none)'))
  assert.ok(!latestNames.has('GPT-5.1 (high)'))
  assert.ok(latestNames.has('Standalone Older'))
  assert.ok(latestNames.has('Standalone Newer'))
  assert.ok(latestNames.has('Undated GPT'))

  assert.equal(isFreeModel('GPT-5.4 (high)', metadata), true)
  assert.equal(isFreeModel('Paid Tier', metadata), false)
  assert.equal(isFreeModel('Unknown Tier', metadata), false)
  assert.equal(isFreeModel('Missing Model', metadata), false)

  assert.deepEqual(
    applyQuickFilters(['GPT-5.1 (high)'], { freeOnly: false, latestOnly: true }, metadata),
    []
  )
  assert.deepEqual(
    applyQuickFilters(['GPT-5.4 (high)', 'GPT-5.4 (none)'], { freeOnly: false, latestOnly: true }, metadata),
    ['GPT-5.4 (high)', 'GPT-5.4 (none)']
  )
  assert.deepEqual(
    applyQuickFilters(
      ['GPT-5.4 (high)', 'GPT-5.4 (none)', 'GPT-5.1 (high)', 'Unknown Tier'],
      { freeOnly: true, latestOnly: true },
      metadata
    ),
    ['GPT-5.4 (high)', 'GPT-5.4 (none)']
  )
  assert.deepEqual(applyQuickFilters([], { freeOnly: true, latestOnly: true }, metadata), [])

  const originalNames = ['GPT-5.1 (high)', 'Missing Model', 'GPT-5.4 (high)']
  assert.deepEqual(
    applyQuickFilters(originalNames, { freeOnly: false, latestOnly: false }, metadata),
    originalNames
  )

  const mixedNames = [
    'GPT-5.1 (high)',
    'GPT-5.4 (high)',
    'Standalone Older',
    'Missing Model',
    'Claude Opus 4.5'
  ]
  for (const modelName of mixedNames) {
    assert.equal(
      isLegacyModel(modelName, latestNames, metadata),
      !isLatestVersionModel(modelName, latestNames, metadata),
      modelName
    )
  }
} finally {
  await server.close()
}

console.log('model-filters: free and latest-version filters passed')
