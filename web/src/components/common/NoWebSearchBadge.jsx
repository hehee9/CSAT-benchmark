/**
 * @file NoWebSearchBadge.jsx
 * @brief 차트·표 제목 줄의 "검색 없이 실행" 배지와 설명 팝오버
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import Popover from './Popover'
import SearchExplanation, { NoSearchIcon } from './SearchExplanation'

/**
 * @brief 검색 없이 실행 배지
 * @param {{ className: string }} props
 *
 * 이미지 내보내기에 포함되도록 data-export-hide를 쓰지 않고 export-role-badge 글꼴 규칙을 따른다.
 */
export default function NoWebSearchBadge({ className = '' }) {
  const { t } = useTranslation()
  const [anchorEl, setAnchorEl] = useState(null)
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <button
        ref={setAnchorEl}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(open => !open)}
        className={`export-role-badge inline-flex shrink-0 items-center gap-[0.35em] whitespace-nowrap rounded-full border border-gray-300 bg-gray-50 px-[0.75em] py-[0.25em] text-xs font-medium leading-tight text-gray-600 transition-colors hover:border-gray-400 hover:bg-gray-100 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 dark:border-gray-600 dark:bg-gray-700/60 dark:text-gray-300 dark:hover:border-gray-500 dark:hover:bg-gray-700 dark:hover:text-gray-100 ${className}`}
      >
        <NoSearchIcon className="h-[1.1em] w-[1.1em] shrink-0" />
        {t('searchNote.badge')}
      </button>
      {isOpen && (
        <Popover anchorEl={anchorEl} onClose={() => setIsOpen(false)} ariaLabel={t('searchNote.badge')}>
          <SearchExplanation />
        </Popover>
      )}
    </>
  )
}
