/**
 * @file ModelFilter.jsx
 * @brief 모델 필터 체크박스 컴포넌트 (개발사별 그룹화, Tri-State Checkbox, 빠른 필터, 모델 정보 카드)
 */

import { useRef, useEffect, useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useData } from '@/hooks/useData'
import { ModelInfoPopover, PlanTierIcon } from '@/components/common'
import { groupModelsByVendor, getSortedVendors } from '@/utils/colorUtils'
import { formatModelDisplayName, getModelDescription } from '@/utils/modelMeta'
import { getLatestVersionModelNames, isLegacyModel } from '@/utils/modelFilters'

const HOVER_OPEN_DELAY = 450
const HOVER_CLOSE_DELAY = 180
const LONG_PRESS_DELAY = 500
const LONG_PRESS_MOVE_TOLERANCE = 10

/**
 * @brief 사이드바 아이콘으로 표시할 요금제 반환
 * @param {string} modelName - 모델명
 * @param {Object} modelMetadata - 모델별 메타데이터
 * @param {string} language - 언어 코드
 * @return {'free' | 'paid' | null} 요금제 설명이 있는 모델의 요금제, 없으면 null
 *
 * 기존 요금제 설명(?) 버튼이 있던 모델에만 아이콘을 둔다.
 */
function _getIconTier(modelName, modelMetadata, language) {
  if (!getModelDescription(modelName, language, modelMetadata)) return null
  const tier = modelMetadata[modelName]?.accessTier
  return tier === 'free' || tier === 'paid' ? tier : null
}

/**
 * @brief 빠른 필터 토글 버튼
 * @param {{ pressed: boolean, onToggle: function, children: React.ReactNode }} props
 */
function _QuickFilterToggle({ pressed, onToggle, children }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onToggle}
      className={`inline-flex min-h-[36px] items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 md:min-h-0 ${
        pressed
          ? 'border-blue-500 bg-blue-500 text-white hover:bg-blue-600'
          : 'border-gray-300 bg-white text-gray-600 hover:border-gray-400 hover:text-gray-800 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:border-gray-500 dark:hover:text-gray-100'
      }`}
    >
      {pressed && (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3" aria-hidden="true">
          <path d="M3.5 8.5 6.5 11.5 12.5 4.5" />
        </svg>
      )}
      {children}
    </button>
  )
}

/**
 * @brief 모델 필터 컴포넌트
 * @param {Object} props - { selected, onChange, hoveredModel, onModelHover, quickFilters, onQuickFiltersChange }
 * @param {{ freeOnly: boolean, latestOnly: boolean }} props.quickFilters - 선택 결과 위에 적용할 빠른 필터
 * @param {function} props.onQuickFiltersChange - 빠른 필터 변경 콜백
 */
export default function ModelFilter({ selected, onChange, hoveredModel, onModelHover, quickFilters, onQuickFiltersChange }) {
  const { t, i18n } = useTranslation()
  const { models, modelMetadata } = useData()
  const checkboxRefs = useRef({})
  const [collapsed, setCollapsed] = useState({})
  const [infoCard, setInfoCard] = useState(null)
  const openTimerRef = useRef(null)
  const closeTimerRef = useRef(null)
  const pressTimerRef = useRef(null)
  const pressOriginRef = useRef(null)
  const longPressFiredRef = useRef(false)

  /** @brief 개발사별 그룹화 (이름 내림차순 정렬) */
  const groupedModels = useMemo(() => groupModelsByVendor(models), [models])

  /** @brief 개발사 목록 (모델 수 내림차순 정렬) */
  const sortedVendors = useMemo(() => getSortedVendors(groupedModels), [groupedModels])

  /** @brief 등록 모델 전체 기준 제품군별 최신 모델 */
  const latestVersionModelNames = useMemo(() => getLatestVersionModelNames(modelMetadata), [modelMetadata])

  /** @brief 모델별 요금제 아이콘과 후속 버전 여부 (구형 모델은 아이콘 없음) */
  const modelMarks = useMemo(() => new Map(models.map(model => {
    const isLegacy = isLegacyModel(model, latestVersionModelNames, modelMetadata)
    const iconTier = isLegacy ? null : _getIconTier(model, modelMetadata, i18n.language)
    return [model, { iconTier, isLegacy }]
  })), [models, modelMetadata, i18n.language, latestVersionModelNames])

  const legend = useMemo(() => {
    const marks = Array.from(modelMarks.values())
    return {
      hasFree: marks.some(mark => mark.iconTier === 'free'),
      hasPaid: marks.some(mark => mark.iconTier === 'paid'),
      hasLegacy: marks.some(mark => mark.isLegacy)
    }
  }, [modelMarks])

  /**
   * @brief 개발사의 체크박스 상태 계산
   * @param {string} vendorId - 개발사 ID
   * @return {'checked' | 'unchecked' | 'indeterminate'} 체크 상태
   */
  function getVendorState(vendorId) {
    const vendorModels = groupedModels[vendorId]
    if (!vendorModels?.length) return 'unchecked'
    const count = vendorModels.filter(m => selected.includes(m)).length
    if (count === 0) return 'unchecked'
    if (count === vendorModels.length) return 'checked'
    return 'indeterminate'
  }

  /**
   * @brief 개발사 토글 (전체 선택/해제)
   * @param {string} vendorId - 개발사 ID
   */
  function handleVendorToggle(vendorId) {
    const vendorModels = groupedModels[vendorId]
    const allSelected = vendorModels.every(m => selected.includes(m))
    const filtered = selected.filter(m => !vendorModels.includes(m))
    onChange(allSelected ? filtered : [...filtered, ...vendorModels])
  }

  /**
   * @brief 개별 모델 토글
   * @param {string} model - 모델명
   */
  function handleModelToggle(model) {
    onChange(selected.includes(model)
      ? selected.filter(m => m !== model)
      : [...selected, model])
  }

  /**
   * @brief 접기/펼치기 토글
   * @param {string} vendorId - 개발사 ID
   */
  function toggleCollapse(vendorId) {
    setCollapsed(prev => ({ ...prev, [vendorId]: !prev[vendorId] }))
  }

  /** @brief 전체 선택/해제 */
  function handleSelectAll() {
    onChange(selected.length === models.length ? [] : [...models])
  }

  /** @brief indeterminate 상태 동기화 */
  useEffect(() => {
    sortedVendors.forEach(vendor => {
      const ref = checkboxRefs.current[vendor.id]
      if (ref) {
        const vendorModels = groupedModels[vendor.id]
        const count = vendorModels.filter(m => selected.includes(m)).length
        ref.indeterminate = count > 0 && count < vendorModels.length
      }
    })
  }, [selected, groupedModels, sortedVendors])

  /** @brief 언마운트 시 대기 중인 정보 카드 타이머 정리 */
  useEffect(() => () => {
    clearTimeout(openTimerRef.current)
    clearTimeout(closeTimerRef.current)
    clearTimeout(pressTimerRef.current)
  }, [])

  /** @brief 마우스가 이름과 카드를 모두 벗어나면 잠시 뒤 카드 닫기 */
  function _scheduleCardClose() {
    clearTimeout(closeTimerRef.current)
    closeTimerRef.current = setTimeout(() => setInfoCard(null), HOVER_CLOSE_DELAY)
  }

  /**
   * @brief 데스크톱에서 이름에 마우스를 올리면 지연 후 정보 카드 열기
   * @param {PointerEvent} event - 포인터 진입 이벤트
   * @param {string} model - 모델명
   */
  function handleNamePointerEnter(event, model) {
    if (event.pointerType !== 'mouse') return
    const anchorEl = event.currentTarget
    clearTimeout(closeTimerRef.current)
    clearTimeout(openTimerRef.current)
    openTimerRef.current = setTimeout(() => setInfoCard({ model, anchorEl }), HOVER_OPEN_DELAY)
  }

  /**
   * @brief 이름에서 마우스가 벗어나면 열기 대기 취소 후 닫기 예약
   * @param {PointerEvent} event - 포인터 이탈 이벤트
   */
  function handleNamePointerLeave(event) {
    if (event.pointerType !== 'mouse') return
    clearTimeout(openTimerRef.current)
    _scheduleCardClose()
  }

  /**
   * @brief 터치로 이름을 길게 누르면 정보 카드 열기
   * @param {PointerEvent} event - 포인터 누름 이벤트
   * @param {string} model - 모델명
   */
  function handleNamePointerDown(event, model) {
    longPressFiredRef.current = false
    if (event.pointerType === 'mouse') return
    const anchorEl = event.currentTarget
    pressOriginRef.current = { x: event.clientX, y: event.clientY }
    clearTimeout(pressTimerRef.current)
    pressTimerRef.current = setTimeout(() => {
      longPressFiredRef.current = true
      pressOriginRef.current = null
      setInfoCard({ model, anchorEl })
    }, LONG_PRESS_DELAY)
  }

  /**
   * @brief 길게 누르는 중 손가락이 움직이면 스크롤로 보고 취소
   * @param {PointerEvent} event - 포인터 이동 이벤트
   */
  function handleNamePointerMove(event) {
    const origin = pressOriginRef.current
    if (origin && Math.hypot(event.clientX - origin.x, event.clientY - origin.y) > LONG_PRESS_MOVE_TOLERANCE) {
      _cancelLongPress()
    }
  }

  /** @brief 길게 누르기 대기 취소 */
  function _cancelLongPress() {
    clearTimeout(pressTimerRef.current)
    pressOriginRef.current = null
  }

  /**
   * @brief 길게 눌러 카드를 연 직후의 클릭이 체크박스를 바꾸지 않게 막기
   * @param {MouseEvent} event - 라벨 클릭 이벤트
   */
  function handleLabelClick(event) {
    if (!longPressFiredRef.current) return
    event.preventDefault()
    longPressFiredRef.current = false
  }

  /**
   * @brief 길게 누르는 동안 브라우저 기본 메뉴 차단
   * @param {MouseEvent} event - 컨텍스트 메뉴 이벤트
   */
  function handleNameContextMenu(event) {
    if (pressOriginRef.current || longPressFiredRef.current) event.preventDefault()
  }

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-gray-700 dark:text-gray-300">{t('sidebar.modelFilter')}</h3>
        <button
          onClick={handleSelectAll}
          className="text-xs text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
        >
          {selected.length === models.length ? t('sidebar.deselectAll') : t('sidebar.selectAll')}
        </button>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label={t('sidebar.quickFilters')}>
        <_QuickFilterToggle
          pressed={quickFilters.freeOnly}
          onToggle={() => onQuickFiltersChange({ ...quickFilters, freeOnly: !quickFilters.freeOnly })}
        >
          {t('sidebar.freeOnly')}
        </_QuickFilterToggle>
        <_QuickFilterToggle
          pressed={quickFilters.latestOnly}
          onToggle={() => onQuickFiltersChange({ ...quickFilters, latestOnly: !quickFilters.latestOnly })}
        >
          {t('sidebar.latestOnly')}
        </_QuickFilterToggle>
      </div>

      <div className="space-y-2">
        {sortedVendors.map(vendor => {
          const vendorModels = groupedModels[vendor.id]
          const isCollapsed = collapsed[vendor.id]

          return (
            <div key={vendor.id}>
              {/* 개발사 헤더 */}
              <div className="flex items-center p-1 hover:bg-gray-50 dark:hover:bg-gray-700 rounded text-gray-800 dark:text-gray-200">
                <button
                  onClick={() => toggleCollapse(vendor.id)}
                  className="w-5 h-5 flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 shrink-0"
                >
                  {isCollapsed ? '▶' : '▼'}
                </button>
                <input
                  ref={el => checkboxRefs.current[vendor.id] = el}
                  type="checkbox"
                  checked={getVendorState(vendor.id) === 'checked'}
                  onChange={() => handleVendorToggle(vendor.id)}
                  className="mr-2 rounded"
                />
                <span
                  className="w-3 h-3 rounded-full mr-2 shrink-0"
                  style={{ backgroundColor: vendor.color }}
                />
                <span className="text-sm font-medium">{vendor.name}</span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">({vendorModels.length})</span>
              </div>

              {/* 모델 목록 (접기 가능) */}
              {!isCollapsed && (
                <div className="ml-6 space-y-0.5">
                  {vendorModels.map(model => {
                    const isHovered = hoveredModel === model
                    const { iconTier, isLegacy } = modelMarks.get(model)
                    return (
                      <div
                        key={model}
                        className={`relative flex min-w-0 items-center rounded p-1 transition-colors ${
                          isHovered
                            ? 'bg-blue-50 dark:bg-blue-900/30 ring-1 ring-blue-300 dark:ring-blue-700'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-700'
                        }`}
                        onMouseEnter={() => onModelHover?.(model)}
                        onMouseLeave={() => onModelHover?.(null)}
                      >
                        <label className="flex min-w-0 flex-1 items-center cursor-pointer" onClick={handleLabelClick}>
                          <input
                            type="checkbox"
                            checked={selected.includes(model)}
                            onChange={() => handleModelToggle(model)}
                            className="mr-2 rounded"
                          />
                          <span
                            className={`flex-1 truncate select-none text-xs [-webkit-touch-callout:none] ${isLegacy ? 'text-gray-400 dark:text-gray-500' : 'text-gray-800 dark:text-gray-200'}`}
                            onPointerEnter={event => handleNamePointerEnter(event, model)}
                            onPointerLeave={handleNamePointerLeave}
                            onPointerDown={event => handleNamePointerDown(event, model)}
                            onPointerMove={handleNamePointerMove}
                            onPointerUp={_cancelLongPress}
                            onPointerCancel={_cancelLongPress}
                            onContextMenu={handleNameContextMenu}
                          >
                            {formatModelDisplayName(model)}
                          </span>
                        </label>
                        {iconTier && <PlanTierIcon tier={iconTier} className="ml-1 h-3.5 w-3.5" />}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {(legend.hasFree || legend.hasPaid || legend.hasLegacy) && (
        <div
          role="note"
          aria-label={t('sidebar.modelListLegend')}
          className="mt-3 space-y-1.5 border-t border-gray-200 pt-3 text-xs leading-snug text-gray-500 dark:border-gray-700 dark:text-gray-400"
        >
          {(legend.hasFree || legend.hasPaid) && (
            <div>
              <div className="flex flex-col items-start gap-y-1">
                {legend.hasFree && (
                  <span className="inline-flex items-center gap-1">
                    <PlanTierIcon tier="free" decorative className="h-3.5 w-3.5" />
                    {t('sidebar.legendFree')}
                  </span>
                )}
                {legend.hasPaid && (
                  <span className="inline-flex items-center gap-1">
                    <PlanTierIcon tier="paid" decorative className="h-3.5 w-3.5" />
                    {t('sidebar.legendPaid')}
                  </span>
                )}
              </div>
              <p className="mt-0.5">{t('sidebar.legendBasis')}</p>
            </div>
          )}
          {legend.hasLegacy && <p>{t('sidebar.legendLegacy')}</p>}
        </div>
      )}

      {infoCard && (
        <ModelInfoPopover
          key={infoCard.model}
          model={infoCard.model}
          anchorEl={infoCard.anchorEl}
          autoFocus={false}
          onClose={() => setInfoCard(null)}
          onPointerEnter={event => event.pointerType === 'mouse' && clearTimeout(closeTimerRef.current)}
          onPointerLeave={event => event.pointerType === 'mouse' && _scheduleCardClose()}
        />
      )}
    </div>
  )
}
