/**
 * @file trendTransform.js
 * @brief 출시일 기준 성적 변화 추이 데이터 변환 유틸리티
 */

import { getVendor } from './colorUtils'

const RELEASE_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const MONTH_TICK_STEPS = [1, 2, 3, 4, 6, 12, 24]

/**
 * @brief YYYY-MM-DD 출시일 문자열을 UTC 자정 타임스탬프로 변환
 * @param {*} value - 출시일 값
 * @return {number|null} 유효한 날짜면 UTC 타임스탬프, 아니면 null
 */
export function parseReleaseDate(value) {
  if (typeof value !== 'string') return null
  const match = RELEASE_DATE_PATTERN.exec(value)
  if (!match) return null

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const time = Date.UTC(year, month - 1, day)
  const date = new Date(time)
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return null
  }
  return time
}

/**
 * @brief 모델 점수와 메타데이터를 출시일 산점도 좌표로 변환
 * @param {Array<{model: string, total: number}>} scores - calculateAllModelScores 결과
 * @param {Object} modelMetadata - 모델명별 메타데이터 (releaseDate 포함)
 * @return {{points: Array<Object>, excludedCount: number}} 출시일 오름차순 좌표와 제외 모델 수
 */
export function buildTrendPoints(scores = [], modelMetadata = {}) {
  const points = []
  let excludedCount = 0

  scores.forEach(({ model, total }) => {
    const releaseDate = modelMetadata?.[model]?.releaseDate
    const time = parseReleaseDate(releaseDate)
    if (time === null || !Number.isFinite(total)) {
      excludedCount += 1
      return
    }
    points.push({
      model,
      vendorId: getVendor(model).id,
      releaseDate,
      time,
      score: total
    })
  })

  points.sort((a, b) => a.time - b.time || b.score - a.score || a.model.localeCompare(b.model))
  return { points, excludedCount }
}

/**
 * @brief 개발사별 누적 최고 점수 계단선 계산
 * @param {Array<{vendorId: string, time: number, score: number}>} points - buildTrendPoints 결과
 * @return {Object<string, Array<{time: number, score: number}>>} 개발사 ID별 계단선 꼭짓점
 *
 * 같은 날짜의 모델은 그날의 최고 점수 하나로 합치고, 최고 점수가 갱신된 날짜에만 꼭짓점을 둔다.
 * 계단선은 마지막 최고 점수 갱신 꼭짓점에서 끝난다.
 */
export function buildVendorStepLines(points = []) {
  const dailyBestByVendor = new Map()

  points.forEach(({ vendorId, time, score }) => {
    if (!dailyBestByVendor.has(vendorId)) dailyBestByVendor.set(vendorId, new Map())
    const dailyBest = dailyBestByVendor.get(vendorId)
    dailyBest.set(time, Math.max(dailyBest.get(time) ?? -Infinity, score))
  })

  const lines = {}
  dailyBestByVendor.forEach((dailyBest, vendorId) => {
    const vertices = []
    let runningBest = -Infinity

    Array.from(dailyBest.entries())
      .sort(([firstTime], [secondTime]) => firstTime - secondTime)
      .forEach(([time, score]) => {
        if (score <= runningBest) return
        runningBest = score
        vertices.push({ time, score })
      })
    lines[vendorId] = vertices
  })

  return lines
}

/**
 * @brief 출시 시점에 개발사 최고 점수를 새로 세운 모델 집합 계산
 * @param {Array<{model: string, vendorId: string, time: number, score: number}>} points - 출시일 오름차순 좌표
 * @return {Set<string>} 최고 점수 갱신 모델명
 *
 * 같은 날짜에 같은 개발사의 최고 점수 모델이 여러 개면 모두 포함한다.
 */
export function getFrontierModels(points = []) {
  const runningBestByVendor = new Map()
  const frontierModels = new Set()
  let index = 0

  while (index < points.length) {
    const time = points[index].time
    const sameDayPoints = []
    while (index < points.length && points[index].time === time) {
      sameDayPoints.push(points[index])
      index += 1
    }

    const dayBestByVendor = new Map()
    sameDayPoints.forEach(({ vendorId, score }) => {
      dayBestByVendor.set(vendorId, Math.max(dayBestByVendor.get(vendorId) ?? -Infinity, score))
    })
    sameDayPoints.forEach(({ model, vendorId, score }) => {
      const previousBest = runningBestByVendor.get(vendorId) ?? -Infinity
      if (score === dayBestByVendor.get(vendorId) && score > previousBest) frontierModels.add(model)
    })
    dayBestByVendor.forEach((score, vendorId) => {
      runningBestByVendor.set(vendorId, Math.max(runningBestByVendor.get(vendorId) ?? -Infinity, score))
    })
  }

  return frontierModels
}

/**
 * @brief 시간 축에 표시할 월초 눈금 계산
 * @param {number} minTime - 축 시작 시각
 * @param {number} maxTime - 축 끝 시각
 * @param {number} maxTickCount - 최대 눈금 수
 * @return {number[]} 범위 안의 월초 UTC 타임스탬프
 */
export function getMonthTicks(minTime, maxTime, maxTickCount = 8) {
  if (!Number.isFinite(minTime) || !Number.isFinite(maxTime) || maxTime < minTime) return []

  const start = new Date(minTime)
  const end = new Date(maxTime)
  let firstMonthIndex = start.getUTCFullYear() * 12 + start.getUTCMonth()
  if (Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1) < minTime) firstMonthIndex += 1
  const lastMonthIndex = end.getUTCFullYear() * 12 + end.getUTCMonth()
  const monthCount = lastMonthIndex - firstMonthIndex + 1
  if (monthCount <= 0) return []

  const step = MONTH_TICK_STEPS.find(candidate => Math.ceil(monthCount / candidate) <= maxTickCount)
    ?? Math.ceil(monthCount / maxTickCount)
  const ticks = []
  for (let index = Math.ceil(firstMonthIndex / step) * step; index <= lastMonthIndex; index += step) {
    ticks.push(Date.UTC(Math.floor(index / 12), index % 12, 1))
  }
  return ticks
}
