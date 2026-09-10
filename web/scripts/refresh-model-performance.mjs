import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { discoverPublishedModelNames } from './copy-data.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const DEFAULT_MAP_PATH = path.resolve(__dirname, '..', 'model_performance_map.json')
const DEFAULT_OUTPUT_PATH = path.resolve(__dirname, '..', 'model_performance.json')
const OPENROUTER_API_ROOT = 'https://openrouter.ai/api/v1'
const SNAPSHOT_SCHEMA_VERSION = 1
const PUBLISHER_TAGS = {
  Google: 'google-vertex/global',
  'Moonshot AI': 'moonshotai',
  'Z.AI': 'z-ai',
  xAI: 'xai'
}
const PUBLISHER_ALIASES = {
  anthropic: 'Anthropic',
  deepseek: 'DeepSeek',
  google: 'Google',
  openai: 'OpenAI',
  'x-ai': 'xAI',
  'z-ai': 'Z.AI',
  moonshotai: 'Moonshot AI',
  minimax: 'Minimax',
  mistralai: 'Mistral',
  meta: 'Meta',
  qwen: 'Alibaba',
  upstage: 'Upstage'
}
const REASONING_ANNOTATION = /^(?:high|low|minimal|medium|max|none|instant|thinking|non[- ]thinking|xhigh\*?|max\*?|\d+\s*k\s+(?:thinking|non[- ]thinking))$/i

/** @description 수치 목록의 중앙값 계산 */
export function median(values) {
  if (values.length === 0) return null
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle]
}

/** @description 처리량 통계가 있는 일반 공급자 엔드포인트 선택 */
function _isRegularEndpoint(endpoint) {
  const tag = typeof endpoint.tag === 'string' ? endpoint.tag : ''
  return !tag.endsWith('/fast') && !tag.endsWith('/flex')
}

/** @description 처리량 p50가 유효한지 확인 */
function _getThroughput(endpoint) {
  const value = endpoint.throughput_last_30m?.p50
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

/** @description 공급자별 일반 엔드포인트 처리량 중앙값 계산 */
function _getProviderMedians(endpoints) {
  const valuesByProvider = new Map()
  endpoints.forEach(endpoint => {
    const provider = endpoint.provider_name
    const throughput = _getThroughput(endpoint)
    if (typeof provider !== 'string' || !provider || throughput === null) return
    if (!valuesByProvider.has(provider)) valuesByProvider.set(provider, [])
    valuesByProvider.get(provider).push(throughput)
  })

  return [...valuesByProvider.entries()]
    .map(([provider, values]) => ({ provider, throughput: median(values) }))
    .sort((left, right) => left.provider.localeCompare(right.provider))
}

/** @description 공식 공급자의 일반 태그 확인 */
function _getPublisherTag(mapping) {
  return PUBLISHER_TAGS[mapping.officialProvider] || mapping.modelId.split('/')[0]
}

/** @description 모델명 끝의 벤치마크 추론 표기 제거 */
function _stripReasoningAnnotations(value) {
  let result = value.trim()
  let match = result.match(/\s*\(([^()]*)\)\s*$/)
  while (match) {
    const segments = match[1].split(',').map(segment => segment.trim())
    const retained = segments.filter(segment => !REASONING_ANNOTATION.test(segment))
    if (retained.length === segments.length) break
    result = retained.length === 0
      ? result.slice(0, match.index).trim()
      : `${result.slice(0, match.index).trim()} (${retained.join(', ')})`
    match = result.match(/\s*\(([^()]*)\)\s*$/)
  }
  return result
}

/** @description 모델명 비교용 소문자·구두점 제거 키 생성 */
function _normalizeModelName(value) {
  return _stripReasoningAnnotations(value)
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[\p{P}\p{S}\s]+/gu, '')
}

/** @description 공급자 접두어를 제외한 OpenRouter 표시명 반환 */
function _removePublisherPrefix(value) {
  const separatorIndex = value.indexOf(':')
  return separatorIndex === -1 ? value : value.slice(separatorIndex + 1).trim()
}

/** @description OpenRouter 모델의 비교 키 생성 */
function _getCatalogKeys(model) {
  return new Set([
    _normalizeModelName(model.id.slice(model.id.indexOf('/') + 1)),
    _normalizeModelName(_removePublisherPrefix(model.name))
  ].filter(Boolean))
}

/** @description 끝의 Preview 표기를 제거한 비교 키 생성 */
function _withoutTrailingPreview(key) {
  return key.endsWith('preview') ? key.slice(0, -'preview'.length) : key
}

/** @description 두 키가 Preview 별칭으로 일치하는지 확인 */
function _matchesPreviewAlias(rawKey, catalogKey) {
  return (catalogKey !== rawKey && _withoutTrailingPreview(catalogKey) === rawKey) ||
    (rawKey !== catalogKey && _withoutTrailingPreview(rawKey) === catalogKey)
}

/** @description 매칭된 모델의 공식 공급자 추론 */
function _inferOfficialProvider(model) {
  const publisherId = model.id.split('/')[0]
  if (PUBLISHER_ALIASES[publisherId]) return PUBLISHER_ALIASES[publisherId]
  const namePrefix = model.name.includes(':') ? model.name.slice(0, model.name.indexOf(':')).trim() : ''
  return namePrefix || publisherId
}

/** @description OpenRouter 후보 중 단일 모델 ID 반환 */
function _findModelMatch(rawName, modelCatalog) {
  const rawKey = _normalizeModelName(rawName)
  const candidates = modelCatalog
    .filter(model => !model.id.includes(':'))
    .map(model => ({ model, keys: _getCatalogKeys(model) }))
  const exact = candidates.filter(candidate => [...candidate.keys].includes(rawKey))
  const exactIds = [...new Set(exact.map(candidate => candidate.model.id))].sort()
  if (exactIds.length > 0) {
    const model = exactIds.length === 1
      ? exact.find(candidate => candidate.model.id === exactIds[0]).model
      : null
    return { model, candidates: exactIds }
  }

  const preview = candidates.filter(candidate => [...candidate.keys].some(catalogKey => _matchesPreviewAlias(rawKey, catalogKey)))
  const previewIds = [...new Set(preview.map(candidate => candidate.model.id))].sort()
  const model = previewIds.length === 1
    ? preview.find(candidate => candidate.model.id === previewIds[0]).model
    : null
  return { model, candidates: previewIds }
}

/** @description 공개 모델명과 OpenRouter 모델 목록의 매핑 생성 */
export function matchModelNames(modelNames, mapPayload, modelCatalog) {
  const discoveredNames = [...new Set(modelNames)]
    .filter(modelName => typeof modelName === 'string' && modelName.trim())
    .sort((left, right) => left.localeCompare(right))
  const models = {}
  const unmatched = []
  const ambiguous = []

  for (const modelName of discoveredNames) {
    const override = mapPayload.models[modelName]
    if (override) {
      models[modelName] = override
      continue
    }

    const match = _findModelMatch(modelName, modelCatalog)
    if (match.model) {
      models[modelName] = {
        modelId: match.model.id,
        officialProvider: _inferOfficialProvider(match.model)
      }
    } else {
      models[modelName] = null
      if (match.candidates.length > 1) {
        ambiguous.push({ modelName, candidates: match.candidates })
      } else {
        unmatched.push(modelName)
      }
    }
  }

  return { models, diagnostics: { unmatched, ambiguous } }
}

/**
 * @description 공식 공급자 우선 처리량 선택
 * @param {Array} endpoints - OpenRouter 엔드포인트 목록
 * @param {Object} mapping - 모델 매핑 { modelId, officialProvider }
 * @return {Object} 처리량·공급자·선택 근거
 */
export function selectThroughput(endpoints, mapping) {
  const regularEndpoints = endpoints.filter(_isRegularEndpoint)
  const providers = [...new Set(
    regularEndpoints
      .filter(endpoint => _getThroughput(endpoint) !== null)
      .map(endpoint => endpoint.provider_name)
      .filter(provider => typeof provider === 'string' && provider)
  )].sort((left, right) => left.localeCompare(right))
  const officialEndpoints = regularEndpoints.filter(endpoint =>
    endpoint.provider_name === mapping.officialProvider && _getThroughput(endpoint) !== null
  )

  if (officialEndpoints.length > 0) {
    const publisherTag = _getPublisherTag(mapping)
    const preferred = officialEndpoints.filter(endpoint => endpoint.tag === publisherTag)
    const selected = preferred.length > 0 ? preferred : officialEndpoints
    const tags = [...new Set(selected.map(endpoint => endpoint.tag).filter(Boolean))].sort()
    return {
      tokensPerSecond: median(selected.map(_getThroughput).filter(value => value !== null)),
      providers,
      selection: {
        strategy: 'official',
        provider: mapping.officialProvider,
        tag: tags.length === 1 ? tags[0] : null
      }
    }
  }

  const providerMedians = _getProviderMedians(regularEndpoints)
  if (providerMedians.length === 0) {
    return {
      tokensPerSecond: null,
      providers,
      selection: {
        strategy: 'unavailable',
        provider: null,
        tag: null
      }
    }
  }

  return {
    tokensPerSecond: median(providerMedians.map(item => item.throughput)),
    providers,
    selection: {
      strategy: 'provider-median',
      provider: null,
      tag: null
    }
  }
}

/**
 * @description 엔드포인트 응답을 공개 처리량 스냅샷으로 변환
 * @param {Object} mapPayload - 모델 표시명 매핑
 * @param {Map<string, Array>} endpointsByModel - 모델 ID별 엔드포인트
 * @param {string} updatedAt - 갱신 시각
 * @return {Object} 공개 처리량 스냅샷
 */
export function buildModelPerformanceSnapshot(mapPayload, endpointsByModel, updatedAt) {
  const models = Object.fromEntries(
    Object.entries(mapPayload.models).map(([displayName, mapping]) => {
      const stats = mapping
        ? selectThroughput(endpointsByModel.get(mapping.modelId) || [], mapping)
        : {
            tokensPerSecond: null,
            providers: [],
            selection: { strategy: 'unavailable', provider: null, tag: null }
          }
      return [displayName, {
        modelId: mapping ? mapping.modelId : null,
        tokensPerSecond: stats.tokensPerSecond,
        providers: stats.providers,
        selection: stats.selection
      }]
    })
  )

  return {
    schema_version: SNAPSHOT_SCHEMA_VERSION,
    updatedAt,
    models
  }
}

/** @description JSON 파일 로드 */
async function _readJson(filePath, optional = false) {
  let contents
  try {
    contents = await readFile(filePath, 'utf8')
  } catch (error) {
    if (optional && error.code === 'ENOENT') return null
    throw error
  }
  return JSON.parse(contents)
}

/** @description JSON 파일 저장 */
async function _writeJson(filePath, payload) {
  await mkdir(path.dirname(filePath), { recursive: true })
  await writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
}

/** @description 처리량 매핑의 필수 필드 검증 */
function _validateMapPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) || !payload.models ||
      typeof payload.models !== 'object' || Array.isArray(payload.models)) {
    throw new Error('모델 처리량 매핑의 models가 필요합니다')
  }
  Object.entries(payload.models).forEach(([displayName, mapping]) => {
    if (!displayName || !mapping || typeof mapping.modelId !== 'string' ||
        typeof mapping.officialProvider !== 'string') {
      throw new Error(`모델 처리량 매핑이 올바르지 않습니다: ${displayName}`)
    }
  })
}

/** @description OpenRouter JSON 요청 */
async function _fetchJson(fetchImpl, url, apiKey) {
  const response = await fetchImpl(url, {
    headers: { Authorization: `Bearer ${apiKey}` }
  })
  if (!response.ok) throw new Error(`OpenRouter 요청 실패: ${response.status}`)
  return response.json()
}

/** @description OpenRouter 모델 목록의 전체 모델 정보 요청 */
async function _fetchModelCatalog(fetchImpl, apiKey) {
  const payload = await _fetchJson(fetchImpl, `${OPENROUTER_API_ROOT}/models`, apiKey)
  if (!Array.isArray(payload.data)) throw new Error('OpenRouter 모델 목록이 올바르지 않습니다')
  return payload.data
    .filter(model => model && typeof model.id === 'string' && typeof model.name === 'string')
    .map(model => ({ id: model.id, name: model.name }))
}

/** @description 모델별 엔드포인트 처리량 요청 */
async function _fetchEndpoints(fetchImpl, modelId, apiKey) {
  const payload = await _fetchJson(
    fetchImpl,
    `${OPENROUTER_API_ROOT}/models/${modelId}/endpoints`,
    apiKey
  )
  if (!Array.isArray(payload.data?.endpoints)) {
    throw new Error(`엔드포인트 목록이 올바르지 않습니다: ${modelId}`)
  }
  return payload.data.endpoints
}

/**
 * @description OpenRouter 처리량 스냅샷 갱신
 * @param {Object} options - 경로·인증·시계·요청 함수 옵션
 * @return {Promise<Object>} 스냅샷과 갱신 상태
 */
export async function refreshModelPerformance({
  mapPath = DEFAULT_MAP_PATH,
  outputPath = DEFAULT_OUTPUT_PATH,
  apiKey = process.env.OPENROUTER_API_KEY,
  fetchImpl = fetch,
  now = new Date(),
  repoRoot,
  catalogDir,
  publishedDir,
  webRoot
} = {}) {
  if (!apiKey) throw new Error('OPENROUTER_API_KEY가 없습니다')

  const mapPayload = await _readJson(mapPath)
  _validateMapPayload(mapPayload)
  const previous = await _readJson(outputPath, true)
  let modelCatalog
  try {
    modelCatalog = await _fetchModelCatalog(fetchImpl, apiKey)
  } catch (error) {
    if (previous) return { snapshot: previous, refreshed: false, errors: [error.message], matching: null }
    throw error
  }

  const discoveredModelNames = await discoverPublishedModelNames({
    repoRoot,
    webRoot,
    catalogDir,
    publishedDir
  })
  const resolved = matchModelNames(discoveredModelNames, mapPayload, modelCatalog)
  const modelIds = new Set(modelCatalog.map(model => model.id))
  const uniqueModelIds = [...new Set(
    Object.values(resolved.models)
      .filter(mapping => mapping && typeof mapping.modelId === 'string')
      .map(mapping => mapping.modelId)
  )].sort()
  const endpointsByModel = new Map()
  const errors = []
  let successfulRequests = 0
  await Promise.all(uniqueModelIds.map(async modelId => {
    if (!modelIds.has(modelId)) {
      endpointsByModel.set(modelId, [])
      return
    }
    try {
      endpointsByModel.set(modelId, await _fetchEndpoints(fetchImpl, modelId, apiKey))
      successfulRequests += 1
    } catch (error) {
      endpointsByModel.set(modelId, [])
      errors.push(`${modelId}: ${error.message}`)
    }
  }))

  if (successfulRequests === 0 && uniqueModelIds.length > 0 && previous) {
    return { snapshot: previous, refreshed: false, errors, matching: resolved.diagnostics }
  }

  const snapshot = buildModelPerformanceSnapshot({ ...mapPayload, models: resolved.models }, endpointsByModel, now.toISOString())
  await _writeJson(outputPath, snapshot)
  return { snapshot, refreshed: true, errors, matching: resolved.diagnostics }
}

/** @description CLI 인자 파싱 */
function _parseArgs(argv) {
  const options = {}
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--map') options.mapPath = path.resolve(argv[++index])
    else if (argument === '--output') options.outputPath = path.resolve(argv[++index])
    else if (argument === '--repo-root') options.repoRoot = path.resolve(argv[++index])
    else if (argument === '--catalog-dir') options.catalogDir = path.resolve(argv[++index])
    else if (argument === '--published-dir') options.publishedDir = path.resolve(argv[++index])
    else if (argument === '--web-root') options.webRoot = path.resolve(argv[++index])
    else throw new Error(`알 수 없는 옵션입니다: ${argument}`)
  }
  return options
}

if (process.argv[1] === __filename) {
  refreshModelPerformance(_parseArgs(process.argv.slice(2)))
    .then(result => {
      if (!result.refreshed) {
        console.error(`모델 처리량 갱신 실패로 이전 스냅샷을 유지했습니다: ${result.errors.join('; ')}`)
        if (result.matching?.unmatched.length > 0) {
          console.error(`자동 매칭 미확인 모델: ${result.matching.unmatched.join(', ')}`)
        }
        if (result.matching?.ambiguous.length > 0) {
          console.error(`자동 매칭 후보 다중 모델: ${result.matching.ambiguous.map(item => item.modelName).join(', ')}`)
        }
        process.exitCode = 1
        return
      }
      console.log(`모델 처리량 스냅샷 갱신 완료${result.errors.length > 0 ? `, 요청 오류 ${result.errors.length}개` : ''}`)
      if (result.matching.unmatched.length > 0) {
        console.error(`자동 매칭 미확인 모델: ${result.matching.unmatched.join(', ')}`)
      }
      if (result.matching.ambiguous.length > 0) {
        console.error(`자동 매칭 후보 다중 모델: ${result.matching.ambiguous.map(item => item.modelName).join(', ')}`)
      }
    })
    .catch(error => {
      console.error(error.message)
      process.exitCode = 1
    })
}
