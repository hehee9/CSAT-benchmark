/**
 * @file useExportImage.js
 * @brief DOM 요소 이미지 내보내기 훅 및 내보내기 프로필
 */

import { useRef, useState, useCallback } from 'react'
import { getFontEmbedCSS, toPng } from 'html-to-image'
import './export-image.css'

export const README_EXPORT_WIDTH = 1680

/**
 * @brief 차트·표별 이미지 내보내기 스타일 프로필
 */
export const EXPORT_PROFILES = Object.freeze({
  default: { className: 'export-profile-default' },
  overviewScore: { className: 'export-profile-overview-score' },
  tokenUsage: { className: 'export-profile-token-usage' },
  modelCompare: { className: 'export-profile-model-compare' },
  questionHeatmap: { className: 'export-profile-question-heatmap' },
  choiceSelection: { className: 'export-profile-choice-selection' },
  scoreTable: { className: 'export-profile-score-table' },
  scoreCard: { className: 'export-profile-score-card' },
  costScatter: { className: 'export-profile-cost-scatter' },
  costTable: { className: 'export-profile-cost-table' }
})

const FONT_EMBED_OPTIONS = { preferredFontFormat: 'woff2' }
let fontReadyPromise
let fontEmbedCssPromise

function _getExportWidth(element, exportWidth) {
  if (typeof exportWidth === 'number') return exportWidth
  const attrValue = element.dataset?.exportWidth
  if (!attrValue) return undefined

  const parsed = Number(attrValue)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
}

function _nextFrame() {
  return new Promise(resolve => requestAnimationFrame(resolve))
}

async function _waitForFrames(count = 1) {
  for (let index = 0; index < count; index += 1) {
    await _nextFrame()
  }
}

/**
 * @brief 현재 문서 폰트 준비 완료 대기
 * @return {Promise<FontFaceSet>} 폰트 준비 완료 약속
 */
function _waitForFonts() {
  if (!fontReadyPromise) fontReadyPromise = document.fonts.ready
  return fontReadyPromise
}

/**
 * @brief 폰트 임베드 CSS를 최초 한 번만 생성
 * @param {HTMLElement} element - 폰트 사용 내보내기 요소
 * @return {Promise<string>} 임베드용 CSS
 */
export function getExportFontEmbedCSS(element) {
  if (!fontEmbedCssPromise) {
    fontEmbedCssPromise = getFontEmbedCSS(element, FONT_EMBED_OPTIONS)
  }
  return fontEmbedCssPromise
}

/**
 * @brief 요소에 내보내기 프로필 적용
 * @param {HTMLElement} element - 내보내기 요소
 * @param {string} profile - 프로필 이름
 * @return {function} 프로필 복원 함수
 */
export function applyExportProfile(element, profile = 'default') {
  const { className } = EXPORT_PROFILES[profile]
  const hadClass = element.classList.contains(className)
  element.classList.add(className)

  return () => {
    if (!hadClass) element.classList.remove(className)
  }
}

/**
 * @brief 다크모드 여부 확인
 * @return {boolean} 다크모드 여부
 */
function _isDarkMode() {
  return document.documentElement.classList.contains('dark')
}

/**
 * @brief 이미지 내보내기 훅
 * @param {Object} options - 내보내기 옵션
 * @param {number} options.exportWidth - 내보내기 시 임시 적용 고정 폭
 * @param {number} options.exportPadding - 캡처 이미지 여백
 * @param {number} options.pixelRatio - 캡처 화소 비율
 * @param {function} options.prepareExport - 캡처 직전 배치 조정 함수
 * @param {string} options.exportProfile - 차트·표별 내보내기 프로필
 * @return {Object} { ref, exportImage, isExporting }
 */
export function useExportImage({
  exportWidth,
  exportPadding = 16,
  pixelRatio = 2,
  prepareExport,
  exportProfile = 'default'
} = {}) {
  const ref = useRef(null)
  const [isExporting, setIsExporting] = useState(false)

  /**
   * @brief 현재 ref 요소를 PNG 이미지로 내보내기
   * @param {string} filename - 저장할 파일명
   */
  const exportImage = useCallback(async (filename = 'export.png') => {
    if (!ref.current) return

    setIsExporting(true)
    await _nextFrame()

    const element = ref.current
    if (!element) {
      setIsExporting(false)
      return
    }

    const resolvedExportWidth = _getExportWidth(element, exportWidth)
    const originalWidth = element.style.width
    const originalMaxWidth = element.style.maxWidth
    const originalMinWidth = element.style.minWidth
    const profileCleanup = applyExportProfile(element, exportProfile)
    const overflowElements = element.querySelectorAll('[class*="overflow"]')
    const originalOverflows = Array.from(overflowElements).map(el => el.style.overflow)
    const exportHideElements = Array.from(element.querySelectorAll('[data-export-hide="true"]')).map(el => ({
      element: el,
      display: el.style.display
    }))
    const exportShowElements = new Map()
    const registerExportShowElements = () => {
      element.querySelectorAll('[data-export-show="true"]').forEach(showElement => {
        if (!exportShowElements.has(showElement)) {
          exportShowElements.set(showElement, showElement.classList.contains('hidden'))
        }
        showElement.classList.remove('hidden')
      })
    }
    let exportCleanup = null

    try {
      const isDark = _isDarkMode()
      overflowElements.forEach(el => {
        el.style.overflow = 'visible'
      })
      exportHideElements.forEach(({ element: hideElement }) => {
        hideElement.style.display = 'none'
      })

      if (resolvedExportWidth) {
        element.style.width = `${resolvedExportWidth}px`
        element.style.maxWidth = 'none'
        element.style.minWidth = `${resolvedExportWidth}px`
        window.dispatchEvent(new Event('resize'))
        await _waitForFrames(2)
      }

      registerExportShowElements()

      await _waitForFonts()
      const fontEmbedCSS = await getExportFontEmbedCSS(element)

      if (prepareExport) {
        const cleanup = await prepareExport(element)
        exportCleanup = typeof cleanup === 'function' ? cleanup : null
        await _nextFrame()
        registerExportShowElements()
      }

      const width = element.scrollWidth + exportPadding * 2
      const height = element.scrollHeight + exportPadding * 2
      const backgroundColor = isDark ? '#111827' : '#ffffff'

      const dataUrl = await toPng(element, {
        backgroundColor,
        pixelRatio,
        width,
        height,
        fontEmbedCSS,
        preferredFontFormat: FONT_EMBED_OPTIONS.preferredFontFormat,
        filter: node => node.dataset?.exportHide !== 'true',
        style: {
          padding: `${exportPadding}px`
        }
      })

      const link = document.createElement('a')
      link.download = filename
      link.href = dataUrl
      link.click()
    } catch (err) {
      console.error('이미지 내보내기 실패:', err)
    } finally {
      if (exportCleanup) {
        try {
          await exportCleanup()
        } catch (cleanupError) {
          console.error('이미지 내보내기 배치 복원 실패:', cleanupError)
        }
      }

      profileCleanup()
      overflowElements.forEach((el, index) => {
        el.style.overflow = originalOverflows[index]
      })
      exportHideElements.forEach(({ element: hideElement, display }) => {
        hideElement.style.display = display
      })
      element.querySelectorAll('[data-export-show="true"]').forEach(showElement => {
        if (exportShowElements.has(showElement)) {
          showElement.classList.toggle('hidden', exportShowElements.get(showElement))
        }
      })

      element.style.width = originalWidth
      element.style.maxWidth = originalMaxWidth
      element.style.minWidth = originalMinWidth

      setIsExporting(false)
      if (resolvedExportWidth) {
        window.dispatchEvent(new Event('resize'))
      }
      await _nextFrame()
    }
  }, [exportPadding, exportProfile, exportWidth, pixelRatio, prepareExport])

  return { ref, exportImage, isExporting }
}
