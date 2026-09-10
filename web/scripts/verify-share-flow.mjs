import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('../src/views/MaterialLibraryView.vue', import.meta.url), 'utf8')

for (const forbidden of ['navigator.share', 'weixin://', 'wxwork://']) {
  if (source.includes(forbidden)) {
    throw new Error(`share flow still contains forbidden handoff: ${forbidden}`)
  }
}

for (const required of ['response.share.url', '链接已复制，请粘贴到微信或企业微信']) {
  if (!source.includes(required)) {
    throw new Error(`share flow is missing required behavior: ${required}`)
  }
}

console.log('share flow contract passed')
