from pydantic import ValidationError

import pytest

from yuxi.services.variable_service import SERVICE_ENTRIES, VariableCreate, VariableUpdate, next_variable_code


def test_variable_create_schema_requires_name_and_service_entry():
    with pytest.raises(ValidationError):
        VariableCreate(name="", service_entry="好评笔记")
    with pytest.raises(ValidationError):
        VariableCreate(name="设计师", service_entry="")


def test_variable_update_schema_allows_partial_enabled():
    payload = VariableUpdate(enabled=False)
    assert payload.model_dump(exclude_unset=True) == {"enabled": False}


def test_next_variable_code_increments_fwtd_sequence():
    assert next_variable_code([]) == "FWTD0001"
    assert next_variable_code(["FWTD0001", "FWTD0005", "OTHER01"]) == "FWTD0006"
    assert next_variable_code(["FWTD0009"]) == "FWTD0010"


def test_service_entries_are_home_and_review_notes():
    assert SERVICE_ENTRIES == ("装修家居", "好评笔记")
