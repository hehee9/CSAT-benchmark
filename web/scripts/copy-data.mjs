import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import {
  access,
  cp,
  mkdir,
  readdir,
  readFile,
  rm,
  writeFile
} from 'node:fs/promises'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const webRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(webRoot, '..')
const CATALOG_SCHEMA_VERSION = 1
const DEFAULT_EXAM_ID = 'csat-2026'
const YEAR_MONTH_PATTERN = /^\d{4}-(?:0[1-9]|1[0-2])$/
const HISTORICAL_MIRRORS = {
  default: { results: 'all_results.json', tokenUsage: 'token_usage.json' },
  easy: { results: 'easy_all_results.json', tokenUsage: 'easy_token_usage.json' }
}

/** @description 환경 변수 또는 옵션 경로를 기준 루트 기준 절대 경로로 변환 */
function _resolveConfiguredPath(value, fallback, baseRoot) {
  if (!value) return fallback
  return path.isAbsolute(value) ? path.resolve(value) : path.resolve(baseRoot, value)
}

/** @description 기준 디렉터리 내부 경로 검증 및 변환 */
function _resolveInside(root, relativePath, label) {
  if (typeof relativePath !== 'string' || !relativePath.trim()) {
    throw new Error(`${label}은 비어 있지 않은 상대 경로여야 합니다`)
  }

  const basePath = path.resolve(root)
  const resolvedPath = path.resolve(basePath, relativePath)
  if (resolvedPath !== basePath && !resolvedPath.startsWith(`${basePath}${path.sep}`)) {
    throw new Error(`${label}이 기준 경로를 벗어납니다: ${relativePath}`)
  }
  return resolvedPath
}

/** @description UTF-8 JSON 파일 로드 */
async function _readJson(filePath, label) {
  let contents
  try {
    contents = await readFile(filePath, 'utf8')
  } catch (error) {
    if (error.code === 'ENOENT') return null
    throw error
  }

  try {
    return JSON.parse(contents)
  } catch (error) {
    throw new Error(`${label} JSON 파싱 실패: ${filePath}: ${error.message}`)
  }
}

/** @description 파일 존재 여부 확인 */
async function _fileExists(filePath) {
  try {
    await access(filePath)
    return true
  } catch (error) {
    if (error.code === 'ENOENT') return false
    throw error
  }
}

/** @description 공개 파일을 그대로 복사하고 동일 파일 복사를 건너뜀 */
async function _copyExact(sourcePath, targetPath) {
  const source = path.resolve(sourcePath)
  const target = path.resolve(targetPath)
  await mkdir(path.dirname(target), { recursive: true })
  if (source === target) return
  await cp(source, target, { force: true })
}

/** @description 공개 JSON 기본값을 파일로 저장 */
async function _writeJson(targetPath, payload) {
  await mkdir(path.dirname(targetPath), { recursive: true })
  await writeFile(targetPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
}

/** @description 시험 매니페스트의 공개 섹션 필드만 추림 */
function _publicSections(manifest, manifestPath) {
  if (!Array.isArray(manifest.sections)) {
    throw new Error(`시험 sections가 목록이 아닙니다: ${manifestPath}`)
  }

  const targets = new Set()
  return manifest.sections.map((section, index) => {
    if (!section || typeof section !== 'object') {
      throw new Error(`시험 sections[${index}]가 객체가 아닙니다: ${manifestPath}`)
    }

    const fields = ['target', 'subject', 'section', 'group', 'kind', 'max_points']
    for (const field of fields) {
      if (section[field] === undefined) {
        throw new Error(`시험 sections[${index}].${field}가 없습니다: ${manifestPath}`)
      }
    }
    for (const field of fields.slice(0, -1)) {
      if (typeof section[field] !== 'string' || !section[field].trim()) {
        throw new Error(`시험 sections[${index}].${field}가 올바르지 않습니다: ${manifestPath}`)
      }
    }
    if (
      typeof section.max_points !== 'number' ||
      !Number.isInteger(section.max_points) ||
      section.max_points < 1
    ) {
      throw new Error(`시험 sections[${index}].max_points가 올바르지 않습니다: ${manifestPath}`)
    }
    if (targets.has(section.target)) {
      throw new Error(`시험 sections target이 중복됩니다: ${manifestPath}`)
    }
    targets.add(section.target)

    return Object.fromEntries(fields.map(field => [field, section[field]]))
  })
}

/** @description 공개 모드 카탈로그와 내부 소스 힌트를 분리 */
function _publicModes(manifest, manifestPath) {
  if (!Array.isArray(manifest.modes)) {
    throw new Error(`시험 modes가 목록이 아닙니다: ${manifestPath}`)
  }

  const modeIds = new Set()
  return manifest.modes.map((mode, index) => {
    if (!mode || typeof mode !== 'object') {
      throw new Error(`시험 modes[${index}]가 객체가 아닙니다: ${manifestPath}`)
    }
    for (const field of ['id', 'label', 'input_mode']) {
      if (mode[field] === undefined) {
        throw new Error(`시험 modes[${index}].${field}가 없습니다: ${manifestPath}`)
      }
    }
    for (const field of ['label', 'input_mode']) {
      if (typeof mode[field] !== 'string' || !mode[field].trim()) {
        throw new Error(`시험 modes[${index}].${field}가 올바르지 않습니다: ${manifestPath}`)
      }
    }
    if (
      typeof mode.id !== 'string' ||
      !mode.id.trim() ||
      mode.id === '.' ||
      mode.id === '..' ||
      mode.id.includes('/') ||
      mode.id.includes('\\')
    ) {
      throw new Error(`시험 modes[${index}].id가 올바르지 않습니다: ${manifestPath}`)
    }
    if (modeIds.has(mode.id)) {
      throw new Error(`시험 modes id가 중복됩니다: ${manifestPath}`)
    }
    modeIds.add(mode.id)

    return {
      id: mode.id,
      label: mode.label,
      input_mode: mode.input_mode,
      results: `benchmarks/${manifest.id}/${mode.id}/results.json`,
      token_usage: `benchmarks/${manifest.id}/${mode.id}/token_usage.json`,
      questions_metadata: `benchmarks/${manifest.id}/${mode.id}/questions_metadata.json`
    }
  })
}

/** @description 내부 경로를 제거한 공개 시험 카탈로그 생성 */
export function createPublicCatalog(manifests, defaultExamId = DEFAULT_EXAM_ID) {
  const exams = manifests
    .filter(({ manifest }) => manifest.publish === true)
    .map(({ manifest, manifestPath }) => {
      if (
        typeof manifest.id !== 'string' ||
        !manifest.id.trim() ||
        manifest.id === '.' ||
        manifest.id === '..' ||
        manifest.id.includes('/') ||
        manifest.id.includes('\\')
      ) {
        throw new Error(`시험 id가 올바르지 않습니다: ${manifestPath}`)
      }
      for (const field of ['title', 'status']) {
        if (typeof manifest[field] !== 'string' || !manifest[field].trim()) {
          throw new Error(`시험 ${field}가 없습니다: ${manifestPath}`)
        }
      }
      const shortName = manifest.short_name === undefined ? manifest.title : manifest.short_name
      if (typeof shortName !== 'string' || !shortName.trim()) {
        throw new Error(`시험 short_name이 올바르지 않습니다: ${manifestPath}`)
      }
      const examMonth = manifest.exam_month === undefined ? null : manifest.exam_month
      if (examMonth !== null && (typeof examMonth !== 'string' || !YEAR_MONTH_PATTERN.test(examMonth))) {
        throw new Error(`시험 exam_month가 올바르지 않습니다: ${manifestPath}`)
      }
      return {
        id: manifest.id,
        title: manifest.title,
        status: manifest.status,
        short_name: shortName,
        exam_month: examMonth,
        sections: _publicSections(manifest, manifestPath),
        modes: _publicModes(manifest, manifestPath)
      }
    })

  const examIds = new Set()
  for (const exam of exams) {
    if (examIds.has(exam.id)) throw new Error(`공개 시험 id가 중복됩니다: ${exam.id}`)
    examIds.add(exam.id)
  }

  if (!exams.some(exam => exam.id === defaultExamId)) {
    throw new Error(`공개 기본 시험이 없습니다: ${defaultExamId}`)
  }

  return {
    schema_version: CATALOG_SCHEMA_VERSION,
    default_exam: defaultExamId,
    exams
  }
}

/** @description benchmarks 디렉터리에서 시험 매니페스트 로드 */
async function _loadManifests(catalogDir) {
  const entries = await readdir(catalogDir, { withFileTypes: true })
  const manifestEntries = entries
    .filter(entry => entry.isFile() && entry.name.endsWith('.json'))
    .sort((left, right) => left.name.localeCompare(right.name))

  const manifests = []
  for (const entry of manifestEntries) {
    const manifestPath = path.join(catalogDir, entry.name)
    const manifest = await _readJson(manifestPath, '시험 매니페스트')
    if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
      throw new Error(`시험 매니페스트가 객체가 아닙니다: ${manifestPath}`)
    }
    if (typeof manifest.id !== 'string' || !manifest.id.trim()) {
      throw new Error(`시험 id가 없습니다: ${manifestPath}`)
    }
    if (manifest.schema_version !== CATALOG_SCHEMA_VERSION) {
      throw new Error(`지원하지 않는 시험 schema_version입니다: ${manifestPath}`)
    }
    manifests.push({ manifest, manifestPath })
  }

  return manifests
}

/** @description 모드 공개 자료의 경로 후보를 계산 */
function _getModeSourceCandidates(manifest, mode, roots) {
  const modernDir = _resolveInside(
    roots.publishedDir,
    path.join(manifest.id, mode.id),
    'published 모드 경로'
  )
  const modern = {
    results: path.join(modernDir, 'results.json'),
    tokenUsage: path.join(modernDir, 'token_usage.json'),
    questionsMetadata: path.join(modernDir, 'questions_metadata.json')
  }
  const legacy = {
    results: mode.public_results
      ? _resolveInside(roots.repoRoot, mode.public_results, 'public_results')
      : null,
    tokenUsage: mode.public_token_usage
      ? _resolveInside(roots.repoRoot, mode.public_token_usage, 'public_token_usage')
      : null
  }
  const metadataCandidates = manifest.id === DEFAULT_EXAM_ID
    ? [
        path.join(roots.repoRoot, 'questions_metadata.json'),
        path.join(roots.webRoot, 'public', 'questions_metadata.json'),
        path.join(roots.repoRoot, 'docs', 'questions_metadata.json'),
        modern.questionsMetadata
      ]
    : [modern.questionsMetadata]

  return { modern, legacy, metadataCandidates }
}

/** @description 공개 결과에서 문항 메타데이터를 최소 생성 */
function _deriveQuestionsMetadata(results) {
  const metadata = {}
  for (const record of results) {
    if (!record || typeof record !== 'object' || !Array.isArray(record.results)) continue
    const key = record.sheet_name || `${record.subject}-${record.section}`
    if (!key || typeof key !== 'string') continue
    metadata[key] ||= {}
    for (const result of record.results) {
      if (!result || result.question_number === undefined) continue
      const hasImage = result.hasImage ?? result.has_image ?? false
      metadata[key][String(result.question_number)] = {
        hasImage: Boolean(hasImage),
        points: result.points || 0
      }
    }
  }
  return metadata
}

/** @description 파일 후보 중 첫 번째 존재 파일 반환 */
async function _firstExisting(candidates) {
  for (const candidate of candidates) {
    if (candidate && await _fileExists(candidate)) return candidate
  }
  return null
}

/** @description 준비 상태 시험의 빈 공개 자료 생성 여부 확인 */
function _isPreparing(manifest) {
  return manifest.status !== 'ready'
}

/** @description 시험 모드 공개 자료 소스 선택 */
async function _resolveModeSources(manifest, mode, roots) {
  const candidates = _getModeSourceCandidates(manifest, mode, roots)
  const hasLegacyHints = Boolean(candidates.legacy.results || candidates.legacy.tokenUsage)
  const modernPresence = await Promise.all(
    Object.values(candidates.modern).map(filePath => _fileExists(filePath))
  )
  const modernCount = modernPresence.filter(Boolean).length

  if (modernCount > 0) {
    if (modernCount !== 3) {
      throw new Error(`공개 모드 자료가 불완전합니다: ${manifest.id}/${mode.id}`)
    }
    return {
      results: candidates.modern.results,
      tokenUsage: candidates.modern.tokenUsage,
      questionsMetadata: candidates.modern.questionsMetadata,
      sourceKind: 'published'
    }
  }

  const legacyResults = candidates.legacy.results && await _fileExists(candidates.legacy.results)
  const legacyTokenUsage = candidates.legacy.tokenUsage && await _fileExists(candidates.legacy.tokenUsage)
  if (hasLegacyHints && legacyResults && legacyTokenUsage) {
    const metadataPath = await _firstExisting(candidates.metadataCandidates)
    return {
      results: candidates.legacy.results,
      tokenUsage: candidates.legacy.tokenUsage,
      questionsMetadata: metadataPath,
      sourceKind: 'legacy'
    }
  }

  if (_isPreparing(manifest) && !hasLegacyHints && modernCount === 0) {
    return { sourceKind: 'empty' }
  }

  throw new Error(`준비 완료 시험의 공개 자료가 없습니다: ${manifest.id}/${mode.id}`)
}

/** @description 공개 시험 결과에서 실제 모델명 수집 */
export async function discoverPublishedModelNames(options = {}) {
  const configuredRepoRoot = path.resolve(options.repoRoot || repoRoot)
  const configuredWebRoot = path.resolve(options.webRoot || path.join(configuredRepoRoot, 'web'))
  const catalogDir = _resolveConfiguredPath(
    options.catalogDir,
    path.join(configuredRepoRoot, 'benchmarks'),
    configuredRepoRoot
  )
  const publishedDir = _resolveConfiguredPath(
    options.publishedDir,
    path.join(configuredRepoRoot, 'published'),
    configuredRepoRoot
  )
  const roots = {
    repoRoot: configuredRepoRoot,
    webRoot: configuredWebRoot,
    publishedDir
  }
  const manifests = await _loadManifests(catalogDir)
  const modelNames = new Set()

  for (const { manifest } of manifests.filter(item => item.manifest.publish === true)) {
    for (const mode of manifest.modes) {
      const sources = await _resolveModeSources(manifest, mode, roots)
      if (sources.sourceKind === 'empty') continue

      const results = await _readJson(sources.results, '공개 결과')
      if (!Array.isArray(results)) {
        throw new Error(`공개 결과가 배열이 아닙니다: ${sources.results}`)
      }
      for (const record of results) {
        if (record && typeof record.model_name === 'string' && record.model_name.trim()) {
          modelNames.add(record.model_name)
        }
      }
    }
  }

  return [...modelNames].sort((left, right) => left.localeCompare(right))
}

/** @description 모드 자료를 중첩 공개 경로와 필요한 역사적 루트 경로에 기록 */
async function _publishMode(manifest, mode, roots, outputDir) {
  const sources = await _resolveModeSources(manifest, mode, roots)
  const modeOutputDir = path.join(outputDir, 'benchmarks', manifest.id, mode.id)
  const outputPaths = {
    results: path.join(modeOutputDir, 'results.json'),
    tokenUsage: path.join(modeOutputDir, 'token_usage.json'),
    questionsMetadata: path.join(modeOutputDir, 'questions_metadata.json')
  }

  if (sources.sourceKind === 'empty') {
    await _writeJson(outputPaths.results, [])
    await _writeJson(outputPaths.tokenUsage, {})
    await _writeJson(outputPaths.questionsMetadata, {})
    return { sources, outputPaths, results: [] }
  }

  await _copyExact(sources.results, outputPaths.results)
  await _copyExact(sources.tokenUsage, outputPaths.tokenUsage)
  const results = await _readJson(sources.results, '공개 결과')
  if (!Array.isArray(results)) {
    throw new Error(`공개 결과가 배열이 아닙니다: ${sources.results}`)
  }

  const tokenUsage = await _readJson(sources.tokenUsage, '토큰 사용량')
  if (!tokenUsage || typeof tokenUsage !== 'object' || Array.isArray(tokenUsage)) {
    throw new Error(`토큰 사용량이 객체가 아닙니다: ${sources.tokenUsage}`)
  }

  if (sources.questionsMetadata) {
    await _copyExact(sources.questionsMetadata, outputPaths.questionsMetadata)
    const questionsMetadata = await _readJson(sources.questionsMetadata, '문항 메타데이터')
    if (!questionsMetadata || typeof questionsMetadata !== 'object' || Array.isArray(questionsMetadata)) {
      throw new Error(`문항 메타데이터가 객체가 아닙니다: ${sources.questionsMetadata}`)
    }
  } else {
    await _writeJson(outputPaths.questionsMetadata, _deriveQuestionsMetadata(results))
  }

  if (manifest.id === DEFAULT_EXAM_ID && HISTORICAL_MIRRORS[mode.id]) {
    const mirrors = HISTORICAL_MIRRORS[mode.id]
    await _copyExact(sources.results, path.join(outputDir, mirrors.results))
    await _copyExact(sources.tokenUsage, path.join(outputDir, mirrors.tokenUsage))
    if (mode.id === 'default') {
      await _copyExact(
        sources.questionsMetadata || outputPaths.questionsMetadata,
        path.join(outputDir, 'questions_metadata.json')
      )
    }
  }

  return { sources, outputPaths, results }
}

/**
 * @description 카탈로그 기준 공개 데이터 복사
 * @param {object} options 복사 옵션
 * @returns {Promise<object>} 생성 카탈로그와 출력 경로
 */
export async function copyDataFiles(options = {}) {
  const configuredRepoRoot = path.resolve(options.repoRoot || repoRoot)
  const configuredWebRoot = path.resolve(options.webRoot || path.join(configuredRepoRoot, 'web'))
  const catalogDir = _resolveConfiguredPath(
    options.catalogDir,
    path.join(configuredRepoRoot, 'benchmarks'),
    configuredRepoRoot
  )
  const outputDir = _resolveConfiguredPath(
    options.outputDir || process.env.CSAT_PUBLIC_DIR,
    path.join(configuredWebRoot, 'public'),
    configuredRepoRoot
  )
  const publishedDir = _resolveConfiguredPath(
    options.publishedDir,
    path.join(configuredRepoRoot, 'published'),
    configuredRepoRoot
  )
  const modelMetadataPath = _resolveConfiguredPath(
    options.modelMetadataPath,
    path.join(configuredWebRoot, 'model_metadata.json'),
    configuredRepoRoot
  )
  const modelPerformancePath = _resolveConfiguredPath(
    options.modelPerformancePath,
    path.join(configuredWebRoot, 'model_performance.json'),
    configuredRepoRoot
  )
  const roots = {
    repoRoot: configuredRepoRoot,
    webRoot: configuredWebRoot,
    publishedDir
  }
  const manifests = await _loadManifests(catalogDir)
  const catalog = createPublicCatalog(manifests)

  await mkdir(outputDir, { recursive: true })
  const generatedBenchmarksDir = path.join(outputDir, 'benchmarks')
  if (
    outputDir === path.parse(outputDir).root ||
    !generatedBenchmarksDir.startsWith(`${outputDir}${path.sep}`)
  ) {
    throw new Error(`공개 출력 경로가 삭제 허용 경로가 아닙니다: ${outputDir}`)
  }
  await rm(generatedBenchmarksDir, { recursive: true, force: true })
  for (const { manifest } of manifests.filter(item => item.manifest.publish === true)) {
    for (const mode of manifest.modes) {
      await _publishMode(manifest, mode, roots, outputDir)
    }
  }

  await _copyExact(modelMetadataPath, path.join(outputDir, 'model_metadata.json'))
  if (await _fileExists(modelPerformancePath)) {
    await _copyExact(modelPerformancePath, path.join(outputDir, 'model_performance.json'))
  }
  await _writeJson(path.join(outputDir, 'benchmarks.json'), catalog)
  console.log(`Generated ${path.relative(configuredRepoRoot, path.join(outputDir, 'benchmarks.json'))}`)
  return { catalog, outputDir }
}

/** @description CLI 옵션 파싱 */
function _parseArgs(argv) {
  const options = {}
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--output-dir') {
      options.outputDir = argv[++index]
    } else if (argument === '--catalog-dir') {
      options.catalogDir = argv[++index]
    } else if (argument === '--published-dir') {
      options.publishedDir = argv[++index]
    } else if (argument === '--model-metadata') {
      options.modelMetadataPath = argv[++index]
    } else if (argument === '--model-performance') {
      options.modelPerformancePath = argv[++index]
    } else {
      throw new Error(`알 수 없는 옵션입니다: ${argument}`)
    }
  }
  return options
}

if (process.argv[1] === __filename) {
  copyDataFiles(_parseArgs(process.argv.slice(2))).catch(error => {
    console.error(error)
    process.exit(1)
  })
}
