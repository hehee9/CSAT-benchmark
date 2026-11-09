/**
 * @file useBarChartExportLayout.js
 * @brief 막대 차트 이미지 내보내기용 높이 조정 훅
 */

import { useCallback, useState } from 'react'

/**
 * @brief SVG 높이와 모델명 레이블이 지정한 내보내기 레이아웃에 반영될 때까지 대기
 * @param {HTMLElement} element - 내보내기 대상 요소
 * @param {number} expectedHeight - SVG에 반영할 기대 높이
 * @param {boolean} requireModelLabels - 모델명 레이블 존재 여부 확인
 * @return {Promise<void>} 레이아웃 반영 완료 약속
 */
function _waitForSvgHeight(element, expectedHeight, requireModelLabels = false) {
  return new Promise(resolve => {
    const checkLayout = () => {
      const svg = element.querySelector('svg.recharts-surface')
      const hasModelLabels = !requireModelLabels || svg?.querySelector('.export-role-model-label')
      const heightMatches = svg && Math.abs(svg.getBoundingClientRect().height - expectedHeight) <= 0.5

      if (heightMatches && hasModelLabels) {
        resolve()
        return
      }

      requestAnimationFrame(checkLayout)
    }

    requestAnimationFrame(checkLayout)
  })
}

/**
 * @brief 내보내기 SVG에서 회전된 모델명 아래의 미사용 높이 측정
 * @param {HTMLElement} element - 내보내기 대상 요소
 * @return {number} SVG 아래쪽의 미사용 높이
 */
function _measureUnusedBottom(element) {
  const svg = element.querySelector('svg.recharts-surface')
  const labels = [...svg.querySelectorAll('.export-role-model-label')]
  const svgRect = svg.getBoundingClientRect()
  const lowestLabelBottom = Math.max(...labels.map(label => label.getBoundingClientRect().bottom))

  return Math.max(0, svgRect.bottom - lowestLabelBottom)
}

/**
 * @brief 막대 차트 내보내기용 X축·전체 높이 임시 조정
 * @param {Object} options - 내보내기 레이아웃 옵션
 * @param {boolean} options.enabled - 회전된 X축 레이블 측정 여부
 * @param {number} options.baseXAxisHeight - 측정 전 X축 예약 높이
 * @param {number} options.baseChartHeight - 측정 전 전체 차트 높이
 * @return {Object} 조정된 높이와 prepareExport 콜백
 */
export function useBarChartExportLayout({ enabled, baseXAxisHeight, baseChartHeight }) {
  const [reduction, setReduction] = useState(0)

  const prepareExport = useCallback(async (element) => {
    if (!enabled) return undefined

    await _waitForSvgHeight(element, baseChartHeight, true)

    const nextReduction = Math.min(_measureUnusedBottom(element), baseXAxisHeight - 1)
    setReduction(nextReduction)

    if (nextReduction > 0.5) {
      await _waitForSvgHeight(element, baseChartHeight - nextReduction)
    }

    return () => setReduction(0)
  }, [baseChartHeight, baseXAxisHeight, enabled])

  return {
    prepareExport,
    xAxisHeight: baseXAxisHeight - reduction,
    chartHeight: baseChartHeight - reduction
  }
}
