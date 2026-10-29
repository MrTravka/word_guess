import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import type { Plugin } from 'vite'

export default function pwa(): Plugin {
  return {
    name: 'word-guess-pwa', apply: 'build',
    generateBundle(_options, bundle) {
      const files = Object.keys(bundle).filter((name) => name.startsWith('assets/')).sort()
      const publicFiles = ['manifest.webmanifest', 'icons/icon-180.png', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/maskable-512.png']
      const hash = createHash('sha256')
      hash.update(readFileSync(new URL('../index.html', import.meta.url)))
      for (const name of files) {
        const item = bundle[name]
        hash.update(name).update(item.type === 'chunk' ? item.code : item.source)
      }
      for (const name of publicFiles) hash.update(readFileSync(new URL(`../public/${name}`, import.meta.url)))
      const template = readFileSync(new URL('../src/pwa/service-worker.js', import.meta.url), 'utf8')
      hash.update(template)
      this.emitFile({ type: 'asset', fileName: 'sw.js', source: template
        .replace('__CACHE_ID__', hash.digest('hex').slice(0, 20))
        .replace('__SHELL_FILES__', JSON.stringify(['index.html', ...files, ...publicFiles].map((name) => '/' + name))) })
    },
  }
}
