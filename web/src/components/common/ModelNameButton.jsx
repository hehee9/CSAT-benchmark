/**
 * @file ModelNameButton.jsx
 * @brief 누르면 모델 정보 카드를 여는 표용 모델명 버튼
 */

import { useState } from 'react'
import { formatModelDisplayName } from '@/utils/modelMeta'
import ModelInfoPopover from './ModelInfoPopover'

/**
 * @brief 모델명 버튼
 * @param {{ model: string, className: string, children: React.ReactNode }} props
 *
 * children이 없으면 표시용 모델명을 그대로 쓴다. 글꼴과 색은 감싸는 셀을 따른다.
 */
export default function ModelNameButton({ model, className = '', children }) {
  const [anchorEl, setAnchorEl] = useState(null)
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <button
        ref={setAnchorEl}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(open => !open)}
        className={`cursor-pointer rounded-sm text-left decoration-gray-400 decoration-dotted underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 dark:decoration-gray-500 ${className}`}
      >
        {children ?? formatModelDisplayName(model)}
      </button>
      {isOpen && <ModelInfoPopover model={model} anchorEl={anchorEl} onClose={() => setIsOpen(false)} />}
    </>
  )
}
