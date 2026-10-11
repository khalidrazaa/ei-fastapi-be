"""Isolated workflow tests: real SQL persistence, no deployment DB or paid APIs."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, MetaData, JSON, text
from sqlalchemy.orm import Session
from app.db.models.article import Article
from app.db.models.content_workflow import ContentTopic, ContentRun, ContentVersion, ContentQA, TopicIdentifier, now
from app.db.base import Base
from app.db.query import content_workflow as q
from app.schemas.content_workflow import TopicInput, TopicEdit, Brief, BriefEdit, RunInput, SaveDraftInput, VersionInput, DraftPayload, ImportInput
from app.services import content_workflow as service
from app.services.content_policy import safe_url, deterministic_qa, fingerprint
from app.services.content_worker import finish
from app.services.content_ai import ContentAI
from app.api.admin.content_routes import router
from app.core.admin_security import require_admin

PAYLOAD = dict(title='Warehouse decision', slug='warehouse-decision', content='## A business decision\n'+('Useful business detail. '*60)+' [Source](https://example.com/docs)', excerpt='When a warehouse helps managers.', meta_description='A practical warehouse decision guide.', tags=['analytics'], diagram_alt='', unresolved_claims=[])
RESEARCH = dict(ready=True, summary='Evidence collected', claims=[{'claim':'Stores reporting data','source_urls':['https://example.com/docs'],'evidence':'Documentation','qualification':''}], gaps=[], sources=[{'url':'https://example.com/docs','title':'Docs','checked_at':'2026-10-10'}])

class Adapter:
    def __init__(self, session): self.session=session
    async def execute(self, stmt):
        if str(stmt).startswith(('SELECT pg_advisory','SELECT setval')): return None
        return self.session.execute(stmt)
    async def get(self,*a): return self.session.get(*a)
    def add(self,x): self.session.add(x)
    async def flush(self): self.session.flush()
    async def commit(self): self.session.commit()
    async def rollback(self): self.session.rollback()
    async def delete(self,x): self.session.delete(x)

class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        self.addCleanup(self.engine.dispose)
        self.tags=Article.__table__.c.tags.type; self.keywords=Article.__table__.c.keywords.type
        Article.__table__.c.tags.type=JSON(); Article.__table__.c.keywords.type=JSON()
        self.addCleanup(self.restore_types)
        meta=MetaData()
        for t in Base.metadata.sorted_tables:
            if t.name=='articles' or t.name.startswith('content_'):
                copy=t.to_metadata(meta)
                for idx in copy.indexes:
                    if idx.name=='uq_content_active_topic': idx.dialect_options['sqlite']['where']=text("status IN ('queued','running')")
        meta.create_all(self.engine)
        self.session=Session(self.engine,expire_on_commit=False)
        self.addCleanup(self.session.close)
        self.db=Adapter(self.session)
    def restore_types(self):
        Article.__table__.c.tags.type=self.tags;Article.__table__.c.keywords.type=self.keywords
    async def topic(self):
        data=await service.create(self.db,TopicInput(title='Data warehouse decision', reader_question='Does our company need a warehouse?',track='Foundations'),1)
        return await q.topic(self.db,data['topic_id'])
    async def researched(self):
        topic=await self.topic()
        await service.brief(self.db,topic.topic_id,BriefEdit(expected_version=topic.version,brief=Brief(scope=topic.reader_question)),1)
        result=await service.start(self.db,topic.topic_id,RunInput(stage='research',request_key='research-request',expected_version=topic.version),1)
        job=await q.run(self.db,result['id']);job.status='running';job.lease_token='lease'
        await finish(self.db,job.id,'lease',RESEARCH)
        return topic,job
    async def generated(self):
        topic,research=await self.researched()
        request=RunInput(stage='generate',request_key='generation-request',expected_version=topic.version)
        result=await service.start(self.db,topic.topic_id,request,1)
        job=await q.run(self.db,result['id']);job.status='running';job.lease_token='lease'
        await finish(self.db,job.id,'lease',{'payload':PAYLOAD,'usage':[]})
        qa=await q.active(self.db,topic.topic_id);qa.status='running';qa.lease_token='qa-lease'
        await finish(self.db,qa.id,'qa-lease',{'findings':[]})
        return topic,(await q.versions(self.db,topic.topic_id))[0]
    async def test_id_never_reused_after_delete(self):
        t=await self.topic();await service.delete(self.db,t.topic_id,1)
        next_topic=await self.topic();self.assertNotEqual(t.topic_id,next_topic.topic_id)
    async def test_import_is_idempotent_and_missing_rows_do_not_delete(self):
        csv='topic_id,title,reader_question,track\nEXPLAINIT-010,Warehouse question,Do we need a warehouse?,Foundations\n'
        await service.import_csv(self.db,ImportInput(csv_text=csv,apply=True),1)
        await service.import_csv(self.db,ImportInput(csv_text=csv,apply=True),1)
        self.assertEqual(len(await q.topics(self.db)),1)
        t=await self.topic();self.assertEqual(t.topic_id,'EXPLAINIT-011')
    async def test_overlap_and_history_protection(self):
        t,_=await self.researched()
        with self.assertRaises(service.Conflict): await service.delete(self.db,t.topic_id,1)
        data=await service.workspace(self.db,t.topic_id)
        self.assertIn('runs',data)
    async def test_generation_does_not_create_article_and_qa_is_versioned(self):
        t,v=await self.generated()
        self.assertEqual(await q.articles(self.db),[])
        self.assertEqual((await q.reports(self.db,[v.id]))[0].version_id,v.id)
        self.assertEqual(t.status,'Researched')
    async def test_save_draft_idempotent_and_manual_publish_visible(self):
        t,v=await self.generated()
        p=SaveDraftInput(expected_version=t.version,version_id=v.id)
        first=await service.save_draft(self.db,t.topic_id,p,1)
        second=await service.save_draft(self.db,t.topic_id,p,1)
        self.assertEqual(first,second);self.assertEqual(len(await q.articles(self.db)),1)
        a=await q.article(self.db,t.article_id);self.assertEqual(a.status,'draft')
        a.status='published';await q.commit(self.db)
        view=(await service.list_topics(self.db))[0]
        self.assertEqual(view['status'],'Published');self.assertIn('/articles/',view['published_url'])
        with self.assertRaises(service.Conflict):await service.save_draft(self.db,t.topic_id,p,1)
        a.status='draft';await q.commit(self.db)
        self.assertIsNone((await service.list_topics(self.db))[0]['published_url'])
    async def test_edit_invalidates_qa_and_article_conflict_preserves_manual_work(self):
        t,v=await self.generated()
        await service.save_draft(self.db,t.topic_id,SaveDraftInput(expected_version=t.version,version_id=v.id),1)
        a=await q.article(self.db,t.article_id);old=fingerprint(a)
        edited=await service.save_version(self.db,t.topic_id,VersionInput(expected_version=t.version,base_version_id=v.id,payload=DraftPayload(**{**PAYLOAD,'title':'Revised decision'})),1)
        self.assertEqual(await q.reports(self.db,[edited['id']]),[])
        a.content='Manual editor changes';await q.commit(self.db)
        with self.assertRaises(service.Conflict):
            await service.save_draft(self.db,t.topic_id,SaveDraftInput(expected_version=t.version,version_id=edited['id'],article_fingerprint=old),1)
        self.assertEqual(a.content,'Manual editor changes')
    async def test_stale_lease_and_cancelled_result_cannot_commit(self):
        t=await self.topic();t.brief={'scope':'Something'};t.brief_version=1
        j=ContentRun(id='job',topic_id=t.topic_id,stage='research',request_key='job-key',status='running',lease_token='new',inputs={'brief_version':1})
        await q.add(self.db,j);await q.commit(self.db)
        await finish(self.db,j.id,'old',RESEARCH);self.assertEqual(j.status,'running')
        await service.cancel(self.db,j.id,1);await finish(self.db,j.id,'new',RESEARCH)
        self.assertEqual(j.status,'cancelled');self.assertIsNone(j.result)
    async def test_stale_brief_cannot_reuse_research(self):
        t,_=await self.researched()
        await service.brief(self.db,t.topic_id,BriefEdit(expected_version=t.version,brief=Brief(scope='A changed scope')),1)
        with self.assertRaises(service.Conflict):
            await service.start(self.db,t.topic_id,RunInput(stage='generate',request_key='generate-stale',expected_version=t.version),1)
    async def test_active_job_rejects_archiving(self):
        t,_=await self.researched()
        await service.start(self.db,t.topic_id,RunInput(stage='generate',request_key='active-run',expected_version=t.version),1)
        with self.assertRaises(service.Conflict):
            await service.edit(self.db,t.topic_id,TopicEdit(title=t.title,reader_question=t.reader_question,track=t.track,archived=True,expected_version=t.version),1)
    async def test_request_key_replay_returns_same_job(self):
        t,_=await self.researched()
        p=RunInput(stage='generate',request_key='idempotent-request',expected_version=t.version)
        a=await service.start(self.db,t.topic_id,p,1);b=await service.start(self.db,t.topic_id,p,1)
        self.assertEqual(a['id'],b['id'])

class PolicyTests(unittest.TestCase):
    def test_safe_urls(self):
        for url in ['http://example.com','https://127.0.0.1','https://169.254.169.254','https://example.com@localhost','javascript:alert(1)','https://foo.internal','https://foo.com:9000']:
            self.assertFalse(safe_url(url),url)
        self.assertTrue(safe_url('https://docs.example.com/page'))
    def test_missing_and_invented_citations_are_flagged(self):
        result=deterministic_qa({**PAYLOAD,'content':PAYLOAD['content'].replace('example.com','invented.com')},RESEARCH)
        self.assertTrue(any(x['severity']=='error' for x in result))
    def test_admin_routes_require_authentication(self):
        app=FastAPI();app.include_router(router)
        async def deny():
            from fastapi import HTTPException
            raise HTTPException(401,'Sign in')
        app.dependency_overrides[require_admin]=deny
        with TestClient(app) as client:
            for method,path in [('get','/content-topics'),('post','/content-topics'),('delete','/content-topics/EXPLAINIT-001'),('post','/content-topics/EXPLAINIT-001/save-draft')]:
                self.assertEqual(getattr(client,method)(path).status_code,401)

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_rejects_invented_evidence_url(self):
        ai=object.__new__(ContentAI);ai.usage=[]
        output=SimpleNamespace(model_dump=lambda:{'content':[{'annotations':[{'url':'https://example.com/docs','title':'Docs'}]}]})
        response=SimpleNamespace(output=[output],output_text='Source findings',id='response',model='fixture',usage=None)
        ai.client=SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response)))
        ai.structured=AsyncMock(return_value={**RESEARCH,'claims':[{'source_urls':['https://fake.example.com']}]})
        with self.assertRaises(ValueError): await ai.research({'title':'Title','question':'Question','brief':{}})
