import assert from 'node:assert/strict'

import { formatEvidenceReference } from '../contentEvidencePresentation.js'

assert.equal(
  formatEvidenceReference(
    {
      id: 'ev_internal_id',
      variable_codes: ['area'],
      value: '89㎡',
      source_type: 'manual_input'
    },
    { area: '房屋面积' }
  ),
  '房屋面积：89㎡'
)

assert.equal(
  formatEvidenceReference({
    id: 'ev_internal_id',
    variable_codes: ['price'],
    value: { standard_package: '18万元', effective_at: '2026年8月' },
    source_type: 'knowledge_base'
  }),
  '产品价格：标准套餐：18万元；生效时间：2026年8月'
)

assert.equal(formatEvidenceReference(null, {}, 1), '已确认事实 2')
assert.equal(formatEvidenceReference({ source_type: 'knowledge_base', value: '企业产品手册' }), '知识库资料：企业产品手册')

console.log('contentEvidencePresentation: all assertions passed')
