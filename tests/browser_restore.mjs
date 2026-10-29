import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import path from 'node:path'

export async function restoreBrowserDatabase({ python, directory, env, start, freePort, waitFor }) {
  const database = path.join(directory, 'test.db')
  const backup = path.join(directory, 'acceptance-backup.db')
  const restored = path.join(directory, 'acceptance-restored.db')
  for (const arguments_ of [
    ['backup', '--database', database, '--output', backup],
    ['restore', '--source', backup, '--output', restored],
  ]) await promisify(execFile)(python, ['-m', 'backend.app.backup', ...arguments_], { windowsHide: true })
  const port = await freePort()
  const server = start(python, ['-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', String(port)],
    { env: { ...env, DATABASE_URL: `sqlite:///${restored.replaceAll('\\', '/')}` } })
  const url = `http://127.0.0.1:${port}`
  await waitFor(async () => {
    if (server.exitCode !== null) throw new Error(server.log)
    try { return (await fetch(`${url}/api/health`)).ok } catch { return false }
  }, 'restored server ready')
  return url
}
