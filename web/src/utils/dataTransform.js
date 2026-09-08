/**
 * @file dataTransform.js
 * @brief 시험 정의 기반 점수·비용 데이터 변환
 *
 * 기본 점수 기준은 정규화 점수(450점)이며, 원점수 기준은 각 섹션을 한 번씩
 * 더한 값이다. 시험 정의가 전달되면 섹션 목록과 배점을 모두 시험 정의에서
 * 읽고, 전달되지 않은 기존 호출은 현재 2026 수능 데이터 계약을 사용한다.
 */

import { getModelData } from './dataLoader'

/** @brief 지원 점수 기준 */
export const SCORE_BASIS = Object.freeze({
  NORMALIZED: 'normalized',
  RAW: 'raw'
})

/** @brief 기존 2026 대시보드의 과목별 정규화 만점 */
export const SUBJECT_MAX_SCORES = {
  '국어': 100,
  '수학': 100,
  '영어': 100,
  '한국사': 50,
  '탐구': 100
}

/** @brief 기존 2026 데이터의 세부 과목명 매핑 */
const LEGACY_NAME_MAP = {
  '사문': '사회문화'
}

/**
 * @brief 인자가 옵션 객체인지 판별
 * @param {any} value - 검사할 값
 * @return {boolean} 옵션 객체 여부
 */
function _isOptions(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/**
 * @brief 점수 기준 옵션 정규화
 * @param {Object} options - { exam, scoreBasis }
 * @return {Object} 정규화된 옵션
 */
function _normalizeOptions(options = {}) {
  const scoreBasis = options.scoreBasis ?? SCORE_BASIS.NORMALIZED
  if (scoreBasis !== SCORE_BASIS.NORMALIZED && scoreBasis !== SCORE_BASIS.RAW) {
    throw new Error(`지원하지 않는 점수 기준입니다: ${scoreBasis}`)
  }

  return {
    exam: options.exam ?? null,
    scoreBasis,
    modelPerformance: options.modelPerformance ?? null
  }
}

/**
 * @brief 기존 배열 인자와 새 옵션 객체 인자 분리
 * @param {Array|string[]|Object} subjectFilter - 과목 필터 또는 옵션
 * @param {Object} options - 점수 기준 옵션
 * @return {Object} { subjectFilter, options }
 */
function _resolveFilterArgs(subjectFilter = [], options = {}) {
  if (_isOptions(subjectFilter)) {
    return {
      subjectFilter: subjectFilter.subjectFilter ?? [],
      options: subjectFilter
    }
  }

  return {
    subjectFilter: subjectFilter ?? [],
    options
  }
}

/**
 * @brief 현재 2026 수능의 고정 시험 정의
 * @return {Object} 2026 수능 시험 정의
 */
function _getLegacyExam() {
  return {
    id: 'csat-2026',
    title: '2026 수능',
    sections: [
      { target: '국어/공통', subject: '국어', section: '공통', group: '국어', kind: 'common', questions: 34, max_points: 76 },
      { target: '국어/화작', subject: '국어', section: '화작', group: '국어', kind: 'elective', questions: 11, max_points: 24 },
      { target: '국어/언매', subject: '국어', section: '언매', group: '국어', kind: 'elective', questions: 11, max_points: 24 },
      { target: '수학/공통', subject: '수학', section: '공통', group: '수학', kind: 'common', questions: 22, max_points: 74 },
      { target: '수학/확통', subject: '수학', section: '확통', group: '수학', kind: 'elective', questions: 8, max_points: 26 },
      { target: '수학/미적', subject: '수학', section: '미적', group: '수학', kind: 'elective', questions: 8, max_points: 26 },
      { target: '수학/기하', subject: '수학', section: '기하', group: '수학', kind: 'elective', questions: 8, max_points: 26 },
      { target: '영어/영어', subject: '영어', section: '영어', group: '영어', kind: 'subject', questions: 45, max_points: 100 },
      { target: '한국사/한국사', subject: '한국사', section: '한국사', group: '한국사', kind: 'subject', questions: 20, max_points: 50 },
      { target: '탐구/물리1', subject: '물리1', section: '탐구', group: '탐구', kind: 'subject', questions: 20, max_points: 50 },
      { target: '탐구/화학1', subject: '화학1', section: '탐구', group: '탐구', kind: 'subject', questions: 20, max_points: 50 },
      { target: '탐구/생명1', subject: '생명1', section: '탐구', group: '탐구', kind: 'subject', questions: 20, max_points: 50 },
      { target: '탐구/사회문화', subject: '사회문화', section: '탐구', group: '탐구', kind: 'subject', questions: 20, max_points: 50 }
    ]
  }
}

/**
 * @brief 실제 결과 배열에서 현재 시험 정의 추론
 * @param {Array} data - all_results.json 배열
 * @return {Object} 추론한 시험 정의
 */
function _inferExamFromData(data) {
  if (!Array.isArray(data) || data.length === 0) {
    return _getLegacyExam()
  }

  const sectionMap = new Map()
  data.forEach(entry => {
    if (entry.subject == null || entry.section == null) return
    const key = `${entry.subject}\u0000${entry.section}`
    if (sectionMap.has(key)) return

    const group = entry.section === '탐구' ? '탐구' : entry.subject
    const kind = (group === '국어' || group === '수학')
      ? (entry.section === '공통' ? 'common' : 'elective')
      : 'subject'
    const target = group === '탐구'
      ? `${group}/${entry.subject}`
      : `${group}/${entry.section}`

    sectionMap.set(key, {
      target,
      subject: entry.subject,
      section: entry.section,
      group,
      kind,
      questions: entry.total_questions ?? 0,
      max_points: entry.total_points ?? 0
    })
  })

  if (sectionMap.size === 0) return _getLegacyExam()
  return {
    id: 'inferred-exam',
    title: '추론된 시험',
    sections: [...sectionMap.values()]
  }
}

/**
 * @brief 시험 정의 해석
 * @param {Array} data - 결과 배열
 * @param {Object|null} exam - 명시적 시험 정의
 * @return {Object} 사용할 시험 정의
 */
function _resolveExam(data, exam) {
  return exam ?? _inferExamFromData(data)
}

/**
 * @brief 시험 정의의 섹션을 그룹별로 묶음
 * @param {Object} exam - 시험 정의
 * @return {Array} 그룹별 섹션 배열
 */
function _groupSections(exam) {
  const groups = new Map()
  exam.sections.forEach(section => {
    const group = section.group
    if (!groups.has(group)) groups.set(group, [])
    groups.get(group).push(section)
  })
  return [...groups.entries()].map(([group, sections]) => ({ group, sections }))
}

/**
 * @brief 섹션의 기존 필터 키 생성
 * @param {Object} section - 시험 섹션
 * @return {string} 기존 과목 필터 키
 */
function _getLegacySectionKey(section) {
  const child = section.group === '탐구' ? section.subject : section.section
  return `${section.group}-${child}`
}

/**
 * @brief 섹션에 대응하는 필터 키 목록 생성
 * @param {Object} section - 시험 섹션
 * @return {Set<string>} 필터 키 집합
 */
function _getSectionFilterKeys(section) {
  const legacyShortName = Object.entries(LEGACY_NAME_MAP)
    .find(([, fullName]) => fullName === section.subject)?.[0]
  return new Set([
    section.group,
    section.target,
    _getLegacySectionKey(section),
    `${section.group}/${section.section}`,
    `${section.subject}-${section.section}`,
    legacyShortName ? `${section.group}-${legacyShortName}` : null
  ].filter(Boolean))
}

/**
 * @brief 필터에 해당하는 섹션 목록 선택
 * @param {Array} sections - 시험 섹션 배열
 * @param {Array} subjectFilter - 과목 필터 배열
 * @return {Array} 중복 제거된 선택 섹션 배열
 */
function _selectSections(sections, subjectFilter) {
  if (!subjectFilter || subjectFilter.length === 0) return sections

  const selected = new Set()
  sections.forEach((section, index) => {
    const keys = _getSectionFilterKeys(section)
    if (subjectFilter.some(filter => keys.has(filter))) selected.add(index)
  })

  // 선택 과목만 고른 경우에도 공통 섹션은 한 번만 포함한다.
  sections.forEach((section, index) => {
    if (!selected.has(index) || section.kind !== 'elective') return
    sections.forEach((candidate, candidateIndex) => {
      if (candidate.group === section.group && candidate.kind === 'common') {
        selected.add(candidateIndex)
      }
    })
  })

  return sections.filter((_, index) => selected.has(index))
}

/**
 * @brief 섹션 점수 레코드 생성
 * @param {Array} modelData - 모델별 결과 배열
 * @param {Object} section - 시험 섹션
 * @return {Object} 섹션 점수 레코드
 */
function _createSectionScore(modelData, section) {
  const entry = modelData.find(d => d.subject === section.subject && d.section === section.section)
  return {
    target: section.target,
    subject: section.subject,
    section: section.section,
    group: section.group,
    kind: section.kind,
    name: section.group === '탐구' ? section.subject : section.section,
    score: entry?.score ?? 0,
    maxScore: section.max_points,
    available: Boolean(entry)
  }
}

/**
 * @brief 그룹 섹션의 점수와 만점 계산
 * @param {Object} groupInfo - { group, sections }
 * @param {Array} sectionScores - 섹션 점수 배열
 * @param {string} scoreBasis - normalized 또는 raw
 * @return {Object} 그룹 상세 점수
 */
function _calculateGroupDetail(groupInfo, sectionScores, scoreBasis) {
  const commonSections = sectionScores.filter(section => section.kind === 'common')
  const electiveSections = sectionScores.filter(section => section.kind === 'elective')
  const subjectSections = sectionScores.filter(section => section.kind === 'subject')
  const common = commonSections.reduce((sum, section) => sum + section.score, 0)
  const commonMax = commonSections.reduce((sum, section) => sum + section.maxScore, 0)
  const electiveSum = electiveSections.reduce((sum, section) => sum + section.score, 0)
  const electiveMaxSum = electiveSections.reduce((sum, section) => sum + section.maxScore, 0)
  const electiveAvg = electiveSections.length > 0 ? electiveSum / electiveSections.length : 0
  const electiveAvgMax = electiveSections.length > 0 ? electiveMaxSum / electiveSections.length : 0
  const subjectSum = subjectSections.reduce((sum, section) => sum + section.score, 0)
  const subjectMaxSum = subjectSections.reduce((sum, section) => sum + section.maxScore, 0)
  const explorationAverage = subjectSections.length > 0 ? subjectSum / subjectSections.length : 0
  const explorationAverageMax = subjectSections.length > 0 ? subjectMaxSum / subjectSections.length : 0

  let normalizedTotal
  let normalizedMax
  if (groupInfo.group === '탐구') {
    normalizedTotal = explorationAverage * 2
    normalizedMax = explorationAverageMax * 2
  } else if (commonSections.length > 0 || electiveSections.length > 0) {
    normalizedTotal = common + electiveAvg
    normalizedMax = commonMax + electiveAvgMax
  } else {
    normalizedTotal = subjectSum
    normalizedMax = subjectMaxSum
  }

  const rawTotal = sectionScores.reduce((sum, section) => sum + section.score, 0)
  const rawMax = sectionScores.reduce((sum, section) => sum + section.maxScore, 0)
  const total = scoreBasis === SCORE_BASIS.RAW ? rawTotal : normalizedTotal
  const maxScore = scoreBasis === SCORE_BASIS.RAW ? rawMax : normalizedMax

  return {
    group: groupInfo.group,
    total,
    maxScore,
    normalizedTotal,
    normalizedMaxScore: normalizedMax,
    rawTotal,
    rawMaxScore: rawMax,
    common,
    commonMaxScore: commonMax,
    electives: electiveSections,
    electiveAvg,
    electiveAvgMaxScore: electiveAvgMax,
    subjects: subjectSections,
    average: explorationAverage,
    averageMaxScore: explorationAverageMax,
    sections: sectionScores
  }
}

/**
 * @brief 선택 섹션들의 그룹별 점수 계산
 * @param {Object} exam - 시험 정의
 * @param {Array} sectionScores - 전체 섹션 점수 배열
 * @param {Array} selectedSections - 선택 섹션 정의 배열
 * @param {string} scoreBasis - 점수 기준
 * @return {Object} { details, total, maxScore }
 */
function _calculateSelectedGroups(exam, sectionScores, selectedSections, scoreBasis) {
  const selectedTargets = new Set(selectedSections.map(section => section.target))
  const details = _groupSections(exam)
    .map(groupInfo => {
      const selectedScores = sectionScores.filter(score =>
        score.group === groupInfo.group && selectedTargets.has(score.target)
      )
      return _calculateGroupDetail(groupInfo, selectedScores, scoreBasis)
    })
    .filter(detail => detail.sections.length > 0)

  return {
    details,
    total: details.reduce((sum, detail) => sum + detail.total, 0),
    maxScore: details.reduce((sum, detail) => sum + detail.maxScore, 0)
  }
}

/**
 * @brief 점수 객체에서 지정 기준의 전체 점수 추출
 * @param {Object} score - 종합 점수 객체
 * @param {string} scoreBasis - 점수 기준
 * @return {number} 지정 기준 총점
 */
function _getScoreTotalForBasis(score, scoreBasis) {
  if (score.scoreBasis === scoreBasis) return score.total
  const exam = score.exam
  if (!exam || !score.sectionScores) return score.total
  return _calculateSelectedGroups(
    exam,
    score.sectionScores,
    exam.sections,
    scoreBasis
  ).total
}

/**
 * @brief 시험 정의의 그룹별 필터·만점 정보 생성
 * @param {Object|null} exam - 시험 정의
 * @param {Array} data - 시험 정의가 없을 때 사용할 결과 배열
 * @return {Array} 그룹·하위 섹션·정규화/원점수 만점 정보
 */
export function getSubjectFilterGroups(exam = null, data = []) {
  const resolvedExam = _resolveExam(data, exam)
  return _groupSections(resolvedExam).map(groupInfo => {
    const allScores = groupInfo.sections.map(section => ({
      target: section.target,
      subject: section.subject,
      section: section.section,
      group: section.group,
      kind: section.kind,
      name: section.group === '탐구' ? section.subject : section.section,
      score: 0,
      maxScore: section.max_points,
      available: true
    }))
    const detail = _calculateGroupDetail(groupInfo, allScores, SCORE_BASIS.NORMALIZED)
    const rawDetail = _calculateGroupDetail(groupInfo, allScores, SCORE_BASIS.RAW)
    const children = groupInfo.sections
      .filter(section => section.kind !== 'common')
      .map(section => {
        const normalizedKey = section.target
        const childMaxNormalized = _calculateSelectedGroups(
          resolvedExam,
          allScores,
          _selectSections(resolvedExam.sections, [normalizedKey]),
          SCORE_BASIS.NORMALIZED
        ).maxScore
        const childMaxRaw = _calculateSelectedGroups(
          resolvedExam,
          allScores,
          _selectSections(resolvedExam.sections, [normalizedKey]),
          SCORE_BASIS.RAW
        ).maxScore
        return {
          key: normalizedKey,
          target: normalizedKey,
          legacyKey: _getLegacySectionKey(section),
          name: section.group === '탐구' ? section.subject : section.section,
          subject: section.subject,
          section: section.section,
          kind: section.kind,
          max_points: section.max_points,
          maxScores: {
            normalized: childMaxNormalized,
            raw: childMaxRaw
          },
          maxScore: childMaxNormalized
        }
      })

    return {
      group: groupInfo.group,
      name: groupInfo.group,
      key: groupInfo.group,
      sections: groupInfo.sections,
      children,
      maxScores: {
        normalized: detail.normalizedMaxScore,
        raw: rawDetail.rawMaxScore
      },
      maxScore: detail.normalizedMaxScore
    }
  })
}

/**
 * @brief 시험 정의의 전체 만점 계산
 * @param {Object} exam - 시험 정의
 * @param {Array} subjectFilter - 과목 필터
 * @param {string} scoreBasis - 점수 기준
 * @return {number} 필터 만점
 */
function _calculateMaxFromExam(exam, subjectFilter, scoreBasis) {
  const selectedSections = _selectSections(exam.sections, subjectFilter)
  const zeroScores = selectedSections.map(section => ({
    target: section.target,
    subject: section.subject,
    section: section.section,
    group: section.group,
    kind: section.kind,
    name: section.group === '탐구' ? section.subject : section.section,
    score: 0,
    maxScore: section.max_points,
    available: true
  }))
  return _calculateSelectedGroups(exam, zeroScores, selectedSections, scoreBasis).maxScore
}

/**
 * @brief 과목 필터에 따른 만점 계산
 * @param {Array|Object} subjectFilter - 과목 필터 배열 또는 { exam, scoreBasis, subjectFilter }
 * @param {Object} options - { exam, scoreBasis }
 * @return {number} 만점
 */
export function getMaxScore(subjectFilter = [], options = {}) {
  const args = _resolveFilterArgs(subjectFilter, options)
  const resolvedOptions = _normalizeOptions(args.options)
  const exam = _resolveExam([], resolvedOptions.exam)
  return _calculateMaxFromExam(exam, args.subjectFilter, resolvedOptions.scoreBasis)
}

/**
 * @brief 모델의 전체 점수 계산
 * @param {Array} data - all_results.json 배열
 * @param {string} modelName - 모델명
 * @param {Object} options - { exam, scoreBasis, subjectFilter }
 * @return {Object} 과목별 점수와 만점·섹션 상세
 */
export function calculateOverallScore(data, modelName, options = {}) {
  const resolvedOptions = _normalizeOptions(options)
  const exam = _resolveExam(data, resolvedOptions.exam)
  const modelData = getModelData(data, modelName)
  const sectionScores = exam.sections.map(section => _createSectionScore(modelData, section))
  const allSelected = _calculateSelectedGroups(exam, sectionScores, exam.sections, resolvedOptions.scoreBasis)
  const filter = options.subjectFilter ?? []
  const selectedSections = _selectSections(exam.sections, filter)
  const selected = filter.length > 0
    ? _calculateSelectedGroups(exam, sectionScores, selectedSections, resolvedOptions.scoreBasis)
    : allSelected
  const detailsByGroup = new Map(allSelected.details.map(detail => [detail.group, detail]))
  const groupMaxScores = {}
  const groupDetails = allSelected.details.map(detail => {
    groupMaxScores[detail.group] = {
      normalized: detail.normalizedMaxScore,
      raw: detail.rawMaxScore
    }
    return detail
  })

  return {
    model: modelName,
    scoreBasis: resolvedOptions.scoreBasis,
    maxScore: filter.length > 0 ? selected.maxScore : allSelected.maxScore,
    korean: detailsByGroup.get('국어')?.total ?? 0,
    koreanDetail: detailsByGroup.get('국어') ?? null,
    math: detailsByGroup.get('수학')?.total ?? 0,
    mathDetail: detailsByGroup.get('수학') ?? null,
    english: detailsByGroup.get('영어')?.total ?? 0,
    englishDetail: detailsByGroup.get('영어') ?? null,
    history: detailsByGroup.get('한국사')?.total ?? 0,
    historyDetail: detailsByGroup.get('한국사') ?? null,
    exploration: detailsByGroup.get('탐구')?.total ?? 0,
    explorationDetail: detailsByGroup.get('탐구') ?? null,
    groupDetails,
    groupMaxScores,
    sectionScores,
    exam,
    total: selected.total
  }
}

/**
 * @brief 모델별 전체 점수 계산
 * @param {Array} data - all_results.json 배열
 * @param {Array} models - 모델명 배열
 * @param {Array|Object} subjectFilter - 과목 필터 또는 옵션
 * @param {Object} options - { exam, scoreBasis }
 * @return {Array} 총점 내림차순 모델 점수 배열
 */
export function calculateAllModelScores(data, models, subjectFilter = [], options = {}) {
  const args = _resolveFilterArgs(subjectFilter, options)
  const resolvedOptions = _normalizeOptions(args.options)
  const scores = models.map(model => {
    const score = calculateOverallScore(data, model, resolvedOptions)
    if (args.subjectFilter.length > 0) {
      score.total = getFilteredTotal(score, args.subjectFilter, resolvedOptions)
      score.maxScore = getMaxScore(args.subjectFilter, resolvedOptions)
    }
    score.subjectFilter = args.subjectFilter
    return score
  })

  return scores.sort((a, b) => b.total - a.total)
}

/**
 * @brief 모델 점수 객체에서 필터 총점 계산
 * @param {Object} scoreObj - calculateOverallScore 결과
 * @param {Array|Object} subjectFilter - 과목 필터 또는 옵션
 * @param {Object} options - { exam, scoreBasis }
 * @return {number} 필터 총점
 */
export function getFilteredTotal(scoreObj, subjectFilter = [], options = {}) {
  const args = _resolveFilterArgs(subjectFilter, options)
  const resolvedOptions = _normalizeOptions({
    exam: args.options.exam ?? scoreObj.exam,
    scoreBasis: args.options.scoreBasis ?? scoreObj.scoreBasis
  })
  const exam = _resolveExam([], resolvedOptions.exam)
  if (args.subjectFilter.length === 0) return scoreObj.total

  const sectionScores = scoreObj.sectionScores ?? []
  if (sectionScores.length === 0) return 0
  const selectedSections = _selectSections(exam.sections, args.subjectFilter)
  return _calculateSelectedGroups(
    exam,
    sectionScores,
    selectedSections,
    resolvedOptions.scoreBasis
  ).total
}

/**
 * @brief 특정 과목·섹션의 점수 데이터 추출
 * @param {Array} data - all_results.json 배열
 * @param {string} subject - 과목명
 * @param {string} section - 섹션명
 * @return {Array} 차트용 점수 배열
 */
export function getSubjectScores(data, subject, section) {
  return data
    .filter(d => d.subject === subject && d.section === section)
    .map(d => ({
      model: d.model_name,
      score: d.score,
      totalPoints: d.total_points
    }))
    .sort((a, b) => b.score - a.score)
}

/**
 * @brief 최고·최저 선택 조합 점수 계산
 * @param {Array} data - all_results.json 배열
 * @param {Array} models - 모델명 배열
 * @param {Object} options - { exam }
 * @return {Array} [{ model, best, worst, scoreBasis, maxScore }]
 */
export function calculateBestWorstScores(data, models, options = {}) {
  const resolvedOptions = _normalizeOptions({ ...options, scoreBasis: SCORE_BASIS.NORMALIZED })
  const exam = _resolveExam(data, resolvedOptions.exam)
  const maxScore = _calculateMaxFromExam(exam, [], SCORE_BASIS.NORMALIZED)

  return models
    .map(model => {
      const modelData = getModelData(data, model)
      const sectionScores = exam.sections.map(section => _createSectionScore(modelData, section))
      let best = 0
      let worst = 0

      _groupSections(exam).forEach(groupInfo => {
        const groupScores = sectionScores.filter(score => score.group === groupInfo.group)
        const common = groupScores
          .filter(score => score.kind === 'common')
          .reduce((sum, score) => sum + score.score, 0)
        const electives = groupScores.filter(score => score.kind === 'elective').map(score => score.score)
        const subjects = groupScores.filter(score => score.kind === 'subject').map(score => score.score)

        if (groupInfo.group === '탐구') {
          if (subjects.length >= 2) {
            const combinations = []
            for (let i = 0; i < subjects.length; i++) {
              for (let j = i + 1; j < subjects.length; j++) {
                combinations.push(subjects[i] + subjects[j])
              }
            }
            best += Math.max(...combinations)
            worst += Math.min(...combinations)
          } else if (subjects.length === 1) {
            best += subjects[0] * 2
            worst += subjects[0] * 2
          }
          return
        }

        if (electives.length > 0 || groupScores.some(score => score.kind === 'common')) {
          best += common + (electives.length > 0 ? Math.max(...electives) : 0)
          worst += common + (electives.length > 0 ? Math.min(...electives) : 0)
          return
        }

        const subjectTotal = subjects.reduce((sum, score) => sum + score, 0)
        best += subjectTotal
        worst += subjectTotal
      })

      return {
        model,
        best,
        worst,
        scoreBasis: SCORE_BASIS.NORMALIZED,
        maxScore
      }
    })
    .sort((a, b) => b.best - a.best)
}

/**
 * @brief 이미지 포함 여부별 득점률 계산
 * @param {Array} data - all_results.json 배열
 * @param {Object} questionsMetadata - 문제 메타데이터
 * @param {Array} models - 모델명 배열
 * @param {boolean} hasImage - 이미지 포함 여부
 * @return {Array} 모델별 득점률 배열
 */
export function calculateImageBasedScores(data, questionsMetadata, models, hasImage) {
  if (!questionsMetadata || Object.keys(questionsMetadata).length === 0) return []

  const modelStats = {}
  models.forEach(model => {
    modelStats[model] = { totalScore: 0, totalMax: 0 }
  })

  Object.entries(questionsMetadata).forEach(([key, questions]) => {
    const [subject, section] = key.split('-')
    const filteredQuestions = Object.entries(questions).filter(([, question]) =>
      hasImage ? question.hasImage : !question.hasImage
    )
    if (filteredQuestions.length === 0) return

    const maxScore = filteredQuestions.reduce((sum, [, question]) => sum + (question.points || 0), 0)
    if (maxScore === 0) return

    models.forEach(model => {
      const modelSectionData = data.find(d =>
        d.model_name === model && d.subject === subject && d.section === section
      )
      if (!modelSectionData?.results) return

      let score = 0
      filteredQuestions.forEach(([questionNumber, question]) => {
        const result = modelSectionData.results.find(item =>
          item.question_number === parseInt(questionNumber)
        )
        if (result?.is_correct) score += question.points || 0
      })
      modelStats[model].totalScore += score
      modelStats[model].totalMax += maxScore
    })
  })

  return Object.entries(modelStats)
    .map(([model, stats]) => ({
      model,
      rate: stats.totalMax > 0 ? (stats.totalScore / stats.totalMax) * 100 : 0,
      score: stats.totalScore,
      maxScore: stats.totalMax
    }))
    .filter(item => item.maxScore > 0)
    .sort((a, b) => b.rate - a.rate)
}

/**
 * @brief 사용량 섹션 키 별칭 생성
 * @param {Object} section - 시험 섹션
 * @return {Array} 토큰 사용량 키 별칭
 */
function _getUsageSectionAliases(section) {
  return [
    section.target,
    _getLegacySectionKey(section),
    `${section.subject}-${section.section}`,
    `${section.group}-공통`,
    section.group === section.subject ? section.subject : null,
    section.section === section.subject ? section.section : null
  ].filter(Boolean)
}

/**
 * @brief 여러 회차 사용량인지 판별
 * @param {Object} usage - 모델별 토큰 사용량
 * @return {boolean} 여러 회차 사용량 여부
 */
function _isRepeatedUsage(usage) {
  return usage.attempts > 1
}

/**
 * @brief 사용량 값을 합산하고 현대 형식의 미상 값을 보존
 * @param {Array} values - 합산할 토큰 값
 * @param {boolean} preserveUnknown - null·undefined를 미상으로 보존할지 여부
 * @return {number|null} 합계 또는 미상
 */
function _sumUsageValues(values, preserveUnknown) {
  if (!preserveUnknown) return values.reduce((sum, value) => sum + (value || 0), 0)
  if (values.length === 0 || values.some(value => value === null || value === undefined)) return null
  return values.reduce((sum, value) => sum + value, 0)
}

/**
 * @brief 토큰 수와 단가로 비용 계산
 * @param {number|null} tokens - 토큰 수
 * @param {number|null} price - 백만 토큰당 단가
 * @param {boolean} preserveUnknown - 미상 값을 보존할지 여부
 * @return {number|null} 비용 또는 미상
 */
function _calculateTokenCost(tokens, price, preserveUnknown) {
  if (preserveUnknown) {
    if (tokens === null || tokens === undefined || price === null || price === undefined) return null
    if (tokens === 0) return 0
  }
  return tokens * (price / 1000000)
}

/**
 * @brief 필터된 토큰 사용량 계산
 * @param {Object} usage - 모델별 토큰 사용량
 * @param {Object} exam - 시험 정의
 * @param {Array} subjectFilter - 과목 필터
 * @return {Object} input/output 토큰과 선택 키
 */
function _getFilteredUsage(usage, exam, subjectFilter) {
  const preserveUnknown = _isRepeatedUsage(usage)
  if (!subjectFilter || subjectFilter.length === 0) {
    return {
      inputTokens: preserveUnknown
        ? (usage.total_input_tokens ?? null)
        : (usage.total_input_tokens || 0),
      outputTokens: preserveUnknown
        ? (usage.total_output_tokens ?? null)
        : (usage.total_output_tokens || 0),
      sectionKeys: [],
      attemptDetails: usage.attempt_details,
      attemptTotals: usage.attempt_totals
    }
  }

  if (!usage.sections) {
    return {
      inputTokens: preserveUnknown ? null : 0,
      outputTokens: preserveUnknown ? null : 0,
      sectionKeys: [],
      attemptDetails: usage.attempt_details,
      attemptTotals: usage.attempt_totals
    }
  }

  const selectedSections = _selectSections(exam.sections, subjectFilter)
  const aliases = new Set(selectedSections.flatMap(_getUsageSectionAliases))
  const sectionKeys = []
  const selectedUsage = Object.entries(usage.sections).filter(([key]) => aliases.has(key))
  selectedUsage.forEach(([key]) => sectionKeys.push(key))
  const inputTokens = _sumUsageValues(
    selectedUsage.map(([, section]) => section.input_tokens),
    preserveUnknown
  )
  const outputTokens = _sumUsageValues(
    selectedUsage.map(([, section]) => section.output_tokens),
    preserveUnknown
  )

  return {
    inputTokens,
    outputTokens,
    sectionKeys,
    attemptDetails: usage.attempt_details,
    attemptTotals: usage.attempt_totals
  }
}

/**
 * @brief 선택 범위의 토큰 합계가 완전한지 확인
 * @param {Object} usage - 모델별 토큰 사용량
 * @param {Object} exam - 시험 정의
 * @param {Array} subjectFilter - 과목 필터
 * @param {Object} filteredUsage - 필터된 사용량
 * @return {Object} 입력·출력 토큰 합계 또는 미상
 */
function _getKnownPerformanceTokens(usage, exam, subjectFilter, filteredUsage) {
  if (!subjectFilter || subjectFilter.length === 0) {
    const inputTokens = typeof usage.total_input_tokens === 'number' && Number.isFinite(usage.total_input_tokens)
      ? usage.total_input_tokens
      : null
    const outputTokens = typeof usage.total_output_tokens === 'number' && Number.isFinite(usage.total_output_tokens)
      ? usage.total_output_tokens
      : null
    return { inputTokens, outputTokens }
  }

  if (!usage.sections || filteredUsage.sectionKeys.length === 0) {
    return { inputTokens: null, outputTokens: null }
  }

  const selectedSections = _selectSections(exam.sections, subjectFilter)
  const selectedKeys = new Set(filteredUsage.sectionKeys)
  const aggregateGroups = new Set(
    selectedSections
      .map(section => section.group)
      .filter(group => selectedKeys.has(group))
  )
  const complete = selectedSections.every(section => {
    if (aggregateGroups.has(section.group)) return true
    const hasCommonSection = exam.sections.some(candidate =>
      candidate.group === section.group && candidate.kind === 'common'
    )
    return _getUsageSectionAliases(section)
      .filter(key => key !== `${section.group}-공통` || section.kind === 'common' || !hasCommonSection)
      .some(key => selectedKeys.has(key))
  })
  if (!complete) return { inputTokens: null, outputTokens: null }
  const selectedEntries = Object.entries(usage.sections)
    .filter(([key]) => selectedKeys.has(key))
  const inputTokens = selectedEntries.every(([, section]) => Number.isFinite(section.input_tokens))
    ? filteredUsage.inputTokens
    : null
  const outputTokens = selectedEntries.every(([, section]) => Number.isFinite(section.output_tokens))
    ? filteredUsage.outputTokens
    : null
  return { inputTokens, outputTokens }
}

/**
 * @brief 토큰 사용량과 현재 처리량으로 예상 소요 시간 계산
 * @param {Object} usage - 모델별 토큰 사용량
 * @param {Object} exam - 시험 정의
 * @param {Array} subjectFilter - 과목 필터
 * @param {Object} filteredUsage - 필터된 사용량
 * @param {Object|null} modelPerformance - 모델별 처리량 스냅샷
 * @param {string} model - 모델 표시명
 * @return {Object} 시간·토큰·처리량 지표
 */
function _getPerformanceMetrics(usage, exam, subjectFilter, filteredUsage, modelPerformance, model) {
  const tokens = _getKnownPerformanceTokens(usage, exam, subjectFilter, filteredUsage)
  const totalTokens = tokens.inputTokens !== null && tokens.outputTokens !== null
    ? tokens.inputTokens + tokens.outputTokens
    : null
  const performance = modelPerformance?.models?.[model] ?? null
  const tokensPerSecond = typeof performance?.tokensPerSecond === 'number' &&
      Number.isFinite(performance.tokensPerSecond) && performance.tokensPerSecond > 0
    ? performance.tokensPerSecond
    : null
  const estimatedSeconds = tokens.outputTokens !== null && tokensPerSecond !== null
    ? tokens.outputTokens / tokensPerSecond
    : null
  const provider = typeof performance?.selection?.provider === 'string'
    ? performance.selection.provider
    : null

  return {
    totalTokens,
    estimatedSeconds,
    tokensPerSecond,
    provider,
    performance
  }
}

/**
 * @brief 실제 토큰 사용량 기반 비용·효율성 계산
 * @param {Array} data - all_results.json 배열
 * @param {Array} overallScores - calculateAllModelScores 결과
 * @param {Object} tokenUsage - 모델별 토큰 사용량
 * @param {Array|Object} subjectFilter - 과목 필터 또는 옵션
 * @param {Object} options - { exam, scoreBasis }
 * @return {Array} 비용·효율성 데이터
 */
export function getCostData(data, overallScores, tokenUsage = {}, subjectFilter = [], options = {}) {
  const args = _resolveFilterArgs(subjectFilter, options)
  const inferredBasis = overallScores[0]?.scoreBasis
  const resolvedOptions = _normalizeOptions({
    ...args.options,
    scoreBasis: args.options.scoreBasis ?? inferredBasis
  })
  const exam = _resolveExam(data, resolvedOptions.exam)
  const priceMap = {}
  data.forEach(entry => {
    if (!priceMap[entry.model_name] && entry.price) {
      priceMap[entry.model_name] = {
        input: entry.price.input,
        output: entry.price.output
      }
    }
  })

  const results = overallScores.map(score => {
    const usage = tokenUsage[score.model] || {}
    const preserveUnknown = _isRepeatedUsage(usage)
    const storedPrice = priceMap[score.model]
    const price = preserveUnknown
      ? {
        input: storedPrice?.input ?? null,
        output: storedPrice?.output ?? null
      }
      : {
        input: storedPrice?.input ?? 0,
        output: storedPrice?.output ?? 0
      }
    const filteredUsage = _getFilteredUsage(usage, exam, args.subjectFilter)
    const inputCostActual = _calculateTokenCost(filteredUsage.inputTokens, price.input, preserveUnknown)
    const outputCostActual = _calculateTokenCost(filteredUsage.outputTokens, price.output, preserveUnknown)
    const totalCost = preserveUnknown && (inputCostActual === null || outputCostActual === null)
      ? null
      : inputCostActual + outputCostActual
    const scoreValue = args.subjectFilter.length > 0
      ? getFilteredTotal(score, args.subjectFilter, resolvedOptions)
      : _getScoreTotalForBasis(score, resolvedOptions.scoreBasis)
    const performanceMetrics = _getPerformanceMetrics(
      usage,
      exam,
      args.subjectFilter,
      filteredUsage,
      resolvedOptions.modelPerformance,
      score.model
    )

    return {
      model: score.model,
      score: scoreValue,
      maxScore: getMaxScore(args.subjectFilter, resolvedOptions),
      scoreBasis: resolvedOptions.scoreBasis,
      inputPrice: price.input,
      outputPrice: price.output,
      inputTokens: filteredUsage.inputTokens,
      outputTokens: filteredUsage.outputTokens,
      totalCost,
      tokenUsage: usage,
      tokenSectionKeys: filteredUsage.sectionKeys,
      attempts: usage.attempts,
      attemptDetails: filteredUsage.attemptDetails,
      attemptTotals: filteredUsage.attemptTotals,
      ...performanceMetrics
    }
  })

  const maxCost = Math.max(...results.map(result => result.totalCost).filter(cost => cost > 0), 1)
  const scoreMax = getMaxScore(args.subjectFilter, resolvedOptions)
  return results.map(result => {
    if (result.totalCost <= 0) return { ...result, efficiency: 0 }

    const scoreNorm = scoreMax > 0
      ? Math.max(0, Math.min(1, result.score / scoreMax))
      : 0
    const costNorm = result.totalCost / maxCost
    const efficiency = (scoreNorm * 0.7 + (1 - costNorm) * 0.3) * 100
    return { ...result, efficiency }
  })
}
