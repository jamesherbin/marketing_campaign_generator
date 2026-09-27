// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { GoogleAuthProvider } from 'firebase/auth'
import { createGoogleAuthProvider } from '@/lib/google-auth-provider'

afterEach(() => vi.restoreAllMocks())

it('002-R8 always asks Google to show the account chooser', () => {
  const setCustomParameters = vi.spyOn(GoogleAuthProvider.prototype, 'setCustomParameters')
  expect(createGoogleAuthProvider()).toBeInstanceOf(GoogleAuthProvider)
  expect(setCustomParameters).toHaveBeenCalledWith({ prompt: 'select_account' })
})
