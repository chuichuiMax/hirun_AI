from pydantic import ValidationError

import pytest

from yuxi.services.business_variable_service import (
    BusinessVariableCreate,
    BusinessVariableUpdate,
    _normalize_ports,
)


def test_business_variable_create_requires_variable_id():
    with pytest.raises(ValidationError):
        BusinessVariableCreate(service_entry="装修家居", content_type_id="t1", variable_id="")


def test_decoration_requires_content_type():
    with pytest.raises(ValidationError):
        BusinessVariableCreate(service_entry="装修家居", content_type_id=None, variable_id="var-1")


def test_review_notes_skips_content_type():
    payload = BusinessVariableCreate(service_entry="好评笔记", content_type_id=None, variable_id="var-1")
    assert payload.content_type_id is None
    assert payload.required is True
    assert payload.enabled is True


def test_review_notes_clears_provided_content_type():
    payload = BusinessVariableCreate(
        service_entry="好评笔记",
        content_type_id="type-should-ignore",
        variable_id="var-1",
    )
    assert payload.content_type_id is None


def test_business_variable_update_allows_partial_fields():
    payload = BusinessVariableUpdate(enabled=False)
    assert payload.model_dump(exclude_unset=True) == {"enabled": False}


def test_business_variable_create_defaults_ports():
    payload = BusinessVariableCreate(service_entry="好评笔记", variable_id="var-1")
    assert payload.ports == ["pc", "app"]


def test_business_variable_create_rejects_empty_ports():
    with pytest.raises(ValidationError):
        BusinessVariableCreate(service_entry="好评笔记", variable_id="var-1", ports=[])


def test_normalize_ports_keeps_order():
    assert _normalize_ports(["app", "pc"]) == ["pc", "app"]
