/**
 * @file Sidebar.jsx
 * @brief 대시보드 사이드바 레이아웃 컴포넌트 (모바일 드로어 지원)
 */

import { useTranslation } from 'react-i18next'
import { SubjectFilter, ModelFilter, SortOptions } from '@/components/filters'
import { ThemeToggle, LanguageSwitcher } from '@/components/common'

/**
 * @brief 사이드바 컴포넌트
 * @param {Object} props - { filters, onFilterChange, hoveredModel, onModelHover, isOpen, onClose }
 */
export default function Sidebar({
  filters,
  onFilterChange,
  subjectFilterGroups = [],
  hoveredModel,
  onModelHover,
  isOpen = false,
  onClose
}) {
  const { t } = useTranslation()

  return (
    <>
      {/* 모바일 백드롭 오버레이 */}
      <div
        className={`
          fixed inset-0 bg-black/50 z-40 md:hidden
          transition-opacity duration-300
          ${isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'}
        `}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* 사이드바 */}
      <aside
        className={`
          fixed md:relative z-50 md:z-auto
          w-64 bg-gray-50 dark:bg-gray-800 p-4
          h-full md:h-auto md:min-h-screen
          border-r border-gray-200 dark:border-gray-700 shrink-0
          transform transition-transform duration-300 ease-in-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 md:transition-none
          overflow-y-auto
          top-0 left-0
        `}
      >
        {/* 모바일 헤더: 닫기 버튼 + 설정 */}
        <div className="md:hidden flex items-center justify-between mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="font-semibold text-gray-700 dark:text-gray-300">
            {t('sidebar.settings')}
          </h2>
          <div className="flex items-center gap-1">
            <LanguageSwitcher />
            <ThemeToggle />
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 min-w-[44px] min-h-[44px] flex items-center justify-center"
              aria-label="Close menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 표시 옵션 */}
        <div className="mb-6">
          <h3 className="font-semibold mb-2 text-gray-700 dark:text-gray-300">{t('sidebar.displayOptions')}</h3>
          <button
            className={`w-full px-3 py-2 text-sm rounded-lg transition-colors min-h-[44px] md:min-h-0 ${
              filters.showDetail
                ? 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                : 'bg-blue-500 text-white hover:bg-blue-600'
            }`}
            onClick={() => onFilterChange({ ...filters, showDetail: !filters.showDetail })}
          >
            {filters.showDetail ? t('sidebar.hideDetail') : t('sidebar.showDetail')}
          </button>
        </div>

        <SubjectFilter
          selected={filters.subjects}
          onChange={(subjects) => onFilterChange({ ...filters, subjects })}
          showDetail={filters.showDetail}
          groups={subjectFilterGroups}
        />
        <ModelFilter
          selected={filters.models}
          onChange={(models) => onFilterChange({ ...filters, models })}
          hoveredModel={hoveredModel}
          onModelHover={onModelHover}
        />
        <SortOptions
          sortBy={filters.sortBy}
          onChange={(sortBy) => onFilterChange({ ...filters, sortBy })}
        />
      </aside>
    </>
  )
}
