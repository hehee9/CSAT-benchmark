import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true }
})

try {
  const { formatPublishedDate } = await server.ssrLoadModule('/src/utils/modelMeta.js')

  // 출시일은 일 단위, 지식 컷오프와 시험 월은 월 단위까지만 표시
  assert.equal(formatPublishedDate('2026-03-05', 'ko-KR'), '2026년 3월 5일')
  assert.equal(formatPublishedDate('2026-03-05', 'en-US'), 'March 5, 2026')
  assert.equal(formatPublishedDate('2025-11', 'ko-KR'), '2025년 11월')
  assert.equal(formatPublishedDate('2025-11', 'en-US'), 'November 2025')

  // 시간대와 무관하게 월 경계 날짜가 바뀌지 않음
  assert.equal(formatPublishedDate('2026-01-01', 'en-US'), 'January 1, 2026')
  assert.equal(formatPublishedDate('2025-12', 'en-US'), 'December 2025')

  // 값이 없으면 null (화면에서는 '공개되지 않음'), 알 수 없는 형식은 원문 유지
  assert.equal(formatPublishedDate(undefined, 'ko-KR'), null)
  assert.equal(formatPublishedDate(null, 'ko-KR'), null)
  assert.equal(formatPublishedDate('', 'ko-KR'), null)
  assert.equal(formatPublishedDate('2026 Q1', 'ko-KR'), '2026 Q1')
} finally {
  await server.close()
}

console.log('model-info: published-date precision passed')

