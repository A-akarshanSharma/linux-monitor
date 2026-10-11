import { createHash } from 'node:crypto'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const publicDir = fileURLToPath(new URL('../public/', import.meta.url))
const workerPath = fileURLToPath(new URL('./service-worker.js', import.meta.url))

function publicFiles(dir = publicDir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const filename = path.join(dir, entry.name)
    return entry.isDirectory() ? publicFiles(filename) : [filename]
  })
}

export function appShellPlugin() {
  return {
    name: 'linux-monitor-app-shell',
    apply: 'build',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const source = readFileSync(workerPath, 'utf8')
      const hash = createHash('sha256').update(source)
      const urls = []
      for (const [filename, output] of Object.entries(bundle).sort()) {
        if (!/\.(?:html|js|css)$/.test(filename)) continue
        urls.push(`/${filename}`)
        hash.update(filename).update(output.type === 'chunk' ? output.code : output.source)
      }
      for (const filename of publicFiles().sort()) {
        const url = `/${path.relative(publicDir, filename).split(path.sep).join('/')}`
        urls.push(url)
        hash.update(url).update(readFileSync(filename))
      }
      this.emitFile({
        type: 'asset',
        fileName: 'sw.js',
        source: source
          .replace('__SHELL_CACHE_NAME__', `linux-monitor-shell-${hash.digest('hex').slice(0, 16)}`)
          .replace('__SHELL_URLS__', JSON.stringify(urls)),
      })
    },
  }
}
