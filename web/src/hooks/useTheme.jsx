/**
 * @file useTheme.jsx
 * @brief 테마 상태 관리를 위한 Context 및 Hook
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const ThemeContext = createContext(null)

/**
 * @brief 시스템 다크모드 설정 감지
 * @return {boolean} 시스템이 다크모드인지 여부
 */
function _getSystemPreference() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

/**
 * @brief 테마 제공자 컴포넌트
 * @param {Object} props - { children }
 */
export function ThemeProvider({ children }) {
  // 'light' | 'dark' | 'system'
  const [themeMode, setThemeMode] = useState(() => {
    const saved = localStorage.getItem('theme')
    return saved || 'system'
  })

  const [isDark, setIsDark] = useState(false)

  /**
   * @brief 실제 테마 적용
   * @param {string} mode - 테마 모드
   */
  const applyTheme = useCallback((mode) => {
    const shouldBeDark = mode === 'system'
      ? _getSystemPreference()
      : mode === 'dark'

    setIsDark(shouldBeDark)

    if (shouldBeDark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [])

  /**
   * @brief 테마 모드 변경
   * @param {'light' | 'dark' | 'system'} mode - 테마 모드
   */
  const setTheme = useCallback((mode) => {
    setThemeMode(mode)
    localStorage.setItem('theme', mode)
    applyTheme(mode)
  }, [applyTheme])

  /**
   * @brief 테마 토글 (light <-> dark)
   */
  const toggleTheme = useCallback(() => {
    const newMode = isDark ? 'light' : 'dark'
    setTheme(newMode)
  }, [isDark, setTheme])

  // 초기 테마 적용
  useEffect(() => {
    applyTheme(themeMode)
  }, [themeMode, applyTheme])

  // 시스템 설정 변경 감지
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      if (themeMode === 'system') {
        applyTheme('system')
      }
    }
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [themeMode, applyTheme])

  const value = {
    themeMode,
    isDark,
    setTheme,
    toggleTheme
  }

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}

/**
 * @brief 테마 컨텍스트 사용 훅
 * @return {Object} { themeMode, isDark, setTheme, toggleTheme }
 */
export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
