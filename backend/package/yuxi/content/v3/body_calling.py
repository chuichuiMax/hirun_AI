"""装修行业“3.2 正文调用”执行规则。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SOURCE_METADATA = {
    "document": "小红书自运营内容生产工具V2.0设计框架",
    "section": "3.2 正文调用",
    "url": "https://fycrbjmor5.feishu.cn/wiki/W1fhwWyKGi86ABkz1VTcBmWJnEf",
    "source_revision": "8月11日修改",
}


DECORATION_BODY_CALLING: dict[str, dict[str, Any]] = {
    "C01": {
        "formula_name": "报价转化类：痛点+数据+品牌背书+引流",
        "lexicon_calls": [
            "body.budget_pain",
            "body.budget_contrast",
            "body.owner_expectation_gap",
            "body.quotation_chaos",
            "body.quotation_cognitive_contrast",
            "persona.service_contrast",
            "body.cost_result",
            "ending.quotation_cta",
        ],
        "sections": [
            {
                "id": "audience_pain",
                "name": "人群痛点开篇",
                "instruction": "锁定本地装修业主，聚焦看不懂报价、怕隐形增项、怕低价陷阱等困扰；痛点可谈预算，但不要把「低价」塑造成解决方案",
                "fill_rule": "仅使用预算痛点词库描述业主普遍报价、预算困扰",
                "lexicon_calls": ["body.budget_pain"],
                "fact_source": "lexicon",
            },
            {
                "id": "verified_data",
                "name": "数据落地铺垫",
                "instruction": "用简报信息卡点写出小区名称、房屋面积、房屋布局（有填才写）、风格、项目施工鸿扬家装；可并列基础/木制品/主材等报价作参考口径，并点明报价仅供参考、不是核心卖点；面积等字段原样抄写证据文本；对应事实写入本段 evidence_ids",
                "fill_rule": "只使用 ContentBrief 或 EvidenceBundle 中的真实数据，逐字复制匹配条目的 id，不调用词库补造数字，不编造布局与改造细节，不把面积区间改成中间值",
                "lexicon_calls": [],
                "fact_source": "evidence",
            },
            {
                "id": "single_contrast",
                "name": "多维度前后反差展示",
                "instruction": "四选一且单篇只使用一种反差逻辑，禁止混用；优先服务/认知反差；反差结论导向透明交付与品牌靠谱，禁止主推「我们更便宜/低价碾压」",
                "fill_rule": "按所选反差维度使用对应词库，保持统一正反对比逻辑；涉及预算时强调口径清晰与少踩坑，不强调低价优势",
                "lexicon_calls": [],
                "fact_source": "lexicon_and_evidence",
            },
            {
                "id": "persona_cta",
                "name": "品牌优势+引流收尾",
                "instruction": "用充足篇幅写鸿扬家居/鸿扬家装品牌优势（定制化家装、透明施工、规范工艺、售后与靠谱交付；禁止写成整装或标准化整装），再给明确引流点（同城咨询、看工艺、留言要参考清单）；报价不是收尾卖点",
                "fill_rule": "使用服务反差/人设词库输出品牌与交付优势，并用报价引导词库做轻咨询转化，禁止把低价写成转化理由",
                "lexicon_calls": ["persona.service_contrast", "ending.quotation_cta"],
                "fact_source": "lexicon_and_evidence",
            },
        ],
        "variants": [
            {
                "id": "service_contrast",
                "name": "服务反差",
                "instruction": "行业乱象套路 VS 鸿扬透明施工与品牌交付",
                "lexicon_calls": ["body.quotation_chaos", "persona.service_contrast"],
            },
            {
                "id": "budget_contrast",
                "name": "预算反差",
                "instruction": "业主理想化预算预期 VS 实际装修超支现状；解决方向是口径透明与品牌交付，不是拼最低价",
                "lexicon_calls": ["body.owner_expectation_gap", "body.budget_contrast"],
            },
            {
                "id": "cognitive_contrast",
                "name": "认知反差",
                "instruction": "业主错误报价认知 VS 专业正规报价逻辑与品牌标准",
                "lexicon_calls": ["body.quotation_cognitive_contrast"],
            },
            {
                "id": "cost_contrast",
                "name": "代价反差",
                "instruction": "盲目低价签约的踩坑代价 VS 选择规范品牌与透明交付的长期省心（不要写成「我们更便宜」）",
                "lexicon_calls": ["body.cost_result"],
            },
        ],
        "variation_rule": "不同正文轮换反差维度和表达，单篇不得混用多个反差维度；报价清单类始终以品牌优势收束",
        "reference_examples": [
            "从看不懂报价、怕增项切入；用小区、面积、风格与参考报价卡点说明；重点讲鸿扬品牌与透明交付，最后邀请同城咨询。"
        ],
    },
    "C02": {
        "formula_name": "实景流量类：痛点+数据+优势+引流",
        "lexicon_calls": [
            "body.old_house_pain",
            "body.renovation_advantage",
            "persona.delivery_endorsement",
            "ending.case_cta",
        ],
        "sections": [
            {
                "id": "old_house_pain",
                "name": "人群痛点开篇",
                "instruction": "锁定本地装修业主的普遍痛点（预算、增项、交付担心），用词库表达共鸣；不要写成某一套房的旧况故事",
                "fill_rule": "使用旧房痛点词库描述共性困扰，不编造具体户型缺陷与改造情节",
                "lexicon_calls": ["body.old_house_pain"],
                "fact_source": "lexicon_and_evidence",
            },
            {
                "id": "verified_renovation_data",
                "name": "数据落地铺垫",
                "instruction": "信息卡点写出小区名称、房屋面积、房屋布局（有填才写）、风格、项目施工鸿扬家装；面积等字段原样抄写证据文本；可并列预算与施工项目，禁止展开案例描述；对应事实写入本段 evidence_ids",
                "fill_rule": "只使用 ContentBrief 或 EvidenceBundle 中的真实字段，逐字复制匹配条目的 id；缺失布局则跳过该卡点；禁止把面积区间改成中间值",
                "lexicon_calls": [],
                "fact_source": "evidence",
            },
            {
                "id": "before_after",
                "name": "优势反差展示",
                "instruction": "用服务/交付/工艺优势词库形成反差，不写改造前问题 VS 改造后效果的虚构案例对比",
                "fill_rule": "使用改造优势词库对应开篇痛点，不得虚构效果与户型故事",
                "lexicon_calls": ["body.renovation_advantage"],
                "fact_source": "lexicon_and_evidence",
            },
            {
                "id": "delivery_cta",
                "name": "细节+人设收尾",
                "instruction": "写明鸿扬家居/鸿扬家装品牌优势（定制化家装，禁止整装/标准化整装）与落地背书，并用明确引流点收尾（同城看工艺、咨询、留言）",
                "fill_rule": "使用落地背书词库作短背书，并用案例引导词库收尾；禁止长篇案例叙事",
                "lexicon_calls": ["persona.delivery_endorsement", "ending.case_cta"],
                "fact_source": "lexicon_and_evidence",
            },
        ],
        "variants": [],
        "variation_rule": "痛点、优势与引流表达应轮换，不复制参考案例原句，不编造单套房改造故事",
        "reference_examples": [
            "从本地业主共性痛点切入，用小区、面积、风格与鸿扬家装施工信息卡点增强可信，再写品牌优势并以同城咨询引流收尾。"
        ],
    },
    "C03": {
        "formula_name": "干货人设类：悬念+误区+正解+忠告",
        "lexicon_calls": [
            "body.industry_suspense",
            "body.decoration_misconception",
            "body.professional_answer",
            "persona.craftsman_advice",
        ],
        "sections": [
            {
                "id": "industry_suspense",
                "name": "行业悬念开篇",
                "instruction": "抛出装修内行内幕或隐形细节坑，制造信息差",
                "fill_rule": "使用行业悬念词库勾起好奇，不把无来源数字当作悬念",
                "lexicon_calls": ["body.industry_suspense"],
                "fact_source": "lexicon_and_evidence",
            },
            {
                "id": "owner_misconceptions",
                "name": "业主误区罗列",
                "instruction": "呈现装修新手高频错误做法和认知误区",
                "fill_rule": "使用装修误区词库，并与当前主题保持一致",
                "lexicon_calls": ["body.decoration_misconception"],
                "fact_source": "lexicon",
            },
            {
                "id": "professional_answer",
                "name": "专业正解反差",
                "instruction": "错误做法 VS 标准化施工工艺或正确装修方案",
                "fill_rule": "使用专业正解词库，标准和事实必须有证据支持",
                "lexicon_calls": ["body.professional_answer"],
                "fact_source": "lexicon_and_evidence",
            },
            {
                "id": "craftsman_advice",
                "name": "匠人忠告收尾",
                "instruction": "输出真诚行业价值观和避坑理念，塑造专业可靠人设",
                "fill_rule": "使用匠人忠告词库沉淀人设，不写无法证明的资历",
                "lexicon_calls": ["persona.craftsman_advice"],
                "fact_source": "lexicon_and_evidence",
            },
        ],
        "variants": [],
        "variation_rule": "悬念、误区和忠告表达应轮换，避免多篇正文话术重复",
        "reference_examples": [
            "以内行细节制造悬念，指出新手误区，给出有依据的标准做法，最后用真诚匠人忠告收尾。"
        ],
    },
    "C04": {
        "formula_name": "人设沉淀类：人设+行业痛点+优势+承诺",
        "lexicon_calls": ["persona.stance"],
        "sections": [
            {
                "id": "persona_stance",
                "name": "人设立场开篇",
                "instruction": "亮明本地深耕身份、靠谱施工定位和真实做事立场",
                "fill_rule": "使用人设立场词库；身份和经历必须来自真实资料",
                "lexicon_calls": ["persona.stance"],
                "fact_source": "lexicon_and_evidence",
            },
        ],
        "variants": [],
        "variation_rule": "人设立场必须来自同一真实身份，不拼接不同人物经历",
        "reference_examples": ["亮明本地从业者的真实立场，用真实身份和做事方式建立初始信任。"],
    },
}


def get_decoration_body_calling(formula_code: str) -> dict[str, Any]:
    """返回可冻结进 StrategySnapshot 的正文调用规则。"""

    return deepcopy(DECORATION_BODY_CALLING[formula_code])
