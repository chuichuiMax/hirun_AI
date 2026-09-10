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
        "formula_name": "报价转化类：痛点+数据+反差+背书",
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
                "instruction": "锁定本地装修业主，聚焦装修预算、报价核心困扰，直击业主刚需痛点",
                "fill_rule": "仅使用预算痛点词库描述业主普遍报价、预算困扰",
                "lexicon_calls": ["body.budget_pain"],
                "fact_source": "lexicon",
            },
            {
                "id": "verified_data",
                "name": "数据落地铺垫",
                "instruction": "用简报信息卡点写出小区名称、房屋面积、房屋布局（有填才写）、风格、项目施工鸿扬家装；可并列整体预算，不展开某套房案例故事",
                "fill_rule": "只使用 ContentBrief 或 EvidenceBundle 中的真实数据，不调用词库补造数字，不编造布局与改造细节",
                "lexicon_calls": [],
                "fact_source": "evidence",
            },
            {
                "id": "single_contrast",
                "name": "多维度前后反差展示",
                "instruction": "四选一且单篇只使用一种反差逻辑，禁止混用；反差讲服务/预算/认知/代价，不讲虚构户型改造前后故事",
                "fill_rule": "按所选反差维度使用对应词库，保持统一正反对比逻辑",
                "lexicon_calls": [],
                "fact_source": "lexicon_and_evidence",
            },
            {
                "id": "persona_cta",
                "name": "细节+人设收尾引导",
                "instruction": "点明鸿扬家居/鸿扬家装品牌优势，结合透明施工细节与明确引流点（同城咨询、报价参考、留言私信）",
                "fill_rule": "使用服务反差词库输出优势，并用报价引导词库完成转化",
                "lexicon_calls": ["persona.service_contrast", "ending.quotation_cta"],
                "fact_source": "lexicon_and_evidence",
            },
        ],
        "variants": [
            {
                "id": "service_contrast",
                "name": "服务反差",
                "instruction": "行业乱象套路 VS 我方透明施工服务",
                "lexicon_calls": ["body.quotation_chaos", "persona.service_contrast"],
            },
            {
                "id": "budget_contrast",
                "name": "预算反差",
                "instruction": "业主理想化预算预期 VS 实际装修超支现状",
                "lexicon_calls": ["body.owner_expectation_gap", "body.budget_contrast"],
            },
            {
                "id": "cognitive_contrast",
                "name": "认知反差",
                "instruction": "业主错误报价认知 VS 专业正规报价逻辑",
                "lexicon_calls": ["body.quotation_cognitive_contrast"],
            },
            {
                "id": "cost_contrast",
                "name": "代价反差",
                "instruction": "盲目低价签约的踩坑代价 VS 规范报价的省钱优势",
                "lexicon_calls": ["body.cost_result"],
            },
        ],
        "variation_rule": "不同正文轮换反差维度和表达，单篇不得混用多个反差维度",
        "reference_examples": [
            "很多业主装修都会遇到预算问题；用小区、面积、风格与施工方信息卡点说明，再以品牌优势和同城报价咨询收尾。"
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
                "instruction": "信息卡点写出小区名称、房屋面积、房屋布局（有填才写）、风格、项目施工鸿扬家装；可并列预算与施工项目，禁止展开案例描述",
                "fill_rule": "只使用 ContentBrief 或 EvidenceBundle 中的真实字段，缺失布局则跳过该卡点",
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
                "instruction": "写明鸿扬家居/鸿扬家装品牌优势与落地背书，并用明确引流点收尾（同城看工艺、咨询、留言）",
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
