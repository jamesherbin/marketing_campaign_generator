import { GoogleAuthProvider } from 'firebase/auth'

export function createGoogleAuthProvider(): GoogleAuthProvider {
  const provider = new GoogleAuthProvider()
  provider.setCustomParameters({ prompt: 'select_account' })
  return provider
}
