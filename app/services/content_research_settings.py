"""Persistence and optimistic editing of reusable research preferences."""

from copy import deepcopy

from app.db.models.content_workflow import ContentResearchSettings
from app.db.query import content_workflow as q
from app.services.content_research_defaults import default_research_settings


class Conflict(ValueError):
    pass


def settings_view(item):
    return {
        "version": item.version,
        "instructions": item.instructions,
        "source_groups": deepcopy(item.source_groups),
    }


async def get_settings(db):
    item = await q.research_settings(db)
    return settings_view(item) if item else default_research_settings()


async def save_settings(db, payload):
    item = await q.research_settings(db, lock=True)
    if (item.version if item else 0) != payload.expected_version:
        raise Conflict("Research settings changed. Reload before saving.")
    values = payload.model_dump(exclude={"expected_version"})
    if item:
        item.instructions = values["instructions"]
        item.source_groups = values["source_groups"]
        item.version += 1
    else:
        item = await q.add(
            db, ContentResearchSettings(id=1, version=1, **values)
        )
    await q.commit(db)
    return settings_view(item)
