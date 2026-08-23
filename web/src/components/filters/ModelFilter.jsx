/**
 * @file ModelFilter.jsx
 * @brief 모델 필터 체크박스 컴포넌트 (개발사별 그룹화, Tri-State Checkbox)
 */

import { useRef, useEffect, useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useData } from '@/hooks/useData'
import { groupModelsByVendor, getSortedVendors } from '@/utils/colorUtils'
import { formatModelDisplayName, getModelDescription } from '@/utils/modelMeta'

/**
 * @brief 모델명으로 설명 툴팁 ID 생성
 * @param {string} modelName - 모델명
 * @return {string} 툴팁 ID
 */
function _getModelTooltipId(modelName) {
  return `model-description-${encodeURIComponent(modelName)}`
}

/**
 * @brief 모델 필터 컴포넌트
 * @param {Object} props - { selected, onChange, hoveredModel, onModelHover }
 */
export default function ModelFilter({ selected, onChange, hoveredModel, onModelHover }) {
  const { t, i18n } = useTranslation()
  const { models, modelMetadata } = useData()
  const checkboxRefs = useRef({})
  const modelRowRefs = useRef({})
  const [collapsed, setCollapsed] = useState({})
  const [openModelDescription, setOpenModelDescription] = useState(null)

  /** @brief 개발사별 그룹화 (이름 내림차순 정렬) */
  const groupedModels = useMemo(() => groupModelsByVendor(models), [models])

  /** @brief 개발사 목록 (모델 수 내림차순 정렬) */
  const sortedVendors = useMemo(() => getSortedVendors(groupedModels), [groupedModels])

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

  useEffect(() => {
    if (!openModelDescription) return undefined

    const handleOutsidePointerDown = (event) => {
      const row = modelRowRefs.current[openModelDescription]
      if (row && !row.contains(event.target)) {
        setOpenModelDescription(null)
      }
    }

    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        setOpenModelDescription(null)
      }
    }

    document.addEventListener('pointerdown', handleOutsidePointerDown)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('pointerdown', handleOutsidePointerDown)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [openModelDescription])

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
                    const description = getModelDescription(model, i18n.language, modelMetadata)
                    const hasDescription = Boolean(description)
                    const isDescriptionOpen = openModelDescription === model
                    const tooltipId = _getModelTooltipId(model)
                    return (
                      <div
                        key={model}
                        ref={element => { modelRowRefs.current[model] = element }}
                        className={`relative flex min-w-0 items-center rounded p-1 transition-colors ${
                          isHovered
                            ? 'bg-blue-50 dark:bg-blue-900/30 ring-1 ring-blue-300 dark:ring-blue-700'
                            : 'hover:bg-gray-50 dark:hover:bg-gray-700'
                        }`}
                        onMouseEnter={() => onModelHover?.(model)}
                        onMouseLeave={() => onModelHover?.(null)}
                      >
                        <label className="flex min-w-0 flex-1 items-center cursor-pointer">
                          <input
                            type="checkbox"
                            checked={selected.includes(model)}
                            onChange={() => handleModelToggle(model)}
                            className="mr-2 rounded"
                          />
                          <span className="text-xs text-gray-600 dark:text-gray-400 truncate" title={formatModelDisplayName(model)}>
                            {formatModelDisplayName(model)}
                          </span>
                        </label>
                        {hasDescription && (
                          <button
                            type="button"
                            aria-label={isDescriptionOpen ? t('sidebar.hideModelDescription') : t('sidebar.showModelDescription')}
                            aria-describedby={isDescriptionOpen ? tooltipId : undefined}
                            className="ml-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-gray-300 text-[10px] font-semibold leading-none text-gray-500 transition-colors hover:border-gray-400 hover:bg-gray-100 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 focus-visible:ring-offset-1 dark:border-gray-600 dark:text-gray-400 dark:hover:border-gray-500 dark:hover:bg-gray-700 dark:hover:text-gray-200 dark:focus-visible:ring-offset-gray-800"
                            onPointerEnter={(event) => {
                              if (event.pointerType !== 'touch') {
                                setOpenModelDescription(model)
                              }
                            }}
                            onPointerLeave={(event) => {
                              if (event.pointerType !== 'touch' && document.activeElement !== event.currentTarget) {
                                setOpenModelDescription(current => current === model ? null : current)
                              }
                            }}
                            onPointerDown={(event) => {
                              if (event.pointerType === 'touch') {
                                event.preventDefault()
                                setOpenModelDescription(current => current === model ? null : model)
                              }
                            }}
                            onFocus={() => setOpenModelDescription(model)}
                            onBlur={() => setOpenModelDescription(current => current === model ? null : current)}
                            onClick={(event) => {
                              if (event.detail === 0) {
                                setOpenModelDescription(current => current === model ? null : model)
                              }
                            }}
                          >
                            ?
                          </button>
                        )}
                        {isDescriptionOpen && hasDescription && (
                          <div
                            id={tooltipId}
                            role="tooltip"
                            className="absolute left-6 right-0 top-full z-50 mt-1 break-words whitespace-normal rounded border border-gray-200 bg-white px-2 py-1.5 text-xs leading-snug text-gray-700 shadow-lg dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                          >
                            {description}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
