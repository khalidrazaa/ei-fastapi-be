"""Portable editorial policy, native diagrams and transactional draft media."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from lxml import etree
from pydantic import ValidationError
from app.schemas.content_workflow import Brief, DraftPayload, RunInput, SaveDraftInput, VersionInput
from app.services.content_editorial import append_sources, editorial_snapshot
from app.services.content_policy import deterministic_qa, main_body_words
from app.services.content_diagram import render_svg, generate_diagram
from app.services import content_workflow as workflow
from app.services import content_worker as worker
from app.db.query import content_workflow as query
from app.db.models.article_image import ArticleImage
from app.core.config import settings
import test_content_workflow as base


PLAN = dict(title='A controlled document flow', description='Prepare evidence, then retrieve permitted passages for a response.',
            layout='sequence', cards=[{'heading':'Prepare evidence','detail':'Owner approves the version and audience.'},
                                    {'heading':'Retrieve and respond','detail':'Apply permissions and provide references.'}])


class EditorialTests(unittest.TestCase):
    def test_main_body_count_excludes_sources_images_metadata_and_h1(self):
        body='# Title excluded\n\n## Decision\n\n'+'detail '*399+'\n\n![excluded image words](diagram.svg)\n\n## Sources\n\n'+'reference '*500
        self.assertEqual(main_body_words(body),400)
        self.assertFalse(any(f['category']=='length' for f in deterministic_qa(dict(base.PAYLOAD,content=body),base.RESEARCH)))

    def test_sources_assembled_from_checked_catalog_only(self):
        payload=append_sources(dict(base.PAYLOAD,content='Decision\n\n## Sources\n\n[Invented](https://invented.example)'),base.RESEARCH)
        self.assertNotIn('invented.example',payload['content'])
        self.assertIn('checked 2026-10-10',payload['content'])
        self.assertEqual(payload['content'].count('## Sources'),1)

    def test_layouts_escape_text_and_svg_has_no_bitmap_or_script(self):
        for layout in ['sequence','stages','comparison']:
            source=render_svg(dict(PLAN,layout=layout,title='Read <script> & compare'))
            svg=etree.fromstring(source.encode())
            self.assertEqual(svg.tag,'{http://www.w3.org/2000/svg}svg')
            self.assertFalse(svg.xpath('//*[local-name()="script" or local-name()="image"]'))
            self.assertIn('&lt;script&gt;',source)

    def test_snapshot_and_contract_boundaries(self):
        snapshot=editorial_snapshot()
        copy=editorial_snapshot({'editorial_policy':snapshot})
        copy['instructions']='changed'
        self.assertNotEqual(snapshot['instructions'],copy['instructions'])
        self.assertEqual(len(snapshot['sha256']),64)
        self.assertEqual(len(DraftPayload.model_fields),16)
        with self.assertRaises(ValidationError):Brief(scope='Business question',target_words=801)

    def test_qa_flags_source_placement_pricing_and_legacy_diagrams(self):
        body='detail '*450+'\n[Docs](https://example.com/docs)\n$25 per month\n```mermaid\nflowchart TD\n```'
        categories={f['category'] for f in deterministic_qa(dict(base.PAYLOAD,content=body),base.RESEARCH)}
        self.assertTrue({'sources','pricing','diagram'}<=categories)


class DiagramPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_writers_use_pinned_rules_and_canonical_sources(self):
        from app.services.content_ai import ContentAI
        from app.services.content_gemini import GeminiContentAI
        snapshot=editorial_snapshot()
        for provider in [ContentAI,GeminiContentAI]:
            ai=provider.__new__(provider)
            ai.structured=AsyncMock(return_value=dict(base.PAYLOAD,content='Useful detail. '*250))
            result=await ai.write({'research':base.RESEARCH,'editorial_policy':snapshot})
            self.assertEqual(ai.structured.call_args.args[1],snapshot['instructions'])
            self.assertEqual(set(result),set(base.PAYLOAD))
            self.assertIn('## Sources\n\n',result['content'])
            self.assertIn('checked 2026-10-10',result['content'])

    async def test_worker_keeps_svg_outside_strict_payload(self):
        job=SimpleNamespace(id=str(uuid4()),stage='generate',inputs={'brief':{'diagram':True},'question':'How does it work?','research':base.RESEARCH})
        payload=dict(base.PAYLOAD,content='detail '*450+'\n![Evidence](diagram.svg)')
        ai=SimpleNamespace(write=AsyncMock(return_value=payload),structured=AsyncMock(return_value=deepcopy(PLAN)),usage=[])
        with patch('app.services.content_diagram.check_layout',AsyncMock(return_value={'rendered':True,'bounds_checked':True})):
            result=await worker.perform(job,ai)
        DraftPayload.model_validate(result['payload'])
        self.assertIn(f'diagram-{job.id}.svg',result['payload']['content'])
        self.assertIn('<svg',result['diagram']['svg'])
        self.assertNotIn('svg',result['payload'])
        self.assertEqual(result['editorial_policy']['version'],'2026-11-01')

    async def test_disabled_diagram_does_not_call_provider_and_rejects_hidden_images(self):
        job=SimpleNamespace(inputs={'brief':{'diagram':False}})
        ai=SimpleNamespace(structured=AsyncMock())
        payload,diagram=await generate_diagram(job,ai,base.PAYLOAD)
        self.assertIsNone(diagram)
        self.assertEqual(payload['diagram_alt'],'')
        ai.structured.assert_not_called()
        with self.assertRaises(ValueError):
            await generate_diagram(job,ai,dict(base.PAYLOAD,content='![image](https://example.com/image.svg)'))

    async def test_missing_diagram_or_render_failure_does_not_silently_pass(self):
        job=SimpleNamespace(id=str(uuid4()),inputs={'brief':{'diagram':True},'question':'How?'})
        ai=SimpleNamespace(structured=AsyncMock(return_value=deepcopy(PLAN)))
        with self.assertRaises(ValueError):await generate_diagram(job,ai,base.PAYLOAD)
        with patch('app.services.content_diagram.check_layout',AsyncMock(side_effect=ValueError('clipped label'))):
            with self.assertRaisesRegex(ValueError,'clipped label'):
                await generate_diagram(job,ai,dict(base.PAYLOAD,content='![Diagram](diagram.svg)'))


class DiagramStorageTests(base.WorkflowTests):
    async def test_generation_pins_the_research_policy_snapshot(self):
        topic,research=await self.researched()
        pinned=deepcopy(research.inputs['editorial_policy'])
        with TemporaryDirectory() as folder:
            changed=Path(folder)/'policy.md'
            changed.write_text('Changed policy; must not alter this research.')
            with patch('app.services.content_editorial.POLICY_FILE',changed):
                run=await workflow.start(self.db,topic.topic_id,RunInput(stage='generate',request_key='policy-snapshot-test',expected_version=topic.version),1)
        self.assertEqual(run['inputs']['editorial_policy'],pinned)

    async def diagram_version(self):
        topic,version=await self.generated()
        run=await query.run(self.db,version.run_id)
        name=f'diagram-{run.id}.svg'
        version.payload=dict(base.PAYLOAD,content='## The workflow\n\n'+'Reviewed evidence. '*20+'\n\n![Evidence]('+name+')')
        run.result={**run.result,'diagram':{'filename':name,'svg':render_svg(PLAN),'alt':'Evidence flow','plan':PLAN,'visual_checks':{'rendered':True}}}
        await query.commit(self.db)
        return topic,version,name

    async def test_edited_version_retains_original_svg_and_save_is_idempotent(self):
        ArticleImage.__table__.create(self.engine,checkfirst=True)
        topic,version,name=await self.diagram_version()
        edited=await workflow.save_version(self.db,topic.topic_id,VersionInput(expected_version=topic.version,
            base_version_id=version.id,payload=DraftPayload(**dict(version.payload,title='Revised decision'))),1)
        workspace=await workflow.workspace(self.db,topic.topic_id)
        self.assertIn(name,workspace['diagrams'])
        with TemporaryDirectory() as folder,patch.object(settings,'MEDIA_ROOT',folder),patch.object(settings,'MEDIA_PUBLIC_BASE_URL','https://api.example.com/v1'):
            request=SaveDraftInput(expected_version=topic.version,version_id=edited['id'])
            result=await workflow.save_draft(self.db,topic.topic_id,request,1)
            await workflow.save_draft(self.db,topic.topic_id,request,1)
            article=await query.article(self.db,result['article_id'])
            self.assertIn('https://api.example.com/v1/media/articles/',article.content)
            self.assertNotIn(name,article.content)
            self.assertEqual(len(list(Path(folder).rglob('*.svg'))),1)
            self.assertEqual(list(Path(folder).rglob('*.png')),[])
            self.assertEqual(article.status,'draft')

    async def test_cross_topic_artifact_is_rejected(self):
        topic,version,name=await self.diagram_version()
        other=await self.topic()
        with self.assertRaisesRegex(ValueError,'does not belong'):
            await workflow.diagrams_for_content(self.db,other.topic_id,version.payload['content'])

    async def test_foreign_diagram_edit_does_not_poison_workspace_history(self):
        topic,version,name=await self.diagram_version()
        other=await self.topic()
        foreign_id=str(uuid4())
        foreign_name=f'diagram-{foreign_id}.svg'
        await query.add(self.db,base.ContentRun(id=foreign_id,topic_id=other.topic_id,
            stage='generate',status='completed',request_key='foreign-svg-test',inputs={},
            result={'diagram':{'filename':foreign_name,'svg':render_svg(PLAN)}}))
        await query.commit(self.db)
        request=VersionInput(expected_version=topic.version,base_version_id=version.id,
            payload=DraftPayload(**dict(version.payload,content='Reviewed body. '*30+f'![Foreign]({foreign_name})')))
        before=len(await query.versions(self.db,topic.topic_id))
        with self.assertRaisesRegex(ValueError,'does not belong'):
            await workflow.save_version(self.db,topic.topic_id,request,1)
        self.assertEqual(len(await query.versions(self.db,topic.topic_id)),before)
        self.assertIn(name,(await workflow.workspace(self.db,topic.topic_id))['diagrams'])

    async def test_failed_draft_commit_removes_uncommitted_media(self):
        ArticleImage.__table__.create(self.engine,checkfirst=True)
        topic,version,name=await self.diagram_version()
        topic_id=topic.topic_id
        with TemporaryDirectory() as folder,patch.object(settings,'MEDIA_ROOT',folder),patch.object(settings,'MEDIA_PUBLIC_BASE_URL','https://api.example.com/v1'):
            with patch.object(query,'commit',AsyncMock(side_effect=ValueError('commit failed'))):
                with self.assertRaisesRegex(ValueError,'commit failed'):
                    await workflow.save_draft(self.db,topic_id,SaveDraftInput(expected_version=topic.version,version_id=version.id),1)
            self.assertEqual(list(Path(folder).rglob('*.svg')),[])

    async def test_uncertain_successful_commit_retains_media_and_allows_replay(self):
        ArticleImage.__table__.create(self.engine,checkfirst=True)
        topic,version,name=await self.diagram_version()
        topic_id=topic.topic_id
        request=SaveDraftInput(expected_version=topic.version,version_id=version.id)
        original_commit=query.commit
        async def committed_but_connection_failed(db):
            await original_commit(db)
            raise OSError('connection lost after COMMIT')
        with TemporaryDirectory() as folder,patch.object(settings,'MEDIA_ROOT',folder),patch.object(settings,'MEDIA_PUBLIC_BASE_URL','https://api.example.com/v1'):
            with patch.object(query,'commit',committed_but_connection_failed):
                with self.assertRaises(OSError):
                    await workflow.save_draft(self.db,topic_id,request,1)
            self.assertEqual(len(list(Path(folder).rglob('*.svg'))),1)
            replay=await workflow.save_draft(self.db,topic_id,request,1)
            article=await query.article(self.db,replay['article_id'])
            self.assertIn('/media/articles/',article.content)
