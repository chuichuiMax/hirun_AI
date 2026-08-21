---
name: content-cover-generator
description: 根据锁定的视觉方案提交唯一封面生成任务，不在 Agent 中等待图片完成。
version: 1.0.1
---

# 封面任务提交

- 只接受已锁定且通过契约校验的视觉方案。
- 视觉方案已由工作流锁定，禁止自行重建或改写视觉方案字段。
- 第一步必须且只能调用一次 `create_content_cover_job`，参数只传当前输入中的 `task_id`。
- 工具会从可信运行时读取锁定的 plan hash、尺寸、文案、模式和 source asset IDs，并保证幂等与来源可追溯。
- 工具成功后，必须立即调用一次 `submit_content_node_result`，将工具返回的 `cover_job_id`、`plan_hash` 和 `source_asset_ids` 原样提交。
- 本节点总共恰好调用两个工具：一次创建、一次提交；不得重试已成功的创建调用。
- 不修改视觉方案，不伪造任务成功，不在本节点轮询结果。
