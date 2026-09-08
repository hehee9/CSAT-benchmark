import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import process from 'process'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..')

/** @description 환경 변수 경로를 저장소 기준 절대 경로로 변환 */
function _resolveConfiguredPath(value, fallback) {
  if (!value) return fallback
  return path.isAbsolute(value) ? path.resolve(value) : path.resolve(repoRoot, value)
}

/**
 * @brief Vite 설정
 * - 기본 빌드: 로컬 검증용 `web/dist`
 * - pages 모드: GitHub Pages 배포용 `docs`
 */
export default defineConfig(({ mode }) => {
  const isPagesBuild = mode === 'pages'
  const publicDir = _resolveConfiguredPath(
    process.env.CSAT_PUBLIC_DIR,
    path.resolve(__dirname, 'public')
  )
  const defaultOutputDir = isPagesBuild
    ? path.resolve(repoRoot, 'docs')
    : path.resolve(__dirname, 'dist')
  const outputDir = _resolveConfiguredPath(process.env.CSAT_BUILD_DIR, defaultOutputDir)

  return {
    plugins: [react(), tailwindcss()],
    base: '/CSAT-benchmark/',
    publicDir,
    build: {
      outDir: outputDir,
      emptyOutDir: !isPagesBuild
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src')
      }
    }
  }
})
