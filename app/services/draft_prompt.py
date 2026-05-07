from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import draft_prompt as draft_prompt_query


def _normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


async def get_draft_prompts(
    db: AsyncSession,
    *,
    active_only: bool = False,
) -> object:
    return await draft_prompt_query.get_draft_prompts(
        db,
        active_only=active_only,
    )


async def create_draft_prompt(
    db: AsyncSession,
    *,
    name: str,
    prompt: str,
    is_active: bool = True,
) -> object:
    return await draft_prompt_query.create_draft_prompt(
        db,
        name=_normalize_required_text(name, "Name"),
        prompt=_normalize_required_text(prompt, "Prompt"),
        is_active=is_active,
    )


async def update_draft_prompt(
    db: AsyncSession,
    prompt_id: int,
    *,
    name: str | None = None,
    prompt: str | None = None,
    is_active: bool | None = None,
) -> object:
    draft_prompt = await draft_prompt_query.get_draft_prompt_by_id(db, prompt_id)
    if draft_prompt is None:
        raise LookupError("Prompt not found.")

    return await draft_prompt_query.update_draft_prompt(
        db,
        draft_prompt,
        name=_normalize_required_text(name, "Name") if name is not None else None,
        prompt=(
            _normalize_required_text(prompt, "Prompt")
            if prompt is not None
            else None
        ),
        is_active=is_active,
    )


async def delete_draft_prompt(
    db: AsyncSession,
    prompt_id: int,
) -> None:
    draft_prompt = await draft_prompt_query.get_draft_prompt_by_id(db, prompt_id)
    if draft_prompt is None:
        raise LookupError("Prompt not found.")

    await draft_prompt_query.delete_draft_prompt(db, draft_prompt)
