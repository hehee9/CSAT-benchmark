/**
 * @file SubjectFilter.jsx
 * @brief 시험 정의에 따라 과목 필터를 표시하는 컴포넌트
 */

import { useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'

const SUBJECT_I18N_KEYS = {
  '국어': 'subjects.korean',
  '수학': 'subjects.math',
  '영어': 'subjects.english',
  '한국사': 'subjects.history',
  '탐구': 'subjects.exploration',
  '공통': 'subjects.common',
  '화작': 'subjects.hwajak',
  '언매': 'subjects.unmae',
  '확통': 'subjects.hwakton',
  '미적': 'subjects.mijeok',
  '기하': 'subjects.giha',
  '물리1': 'subjects.physics1',
  '물리2': 'subjects.physics2',
  '화학1': 'subjects.chemistry1',
  '화학2': 'subjects.chemistry2',
  '생명1': 'subjects.biology1',
  '생명2': 'subjects.biology2',
  '지구1': 'subjects.earthScience1',
  '지구2': 'subjects.earthScience2',
  '생활과윤리': 'subjects.lifeEthics',
  '윤리와사상': 'subjects.ethicsAndThought',
  '한국지리': 'subjects.koreanGeography',
  '세계지리': 'subjects.worldGeography',
  '동아시아사': 'subjects.eastAsianHistory',
  '세계사': 'subjects.worldHistory',
  '경제': 'subjects.economics',
  '정치와법': 'subjects.politicsAndLaw',
  '사회문화': 'subjects.society'
}

/**
 * @brief 필터 키가 선택되었는지 확인
 * @param {string[]} selected - 선택된 필터 키
 * @param {Object} child - 시험 정의 하위 섹션
 * @return {boolean} 선택 여부
 */
function _isChildSelected(selected, child) {
  return selected.includes(child.key) || selected.includes(child.legacyKey)
}

/**
 * @brief 필터 키의 기존 별칭을 제거
 * @param {string[]} selected - 선택된 필터 키
 * @param {Object} child - 시험 정의 하위 섹션
 * @return {string[]} 별칭을 제거한 목록
 */
function _removeChildAliases(selected, child) {
  return selected.filter(value => value !== child.key && value !== child.legacyKey)
}

/**
 * @brief 시험 정의 기반 과목 필터
 * @param {Object} props - { selected, onChange, showDetail, groups }
 * @param {string[]} props.selected - 선택된 과목 필터 키
 * @param {function} props.onChange - 선택 변경 콜백
 * @param {boolean} props.showDetail - 하위 섹션 표시 여부
 * @param {Array} props.groups - getSubjectFilterGroups 결과
 */
export default function SubjectFilter({ selected, onChange, showDetail = false, groups = [] }) {
  const { t } = useTranslation()
  const checkboxRefs = useRef({})

  const translate = (name) => SUBJECT_I18N_KEYS[name] ? t(SUBJECT_I18N_KEYS[name]) : name

  /**
   * @brief 상위 과목 체크박스 상태 계산
   * @param {Object} group - 시험 정의 그룹
   * @return {'checked' | 'unchecked' | 'indeterminate'} 체크 상태
   */
  function getParentState(group) {
    if (!group.children?.length) return selected.includes(group.key) ? 'checked' : 'unchecked'
    const selectedCount = group.children.filter(child => _isChildSelected(selected, child)).length
    if (selectedCount === 0) return 'unchecked'
    if (selectedCount === group.children.length) return 'checked'
    return 'indeterminate'
  }

  /**
   * @brief 상위 과목 토글
   * @param {Object} group - 시험 정의 그룹
   */
  function handleParentToggle(group) {
    if (!group.children?.length) {
      onChange(selected.includes(group.key)
        ? selected.filter(value => value !== group.key)
        : [...selected, group.key])
      return
    }

    const allSelected = group.children.every(child => _isChildSelected(selected, child))
    const filtered = group.children.reduce(_removeChildAliases, selected)
      .filter(value => value !== group.key)
    onChange(allSelected ? filtered : [...filtered, ...group.children.map(child => child.key)])
  }

  useEffect(() => {
    groups.forEach(group => {
      const ref = checkboxRefs.current[group.key]
      if (!ref || !group.children?.length) return
      const count = group.children.filter(child => _isChildSelected(selected, child)).length
      ref.indeterminate = count > 0 && count < group.children.length
    })
  }, [groups, selected])

  /**
   * @brief 하위 섹션 토글
   * @param {Object} group - 시험 정의 그룹
   * @param {Object} child - 시험 정의 하위 섹션
   */
  function handleChildToggle(group, child) {
    const filtered = _removeChildAliases(selected, child)
    onChange(_isChildSelected(selected, child) ? filtered : [...filtered, child.key])
  }

  return (
    <div className="mb-6">
      <h3 className="font-semibold mb-2 text-gray-700 dark:text-gray-300">{t('sidebar.subjectFilter')}</h3>
      <div className="space-y-1">
        {groups.map(group => {
          const hasChildren = group.children?.length > 0
          return (
            <div key={group.key}>
              <label className="flex items-center cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 p-1 rounded text-gray-800 dark:text-gray-200">
                <input
                  ref={element => { checkboxRefs.current[group.key] = element }}
                  type="checkbox"
                  checked={getParentState(group) === 'checked'}
                  onChange={() => handleParentToggle(group)}
                  className="mr-2 rounded"
                />
                <span className="text-sm font-medium">{translate(group.name || group.group)}</span>
              </label>

              {showDetail && hasChildren && (
                <div className="ml-5 space-y-0.5">
                  {group.children.map(child => (
                    <label key={child.key} className="flex items-center cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 p-1 rounded">
                      <input
                        type="checkbox"
                        checked={_isChildSelected(selected, child)}
                        onChange={() => handleChildToggle(group, child)}
                        className="mr-2 rounded text-blue-400"
                      />
                      <span className="text-xs text-gray-600 dark:text-gray-400">{translate(child.name)}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
