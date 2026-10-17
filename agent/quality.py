from __future__ import annotations
import html
import re
from urllib.parse import urlsplit, quote
from models.research import Requirement, StructuredReport, SemanticReview


def requirements(text: str) -> list[Requirement]:
    numbered = list(re.finditer(r'(?:^|[：:\n?？])\s*\d+[.、)]\s*', text))
    if len(numbered) > 1:
        extracted = [text[m.end():numbered[i+1].start() if i+1 < len(numbered) else len(text)].strip(' ?？。\n') for i,m in enumerate(numbered)]
        return [Requirement(id=f'r{i}', text=value) for i,value in enumerate(extracted,1) if value]
    parts = [p.strip(' ;；。\n') for p in re.split(r'(?:\n\s*(?:\d+[.、)]|[-•])\s*|(?:^|[：:\s])\d+[.、)]\s*|[?？；;]\s*|(?<=。)\s*\n)', text) if p.strip(' ;；。\n')]
    if len(parts) == 1 and len(re.findall(r'是否|能否|会不会', text)) > 1:
        parts = re.split(r'，?以及|，?并且', text)
        if len(parts) == 1:
            parts = re.split(r'(?<=[?？])\s*', text)
    parts = [p.strip() for p in parts if p.strip()]
    candidates = [p for p in parts if not re.fullmatch(r'(?:两问分别作答|分别回答|引用原文|请用中文|不要联网|仅根据提供材料[，。 ]*不要联网|仅根据提供材料|分别回答|说明证据是否足够)[。.!！:：]*', p)]
    if len(candidates) <= 1:
        return [Requirement(id='r1', text=text.strip())]
    return [Requirement(id=f'r{i}', text=p) for i, p in enumerate(candidates or [text.strip()], 1)]


def check_plan(plan, reqs):
    expected = {r.id for r in reqs}
    seen = set()
    for question in plan.questions:
        if not question.requirement_ids and len(reqs) == 1:
            question.requirement_ids = [reqs[0].id]
        ids = set(question.requirement_ids)
        if not ids or not ids <= expected or (len(reqs) > 1 and len(ids) > 1):
            raise ValueError('Each independent requirement needs its own research question')
        seen.update(ids)
    if seen != expected:
        raise ValueError('Plan omitted explicit user requirements')


def source_type(url: str, official_prefixes=()) -> str:
    p = urlsplit(url)
    if p.scheme == 'user':
        return 'user'
    path = p.path.lower()
    if any(x in path for x in ('/forum', '/community', '/discuss')) or p.hostname and p.hostname.startswith(('forum.', 'community.', 'discuss.')):
        return 'forum'
    for prefix in official_prefixes:
        approved = urlsplit(prefix)
        if p.scheme == 'https' and p.hostname == approved.hostname and (p.path == approved.path.rstrip('/') or p.path.startswith(approved.path.rstrip('/') + '/')):
            return 'official'
    return 'unknown'


def check_report(report: StructuredReport, questions, evidence, *, official_only=False, official_prefixes=()):
    errors = []
    expected = {q['id'] for q in questions}
    if len(report.sections) != len(expected) or {s.question_id for s in report.sections} != expected:
        errors.append('Report must cover every question exactly once')
    ids = set()
    by_id = {e['id']: e for e in evidence}
    for section in report.sections:
        for claim in section.claims:
            if claim.id in ids:
                errors.append(f'{claim.id}: duplicate claim id')
            ids.add(claim.id)
            if not claim.supports:
                errors.append(f'{claim.id}: no evidence')
            primary = False
            for support in claim.supports:
                e = by_id.get(support.evidence_id)
                if not e or section.question_id not in e.get('question_ids', []):
                    errors.append(f'{claim.id}: unknown/unrelated evidence {support.evidence_id}')
                    continue
                if support.quote not in e['text']:
                    errors.append(f'{claim.id}: quotation not present in evidence')
                eligible = e.get('kind') in {'body', 'user'} and not e.get('download_truncated')
                if official_only:
                    eligible = eligible and source_type(e.get('final_url') or e['url'], official_prefixes) == 'official'
                primary |= eligible and support.relation == 'supports' and support.quote in e['text']
            if not primary:
                errors.append(f'{claim.id}: no qualifying primary quotation')
    return errors


def check_semantics(report, review: SemanticReview, *, time_required=False):
    claims = {c.id for s in report.sections for c in s.claims}
    questions = {s.question_id for s in report.sections}
    errors = list(review.issues)
    if len(review.claims) != len(claims) or {v.claim_id for v in review.claims} != claims:
        errors.append('Semantic review must cover each claim exactly once')
    if len(review.questions) != len(questions) or {v.question_id for v in review.questions} != questions:
        errors.append('Semantic review must cover each question exactly once')
    for v in review.claims:
        if v.status != 'supported' or (time_required and v.temporal_applicability != 'confirmed'):
            errors.append(f'{v.claim_id}: {v.status}; {v.explanation}')
    if not review.task_compliant:
        errors.append('Original request constraints not satisfied')
    for section in report.sections:
        for claim in section.claims:
            if any(s.relation == 'contradicts' for s in claim.supports):
                errors.append(f'{claim.id}: contradictory evidence requires resolution')
    return errors


def escape_text(text):
    result = html.escape(text).replace('\n', ' ')
    for c in ('\\', '*', '_', '[', ']', '(', ')', '#', '|', '>', chr(96)):
        result = result.replace(c, '\\' + c)
    return result


def render_report(report, questions, evidence, verdicts=None):
    by_id = {e['id']: e for e in evidence}
    labels = {q['id']: q['text'] for q in questions}
    verdicts = verdicts or {}
    lines = ['# 研究报告', '', '> 结论支持度由当前校验流程判断，不等同于独立事实认证。', '']
    for section in report.sections:
        lines += ['## ' + escape_text(labels.get(section.question_id, section.question_id)), '']
        for claim in section.claims:
            status = verdicts.get(claim.id, {}).get('status', 'unverified')
            lines.append(f'**{escape_text(claim.id)} · {escape_text(status)}**')
            refs = []
            for support in claim.supports:
                e = by_id.get(support.evidence_id)
                if e and urlsplit(e['url']).scheme in {'https', 'http', 'user'}:
                    refs.append(f'[证据 {e["id"]}]({quote(e["url"], safe=":/?=&%#@+~!$,-_.")})')
            lines += [escape_text(claim.text) + ' ' + ' '.join(dict.fromkeys(refs)), '']
            for support in claim.supports:
                lines.append('> 原文（' + escape_text(support.relation) + '）：' + escape_text(support.quote))
            lines.append('')
        for gap in section.gaps:
            lines.append('> 未解答：' + escape_text(gap))
        if not section.claims and not section.gaps:
            lines.append('> 未解答：未形成可验证结论。')
        lines.append('')
    return '\n'.join(lines)
