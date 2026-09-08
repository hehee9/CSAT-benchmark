/**
 * @file App.jsx
 * @brief 2026 수능 LLM 풀이 대시보드 - 메인 App 컴포넌트
 */

import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { DataProvider, useData } from '@/hooks/useData'
import { ThemeProvider } from '@/hooks/useTheme'
import { useSidebar } from '@/hooks/useSidebar'
import { Header, Sidebar, Footer, BottomNav } from '@/components/layout'
import {
  ScoreBarChart,
  ScoreBreakdownChart,
  CostScatterChart,
  TokenUsageChart,
  QuestionHeatmap,
  ModelCompareChart,
  ChoiceSelectionChart
} from '@/components/charts'
import { ScoreTable, CostTable } from '@/components/tables'
import { ModelSelectDropdown } from '@/components/common'
import { calculateAllModelScores, getCostData, getMaxScore, calculateBestWorstScores, calculateImageBasedScores, getSubjectFilterGroups, SCORE_BASIS } from '@/utils/dataTransform'
import { transformToHeatmapData, transformToRadarData } from '@/utils/heatmapTransform'
import { transformToChoiceData } from '@/utils/choiceTransform'
import { getModelColor, VENDORS, groupModelsByVendor, getSortedVendors, getDefaultSelectedModels } from '@/utils/colorUtils'
import { getDashboardQueryState, replaceDashboardQueryState } from '@/utils/urlState'
import { DEFAULT_ANALYSIS_X, DEFAULT_ANALYSIS_Y } from '@/utils/analysisMetrics'
import { loadBenchmarkCatalog } from '@/utils/dataLoader'
import { formatModelDisplayName } from '@/utils/modelMeta'

/**
 * @brief 탭 정의
 */
const TAB_KEYS = ['overview', 'subjects', 'compare', 'cost']

/**
 * @brief 점수 기준 선택 컨트롤
 * @param {Object} props - 점수 기준과 변경 콜백
 */
function ScoreBasisControl({ scoreBasis, onScoreBasisChange, t }) {
  return (
    <div className="flex shrink-0 rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden" role="group" aria-label={t('header.scoreBasis')}>
      <button
        type="button"
        onClick={() => onScoreBasisChange('normalized')}
        aria-pressed={scoreBasis === SCORE_BASIS.NORMALIZED}
        className={`px-2.5 py-2 text-xs md:text-sm ${scoreBasis === SCORE_BASIS.NORMALIZED ? 'bg-blue-500 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}
      >
        {t('header.normalized')}
      </button>
      <button
        type="button"
        onClick={() => onScoreBasisChange('raw')}
        aria-pressed={scoreBasis === SCORE_BASIS.RAW}
        className={`px-2.5 py-2 text-xs md:text-sm border-l border-gray-300 dark:border-gray-600 ${scoreBasis === SCORE_BASIS.RAW ? 'bg-blue-500 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}
      >
        {t('header.raw')}
      </button>
    </div>
  )
}

/**
 * @brief 탐구 과목 목록 (데이터에서는 subject로 저장됨)
 */
/**
 * @brief 과목/섹션명 → 번역 키 맵핑
 */
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

const INITIAL_UI_STATE = {
  tab: 'overview',
  scoreView: 'average',
  analysisX: DEFAULT_ANALYSIS_X,
  analysisY: DEFAULT_ANALYSIS_Y,
  subjects: [],
  selectedSubject: '',
  selectedSection: ''
}

/**
 * @brief 과목/섹션명 번역 헬퍼
 * @param {string} name - 과목/섹션명
 * @param {function} t - 번역 함수
 * @return {string} 번역된 이름
 */
function _translateSubject(name, t) {
  return SUBJECT_I18N_KEYS[name] ? t(SUBJECT_I18N_KEYS[name]) : name
}

/**
 * @brief 대시보드 메인 컴포넌트
 */
function Dashboard({
  exam: requestedExam,
  exams = [],
  benchmarkMode = 'default',
  onExamChange,
  onBenchmarkModeChange,
  scoreBasis = SCORE_BASIS.NORMALIZED,
  onScoreBasisChange
}) {
  const { t } = useTranslation()
  const { data, tokenUsage, modelMetadata, modelPerformance, questionsMetadata, loading, error, models, dataMode, exam, committedExam } = useData()
  const sidebar = useSidebar()
  const subjectFilterGroups = useMemo(() => getSubjectFilterGroups(exam, data), [exam, data])
  const isPreparation = committedExam?.status === 'preparation' && data.length === 0

  const [filters, setFilters] = useState({
    subjects: INITIAL_UI_STATE.subjects,
    models: [],
    sortBy: 'score_desc',
    showDetail: false
  })
  const [activeTab, setActiveTab] = useState(INITIAL_UI_STATE.tab)
  const [analysisX, setAnalysisX] = useState(INITIAL_UI_STATE.analysisX)
  const [analysisY, setAnalysisY] = useState(INITIAL_UI_STATE.analysisY)
  const [selectedSubject, setSelectedSubject] = useState(INITIAL_UI_STATE.selectedSubject)
  const [selectedSection, setSelectedSection] = useState(INITIAL_UI_STATE.selectedSection)
  const [compareModels, setCompareModels] = useState([])
  const [hoveredModel, setHoveredModel] = useState(null)
  const [scoreViewMode, setScoreViewMode] = useState(INITIAL_UI_STATE.scoreView)
  const [isModelSelectionTouched, setIsModelSelectionTouched] = useState(false)
  const subjectSelectRef = useRef(null)
  const sectionSelectRef = useRef(null)
  const mainRef = useRef(null)
  const scrollPositions = useRef({})
  const [defaultSelectionReady, setDefaultSelectionReady] = useState({ key: '', data: null })
  const [headerVisible, setHeaderVisible] = useState(false)
  const [scrolledPastHeader, setScrolledPastHeader] = useState(false)
  const headerTimeoutRef = useRef(null)
  const originalHeaderRef = useRef(null)
  const selectionKey = `${requestedExam.id}:${benchmarkMode}`
  const selectionBoundaryRef = useRef({ key: selectionKey, data, pending: false })

  useEffect(() => {
    const selectionBoundary = selectionBoundaryRef.current
    if (selectionBoundary.key !== selectionKey) {
      selectionBoundaryRef.current = { key: selectionKey, data, pending: true }
      return
    }
    if (selectionBoundary.pending && selectionBoundary.data !== data) {
      selectionBoundaryRef.current = { key: selectionKey, data, pending: false }
    }
  }, [selectionKey, data])

  const _areArraysEqual = useCallback((a = [], b = []) => {
    if (a.length !== b.length) return false
    return a.every((value, index) => value === b[index])
  }, [])

  const handleFilterChange = useCallback((nextFilters) => {
    if (!_areArraysEqual(filters.models, nextFilters.models)) {
      setIsModelSelectionTouched(true)
    }
    setFilters(nextFilters)
  }, [_areArraysEqual, filters.models])

  /**
   * @brief 점수 기준 전환 시 허용되지 않는 보기 모드 초기화
   */
  const handleScoreBasisChange = useCallback((nextBasis) => {
    if (nextBasis === SCORE_BASIS.RAW) {
      setScoreViewMode(prev => prev === 'bestWorst' ? 'average' : prev)
    }
    onScoreBasisChange?.(nextBasis)
  }, [onScoreBasisChange])

  /**
   * @brief 현재 점수 기준에 맞는 차트 보기 모드 적용
   */
  const handleScoreViewModeChange = useCallback((nextViewMode) => {
    setScoreViewMode(scoreBasis === SCORE_BASIS.RAW && nextViewMode === 'bestWorst' ? 'average' : nextViewMode)
  }, [scoreBasis])

  // 전체 모델 점수 계산 (과목 필터 적용)
  const overallScores = useMemo(() => {
    if (!data?.length || !models?.length) return []
    return calculateAllModelScores(data, models, filters.subjects, { exam, scoreBasis })
  }, [data, models, filters.subjects, exam, scoreBasis])

  // 동적 만점 계산
  const maxScore = useMemo(() => {
    return getMaxScore(filters.subjects, { exam, scoreBasis })
  }, [filters.subjects, exam, scoreBasis])

  const normalizedMaxScore = useMemo(() => {
    return getMaxScore(filters.subjects, { exam, scoreBasis: SCORE_BASIS.NORMALIZED })
  }, [filters.subjects, exam])

  /**
   * @brief 데이터 로드 완료 후 기본 모델 필터 설정
   * - 모델 필터를 건드리지 않은 상태에서는 각 모드의 기본 표시 규칙 적용
   * - 모델 필터를 건드린 뒤에는 새 모드에 있는 선택 모델 유지
   * - 유지되는 모델이 없으면 각 모드의 기본 표시 규칙 적용
   * - 비교 탭 선택 모델도 새 모드에 있는 모델만 유지
   */
  useEffect(() => {
    if (loading || (defaultSelectionReady.key === selectionKey && defaultSelectionReady.data === data)) return
    if (dataMode !== benchmarkMode) return
    const selectionBoundary = selectionBoundaryRef.current
    if (selectionBoundary.pending && selectionBoundary.data === data) return

    if (!data?.length || !models?.length) {
      // 새 데이터셋의 선택 모델 상태를 외부 데이터 로드 결과와 동기화한다.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFilters(prev => ({ ...prev, models: [] }))
      setCompareModels([])
      // 시험·모드 조합마다 모델 기본 선택을 한 번만 계산한다.
      setDefaultSelectionReady({ key: selectionKey, data })
      selectionBoundaryRef.current = { key: selectionKey, data, pending: false }
      return
    }

    const allScores = calculateAllModelScores(data, models, [], { exam, scoreBasis })
    const defaultModels = getDefaultSelectedModels(models, allScores)
    const availableModels = new Set(models)

    // 새 시험에서 사용할 기본 모델 목록을 필터 상태에 반영한다.
    setFilters(prev => {
      const retainedModels = prev.models.filter(model => availableModels.has(model))
      if (!isModelSelectionTouched) {
        return {
          ...prev,
          models: defaultModels
        }
      }
      return {
        ...prev,
        models: retainedModels.length > 0 ? retainedModels : defaultModels
      }
    })
    setCompareModels(prev => prev.filter(model => availableModels.has(model)))
    setDefaultSelectionReady({ key: selectionKey, data })
    selectionBoundaryRef.current = { key: selectionKey, data, pending: false }
  }, [loading, data, models, dataMode, benchmarkMode, exam, scoreBasis, defaultSelectionReady, isModelSelectionTouched, selectionKey])

  // 필터 및 정렬 적용
  const filteredScores = useMemo(() => {
    let result = [...overallScores]

    // 모델 필터
    if (filters.models.length > 0) {
      result = result.filter(s => filters.models.includes(s.model))
    }

    // 정렬
    switch (filters.sortBy) {
      case 'score_asc':
        result.sort((a, b) => a.total - b.total)
        break
      case 'name_asc':
        result.sort((a, b) => a.model.localeCompare(b.model))
        break
      case 'name_desc':
        result.sort((a, b) => b.model.localeCompare(a.model))
        break
      case 'vendor':
        // VENDORS 배열 순서대로, 같은 개발사 내에서는 이름 내림차순
        result.sort((a, b) => {
          const vendorA = VENDORS.findIndex(v => v.pattern?.test(a.model))
          const vendorB = VENDORS.findIndex(v => v.pattern?.test(b.model))
          const idxA = vendorA === -1 ? VENDORS.length : vendorA
          const idxB = vendorB === -1 ? VENDORS.length : vendorB
          if (idxA !== idxB) return idxA - idxB
          return b.model.localeCompare(a.model) // 같은 개발사 내에서는 이름 내림차순
        })
        break
      case 'score_desc':
      default:
        result.sort((a, b) => b.total - a.total)
    }

    return result
  }, [overallScores, filters])

  // 보기 모드에 따른 점수 차트 데이터
  const scoreChartData = useMemo(() => {
    if (!data?.length || !filteredScores?.length) return []

    const displayModels = filteredScores.map(s => s.model)

    if (scoreViewMode === 'bestWorst') {
      // 최고/최저 조합 점수
      const scores = calculateBestWorstScores(data, displayModels, { exam })
      return scores.map(s => ({
        ...s,
        color: getModelColor(s.model)
      }))
    }

    if (scoreViewMode === 'withImage' || scoreViewMode === 'withoutImage') {
      // 이미지 O/X 득점률
      const hasImage = scoreViewMode === 'withImage'
      const scores = calculateImageBasedScores(data, questionsMetadata, displayModels, hasImage)
      return scores.map(s => ({
        ...s,
        color: getModelColor(s.model)
      }))
    }

    // 기본(평균) 모드: filteredScores 사용
    return filteredScores.map(s => ({
      model: s.model,
      score: s.total,
      totalPoints: maxScore,
      color: getModelColor(s.model)
    }))
  }, [data, filteredScores, questionsMetadata, scoreViewMode, maxScore, exam])

  // 비용 데이터 (모델 필터링 + 과목 필터링 적용)
  const costData = useMemo(() => {
    if (!data?.length || !filteredScores?.length) return []
    return getCostData(data, filteredScores, tokenUsage || {}, filters.subjects, { exam, scoreBasis, modelPerformance })
  }, [data, filteredScores, tokenUsage, filters.subjects, exam, scoreBasis, modelPerformance])

  const sectionKeysByModel = useMemo(() => Object.fromEntries(
    costData.map(entry => [entry.model, entry.tokenSectionKeys || []])
  ), [costData])

  // 히트맵 데이터
  const heatmapData = useMemo(() => {
    if (!data?.length || !selectedSubject || !selectedSection) return {}

    // 탐구 과목인 경우: 실제 데이터의 subject=섹션명, section="탐구"
    if (selectedSubject === '탐구') {
      return transformToHeatmapData(data, selectedSection, '탐구')
    }

    return transformToHeatmapData(data, selectedSubject, selectedSection)
  }, [data, selectedSubject, selectedSection])

  // 레이더 차트 데이터
  const radarData = useMemo(() => {
    if (!overallScores?.length || !compareModels?.length) return []
    return transformToRadarData(overallScores, compareModels, t, { exam, scoreBasis })
  }, [overallScores, compareModels, t, exam, scoreBasis])

  // 표시할 모델 목록 (필터 및 정렬 적용 - filteredScores 순서 따름)
  const displayModels = useMemo(() => {
    return filteredScores.map(s => s.model)
  }, [filteredScores])

  // 문항 상세에서는 전체 결과 중 사용자가 선택한 모델의 부분 결과도 표시
  const detailModels = useMemo(() => {
    return isModelSelectionTouched && filters.models.length > 0
      ? filters.models.filter(model => models.includes(model))
      : models
  }, [filters.models, models, isModelSelectionTouched])

  // 선지 선택률 데이터
  const choiceData = useMemo(() => {
    if (!heatmapData || !Object.keys(heatmapData).length || !detailModels?.length) return []
    return transformToChoiceData(heatmapData, detailModels, selectedSubject, selectedSection)
  }, [heatmapData, detailModels, selectedSubject, selectedSection])

  // 시험 정의의 그룹 목록을 화면용 과목 목록으로 변환
  const virtualSubjects = useMemo(() => {
    return subjectFilterGroups.map(group => group.group)
  }, [subjectFilterGroups])

  // 과목 선택 시 섹션 목록
  const availableSections = useMemo(() => {
    if (!selectedSubject) return []

    const group = subjectFilterGroups.find(item => item.group === selectedSubject)
    if (!group) return []
    const sectionNames = group.sections.map(section => section.group === '탐구' ? section.subject : section.section)
    if (sectionNames.length === 1 && sectionNames[0] === selectedSubject) return []
    return sectionNames
  }, [selectedSubject, subjectFilterGroups])

  /**
   * @brief 시험 전환 시 현재 필터와 상세 선택을 유효한 값으로 정리
   */
  useEffect(() => {
    const validFilters = new Set(subjectFilterGroups.flatMap(group => [
      group.key,
      ...(group.children || []).flatMap(child => [child.key, child.legacyKey])
    ]))
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFilters(prev => ({
      ...prev,
      subjects: prev.subjects.filter(subject => validFilters.has(subject))
    }))

    const validSubjects = new Set(subjectFilterGroups.map(group => group.group))
    if (selectedSubject && !validSubjects.has(selectedSubject)) {
      setSelectedSubject('')
      setSelectedSection('')
      return
    }

    if (selectedSection && !availableSections.includes(selectedSection)) {
      setSelectedSection('')
    }
  }, [subjectFilterGroups, selectedSubject, selectedSection, availableSections])

  /**
   * @brief PC 헤더 스크롤 감지 (원본 헤더가 화면 밖으로 나갔는지)
   */
  useEffect(() => {
    const handleScroll = () => {
      if (originalHeaderRef.current) {
        const rect = originalHeaderRef.current.getBoundingClientRect()
        setScrolledPastHeader(rect.bottom < 0)
      }
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  /**
   * @brief PC 헤더 호버 핸들러
   */
  const handleHeaderTriggerEnter = useCallback(() => {
    if (!scrolledPastHeader) return
    if (headerTimeoutRef.current) {
      clearTimeout(headerTimeoutRef.current)
      headerTimeoutRef.current = null
    }
    setHeaderVisible(true)
  }, [scrolledPastHeader])

  const handleHeaderTriggerLeave = useCallback(() => {
    headerTimeoutRef.current = setTimeout(() => {
      setHeaderVisible(false)
    }, 300)
  }, [])

  /**
   * @brief 탭 전환 시 스크롤 위치 저장/복원
   * @param {string} newTab - 새 탭 키
   */
  const handleTabChange = useCallback((newTab) => {
    // 현재 탭 스크롤 위치 저장
    if (mainRef.current) {
      scrollPositions.current[activeTab] = mainRef.current.scrollTop
    }

    setActiveTab(newTab)

    // 새 탭 스크롤 위치 복원 (다음 렌더 사이클에서)
    requestAnimationFrame(() => {
      if (mainRef.current) {
        mainRef.current.scrollTop = scrollPositions.current[newTab] || 0
      }
    })
  }, [activeTab])

  /**
   * @brief 과목 선택 시 자동 섹션 설정
   */
  const handleSubjectChange = useCallback((newSubject) => {
    setSelectedSubject(newSubject)

    if (!newSubject) {
      setSelectedSection('')
      return
    }

    const group = subjectFilterGroups.find(item => item.group === newSubject)
    const detailSections = group?.sections
      .filter(section => section.kind !== 'common')
      .map(section => section.group === '탐구' ? section.subject : section.section) || []
    const allSections = group?.sections || []
    if (detailSections.length === 1 && detailSections[0] === newSubject) {
      setSelectedSection(newSubject)
    } else if (newSubject === '탐구') {
      setSelectedSection(detailSections[0] || '')
    } else {
      setSelectedSection(allSections[0]?.section || '')
    }
  }, [subjectFilterGroups])

  // 데이터 로드 완료 후 기본 과목 선택
  useEffect(() => {
    if (!loading && virtualSubjects.length > 0 && !selectedSubject) {
      const firstSubject = virtualSubjects[0]
      if (firstSubject) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        handleSubjectChange(firstSubject)
      }
    }
  }, [loading, virtualSubjects, selectedSubject, handleSubjectChange])

  // 과목 드롭다운 휠 스크롤 이벤트 등록 (passive: false로 스크롤 방지)
  useEffect(() => {
    const el = subjectSelectRef.current
    if (!el) return

    const handler = (e) => {
      e.preventDefault()
      e.stopPropagation()
      if (!virtualSubjects.length) return

      const currentIndex = virtualSubjects.indexOf(selectedSubject)
      let newIndex

      if (e.deltaY > 0) {
        newIndex = currentIndex >= virtualSubjects.length - 1 ? 0 : currentIndex + 1
      } else {
        newIndex = currentIndex <= 0 ? virtualSubjects.length - 1 : currentIndex - 1
      }

      handleSubjectChange(virtualSubjects[newIndex])
    }

    el.addEventListener('wheel', handler, { passive: false })
    return () => el.removeEventListener('wheel', handler)
  }, [virtualSubjects, selectedSubject, handleSubjectChange, activeTab])

  // 섹션 드롭다운 휠 스크롤 이벤트 등록
  useEffect(() => {
    const el = sectionSelectRef.current
    if (!el) return

    const handler = (e) => {
      e.preventDefault()
      e.stopPropagation()
      if (!availableSections.length) return

      const currentIndex = availableSections.indexOf(selectedSection)
      let newIndex

      if (e.deltaY > 0) {
        newIndex = currentIndex >= availableSections.length - 1 ? 0 : currentIndex + 1
      } else {
        newIndex = currentIndex <= 0 ? availableSections.length - 1 : currentIndex - 1
      }

      setSelectedSection(availableSections[newIndex])
    }

    el.addEventListener('wheel', handler, { passive: false })
    return () => el.removeEventListener('wheel', handler)
  }, [availableSections, selectedSection, activeTab])

  /**
   * @brief 현재 시험·실행 모드·점수 기준을 공유 가능한 URL에 반영
   */
  useEffect(() => {
    if (loading || dataMode !== benchmarkMode || committedExam?.id !== requestedExam.id) return
    replaceDashboardQueryState({
      exam: requestedExam.id,
      mode: benchmarkMode,
      scoreBasis
    })
  }, [loading, dataMode, benchmarkMode, requestedExam, committedExam, scoreBasis])

  if (loading && !committedExam) {
    return (
      <div
        className="flex items-center justify-center h-screen bg-gray-100 dark:bg-gray-900"
        data-benchmark-mode={benchmarkMode}
        data-exam-id={requestedExam.id}
      >
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-100 dark:bg-gray-900">
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 max-w-md">
          <h2 className="text-xl font-bold text-red-600 dark:text-red-400 mb-2">{t('common.error')}</h2>
          <p className="text-gray-600 dark:text-gray-400">{error}</p>
        </div>
      </div>
    )
  }

  return (
      <div
        className="min-h-screen bg-gray-100 dark:bg-gray-900 flex flex-col"
        data-benchmark-mode={benchmarkMode}
        data-exam-id={requestedExam.id}
        data-dashboard-ready={!loading && !error && defaultSelectionReady.key === selectionKey && defaultSelectionReady.data === data ? 'true' : 'false'}
    >
      {/* PC 헤더 호버 트리거 영역 (스크롤 시에만 활성화) */}
      {scrolledPastHeader && (
        <div
          className="hidden md:block fixed top-0 left-0 right-0 h-3 z-50"
          onMouseEnter={handleHeaderTriggerEnter}
        />
      )}
      {/* PC 헤더 (스크롤 후 호버 시 표시) */}
      <div
        className={`hidden md:block fixed top-0 left-0 right-0 z-40 transition-transform duration-300 ${
          headerVisible && scrolledPastHeader ? 'translate-y-0' : '-translate-y-full'
        }`}
        onMouseEnter={handleHeaderTriggerEnter}
        onMouseLeave={handleHeaderTriggerLeave}
      >
        <Header
          onMenuToggle={sidebar.toggle}
          exam={requestedExam}
          exams={exams}
          mode={benchmarkMode}
          modes={requestedExam.modes}
          onExamChange={onExamChange}
          onModeChange={onBenchmarkModeChange}
        />
      </div>
      {/* 원본 헤더 (항상 표시) */}
      <div ref={originalHeaderRef}>
        <Header
          onMenuToggle={sidebar.toggle}
          exam={requestedExam}
          exams={exams}
          mode={benchmarkMode}
          modes={requestedExam.modes}
          onExamChange={onExamChange}
          onModeChange={onBenchmarkModeChange}
        />
      </div>
      <div className="flex flex-1">
        <Sidebar
          filters={filters}
          onFilterChange={handleFilterChange}
          subjectFilterGroups={subjectFilterGroups}
          hoveredModel={hoveredModel}
          onModelHover={setHoveredModel}
          isOpen={sidebar.isOpen}
          onClose={sidebar.close}
        />
        <main
          ref={mainRef}
          className="flex-1 p-4 md:p-6 overflow-auto pb-20 md:pb-6"
          onClick={(e) => {
            // 빈 공간 클릭 시 호버 효과 해제
            if (e.target === e.currentTarget) {
              setHoveredModel(null)
            }
          }}
        >
          {/* 탭 네비게이션과 점수 기준 선택 */}
          <div className="flex flex-wrap items-center justify-end md:justify-between gap-3 mb-6">
            <div className="desktop-tabs hidden md:flex gap-2">
              {TAB_KEYS.map(tabKey => (
                <button
                  key={tabKey}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                    activeTab === tabKey
                      ? 'bg-blue-500 text-white shadow-md'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700'
                  }`}
                  onClick={() => handleTabChange(tabKey)}
                >
                  {t(`tabs.${tabKey}`)}
                </button>
              ))}
            </div>
            <ScoreBasisControl
              scoreBasis={scoreBasis}
              onScoreBasisChange={handleScoreBasisChange}
              t={t}
            />
          </div>

          {/* 콘텐츠 영역 */}
          <div className="space-y-6">
            {isPreparation ? (
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                  {t('common.preparingResults')}
                </p>
              </div>
            ) : (
              <>
                {/* 종합 대시보드 탭 */}
                {activeTab === 'overview' && (
                  <>
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                      <ScoreBarChart
                        data={scoreChartData}
                        maxScore={scoreViewMode === 'bestWorst' ? normalizedMaxScore : maxScore}
                        viewMode={scoreViewMode}
                        onViewModeChange={handleScoreViewModeChange}
                        showViewModeButtons={true}
                        allowBestWorst={scoreBasis === SCORE_BASIS.NORMALIZED}
                        title={
                          scoreViewMode === 'withImage' ? t('charts.withImageAccuracy') :
                          scoreViewMode === 'withoutImage' ? t('charts.withoutImageAccuracy') :
                          scoreViewMode === 'bestWorst' ? `${t('charts.bestWorstScore')} (${t('charts.maxPoints', { max: normalizedMaxScore })})` :
                          `${t('charts.totalScore')} (${t('charts.maxPoints', { max: maxScore })})`
                        }
                        subtitle={(() => {
                          if (filters.subjects.length === 0) return null
                          const selectedLabels = subjectFilterGroups.flatMap(group => {
                            if (filters.subjects.includes(group.key)) return []
                            return (group.children || [])
                              .filter(child => filters.subjects.includes(child.key) || filters.subjects.includes(child.legacyKey))
                              .map(child => child.name)
                          })
                          const selectedGroups = subjectFilterGroups
                            .filter(group => filters.subjects.includes(group.key))
                            .map(group => group.name || group.group)
                          return [...selectedGroups, ...selectedLabels].join(', ')
                        })()}
                        hoveredModel={hoveredModel}
                        onModelHover={setHoveredModel}
                        modelMetadata={modelMetadata}
                      />
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                      <ScoreTable
                        data={filteredScores}
                        title={t('charts.scoreTable')}
                        showDetail={filters.showDetail}
                        onToggleDetail={() => setFilters(f => ({ ...f, showDetail: !f.showDetail }))}
                        subjectFilter={filters.subjects}
                        maxScore={maxScore}
                        hoveredModel={hoveredModel}
                        onModelHover={setHoveredModel}
                      />
                    </div>
                  </>
                )}

                {/* 과목별 상세 탭 */}
                {activeTab === 'subjects' && (
                  <>
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                      <div className="flex gap-4 mb-6">
                        <select
                          ref={subjectSelectRef}
                          className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 cursor-pointer"
                          value={selectedSubject}
                          onChange={(e) => handleSubjectChange(e.target.value)}
                        >
                          <option value="">{t('charts.selectSubject')}</option>
                          {virtualSubjects.map(s => (
                            <option key={s} value={s}>{_translateSubject(s, t)}</option>
                          ))}
                        </select>
                        {selectedSubject && availableSections.length > 0 && (
                          <select
                            ref={sectionSelectRef}
                            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 cursor-pointer"
                            value={selectedSection}
                            onChange={(e) => setSelectedSection(e.target.value)}
                          >
                            {availableSections.map(s => (
                              <option key={s} value={s}>{_translateSubject(s, t)}</option>
                            ))}
                          </select>
                        )}
                      </div>

                      {selectedSubject && selectedSection && Object.keys(heatmapData).length > 0 && (
                        <QuestionHeatmap
                          data={heatmapData}
                          models={detailModels}
                          title={`${_translateSubject(selectedSubject, t)} - ${_translateSubject(selectedSection, t)} ${t('charts.questionStatus')}`}
                          subjectName={`${_translateSubject(selectedSubject, t)}_${_translateSubject(selectedSection, t)}`}
                          modelMetadata={modelMetadata}
                        />
                      )}

                      {selectedSubject && selectedSection && choiceData.length > 0 && (
                        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                          <ChoiceSelectionChart
                            data={choiceData}
                            title={`${_translateSubject(selectedSubject, t)} - ${_translateSubject(selectedSection, t)} ${t('charts.choiceRate')}`}
                          />
                        </div>
                      )}

                      {!selectedSubject && (
                        <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                          {t('charts.selectSubject')}
                        </p>
                      )}
                    </div>
                  </>
                )}

                {/* 모델 비교 탭 */}
                {activeTab === 'compare' && (() => {
                  // 정렬된 모델 순서로 개발사별 그룹화
                  const sortedModels = filteredScores.map(s => s.model)
                  const groupedCompareModels = groupModelsByVendor(sortedModels)
                  const sortedVendors = getSortedVendors(groupedCompareModels)

                  return (
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 md:p-6">
                      <div className="mb-6">
                        <h4 className="font-medium text-gray-700 dark:text-gray-300 mb-3">
                          {t('charts.compareModels')}
                        </h4>

                        {/* 모바일: 드롭다운 */}
                        <div className="md:hidden">
                          <ModelSelectDropdown
                            models={sortedModels}
                            selected={compareModels}
                            onChange={setCompareModels}
                            maxSelect={5}
                          />
                        </div>

                        {/* 데스크톱: 체크박스 그룹 */}
                        <div className="hidden md:block space-y-3">
                          {sortedVendors.map(vendor => {
                            const vendorModels = groupedCompareModels[vendor.id]
                            if (!vendorModels?.length) return null

                            return (
                              <div key={vendor.id}>
                                {/* 개발사 헤더 */}
                                <div className="flex items-center gap-2 mb-1.5">
                                  <span
                                    className="w-3 h-3 rounded-full"
                                    style={{ backgroundColor: vendor.color }}
                                  />
                                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                    {vendor.name}
                                  </span>
                                  <span className="text-xs text-gray-400 dark:text-gray-500">
                                    ({vendorModels.length})
                                  </span>
                                </div>
                                {/* 모델 목록 */}
                                <div className="flex flex-wrap gap-2 ml-5">
                                  {vendorModels.map(model => {
                                    const isSelected = compareModels.includes(model)
                                    const isFiltered = filters.models.length === 0 ||
                                                       filters.models.includes(model)
                                    return (
                                      <label
                                        key={model}
                                        className={`flex items-center gap-2 px-3 py-1.5 rounded-full cursor-pointer transition-colors border ${
                                          isSelected
                                            ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700'
                                            : isFiltered
                                              ? 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600'
                                              : 'bg-gray-50 dark:bg-gray-800 text-gray-400 dark:text-gray-500 border-gray-200 dark:border-gray-700 opacity-60'
                                        }`}
                                        onMouseEnter={() => setHoveredModel(model)}
                                        onMouseLeave={() => setHoveredModel(null)}
                                      >
                                        <input
                                          type="checkbox"
                                          className="hidden"
                                          checked={isSelected}
                                          onChange={(e) => {
                                            if (e.target.checked && compareModels.length < 5) {
                                              setCompareModels([...compareModels, model])
                                            } else if (!e.target.checked) {
                                              setCompareModels(compareModels.filter(m => m !== model))
                                            }
                                          }}
                                        />
                                        <span className="text-sm">{formatModelDisplayName(model)}</span>
                                      </label>
                                    )
                                  })}
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                      <ModelCompareChart
                        data={radarData}
                        selectedModels={compareModels}
                        allScores={overallScores}
                        title={t('charts.modelCompare')}
                        height={450}
                        scoreBasis={scoreBasis}
                        hoveredModel={hoveredModel}
                        onModelHover={setHoveredModel}
                      />
                    </div>
                  )
                })()}

                {/* 상세 분석 탭 */}
                {activeTab === 'cost' && (
                  <>
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                      <CostScatterChart
                        data={costData}
                        maxScore={maxScore}
                        modelPerformance={modelPerformance}
                        xMetric={analysisX}
                        yMetric={analysisY}
                        onXMetricChange={setAnalysisX}
                        onYMetricChange={setAnalysisY}
                      />
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                      <TokenUsageChart
                        data={tokenUsage}
                        models={displayModels}
                        subjectFilter={filters.subjects}
                        title={t('charts.tokenUsage')}
                        modelMetadata={modelMetadata}
                        sectionKeysByModel={sectionKeysByModel}
                      />
                    </div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
                      <CostTable
                        data={costData}
                        title={t('charts.costInfo')}
                        showDetail={filters.showDetail}
                        onToggleDetail={() => setFilters(f => ({ ...f, showDetail: !f.showDetail }))}
                      />
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </main>
      </div>
      <Footer />
      <BottomNav activeTab={activeTab} onTabChange={handleTabChange} />
    </div>
  )
}

/**
 * @brief App 루트 컴포넌트
 */
export default function App() {
  const { t } = useTranslation()
  const [catalog, setCatalog] = useState(null)
  const [catalogError, setCatalogError] = useState(null)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [queryState] = useState(() => getDashboardQueryState())
  const [selectedExamId, setSelectedExamId] = useState(queryState.exam)
  const [benchmarkMode, setBenchmarkMode] = useState(queryState.mode)
  const [scoreBasis, setScoreBasis] = useState(queryState.scoreBasis)

  useEffect(() => {
    let cancelled = false
    loadBenchmarkCatalog()
      .then(nextCatalog => {
        if (!cancelled) {
          setCatalog(nextCatalog)
          setCatalogLoading(false)
        }
      })
      .catch(error => {
        if (!cancelled) {
          setCatalogError(error.message)
          setCatalogLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!catalog) return
    const currentExam = catalog.exams.find(item => item.id === selectedExamId) || catalog.exams.find(item => item.id === catalog.default_exam) || catalog.exams[0]
    document.title = currentExam.id === 'csat-2026'
      ? t('header.title')
      : currentExam.title.replace(/ LLM 벤치마크$/, ' LLM 풀이 대시보드')
  }, [catalog, selectedExamId, t])

  if (catalogLoading) {
    return <div className="flex items-center justify-center h-screen bg-gray-100 dark:bg-gray-900 text-gray-600 dark:text-gray-400">{t('common.loading')}</div>
  }

  if (catalogError) {
    return <div className="flex items-center justify-center h-screen bg-gray-100 dark:bg-gray-900"><div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 max-w-md"><h2 className="text-xl font-bold text-red-600 dark:text-red-400 mb-2">{t('common.error')}</h2><p className="text-gray-600 dark:text-gray-400">{catalogError}</p></div></div>
  }

  const defaultExam = catalog.exams.find(exam => exam.id === catalog.default_exam) || catalog.exams[0]
  const exam = catalog.exams.find(item => item.id === selectedExamId) || defaultExam
  const availableModes = exam.modes
  const activeMode = availableModes.find(item => item.id === benchmarkMode)?.id || availableModes[0]?.id || 'default'

  const handleExamChange = (nextExamId) => {
    const nextExam = catalog.exams.find(item => item.id === nextExamId)
    if (!nextExam) return
    const nextModes = nextExam.modes
    setSelectedExamId(nextExam.id)
    setBenchmarkMode(prev => nextModes.some(item => item.id === prev) ? prev : nextModes[0]?.id || 'default')
  }

  const handleModeChange = (nextMode) => {
    if (availableModes.some(item => item.id === nextMode)) setBenchmarkMode(nextMode)
  }

  return (
    <ThemeProvider>
      <DataProvider exam={exam} mode={activeMode}>
        <Dashboard
          exam={exam}
          exams={catalog.exams}
          benchmarkMode={activeMode}
          onExamChange={handleExamChange}
          onBenchmarkModeChange={handleModeChange}
          scoreBasis={scoreBasis}
          onScoreBasisChange={setScoreBasis}
        />
      </DataProvider>
    </ThemeProvider>
  )
}
