from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, text
from app.db.models.article import Article
from app.db.models.content_workflow import ContentTopic, ContentRun, ContentVersion, ContentQA, ContentAudit, TopicIdentifier, ContentResearchSettings, now

async def research_settings(db, lock=False):
    stmt = select(ContentResearchSettings).where(ContentResearchSettings.id == 1)
    if lock:
        # Refresh an already-loaded row after waiting for another editor's lock.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()

async def topic(db, topic_id, lock=False):
    stmt = select(ContentTopic).where(ContentTopic.topic_id == topic_id)
    return (await db.execute(stmt.with_for_update() if lock else stmt)).scalar_one_or_none()

async def topics(db):
    return list((await db.execute(select(ContentTopic).order_by(ContentTopic.priority.desc(), ContentTopic.topic_id))).scalars())

async def articles(db):
    return list((await db.execute(select(Article))).scalars())

async def article(db, article_id, lock=False):
    if not article_id: return None
    stmt = select(Article).where(Article.id == article_id)
    return (await db.execute(stmt.with_for_update() if lock else stmt)).scalar_one_or_none()

async def reserve_id(db, number=None):
    # Shared with imports. Registry rows survive topic deletion.
    await db.execute(text('SELECT pg_advisory_xact_lock(7140921)'))
    if number is not None:
        if await db.get(TopicIdentifier, number):
            raise ValueError('Topic ID was previously allocated and cannot be reused.')
        record = TopicIdentifier(id=number)
    else:
        record = TopicIdentifier()
    db.add(record)
    await db.flush()
    if number is not None:
        await db.execute(text("SELECT setval(pg_get_serial_sequence('content_topic_identifiers','id'), (SELECT max(id) FROM content_topic_identifiers))"))
    return f'EXPLAINIT-{record.id:03d}'

async def runs(db, topic_id):
    return list((await db.execute(select(ContentRun).where(ContentRun.topic_id == topic_id).order_by(ContentRun.created_at.desc()).limit(100))).scalars())

async def active(db, topic_id):
    return (await db.execute(select(ContentRun).where(ContentRun.topic_id == topic_id, ContentRun.status.in_(['queued','running'])))).scalar_one_or_none()

async def by_key(db, key):
    return (await db.execute(select(ContentRun).where(ContentRun.request_key == key))).scalar_one_or_none()

async def run(db, run_id, lock=False):
    stmt = select(ContentRun).where(ContentRun.id == run_id)
    return (await db.execute(stmt.with_for_update() if lock else stmt)).scalar_one_or_none()

async def versions(db, topic_id):
    return list((await db.execute(select(ContentVersion).where(ContentVersion.topic_id == topic_id).order_by(ContentVersion.id.desc()))).scalars())

async def version(db, version_id):
    return await db.get(ContentVersion, version_id) if version_id else None

async def reports(db, version_ids):
    if not version_ids: return []
    return list((await db.execute(select(ContentQA).where(ContentQA.version_id.in_(version_ids)).order_by(ContentQA.id.desc()))).scalars())

async def add(db, obj):
    db.add(obj)
    await db.flush()
    return obj

async def remove(db, obj):
    await db.delete(obj)

async def audit(db, topic_id, actor, action, details=None):
    db.add(ContentAudit(topic_id=topic_id, actor=str(actor), action=action, details=details or {}))

async def commit(db): await db.commit()

async def claim(db):
    # Expired attempts may be reclaimed; fencing tokens prevent stale writes.
    expired = list((await db.execute(select(ContentRun).where(ContentRun.status == 'running', ContentRun.lease_until < now()).with_for_update(skip_locked=True))).scalars())
    for job in expired:
        job.status = 'cancelled' if job.cancel_requested else ('failed' if job.attempts >= 3 else 'queued')
        job.error = 'Worker lease expired. Retry the stage if necessary.'
        job.lease_token = None
    await db.flush()
    job = (await db.execute(select(ContentRun).where(ContentRun.status == 'queued').order_by(ContentRun.created_at).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
    if job:
        job.status = 'running'
        job.attempts += 1
        job.lease_token = str(uuid4())
        job.lease_until = now() + timedelta(minutes=10)
    await db.commit()
    return job

async def generated_topic_ids(db):
    return set((await db.execute(select(ContentVersion.topic_id).distinct())).scalars())
