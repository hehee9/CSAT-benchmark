/**
 * @file i18n.js
 * @brief react-i18next 설정
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import ko from './locales/ko.json'
import en from './locales/en.json'

/**
 * @brief 저장된 언어 또는 브라우저 언어 반환
 * @return {string} 언어 코드 ('ko' | 'en')
 */
function _getInitialLanguage() {
  const saved = localStorage.getItem('language')
  if (saved) return saved

  const browserLang = navigator.language.split('-')[0]
  return browserLang === 'ko' ? 'ko' : 'en'
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      ko: { translation: ko },
      en: { translation: en }
    },
    lng: _getInitialLanguage(),
    fallbackLng: 'ko',
    interpolation: {
      escapeValue: false
    }
  })

export default i18n
