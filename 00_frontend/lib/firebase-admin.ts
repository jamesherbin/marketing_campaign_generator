import { applicationDefault, getApps, initializeApp } from 'firebase-admin/app'
import { getAuth } from 'firebase-admin/auth'

const projectId = process.env.GOOGLE_CLOUD_PROJECT ?? process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID

if (!projectId) throw new Error('GOOGLE_CLOUD_PROJECT is required for Firebase Admin')

const app = getApps().length
  ? getApps()[0]
  : initializeApp({ credential: applicationDefault(), projectId })

export const firebaseAdminAuth = getAuth(app)
