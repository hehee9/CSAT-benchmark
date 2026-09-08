import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { mkdir, readFile, writeFile } from 'node:fs/promises'

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
      const stats = selectThroughput(endpointsByModel.get(mapping.modelId) || [], mapping)
      return [displayName, {
        modelId: mapping.modelId,
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

/** @description OpenRouter 모델 목록에서 모델 ID 집합 추출 */
async function _fetchModelIds(fetchImpl, apiKey) {
  const payload = await _fetchJson(fetchImpl, `${OPENROUTER_API_ROOT}/models`, apiKey)
  if (!Array.isArray(payload.data)) throw new Error('OpenRouter 모델 목록이 올바르지 않습니다')
  return new Set(payload.data.map(model => model.id).filter(id => typeof id === 'string'))
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
  now = new Date()
} = {}) {
  if (!apiKey) throw new Error('OPENROUTER_API_KEY가 없습니다')

  const mapPayload = await _readJson(mapPath)
  _validateMapPayload(mapPayload)
  const previous = await _readJson(outputPath, true)
  let modelIds
  try {
    modelIds = await _fetchModelIds(fetchImpl, apiKey)
  } catch (error) {
    if (previous) return { snapshot: previous, refreshed: false, errors: [error.message] }
    throw error
  }

  const uniqueModelIds = [...new Set(Object.values(mapPayload.models).map(mapping => mapping.modelId))]
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
    return { snapshot: previous, refreshed: false, errors }
  }

  const snapshot = buildModelPerformanceSnapshot(mapPayload, endpointsByModel, now.toISOString())
  await _writeJson(outputPath, snapshot)
  return { snapshot, refreshed: true, errors }
}

/** @description CLI 인자 파싱 */
function _parseArgs(argv) {
  const options = {}
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--map') options.mapPath = path.resolve(argv[++index])
    else if (argument === '--output') options.outputPath = path.resolve(argv[++index])
    else throw new Error(`알 수 없는 옵션입니다: ${argument}`)
  }
  return options
}

if (process.argv[1] === __filename) {
  refreshModelPerformance(_parseArgs(process.argv.slice(2)))
    .then(result => {
      if (!result.refreshed) {
        console.error(`모델 처리량 갱신 실패로 이전 스냅샷을 유지했습니다: ${result.errors.join('; ')}`)
        process.exitCode = 1
        return
      }
      const failedCount = result.errors.length
      console.log(`모델 처리량 스냅샷 갱신 완료${failedCount > 0 ? `, 미상 모델 ${failedCount}개` : ''}`)
    })
    .catch(error => {
      console.error(error.message)
      process.exitCode = 1
    })
}
