import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { rm } from 'node:fs/promises'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const webRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(webRoot, '..')
const pagesOutputDir = process.env.CSAT_BUILD_DIR
  ? path.isAbsolute(process.env.CSAT_BUILD_DIR)
    ? path.resolve(process.env.CSAT_BUILD_DIR)
    : path.resolve(repoRoot, process.env.CSAT_BUILD_DIR)
  : path.join(repoRoot, 'docs')
const docsAssetsDir = path.join(pagesOutputDir, 'assets')
const outputRoot = path.parse(pagesOutputDir).root
if (pagesOutputDir === outputRoot || !docsAssetsDir.startsWith(`${pagesOutputDir}${path.sep}`)) {
  throw new Error(`CSAT_BUILD_DIR가 삭제 허용 경로가 아닙니다: ${pagesOutputDir}`)
}

async function cleanPagesBuild() {
  await rm(docsAssetsDir, { recursive: true, force: true })
  console.log(`Removed ${path.relative(repoRoot, docsAssetsDir)}`)
}

if (process.argv[1] === __filename) {
  cleanPagesBuild().catch((error) => {
    console.error(error)
    process.exit(1)
  })
}

export { cleanPagesBuild }
