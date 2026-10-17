/**
 * @file BottomNav.jsx
 * @brief 모바일 하단 탭 네비게이션 컴포넌트
 */

import { useTranslation } from 'react-i18next'

/**
 * @brief 탭별 아이콘 컴포넌트
 */
const TAB_ICONS = {
  overview: (
    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
    </svg>
  ),
  subjects: (
    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
    </svg>
  ),
  compare: (
    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
  cost: (
    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  trend: (
    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 4v16h18M7 16h3v-4h4V9h3V6h3" />
    </svg>
  )
}

const TAB_KEYS = ['overview', 'subjects', 'compare', 'cost', 'trend']

/**
 * @brief 하단 네비게이션 컴포넌트
 * @param {Object} props - { activeTab, onTabChange }
 */
export default function BottomNav({ activeTab, onTabChange }) {
  const { t } = useTranslation()

  return (
    <nav className="mobile-bottom-nav fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 md:hidden z-40 safe-area-bottom">
      <div className="flex justify-around items-stretch h-16">
        {TAB_KEYS.map(tabKey => {
          const isActive = activeTab === tabKey

          return (
            <button
              key={tabKey}
              className={`flex flex-col items-center justify-center flex-1 min-w-0 px-1 py-2 transition-colors ${
                isActive
                  ? 'text-blue-500 dark:text-blue-400'
                  : 'text-gray-500 dark:text-gray-400 active:bg-gray-100 dark:active:bg-gray-700'
              }`}
              onClick={() => onTabChange(tabKey)}
              aria-current={isActive ? 'page' : undefined}
            >
              <div className={`${isActive ? 'scale-110' : ''} transition-transform`}>
                {TAB_ICONS[tabKey]}
              </div>
              <span className="text-xs mt-1 truncate max-w-full px-1">
                {t(`tabs.${tabKey}`)}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
