import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { middlewareMode: true },
  optimizeDeps: { noDiscovery: true }
})

try {
  const { getCostData } = await server.ssrLoadModule('/src/utils/dataTransform.js')
  const {
    formatDiscountEndDate,
    getActivePriceDiscount,
    normalizePriceDiscount
  } = await server.ssrLoadModule('/src/utils/priceDiscount.js')

  const exam = {
    id: 'discount-test',
    title: '할인 시험',
    sections: [
      { target: '국어/공통', subject: '국어', section: '공통', group: '국어', kind: 'common', max_points: 100 }
    ]
  }
  const discount = { input: 2, output: 10, start: '2026-11-23', end: '2026-11-30' }
  const _row = (model, price) => ({
    subject: '국어',
    section: '공통',
    model_name: model,
    score: 100,
    total_points: 100,
    total_questions: 1,
    price,
    results: []
  })
  const data = [
    _row('할인 모델', { input: 4, output: 20, discount }),
    _row('할인 모델', { input: 9, output: 9, discount: { ...discount, input: 1 } }),
    _row('정가 모델', { input: 4, output: 20 }),
    _row('무효 모델', { input: 4, output: 20, discount: { ...discount, start: '2026-12-01' } })
  ]
  const scores = ['할인 모델', '정가 모델', '무효 모델'].map(model => ({ model, total: 100, scoreBasis: 'normalized', exam }))
  const usage = { total_input_tokens: 1000000, total_output_tokens: 100000 }
  const rows = getCostData(
    data,
    scores,
    { '할인 모델': usage, '정가 모델': usage, '무효 모델': usage },
    [],
    { exam }
  )
  const byModel = Object.fromEntries(rows.map(row => [row.model, row]))

  // 첫 가격 보유 결과의 할인 정보가 그대로 보존되고, 비용은 정가 기준 유지
  assert.deepEqual(byModel['할인 모델'].priceDiscount, discount)
  assert.equal(byModel['할인 모델'].inputPrice, 4)
  assert.equal(byModel['할인 모델'].outputPrice, 20)
  assert.ok(Math.abs(byModel['할인 모델'].totalCost - 6) < 1e-12)
  assert.equal(byModel['할인 모델'].totalCost, byModel['정가 모델'].totalCost)
  assert.equal(byModel['할인 모델'].efficiency, byModel['정가 모델'].efficiency)
  assert.equal(byModel['정가 모델'].priceDiscount, null)
  assert.equal(byModel['무효 모델'].priceDiscount, null)

  // 무효·누락 할인 데이터는 조용히 무시
  assert.equal(normalizePriceDiscount(undefined), null)
  assert.equal(normalizePriceDiscount('50%'), null)
  assert.equal(normalizePriceDiscount({ ...discount, input: '2' }), null)
  assert.equal(normalizePriceDiscount({ ...discount, output: -1 }), null)
  assert.equal(normalizePriceDiscount({ ...discount, output: Number.NaN }), null)
  assert.equal(normalizePriceDiscount({ ...discount, end: undefined }), null)
  assert.equal(normalizePriceDiscount({ ...discount, end: '2026-11-31' }), null)
  assert.equal(normalizePriceDiscount({ ...discount, start: '2026/11/23' }), null)
  assert.deepEqual(normalizePriceDiscount({ ...discount, note: 'extra' }), discount)

  // 시작일·종료일을 포함한 브라우저 현지 날짜 기준 적용 기간
  assert.equal(getActivePriceDiscount(discount, new Date(2026, 10, 22, 23, 59)), null)
  assert.equal(getActivePriceDiscount(discount, new Date(2026, 10, 23, 0, 0)), discount)
  assert.equal(getActivePriceDiscount(discount, new Date(2026, 10, 26, 12, 0)), discount)
  assert.equal(getActivePriceDiscount(discount, new Date(2026, 10, 30, 23, 59)), discount)
  assert.equal(getActivePriceDiscount(discount, new Date(2026, 11, 1, 0, 0)), null)
  assert.equal(getActivePriceDiscount(null, new Date(2026, 10, 26)), null)

  assert.equal(formatDiscountEndDate('2026-11-30'), '11/30')
  assert.equal(formatDiscountEndDate('2026-12-05'), '12/5')
} finally {
  await server.close()
}

console.log('price-discount: preservation, validation, and active window passed')
