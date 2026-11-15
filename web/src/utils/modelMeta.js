/**
 * @file modelMeta.js
 * @brief 모델 메타데이터 유틸리티 (설명, 부분 벤치마크, 이미지 미지원, 비표준 설정, 지식 컷오프, 웹 서비스 환경)
 */

const PARTIAL_BENCHMARK_MODELS = {
  'GPT-5.6 Sol (max*)': {
    isPartialBenchmark: true,
    displaySuffix: '*',
    descriptionKey: 'models.partialWrongOnly'
  },
  'GPT-5.6 Terra (max*)': {
    isPartialBenchmark: true,
    displaySuffix: '*',
    descriptionKey: 'models.partialWrongOnly'
  },
  'GPT-5.6 Luna (max*)': {
    isPartialBenchmark: true,
    displaySuffix: '*',
    descriptionKey: 'models.partialWrongOnly'
  },
  'GPT-5.5 (xhigh*)': {
    isPartialBenchmark: true,
    displaySuffix: '*',
    descriptionKey: 'models.partialWrongOnly'
  },
  'GPT-5.4 (xhigh*)': {
    isPartialBenchmark: true,
    displaySuffix: '*',
    descriptionKey: 'models.partialWrongOnly'
  },
  'Claude Opus 4.7 (max*)': {
    isPartialBenchmark: true,
    displaySuffix: '*',
    descriptionKey: 'models.partialWrongOnly'
  }
}

const MODEL_DISPLAY_NAMES = {
  'GPT-5.5 Pro': 'GPT-5.5 Pro (xhigh, GPTs)',
  'DeepSeek V4.1 Flash (High)': 'DeepSeek V4.1 Flash (high)'
}

/**
 * @brief 비표준 설정 모델 (부분 벤치마크 모델과 동일)
 */
const NON_STANDARD_MODELS = new Set(Object.keys(PARTIAL_BENCHMARK_MODELS))

const DAY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const MONTH_PATTERN = /^(\d{4})-(\d{2})$/

/**
 * @brief 지원하는 언어 태그를 기본 언어 코드로 정규화
 * @param {string} language - 언어 코드 또는 지역 언어 태그
 * @return {'ko' | 'en' | null} 정규화된 언어 코드
 */
function _normalizeLanguage(language) {
  if (typeof language !== 'string') return null

  const baseLanguage = language.trim().toLowerCase().split(/[-_]/)[0]
  return baseLanguage === 'ko' || baseLanguage === 'en' ? baseLanguage : null
}

export function getModelMeta(modelName) {
  return PARTIAL_BENCHMARK_MODELS[modelName] || null
}

export function isPartialBenchmarkModel(modelName) {
  return Boolean(getModelMeta(modelName)?.isPartialBenchmark)
}

export function formatModelDisplayName(modelName) {
  const meta = getModelMeta(modelName)
  const displayName = MODEL_DISPLAY_NAMES[modelName] || modelName
  if (!meta?.displaySuffix) return displayName
  if (displayName.includes(meta.displaySuffix)) return displayName
  return `${displayName}${meta.displaySuffix}`
}

export function hasPartialBenchmark(models = []) {
  return models.some(model => isPartialBenchmarkModel(model))
}

/**
 * @brief 모델 설명을 요청한 언어로 반환
 * @param {string} modelName - 모델명
 * @param {string} language - 언어 코드 또는 지역 언어 태그
 * @param {Object} modelMetadata - 모델별 메타데이터
 * @return {string|null} 모델 설명 또는 null
 */
export function getModelDescription(modelName, language, modelMetadata = {}) {
  const normalizedLanguage = _normalizeLanguage(language)
  const description = modelMetadata?.[modelName]?.description
  const text = description?.[normalizedLanguage]

  return typeof text === 'string' && text.trim() ? text : null
}

/**
 * @brief 공개된 정밀도에 맞춰 날짜 문자열 표시 (YYYY-MM-DD는 일, YYYY-MM은 월까지)
 * @param {string|null|undefined} value - 메타데이터 날짜 문자열
 * @param {string} locale - 표시 언어
 * @return {string|null} 표시 문자열, 값이 없으면 null
 */
export function formatPublishedDate(value, locale) {
  if (typeof value !== 'string' || !value.trim()) return null
  const day = DAY_PATTERN.exec(value)
  if (day) {
    return new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC' })
      .format(Date.UTC(Number(day[1]), Number(day[2]) - 1, Number(day[3])))
  }
  const month = MONTH_PATTERN.exec(value)
  if (month) {
    return new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'long', timeZone: 'UTC' })
      .format(Date.UTC(Number(month[1]), Number(month[2]) - 1, 1))
  }
  return value
}

/**
 * @brief 이미지 미지원 모델 여부
 * @param {string} modelName - 모델명
 * @param {Object} modelMetadata - 모델별 메타데이터
 * @return {boolean}
 */
export function hasNoVision(modelName, modelMetadata = {}) {
  return modelMetadata?.[modelName]?.supportsVision === false
}

/**
 * @brief 비표준 설정 모델 여부
 * @param {string} modelName - 모델명
 * @return {boolean}
 */
export function isNonStandard(modelName) {
  return NON_STANDARD_MODELS.has(modelName)
}

/**
 * @brief 지식 컷오프가 수능 이후인 모델 여부
 * @param {string} modelName - 모델명
 * @param {Object} modelMetadata - 모델별 메타데이터
 * @param {string|null} examMonth - 시험 시행 월 (YYYY-MM)
 * @return {boolean}
 */
export function hasPostExamKnowledgeCutoff(modelName, modelMetadata = {}, examMonth = null) {
  const knowledgeCutoff = modelMetadata?.[modelName]?.knowledgeCutoff
  return typeof knowledgeCutoff === 'string' && typeof examMonth === 'string' && knowledgeCutoff > examMonth
}

/**
 * @brief 도구 차단 웹 서비스 환경에서 실행한 모델 여부
 * @param {string} modelName - 모델명
 * @param {Object} modelMetadata - 모델별 메타데이터
 * @return {boolean}
 */
export function hasWebServiceNoTools(modelName, modelMetadata = {}) {
  return modelMetadata?.[modelName]?.webServiceNoTools === true
}

/**
 * @brief 모델의 시각적 플래그 반환
 * @param {string} modelName - 모델명
 * @param {Object} modelMetadata - 모델별 메타데이터
 * @param {string|null} examMonth - 시험 시행 월 (YYYY-MM)
 * @return {{ noVision: boolean, nonStandard: boolean, postExamKnowledgeCutoff: boolean, webServiceNoTools: boolean }}
 */
export function getModelFlags(modelName, modelMetadata = {}, examMonth = null) {
  return {
    noVision: hasNoVision(modelName, modelMetadata),
    nonStandard: isNonStandard(modelName),
    postExamKnowledgeCutoff: hasPostExamKnowledgeCutoff(modelName, modelMetadata, examMonth),
    webServiceNoTools: hasWebServiceNoTools(modelName, modelMetadata)
  }
}

/**
 * @brief 모델 목록에 플래그가 있는 모델이 포함되어 있는지 확인
 * @param {string[]} models - 모델명 배열
 * @param {Object} modelMetadata - 모델별 메타데이터
 * @param {string|null} examMonth - 시험 시행 월 (YYYY-MM)
 * @return {{ hasNoVision: boolean, hasNonStandard: boolean, hasPostExamKnowledgeCutoff: boolean, hasWebServiceNoTools: boolean }}
 */
export function getAnyModelFlags(models = [], modelMetadata = {}, examMonth = null) {
  return {
    hasNoVision: models.some(model => hasNoVision(model, modelMetadata)),
    hasNonStandard: models.some(isNonStandard),
    hasPostExamKnowledgeCutoff: models.some(model => hasPostExamKnowledgeCutoff(model, modelMetadata, examMonth)),
    hasWebServiceNoTools: models.some(model => hasWebServiceNoTools(model, modelMetadata))
  }
}
