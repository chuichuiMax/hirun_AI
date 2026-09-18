from __future__ import annotations

from yuxi.storage.postgres.manager import material_gallery_role_migration_statements
from yuxi.storage.postgres.models_content import ContentMaterialCategory


def _normalized(sql: str) -> str:
    return " ".join(sql.split())


def test_material_gallery_role_migration_is_strict_atomic_and_ordered():
    statements = material_gallery_role_migration_statements()
    sql = [_normalized(statement) for statement in statements]

    assert sql[0] == (
        "ALTER TABLE IF EXISTS content_material_categories "
        "ADD COLUMN IF NOT EXISTS image_design_role VARCHAR(20)"
    )
    assert "LOCK TABLE content_material_categories IN SHARE ROW EXCLUSIVE MODE" in sql[1]
    assert "name = '案例图库'" in sql[1]
    assert "name IN ('毛坯房图库', '毛坯图库')" in sql[1]
    assert "expected exactly one enterprise case gallery, found %" in sql[1]
    assert "expected exactly one enterprise rough gallery, found %" in sql[1]
    assert "expected exactly one active enterprise reference gallery role, found %" in sql[1]
    assert "expected exactly one active enterprise rough gallery role, found %" in sql[1]
    assert "ck_content_material_category_image_design_role" in sql[2]
    assert "CHECK (image_design_role IS NULL OR image_design_role IN ('reference', 'rough'))" in sql[2]
    assert sql[3].startswith(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_content_material_category_image_design_role_active"
    )


def test_material_gallery_role_migration_does_not_rebind_existing_roles_by_name():
    migration_sql = _normalized(material_gallery_role_migration_statements()[1])

    assert "IF NOT EXISTS" in migration_sql
    assert "image_design_role = 'reference'" in migration_sql
    assert "image_design_role = 'rough'" in migration_sql
    assert migration_sql.index("IF NOT EXISTS") < migration_sql.index("name = '案例图库'")


def test_material_gallery_role_is_persisted_independently_of_name():
    category = ContentMaterialCategory(
        owner_uid="owner-1",
        material_type="image",
        id="gallery-reference",
        visibility="enterprise",
        image_design_role="reference",
        name="案例图库",
    )

    category.name = "案例图库（已改名）"

    assert category.to_dict()["image_design_role"] == "reference"
