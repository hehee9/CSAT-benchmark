/**
 * @file modelFilters.js
 * @brief 무료 모델과 제품군 최신 모델을 판별하고 목록 필터링
 */

/**
 * @brief 모든 등록 모델을 기준으로 제품군별 최신 모델명을 반환
 * @param {Object} modelMetadata - 모델명별 메타데이터
 * @returns {Set<string>} 제품군별 최신 모델명 집합
 */
export function getLatestVersionModelNames(modelMetadata) {
  const groups = new Map()

  for (const [modelName, metadata] of Object.entries(modelMetadata)) {
    const lineKey = metadata.productLine ? metadata.productLine : Symbol(modelName)
    if (!groups.has(lineKey)) {
      groups.set(lineKey, { models: [], latestReleaseDate: undefined })
    }

    const group = groups.get(lineKey)
    const releaseDate = metadata.releaseDate
    group.models.push({ modelName, releaseDate })

    if (releaseDate !== undefined &&
      (group.latestReleaseDate === undefined || releaseDate > group.latestReleaseDate)) {
      group.latestReleaseDate = releaseDate
    }
  }

  const latestModelNames = new Set()
  for (const group of groups.values()) {
    for (const model of group.models) {
      if (model.releaseDate === undefined || model.releaseDate === group.latestReleaseDate) {
        latestModelNames.add(model.modelName)
      }
    }
  }

  return latestModelNames
}

/**
 * @brief 모델이 최신 버전인지 확인
 * @param {string} modelName - 모델명
 * @param {Set<string>} latestVersionModelNames - 제품군별 최신 모델명 집합
 * @param {Object} modelMetadata - 모델명별 메타데이터
 * @returns {boolean} 최신 모델이거나 메타데이터에 없는 모델이면 true
 */
export function isLatestVersionModel(modelName, latestVersionModelNames, modelMetadata) {
  return latestVersionModelNames.has(modelName) || !Object.hasOwn(modelMetadata, modelName)
}

/**
 * @brief 모델이 제품군의 구버전인지 확인
 * @param {string} modelName - 모델명
 * @param {Set<string>} latestVersionModelNames - 제품군별 최신 모델명 집합
 * @param {Object} modelMetadata - 모델명별 메타데이터
 * @returns {boolean} 최신 모델이 아니면 true
 */
export function isLegacyModel(modelName, latestVersionModelNames, modelMetadata) {
  return !isLatestVersionModel(modelName, latestVersionModelNames, modelMetadata)
}

/**
 * @brief 모델이 무료 등급인지 확인
 * @param {string} modelName - 모델명
 * @param {Object} modelMetadata - 모델명별 메타데이터
 * @returns {boolean} 접근 등급이 free이면 true
 */
export function isFreeModel(modelName, modelMetadata) {
  return modelMetadata[modelName]?.accessTier === 'free'
}

/**
 * @brief 이미 선택된 모델 목록에 무료/최신 조건을 적용
 * @param {string[]} modelNames - 화면에 표시할 모델명 목록으로, 빈 선택의 전체 표시 규칙은 호출자가 처리
 * @param {{ freeOnly: boolean, latestOnly: boolean }} options - 적용할 빠른 필터
 * @param {Object} modelMetadata - 모델명별 메타데이터
 * @returns {string[]} 조건을 만족하는 모델명 목록
 */
export function applyQuickFilters(modelNames, { freeOnly, latestOnly }, modelMetadata) {
  const latestVersionModelNames = latestOnly ? getLatestVersionModelNames(modelMetadata) : null

  return modelNames.filter(modelName => {
    if (freeOnly && !isFreeModel(modelName, modelMetadata)) return false
    return !latestOnly || isLatestVersionModel(modelName, latestVersionModelNames, modelMetadata)
  })
}
