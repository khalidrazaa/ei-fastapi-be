import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from app.services.content_gemini import GeminiContentAI
from app.schemas.content_workflow import RunInput

class GeminiWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def ai(self, sources=True):
        ai=GeminiContentAI.__new__(GeminiContentAI)
        ai.usage=[]
        response=NS(text='Supported research', usage_metadata=None, candidates=[NS(grounding_metadata=NS(web_search_queries=['warehouse docs'],grounding_chunks=[NS(web=NS(uri='https://example.com/docs',title='Docs'))] if sources else []))])
        ai.client=NS(aio=NS(models=NS(generate_content=AsyncMock(return_value=response))))
        ai.structured=AsyncMock(return_value={'ready':True,'summary':'Evidence','gaps':[],'claims':[{'claim':'Reporting','evidence':'Docs','qualification':'','source_urls':['https://example.com/docs']}]})
        return ai
    async def test_grounded_research_retains_sources_and_usage(self):
        ai=self.ai(); result=await ai.research({'title':'Warehouse','question':'Need one?','brief':{}})
        self.assertTrue(result['ready'])
        self.assertEqual(result['sources'][0]['url'],'https://example.com/docs')
        self.assertEqual(result['usage'][0]['provider'],'gemini')
        self.assertIn('google_search',ai.client.aio.models.generate_content.call_args.kwargs['config']['tools'][0])
    async def test_rejects_ungrounded_research(self):
        with self.assertRaises(ValueError): await self.ai(False).research({'title':'Warehouse','question':'Need one?','brief':{}})
    async def test_rejects_invented_source(self):
        ai=self.ai();ai.structured.return_value['claims'][0]['source_urls']=['https://invented.example/docs']
        with self.assertRaises(ValueError): await ai.research({'title':'Warehouse','question':'Need one?','brief':{}})
    def test_provider_validation(self):
        args=dict(stage='research',request_key='provider-test',expected_version=1)
        self.assertEqual(RunInput(**args).provider,'openai')
        self.assertEqual(RunInput(provider='gemini',**args).provider,'gemini')
        with self.assertRaises(ValueError):RunInput(provider='unknown',**args)
