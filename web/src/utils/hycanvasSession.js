const isLoopbackHostname = (hostname) => (
  hostname === 'localhost' || hostname === '[::1]' || /^127(?:\.\d{1,3}){3}$/.test(hostname)
)

/** Align loopback HyCanvas URLs with the ContentFlow host the browser is actually using. */
export const normalizeHyCanvasSessionUrl = (sessionUrl, appUrl) => {
  const target = new URL(sessionUrl)
  const app = new URL(appUrl)
  if (isLoopbackHostname(target.hostname)) {
    target.hostname = app.hostname
  }
  return target.toString()
}
