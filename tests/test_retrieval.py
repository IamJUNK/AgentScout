import pytest
from agent.evidence import select_evidence, split_document
from agent.retrieval.ranking import rrf, cosine_rank
from config import Settings
from models.schemas import SourceDocument
from tools.urls import canonical_url


def test_long_document_tail_and_conditions_keep_offsets():
    text = 'background\n' * 1400 + '# Writer limits\nOnly one writer is allowed.\nHowever, readers may proceed concurrently.'
    chunks = list(split_document(text))
    found = [c for c in chunks if 'Only one writer' in c[0]]
    assert found and found[0][1] > 8000 and 'However' in found[0][0]
    for value, start, end, _ in chunks:
        assert value == text[start:end]


def test_lexical_and_hybrid_selection_are_disclosed():
    doc = SourceDocument(url='user://test', source_id='S1', title='test', content='single writer limit').model_dump()
    questions = [{'id':'q1','text':'writer','queries':['writer']}]
    evidence, info = select_evidence([doc], questions, 1000, settings=Settings(retrieval_mode='hybrid'), embed=lambda texts: [[1.0, 0.0] for _ in texts])
    assert evidence and info['selection_method'] == 'hybrid_rrf'
    _, degraded = select_evidence([doc], questions, 1000, settings=Settings(retrieval_mode='hybrid'))
    assert degraded['selection_method'] == 'bm25' and degraded['degradation']


def test_canonical_url_preserves_semantics():
    assert canonical_url('https://EXAMPLE.com:443/doc?v=2&utm_source=x#part') == 'https://example.com/doc?v=2'
    assert canonical_url('https://example.com/doc?v=1') != canonical_url('https://example.com/doc?v=2')
    with pytest.raises(ValueError): canonical_url('https://name:password@example.com')


def test_rankings_reject_invalid_dimensions_and_stably_fuse():
    with pytest.raises(ValueError): cosine_rank([1,0], [[1]])
    assert rrf([(1,3),(2,1)],[(2,.9),(1,.8)])[0][0] == 1
