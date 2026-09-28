import json

from alembic import op
from sqlalchemy import text

revision = "0003_channel_model_mapping_names"
down_revision = "0002_drop_channel_provider_type"
branch_labels = None
depends_on = None


def _convert_model_mapping(mapping: object) -> dict[str, str]:
    if not isinstance(mapping, dict):
        return {}
    converted: dict[str, str] = {}
    for name, value in mapping.items():
        if not isinstance(name, str) or not name:
            continue
        if isinstance(value, str):
            converted[name] = value
            continue
        if not isinstance(value, dict):
            continue
        model = value.get("model")
        if isinstance(model, str):
            converted[name] = model
            continue
        fields = value.get("fields")
        if not isinstance(fields, list):
            continue
        for field in fields:
            if not isinstance(field, dict) or field.get("target") != "model":
                continue
            fixed = field.get("fixed")
            if isinstance(fixed, str):
                converted[name] = fixed
                break
    return converted


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    rows = bind.execute(text("SELECT id, model_mapping FROM channels")).all()
    for channel_id, mapping in rows:
        converted = _convert_model_mapping(mapping)
        if converted != mapping:
            bind.execute(
                text("UPDATE channels SET model_mapping = CAST(:mapping AS jsonb) WHERE id = :channel_id"),
                {"channel_id": channel_id, "mapping": json.dumps(converted)},
            )


def downgrade() -> None:
    return None
