/**
 * @file TestEnvModal.jsx
 * @brief 시험 환경 설명 모달 (실행 방식, 문제 입력, 450점 환산, 자주 받는 오해, 한계)
 */

import { useEffect, useId, useRef } from 'react'
import { Trans, useTranslation } from 'react-i18next'

const RICH_TEXT_COMPONENTS = { b: <strong className="font-semibold text-gray-900 dark:text-gray-100" /> }
const FAQ_KEYS = ['prompt', 'harness', 'training', 'search', 'timeLimit']

/**
 * @brief <b> 표시를 굵게 렌더링하는 번역 문자열
 * @param {{ i18nKey: string }} props
 */
function RichText({ i18nKey }) {
  return <Trans i18nKey={i18nKey} components={RICH_TEXT_COMPONENTS} />
}

/**
 * @brief 제목이 있는 모달 본문 구역
 * @param {{ title: string, children: React.ReactNode }} props
 */
function Section({ title, children }) {
  return (
    <section>
      <h3 className="mb-2 text-[0.8125rem] font-semibold text-gray-900 dark:text-gray-100">{title}</h3>
      {children}
    </section>
  )
}

/**
 * @brief 시험 환경 설명 모달
 * @param {Object} props - 모달 속성
 * @param {HTMLElement} props.anchorEl - 모달을 연 요소이자 닫힐 때 포커스를 돌려줄 요소
 * @param {function} props.onClose - 닫기 요청 콜백
 *
 * 열림 상태는 호출자가 렌더링 여부로 관리한다. 네이티브 모달 dialog로 배경 조작과 Tab 이탈을 막고,
 * Escape(cancel 이벤트)와 배경 클릭은 onClose로 넘긴다.
 */
export default function TestEnvModal({ anchorEl, onClose }) {
  const { t } = useTranslation()
  const dialogRef = useRef(null)
  const isBackdropPressRef = useRef(false)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    dialog.showModal()
    return () => {
      dialog.close()
      anchorEl.focus({ preventScroll: true })
    }
  }, [anchorEl])

  /**
   * @brief Escape 기본 닫기 대신 호출자 상태로 닫기
   * @param {Event} event - dialog cancel 이벤트
   */
  const handleCancel = (event) => {
    event.preventDefault()
    onClose()
  }

  /**
   * @brief 누름과 뗌이 모두 배경(dialog 자신)일 때만 닫기
   * @param {MouseEvent} event - 클릭 이벤트
   *
   * 본문에서 드래그를 시작해 배경에서 놓은 경우는 닫지 않는다.
   */
  const handleClick = (event) => {
    if (isBackdropPressRef.current && event.target === event.currentTarget) onClose()
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onCancel={handleCancel}
      onPointerDown={event => { isBackdropPressRef.current = event.target === event.currentTarget }}
      onClick={handleClick}
      className="mx-auto mb-0 mt-auto max-h-[85dvh] w-full max-w-none overflow-hidden rounded-t-2xl border border-gray-200 bg-white p-0 text-left text-sm font-normal text-gray-700 shadow-[0_-8px_32px_rgba(15,23,42,0.18)] backdrop:bg-gray-900/40 open:flex open:flex-col md:my-auto md:max-h-[min(82vh,48rem)] md:w-[min(36rem,calc(100vw-32px))] md:rounded-2xl md:shadow-[0_12px_40px_rgba(15,23,42,0.22)] dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:shadow-[0_12px_40px_rgba(0,0,0,0.55)] dark:backdrop:bg-black/60"
    >
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-gray-200 py-3 pl-5 pr-3 dark:border-gray-700">
        <h2 id={titleId} className="text-base font-semibold text-gray-900 dark:text-gray-100">{t('testEnv.title')}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('testEnv.close')}
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-100"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="h-4 w-4" aria-hidden="true">
            <path d="M4 4 12 12M12 4 4 12" />
          </svg>
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain px-5 pb-6 pt-4 break-keep leading-relaxed text-gray-600 dark:text-gray-300">
        <Section title={t('testEnv.execution.title')}>
          <ul className="list-disc space-y-1 pl-4 marker:text-gray-400 dark:marker:text-gray-500">
            <li><RichText i18nKey="testEnv.execution.api" /></li>
            <li><RichText i18nKey="testEnv.execution.noSystemPrompt" /></li>
            <li><RichText i18nKey="testEnv.execution.input" /></li>
          </ul>
          <p className="mt-2 text-[0.8125rem] text-gray-500 dark:text-gray-400"><RichText i18nKey="testEnv.execution.easyNote" /></p>
        </Section>

        <Section title={t('testEnv.problemInput.title')}>
          <p><RichText i18nKey="testEnv.problemInput.body" /></p>
        </Section>

        <Section title={t('testEnv.scoring.title')}>
          <p><RichText i18nKey="testEnv.scoring.body" /></p>
        </Section>

        <Section title={t('testEnv.faq.title')}>
          <div className="divide-y divide-gray-200 overflow-hidden rounded-xl border border-gray-200 dark:divide-gray-700 dark:border-gray-700">
            {FAQ_KEYS.map(key => (
              <details key={key} className="group">
                <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-3.5 py-2.5 font-medium text-gray-800 transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-400 dark:text-gray-100 dark:hover:bg-gray-700/50 [&::-webkit-details-marker]:hidden">
                  <span>{t(`testEnv.faq.${key}.q`)}</span>
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="mt-[0.2em] h-4 w-4 shrink-0 text-gray-400 transition-transform group-open:rotate-180" aria-hidden="true">
                    <path d="M4 6 8 10 12 6" />
                  </svg>
                </summary>
                <p className="whitespace-pre-line px-3.5 pb-3 pt-0.5"><RichText i18nKey={`testEnv.faq.${key}.a`} /></p>
              </details>
            ))}
          </div>
        </Section>

        <Section title={t('testEnv.limits.title')}>
          <ul className="list-disc space-y-1 pl-4 marker:text-gray-400 dark:marker:text-gray-500">
            <li><RichText i18nKey="testEnv.limits.cutoff" /></li>
          </ul>
        </Section>
      </div>
    </dialog>
  )
}
