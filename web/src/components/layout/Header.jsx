/**
 * @file Header.jsx
 * @brief 대시보드 상단 헤더 컴포넌트 (모바일 반응형)
 */

import { useState, useRef, useEffect, useId } from 'react'
import { useTranslation } from 'react-i18next'
import { ThemeToggle, LanguageSwitcher } from '@/components/common'
import './Header.css'

/** @description 현재 언어에 맞춘 시험명 표시 */
function _translateExamName(name, t, language) {
  const translatedName = name
    .replace('수능', t('header.csatName'))
    .replace('모의고사', t('header.mockExamName'))
    .replace('모의평가', t('header.mockEvaluationName'))
  return language === 'en'
    ? translatedName
      .replace('모고', t('header.mockExamName'))
      .replace(/(1[0-2]|[1-9])월/g, (_, month) => new Intl.DateTimeFormat('en', { month: 'long' }).format(new Date(2000, Number(month) - 1)))
    : translatedName
}

/**
 * @brief GitHub 아이콘
 */
function GitHubIcon() {
  return (
    <svg className="w-10 h-10" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
        clipRule="evenodd"
      />
    </svg>
  )
}

/**
 * @brief 헤더 컴포넌트
 * @param {Object} props - 헤더 상태와 변경 콜백
 */
export default function Header({
  onMenuToggle,
  exam,
  exams = [],
  modes = [],
  mode = 'default',
  onModeChange,
  onExamChange
}) {
  const { t, i18n } = useTranslation()
  const is2026Exam = exam?.id === 'csat-2026'
  const isEasyMode = mode === 'easy'
  const currentModeIndex = modes.findIndex(item => item.id === mode)
  const nextMode = modes[(currentModeIndex + 1) % modes.length]
  const modeLabelKey = mode === 'default' ? 'header.modeDefault' : mode === 'easy' ? 'header.modeEasy' : null
  const modeDescriptionKey = mode === 'default' ? 'header.modeDefaultDesc' : mode === 'easy' ? 'header.modeEasyDesc' : null
  const modeLabel = modeLabelKey ? t(modeLabelKey) : modes[currentModeIndex]?.label || mode
  const modeDescription = modeDescriptionKey ? t(modeDescriptionKey) : modes[currentModeIndex]?.input_mode || ''
  const showModeToggle = modes.length > 1
  const examSelectId = `header-exam-select-${useId().replace(/:/g, '')}`
  const hasExamPicker = exams.length > 0 && exam
  const titleSuffix = t('header.titleSuffix')
  const isMockExam = /모의고사|모의평가|\bmock(?:\s+exam|\s+test)?\b/i.test(`${exam?.short_name || ''} ${exam?.title || ''}`)
  const subtitle = isMockExam
    ? t('header.mockSubtitle')
    : t('header.subtitle')
  const [showTooltip, setShowTooltip] = useState(false)
  const tooltipTimeout = useRef(null)

  /**
   * @brief 툴팁 표시 (hover/focus)
   */
  const _handleTooltipShow = () => {
    clearTimeout(tooltipTimeout.current)
    setShowTooltip(true)
  }

  /**
   * @brief 툴팁 숨기기 (약간의 딜레이로 깜빡임 방지)
   */
  const _handleTooltipHide = () => {
    tooltipTimeout.current = setTimeout(() => setShowTooltip(false), 150)
  }

  useEffect(() => {
    return () => clearTimeout(tooltipTimeout.current)
  }, [])

  /**
   * @brief 다음 실행 모드로 전환
   */
  const _handleModeToggle = () => {
    if (nextMode) onModeChange?.(nextMode.id)
  }

  return (
    <header
      className={`dashboard-header ${isEasyMode ? 'bg-emerald-950' : 'bg-gray-900'} text-white p-3 md:p-4 transition-colors duration-300`}
      data-exam-id={exam?.id}
      data-header-mode={mode}
    >
      <div className="container mx-auto flex flex-wrap items-center justify-between gap-2 md:flex-nowrap">
        {/* 햄버거 메뉴 버튼 (모바일) */}
        <button
          className="header__menu-button md:hidden p-2 -ml-2 rounded-lg hover:bg-gray-700 min-w-[44px] min-h-[44px] flex items-center justify-center shrink-0"
          onClick={onMenuToggle}
          aria-label={t('header.openMenu')}
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        {/* 제목 + 모드 토글 */}
        <div className="header__brand flex-1 min-w-0 flex items-center gap-3 md:flex-none md:gap-4">
          <a
            href="https://github.com/hehee9/CSAT-benchmark"
            target="_blank"
            rel="noopener noreferrer"
            title="GitHub"
            aria-label="GitHub"
            className="header__github-link shrink-0 text-gray-300 hover:text-white rounded-lg transition-colors"
          >
            <GitHubIcon />
          </a>

          {/* 제목 블록 */}
          <div className="header__title-block min-w-0">
            <h1 className="header__title text-lg md:text-2xl font-bold leading-tight">
              {hasExamPicker ? (
                <span className="header__title-picker">
                  <span className="header__exam-name" aria-hidden="true">{_translateExamName(exam.short_name, t, i18n.language)}</span>
                  <svg className="header__exam-chevron" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                    <path d="m5 7.5 5 5 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <label className="sr-only" htmlFor={examSelectId}>{t('header.examSelect')}</label>
                  <select
                    id={examSelectId}
                    value={exam.id}
                    onChange={event => onExamChange?.(event.target.value)}
                    className="header__exam-select"
                    aria-label={t('header.examSelect')}
                  >
                    {exams.map(item => (
                      <option key={item.id} value={item.id}>{_translateExamName(item.short_name, t, i18n.language)}</option>
                    ))}
                  </select>
                </span>
              ) : (
                <span>{is2026Exam ? t('header.title') : exam?.title?.replace(/ LLM 벤치마크$/, ' LLM 풀이 대시보드') || t('header.title')}</span>
              )}
              {hasExamPicker && <span className="header__title-suffix"> {titleSuffix}</span>}
            </h1>
            <p className="header__subtitle text-gray-400 text-xs md:text-sm hidden md:block">
              {subtitle}
            </p>
          </div>

          {/* 모드 토글 버튼 (ⓘ 포함) */}
          {showModeToggle && (
            <div
              className="header__mode relative shrink-0"
              onMouseEnter={_handleTooltipShow}
              onMouseLeave={_handleTooltipHide}
            >
              <button
                type="button"
                onClick={_handleModeToggle}
                onFocus={_handleTooltipShow}
                onBlur={_handleTooltipHide}
                aria-label={`${t('header.modeSelect')}: ${modeLabel}`}
                className={`header__mode-toggle flex items-center gap-1.5 text-base md:text-lg font-semibold px-4 py-2 rounded-lg transition-all duration-200 cursor-pointer border border-white/20 hover:border-white/40 hover:bg-white/5 ${
                  isEasyMode ? 'text-emerald-300' : 'text-sky-300'
                }`}
              >
                {modeLabel}
                <svg className="w-4 h-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4M12 8h.01" strokeLinecap="round" />
                </svg>
              </button>

              {/* 툴팁 */}
              {showTooltip && (
                <div className="header__tooltip absolute left-1/2 -translate-x-1/2 top-full mt-2 px-3 py-2 bg-gray-800 border border-gray-600 text-gray-200 text-xs rounded-lg shadow-lg whitespace-nowrap z-50 pointer-events-none">
                  {modeDescription}
                  {/* 툴팁 화살표 */}
                  <div className="header__tooltip-arrow absolute left-1/2 -translate-x-1/2 -top-1 w-2 h-2 bg-gray-800 border-l border-t border-gray-600 rotate-45" />
                </div>
              )}
            </div>
          )}
        </div>

        {/* 언어·테마 */}
        <div className="header__actions hidden md:flex shrink-0 items-center justify-end gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
