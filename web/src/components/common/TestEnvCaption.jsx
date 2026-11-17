/**
 * @file TestEnvCaption.jsx
 * @brief 차트·표 제목 아래의 시험 환경 요약 캡션
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import TestEnvModal from './TestEnvModal'

/**
 * @brief 원 안에 i를 그린 정보 아이콘
 * @param {{ className: string }} props
 */
function InfoIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" className={className} aria-hidden="true">
      <circle cx="8" cy="8" r="6.25" />
      <path d="M8 7.25v3.75" />
      <circle cx="8" cy="5" r="0.4" fill="currentColor" />
    </svg>
  )
}

/**
 * @brief 시험 환경 요약 캡션
 * @param {Object} props - 캡션 속성
 * @param {boolean} props.asText - 버튼 없이 문구만 렌더링할지 여부
 * @param {string} props.className - 추가 클래스
 *
 * 화면에서는 설명 모달을 여는 버튼이고, 이미지 내보내기에서는 아이콘이 빠져 일반 문구로 남는다.
 * asText는 개별 카드 캡처처럼 버튼이 필요 없는 곳에 쓰며, 나머지 속성은 문구 요소에 그대로 전달한다.
 */
export default function TestEnvCaption({ asText = false, className = '', ...rest }) {
  const { t } = useTranslation()
  const [anchorEl, setAnchorEl] = useState(null)
  const [isOpen, setIsOpen] = useState(false)
  const caption = t('testEnv.caption')

  if (asText) {
    return <p className={`export-role-note text-xs leading-snug break-keep text-gray-500 dark:text-gray-400 ${className}`} {...rest}>{caption}</p>
  }

  return (
    <>
      {/* 고유 폭을 0으로 두어 제목 줄의 폭을 늘리지 않고, 부모 폭에 맞춰 줄바꿈한다 */}
      <div className={`contain-inline-size ${className}`}>
        <button
          ref={setAnchorEl}
          type="button"
          aria-haspopup="dialog"
          aria-expanded={isOpen}
          onClick={() => setIsOpen(true)}
          className="export-role-note group inline-flex max-w-full items-start gap-1 rounded text-left text-xs leading-snug break-keep text-gray-500 transition-colors hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 dark:text-gray-400 dark:hover:text-gray-100"
        >
          <span data-export-hide="true" className="flex h-[1.375em] shrink-0 items-center">
            <InfoIcon className="h-[1.1em] w-[1.1em]" />
          </span>
          <span className="underline decoration-transparent decoration-dotted underline-offset-[3px] transition-colors group-hover:decoration-current">{caption}</span>
        </button>
      </div>
      {isOpen && <TestEnvModal anchorEl={anchorEl} onClose={() => setIsOpen(false)} />}
    </>
  )
}
