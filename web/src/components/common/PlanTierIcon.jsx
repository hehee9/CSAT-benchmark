/**
 * @file PlanTierIcon.jsx
 * @brief 무료/유료 요금제 아이콘
 */

import { useTranslation } from 'react-i18next'

/**
 * @brief 무료는 빈 고리, 유료는 달러 표시가 있는 채운 동전으로 구분하는 아이콘
 * @param {{ tier: 'free' | 'paid', className: string, decorative: boolean }} props
 *
 * decorative가 true면 옆 글자가 뜻을 전하므로 접근성 이름 없이 숨긴다.
 */
export default function PlanTierIcon({ tier, className = '', decorative = false }) {
  const { t } = useTranslation()
  const label = t(tier === 'free' ? 'modelInfo.free' : 'modelInfo.paid')
  const a11yProps = decorative ? { 'aria-hidden': true } : { role: 'img', 'aria-label': label }

  if (tier === 'free') {
    return (
      <svg viewBox="0 0 16 16" {...a11yProps} className={`shrink-0 text-emerald-600 dark:text-emerald-400 ${className}`}>
        {!decorative && <title>{label}</title>}
        <circle cx="8" cy="8" r="5.6" fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 16 16" {...a11yProps} className={`shrink-0 text-amber-600 dark:text-amber-400 ${className}`}>
      {!decorative && <title>{label}</title>}
      <circle cx="8" cy="8" r="6.6" fill="currentColor" />
      <path
        d="M10.1 5.9c-.4-.6-1.1-.9-2-.9-1.1 0-1.9.6-1.9 1.4 0 1.9 3.9 1 3.9 3.1 0 .9-.9 1.5-2 1.5-1 0-1.7-.4-2.1-1M8.1 3.7v1.3M8.1 11v1.3"
        fill="none"
        stroke="white"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  )
}
