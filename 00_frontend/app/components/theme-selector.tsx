'use client'

import { useEffect, useState } from 'react'

import { themeStorageKey } from '@/lib/theme'
type Theme = 'system' | 'light' | 'dark'
const validTheme = (value: string | null): Theme => value === 'light' || value === 'dark' ? value : 'system'

let sessionPreference: Theme = 'system'

export default function ThemeSelector() {
  const [theme, setTheme] = useState<Theme>('system')
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    let preference: Theme = sessionPreference
    try { preference = validTheme(localStorage.getItem(themeStorageKey)) } catch { /* Storage is optional. */ }
    const apply = () => {
      sessionPreference = preference
      document.documentElement.dataset.theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference
      setTheme(preference)
    }
    const change = (event: Event) => {
      preference = (event as CustomEvent<Theme>).detail
      apply()
    }
    const sync = (event: StorageEvent) => {
      if (event.key === themeStorageKey || event.key === null) { preference = validTheme(event.newValue); apply() }
    }
    apply()
    media.addEventListener('change', apply)
    window.addEventListener('campaign-theme', change)
    window.addEventListener('storage', sync)
    return () => {
      media.removeEventListener('change', apply)
      window.removeEventListener('campaign-theme', change)
      window.removeEventListener('storage', sync)
    }
  }, [])

  return <label className="theme-selector">Theme
    <select aria-label="Theme" value={theme} onChange={event => {
      const preference = validTheme(event.target.value)
      try { localStorage.setItem(themeStorageKey, preference) } catch { /* Keep in-session selection usable. */ }
      window.dispatchEvent(new CustomEvent('campaign-theme', { detail: preference }))
    }}>
      <option value="system">System</option>
      <option value="light">Light</option>
      <option value="dark">Dark</option>
    </select>
  </label>
}
