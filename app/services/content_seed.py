"""Preview: python -m app.services.content_seed. Apply explicitly with --apply."""
import argparse
import asyncio
import json
from pathlib import Path
from app.db.session import SessionLocal
from app.db.query import content_workflow as q
from app.db.models.content_workflow import ContentVersion
from app.schemas.content_workflow import ImportInput, SaveDraftInput, DraftPayload, Brief
from app.services import content_workflow as service

async def seed(apply=False):
    folder = Path(__file__).resolve().parents[2] / 'docs/content-seed'
    async with SessionLocal() as db:
        result = await service.import_csv(db, ImportInput(csv_text=(folder/'content-inventory.csv').read_text(encoding='utf-8-sig'), apply=apply), 'seed-import')
        print(f"{'Imported' if apply else 'Preview'} {len(result['rows'])} inventory rows.")
        if not apply: return
        item = await q.topic(db, 'EXPLAINIT-001', True)
        if item.article_id or await q.versions(db, item.topic_id):
            print('EXPLAINIT-001 already has work; preserved.')
            return
        payload = DraftPayload.model_validate_json((folder/'EXPLAINIT-001.json').read_text(encoding='utf-8'))
        item.brief = Brief(scope=item.reader_question).model_dump()
        item.brief_version = 1
        version = await q.add(db, ContentVersion(topic_id=item.topic_id, brief_version=1, payload=payload.model_dump()))
        # The existing local article is imported as a draft, not AI-researched anew.
        await service.save_draft(db, item.topic_id, SaveDraftInput(expected_version=item.version, version_id=version.id), 'seed-import')
        print('Imported EXPLAINIT-001 as draft. No publication or paid API calls.')

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args=parser.parse_args()
    asyncio.run(seed(args.apply))
