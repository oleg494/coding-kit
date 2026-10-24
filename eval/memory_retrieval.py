"""Offline retrieval comparison on a public synthetic bilingual coding corpus.

This is a diagnostic dataset, not held-out production evidence or a universal
quality claim. The explicit model path must already contain local ONNX files.
Only temporary stores are created; no user memories are read or changed.
"""
import argparse
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from contextlib import closing

KIT = Path(__file__).resolve().parents[1]
# Fixed cases are declared before running any retriever; no expected answer in queries.
CASES = [
    ('Session continuity', 'Persist a checkpoint containing pending work and constraints so an interrupted assistant can resume.',
     'How can I pick up unfinished work after restarting?', 'Как продолжить незавершённую работу после перезапуска?'),
    ('Credential hygiene', 'Never put API keys or passwords into logs; redact credentials before recording diagnostics.',
     'How do we prevent secrets appearing in diagnostic output?', 'Как не допустить попадания паролей в журнал?'),
    ('Recovery drill', 'Restore a backup into a disposable directory and verify integrity and searchable records before trusting it.',
     'How do I know the saved copy will actually recover my data?', 'Как убедиться что резервная копия восстанавливается?'),
    ('Atomic publication', 'Write a complete temporary file then replace the destination atomically to avoid half-written output.',
     'How can readers avoid seeing an incomplete file?', 'Как избежать чтения недописанного файла?'),
    ('Retry idempotency', 'Deduplicate payment requests by an idempotency key so retries cannot charge the same customer twice.',
     'What prevents a second debit when a request is sent again?', 'Как не списать деньги дважды при повторной отправке?'),
    ('Evidence freshness', 'Clear previous verification when the evidence changes; old passing results do not validate new contents.',
     'Can I rely on a check that passed before the document was edited?', 'Можно ли доверять проверке выполненной до изменения данных?'),
    ('Project isolation', 'Apply the project filter before ranking so another workspace cannot contribute private findings.',
     'How do I keep another workspace out of my search results?', 'Как исключить сведения другого проекта из поиска?'),
    ('Query failure', 'Distinguish a malformed search expression from a valid query with no matches; return an explicit error.',
     'Does an invalid search expression mean no documents exist?', 'Ошибка поискового запроса означает отсутствие документов?'),
    ('Dependency boundary', 'Optional embedding packages are imported only for semantic modes; keyword retrieval works without them.',
     'Can basic lookup work without installing neural inference libraries?', 'Будет ли обычный поиск работать без нейросетевых библиотек?'),
    ('Source precedence', 'Current user corrections override older stored decisions. Recalled notes do not grant permission to deploy.',
     'Which wins if the latest instruction contradicts an old note?', 'Что важнее новое указание пользователя или старая заметка?'),
    ('Database corruption', 'An unreadable SQLite database makes retrieval incomplete; partial results must carry an error status.',
     'Should successful hits hide a broken database?', 'Можно ли скрыть повреждение базы если часть записей нашлась?'),
    ('Model identity', 'Rebuild embeddings when model weights or tokenization change; vectors from different models are incompatible.',
     'Can an old vector index be reused with different neural weights?', 'Можно ли использовать старые векторы с другой моделью?'),
    ('Local privacy', 'Compute text embeddings on the local CPU. Private memory content must not be transmitted to a hosted API.',
     'How can semantic lookup avoid sending my notes to a provider?', 'Как искать по смыслу не отправляя заметки внешнему сервису?'),
    ('Superseded conclusions', 'Mark replaced decisions as superseded and retrieve their correction rather than treating old advice as current.',
     'What should happen to advice that was later corrected?', 'Что делать с рекомендацией которую позже исправили?'),
    ('Read only retrieval', 'Searching must not create databases, run migrations, repair indexes or log queries to persistent storage.',
     'Can looking up a note unexpectedly modify my storage?', 'Может ли чтение заметки неожиданно изменить хранилище?'),
    ('Long document coverage', 'Split lengthy notes into overlapping token windows so an important decision near the end is still indexed.',
     'How do we find a fact buried at the end of a long document?', 'Как найти факт в конце очень длинного документа?'),
]


def run(model_dir):
    with tempfile.TemporaryDirectory(prefix='kit-retrieval-benchmark-') as temporary:
        root = Path(temporary)
        (root/'db').mkdir()
        (root/'db-tools').mkdir()
        (root/'scripts').mkdir()
        (root/'scripts/_compat.py').touch()
        (root/'VERSION').write_text('benchmark')
        previous = {key: os.environ.get(key) for key in ('MEMORY_ROOT','MEMORY_ROOT_RESEARCH_DB')}
        os.environ['MEMORY_ROOT'] = str(root)
        os.environ['MEMORY_ROOT_RESEARCH_DB'] = str(root/'db/research.db')
        sys.path.insert(0, str(KIT/'memory/db-tools'))
        try:
            from findings_db import SCHEMA
            from search_all import search_all, natural_query
            from vector_search import build_index
            db = root/'db/research.db'
            with closing(sqlite3.connect(db)) as con:
                con.executescript(SCHEMA)
                for i, (topic, text, _, _) in enumerate(CASES, 1):
                    con.execute('INSERT INTO findings(id,created,topic,text,project) VALUES (?,?,?,?,?)',
                                (i,'2026-10-25',topic,text,'benchmark'))
                con.commit()
            built = build_index(root/'db', db, model_dir=model_dir)
            result = {'dataset':'public synthetic bilingual, 16 documents / 32 paraphrase queries',
                      'model_fingerprint': built['model'], 'modes': {}}
            for mode in ('lexical','vector','hybrid'):
                observations = []
                for expected, case in enumerate(CASES, 1):
                    for query in case[2:]:
                        start = time.perf_counter()
                        lookup = natural_query(query) if mode == 'lexical' else query
                        hits = search_all(lookup, limit=5, db_dir=root/'db', research_db=db,
                                          mode=mode, model_dir=model_dir)
                        elapsed = (time.perf_counter()-start)*1000
                        ids = [h[4] for h in hits]
                        observations.append({'expected':expected,'query':query,'ids':ids,'ms':round(elapsed,2),
                                             'rank':ids.index(expected)+1 if expected in ids else None})
                result['modes'][mode] = {
                    'recall_at_5':sum(r['rank'] is not None for r in observations)/len(observations),
                    'mrr_at_5':sum(1/r['rank'] if r['rank'] else 0 for r in observations)/len(observations),
                    'median_ms':round(statistics.median(r['ms'] for r in observations),2),
                    'nonrelevant_top5':sum(len(r['ids'])-(r['rank'] is not None) for r in observations),
                    'observations':observations}
            return result
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.model_dir), ensure_ascii=False, indent=2))
