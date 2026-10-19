"""Run separately: python -m app.services.content_worker. Does not start scan jobs."""
import asyncio
import logging
from uuid import uuid4
from openai import APIStatusError
from app.db.session import SessionLocal
from app.db.query import content_workflow as q
from app.db.models.content_workflow import ContentRun, ContentVersion, ContentQA, now
from app.services.content_ai import ContentAI
from app.services.content_gemini import GeminiContentAI
from app.services.content_research_defaults import snapshot_research_settings

logger = logging.getLogger(__name__)

async def perform(job, ai):
    if job.stage == 'research': return await ai.research(job.inputs)
    if job.stage in ['generate', 'fix']:
        return {'payload': await ai.write(job.inputs, job.stage == 'fix'), 'usage': ai.usage}
    return await ai.qa(job.inputs['payload'], job.inputs['research'])

async def finish(db, job_id, token, result=None, error=None):
    job = await q.run(db, job_id, True)
    if not job or job.status != 'running' or job.lease_token != token: return
    topic = await q.topic(db, job.topic_id, True)
    if job.cancel_requested:
        job.status = 'cancelled'
    elif topic.brief_version != job.inputs['brief_version']:
        job.status, job.error = 'failed', 'Brief changed; result discarded. Start a new run.'
    elif error:
        job.status, job.error = 'failed', error
        # Failure diagnostics retain usage metadata, never partial content.
        job.result = (
            {'usage': result['usage']}
            if isinstance(result, dict) and result.get('usage') else None
        )
    else:
        job.status, job.result, job.error = 'completed', result, None
        if job.stage == 'research':
            if result['ready'] and not topic.article_id: topic.status = 'Researched'
        elif job.stage in ['generate','fix']:
            version = await q.add(db, ContentVersion(topic_id=topic.topic_id, run_id=job.id,
                research_id=job.inputs['research_id'], brief_version=topic.brief_version, payload=result['payload']))
            # Release unique active-run slot before inserting auto-QA in this transaction.
            await db.flush()
            await q.add(db, ContentRun(id=str(uuid4()), topic_id=topic.topic_id, stage='qa',
                request_key=f'qa-{version.id}', inputs={**job.inputs, 'payload': version.payload, 'version_id': version.id,
                    'research_settings': snapshot_research_settings(job.inputs)}))
        elif job.stage == 'qa':
            await q.add(db, ContentQA(version_id=job.inputs['version_id'], report=result))
        topic.version += 1
    job.finished_at = now()
    job.lease_until = None
    await q.commit(db)

async def tick():
    async with SessionLocal() as db:
        job = await q.claim(db)
    if not job: return False
    result, error, ai = None, None, None
    try:
        ai = GeminiContentAI() if job.inputs.get('provider', 'openai') == 'gemini' else ContentAI()
        # Less than the ten-minute lease; process crashes are recovered by claim().
        result = await asyncio.wait_for(perform(job, ai), timeout=480)
    except Exception as exc:
        logger.warning('Content run %s failed (%s)', job.id, type(exc).__name__)
        error = str(exc) if isinstance(exc, ValueError) else f'{type(exc).__name__}: provider or worker unavailable. Check configuration and retry.'
        if isinstance(exc, APIStatusError):
            body = exc.body if isinstance(exc.body, dict) else {}
            detail = body.get('error', body)
            detail = detail if isinstance(detail, dict) else {}
            if detail.get('code') in {'insufficient_quota', 'credit_balance_exhausted'} or detail.get('type') == 'insufficient_quota':
                error = 'OpenAI API credit or quota is exhausted. Restore API credit/quota for the configured key, then retry this stage.'
            elif exc.status_code == 429:
                error = 'OpenAI rate limit reached. Wait briefly, then retry this stage.'
        if ai and ai.usage:
            result = {'usage': ai.usage}
    finally:
        if ai: await ai.close()
    async with SessionLocal() as db:
        await finish(db, job.id, job.lease_token, result, error)
    return True

async def main():
    while True:
        try:
            busy = await tick()
        except Exception as exc:
            logger.warning('Worker database check failed (%s)', type(exc).__name__)
            busy = False
        await asyncio.sleep(1 if busy else 5)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
