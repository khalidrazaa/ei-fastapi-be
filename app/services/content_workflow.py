import csv
import io
import re
from uuid import uuid4
from app.db.query import content_workflow as q
from app.db.models.article import Article
from app.db.models.content_workflow import ContentTopic, ContentRun, ContentVersion, now
from app.schemas.content_workflow import TopicInput, DraftPayload
from app.services.content_policy import fingerprint, overlaps

class Conflict(ValueError): pass

def row(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

async def require_topic(db, topic_id, expected=None, editable=False):
    item = await q.topic(db, topic_id, lock=editable)
    if not item: raise LookupError('Topic not found.')
    if expected is not None and item.version != expected: raise Conflict('Topic changed. Reload before continuing.')
    if editable and await q.active(db, topic_id): raise Conflict('A job is active. Cancel it or wait for completion.')
    return item

def topic_view(item, article=None):
    data = row(item)
    data['published_url'] = None
    if article:
        data['status'] = 'Published' if article.status == 'published' else 'Drafted'
        if article.status == 'published': data['published_url'] = f'https://{article.host_site}/articles/{article.slug}'
    elif item.status == 'Drafted' and item.saved_version_id:
        data['status'] = 'Researched'  # linked article was deleted; workspace survives
    return data

async def list_topics(db):
    articles = {x.id: x for x in await q.articles(db)}
    generated = await q.generated_topic_ids(db)
    return [dict(topic_view(x, articles.get(x.article_id)), has_generated=x.topic_id in generated) for x in await q.topics(db)]

async def create(db, payload, actor):
    item = ContentTopic(topic_id=await q.reserve_id(db), **payload.model_dump())
    await q.add(db, item)
    await q.audit(db, item.topic_id, actor, 'created')
    await q.commit(db)
    return row(item)

async def edit(db, topic_id, payload, actor):
    item = await require_topic(db, topic_id, payload.expected_version, True)
    changed_scope = item.title != payload.title or item.reader_question != payload.reader_question
    for key, value in payload.model_dump(exclude={'expected_version'}).items(): setattr(item, key, value)
    item.version += 1
    if changed_scope:
        item.brief_version += 1
        if not item.article_id: item.status = 'Idea'
    await q.audit(db, topic_id, actor, 'edited', {'version': item.version})
    await q.commit(db)
    return row(item)

async def delete(db, topic_id, actor):
    item = await require_topic(db, topic_id, editable=True)
    if item.article_id or await q.runs(db, topic_id) or await q.versions(db, topic_id):
        raise Conflict('This topic has saved work. Archive it instead.')
    await q.audit(db, topic_id, actor, 'deleted', {'title': item.title})
    await q.remove(db, item)
    await q.commit(db)
    return {'deleted': topic_id}

async def workspace(db, topic_id):
    item = await require_topic(db, topic_id)
    article = await q.article(db, item.article_id)
    versions = await q.versions(db, topic_id)
    candidates = [(x.topic_id, x.title, x.reader_question) for x in await q.topics(db) if x.topic_id != topic_id]
    candidates += [(f'article-{x.id}', x.title, '') for x in await q.articles(db) if x.id != item.article_id]
    return {'topic': topic_view(item, article), 'runs': [row(x) for x in await q.runs(db, topic_id)],
            'versions': [row(x) for x in versions], 'qa': [row(x) for x in await q.reports(db, [v.id for v in versions])],
            'article': row(article) if article else None, 'article_fingerprint': fingerprint(article), 'article_status': article.status if article else None,
            'overlaps': overlaps(item.title, item.reader_question, candidates)}

async def article_workspace(db, article_id):
    item = next((t for t in await q.topics(db) if t.article_id == article_id), None)
    return await workspace(db, item.topic_id) if item else None

async def brief(db, topic_id, payload, actor):
    item = await require_topic(db, topic_id, payload.expected_version, True)
    if item.archived: raise Conflict('Restore this topic first.')
    item.brief = payload.brief.model_dump()
    item.brief_version += 1
    item.version += 1
    if not item.article_id: item.status = 'Briefed'
    await q.audit(db, topic_id, actor, 'brief_saved')
    await q.commit(db)
    return row(item)

async def start(db, topic_id, payload, actor):
    previous = await q.by_key(db, payload.request_key)
    if previous:
        if previous.topic_id != topic_id or previous.stage != payload.stage: raise Conflict('Request key belongs to another operation.')
        return row(previous)
    item = await require_topic(db, topic_id, payload.expected_version, True)
    if item.archived or not item.brief: raise Conflict('Restore topic and save a brief before starting.')
    article = await q.article(db, item.article_id)
    if article and article.status == 'published': raise Conflict('AI changes to published articles are disabled.')
    research = next((r for r in await q.runs(db, topic_id) if r.stage == 'research' and r.status == 'completed' and r.inputs['brief_version'] == item.brief_version), None)
    version = await q.version(db, payload.version_id)
    if payload.stage in ['qa', 'fix'] and version and version.topic_id == topic_id:
        research = await q.run(db, version.research_id) if version.research_id else None
    if payload.stage != 'research' and (not research or not research.result.get('ready')):
        raise Conflict('Complete research with sufficient evidence before generating or reviewing.')
    if payload.stage in ['qa', 'fix'] and (not version or version.topic_id != topic_id or version.brief_version != item.brief_version):
        raise Conflict('Select a version for the current brief.')
    reports = await q.reports(db, [version.id]) if version else []
    inputs = {'provider': payload.provider, 'title': item.title, 'question': item.reader_question, 'brief': item.brief,
              'brief_version': item.brief_version, 'research_id': research.id if research else None,
              'research': research.result if research else None, 'version_id': version.id if version else None,
              'payload': version.payload if version else None, 'qa': reports[0].report if reports else None}
    job = ContentRun(id=str(uuid4()), topic_id=topic_id, stage=payload.stage, request_key=payload.request_key, inputs=inputs)
    await q.add(db, job)
    await q.audit(db, topic_id, actor, 'run_started', {'run_id': job.id, 'stage': job.stage})
    await q.commit(db)
    return row(job)

async def cancel(db, run_id, actor):
    job = await q.run(db, run_id, True)
    if not job: raise LookupError('Run not found.')
    if job.status in ['queued', 'running']:
        job.cancel_requested = True
        if job.status == 'queued': job.status = 'cancelled'
        await q.audit(db, job.topic_id, actor, 'cancel_requested', {'run_id': run_id})
        await q.commit(db)
    return row(job)

async def save_version(db, topic_id, payload, actor):
    item = await require_topic(db, topic_id, payload.expected_version, True)
    article = await q.article(db, item.article_id)
    if item.archived or (article and article.status == 'published'):
        raise Conflict('Archived topics and published articles cannot be changed here.')
    base = await q.version(db, payload.base_version_id)
    if not base or base.topic_id != topic_id or base.brief_version != item.brief_version:
        raise Conflict('Version does not match the current brief.')
    version = ContentVersion(topic_id=topic_id, research_id=base.research_id, brief_version=item.brief_version, payload=payload.payload.model_dump())
    await q.add(db, version)
    item.version += 1
    await q.audit(db, topic_id, actor, 'version_saved', {'version_id': version.id})
    await q.commit(db)
    return row(version)

async def save_draft(db, topic_id, payload, actor):
    item = await require_topic(db, topic_id, editable=True)
    if item.archived: raise Conflict('Restore this topic before saving a draft.')
    version = await q.version(db, payload.version_id)
    if not version or version.topic_id != topic_id: raise LookupError('Workspace version not found.')
    article = await q.article(db, item.article_id, True)
    if article and article.status == 'published': raise Conflict('Published articles cannot be overwritten by the workspace.')
    if article and item.saved_version_id == version.id:
        return {'article_id': article.id, 'topic_id': topic_id}  # safe repeated request, no write
    if item.version != payload.expected_version or version.brief_version != item.brief_version:
        raise Conflict('Workspace changed; reload before saving.')
    if article and fingerprint(article) != payload.article_fingerprint:
        raise Conflict('Article changed in the editor. Reload and compare before saving.')
    data = DraftPayload.model_validate(version.payload).model_dump()
    from app.core.config import settings
    host = settings.CONTENT_HOST
    if any(x.slug == data['slug'] and (not article or x.id != article.id) for x in await q.articles(db)):
        raise Conflict('Slug already exists. Edit the workspace slug.')
    fields = {k: data[k] for k in ['title', 'slug', 'content', 'excerpt', 'meta_description', 'tags', 'keywords', 'seo_title', 'category', 'subcategory', 'language', 'schema_type', 'open_graph_title', 'open_graph_description']}
    fields.update(status='draft', host_site=host, category=data['category'] or item.track, drafted_at=now(),
                  canonical_url=f'https://{host}/articles/{data["slug"]}', reading_time=max(1, len(data['content'].split()) // 200))
    if article:
        for key, value in fields.items(): setattr(article, key, value)
    else:
        article = await q.add(db, Article(**fields))
    item.article_id = article.id
    item.saved_version_id = version.id
    item.status = 'Drafted'
    item.version += 1
    await q.audit(db, topic_id, actor, 'draft_saved', {'article_id': article.id, 'version_id': version.id})
    await q.commit(db)
    return {'article_id': article.id, 'topic_id': topic_id}

async def import_csv(db, payload, actor):
    rows = list(csv.DictReader(io.StringIO(payload.csv_text.lstrip('\ufeff'))))
    if not rows or len(rows) > 2000: raise ValueError('Import requires 1–2000 topics.')
    existing = {x.topic_id: x for x in await q.topics(db)}
    checked, seen = [], set()
    for r in rows:
        key = r.get('topic_id', '')
        if not re.fullmatch(r'EXPLAINIT-\d{3,8}', key) or int(key.split('-')[1]) < 1 or key != f'EXPLAINIT-{int(key.split("-")[1]):03d}' or key in seen:
            raise ValueError('Invalid or duplicate topic ID.')
        seen.add(key)
        data = TopicInput(title=r.get('title',''), reader_question=r.get('reader_question',''), track=r.get('track',''), notes=r.get('notes',''))
        checked.append((key, data))
    preview = [{'topic_id': key, 'action': 'unchanged' if key in existing else 'add'} for key, _ in checked]
    if payload.apply:
        for key, data in checked:
            if key in existing: continue  # never overwrite existing editorial work
            await q.reserve_id(db, int(key.split('-')[1]))
            await q.add(db, ContentTopic(topic_id=key, **data.model_dump()))
            await q.audit(db, key, actor, 'imported')
        await q.commit(db)
    return {'rows': preview, 'applied': payload.apply, 'note': 'Existing rows are preserved. Import article files separately; CSV alone does not create drafts or publish.'}

async def export_csv(db):
    out = io.StringIO()
    fields = ['topic_id','title','reader_question','track','status','article_id','published_url','review_date','notes']
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(await list_topics(db))
    return {'csv_text': out.getvalue()}
