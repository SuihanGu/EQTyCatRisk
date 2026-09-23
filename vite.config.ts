import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { copyFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('.', import.meta.url))
const python =
  process.env.EQTY_PYTHON ||
  (process.platform === 'win32' && existsSync('D:\\Anaconda\\python.exe')
    ? 'D:\\Anaconda\\python.exe'
    : 'python')

function runPython(script: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(python, [script, ...args], { cwd: root, windowsHide: true })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => { stdout += String(chunk) })
    child.stderr.on('data', (chunk) => { stderr += String(chunk) })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve(stdout)
      else reject(new Error(stderr || stdout || `Python exited with code ${code}`))
    })
  })
}

function runBatch(batch: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    // Pass one complete command string to cmd.exe. windowsVerbatimArguments
    // prevents Node from converting the quotes into literal \" characters.
    const quote = (value: string) => `"${value.replace(/"/g, '""')}"`
    const command = ['call', quote(batch), ...args.map(quote)].join(' ')
    const child = spawn('cmd.exe', ['/d', '/c', command], {
      cwd: root,
      windowsHide: true,
      windowsVerbatimArguments: true,
    })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => { stdout += String(chunk) })
    child.stderr.on('data', (chunk) => { stderr += String(chunk) })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve(stdout)
      else reject(new Error(stderr || stdout || `Batch exited with code ${code}`))
    })
  })
}

function jsonResponse(response: import('node:http').ServerResponse, status: number, body: unknown) {
  response.statusCode = status
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.end(JSON.stringify(body))
}

function backendPlugin(): Plugin {
  return {
    name: 'eqtycatrisk-backend',
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        if (request.method !== 'POST' || !request.url?.startsWith('/api/')) {
          next()
          return
        }
        try {
          if (request.url === '/api/recognize') {
            const dataDir = path.join(root, 'data', 'Sample data 1')
            await runPython(path.join(dataDir, 'Preprocessing', 'code', 'run_japan_recognition.py'), [
              '--earthquake-file', path.join(dataDir, '2KIK_earthquake_events_1997-2026_Japan.csv'),
              '--typhoon-file', path.join(dataDir, 'typhoon_events_2001-2026_Japan.csv'),
              '--output-dir', dataDir,
            ])
            await runPython(path.join(root, 'scripts', 'build-coupling-json.py'), [])
            const publicDir = path.join(root, 'public', 'data', 'generated')
            await mkdir(publicDir, { recursive: true })
            for (const filename of [
              'Coupling moment information.csv',
              'Complete set of typhoon events satisfying coupling conditions.csv',
            ]) {
              await copyFile(path.join(dataDir, filename), path.join(publicDir, filename))
            }
            jsonResponse(response, 200, {
              ok: true,
              downloads: {
                coupling: '/data/generated/Coupling%20moment%20information.csv',
                tracks: '/data/generated/Complete%20set%20of%20typhoon%20events%20satisfying%20coupling%20conditions.csv',
              },
            })
            return
          }
          if (request.url?.startsWith('/api/calculate-loss')) {
            const dataDir = path.join(root, 'data', 'Sample data 2')
            const requestedUrl = new URL(request.url, 'http://127.0.0.1')
            const caseId = requestedUrl.searchParams.get('caseId') || ''
            const caseKey = caseId.includes('20041006') ? '2004' : '2005'
            await runPython(path.join(dataDir, 'Preprocessing', 'run_v12_loss_calculation.py'), [
              '--output-dir', path.join(dataDir, 'risk-loss'),
              '--public-dir', path.join(root, 'public', 'data', 'risk-loss'),
              '--case', caseKey,
            ])
            jsonResponse(response, 200, {
              ok: true,
              samples: 2000,
              source: 'repository-local visualization-loss-value-12 calculation engine',
              case: caseKey === '2004' ? '2004 Chiba MA-ON' : '2005 Chiba BANYAN',
              exposure: 'without_Other',
            })
            return
          }
        } catch (error) {
          jsonResponse(response, 500, { ok: false, error: error instanceof Error ? error.message : String(error) })
          return
        }
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), backendPlugin()],
})
