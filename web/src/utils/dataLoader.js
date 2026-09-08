/**
 * @file dataLoader.js
 * @brief 공개 시험 카탈로그와 시험별 결과 데이터를 로드하는 유틸리티
 */

/** @brief 카탈로그 스키마 버전 */
const CATALOG_SCHEMA_VERSION = 1

/**
 * @brief 배포 기준 경로에 상대적인 공개 파일 URL 생성
 * @param {string} path - 공개 파일의 상대 경로
 * @return {string} fetch에 사용할 URL
 */
function _getAssetUrl(path) {
  const basePath = import.meta.env?.BASE_URL || '/'
  return `${basePath.replace(/\/?$/, '/')}${path.replace(/^\/+/, '')}`
}

/**
 * @brief JSON 파일 로드
 * @param {string} path - 공개 파일 경로
 * @param {string} label - 오류 메시지에 사용할 자료 이름
 * @return {Promise<unknown>} 파싱된 JSON
 * @throws {Error} 파일을 읽거나 파싱할 수 없을 때
 */
async function _loadJson(path, label) {
  const response = await fetch(_getAssetUrl(path))
  if (!response.ok) {
    throw new Error(`${label} 로드 실패: ${response.status}`)
  }

  try {
    return await response.json()
  } catch (error) {
    throw new Error(`${label} 파싱 실패: ${error.message}`)
  }
}

/**
 * @brief 공개 시험 카탈로그 로드
 * @return {Promise<Object>} 카탈로그 객체
 * @throws {Error} 카탈로그 계약이 잘못되었을 때
 */
export async function loadBenchmarkCatalog() {
  const catalog = await _loadJson('benchmarks.json', '시험 카탈로그')
  if (catalog?.schema_version !== CATALOG_SCHEMA_VERSION) {
    throw new Error(`지원하지 않는 시험 카탈로그 버전입니다: ${catalog?.schema_version}`)
  }
  if (!Array.isArray(catalog.exams) || !catalog.default_exam) {
    throw new Error('시험 카탈로그의 exams와 default_exam이 필요합니다')
  }

  const exams = catalog.exams.filter(exam => exam.publish !== false)
  if (!exams.some(exam => exam.id === catalog.default_exam)) {
    throw new Error(`기본 시험이 카탈로그에 없습니다: ${catalog.default_exam}`)
  }

  return { ...catalog, exams }
}

/**
 * @brief 시험 카탈로그의 모드 찾기
 * @param {Object} exam - 시험 정의
 * @param {string} modeId - 모드 식별자
 * @return {Object} 모드 정의
 * @throws {Error} 시험 또는 모드가 없을 때
 */
function _getMode(exam, modeId) {
  const mode = exam?.modes?.find(item => item.id === modeId)
  if (!mode) {
    throw new Error(`시험 ${exam?.id}에 모드가 없습니다: ${modeId}`)
  }
  return mode
}

/**
 * @brief 시험·모드에 연결된 공개 데이터 로드
 * @param {Object} exam - 시험 정의
 * @param {string} modeId - 모드 식별자
 * @return {Promise<Object>} 결과·토큰·문항 메타데이터
 * @throws {Error} 모드 데이터 계약이 없거나 로드에 실패할 때
 */
export async function loadExamData(exam, modeId = 'default') {
  const mode = _getMode(exam, modeId)
  const resultsPath = mode.results
  const tokenUsagePath = mode.token_usage
  const questionsMetadataPath = mode.questions_metadata
  if (!resultsPath || !tokenUsagePath || !questionsMetadataPath) {
    throw new Error(`시험 ${exam.id}/${modeId}의 공개 데이터 경로가 완전하지 않습니다`)
  }

  const [results, tokenPayload, questionsMetadata] = await Promise.all([
    _loadJson(resultsPath, '결과 데이터'),
    _loadJson(tokenUsagePath, '토큰 사용량 데이터'),
    _loadJson(questionsMetadataPath, '문항 메타데이터')
  ])

  if (!Array.isArray(results)) {
    throw new Error('결과 데이터는 배열이어야 합니다')
  }
  if (!tokenPayload || typeof tokenPayload !== 'object' || Array.isArray(tokenPayload)) {
    throw new Error('토큰 사용량 데이터는 객체여야 합니다')
  }
  if (!questionsMetadata || typeof questionsMetadata !== 'object' || Array.isArray(questionsMetadata)) {
    throw new Error('문항 메타데이터는 객체여야 합니다')
  }

  return {
    exam,
    mode,
    results,
    tokenUsage: tokenPayload.models || {},
    questionsMetadata
  }
}

/**
 * @brief 기존 호출자를 위한 결과 데이터 로드
 * @param {'default' | 'easy'} mode - 2026 호환 모드
 * @return {Promise<Array>} 결과 배열
 * @throws {Error} 결과 파일을 읽을 수 없을 때
 */
export async function loadAllResults(mode = 'default') {
  const fileNames = {
    default: 'all_results.json',
    easy: 'easy_all_results.json'
  }
  const fileName = fileNames[mode]
  if (!fileName) throw new Error(`지원하지 않는 결과 데이터 모드입니다: ${mode}`)
  const results = await _loadJson(fileName, '결과 데이터')
  if (!Array.isArray(results)) {
    throw new Error('결과 데이터는 배열이어야 합니다')
  }
  return results
}

/**
 * @brief 데이터에서 고유 과목·섹션·모델 추출
 * @param {Array} data - 결과 배열
 * @param {Object|null} exam - 시험 정의(준비 중 시험의 빈 결과 지원)
 * @return {Object} { subjects, sections, models }
 */
export function extractUniqueValues(data, exam = null) {
  const entries = Array.isArray(data) ? data : []
  const subjects = []
  const sections = {}
  const addSection = (subject, section) => {
    if (!subjects.includes(subject)) subjects.push(subject)
    if (!sections[subject]) sections[subject] = []
    if (!sections[subject].includes(section)) sections[subject].push(section)
  }

  exam?.sections?.forEach(section => addSection(section.subject, section.section))
  entries.forEach(entry => {
    if (entry.subject != null && entry.section != null) addSection(entry.subject, entry.section)
  })

  return {
    subjects,
    sections,
    models: [...new Set(entries.map(entry => entry.model_name).filter(Boolean))]
  }
}

/**
 * @brief 특정 모델의 특정 과목·섹션 데이터 조회
 * @param {Array} data - 결과 배열
 * @param {string} modelName - 모델명
 * @param {string} subject - 과목명
 * @param {string|null} section - 섹션명
 * @return {Object|null} 결과 또는 null
 */
export function getModelSubjectData(data, modelName, subject, section = null) {
  return data.find(entry =>
    entry.model_name === modelName &&
    entry.subject === subject &&
    (section === null || entry.section === section)
  ) || null
}

/**
 * @brief 특정 모델의 모든 결과 조회
 * @param {Array} data - 결과 배열
 * @param {string} modelName - 모델명
 * @return {Array} 모델 결과 배열
 */
export function getModelData(data, modelName) {
  return data.filter(entry => entry.model_name === modelName)
}

/**
 * @brief 기존 토큰 사용량 파일 로드
 * @param {'default' | 'easy'} mode - 2026 호환 모드
 * @return {Promise<Object>} 모델별 토큰 사용량
 */
export async function loadTokenUsage(mode = 'default') {
  const fileNames = {
    default: 'token_usage.json',
    easy: 'easy_token_usage.json'
  }
  const fileName = fileNames[mode]
  if (!fileName) throw new Error(`지원하지 않는 토큰 사용량 모드입니다: ${mode}`)
  try {
    const data = await _loadJson(fileName, '토큰 사용량 데이터')
    return data.models || {}
  } catch {
    return {}
  }
}

/**
 * @brief 모델 메타데이터 로드
 * @return {Promise<Object>} 모델별 메타데이터
 */
export async function loadModelMetadata() {
  try {
    return await _loadJson('model_metadata.json', '모델 메타데이터')
  } catch {
    return {}
  }
}

/**
 * @brief 모델 처리량 스냅샷 로드
 * @return {Promise<Object>} 모델별 처리량 스냅샷 또는 빈 스냅샷
 */
export async function loadModelPerformance() {
  try {
    const data = await _loadJson('model_performance.json', '모델 처리량 데이터')
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      return { updatedAt: null, models: {} }
    }
    const models = data.models && typeof data.models === 'object' && !Array.isArray(data.models)
      ? data.models
      : {}
    return {
      updatedAt: typeof data.updatedAt === 'string' ? data.updatedAt : null,
      models
    }
  } catch {
    return { updatedAt: null, models: {} }
  }
}

/**
 * @brief 기존 문항 메타데이터 파일 로드
 * @return {Promise<Object>} 문항 메타데이터
 */
export async function loadQuestionsMetadata() {
  try {
    return await _loadJson('questions_metadata.json', '문항 메타데이터')
  } catch {
    return {}
  }
}
