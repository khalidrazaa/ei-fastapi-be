"""Versioned provider-neutral editorial policy, snapshotted with each job."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re

POLICY_FILE = Path(__file__).resolve().parents[1] / 'editorial/article-workflow.md'


def editorial_snapshot(inputs=None):
    existing = (inputs or {}).get('editorial_policy')
    if existing is not None:
        return deepcopy(existing)
    instructions = POLICY_FILE.read_text(encoding='utf-8')
    version = re.search(r'policy version (\d{4}-\d{2}-\d{2})', instructions)
    if not version:
        raise ValueError('The editorial policy needs a dated version header.')
    return {'version': version[1], 'sha256': sha256(instructions.encode()).hexdigest(),
            'instructions': instructions}


def editorial_instructions(inputs):
    return editorial_snapshot(inputs)['instructions']


def append_sources(payload, research):
    """Keep sources private until appending the checked, canonical source catalog."""
    from app.services.content_policy import safe_url
    result = dict(payload)
    body = re.split(r'^##\s+Sources\s*$', result['content'], maxsplit=1, flags=re.M | re.I)[0].rstrip()
    refs, seen = [], set()
    for source in research.get('sources', []):
        url = source.get('url', '')
        if not safe_url(url) or url in seen:
            continue
        seen.add(url)
        title = re.sub(r'[\[\]\\\r\n<>]', '', source.get('title') or 'Reference').strip()[:300]
        checked = str(source.get('checked_at') or '')[:10]
        date = checked if re.fullmatch(r'\d{4}-\d{2}-\d{2}', checked) else 'date unavailable; recheck before publication'
        refs.append(f'- [{title}]({url}) — checked {date}.')
    result['content'] = body + '\n\n## Sources\n\n' + '\n'.join(refs)
    return result
