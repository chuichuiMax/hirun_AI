const PLATFORM_TOPIC_TAG_PATTERN = /#[^#\n]+?\[话题\]#?/g
const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

export const formatInspireDetailBody = (body, tags = []) => {
  const normalizedTags = [...new Set((tags || []).map((tag) => String(tag).trim()).filter(Boolean))]
  const knownTagPattern = normalizedTags.length
    ? `#(?:${normalizedTags
        .map(escapeRegExp)
        .sort((left, right) => right.length - left.length)
        .join('|')})(?:\\[话题\\]#?)?(?=\\s|#|[。.！!？?，,、；;：:]|$)`
    : ''
  const knownTagTokenPattern = knownTagPattern ? new RegExp(knownTagPattern, 'gu') : null
  const lines = String(body || '').split(/\r?\n/)

  while (lines.length && !lines.at(-1).trim()) lines.pop()
  while (lines.length) {
    const line = lines.at(-1)
    const withoutPlatformTags = line.replace(PLATFORM_TOPIC_TAG_PATTERN, '')
    const withoutKnownTags = knownTagTokenPattern
      ? withoutPlatformTags.replace(knownTagTokenPattern, '')
      : withoutPlatformTags
    const hasTopicTag = withoutKnownTags !== line
    const hasOtherContent = withoutKnownTags.replace(/[\s。.！!？?，,、；;：:]+/g, '')
    if (!hasTopicTag || hasOtherContent) break
    lines.pop()
    while (lines.length && !lines.at(-1).trim()) lines.pop()
  }

  const content = lines
    .join('\n')
    .replace(/\[话题\]#?/g, '')
    .trim()

  if (!content) return ''

  const tagLine = normalizedTags.map((tag) => `#${tag}`).join(' ')

  return [content, tagLine].filter(Boolean).join('\n\n')
}
