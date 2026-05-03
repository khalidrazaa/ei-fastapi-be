from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.draft_prompt import (
    DraftPromptCreate,
    DraftPromptResponse,
    DraftPromptUpdate,
)
from app.services.draft_prompt import (
    create_draft_prompt,
    delete_draft_prompt,
    get_draft_prompts,
    update_draft_prompt,
)

router = APIRouter()


@router.get("/draft-prompts", response_model=list[DraftPromptResponse])
async def get_draft_prompts_route(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    return await get_draft_prompts(db=db, active_only=active_only)


@router.post("/draft-prompts", response_model=DraftPromptResponse)
async def create_draft_prompt_route(
    payload: DraftPromptCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_draft_prompt(
            db=db,
            name=payload.name,
            prompt=payload.prompt,
            is_active=payload.is_active,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/draft-prompts/{prompt_id}", response_model=DraftPromptResponse)
async def update_draft_prompt_route(
    prompt_id: int,
    payload: DraftPromptUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await update_draft_prompt(
            db=db,
            prompt_id=prompt_id,
            name=payload.name,
            prompt=payload.prompt,
            is_active=payload.is_active,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/draft-prompts/{prompt_id}", status_code=204)
async def delete_draft_prompt_route(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_draft_prompt(db=db, prompt_id=prompt_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
