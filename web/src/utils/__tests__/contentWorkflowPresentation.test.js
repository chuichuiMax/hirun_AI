import assert from 'node:assert/strict'

import {
  CONTENT_WORKFLOW_GROUPS,
  CONTENT_WORKFLOW_NODE_LABELS,
  buildContentWorkflowGroups
} from '../contentWorkflowPresentation.js'

const groupedNodeIds = CONTENT_WORKFLOW_GROUPS.flatMap((group) => group.nodes)
assert.equal(CONTENT_WORKFLOW_GROUPS.length, 4)
assert.equal(groupedNodeIds.length, 15)
assert.equal(new Set(groupedNodeIds).size, 15)
assert.ok(groupedNodeIds.every((nodeId) => CONTENT_WORKFLOW_NODE_LABELS[nodeId]))

const groups = buildContentWorkflowGroups([
  { node_id: 'compile_runtime_snapshot', status: 'completed' },
  { node_id: 'ingest_real_materials', status: 'completed' },
  { node_id: 'normalize_evidence', status: 'completed' },
  { node_id: 'select_creation_strategy', status: 'running' }
])

assert.equal(groups[0].status, 'completed')
assert.equal(groups[0].isOpen, false)
assert.equal(groups[0].currentText, '已完成 3 个内部节点')
assert.equal(groups[1].status, 'running')
assert.equal(groups[1].isOpen, true)
assert.equal(groups[1].currentNode.id, 'select_creation_strategy')
assert.equal(groups[1].currentText, '当前：Agent 匹配创作手法、标题公式和正文公式')
assert.equal(groups[1].completedCount, 0)
assert.equal(groups[1].totalCount, 3)

const failedGroups = buildContentWorkflowGroups([
  { node_id: 'compile_runtime_snapshot', status: 'completed' },
  { node_id: 'ingest_real_materials', status: 'failed' }
])
assert.equal(failedGroups[0].status, 'failed')
assert.equal(failedGroups[0].isOpen, true)
assert.equal(failedGroups[0].currentNode.id, 'ingest_real_materials')

console.log('contentWorkflowPresentation: all assertions passed')
