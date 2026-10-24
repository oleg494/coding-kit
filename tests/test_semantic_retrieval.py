"""Lifecycle, isolation and stale-index contracts; synthetic vectors test math only.

Real neural relevance is measured separately by eval/memory_retrieval.py.
"""
import sqlite3
import sys
from pathlib import Path
from contextlib import closing

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'memory' / 'db-tools'))
import search_all
import vector_search
from findings_db import SCHEMA
from memory_corpus import inventory


@pytest.fixture
def store(tmp_path):
    db_dir = tmp_path / 'db'
    db_dir.mkdir()
    db = db_dir / 'research.db'
    with closing(sqlite3.connect(db)) as con:
        con.executescript(SCHEMA)
        con.executemany('INSERT INTO findings(id,created,topic,text,project,importance,verified_at) VALUES (?,?,?,?,?,?,?)', [
            (1,'2026-01-01','checkpoint old','checkpoint restart','alpha','high','2026-01-02'),
            (2,'2026-01-02','checkpoint current','resume after restart','alpha','high',''),
            (3,'2026-01-03','checkpoint elsewhere','other project','beta','normal',''),
            (4,'2026-01-04','checkpoint tombstone','[superseded: replacer deleted]','alpha','high',''),
        ])
        con.execute("INSERT INTO links(from_id,to_id,kind,created) VALUES (2,1,'supersedes','2026-01-02')")
        con.commit()
    return db_dir, db


def test_lifecycle_filters_before_limit_and_no_foreign_project(store):
    db_dir, db = store
    hits = search_all.search_all('checkpoint', db_dir=db_dir, research_db=db,
                                project='alpha', state='current', verification='unverified', limit=1)
    assert [h[4] for h in hits] == [2]
    hits = search_all.search_all('checkpoint', db_dir=db_dir, research_db=db,
                                state='superseded', verification='unverified')
    assert [h[4] for h in hits] == [4]
    assert search_all._json_hits(hits)[0]['superseded'] is True


def test_project_scope_ignores_broken_unrelated_database(store):
    db_dir, db = store
    (db_dir/'unrelated.db').write_bytes(b'not sqlite')
    assert [h[4] for h in search_all.search_all('checkpoint', db_dir=db_dir,
        research_db=db, project='beta')] == [3]


def test_missing_semantic_index_is_not_silent_lexical_fallback(store):
    db_dir, db = store
    with pytest.raises(search_all.SearchError) as error:
        search_all.search_all('checkpoint', db_dir=db_dir, research_db=db, mode='hybrid')
    assert error.value.kind == 'store'
    assert {h[4] for h in error.value.partial} == {1,2,3,4}


class TinyEmbedding:
    """Controlled numeric vectors only; not a semantic model or quality oracle."""
    identity = 'numeric-test-model'
    @classmethod
    def identity_for(cls, directory=None):
        return cls.identity
    def __init__(self, directory=None):
        pass
    def encode_chunks(self, text):
        return [[1.0, *([0.0]*383)]]
    def encode_query(self, text):
        return self.encode_chunks(text)[0]


@pytest.fixture
def numeric_index(store, monkeypatch):
    monkeypatch.setattr(vector_search, 'LocalEmbedding', TinyEmbedding)
    db_dir, db = store
    vector_search.build_index(db_dir, db)
    return store


def test_semantic_lifecycle_and_project_filters_precede_candidates(numeric_index):
    db_dir, db = numeric_index
    hits = search_all.search_all('restart', db_dir=db_dir, research_db=db,
        mode='vector', project='alpha', state='current', verification='unverified', limit=1)
    assert [h[4] for h in hits] == [2]
    assert hits[0].meta['project'] == 'alpha'


def test_edited_or_added_document_refuses_stale_index(numeric_index):
    db_dir, db = numeric_index
    with closing(sqlite3.connect(db)) as con:
        con.execute("UPDATE findings SET text='new evidence' WHERE id=2")
        con.commit()
    with pytest.raises(search_all.SearchError, match='stale'):
        search_all.search_all('restart', db_dir=db_dir, research_db=db, mode='vector')


def test_deleted_findings_never_resurrect_from_index(numeric_index):
    db_dir, db = numeric_index
    with closing(sqlite3.connect(db)) as con:
        con.execute('DELETE FROM findings WHERE id=3')
        con.commit()
    hits = search_all.search_all('restart', db_dir=db_dir, research_db=db, mode='vector')
    assert 3 not in {h[4] for h in hits}


def test_changed_model_requires_rebuild(numeric_index, monkeypatch):
    db_dir, db = numeric_index
    monkeypatch.setattr(TinyEmbedding, 'identity', 'different-model')
    with pytest.raises(search_all.SearchError, match='mismatch'):
        search_all.search_all('restart', db_dir=db_dir, research_db=db, mode='vector')


def test_failed_rebuild_preserves_old_index(numeric_index, monkeypatch):
    db_dir, db = numeric_index
    index = vector_search.index_location(db_dir)
    before = index.read_bytes()
    def broken(self, text):
        raise ValueError('inference failed')
    monkeypatch.setattr(TinyEmbedding, 'encode_chunks', broken)
    with pytest.raises(ValueError, match='inference failed'):
        vector_search.build_index(db_dir, db)
    assert index.read_bytes() == before


def test_source_database_cannot_be_overwritten(store):
    db_dir, db = store
    before = db.read_bytes()
    with pytest.raises(vector_search.VectorError, match='source database'):
        vector_search.build_index(db_dir, db, index_path=db)
    assert db.read_bytes() == before


def test_legacy_unknown_project_filter_excludes_unclassified_rows(tmp_path):
    db = tmp_path/'research.db'
    with closing(sqlite3.connect(db)) as con:
        con.execute('CREATE TABLE findings(id INTEGER PRIMARY KEY,topic TEXT,text TEXT)')
        con.execute("INSERT INTO findings VALUES(1,'old','legacy record')")
        con.commit()
    rows, errors, count = inventory(tmp_path, db, findings_only=True, project='alpha')
    assert rows == [] and errors == [] and count == 1


def test_corrupt_embedding_fails_instead_of_ranking(numeric_index):
    db_dir, db = numeric_index
    with closing(sqlite3.connect(vector_search.index_location(db_dir))) as con:
        con.execute("UPDATE vectors SET vector=? WHERE key='finding:2'", (b'wrong size',))
        con.commit()
    with pytest.raises(search_all.SearchError, match='dimensions'):
        search_all.search_all('restart', db_dir=db_dir, research_db=db, mode='vector')


def test_reads_do_not_modify_source_or_semantic_index(numeric_index):
    db_dir, db = numeric_index
    index = vector_search.index_location(db_dir)
    before = (db.read_bytes(), index.read_bytes())
    search_all.search_all('checkpoint', db_dir=db_dir, research_db=db, mode='hybrid')
    assert (db.read_bytes(), index.read_bytes()) == before
