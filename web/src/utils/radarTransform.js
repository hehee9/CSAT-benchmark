/**
 * @file radarTransform.js
 * @description 레이더 차트 보조 데이터 변환
 */

/** @description 선택되지 않은 모델을 동적 레이더 데이터에 추가 */
export function addHoveredModelRadarData(sourceData, hoveredModel, selectedModels = [], allScores = [], scoreBasis = 'normalized') {
  if (!hoveredModel || selectedModels.includes(hoveredModel)) return sourceData

  const modelScore = allScores.find(score => score.model === hoveredModel)
  if (!modelScore) return sourceData

  return sourceData.map(row => {
    const detail = modelScore.groupDetails?.find(item => item.group === row.group)
    const maxScore = detail?.[scoreBasis === 'raw' ? 'rawMaxScore' : 'normalizedMaxScore'] ?? row.maxScore ?? 0
    const score = detail?.[scoreBasis === 'raw' ? 'rawTotal' : 'normalizedTotal'] ?? 0
    return {
      ...row,
      [hoveredModel]: maxScore > 0 ? (score / maxScore) * 100 : 0
    }
  })
}
