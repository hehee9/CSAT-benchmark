import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..', '..')
const imagesDir = path.join(repoRoot, 'docs', 'images')
export const EXPORT_GROUP_ORDER = ['overview', 'subjects', 'cost']

/** @description 이미지 내보내기 대상 생성 */
function createImageTarget({ id, group, exportKey, fileName, params }) {
  return {
    id,
    group,
    exportKey,
    outputPath: path.join(imagesDir, fileName),
    fileName,
    params: {
      theme: 'light',
      mode: 'default',
      ...params
    }
  }
}

/** @description 쉬움 모드 과목 점수 내보내기 대상 생성 */
function createEasySubjectTarget({ id, fileName, subjects }) {
  return createImageTarget({
    id: `easy-${id}`,
    group: 'subjects',
    exportKey: 'overview-score-chart',
    fileName: `쉬움_${fileName}`,
    params: {
      mode: 'easy',
      tab: 'overview',
      subjects
    }
  })
}

export const EXPORT_TARGETS = [
  createImageTarget({
    id: 'overview-total',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '전체.png',
    params: { tab: 'overview', scoreView: 'average' }
  }),
  createImageTarget({
    id: 'overview-best-worst',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '최고_최저.png',
    params: { tab: 'overview', scoreView: 'bestWorst' }
  }),
  createImageTarget({
    id: 'overview-with-image',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '이미지O.png',
    params: { tab: 'overview', scoreView: 'withImage' }
  }),
  createImageTarget({
    id: 'overview-without-image',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '이미지X.png',
    params: { tab: 'overview', scoreView: 'withoutImage' }
  }),
  createImageTarget({
    id: 'subject-korean',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '국어.png',
    params: { tab: 'overview', subjects: '국어-화작,국어-언매' }
  }),
  createImageTarget({
    id: 'subject-math',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '수학.png',
    params: { tab: 'overview', subjects: '수학-확통,수학-미적,수학-기하' }
  }),
  createImageTarget({
    id: 'subject-english',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '영어.png',
    params: { tab: 'overview', subjects: '영어' }
  }),
  createImageTarget({
    id: 'subject-history',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '한국사.png',
    params: { tab: 'overview', subjects: '한국사' }
  }),
  createImageTarget({
    id: 'subject-physics1',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '물리1.png',
    params: { tab: 'overview', subjects: '탐구-물리1' }
  }),
  createImageTarget({
    id: 'subject-chemistry1',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '화학1.png',
    params: { tab: 'overview', subjects: '탐구-화학1' }
  }),
  createImageTarget({
    id: 'subject-biology1',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '생명1.png',
    params: { tab: 'overview', subjects: '탐구-생명1' }
  }),
  createImageTarget({
    id: 'subject-society',
    group: 'overview',
    exportKey: 'overview-score-chart',
    fileName: '사회문화.png',
    params: { tab: 'overview', subjects: '탐구-사회문화' }
  }),
  createEasySubjectTarget({
    id: 'subject-korean',
    fileName: '국어.png',
    subjects: '국어-화작,국어-언매'
  }),
  createEasySubjectTarget({
    id: 'subject-math',
    fileName: '수학.png',
    subjects: '수학-확통,수학-미적,수학-기하'
  }),
  createEasySubjectTarget({
    id: 'subject-english',
    fileName: '영어.png',
    subjects: '영어'
  }),
  createEasySubjectTarget({
    id: 'subject-history',
    fileName: '한국사.png',
    subjects: '한국사'
  }),
  createEasySubjectTarget({
    id: 'subject-physics1',
    fileName: '물리1.png',
    subjects: '탐구-물리1'
  }),
  createEasySubjectTarget({
    id: 'subject-chemistry1',
    fileName: '화학1.png',
    subjects: '탐구-화학1'
  }),
  createEasySubjectTarget({
    id: 'subject-biology1',
    fileName: '생명1.png',
    subjects: '탐구-생명1'
  }),
  createEasySubjectTarget({
    id: 'subject-society',
    fileName: '사회문화.png',
    subjects: '탐구-사회문화'
  }),
  createImageTarget({
    id: 'cost-analysis',
    group: 'cost',
    exportKey: 'cost-scatter',
    fileName: '비용_분석.png',
    params: { tab: 'cost' }
  }),
  createImageTarget({
    id: 'token-usage',
    group: 'cost',
    exportKey: 'token-usage',
    fileName: '토큰_사용량.png',
    params: { tab: 'cost' }
  })
]

/** @description 지정 출력 경로를 적용한 이미지 내보내기 대상 반환 */
export function getExportTargets(options = {}) {
  const outputDir = options.outputDir
    ? path.resolve(options.outputDir)
    : imagesDir
  return EXPORT_TARGETS.map(target => ({
    ...target,
    outputPath: path.join(outputDir, target.fileName)
  }))
}

/** @description 지정 출력 경로를 적용한 대상 하나 반환 */
export function getExportTargetById(id, options = {}) {
  return getExportTargets(options).find(target => target.id === id) || null
}

/** @description 지정 출력 경로를 적용한 그룹별 대상 반환 */
export function getExportTargetsByGroup(group, options = {}) {
  return getExportTargets(options).filter(target => target.group === group)
}
