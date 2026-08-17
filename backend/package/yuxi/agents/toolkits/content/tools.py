from __future__ import annotations

from typing import Any

from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field
from sqlalchemy import select

from yuxi.agents.toolkits.registry import tool
from yuxi.content.rules import validate_strategy_bundle
from yuxi.content.validators import normalize_manual_evidence, validate_content
from yuxi.repositories.content_repository import ContentRepository
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User


class RuleBundleInput(BaseModel):
    rule_version_id: str = Field(description="任务锁定的创作规则版本 ID")


class CombinationInput(BaseModel):
    rule_version_id: str
    content_goal: str
    methods: list[str]
    title_formula_code: str
    content_formula_code: str
    brief: dict[str, Any]


class TaskFactsInput(BaseModel):
    task_id: str


class TaskOCRInput(BaseModel):
    task_id: str = Field(description="需要读取 OCR 结果的内容任务 ID")


class NormalizeEvidenceInput(BaseModel):
    task_id: str
    brief: dict[str, Any]


class ValidateFactsInput(BaseModel):
    title: str
    body: str
    topics: list[str] = Field(default_factory=list)
    brief: dict[str, Any]
    evidence_bundle: dict[str, Any]
    strategy: dict[str, Any]


def _runtime_uid(runtime: ToolRuntime | None) -> str:
    uid = getattr(getattr(runtime, "context", None), "uid", None)
    if not uid:
        raise ValueError("无法获取当前用户")
    return str(uid)


@tool(
    category="buildin",
    tags=["内容生产", "规则"],
    display_name="读取创作规则包",
    args_schema=RuleBundleInput,
)
async def get_creation_rule_bundle(rule_version_id: str, runtime: ToolRuntime = None) -> dict[str, Any]:
    """读取指定版本的创作手法、标题公式、正文公式和组合规则。"""
    _runtime_uid(runtime)
    async with pg_manager.get_async_session_context() as db:
        bundle = await ContentRepository(db).get_rule_bundle(rule_version_id)
        if bundle is None:
            raise ValueError("规则版本不存在")
        return bundle


@tool(
    category="buildin",
    tags=["内容生产", "规则"],
    display_name="校验内容公式组合",
    args_schema=CombinationInput,
)
async def validate_formula_combination(
    rule_version_id: str,
    content_goal: str,
    methods: list[str],
    title_formula_code: str,
    content_formula_code: str,
    brief: dict[str, Any],
    runtime: ToolRuntime = None,
) -> dict[str, Any]:
    """确定性校验创作手法、标题公式、正文公式与内容目标。"""
    _runtime_uid(runtime)
    async with pg_manager.get_async_session_context() as db:
        bundle = await ContentRepository(db).get_rule_bundle(rule_version_id)
        if bundle is None:
            raise ValueError("规则版本不存在")
        return validate_strategy_bundle(
            bundle,
            brief=brief,
            content_goal=content_goal,
            methods=methods,
            title_formula_code=title_formula_code,
            content_formula_code=content_formula_code,
        )


@tool(
    category="buildin",
    tags=["内容生产", "业务事实"],
    display_name="读取内容任务业务事实",
    args_schema=TaskFactsInput,
)
async def get_business_facts(task_id: str, runtime: ToolRuntime = None) -> dict[str, Any]:
    """读取当前用户可访问任务中已经冻结的业务事实和证据包。"""
    uid = _runtime_uid(runtime)
    async with pg_manager.get_async_session_context() as db:
        user = (await db.execute(select(User).where(User.uid == uid))).scalar_one_or_none()
        if user is None:
            raise ValueError("用户不存在")
        task = await ContentRepository(db).get_task_for_user(task_id, user)
        if task is None:
            raise ValueError("内容任务不存在或无权访问")
        return {
            "task_id": task.id,
            "brief": task.brief_json or {},
            "evidence_bundle": task.evidence_json or {"items": []},
        }


@tool(
    category="buildin",
    tags=["内容生产", "OCR", "业务素材"],
    display_name="读取内容任务 OCR 结果",
    args_schema=TaskOCRInput,
)
async def get_content_ocr_results(task_id: str, runtime: ToolRuntime = None) -> dict[str, Any]:
    """读取当前用户可访问内容任务中已持久化的 OCR 原始结果和校对结果。"""
    uid = _runtime_uid(runtime)
    async with pg_manager.get_async_session_context() as db:
        user = (await db.execute(select(User).where(User.uid == uid))).scalar_one_or_none()
        if user is None:
            raise ValueError("用户不存在")
        repo = ContentRepository(db)
        task = await repo.get_task_for_user(task_id, user)
        if task is None:
            raise ValueError("内容任务不存在或无权访问")
        items = await repo.list_ocr_results(task.id)
        return {"task_id": task.id, "items": [item.to_dict() for item in items]}


@tool(
    category="buildin",
    tags=["内容生产", "证据"],
    display_name="标准化内容证据",
    args_schema=NormalizeEvidenceInput,
)
async def normalize_content_evidence(
    task_id: str, brief: dict[str, Any], runtime: ToolRuntime = None
) -> dict[str, Any]:
    """把业务简报标准化为带稳定来源的 EvidenceBundle。"""
    _runtime_uid(runtime)
    return normalize_manual_evidence(task_id, brief)


@tool(
    category="buildin",
    tags=["内容生产", "审核"],
    display_name="校验内容事实",
    args_schema=ValidateFactsInput,
)
async def validate_content_facts(
    title: str,
    body: str,
    topics: list[str],
    brief: dict[str, Any],
    evidence_bundle: dict[str, Any],
    strategy: dict[str, Any],
    runtime: ToolRuntime = None,
) -> dict[str, Any]:
    """确定性校验数字来源、禁止表达、必含词和策略快照。"""
    _runtime_uid(runtime)
    return validate_content(
        title=title,
        body=body,
        topics=topics,
        brief=brief,
        evidence_bundle=evidence_bundle,
        strategy=strategy,
    )
