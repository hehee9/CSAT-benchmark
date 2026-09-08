import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { access, mkdir, writeFile } from 'node:fs/promises'
import process from 'node:process'
import { chromium } from 'playwright'
import { createServer } from 'vite'
import { copyDataFiles } from './copy-data.mjs'
import {
  EXPORT_GROUP_ORDER,
  getExportTargetById,
  getExportTargetsByGroup
} from './export-manifest.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const webRoot = path.resolve(__dirname, '..')
const DEFAULT_VIEWPORT = { width: 1920, height: 1400 }
const DOWNLOAD_TIMEOUT_MS = 20000
const READINESS_POLL_INTERVAL_MS = 250
const DIAGNOSTICS_DIR = path.join(webRoot, '.tmp', 'export-diagnostics')
const GROUP_TIMEOUTS = {
  overview: 20000,
  subjects: 25000,
  cost: 45000
}
const NO_DATA_PATTERNS = [
  '데이터가 없습니다',
  '비용 데이터가 없습니다',
  'No data available',
  'No cost data available'
]
const TAB_LABELS = {
  overview: '종합 대시보드',
  subjects: '과목별 상세',
  compare: '모델 비교',
  cost: '상세 분석'
}
const SCORE_VIEW_LABELS = {
  average: '종합',
  bestWorst: '최고/최저',
  withImage: '이미지O',
  withoutImage: '이미지X'
}

function parseCsvList(rawValue) {
  if (!rawValue) return []

  return rawValue
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
}

function uniqueValues(values) {
  return [...new Set(values)]
}

function parseArgs(argv) {
  const options = {
    onlyIds: [],
    groups: [],
    positionals: [],
    headed: false,
    baseUrl: '',
    outputDir: '',
    publicDir: process.env.CSAT_PUBLIC_DIR || '',
    viewport: { ...DEFAULT_VIEWPORT }
  }

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]

    if (arg === '--only') {
      options.onlyIds.push(...parseCsvList(argv[i + 1] || ''))
      i += 1
      continue
    }

    if (arg === '--group') {
      options.groups.push(argv[i + 1] || '')
      i += 1
      continue
    }

    if (arg === '--headed') {
      options.headed = true
      continue
    }

    if (arg === '--base-url') {
      options.baseUrl = argv[i + 1] || ''
      i += 1
      continue
    }

    if (arg === '--output-dir') {
      options.outputDir = argv[i + 1] || ''
      i += 1
      continue
    }

    if (arg === '--public-dir') {
      options.publicDir = argv[i + 1] || ''
      i += 1
      continue
    }

    if (arg === '--viewport') {
      const rawViewport = argv[i + 1] || ''
      const match = rawViewport.match(/^(\d+)x(\d+)$/i)
      if (!match) {
        throw new Error(`Invalid viewport: ${rawViewport}`)
      }
      options.viewport = {
        width: Number(match[1]),
        height: Number(match[2])
      }
      i += 1
      continue
    }

    if (!arg.startsWith('--')) {
      options.positionals.push(arg)
    }
  }

  options.onlyIds = uniqueValues(options.onlyIds)
  options.groups = uniqueValues(options.groups.map((group) => group.trim()).filter(Boolean))

  if (options.onlyIds.length === 0 && process.env.npm_config_only) {
    options.onlyIds = uniqueValues(parseCsvList(process.env.npm_config_only))
  }

  if (options.groups.length === 0 && process.env.npm_config_group) {
    options.groups = uniqueValues(parseCsvList(process.env.npm_config_group))
  }

  if (options.onlyIds.length === 0 && options.groups.length === 0 && options.positionals.length > 0) {
    const positionals = uniqueValues(options.positionals.flatMap((value) => parseCsvList(value)))
    const allTargets = positionals.every((value) => Boolean(getExportTargetById(value)))
    const allGroups = positionals.every((value) => EXPORT_GROUP_ORDER.includes(value))

    if (allTargets) {
      options.onlyIds = positionals
    } else if (allGroups) {
      options.groups = positionals
    }
  }

  return options
}

function buildTargetUrl(baseUrl, target) {
  const url = new URL(baseUrl)
  url.search = ''
  const shareState = {
    exam: target.params.exam || 'csat-2026',
    mode: target.params.mode || 'default',
    scoreBasis: target.params.scoreBasis || 'normalized'
  }

  Object.entries(shareState).forEach(([key, value]) => {
    url.searchParams.set(key, value)
  })

  return url.toString()
}

function resolveTargets(options) {
  const targetOptions = options.outputDir ? { outputDir: options.outputDir } : {}
  if (options.onlyIds.length > 0) {
    const unknownIds = options.onlyIds.filter((id) => !getExportTargetById(id, targetOptions))
    if (unknownIds.length > 0) {
      throw new Error(`Unknown export target: ${unknownIds.join(', ')}`)
    }

    return options.onlyIds.map((id) => getExportTargetById(id, targetOptions))
  }

  const groups = options.groups.length > 0 ? options.groups : EXPORT_GROUP_ORDER
  const unknownGroups = groups.filter((group) => !EXPORT_GROUP_ORDER.includes(group))

  if (unknownGroups.length > 0) {
    throw new Error(`Unknown export group: ${unknownGroups.join(', ')}`)
  }

  return groups.flatMap((group) => getExportTargetsByGroup(group, targetOptions))
}

function buildTargetBatches(targets) {
  const batches = []
  const batchMap = new Map()

  targets.forEach((target) => {
    if (!batchMap.has(target.group)) {
      const batch = { group: target.group, targets: [] }
      batchMap.set(target.group, batch)
      batches.push(batch)
    }

    batchMap.get(target.group).targets.push(target)
  })

  return batches
}

function getGroupTimeout(group) {
  return GROUP_TIMEOUTS[group] || GROUP_TIMEOUTS.overview
}

function sanitizeName(value) {
  return value.replace(/[^a-z0-9._-]+/gi, '_')
}

async function startDevServer(publicDir = '') {
  const publicDirPath = publicDir
    ? path.resolve(webRoot, '..', publicDir)
    : undefined
  const server = await createServer({
    root: webRoot,
    publicDir: publicDirPath,
    server: {
      host: '127.0.0.1',
      port: 4173,
      strictPort: true
    }
  })

  await server.listen()
  const baseUrl = server.resolvedUrls?.local?.[0]

  if (!baseUrl) {
    throw new Error('Failed to resolve local Vite server URL')
  }

  return { server, baseUrl }
}

async function collectPageDiagnostics(page) {
  try {
    return await page.evaluate(({ noDataPatterns }) => {
      const bodyText = document.body?.innerText || ''
      const hasNoDataText = noDataPatterns.some((pattern) => bodyText.includes(pattern))
      return {
        title: document.title,
        dashboardReady: Boolean(document.querySelector('[data-dashboard-ready="true"]')),
        exportKeys: Array.from(document.querySelectorAll('[data-export-key]'))
          .map((element) => element.getAttribute('data-export-key'))
          .filter(Boolean),
        hasNoDataText,
        bodySnippet: bodyText.replace(/\s+/g, ' ').trim().slice(0, 1000)
      }
    }, { noDataPatterns: NO_DATA_PATTERNS })
  } catch (error) {
    return {
      title: '',
      dashboardReady: false,
      exportKeys: [],
      hasNoDataText: false,
      bodySnippet: `Failed to collect page diagnostics: ${error.message}`
    }
  }
}

async function writeDiagnostics(page, target, url, status, reason) {
  await mkdir(DIAGNOSTICS_DIR, { recursive: true })

  const baseName = sanitizeName(`${target.group}-${target.id}`)
  const screenshotPath = path.join(DIAGNOSTICS_DIR, `${baseName}.png`)
  const metadataPath = path.join(DIAGNOSTICS_DIR, `${baseName}.json`)
  const pageDiagnostics = await collectPageDiagnostics(page)

  try {
    await page.screenshot({ path: screenshotPath, fullPage: true })
  } catch (error) {
    pageDiagnostics.screenshotError = error.message
  }

  await writeFile(metadataPath, JSON.stringify({
    status,
    reason,
    targetId: target.id,
    group: target.group,
    exportKey: target.exportKey,
    url,
    capturedAt: new Date().toISOString(),
    screenshotPath,
    ...pageDiagnostics
  }, null, 2))

  return { metadataPath, screenshotPath }
}

async function waitForDashboardState(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs

  while (Date.now() < deadline) {
    const state = await page.evaluate(({ noDataPatterns }) => {
      const dashboardReady = Boolean(document.querySelector('[data-dashboard-ready="true"]'))
      const bodyText = document.body?.innerText || ''
      const noDataPattern = noDataPatterns.find((pattern) => bodyText.includes(pattern)) || ''

      return {
        dashboardReady,
        noDataPattern
      }
    }, { noDataPatterns: NO_DATA_PATTERNS })

    if (state.dashboardReady && state.noDataPattern) {
      return {
        status: 'skipped',
        reason: `No data state detected: ${state.noDataPattern}`
      }
    }

    if (state.dashboardReady) {
      await page.waitForTimeout(300)
      return {
        status: 'ready',
        reason: 'Dashboard became ready'
      }
    }

    await page.waitForTimeout(READINESS_POLL_INTERVAL_MS)
  }

  return {
    status: 'failed-to-diagnose',
    reason: 'Timed out waiting for dashboard readiness'
  }
}

async function _waitForExportControl(page, target, timeoutMs) {
  const exportSelector = `[data-export-key="${target.exportKey}"]`
  const deadline = Date.now() + timeoutMs

  while (Date.now() < deadline) {
    const state = await page.evaluate(({ exportKey, noDataPatterns }) => {
      const exportButton = document.querySelector(`[data-export-key="${exportKey}"]`)
      const exportReady = Boolean(
        exportButton &&
        exportButton.getBoundingClientRect().width > 0 &&
        exportButton.getBoundingClientRect().height > 0 &&
        getComputedStyle(exportButton).visibility !== 'hidden' &&
        getComputedStyle(exportButton).display !== 'none'
      )
      const bodyText = document.body?.innerText || ''
      const noDataPattern = noDataPatterns.find((pattern) => bodyText.includes(pattern)) || ''

      return { exportReady, noDataPattern }
    }, { exportKey: target.exportKey, noDataPatterns: NO_DATA_PATTERNS })

    if (state.exportReady) {
      await page.waitForTimeout(300)
      return {
        status: 'ready',
        reason: `Export control became visible: ${exportSelector}`
      }
    }

    if (state.noDataPattern) {
      return {
        status: 'skipped',
        reason: `No data state detected: ${state.noDataPattern}`
      }
    }

    await page.waitForTimeout(READINESS_POLL_INTERVAL_MS)
  }

  return {
    status: 'failed-to-diagnose',
    reason: `Timed out waiting for export control: ${exportSelector}`
  }
}

/**
 * @brief 지정된 버튼이 활성 상태가 될 때까지 대기
 * @param {import('playwright').Page} page - 현재 페이지
 * @param {string} label - 버튼 표시 이름
 * @return {Promise<void>} 활성 상태 대기 완료
 */
async function _waitForActiveButton(page, label) {
  await page.waitForFunction((expectedLabel) => Array.from(document.querySelectorAll('button'))
    .some(button => button.textContent.trim() === expectedLabel && button.classList.contains('bg-blue-500')), label)
}

/**
 * @brief 대상의 화면 상태를 실제 사용자 입력으로 적용
 * @param {import('playwright').Page} page - 현재 페이지
 * @param {Object} target - 이미지 내보내기 대상
 * @return {Promise<void>} 화면 상태 적용 완료
 */
async function _applyTargetParams(page, target) {
  const params = target.params

  if (params.tab) {
    const tabLabel = TAB_LABELS[params.tab]
    if (!tabLabel) throw new Error(`Unknown dashboard tab: ${params.tab}`)
    await page.getByRole('button', { name: tabLabel, exact: true }).click()
    await _waitForActiveButton(page, tabLabel)
  }

  if (params.scoreView) {
    const scoreViewLabel = SCORE_VIEW_LABELS[params.scoreView]
    if (!scoreViewLabel) throw new Error(`Unknown score view: ${params.scoreView}`)
    await page.getByRole('button', { name: scoreViewLabel, exact: true }).click()
    await _waitForActiveButton(page, scoreViewLabel)
  }

  if (params.subjects) {
    const subjects = parseCsvList(params.subjects)
    if (subjects.some(subject => subject.includes('-'))) {
      await page.getByRole('complementary').getByRole('button', { name: '세부 점수 표시', exact: true }).click()
    }

    for (const subject of subjects) {
      const label = subject.includes('-')
        ? subject.slice(subject.indexOf('-') + 1)
        : subject
      const checkbox = page.locator('label').filter({ hasText: label }).first().locator('input[type="checkbox"]')
      await checkbox.check()
    }
  }

  if (params.analysisX) {
    await page.locator('#analysis-x-metric').selectOption(params.analysisX)
  }

  if (params.analysisY) {
    await page.locator('#analysis-y-metric').selectOption(params.analysisY)
  }

  await page.waitForTimeout(300)
}

async function exportTarget(page, baseUrl, target) {
  const url = buildTargetUrl(baseUrl, target)
  const timeoutMs = getGroupTimeout(target.group)

  try {
    await page.goto(url, { waitUntil: 'domcontentloaded' })
    const readiness = await waitForDashboardState(page, timeoutMs)

    if (readiness.status !== 'ready') {
      const diagnostics = await writeDiagnostics(page, target, url, readiness.status, readiness.reason)
      console.warn(
        `${readiness.status === 'skipped' ? 'Skipped' : 'Failed to diagnose'} ${target.id} (${readiness.reason})`
      )
      return {
        status: readiness.status,
        target,
        reason: readiness.reason,
        diagnostics
      }
    }

    await _applyTargetParams(page, target)
    const exportReadiness = await _waitForExportControl(page, target, timeoutMs)

    if (exportReadiness.status !== 'ready') {
      const diagnostics = await writeDiagnostics(page, target, url, exportReadiness.status, exportReadiness.reason)
      console.warn(
        `${exportReadiness.status === 'skipped' ? 'Skipped' : 'Failed to diagnose'} ${target.id} (${exportReadiness.reason})`
      )
      return {
        status: exportReadiness.status,
        target,
        reason: exportReadiness.reason,
        diagnostics
      }
    }

    const outputDir = path.dirname(target.outputPath)
    await mkdir(outputDir, { recursive: true })

    const downloadPromise = page.waitForEvent('download', { timeout: DOWNLOAD_TIMEOUT_MS })
    await page.locator(`[data-export-key="${target.exportKey}"]`).click()
    const download = await downloadPromise
    await download.saveAs(target.outputPath)
    await access(target.outputPath)

    console.log(`Exported ${target.id} -> ${target.outputPath}`)
    return {
      status: 'exported',
      target
    }
  } catch (error) {
    const diagnostics = await writeDiagnostics(page, target, url, 'failed-to-diagnose', error.message)
    console.warn(`Failed to diagnose ${target.id} (${error.message})`)
    return {
      status: 'failed-to-diagnose',
      target,
      reason: error.message,
      diagnostics
    }
  }
}

async function runBatch(browser, baseUrl, targets, options) {
  const context = await browser.newContext({
    acceptDownloads: true,
    viewport: options.viewport
  })
  await context.addInitScript(() => {
    localStorage.setItem('language', 'ko')
    localStorage.setItem('theme', 'light')
  })
  const results = []

  try {
    for (const target of targets) {
      const page = await context.newPage()

      try {
        results.push(await exportTarget(page, baseUrl, target))
      } finally {
        await page.close()
      }
    }
  } finally {
    await context.close()
  }

  return results
}

function printSummary(results) {
  const summary = results.reduce((accumulator, result) => {
    accumulator[result.status] += 1
    return accumulator
  }, {
    exported: 0,
    skipped: 0,
    'failed-to-diagnose': 0
  })

  console.log('')
  console.log('Export summary')
  console.log(`- exported: ${summary.exported}`)
  console.log(`- skipped: ${summary.skipped}`)
  console.log(`- failed-to-diagnose: ${summary['failed-to-diagnose']}`)
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  const targets = resolveTargets(options)

  if (targets.length === 0) {
    throw new Error('No export targets resolved')
  }

  let devServer = null
  let baseUrl = options.baseUrl

  if (!baseUrl) {
    await copyDataFiles({ outputDir: options.publicDir || undefined })
    devServer = await startDevServer(options.publicDir)
    baseUrl = devServer.baseUrl
  }

  const browser = await chromium.launch({ headless: !options.headed })
  const batches = buildTargetBatches(targets)
  const results = []

  try {
    for (const batch of batches) {
      console.log(`Running export batch: ${batch.group} (${batch.targets.length} targets)`)
      const batchResults = await runBatch(browser, baseUrl, batch.targets, options)
      results.push(...batchResults)
    }
  } finally {
    await browser.close()
    if (devServer) {
      await devServer.server.close()
    }
  }

  printSummary(results)

  if (results.every((result) => result.status !== 'exported')) {
    process.exit(1)
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
