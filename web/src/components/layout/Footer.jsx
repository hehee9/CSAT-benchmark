/**
 * @file Footer.jsx
 * @brief 대시보드 하단 Footer 컴포넌트
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useData } from '@/hooks/useData'

/**
 * @brief "YYYY-MM-DD HH:mm:ss" 형식 문자열을 Date로 파싱
 * @param {string} value
 * @return {Date|null}
 */
function parseLastUpdated(value) {
  if (typeof value !== 'string') return null

  const match = value.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2}))?$/
  )

  if (!match) return null

  const [, year, month, day, hour = '00', minute = '00', second = '00'] = match
  const parsed = new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second)
  )

  return Number.isNaN(parsed.getTime()) ? null : parsed
}

/**
 * @brief 가장 최근 업데이트 날짜를 로케일에 맞게 포맷
 * @param {Object} tokenUsage
 * @param {string} language
 * @return {string}
 */
function formatLastUpdated(tokenUsage, language) {
  const latest = Object.values(tokenUsage || {})
    .map(model => parseLastUpdated(model?.last_updated))
    .filter(Boolean)
    .sort((a, b) => b.getTime() - a.getTime())[0]

  if (!latest) return '-'

  if (language === 'ko') {
    const year = latest.getFullYear()
    const month = String(latest.getMonth() + 1).padStart(2, '0')
    const day = String(latest.getDate()).padStart(2, '0')
    return `${year}.${month}.${day}`
  }

  return new Intl.DateTimeFormat(language || 'en', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  }).format(latest)
}

/**
 * @brief GitHub 아이콘 SVG
 */
function GitHubIcon() {
  return (
    <svg
      className="w-5 h-5"
      fill="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        fillRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
        clipRule="evenodd"
      />
    </svg>
  )
}

/**
 * @brief Footer 컴포넌트
 */
export default function Footer() {
  const { t, i18n } = useTranslation()
  const { tokenUsage } = useData()
  const lastUpdated = useMemo(
    () => formatLastUpdated(tokenUsage, i18n.language),
    [tokenUsage, i18n.language]
  )

  return (
    <footer className="bg-gray-100 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 py-4 px-6 pb-20 md:pb-4">
      <div className="container mx-auto text-center">
        {/* 링크 영역 */}
        <div className="flex justify-center items-center gap-6 mb-3">
          <a
            href="https://github.com/hehee9/CSAT-benchmark"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
          >
            <GitHubIcon />
            <span>GitHub</span>
          </a>
          <a
            href="https://ko-fi.com/hehee9"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
          >
            <span aria-hidden="true" className="text-lg leading-none">☕</span>
            <span>{t('footer.supportTests')}</span>
          </a>
        </div>

        {/* 저작권 + 라이선스 */}
        <p className="text-sm text-gray-600 dark:text-gray-400">
          © 2025 hehee9 · MIT License
        </p>

        {/* 최종 업데이트 */}
        <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
          {t('footer.lastUpdated')}: {lastUpdated}
        </p>

        {/* 면책 조항 */}
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
          {t('footer.unofficial')}
        </p>
      </div>
    </footer>
  )
}
