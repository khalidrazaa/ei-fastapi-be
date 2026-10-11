"""Pure validation, shared by the worker, API, and tests."""
import hashlib
import ipaddress
import json
import re
from difflib import SequenceMatcher
from urllib.parse import urlsplit

def safe_url(value):
    try:
        url = urlsplit(value)
        host = (url.hostname or '').lower()
        if url.scheme != 'https' or url.username or url.password or url.port not in (None, 443):
            return False
        if not host or '.' not in host or host.endswith(('.local', '.internal', '.localhost')):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return not host.replace('.', '').isdigit()
    except ValueError:
        return False

def fingerprint(article):
    if not article: return None
    fields = ['title', 'slug', 'content', 'excerpt', 'meta_description', 'tags', 'status', 'host_site', 'updated_at']
    return hashlib.sha256(json.dumps({k: str(getattr(article, k, None)) for k in fields}, sort_keys=True).encode()).hexdigest()

def overlaps(title, question, candidates):
    def norm(value): return re.sub(r'\W+', ' ', value.lower()).strip()
    results = []
    for identifier, other_title, other_question in candidates:
        score = max(SequenceMatcher(None, norm(title), norm(other_title)).ratio(),
                    SequenceMatcher(None, norm(question), norm(other_question or other_title)).ratio())
        if score >= .62:
            results.append({'id': identifier, 'title': other_title, 'similarity': round(score, 2)})
    return sorted(results, key=lambda x: -x['similarity'])[:10]

def deterministic_qa(payload, research):
    body = payload['content']
    sources = {x['url'] for x in research.get('sources', [])}
    findings = []
    def add(category, message, severity='warning'):
        findings.append(dict(category=category, message=message, severity=severity))
    words = len(re.sub(r'```[\s\S]*?```', '', body).split())
    if not 700 <= words <= 900: add('length', f'{words} words; check whether detail justifies the length.')
    citations = re.findall(r'(?<!!)\[[^\]]+\]\((https?://[^\s)]+)\)', body)
    if not citations: add('sources', 'No inline source citations.', 'error')
    for url in citations:
        if url not in sources: add('sources', f'Citation is absent from the research ledger: {url}', 'error')
    if re.search(r'\]\((?:javascript|data|vbscript):', body, re.I): add('links', 'Unsafe link scheme.', 'error')
    if body.startswith('---') or re.search(r'^# ', body, re.M): add('format', 'Remove front matter and duplicate H1.')
    for phrase in ['ever-evolving', 'fast-paced digital', 'game-changer', 'revolutionize', 'delve into', 'in conclusion']:
        if phrase in body.lower(): add('style', f'Replace generic phrasing: {phrase}')
    for claim in payload.get('unresolved_claims', []): add('unresolved', claim)
    for gap in research.get('gaps', []): add('research gap', gap)
    return findings
