/**
 * @file SearchExplanation.jsx
 * @brief "검색 없이 실행" 설명 내용과 아이콘
 */

import { Trans, useTranslation } from 'react-i18next'

/**
 * @brief 돋보기에 사선을 그은 아이콘
 * @param {{ className: string }} props
 */
export function NoSearchIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className={className} aria-hidden="true">
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.2 10.2 13.5 13.5" />
      <path d="M2.5 13.5 13.5 2.5" />
    </svg>
  )
}

/**
 * @brief 검색 없이 실행한 결과의 의미 설명
 */
export default function SearchExplanation() {
  const { t } = useTranslation()

  return (
    <div>
      <p className="flex items-center gap-1.5 font-semibold text-gray-900 dark:text-gray-100">
        <NoSearchIcon className="h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400" />
        {t('searchNote.badge')}
      </p>
      <p className="mt-2 whitespace-pre-line break-keep leading-relaxed text-gray-600 dark:text-gray-300">
        <Trans i18nKey="searchNote.body" components={{ b: <strong className="font-semibold text-gray-900 dark:text-gray-100" /> }} />
      </p>
    </div>
  )
}
