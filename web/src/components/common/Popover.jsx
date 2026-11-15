/**
 * @file Popover.jsx
 * @brief 기준 요소 옆에 띄우는 공용 팝오버 (바깥 클릭·Escape 닫기, 키보드 포커스 지원)
 */

import { useEffect, useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

const VIEWPORT_MARGIN = 8
const ANCHOR_GAP = 6

/**
 * @brief 기준 요소와 팝오버 크기로 화면 안 고정 위치 계산
 * @param {DOMRect} anchorRect - 기준 요소 영역
 * @param {HTMLElement} panel - 팝오버 요소
 * @return {{left: number, top: number}} 고정 위치 좌표
 */
function _computePosition(anchorRect, panel) {
  const { offsetWidth: width, offsetHeight: height } = panel
  const viewportWidth = document.documentElement.clientWidth
  const viewportHeight = window.innerHeight
  const spaceBelow = viewportHeight - anchorRect.bottom - ANCHOR_GAP - VIEWPORT_MARGIN
  const spaceAbove = anchorRect.top - ANCHOR_GAP - VIEWPORT_MARGIN
  const top = spaceBelow >= height || spaceBelow >= spaceAbove
    ? anchorRect.bottom + ANCHOR_GAP
    : anchorRect.top - ANCHOR_GAP - height
  const left = Math.min(
    Math.max(anchorRect.left, VIEWPORT_MARGIN),
    Math.max(viewportWidth - width - VIEWPORT_MARGIN, VIEWPORT_MARGIN)
  )
  return {
    left,
    top: Math.min(Math.max(top, VIEWPORT_MARGIN), Math.max(viewportHeight - height - VIEWPORT_MARGIN, VIEWPORT_MARGIN))
  }
}

/**
 * @brief 공용 팝오버
 * @param {Object} props - 팝오버 속성
 * @param {HTMLElement|null} props.anchorEl - 위치 기준이자 바깥 클릭 판정에서 제외할 요소
 * @param {function} props.onClose - 닫기 요청 콜백
 * @param {string} props.ariaLabel - 팝오버 접근성 이름
 * @param {boolean} props.autoFocus - 열릴 때 팝오버로 포커스 이동 여부
 * @param {string} props.className - 패널 추가 클래스
 * @param {function} props.onPointerEnter - 패널 포인터 진입 콜백
 * @param {function} props.onPointerLeave - 패널 포인터 이탈 콜백
 * @param {React.ReactNode} props.children - 팝오버 내용
 *
 * 열림 상태는 호출자가 렌더링 여부로 관리한다. 닫힐 때 포커스가 팝오버 안에 있었으면 기준 요소로 되돌린다.
 */
export default function Popover({
  anchorEl,
  onClose,
  ariaLabel,
  autoFocus = true,
  className = '',
  onPointerEnter,
  onPointerLeave,
  children
}) {
  const panelRef = useRef(null)
  const onCloseRef = useRef(onClose)

  useLayoutEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  /** @brief 스크롤·크기 변경 시 기준 요소 위치에 맞춰 재배치 */
  useLayoutEffect(() => {
    const panel = panelRef.current
    const update = () => {
      const { left, top } = _computePosition(anchorEl.getBoundingClientRect(), panel)
      panel.style.left = `${left}px`
      panel.style.top = `${top}px`
      panel.style.visibility = 'visible'
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(panel)
    window.addEventListener('scroll', update, true)
    window.addEventListener('resize', update)
    return () => {
      observer.disconnect()
      window.removeEventListener('scroll', update, true)
      window.removeEventListener('resize', update)
    }
  }, [anchorEl])

  useEffect(() => {
    const panel = panelRef.current
    if (autoFocus) panel.focus({ preventScroll: true })

    const handlePointerDown = (event) => {
      const path = event.composedPath()
      if (!path.includes(panel) && !path.includes(anchorEl)) onCloseRef.current()
    }
    const handleKeyDown = (event) => {
      if (event.key !== 'Escape') return
      if (panel.contains(document.activeElement)) anchorEl.focus({ preventScroll: true })
      onCloseRef.current()
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
      if (panel.contains(document.activeElement)) anchorEl.focus({ preventScroll: true })
    }
  }, [anchorEl, autoFocus])

  /**
   * @brief Tab으로 팝오버와 기준 요소 밖으로 포커스가 나가면 닫기
   * @param {FocusEvent} event - 포커스 이탈 이벤트
   *
   * 닫히며 DOM에서 빠질 때도 blur가 오고 그때는 ref가 이미 비어 있으므로 currentTarget으로 판정한다.
   */
  const handleBlur = (event) => {
    const next = event.relatedTarget
    if (next && !event.currentTarget.contains(next) && next !== anchorEl) onCloseRef.current()
  }

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label={ariaLabel}
      tabIndex={-1}
      style={{ position: 'fixed', left: 0, top: 0, visibility: 'hidden' }}
      className={`z-[70] w-[min(22rem,calc(100vw-16px))] rounded-xl border border-gray-200 bg-white p-4 text-left text-sm font-normal text-gray-700 shadow-[0_8px_24px_rgba(15,23,42,0.14)] outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:shadow-[0_8px_24px_rgba(0,0,0,0.45)] ${className}`}
      onBlur={handleBlur}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      {children}
    </div>,
    document.body
  )
}
