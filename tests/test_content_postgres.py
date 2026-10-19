"""Opt-in migration/locking tests. Only a disposable local *_test database."""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from alembic.operations import Operations
from alembic.migration import MigrationContext
from app.db.models.content_workflow import ContentTopic, ContentRun
from app.db.query import content_workflow as q

URL=os.getenv('CONTENT_TEST_DATABASE_URL','')
@unittest.skipUnless(URL,'Set CONTENT_TEST_DATABASE_URL to a disposable local *_test database.')
class ContentPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        url=make_url(URL)
        if url.host not in ['localhost','127.0.0.1','::1'] or not (url.database or '').endswith('_test'):
            raise ValueError('Only a disposable local *_test database is permitted.')
        self.schema='content_test_'+uuid4().hex
        self.admin=create_async_engine(url,poolclass=NullPool)
        async with self.admin.begin() as conn: await conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.engine=create_async_engine(url,poolclass=NullPool,connect_args={'server_settings':{'search_path':self.schema}})
        self.sessions=async_sessionmaker(self.engine,expire_on_commit=False)
        path=Path(__file__).parents[1]/'alembic/versions/c01_content_workflow.py'
        spec=importlib.util.spec_from_file_location('content_migration',path)
        self.migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.migration)
        async with self.engine.begin() as conn:
            await conn.execute(text('CREATE TABLE articles (id integer PRIMARY KEY)'))
            def apply(connection):
                with Operations.context(MigrationContext.configure(connection)): self.migration.upgrade()
            await conn.run_sync(apply)
    async def asyncTearDown(self):
        await self.engine.dispose()
        async with self.admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await self.admin.dispose()
    async def test_registry_and_single_worker_claim(self):
        async with self.sessions() as db:
            identifier=await q.reserve_id(db,100)
            await q.add(db,ContentTopic(topic_id=identifier,title='Warehouse',reader_question='Need a warehouse?',track='Foundations'))
            await q.add(db,ContentRun(id=str(uuid4()),topic_id=identifier,stage='research',request_key='test-research',inputs={'brief_version':1}))
            await db.commit()
        async with self.sessions() as first, self.sessions() as second:
            job=await q.claim(first)
            self.assertEqual(job.status,'running')
            self.assertIsNone(await q.claim(second))
            self.assertEqual(await q.reserve_id(second),'EXPLAINIT-101')
            await second.commit()
    async def test_partial_unique_index_allows_history_not_concurrent_jobs(self):
        from sqlalchemy.exc import IntegrityError
        async with self.sessions() as db:
            await q.add(db,ContentTopic(topic_id='EXPLAINIT-001',title='Warehouse',reader_question='Need a warehouse?',track='Foundations'))
            for status in ['completed','completed','queued']:
                await q.add(db,ContentRun(id=str(uuid4()),topic_id='EXPLAINIT-001',stage='research',request_key=str(uuid4()),status=status,inputs={}))
            await db.commit()
            with self.assertRaises(IntegrityError):
                await q.add(db,ContentRun(id=str(uuid4()),topic_id='EXPLAINIT-001',stage='research',request_key=str(uuid4()),status='queued',inputs={}))
            await db.rollback()
