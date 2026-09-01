'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { GoogleAuthProvider, inMemoryPersistence, setPersistence, signInWithPopup, signOut } from 'firebase/auth'
import { firebaseAuth } from '@/lib/firebase-client'

export default function LoginPage() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function signInWithGoogle() {
    setBusy(true)
    setError(null)
    try {
      await setPersistence(firebaseAuth, inMemoryPersistence)
      const result = await signInWithPopup(firebaseAuth, new GoogleAuthProvider())
      const idToken = await result.user.getIdToken()
      const response = await fetch('/api/auth/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken }),
      })
      if (!response.ok) throw new Error('Unable to establish a secure session')
      await signOut(firebaseAuth)
      router.replace('/')
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google sign-in failed')
      setBusy(false)
    }
  }

  return (
    <main className="login-shell">
      <nav className="login-nav">
        <Link className="brand" href="/" aria-label="Campaign Studio home">
          <span className="brand-mark">MC</span>
          <span>Campaign Studio</span>
        </Link>
        <p>Campaign operations, intelligently orchestrated.</p>
      </nav>

      <section className="login-layout">
        <div className="login-story">
          <p className="eyebrow">Your campaign command center</p>
          <h1>Good work starts with a clear signal.</h1>
          <p className="lede">
            Sign in to plan campaigns, align creative, and turn every brief into measurable momentum.
          </p>
          <div className="signal-card" aria-hidden="true">
            <div className="signal-card-head">
              <span>Campaign signal</span>
              <small>LIVE</small>
            </div>
            <div className="signal-chart"><i /><i /><i /><i /><i /><i /><i /><i /></div>
            <div className="signal-meta">
              <div><strong>4</strong><span>Active phases</span></div>
              <div><strong>+28%</strong><span>Momentum</span></div>
              <div><strong>1</strong><span>Shared view</span></div>
            </div>
          </div>
        </div>

        <div className="login-panel">
          <div className="login-panel-head">
            <p className="eyebrow">Welcome back</p>
            <h2>Sign in to your workspace</h2>
            <p>Use your work email to continue.</p>
          </div>

          <button className="sso-button" type="button" disabled={busy} onClick={() => void signInWithGoogle()}>
            <span className="google-mark">G</span> {busy ? 'Signing in…' : 'Continue with Google'}
          </button>
          {error && <p className="form-error" role="alert">{error}</p>}
          <p className="signup-copy">Access is managed through your organization’s Google account.</p>
        </div>
      </section>

      <footer className="login-footer"><span>© 2026 Campaign Studio</span><span><Link href="#">Privacy</Link><Link href="#">Terms</Link></span></footer>
    </main>
  )
}
