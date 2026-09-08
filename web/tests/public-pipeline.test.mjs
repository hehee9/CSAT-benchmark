import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { copyDataFiles } from '../scripts/copy-data.mjs'

async function _writeJson(filePath, payload) {
  await mkdir(path.dirname(filePath), { recursive: true })
  await writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
}

function _manifest({ id, status = 'ready', publish = true, modes }) {
  return {
    schema_version: 1,
    id,
    title: `${id} 시험`,
    data_dir: `private/${id}/questions`,
    results_dir: `private/${id}/results`,
    status,
    publish,
    sections: [
      {
        target: '국어/공통',
        subject: '국어',
        section: '공통',
        group: '국어',
        kind: 'common',
        questions: 'questions.json',
        max_points: 2
      }
    ],
    modes
  }
}

async function _createFixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'csat-public-pipeline-'))
  const catalogDir = path.join(root, 'benchmarks')
  const webRoot = path.join(root, 'web')
  const outputDir = path.join(root, 'temporary-public')
  await mkdir(catalogDir, { recursive: true })
  await mkdir(webRoot, { recursive: true })

  await _writeJson(path.join(webRoot, 'model_metadata.json'), {
    '공개 모델': { supportsVision: true }
  })
  await _writeJson(path.join(root, 'questions_metadata.json'), {
    '국어-공통': { '1': { hasImage: true, points: 2 } }
  })

  const legacyResults = JSON.stringify([
    {
      sheet_name: '국어-공통',
      subject: '국어',
      section: '공통',
      model_name: '공개 모델',
      results: [{ question_number: 1, points: 2, has_image: true }]
    }
  ])
  const legacyDefaultResults = JSON.stringify([
    {
      sheet_name: '국어-공통',
      subject: '국어',
      section: '공통',
      model_name: '일반 모델',
      results: [{ question_number: 1, points: 2, has_image: false }]
    }
  ])
  const legacyTokenUsage = '{"models":{"공개 모델":{"total_tokens":3}}}\n'
  const legacyDefaultTokenUsage = '{"models":{"일반 모델":{"total_tokens":4}}}\n'
  await mkdir(path.join(root, 'problems'), { recursive: true })
  await writeFile(path.join(root, 'all_results.json'), legacyResults, 'utf8')
  await writeFile(path.join(root, 'problems', 'token_usage.json'), legacyTokenUsage, 'utf8')
  await writeFile(path.join(root, 'hard_all_results.json'), legacyDefaultResults, 'utf8')
  await writeFile(path.join(root, 'problems', 'hard_token_usage.json'), legacyDefaultTokenUsage, 'utf8')

  await _writeJson(path.join(root, 'published', 'csat-2026', 'default', 'results.json'), [
    { subject: '국어', section: '공통', model_name: '게시 모델', results: [] }
  ])
  await _writeJson(path.join(root, 'published', 'csat-2026', 'default', 'token_usage.json'), {
    models: { '게시 모델': { total_tokens: 5 } }
  })
  await _writeJson(path.join(root, 'published', 'csat-2026', 'default', 'questions_metadata.json'), {
    exam_id: 'csat-2026',
    sections: {}
  })
  await _writeJson(path.join(root, 'published', 'csat-2027', 'default', 'results.json'), [
    { subject: '국어', section: '공통', model_name: '준비 모델', results: [] }
  ])
  await _writeJson(path.join(root, 'published', 'csat-2027', 'default', 'token_usage.json'), {
    models: { '준비 모델': { total_tokens: 0 } }
  })
  await _writeJson(path.join(root, 'published', 'csat-2027', 'default', 'questions_metadata.json'), {
    exam_id: 'csat-2027',
    sections: {}
  })

  await _writeJson(path.join(catalogDir, 'csat-2026.json'), _manifest({
    id: 'csat-2026',
    modes: [
      {
        id: 'default',
        label: '일반',
        input_mode: 'section',
        public_results: 'hard_all_results.json',
        public_token_usage: 'problems/hard_token_usage.json'
      },
      {
        id: 'easy',
        label: '쉬움',
        input_mode: 'question',
        public_results: 'all_results.json',
        public_token_usage: 'problems/token_usage.json'
      }
    ]
  }))
  await _writeJson(path.join(catalogDir, 'csat-2027.json'), _manifest({
    id: 'csat-2027',
    status: 'preparing',
    modes: [{ id: 'default', label: '기본', input_mode: 'section' }]
  }))
  await _writeJson(path.join(catalogDir, 'example-text.json'), _manifest({
    id: 'example-text',
    publish: false,
    modes: [{ id: 'default', label: '예시', input_mode: 'section' }]
  }))

  return { repoRoot: root, catalogDir, webRoot, outputDir }
}

test('공개 카탈로그와 중첩 자료를 생성하고 비공개 경로를 제거한다', async () => {
  const fixture = await _createFixture()
  try {
    await copyDataFiles(fixture)
    const output = fixture.outputDir
    const catalog = JSON.parse(await readFile(path.join(output, 'benchmarks.json'), 'utf8'))

    assert.deepEqual(Object.keys(catalog), ['schema_version', 'default_exam', 'exams'])
    assert.deepEqual(catalog.exams.map(exam => exam.id), ['csat-2026', 'csat-2027'])
    assert.deepEqual(Object.keys(catalog.exams[0]), [
      'id', 'title', 'status', 'short_name', 'exam_month', 'sections', 'modes'
    ])
    assert.equal(catalog.exams[0].short_name, catalog.exams[0].title)
    assert.equal(catalog.exams[0].exam_month, null)
    assert.equal(catalog.exams[0].sections[0].questions, undefined)
    assert.equal(catalog.exams[0].modes[0].public_results, undefined)
    assert.equal(catalog.exams[0].modes[0].public_token_usage, undefined)
    assert.equal(catalog.exams[0].modes[0].attempts, undefined)
    assert.equal(catalog.exams[0].modes[0].results, 'benchmarks/csat-2026/default/results.json')
    assert.equal(catalog.exams[0].modes[0].token_usage, 'benchmarks/csat-2026/default/token_usage.json')
    assert.equal(catalog.exams[0].modes[0].questions_metadata, 'benchmarks/csat-2026/default/questions_metadata.json')
    assert.equal(catalog.exams[0].modes[1].id, 'easy')
    assert.equal(catalog.exams[0].modes[1].attempts, undefined)
    assert.equal(catalog.exams[0].modes[1].results, 'benchmarks/csat-2026/easy/results.json')

    assert.deepEqual(
      JSON.parse(await readFile(path.join(output, 'benchmarks', 'csat-2026', 'default', 'results.json'), 'utf8')),
      [{ subject: '국어', section: '공통', model_name: '게시 모델', results: [] }]
    )
    assert.deepEqual(
      JSON.parse(await readFile(path.join(output, 'benchmarks', 'csat-2026', 'easy', 'results.json'), 'utf8')),
      JSON.parse(await readFile(path.join(fixture.repoRoot, 'all_results.json'), 'utf8'))
    )

    const catalogText = await readFile(path.join(output, 'benchmarks.json'), 'utf8')
    assert.equal(catalogText.includes('data_dir'), false)
    assert.equal(catalogText.includes('results_dir'), false)
    assert.equal(catalogText.includes('questions.json'), false)

    assert.equal(
      await readFile(path.join(output, 'benchmarks', 'csat-2026', 'default', 'results.json'), 'utf8'),
      await readFile(path.join(fixture.repoRoot, 'published', 'csat-2026', 'default', 'results.json'), 'utf8')
    )
    assert.equal(
      await readFile(path.join(output, 'all_results.json'), 'utf8'),
      await readFile(path.join(fixture.repoRoot, 'published', 'csat-2026', 'default', 'results.json'), 'utf8')
    )
    assert.equal(
      await readFile(path.join(output, 'token_usage.json'), 'utf8'),
      await readFile(path.join(fixture.repoRoot, 'published', 'csat-2026', 'default', 'token_usage.json'), 'utf8')
    )
    assert.equal(
      await readFile(path.join(output, 'easy_all_results.json'), 'utf8'),
      await readFile(path.join(fixture.repoRoot, 'all_results.json'), 'utf8')
    )
    assert.equal(
      await readFile(path.join(output, 'easy_token_usage.json'), 'utf8'),
      await readFile(path.join(fixture.repoRoot, 'problems', 'token_usage.json'), 'utf8')
    )
    assert.deepEqual(
      JSON.parse(await readFile(path.join(output, 'model_metadata.json'), 'utf8')),
      { '공개 모델': { supportsVision: true } }
    )
    assert.deepEqual(
      JSON.parse(await readFile(path.join(output, 'benchmarks', 'csat-2027', 'default', 'results.json'), 'utf8')),
      [{ subject: '국어', section: '공통', model_name: '준비 모델', results: [] }]
    )
  } finally {
    await rm(fixture.repoRoot, { recursive: true, force: true })
  }
})

test('준비 중 시험은 published 자료가 없으면 빈 파일을 생성한다', async () => {
  const fixture = await _createFixture()
  try {
    await rm(path.join(fixture.repoRoot, 'published'), { recursive: true, force: true })
    await copyDataFiles(fixture)
    const modeDir = path.join(fixture.outputDir, 'benchmarks', 'csat-2027', 'default')
    assert.deepEqual(JSON.parse(await readFile(path.join(modeDir, 'results.json'), 'utf8')), [])
    assert.deepEqual(JSON.parse(await readFile(path.join(modeDir, 'token_usage.json'), 'utf8')), {})
    assert.deepEqual(JSON.parse(await readFile(path.join(modeDir, 'questions_metadata.json'), 'utf8')), {})
  } finally {
    await rm(fixture.repoRoot, { recursive: true, force: true })
  }
})

test('준비 완료 시험의 공개 결과가 없으면 복사를 실패한다', async () => {
  const fixture = await _createFixture()
  try {
    await rm(path.join(fixture.repoRoot, 'all_results.json'), { force: true })
    await rm(path.join(fixture.repoRoot, 'hard_all_results.json'), { force: true })
    await rm(path.join(fixture.repoRoot, 'published', 'csat-2026'), { recursive: true, force: true })
    await assert.rejects(
      copyDataFiles(fixture),
      error => error.message.includes('준비 완료 시험의 공개 자료가 없습니다: csat-2026/default')
    )
  } finally {
    await rm(fixture.repoRoot, { recursive: true, force: true })
  }
})
