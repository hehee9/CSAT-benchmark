/**
 * @file BenchmarkNote.jsx
 * @brief 벤치마크 실행 조건 설명 공통 노트
 */

import { useTranslation } from 'react-i18next'
import { useData } from '@/hooks/useData'
import { getAnyModelFlags } from '@/utils/modelMeta'
import { MODEL_COLORS } from '@/utils/colorUtils'

/**
 * @brief 범례용 미니 사각형 SVG
 * @param {{ type: 'noVision' | 'nonStandard' | 'postExamKnowledgeCutoff' | 'webServiceNoTools' }} props
 */
function _LegendSwatch({ type }) {
  const size = 14
  const d = 3
  if (type === 'webServiceNoTools') {
    return (
      <svg width={size} height={size} className="inline-block align-middle mr-1 shrink-0">
        <defs>
          <pattern id="legend-web-service-no-tools-checker" patternUnits="userSpaceOnUse" width="6" height="6">
            <rect x="0" y="0" width="3" height="3" fill="rgba(255,255,255,0.32)" />
            <rect x="3" y="3" width="3" height="3" fill="rgba(255,255,255,0.32)" />
            <rect x="3" y="0" width="3" height="3" fill="rgba(0,0,0,0.10)" />
            <rect x="0" y="3" width="3" height="3" fill="rgba(0,0,0,0.10)" />
          </pattern>
        </defs>
        <rect width={size} height={size} rx={2} fill="#888" />
        <rect width={size} height={size} rx={2} fill="url(#legend-web-service-no-tools-checker)" />
      </svg>
    )
  }

  if (type === 'postExamKnowledgeCutoff') {
    const colors = [MODEL_COLORS.GPT, MODEL_COLORS.Claude, MODEL_COLORS.Grok]
    const barWidth = 4
    return (
      <svg width={size + 4} height={size} className="inline-block align-middle mr-1 shrink-0 overflow-visible">
        <defs>
          <filter id="legend-post-exam-cutoff-glow" x="-18%" y="-25%" width="136%" height="150%">
            <feGaussianBlur stdDeviation="0.8" />
          </filter>
        </defs>
        {colors.map((color, i) => {
          const x = 1 + i * (barWidth + 1)
          return (
            <g key={color}>
              <rect
                x={x - 0.5}
                y={1}
                width={barWidth + 1}
                height={size - 2}
                rx={1}
                fill={color}
                opacity={0.9}
                filter="url(#legend-post-exam-cutoff-glow)"
              />
              <rect x={x} y={1} width={barWidth} height={size - 2} rx={1} fill={color} />
            </g>
          )
        })}
      </svg>
    )
  }

  if (type === 'noVision') {
    return (
      <svg width={size} height={size} className="inline-block align-middle mr-1 shrink-0">
        <defs>
          <linearGradient id="ls-l" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="rgba(0,0,0,0.4)" /><stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </linearGradient>
          <linearGradient id="ls-r" x1="1" y1="0" x2="0" y2="0">
            <stop offset="0%" stopColor="rgba(0,0,0,0.4)" /><stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </linearGradient>
          <linearGradient id="ls-t" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(0,0,0,0.4)" /><stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </linearGradient>
          <linearGradient id="ls-b" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="rgba(0,0,0,0.4)" /><stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </linearGradient>
        </defs>
        <rect width={size} height={size} rx={2} fill="#888" />
        <rect x={0} y={0} width={d} height={size} fill="url(#ls-l)" />
        <rect x={size - d} y={0} width={d} height={size} fill="url(#ls-r)" />
        <rect x={0} y={0} width={size} height={d} fill="url(#ls-t)" />
        <rect x={0} y={size - d} width={size} height={d} fill="url(#ls-b)" />
      </svg>
    )
  }
  return (
    <svg width={size} height={size} className="inline-block align-middle mr-1 shrink-0">
      <defs>
        <pattern id="legend-hatch" patternUnits="userSpaceOnUse" width="4" height="4" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="4" stroke="rgba(0,0,0,0.4)" strokeWidth="1.5" />
        </pattern>
      </defs>
      <rect width={size} height={size} rx={2} fill="#888" />
      <rect width={size} height={size} rx={2} fill="url(#legend-hatch)" />
    </svg>
  )
}

export default function BenchmarkNote({
  className = 'mt-3 text-sm text-gray-500 dark:text-gray-400',
  modelNames = [],
  modelMetadata
}) {
  const { t } = useTranslation()
  const { exam, modelMetadata: contextModelMetadata } = useData()
  const flags = getAnyModelFlags(modelNames, modelMetadata ?? contextModelMetadata, exam?.exam_month)

  return (
    <div className={`${className} export-role-note`}>
      <p>{t('benchmark.noExternalSearch')}</p>
      {(flags.hasNoVision || flags.hasNonStandard || flags.hasPostExamKnowledgeCutoff || flags.hasWebServiceNoTools) && (
        <div className="export-role-legend mt-1 flex flex-wrap gap-x-4 gap-y-1">
          {flags.hasNoVision && (
            <span className="inline-flex items-center">
              <_LegendSwatch type="noVision" />
              {t('models.noVision')}
            </span>
          )}
          {flags.hasNonStandard && (
            <span className="inline-flex items-center">
              <_LegendSwatch type="nonStandard" />
              {t('models.nonStandard')}
            </span>
          )}
          {flags.hasPostExamKnowledgeCutoff && (
            <span className="inline-flex items-center">
              <_LegendSwatch type="postExamKnowledgeCutoff" />
              {t('models.postExamKnowledgeCutoff')}
            </span>
          )}
          {flags.hasWebServiceNoTools && (
            <span className="inline-flex items-center">
              <_LegendSwatch type="webServiceNoTools" />
              {t('models.webServiceNoTools')}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
