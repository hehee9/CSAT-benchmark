/* eslint-disable react-refresh/only-export-components */

/**
 * @file useData.jsx
 * @brief 전역 시험 데이터 상태 관리를 위한 Context 및 Hook
 */

import { createContext, useContext, useState, useEffect } from 'react'
import {
  loadExamData,
  loadModelMetadata,
  loadModelPerformance,
  extractUniqueValues
} from '@/utils/dataLoader'

const DataContext = createContext(null)

/**
 * @brief 완료된 결과만 대시보드 입력으로 사용
 * @param {Array} results - 공개 결과 배열
 * @return {Array} 완료된 결과 배열
 */
function _getCompletedResults(results) {
  return results.filter(result => result.complete !== false)
}

/**
 * @brief 데이터 제공자 컴포넌트
 * @param {Object} props - { children, exam, mode }
 */
export function DataProvider({ children, exam, mode = 'default' }) {
  const [data, setData] = useState([])
  const [tokenUsage, setTokenUsage] = useState({})
  const [modelMetadata, setModelMetadata] = useState({})
  const [modelPerformance, setModelPerformance] = useState({ updatedAt: null, models: {} })
  const [questionsMetadata, setQuestionsMetadata] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [subjects, setSubjects] = useState([])
  const [sections, setSections] = useState({})
  const [models, setModels] = useState([])
  const [dataMode, setDataMode] = useState(null)
  const [committedExam, setCommittedExam] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function fetchData() {
      setLoading(true)
      setError(null)
      const [examData, modelMetadataData, modelPerformanceData] = await Promise.all([
        loadExamData(exam, mode),
        loadModelMetadata(),
        loadModelPerformance()
      ])
      if (cancelled) return

      const resultsData = _getCompletedResults(examData.results)
      const values = extractUniqueValues(resultsData, exam)
      setData(resultsData)
      setTokenUsage(examData.tokenUsage)
      setModelMetadata(modelMetadataData)
      setModelPerformance(modelPerformanceData)
      setQuestionsMetadata(examData.questionsMetadata)
      setSubjects(values.subjects)
      setSections(values.sections)
      setModels(values.models)
      setDataMode(mode)
      setCommittedExam(exam)
      setLoading(false)
    }

    fetchData().catch(err => {
      if (cancelled) return
      setError(err.message)
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [exam, mode])

  const displayedExam = committedExam || exam
  const displayedMode = dataMode || mode

  const value = {
    data,
    tokenUsage,
    modelMetadata,
    modelPerformance,
    questionsMetadata,
    loading,
    error,
    subjects,
    sections,
    models,
    dataMode,
    committedExam,
    exam: displayedExam,
    mode: displayedMode,
    modeConfig: displayedExam?.modes?.find(item => item.id === displayedMode) || null
  }

  return (
    <DataContext.Provider value={value}>
      {children}
    </DataContext.Provider>
  )
}

/**
 * @brief 데이터 컨텍스트 사용 훅
 * @return {Object} 전역 시험 데이터 상태
 */
export function useData() {
  const context = useContext(DataContext)
  if (!context) {
    throw new Error('useData must be used within a DataProvider')
  }
  return context
}
