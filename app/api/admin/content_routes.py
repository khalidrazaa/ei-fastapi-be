from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.core.admin_security import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.schemas.content_workflow import TopicInput, TopicEdit, BriefEdit, RunInput, VersionInput, SaveDraftInput, ImportInput
from app.schemas.content_workflow import ResearchSettingsInput, ResearchSettingsResponse
from app.services import content_workflow as service
from app.services import content_research_settings as research_settings_service

def enabled():
    if not settings.CONTENT_WORKFLOW_ENABLED: raise HTTPException(404, 'Content workflow is disabled.')

router = APIRouter(dependencies=[Depends(require_admin), Depends(enabled)])

async def invoke(awaitable):
    try: return await awaitable
    except LookupError as exc: raise HTTPException(404, str(exc)) from exc
    except (service.Conflict, research_settings_service.Conflict) as exc: raise HTTPException(409, str(exc)) from exc
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    except IntegrityError as exc: raise HTTPException(409, 'Concurrent change or duplicate value. Reload and retry.') from exc

@router.get('/content-research-settings', response_model=ResearchSettingsResponse)
async def get_research_settings(db: AsyncSession = Depends(get_db)):
    return await invoke(research_settings_service.get_settings(db))

@router.put('/content-research-settings', response_model=ResearchSettingsResponse)
async def save_research_settings(payload: ResearchSettingsInput, db: AsyncSession = Depends(get_db)):
    return await invoke(research_settings_service.save_settings(db, payload))

@router.get('/content-articles/{article_id}')
async def evidence(article_id: int, db: AsyncSession = Depends(get_db)):
    return await invoke(service.article_workspace(db, article_id))

@router.get('/content-topics')
async def topics(db: AsyncSession = Depends(get_db)):
    return await invoke(service.list_topics(db))

@router.post('/content-topics', status_code=201)
async def create(payload: TopicInput, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.create(db, payload, admin.id))

@router.post('/content-topics/import')
async def import_topics(payload: ImportInput, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.import_csv(db, payload, admin.id))

@router.get('/content-topics/export')
async def export(db: AsyncSession = Depends(get_db)):
    return await invoke(service.export_csv(db))

@router.patch('/content-topics/{topic_id}')
async def edit(topic_id: str, payload: TopicEdit, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.edit(db, topic_id, payload, admin.id))

@router.delete('/content-topics/{topic_id}')
async def delete(topic_id: str, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.delete(db, topic_id, admin.id))

@router.get('/content-topics/{topic_id}/workspace')
async def workspace(topic_id: str, db: AsyncSession = Depends(get_db)):
    return await invoke(service.workspace(db, topic_id))

@router.patch('/content-topics/{topic_id}/workspace')
async def brief(topic_id: str, payload: BriefEdit, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.brief(db, topic_id, payload, admin.id))

@router.post('/content-topics/{topic_id}/runs', status_code=202)
async def start(topic_id: str, payload: RunInput, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.start(db, topic_id, payload, admin.id))

@router.post('/content-runs/{run_id}/cancel')
async def cancel(run_id: str, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.cancel(db, run_id, admin.id))

@router.post('/content-topics/{topic_id}/workspace/versions')
async def version(topic_id: str, payload: VersionInput, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.save_version(db, topic_id, payload, admin.id))

@router.post('/content-topics/{topic_id}/save-draft')
async def save(topic_id: str, payload: SaveDraftInput, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    return await invoke(service.save_draft(db, topic_id, payload, admin.id))
