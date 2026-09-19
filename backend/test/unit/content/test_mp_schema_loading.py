from __future__ import annotations

import pytest

from yuxi.services import mp_service


class _EmptyCoverRepository:
    def __init__(self, _db) -> None:
        pass

    async def list_enabled(self) -> list:
        return []


@pytest.mark.asyncio
async def test_form_schema_can_skip_hycanvas_for_first_screen(monkeypatch):
    async def no_op(*_args, **_kwargs):
        return None

    async def empty_bindings(*_args, **_kwargs):
        return {"business_variables": []}

    async def empty_types(*_args, **_kwargs):
        return {"content_types": []}

    async def empty_list(*_args, **_kwargs):
        return []

    async def empty_process_names(*_args, **_kwargs):
        return {}

    async def unexpected_hycanvas_load():
        raise AssertionError("first-screen schema must not wait for HyCanvas")

    monkeypatch.setattr(mp_service, "ensure_default_content_types", no_op)
    monkeypatch.setattr(mp_service, "ensure_default_variables", no_op)
    monkeypatch.setattr(mp_service, "list_business_variables", empty_bindings)
    monkeypatch.setattr(mp_service, "list_content_types", empty_types)
    monkeypatch.setattr(mp_service, "list_enabled_target_audience_names", empty_list)
    monkeypatch.setattr(mp_service, "list_enabled_resident_population_names", empty_list)
    monkeypatch.setattr(mp_service, "list_enabled_process_type_names", empty_list)
    monkeypatch.setattr(mp_service, "list_enabled_process_names_by_type", empty_process_names)
    monkeypatch.setattr(mp_service, "CoverRepository", _EmptyCoverRepository)
    monkeypatch.setattr(mp_service, "_list_mp_hycanvas_templates", unexpected_hycanvas_load)

    schema = await mp_service.get_form_schema(None, "装修家居", include_hycanvas_templates=False)

    assert schema["hycanvas_templates"] == []


@pytest.mark.asyncio
async def test_hycanvas_templates_are_available_from_the_background_endpoint_service(monkeypatch):
    async def fake_hycanvas_load():
        return [{"id": "xiaohongshu-template"}]

    monkeypatch.setattr(mp_service, "_list_mp_hycanvas_templates", fake_hycanvas_load)

    assert await mp_service.list_hycanvas_templates() == {"hycanvas_templates": [{"id": "xiaohongshu-template"}]}
