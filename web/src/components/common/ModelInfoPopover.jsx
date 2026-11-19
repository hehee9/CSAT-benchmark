/**
 * @file ModelInfoPopover.jsx
 * @brief 모델 정보 카드 팝오버 (개발사, 출시일, 지식 컷오프, 요금제, 양자화 수준)
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useData } from '@/hooks/useData'
import { getModelColor, getVendor } from '@/utils/colorUtils'
import { formatModelDisplayName, formatPublishedDate, getModelDescription } from '@/utils/modelMeta'
import Popover from './Popover'
import PlanTierIcon from './PlanTierIcon'
import SearchExplanation, { NoSearchIcon } from './SearchExplanation'

/**
 * @brief 정보 카드의 항목 한 줄
 * @param {{ label: string, value: string|null, emptyLabel: string, children: React.ReactNode }} props
 */
function _InfoRow({ label, value, emptyLabel, children }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt className="shrink-0 text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className={`text-right ${value === null && !children ? 'text-gray-400 dark:text-gray-500' : 'font-medium text-gray-800 dark:text-gray-100'}`}>
        {children ?? value ?? emptyLabel}
      </dd>
    </div>
  )
}

/**
 * @brief 모델 정보 카드 내용
 * @param {{ model: string, t: function, language: string, modelMetadata: Object, onShowSearchExplanation?: function, autoFocusNote?: boolean, children?: React.ReactNode }} props
 *
 * onShowSearchExplanation이 없으면 하단 "검색 없이 실행" 안내 버튼을 그리지 않는다.
 * autoFocusNote는 설명에서 돌아와 카드가 다시 그려질 때 하단 안내 버튼으로 포커스를 되돌리는 데 쓴다.
 * children은 모델 이름과 항목 목록 사이에 끼워 넣는다 (차트 툴팁의 점수 영역).
 */
function _ModelInfoCard({ model, t, language, modelMetadata, onShowSearchExplanation, autoFocusNote, children }) {
  const locale = language === 'en' ? 'en-US' : 'ko-KR'
  const metadata = modelMetadata[model] ?? {}
  const vendor = getVendor(model)
  const tier = metadata.accessTier === 'free' || metadata.accessTier === 'paid' ? metadata.accessTier : null
  const description = getModelDescription(model, language, modelMetadata)
  const emptyLabel = t('modelInfo.notDisclosed')

  return (
    <div>
      <div className="flex items-start gap-2">
        <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: getModelColor(model) }} aria-hidden="true" />
        <div className="min-w-0">
          <p className="break-words font-semibold leading-snug text-gray-900 dark:text-gray-100">{formatModelDisplayName(model)}</p>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{vendor.id === 'other' ? t('trend.otherVendor') : vendor.name}</p>
        </div>
      </div>

      {children}

      <dl className="mt-3 divide-y divide-gray-100 border-y border-gray-100 dark:divide-gray-700 dark:border-gray-700">
        <_InfoRow label={t('modelInfo.releaseDate')} value={formatPublishedDate(metadata.releaseDate, locale)} emptyLabel={emptyLabel} />
        <_InfoRow label={t('modelInfo.knowledgeCutoff')} value={formatPublishedDate(metadata.knowledgeCutoff, locale)} emptyLabel={emptyLabel} />
        <_InfoRow label={t('modelInfo.plan')} value={null} emptyLabel={emptyLabel}>
          {tier ? (
            <span className="inline-flex items-center gap-1.5">
              <PlanTierIcon tier={tier} className="h-3.5 w-3.5" decorative />
              {t(tier === 'free' ? 'modelInfo.free' : 'modelInfo.paid')}
            </span>
          ) : metadata.accessTier === 'not_applicable' ? t('modelInfo.notApplicable') : null}
        </_InfoRow>
        {Object.hasOwn(metadata, 'quantization') && (
          <_InfoRow label={t('modelInfo.quantization')} value={metadata.quantization ?? null} emptyLabel={emptyLabel} />
        )}
      </dl>
      {description && <p className="mt-2 text-xs leading-relaxed text-gray-600 dark:text-gray-300">{description}</p>}

      {onShowSearchExplanation && (
        <button
          type="button"
          autoFocus={autoFocusNote}
          onClick={onShowSearchExplanation}
          className="mt-3 flex w-full items-start gap-1.5 rounded-md text-left text-xs leading-relaxed text-blue-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 dark:text-blue-300"
        >
          <NoSearchIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {t('modelInfo.cutoffNote')}
        </button>
      )}
    </div>
  )
}

/**
 * @brief 팝오버 밖에서 재사용하는 모델 정보 카드 내용 (검색 설명 버튼 제외)
 * @param {{ model: string, children?: React.ReactNode }} props - children은 모델 이름 바로 아래에 표시
 */
export function ModelInfoContent({ model, children }) {
  const { t, i18n } = useTranslation()
  const { modelMetadata } = useData()

  return (
    <_ModelInfoCard model={model} t={t} language={i18n.language} modelMetadata={modelMetadata}>
      {children}
    </_ModelInfoCard>
  )
}

/**
 * @brief 모델 정보 카드 팝오버
 * @param {Object} props - 팝오버 속성
 * @param {string} props.model - 모델명
 * @param {HTMLElement} props.anchorEl - 위치 기준 요소
 * @param {function} props.onClose - 닫기 콜백
 * @param {boolean} props.autoFocus - 열릴 때 카드로 포커스 이동 여부
 * @param {function} props.onPointerEnter - 카드 포인터 진입 콜백
 * @param {function} props.onPointerLeave - 카드 포인터 이탈 콜백
 *
 * 하단 안내를 누르면 같은 자리에 "검색 없이 실행" 설명 팝오버를 연다.
 */
export default function ModelInfoPopover({ model, anchorEl, onClose, autoFocus = true, onPointerEnter, onPointerLeave }) {
  const { t, i18n } = useTranslation()
  const { modelMetadata } = useData()
  const [showExplanation, setShowExplanation] = useState(false)
  const [hasVisitedExplanation, setHasVisitedExplanation] = useState(false)

  return (
    <Popover
      anchorEl={anchorEl}
      onClose={onClose}
      autoFocus={autoFocus}
      ariaLabel={showExplanation ? t('searchNote.badge') : t('modelInfo.label', { model: formatModelDisplayName(model) })}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      {showExplanation ? (
        <div>
          <SearchExplanation />
          <button
            type="button"
            autoFocus
            onClick={() => setShowExplanation(false)}
            className="mt-3 rounded-md text-xs text-blue-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 dark:text-blue-300"
          >
            {t('modelInfo.back')}
          </button>
        </div>
      ) : (
        <_ModelInfoCard
          model={model}
          t={t}
          language={i18n.language}
          modelMetadata={modelMetadata}
          onShowSearchExplanation={() => {
            setShowExplanation(true)
            setHasVisitedExplanation(true)
          }}
          autoFocusNote={hasVisitedExplanation}
        />
      )}
    </Popover>
  )
}
