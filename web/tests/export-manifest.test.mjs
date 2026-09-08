import assert from 'node:assert/strict'
import test from 'node:test'
import {
  EXPORT_TARGETS,
  getExportTargetById
} from '../scripts/export-manifest.mjs'

test('일반·쉬움 이미지 대상이 모드와 파일명에 맞게 연결된다', () => {
  const generalTargets = EXPORT_TARGETS.filter(target => target.params.mode === 'default')
  const easyTargets = EXPORT_TARGETS.filter(target => target.params.mode === 'easy')

  assert.ok(generalTargets.length > 0)
  assert.ok(easyTargets.length > 0)
  assert.ok(generalTargets.every(target => !target.fileName.startsWith('쉬움_')))
  assert.ok(easyTargets.every(target => target.fileName.startsWith('쉬움_')))
  assert.ok(easyTargets.every(target => target.id.startsWith('easy-')))
  assert.equal(EXPORT_TARGETS.some(target => target.params.mode === 'hard'), false)
  assert.equal(getExportTargetById('easy-subject-korean').params.mode, 'easy')
})
