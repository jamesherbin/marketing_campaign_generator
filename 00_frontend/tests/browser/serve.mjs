import { cp } from 'node:fs/promises'
import { existsSync } from 'node:fs'

// Mirror the production container's static-asset layout in generated output only.
await cp('.next/static', '.next/standalone/.next/static', { recursive: true })
if (existsSync('public')) await cp('public', '.next/standalone/public', { recursive: true })
process.env.HOSTNAME = '127.0.0.1'
process.env.PORT = '3100'
await import('../../.next/standalone/server.js')
