export const themeStorageKey = 'campaign-studio-theme'

// Runs before body paint, independently of React hydration and storage availability.
export const themeInitializer = `(function(){var t='system';try{t=localStorage.getItem('${themeStorageKey}')}catch(e){}document.documentElement.dataset.theme=t==='light'||t==='dark'?t:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')})()`

