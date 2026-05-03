from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.draft_prompt import DraftPrompt


async def get_draft_prompts(
    db: AsyncSession,
    *,
    active_only: bool = False,
) -> list[DraftPrompt]:
    query = select(DraftPrompt).order_by(DraftPrompt.created_at.desc(), DraftPrompt.id.desc())
    if active_only:
        query = query.where(DraftPrompt.is_active.is_(True))

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_draft_prompt_by_id(
    db: AsyncSession,
    prompt_id: int,
) -> DraftPrompt | None:
    result = await db.execute(select(DraftPrompt).where(DraftPrompt.id == prompt_id))
    return result.scalar_one_or_none()


async def create_draft_prompt(
    db: AsyncSession,
    *,
    name: str,
    prompt: str,
    is_active: bool,
) -> DraftPrompt:
    draft_prompt = DraftPrompt(name=name, prompt=prompt, is_active=is_active)
    db.add(draft_prompt)
    await db.commit()
    await db.refresh(draft_prompt)
    return draft_prompt


async def update_draft_prompt(
    db: AsyncSession,
    draft_prompt: DraftPrompt,
    *,
    name: str | None = None,
    prompt: str | None = None,
    is_active: bool | None = None,
) -> DraftPrompt:
    if name is not None:
        draft_prompt.name = name
    if prompt is not None:
        draft_prompt.prompt = prompt
    if is_active is not None:
        draft_prompt.is_active = is_active

    await db.commit()
    await db.refresh(draft_prompt)
    return draft_prompt


async def delete_draft_prompt(
    db: AsyncSession,
    draft_prompt: DraftPrompt,
) -> None:
    await db.delete(draft_prompt)
    await db.commit()
