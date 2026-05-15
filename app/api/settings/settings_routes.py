from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.draft_prompt import (
    DraftPromptCreate,
    DraftPromptResponse,
    DraftPromptUpdate,
)
from app.schemas.host_site import (
    HostSiteCreate,
    HostSiteResponse,
    HostSiteUpdate,
)
from app.schemas.public_api_key import (
    PublicApiKeyGenerateRequest,
    PublicApiKeyGenerateResponse,
    PublicApiKeyResponse,
)
from app.services.draft_prompt import (
    create_draft_prompt,
    delete_draft_prompt,
    get_draft_prompts,
    update_draft_prompt,
)
from app.services.host_site import (
    create_host_site,
    delete_host_site,
    get_host_sites,
    update_host_site,
)
from app.services.public_api_key import (
    generate_public_api_key,
    get_public_api_keys,
    revoke_public_api_key,
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


@router.get("/host-sites", response_model=list[HostSiteResponse])
async def get_host_sites_route(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    return await get_host_sites(db=db, active_only=active_only)


@router.post("/host-sites", response_model=HostSiteResponse)
async def create_host_site_route(
    payload: HostSiteCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_host_site(
            db=db,
            host=payload.host,
            is_active=payload.is_active,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/host-sites/{host_site_id}", response_model=HostSiteResponse)
async def update_host_site_route(
    host_site_id: int,
    payload: HostSiteUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await update_host_site(
            db=db,
            host_site_id=host_site_id,
            host=payload.host,
            is_active=payload.is_active,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/host-sites/{host_site_id}", status_code=204)
async def delete_host_site_route(
    host_site_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_host_site(db=db, host_site_id=host_site_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/public-api-keys", response_model=list[PublicApiKeyResponse])
async def get_public_api_keys_route(
    active_only: bool = False,
    host: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_public_api_keys(
            db=db,
            active_only=active_only,
            host=host,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/public-api-keys/generate", response_model=PublicApiKeyGenerateResponse)
async def generate_public_api_key_route(
    payload: PublicApiKeyGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await generate_public_api_key(
            db=db,
            host=payload.host,
            name=payload.name,
            deactivate_old_keys=payload.deactivate_old_keys,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/public-api-keys/{api_key_id}/revoke", response_model=PublicApiKeyResponse)
async def revoke_public_api_key_route(
    api_key_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await revoke_public_api_key(db=db, api_key_id=api_key_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
