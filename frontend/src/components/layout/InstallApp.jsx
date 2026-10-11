import { useEffect, useState } from 'react'

export function InstallApp() {
  const [installPrompt, setInstallPrompt] = useState(null)

  useEffect(() => {
    const onPrompt = (event) => {
      event.preventDefault()
      setInstallPrompt(event)
    }
    const onInstalled = () => setInstallPrompt(null)
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  if (!installPrompt) return null

  async function install() {
    setInstallPrompt(null)
    try {
      await installPrompt.prompt()
    } catch (error) {
      console.warn('Could not open the app installation prompt:', error)
    }
  }

  return <button type="button" className="app-install-button" onClick={install}>Install app</button>
}
