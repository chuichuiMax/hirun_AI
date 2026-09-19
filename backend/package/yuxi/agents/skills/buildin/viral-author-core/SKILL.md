---
slug: viral-author-core
name: 爆款创作核心
description: 冻结规则下一次提交标题与正文；只写可追溯事实。
version: 1.0.0
---

# 爆款创作核心

1. 只读 payload：原始请求、锁定策略、唯一爆款结构、可写 Evidence、expression_guidance。
2. 一次调用直接 submit_content_node_result，禁止 read_file / 空转 / 再检索知识库。
3. 事实只来自可写 Evidence；无证据槽位删除或改成非事实表述。
4. 爆款只提供结构顺序，不提供可写数字、报价、城市、承诺。
5. expression_guidance 只学语气和具象说法，禁止带入人物/城市/数字/报价/经历/反馈/承诺。
6. 回修时只改问题码对应段落，锁定文本逐字保留。

