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
    fields = ['title', 'slug', 'content', 'excerpt', 'meta_description', 'tags', 'status', 'host_site', 'updated_at', 'seo_title', 'category', 'subcategory', 'keywords', 'language', 'schema_type', 'open_graph_title', 'open_graph_description']
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
    sections = re.split(r'^##\s+Sources\s*$', body, flags=re.M | re.I)
    main = sections[0]
    words = main_body_words(body)
    if not 400 <= words <= 800: add('length', f'{words} main-body words; use 400-800, excluding image markup and final Sources.')
    citations = re.findall(r'(?<!!)\[[^\]]+\]\((https?://[^\s)]+)\)', body)
    if len(sections) != 2 or not citations: add('sources', 'Include one final Sources section with checked references.', 'error')
    if re.search(r'https?://|www\.', re.sub(r'!\[[^\]]*\]\([^)]*\)', '', main)):
        add('sources', 'Move source URLs out of the main prose into final Sources.', 'error')
    if len(sections) > 1 and not re.search(r'\b\d{4}-\d{2}-\d{2}\b', sections[-1]):
        add('sources', 'Sources need checked dates.')
    if len(sections) > 1 and re.search(r'^#{1,6}\s+', sections[-1], re.M):
        add('sources', 'Sources must be the final section.')
    if re.search(r'```\s*mermaid|<svg\b', body, re.I):
        add('diagram', 'Use the generated SVG image, not Mermaid or raw SVG markup.', 'error')
    if re.search(r'!\[[^\]]*\]\([^)]*\.png(?:[?#][^)]*)?\)', main, re.I):
        add('diagram', 'New generated diagrams must be SVG only.')
    if re.search(r'[$€£₹]\s*\d|\b\d+(?:\.\d+)?\s*(?:USD|EUR|GBP|INR)\b|break[- ]even|\b\d+%\s*discount', main, re.I):
        add('pricing', 'Vendor rates, discounts, and price break-even comparisons are outside scope; compare billing against usage.')
    for url in citations:
        if url not in sources: add('sources', f'Citation is absent from the research ledger: {url}', 'error')
    if re.search(r'\]\((?:javascript|data|vbscript):', body, re.I): add('links', 'Unsafe link scheme.', 'error')
    if body.startswith('---') or re.search(r'^# ', body, re.M): add('format', 'Remove front matter and duplicate H1.')
    for phrase in ['ever-evolving', 'fast-paced digital', 'game-changer', 'revolutionize', 'delve into', 'in conclusion']:
        if phrase in body.lower(): add('style', f'Replace generic phrasing: {phrase}')
    for claim in payload.get('unresolved_claims', []): add('unresolved', claim)
    for gap in research.get('gaps', []): add('research gap', gap)
    return findings


def main_body_words(body):
    """Count visible prose, headings, tables and captions, excluding Sources/images/H1."""
    from markdown_it import MarkdownIt
    main = re.split(r'^##\s+Sources\s*$', body, maxsplit=1, flags=re.M | re.I)[0]
    tokens = MarkdownIt('commonmark').enable('table').parse(main)
    text, skip_h1 = [], False
    for token in tokens:
        if token.type == 'heading_open' and token.tag == 'h1': skip_h1 = True
        elif token.type == 'heading_close': skip_h1 = False
        elif token.type == 'inline' and not skip_h1:
            text.extend(child.content for child in token.children or [] if child.type in {'text', 'code_inline'})
    return len(re.findall(r"\b\w+(?:[-’']\w+)*\b", ' '.join(text)))
