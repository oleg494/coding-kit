# Memory findings (research.db) — remediation plan

Дата: 2026-09-02. Метод: workflowz-брейшторм — 8 линз (retrieval / lifecycle / datamodel /
write-path / read-path / ops-security / industry / testability) → критик полноты → YAGNI-судья.
Все несущие утверждения перепроверены живьём на prod-базе и в песочнице
(`MEMORY_ROOT_RESEARCH_DB`). Сырьё брейшторма: `local://brainstorm-raw.md`, контекст:
`local://brainstorm-context.md`.

## Что за система

coding-kit v4.0.3. Память = `~/.memory` (корень), движок = `~/.memory/db-tools/` (**junction**
в `coding-kit/memory/db-tools/`), `~/.memory/scripts/` — **copy2-снапшот** (не junction).
Находки живут в `research.db`: `findings` + `links` + `findings_fts` (FTS5 external-content,
синхрон триггерами) + `search_log`. Потребитель — LLM-агент с бюджетом контекста + человек.
Рост: 212 находок, 152 за 7 дней (~22/день), 34 связи. Горизонт: 1k → 10k.

Тесты **есть**: `coding-kit/tests/` — 46 файлов, CI windows+ubuntu. Ранняя «zero tests»
(по `~/.memory`-виду) опровергнута — линза testability это поймала.

## Процесс-гейт (обязателен для КАЖДОЙ фазы)

`integrity-manifest.json` SHA-256-пинит все движковые файлы (`findings.py`, `findings_db.py`,
`ftsquery.py`, `search_all.py`, `log.py`, `tasks.py`, `memory-warmup.py`, `backup_memory.py` —
проверено, все pinned). `deploy.py:65 integrity_gate()` → **exit 3** при дрейфе.

> Правило: правка любого движкового файла → `python scripts/tools/integrity_manifest.py --update`
> → коммит манифеста → иначе деплой заблокирован. Правки в `~/.memory/db-tools` = правки в
> `coding-kit/memory/db-tools` (junction), т.е. в репо.

## Подтверждённые дефекты (сверх 5 известных из первого ответа)

Живые репродукции этой сессии, SQLite 3.53.1:

- **D-A (critical).** `sanitize_query` убивает префиксный поиск. `"body*"` в FTS5 = **точное**
  совпадение токена `body` (звезда внутри кавычек выбрасывается токенизатором), НЕ префикс.
  Доказано: `prox*`→2, `"prox*"`→0, `"prox"*`→2; `агент*`→1, `"агент*"`→0. `firmware*` в
  test_v29 «работает» (3) лишь потому, что `firmware` — и префикс, и полный токен
  (`firmware_2`→`firmware`,`2`); тест маскирует баг. Докстринг `ftsquery.py:8-10`
  («trailing '*' INSIDE quotes keeps prefix meaning») — **ложь**. Единственная защита от
  отсутствия стемминга (RU+EN, unicode61) мертва.
- **D-B (high).** Версия-токен крашит CLI: `findings.py search "5.3"` → `rc=1`,
  `fts5: syntax error near "."`. `.` не в спец-символах (`ftsquery.py:30/34`), FTS5 парсит его
  как column-filter. 58/212 находок содержат `d.d`; доминирующие сущности корпуса — версии.
- **D-C (high).** Миграция `connect()` не перестраивает FTS: строка, существовавшая ДО создания
  виртуальной таблицы, невидима для `MATCH`. Репро: pre-FTS-база → `connect()` → `MATCH 'trigram'`
  → 0 (COUNT показывает 2). Детонирует при restore из `backups/` (штамп уже есть). Тихая потеря
  памяти: `PRAGMA integrity_check` и `doctor.py:268` зелёные (страницы целы, индекс пуст).
  `rebuild` чинит (проверено: 0→1).
- **D-D (critical, изоляция).** `MEMORY_ROOT_RESEARCH_DB` уважает только `findings_db.py:14`.
  Хардкод prod-пути ещё в **6** модулях: `log.py:29`, `tasks.py:45`, `extract_findings.py:47`,
  `githist.py:33`, `repomap.py:182`, `search.py:322`. Каждая «песочная» запись и будущий тест
  write-heavy модулей молча мутирует реальную память. Критик расширил список с 4 до 6.
- **D-E (critical, секрет).** `id=204` содержит рабочий RustDesk-пароль (`пароль …W)`) + IP
  `87.242.85.247` (проверено, regex по read-only). 22 строки с IPv4, 2 с личным email. Текст
  подаётся дословно в контекст каждой будущей сессии (warmup/search/show) и дублируется каждым
  бэкапом. На add-е никакого скрининга.
- **D-F (high, verify_cmd).** `shlex.split` на Windows съедает `\` (`C:\Users\oleg2`→`C:Usersoleg2`)
  и `&&`-цепочка не исполняется как argv (`FileNotFoundError WinError 2` — проверено). 3 из 5
  stored verify_cmd — `cd X && ...`, неисполнимы вечно; только 2 shell-free строки когда-либо
  получили `verified_at`. `cmd_edit` не даёт исправить поле (whitelist = topic/text/tags/source),
  хотя подсказка велит «findings.py edit».
- **D-G (critical, routing).** `AGENTS.md` шлёт «что мы знаем про X» в `search_all.py`, а он
  структурно не видит `research.db` (фильтр по `files_fts`). `search_all.py "workflowz"` → exit 1,
  `findings.py search workflowz` → 3 хита в той же базе. Write-reflex и read-reflex расходятся.
- **D-H (medium, provenance rot).** 5 «висячих» цитат id в shipped-коде: `findings.py:73 id=367`,
  `log.py:95 id=489`, `search.py:89/265/319 id=489/348/540`, `check_file_sizes.py id=543`.
  `MAX(id)=217` → research.db пересоздавали (AUTOINCREMENT-счётчик сброшен), цитаты молча врут.
  Хинт на каждом add учит агента, что инструмент ненадёжен.
- **D-I (medium, supersession dead).** Механизм замены мёртв: links не писались 49 находок
  подряд; `#206 «25 дефектов»` и `#210 «все исправлены»` сосуществуют, search не показывает ни
  сторону → сессия сегодня может чинить 25 уже исправленных багов. 5 contradicts-связей созданы
  одним всплеском 2026-08-26. kinds `extends`/`source` — 0 строк.
- **D-J (medium, split-brain DDL).** `extract_findings.py:209` делает `executescript(SCHEMA)`
  мимо `connect()` → 6-колоночная таблица → `findings.py add` крашится (OperationalError на
  verify_cmd/verified_at). Репро в песочнице. Параллельный DDL-путь.
- **D-K (medium, write-locking reads).** `connect()` на КАЖДЫЙ вызов (search/list/show/stats)
  делает `PRAGMA journal_mode=WAL` + `executescript(SCHEMA)` (пересоздаёт триггеры/индексы,
  берёт write-lock). Параллельные сабагенты сериализуются на write-lock; `database is locked`
  в reflex-записи = тихо потерянная находка (не логируется нигде → ненаблюдаемо).
- **D-L (low, zombie debris).** `~/.memory/db/memory.db` = 0 байт **и** `~/.memory/research.db`
  = 0 байт (второй, в КОРНЕ — критик; физический след бага «join ROOT без db»). Оба копируются в
  каждый бэкап. **ВОПРОС 1 РЕШЁН (2026-09-02):** `db/agent-cian-copy.db` — НЕ клон, а живой индекс
  отдельного проекта `WORK/agent-cian-copy` (2096 файлов, git-коммит 2026-08-30, overlap с
  agent.db 0.73 — общая кодовая база cian). build.py:439 именует БД по `basename(root)`. Удалять
  НЕЛЬЗЯ (проект станет неиндексируемым); search_all-дубли решаются bm25-мерджем P11, не удалением.

Опровержение критика (в план НЕ берём): «search_all.py без UTF-8 reconfigure» — ложь,
`search_all.py:22` вызывает `fix_encoding()` (= reconfigure-обёртка, `_compat.py`).

## План: 15 P-идов в 4 фазы

Порядок жёсткий — по sequencing-traps критика. Каждая фаза: контракт-пин/изоляция/секрет ДО
рефакторов; data-loss-guarantee ДО retrieval; нормализаторы ДО свипа.

### Фаза 1 — Safety net (сделать всё последующее тестируемым, измеримым, неразрушающим)

| P | Что | Файлы | LOC | Verify |
|---|---|---|---|---|
| **P1** | Один резолвер `research_db_path()` в `findings_db.py`; все **6** хардкод-сайтов (log/tasks/extract/githist/repomap/search) импортируют его. Новый pin-тест изоляции. **Первым** — иначе P2/P3 тесты и телеметрия пишают в prod. | `findings_db.py`, `log.py:29`, `tasks.py:45`, `extract_findings.py:47`, `githist.py:33`, `repomap.py:182`, `search.py:322`; `tests/test_findings_isolation.py` (new) | ~10 prod + ~70 test | `MEMORY_ROOT_RESEARCH_DB=$T/x.db` → `log.DB==tasks.DB==extract.DB==$T/x.db`; `pytest tests/test_findings_isolation.py` |
| **P2** | Контракт-пин-тесты before-state: (a) ranking-canary **пинит id-DESC как явный дефект №1** (переписать после P9), (b) comma-tag фильтр **пинит 0-видимых-из-N** (свип P14 должен перевернуть в N — именованно), (c) dedup warn-then-insert. Все 3 — subprocess против temp-базы. Ранжирование-канарейка пинится ПОСЛЕ P8 (звезда/точка меняют match-set); tag-канарейка — ДО свипа. | `tests/test_findings_contracts.py` (new) | ~90 test | `pytest tests/test_findings_contracts.py -q` зелёный на текущем HEAD |
| **P3** | Телеметрия findings-поиска (`log_search` в cmd_search, 2 строки) + вычистить 5 висячих id-цитат (заменить на Wiki-ссылку или убрать id). **ДО** P8/P10: baseline «33% empty» надо мерить на починенном query-пути, иначе логируем «0 hits» для запросов, которые фикс ответит. Но резолвер P1 — ДО телеметрии. | `findings.py cmd_search`, `findings.py:73`, `search.py:89/265/319`, `check_file_sizes.py` | ~6 | `findings.py search dlss` → `SELECT query,hits FROM search_log WHERE db_name='research'` даёт строку; grep висячих id= → 0 |
| **P4** | Секрет/PII-lint в `cmd_add` (stdlib re: пароль/password/token/api_key+значение, gh[pousr]_, AKIA, email, bare IPv4) — hard-refuse на token/secret-формах с `--force`, warn на email/IP. **ДО** любого нового бэкапа/синка. Плюс разовый redact `id=204`. Телеметрия P3 **не** пишет запросы дословно, если в них секрет — скрабб запроса перед `log_search` (критик: телеметрия-vs-скрабб противоречие). | `findings.py cmd_add`; UPDATE #204 | ~20 + 1 data | `findings.py add probe --text 'пароль abcdef123456'` → rc≠0; `SELECT text WHERE id=204` без пароля |

### Фаза 2 — Data-loss guarantee (никакая операция не может тихо потерять/затмить память)

| P | Что | Файлы | LOC | Verify |
|---|---|---|---|---|
| **P5** | `connect()` делает `rebuild` когда `findings_fts` создана в этом прогоне (детект: FTS пуста при непустой findings) + новый `findings.py doctor` (COUNT findings vs FTS, `integrity-check`, при рассинхроне `rebuild` + re-verify, exit≠0). Чинит D-C (restore-bomb). **ДО** P6 — restore-drill его доставка. | `findings_db.py connect()`, `findings.py doctor` (new); `tests/test_findings_migration.py` (new, red→green) | ~45 | `pytest test_findings_migration.py` (pre-FTS fixture → connect 2× → search находит); `findings.py doctor` exit 0 на prod, ≠0 после удаления FTS-строки |
| **P6** | `backup_memory.py --restore BACKUP_DIR [--yes]`: сначала свежий снапшот live в `backups/<stamp>-pre-restore/`, потом restore Wiki+db, потом `findings.py search` подтверждает (P5 вылечил FTS). `backups/` в `~/.memory/.gitignore` (иначе `git add -A` снапшотит 21 МБ секретов). Опц. `MEMORY_ROOT_BACKUP_DEST` — вторая копия ВНЕ папки. Без облака (констрейнт). | `scripts/tools/backup_memory.py`, `~/.memory/.gitignore`, `tests/test_backup_memory.py` | ~60 | `--restore backups/<stamp> --yes` против sandbox MEMORY_ROOT → search даёт хиты; `git check-ignore backups/x` → matched |
| **P7** | Один владелец схемы + read-only чтения + чистка мусора: `connect()` пропускает `executescript` когда схема есть (D-K), `connect(read_only=True)` через `file:...?mode=ro` для search/list/show/stats; **удалить** `extract_findings.py` (235 LOC, 0 вызовов, 0 следов в БД, input-путь не существует — удаление = фикс D-J); удалить оба зомби `db/memory.db` и `~/.memory/research.db` (0 байт); `agent-cian-copy.db` — **решение юзера** (клон). `read_only`-изменение ПОСЛЕ migration-gate и с fallback (mode=ro не может ALTER): warmup уже открывает ro bare-SELECT и должен не сломаться. | `findings_db.py`, удалить `extract_findings.py`+`db/memory.db`+`research.db`(root); install docs | ~20 + delete 235 | grep executescript extract → gone; search под ro работает; `search_all qwen` без `[agent-cian-copy]` |

### Фаза 3 — Retrieval payoff (агент по документированному reflex получает реальные ответы)

| P | Что | Файлы | LOC | Verify |
|---|---|---|---|---|
| **P8** | `ftsquery.py`: снять префикс-звезду НАРУЖУ кавычек (`body*`→`"body"*`, унифицировать с branch-2 который уже правилен), добавить `.` в спец-символы (`v4.0.3`/`5.3`→фраза), + в cmd_search except-branch один retry с quoted-`.` вместо exit 1. **Переписать test_v29 `test_quoted_prefix_still_matches`** на stem-который-не-полный-токен (`prox`/`proxies`), иначе тест продолжает маскировать D-A. Новый `tests/test_ftsquery.py` behavior-matrix. | `ftsquery.py:30/34`, `findings.py cmd_search except`, `tests/test_v29.py` (правка), `tests/test_ftsquery.py` (new) | ~15 prod + ~60 test | `findings.py search 'prox*' --json` → 24 строки (было 0); `findings.py search 5.3` → rc 0 с хитами; `pytest test_ftsquery.py` |
| **P9** | `cmd_search`: `ORDER BY bm25(findings_fts,10.0,1.0), f.id DESC` (веса из `search.py:220`), честный «found: N, showing: M» (COUNT отдельно от LIMIT), `highlight(f.topic,…)` + payload-поля в `--json` (score/source/file/has_verify/verified_at). Чинит дефект №1 (id-DESC = 0/10 overlap с bm25-top-10 на 10k-клоне). `--json` порядок = consumer-visible API: P2-canary именует это изменение. Отклонено: recency-blend exp(-age/τ), importance-веса (нет калибровки). | `findings.py:200-213`, обновить P2-canary | ~20 | `findings.py search 'coding kit' --json` → top-id = ручному bm25-запросу; header «found: 48, showing 10»; у строк score + highlighted topic |
| **P10** | Prefix-retry на пустом результате (query-side, 0 байт хранения): на 0 rows и ≥1 токене len≥4 пересобрать запрос как `"tok"*` через P8-фикс, напечатать «found by prefix (auto)». Зеркалит `search.py:263-274`. **НЕ** trigram-индекс (508 КБ→56 МБ на 10k, ~100×) — он в DEFER за P3-гейтом. | `findings.py cmd_search` | ~15 | `findings.py search стека` → ≥1 строка «found by prefix (auto)» (сегодня «not found») |
| **P11** | `search_all.py`: findings-union-секция (`findings_fts MATCH … ORDER BY bm25`) печатает `[research] finding#<id> <topic> …snippet` + хинт `findings.py show <id>`; глобальный bm25 merge-sort вместо алфавитного db-порядка (Wiki сейчас РАНЖИРУЕТСЯ ПОСЛЕ клона); контракт-тест гоняет **ровно команду из AGENTS.md §4** (`workflowz`). Чинит D-G. Union-секция ДО global-merge; оба ДО правки 6 routing-доков + `eval/scenarios/memory-routing.md` (он кодирует сломанный роут как mock). | `search_all.py`, `tests/test_search_all.py` | ~25 + ~30 test | `search_all.py workflowz` → rc 0, печатает `[research] finding#181`; `search_all.py qwen` → score-desc merge, нет `[agent-cian-copy]` после P7 |
| **P12** | `memory-warmup.py recent_findings()`: вместо `ORDER BY id DESC LIMIT 3` (junk-топики = «скрытая программа», по которой новые агенты имитируют мусор) — feed «в чём память НЕ уверена»: открытые contradicts-связи (JOIN links LIMIT 2) + last-7d строки с пустыми verify_cmd И source; ~200 токенов; + литеральная строка «pull: search_all.py "X"». Push не знает релевантность, но знает неопределённость (растёт с масштабом). | `scripts/memory-warmup.py:132-145` | ~15 | `memory-warmup.py` → вывод содержит contradiction/unanchored + pull-хинт, ≤~250 токенов, нет raw date-topic feed |

### Фаза 4 — Write-path integrity (новые записи несут lifecycle и качество с момента landing)

| P | Что | Файлы | LOC | Verify |
|---|---|---|---|---|
| **P13** | Минимальный supersession-луп: `add --supersedes <ids>` (one-shot link вставка, reuse `:87-93`) + бейдж «⚠ superseded by #N» в search/list (LEFT JOIN links на to_id) + валидация `--related` id (existence-check как `findings_links.py:25-30`). Чинит D-I **без schema-изменения** (links уже моделирует). Status-колонка, active-default фильтр, soft-delete — DEFER за usage-гейтом (file/symbol умерли на 0/212; бейджу надо дать шанс). `--supersedes` ДО первого `cmd_del` по superseded-строке (hard-delete утаскивает contradicts-рёбра). | `findings.py cmd_add/cmd_search/cmd_list`, `:87-93` | ~22 | `add new --supersedes 54` → `search 'behavior oracle' --json` строка id 54 несёт `superseded_by:58`; `add x --related 99999` → rc≠0 (сегодня silent orphan) |
| **P14** | Write-path гигиена (всё в cmd_add/cmd_edit/cmd_search): tag-нормализация (lowercase, comma→space, collapse) + разовый свип 32 comma-строк; auto-promote первого URL из text в пустой source; topic-style warning (date/>60char/prefix-collision → stderr с auto-slug, НЕ CHECK-constraint); normalized dedup (lower(trim) минус trailing date) печатает «edit id=N instead»; `CREATE INDEX idx_findings_topic`. Нормализаторы ДО свипа (иначе 22/день пере-грязнят между свипом и валидатором). DEFER: finding_tags join-table (за post-normalization usage-гейтом), UNIQUE(topic) (сначала разрешить 4 dup-пары). | `findings.py cmd_add/cmd_edit/cmd_search:211`, UPDATE 32 строк | ~30 + sweep | `pytest test_findings_contracts.py` (comma-case обновлён); `list --tag multiproxy` → включает бывшие comma-строки; `SELECT COUNT WHERE tags LIKE '%,%'` → 0 |
| **P15** | `verify_cmd` исполняем: `cmd_verify` передаёт строку в `_compat.run(shell=True)`, убрать `shlex.split` (D-F); дешёвый quote-balance reject на add; расширить `cmd_edit` whitelist на `verify_cmd/file/symbol`; правка help-текста. Предусловие любого будущего staleness-sweep (DEFER). Отклонено: JSON-argv миграция (ломает 5 строк), exec-allowlist/sandbox (непропорционально для локальной single-user машины, где писатели уже держат shell). | `findings.py cmd_verify:177-179, cmd_add, cmd_edit` | ~12 | `findings.py verify 43` (stored `cd … && pytest`) реально исполняется и stamp/FAILED rc; `findings.py edit 43 --verify-cmd 'python x.py'` теперь проходит |

## DEFER (реально, но преждевременно — за измеримым гейтом)

| Что | Гейт |
|---|---|
| `findings_fts_trigram` индекс + auto-fallback (search.py parity) | P3-телеметрия, ≥4 недели findings-side строк ПОСЛЕ P8+P10: если research-db empty-rate всё ещё > ~33% wiki-benchmark (цена: 508 КБ→56 МБ на 10k, ~100×, 3 триггера). Prefix-retry должен быть ДАННЫМИ показан недостаточным, не аналогией |
| `status` колонка + `WHERE status='active'` default + `--all` | P13 usage: агенты реально пишут supersedes/contradicts (≥10 новых связей за 4 недели) И телеметрия/аудит показывает superseded-строки всё ещё всплывают как current |
| Soft-delete (`del --replaced-by`) + `merge` | Тот же status-гейт, ИЛИ первый измеренный инцидент удаления находки с load-bearing связями (5 удалений уже было молча) |
| `finding_tags` join-table + controlled vocabulary + `GROUP BY tag` facet | Post-P14 нормализация: tag-adoption среди новых записей (сейчас 52/212, 75% пусто, 79/102 singleton) — строить только если теги реально заполняются И появился спрос на фильтрацию/synonym-merge |
| Per-finding usage (hits/last_seen) + use-based decay/eviction | ≥30 дней P3-строк db_name='research' + конкретный eviction-policy proposal; сначала проверить, отвечает ли query-level лог |
| `verify_status` колонка + `findings.py stale` sweep | P15 ships + verify_cmd adoption >~10% с хотя бы одним observed failing re-check (сегодня 5/212, 0 failures записываемы). Sweep по 2% adoption = механизм для пустой комнаты |
| Stable `uid` + seconds-UTC created | Первый реальный restore-from-backup (P6 вне теста), инвалидирующий внешнюю цитату. Сегодня фикс = вычистить 5 stale-ссылок (P3) |
| `author` колонка + `[SUSPECT]` flagging + quarantine | Первый подтверждённый finding, который увёл сессию не туда, ИЛИ second-writer/multi-machine event. MEMORY_AGENT_ID plumbing нет; колонка со stamped 'human' = confidence-column провал (file/symbol 0/212) |
| `--type log\|durable` для activity-log строк (~20% записей) | P12 unsure-feed уменьшает видимый вред; затем spot-audit на 500 находках: если session-journal всё ещё доминирует в выдаче |
| file/symbol: drop ИЛИ populate (project-scoped `--file`) | Телеметрия/прямой запрос показывает project-scoped retrieval demand. Дешёвый populate = reflex в AGENTS.md передаёт --file |
| `user_version`-gated ordered MIGRATIONS chain | Третья настоящая схема-миграция в одном поезде (сегодня 2 additive ALTER влезают в if-col-missing блок). Цепь зарабатывает когда if-лист реально даст дрейф-баг |
| links rebuild: FK + kind CHECK + UNIQUE(from,to,kind) + self-guard | Любой orphan/duplicate/self link в prod ПОСЛЕ P13 app-side `--related` валидации. PRAGMA foreign_keys per-connection — миграция даёт мало сверх 2-строчного guard |
| UNIQUE index на topic (hard dedup) | P14 normalized warn-only dedup 4 недели с растущим dup-topic accumulation И после ручного разрешения 4 exact + 6 prefix dup-пар. Открыт WAL-race вопрос (check-then-act в cmd_add) |
| doctor byte-compare `~/.memory/scripts` copy2 vs kit | Первый observed md5-дрейф (2026-09-02 байт-идентичны). Junction-ing scripts/ отклонён (install.py легитимно держит там tools/) |
| Split text → claim (≤1 line) + evidence | Именованный query-класс, который проваливается на blob (пара 192/193 = симптом). Отказать пока запрос не докажет |
| `tests/_memory_fixtures.py` seed builders | Написать 3 новых test-файла после P1/P2; если mkdtemp/env boilerplate измеримо мешает покрытию (3-module gap был isolation, не fixtures — P1 убирает настоящий блок) |

## REJECT (тяжелее нужного / нарушение констрейнтов)

- **Embeddings / sqlite-vec / hybrid RRF / semantic search / LLM re-rank** — нарушение stdlib-only; recall-проблема с measured zero-dep фиксом (prefix-retry 0→24 на prox*); top-k full-text/rerank ломает контекст-бюджет потребителя.
- **mem0-style LLM ADD/UPDATE/DELETE merge на write** — CLI не зовёт LLM; merge в каждом агент-промпте = AGENTS.md contract rewrite + model-call per add. Supersession = один existing-table флаг (P13).
- **Alembic/yoyo migration engine** (version table, ordered steps, downgrade) — один forward-only локальный файл = integer+list максимум, и тот DEFER. D-J чинится удалением параллельного DDL-пути (P7), не фреймворком.
- **SQLCipher encrypted-at-rest / secrets vault / cloud sync / git-bundle remote push** — внешняя зависимость + key management для accidental capture (P4 lint пропорционален); облако = exfiltration-канал для хранилища с кредами и топологией серверов, против no-upload констрейнта.
- **Scheduled daemons** (cron staleness sweep, standing findings linter в CI/Session End) — второй failure domain, поддерживающий пустое поле (2.4% verify_cmd); гигиена = разовый backlog (P4/P14), не unattended job.
- **Per-item FSRS/SM-2 с retention grades** — нужны easy/hard review events, которые LLM-агент надёжно не даст + scheduler UI; plain access counting (DEFER за P3) даст 90% eviction-сигнала.
- **Author/confidence/suspect колонки + review queue + quarantine state machine** — колонки, которые единственные писатели (свои агенты) не заполнят (file/symbol 0/212 = доказательство); human approval gate = friction, который обходят.
- **Rewrite sanitize_query как tokenizer-aware FTS5 parser** (quote state machine) — whitespace-token модель доказуемо достаточна после star-peel + '.'-quote (P8).
- **Custom/simple tokenizer ИЛИ `format=` для атомарного индекса версий** — full reindex всех live-бд + schema migration prod-файлов ради того, что phrase-quoting уже даёт (`"v4.0.3"`=2=LIKE-эквивалент).
- **Recency-blended ranking (bm25+exp(-age/τ)) и per-source weights (wiki×2)** — hand-tuned константы с нулём калибровочных данных; измерения не показывают случая где plain relevance-then-recency проигрывает.
- **verify_cmd как JSON argv + confirmation prompt / allowlist / sandbox** — array миграция ломает 5 строк, агенты всё равно пишут shell-строки; exec gating непропорционален на solo-машине где писатели уже держат shell (ACE-риск = тот же trust domain что гоняет backup_memory).
- **Unified findings-into-files_fts через build.py** (один мега-корпус) — schema coupling двух владельцев, trigger rework, rel_path-семантика не подходит находкам; UNION-секция в уже-mandated инструменте (P11) закрывает тот же гэп за ~25 строк. **Внимание**: `build.py:438` уже ОТКАЗЫВАЕТ проекту с именем 'research' (комментарий признаёт прошлое уничтожение wiki.db) — любой «unify indexes» не должен вернуть эту коллизию.
- **Bitemporal/revision history** (valid_from/valid_to, findings_revisions, FTS-synced triggers на UPDATE) — 5+ колоночная миграция и rewrite всех запросов для store, читаемого snippet-агентами; одно link-ребро + deletion-printed-links = сохраняющий-свидетельства минимум.
- **GraphRAG entity resolution / pairwise cluster-merge / transcript auto-capture** — build-time similarity passes для collision-mode который string-identical ИЛИ date-stamped (P14 normalization ловит); auto-capture на 212 находках = volume firehose ровно того junk-профиля, с которым корпус борется; удаление (P7) = YAGNI-ответ.
- **CHECK-constraints/rejects на topic shape; per-project research DB; session-start relevance auto-injection hooks** — hard-fail mid-task против friction-правила (warn+auto-slug в P14); фрагментация id/links/warmup/dedup по файлам; hook plumbing = 3+ адаптера для miss-prone догадки, pull-путь (P11) сначала.
- **Standalone query-stats table / query-broker / golden-output snapshot framework / coverage-% targets / conftest fixture-plugin** — больше механики чем нужда: log_search + existing search_stats уже служат (P3), 2 INSERT в одну существующую таблицу бьют брокера, три ассерта бьют baselines, реальный риск сьюты = maintenance cost против 4309 LOC.

## Открытые вопросы к юзеру (блокируют часть фазы 2/3)

1. **`db/agent-cian-copy.db` — РЕШЕНО (2026-09-02).** Не клон: живой индекс отдельного проекта
   `WORK/agent-cian-copy` (2096 файлов, git 2026-08-30). НЕ удалять. P7/P11 verify: «нет
   [agent-cian-copy]» заменяется на «agent-cian-copy ранжируется bm25-мерджем, не алфавитом».
   **Но бэкап-след (advisory #1 secondary):** `backup_memory.py:80-93` копирует КАЖДЫЙ `db/*.db`
   в каждый штамп (REBUILDABLE = только `__pycache__`). Кодовые индексы (`agent.db` 6 МБ,
   `coding-kit.db` 5.4, `wiki.db` 4.5, `agent-cian-copy.db` 4.4) **пересобираются** `build.py`
   из исходников — невосстановимы только `research.db` (находки) и `Wiki/`. Итог: ~21 МБ
   пересобираемого состояния × 10 штампов = ~210 МБ бэкапов ради данных, которые не являются
   данными. **P6 расширяется**: бэкапить только `research.db` + `Wiki/` (+ опц. полный режим
   флагом), кодовые индексы — исключение с документированным «rebuild via build.py».
2. **Multi-machine convergence — РЕШЕНО (2026-09-02).** На этой машине ОДИН store:
   `Desktop/memory` = junction → `.memory` (тот же realpath, та же research.db, 213 находок).
   `.coding-kit` (единственный второй корень) = мёртвый install v2.7, 1 smoke-finding — **УДАЛЁН**
   с одобрения юзера (246 файлов, 3.4 МБ). `MEMORY_ROOT` unset, git remote пусто. Вывод: это была
   **разовая миграция**, не двухмашинная история → record-merge tool (last-writer-wins) остаётся
   в REJECT/DEFER до факта появления второй машины. `git log --all -S` + `cat-file --batch-all-objects`
   на обоих .memory-репо: credential в истории НЕ появлялся (git-объекты zlib — byte-walk по .git
   структурно слеп, проверяется только декомпрессией).
3. **~/.memory git-гигиена — РЕШЕНО: вариант A (2026-09-02).** Агенты git НЕ трогают;
   `git_stale_days()` в memory-warmup.py печатает `! git stale: Nd … (human ritual)` при N≥7.
   Сейчас N=14. Обоснование A над B: автокоммит агента закрепляет ошибочную находку как канон в
   истории + параллельные агенты дают конфликт в одну минуту; A = ноль риска, человек владеет
   «что есть истина». B (автокоммит в Session End) стал технически безопаснее после того, как
   `backups/` попал в .gitignore, но отклонён по сути. Тесты: WarmupGitStaleTest (non-repo → -1,
   backdated commit → ~30d). `backups/` в ~/.memory/.gitignore добавлен СРАЗУ в раунде 2, не отложен до P6.

## Несущие риски исполнения (cross-cutting)

- **6+ модулей на один файл**: P1 (резолвер) + P5 (backfill) + P7 (read-only/DDL-guard) + P13/P14/P15 все трогают `findings_db.py`/`findings.py`. Один владелец интеграции, сериализовать мутационную границу `findings_db.py`; P1 строго первым.
- **warmup dual-personality**: уже открывает research.db `mode=ro` bare-SELECT (`warmup:137`) и НЕ может гонять миграции. Если P5/P7 делают `connect()` требующим миграцию, warmup-овский `except sqlite3.Error` молча вернёт `[]` и session-start память исчезнет без ошибки. P12 правит warmup ПОСЛЕ P5/P7, с явным ro-путём.
- **exit-code = API**: `search --json` пусто → rc 0 `[]` (пиннут `test_findings_cli_machine.py:85`), а `.`-запрос → rc 1. Fallback-предложения (P8 retry, P10 prefix-retry) меняют rc и stdout-форму для главного LLM-потребителя; 6 kit-доков + `eval/scenarios/memory-routing.md` встраивают CLI-текст — doc-sweep ПОСЛЕ P8/P10/P11.
- **ranking-canary порядок**: P2 пинит id-DESC, но канарейка измеряет match-set который меняет P8 → P2 ranking-часть коммитится/обновляется согласованно с P8, tag-часть — до P14-свипа.

---

## Статус исполнения

**Фаза 1 (P1-P4) — ГОТОВА 2026-09-02 + ТРИ review-раунда закрыты. Фаза 2: P5 — ГОТОВ.**
Полный набор: 574 passed, 1 skipped. doctor: 14 GREEN. integrity_manifest обновлён (127 файлов), integrity_gate PASS.
- P1: `research_db_path()` в findings_db.py + 6 сайтов переведены (log/tasks/githist/extract/repomap/search) + test_findings_isolation.py (3 теста: 5 module-констант subprocess-пин, default-путь, **поведенческий пин repomap._findings_for/search._did_you_mean** — функция читает sandbox-данные, а не prod; review advisory #2).
- P2: test_findings_contracts.py — 3 пина before-state (ranking id-DESC, comma-tag invisible, dedup warn-then-insert).
- P3: log_search в cmd_search (со скраббом запроса) + 5 висячих id-цитат вычищены (findings.py/search.py×3/log.py/check_file_sizes.py). **Orphan**: `~/.memory/scripts/tools/check_file_sizes.py` (RU-перевод, id=543 жив, install.py ничего не деплоит в tools/, BASELINE_PATH мёртв) — P7 zombie-кандидат; живой код зовёт kit-копию (doctor.py:247).
- P4: find_secrets/scrub_text + lint в cmd_add/cmd_edit (--force) + test_findings_secrets.py (14).

**Review-раунд (advisories, 2026-09-02) — что исправлено:**
- BLOCKER: credential пережил SQL-redaction в байтах live-файла и в бэкапе. Закрыт: redact в бэкапе → `VACUUM` + `wal_checkpoint(TRUNCATE)` на live и бэкапе → byte-scan ВСЕГО ~/.memory (295 файлов) = **0 hits**. `backups/` добавлен в ~/.memory/.gitignore СРАЗУ (не отложен до P6).
- BLOCKER: живой пароль был вписан в fixtures test_findings_secrets.py (репо с public origin!) — заменён на синтетический `Zq8XwVrTnLm` + комментарий «fixtures must never carry a real credential»; grep kit-дерева = 0 hits; в git-историю kit НЕ попадал (log -S = 0).
- FP-гейт (advisory #4): corpus-replay по 214 live-строкам нашёл id=53 «record_token_usage … Only token -m …(9)» — hard-refuse сломал бы reflex. `_looks_secret` ужесточён (alnum-start, без структурной пунктуации `(){}[]<>|;&`, entropy). После: 0 blocking-hits на корпусе, все 6 реальных форм блокируются.
- Leak-in-guard (advisory #5): дескрипторы find_secrets = имена паттернов (aws-access-key/github-token/private-key-block/keyword+value), НИКОГДА срез match — stderr уходит в transcripts.
- **ОСТАТОК (вращение!): литерал пароля жив в 7 локальных session-transcripts** (~/.omp/agent/sessions, ~/.claude/projects, включая эту сессию) — redaction их не лечит. Реальная mitigation = **сменить пароль RustDesk** (и считать его скомпрометированным: он светился в stderr, транскриптах и до 2026-09-02 17:5x в байтах live-базы).

**Review-раунд 2 (advisories, 2026-09-02) — что исправлено:**
- BLOCKER (quoted-value FN): `password="hunter2x"` проходил — regex захватывает кавычки в `val`, alnum-gate видел `"`. Фикс: `_looks_secret` делает `val.strip("'\"")` ДО shape-проверок. Тесты: quoted-формы в test_token_shapes_block + test_quoted_value_strips_before_shape_check.
- BLOCKER (choke-point bypass): cmd_add сканировал topic+text+source, но вставлял **verify_cmd непроверенным**; cmd_verify печатает его verbatim в stdout при каждом re-verify (= утечка в transcript). cmd_edit сканировал только --text, не --topic/--source. Фикс: add сканирует +verify_cmd; edit сканирует все 4 whitelist-колонки. Тесты: test_add_refuses_credential_in_verify_cmd, test_edit_refuses_credential_in_topic_and_source.
- Метод byte-scrub (advisory): grep по .memory — ложно-чистый (бинарные файлы скипаются). Единственно верный = raw byte read каждого файла ЯВНО. Прогнано: все *.db + -wal/-shm в ~/.memory/db, ВЕСЬ бэкап-штамп (6 баз + root-zombie без findings-таблицы — не путать с db/research.db), ~/.coding-kit/db → **76 уникальных файлов, 0 hits**. Corpus-replay после фикса: 0 blocking-hits на 215 строках (reflex цел), id=53-FP не вернулся.
- Тестовый nit: поведенческий пин repomap/search конвертирован в subprocess (in-process import кэшировал ROOT/DEFAULT_DB в sys.modules и тёк sys.path в 561-тестовый прогон). Проверено: modules leaked = NONE.
- ДИЗАЙН-ГРАНИЦА lint (задокументирована в тесте): блокируются keyword+value и известные token-формы; bare high-entropy слово БЕЗ keyword НЕ блокируется by design (entropy-only отказывал бы легитимную прозу). Escape = --force.

**Review-раунд 3 (advisories, 2026-09-02) — что исправлено:**
- Cross-field FP (блокер reflex): `" ".join(полей)` давал regex-мост — keyword в конце --text + dated --source (все plan-имена датированы!) = hard-refuse на документированном `add "<topic>" --text --source` пути. Фикс: каждое поле сканируется НЕЗАВИСИМО в cmd_add и cmd_edit (credential никогда легитимно не пересекает границу поля). Плюс `_PATHISH`-гейт: path/version/date-формы значений (`docs/v2.9-2026`, `2026-09-02-…`) не credentials. Тесты: точные repro-пары в test_prose_passes + CLI test_add_reflex_with_dated_source_passes (rc=0).
- Credential-URL класс ДОБАВЛЕН (advisory-опция 2): `curl -u user:pass` и `scheme://user:pass@host` — канонические verify_cmd-формы, P15 делает shell=True. Паттерны точные (значение через _looks_secret; `https://host:8080/path` и DSN без userinfo НЕ триггерят — тесты на обе стороны).
- Git-история проверена ПРАВИЛЬНЫМ методом (byte-walk по .git читает zlib как plaintext — структурно слеп): `git log --all -S` = 0 hits и `cat-file --batch-all-objects --batch` (все объекты, вкл. unreachable) без литерала — в ~/.memory И в backups/20260902T085826/.git. История чиста; ротация пароля RustDesk остаётся единственной полной mitigation (7 transcripts).
- Corpus-replay после всех фиксов: **1 blocking-hit на 216 строках = id=75, TRUE POSITIVE** (реальный proxy-credential `user:pass@127.0.0.1:4418` в тексте с 2026-08-27, найден новым url-userinfo паттерном). Инвариант изменён: не «0 hits», а «только true positives». Судьба id=75 (redact / оставить как есть / --force-переписать) — решение юзера, localhost-proxy не remote-exploitable.
- Юзер одобрил: мёртвый `~/.coding-kit` (v2.7, 1 finding 'Smoke test port', 246 файлов 3.4 МБ) — **УДАЛЁН** 2026-09-02.
- Полный набор: 567 passed, 1 skipped. doctor 14 GREEN. integrity_gate PASS.
- Забавный факт: находка-урок id=221 была дважды отказана собственным lint (литеральные примеры форм в тексте) — записана переформулированной. Это корректное поведение: обсуждение секретов не должно содержать литералов форм.

**Вариант A (Q3) реализован 2026-09-02:** `git_stale_days()` в memory-warmup.py — warning
`! git stale: 14d … (human ritual)` при ≥7d, в text и JSON-вывод full-warmup. Тесты:
WarmupGitStaleTest (non-repo → -1; backdated commit через GIT_AUTHOR/COMMITTER_DATE → ~30d).
Deployed-копия ~/.memory/scripts синхронизирована copy2 (drift был — kit и deployed разошлись
моим же фиксом; пересинхронизировано, md5 IDENTICAL). Doctor-гейт encoding discipline поймал
мой subprocess.run(text=True) без encoding= — исправлено (gate работает).

**P5 — ГОТОВ 2026-09-02 (restore-bomb D-C закрыт):**
- `connect()` в findings_db.py: backfill — если `findings_fts_docsize` пуста при непустой
  `findings` (индекс создан над pre-existing строками, restore/миграция), выполнить
  `INSERT INTO findings_fts(findings_fts) VALUES('rebuild')`. Только empty-index кейс —
  чтения остаются дешёвыми; частичный desync — работа doctor.
- `findings.py doctor` (новый subcommand): COUNT findings vs FTS + FTS5
  `integrity-check` **rank=1** → при проблеме `rebuild` + re-verify; exit≠0 только
  если лечение не помогло. Чинит класс «silent memory loss»: PRAGMA integrity_check
  (doctor.py:268) пропускает пустой FTS-индекс.
- **Уточнение 2026-09-02 (advisory-раунд, измерено):** content-сравнение у
  external-content FTS5 включается ТОЛЬКО при rank=1 (SQLite docs §6.7). Bare-форма
  (rank=0) проверяет лишь shadow-структуры: PASSED на пустом индексе над 2 строками и
  на stale-контенте с равными counts; rank=1 → 'database disk image is malformed' /
  'checksum mismatch' на обоих классах, PASSED на здоровой и полеченной. rank=1 —
  write-tx INSERT (на mode=ro raises), поэтому в read-пути (connect/search) остаётся
  дешёвый count-детектор, rank=1 живёт в doctor и в drill (на temp-копии).
- tests/test_findings_migration.py (7 тестов): pre-FTS строки видимы после миграции;
  идемпотентность (2×connect, обе строки ровно один раз, **docsize==table — прямой пин**);
  doctor OK на здоровой; doctor лечит частичный desync (DELETE из findings_fts → rebuild →
  поиск снова находит); doctor ловит stale-контент с равными counts (DROP триггера +
  UPDATE → rank=1 checksum mismatch → rebuild → поиск отдаёт НОВЫЙ текст); rank=1 чист
  на здоровой.
- Prod-проверка: `findings.py doctor` → OK, findings=217, docsize=217, integrity-check passed;
  prod-поиск жив (workflowz → 6 hits).

**P6-advisory раунд — ГОТОВ 2026-09-02 (drill видит findings + lint-дыры закрыты):**
- `scripts/tools/backup_memory.py::_findings_probe` — findings-половина restore drill
  (advisory: search_all не видит research.db — нет files_fts; PRAGMA integrity_check
  слепа к FTS-desync). Три слоя: (1) raw rank=1 на TEMP-копии (connect() залечил бы
  пустой индекс до детекта — «приехал desync-ным» видит только raw-проверка до
  connect); (2) `findings.py doctor` rc; (3) функциональный MATCH токена, ВЫВЕДЕННОГО
  из восстановленных строк (первый unicode61-токен новейшего длинного text; прод-бэкап
  не содержит тест-литералов). Нет findings/нет FTS/нет токена → search skip.
  `main()` гейтит rc на findings.ok.
- Probe-гигиена: MEMORY_ROOT НЕ наследуется subprocess-ом (seeded-корень тестов без
  маркеров → RuntimeError в _compat на импорте); unreadable db → sqlite3.Error ловится,
  probe не крашит drill.
- `_seed_memory_root` сеет research.db из прод-Schema (findings_db.SCHEMA): bare
  (id,topic,text) ломал search CLI ('no such column: f.created') — пре-существующий
  дефект сида, вскрытый только теперь, когда probe реально дёрнул поиск.
- Lint (P4): keyword+value — lookaround-границы вместо \b + `access[_-]?key|aws`
  (`\b` умирал на подчёркиваниях `aws_secret_access_key`, измерено: литерал проходил);
  отдельный паттерн `aws-secret-key` для underscore-идентификатора (значение идёт ПОСЛЕ
  всего идентификатора, keyword+value ловил val=`_access_key=…` → gate); `_pathish`:
  bare `/` БОЛЬШЕ не pathish (base64/AWS slash-heavy), многосегментный путь pathish
  только если последний сегмент с точкой (`docs/…/plan.md` exempt, `abc/def123` и
  `…/bPxRfiCYEXAMPLEKEY` блокируются). Фикстуры: 4 block + 1 block-pathish.
- Тесты drill: probe видит восстановленные строки (token/hits/rc) + probe флажит
  пустой индекс (drill rc=1).
- Верификация: 577 passed, 1 skipped, 73 subtests; manifest 127; doctor kit 14 GREEN;
  **prod-drill на реальном бэкапе 20260902T085826: findings=204, rank=1 passed,
  doctor rc=0, token '2026' → 10 hits, rc=0**.
- Находка id=224 (rank=1-урок: проверять форму вызова по докам ДО записи вывода).

**Финальный advisory-раунд P6 — ГОТОВ 2026-09-03:**
- Lint: `aws` УБРАН из keyword+value (FP на `aws iam-role-2024 assumed`; compound-форма
  покрыта `aws-secret-key`, у которого разделитель теперь опционален — space-форма
  `aws_secret_access_key wJal…` блокируется); `_pathish` знает backslash-сепаратор
  (Windows-путь `C:\Users\…\notes.md` — ref, не credential: kit живёт на Windows).
- Probe: CLI-резолв с fallback-цепочкой (repo kit → deployed root → live root →
  restored) + `cli` в выводе (skip отличим от fail); `search_rc`/`search_err` пишутся
  (ошибка поиска больше не схлопывается в «0 hits»); токен поиска — БУКВЕННЫЙ
  `[^\W_\d]{3,}` ('2026' — самый насыщенный токен стора, слой почти ничего не
  проверял; прод-drill теперь выводит 'User').
- Тесты doctor пинят ЧИСЛА детекта, не слово 'rebuild': healthy → нет 'desync'/
  'integrity-check failed'; partial → 'findings=2'+'indexed=1'; stale → именно
  'integrity-check failed' (counts равны, desync-строка fired быть не может).
- **Corpus replay (плановый гейт lint-раунда): 224 живых строки, blocking hits = 1
  (id=75, документированный true-positive) — новых FP нет.**
- Верификация: 577 passed, 1 skipped, 73 subtests; manifest 127; doctor 14 GREEN;
  prod-drill rc=0 (204/204, rank=1 passed, token 'User' → 10 hits).

**P6-собственно — ГОТОВ 2026-09-03:**
- `backup_memory.py backup()`: default scope = CORE (`db/research.db` + `Wiki/`) —
  единственное не-пересобираемое состояние; кодовые индексы (agent.db 6 МБ и др.)
  больше не дублируются в каждый штамп (~21 МБ/штамп не-данных, план Q1). `--full`
  = старый whole-root walk. `skipped[]` в выводе: unreadable live db не роняет снапшот
  (DR-кейс: pre-restore снапшот поверх мёртвой базы).
- `MEMORY_ROOT_BACKUP_DEST` → вторая копия ВНЕ папки бэкапов (copytree + prune, без
  облака по констрейнту); нет env → `offsite: null`.
- `--restore DIR [--yes]`: (1) pre-restore core-снапшот `<stamp>-pre-restore` ДО
  мутаций, (2) replace Wiki + research.db (corrupt live db: unlink + sidecars, не
  краш), (3) `_findings_probe` на LIVE store → rc=1 если verify не зелёный.
- Тесты: core-vs-full scope, offsite-копия, live-restore с pre-снапшотом и verify,
  restore лечит corrupt live db.

**P7 — ГОТОВ 2026-09-03 (один владелец схемы + ro-чтения + мусор удалён):**
- `connect()`: DDL (executescript + WAL-pragma) только когда схема отсутствует ИЛИ
  частична (pre-FTS store: findings без findings_fts; упавший триггер
  findings_ai/ad/au — тоже «частична», иначе индекс молча дрейфует на UPDATE);
  WAL-переключение толерантно к локу. Полная схема = connect() без write-лока (D-K).
  Честно: search всё равно пишет ОДИН INSERT-телеметрию в search_log (log._connect
  с тем же presence-guard: executescript только при отсутствии таблицы); lock-free
  reads — это list/show/stats.
  verify_cmd/verified_at вошли в SCHEMA (single owner), ALTER-блок остался для старых БД.
- `connect_read()` (новый): `file:...?mode=ro` для search/list/show/stats; без DDL и
  backfill; ro-open УСПЕШЕН на desync-сторе, поэтому empty-index check маршрутит
  лечение в rw connect() — D-C не молчит на read-пути. Advisory-nit учтён: heal =
  write, живёт в rw-пути (doctor/drill), не в ro.
- Тесты ReadOnlyConnectTest (3): write через connect_read raises readonly;
  connect_read лечит empty-index (search не пустой); connect() не пишет под
  BEGIN IMMEDIATE (RESERVED: читатели проходят, писатели блокируются — EXCLUSIVE
  блокировал бы даже PRAGMA-чтения, premise теста исправлена по факту).
- Мусор удалён: `extract_findings.py` (235 LOC, 0 вызовов, параллельный DDL-путь D-J),
  зомби `db/memory.db` (0b) и корневой `research.db` (0b), deployed-orphan
  `~/.memory/scripts/tools/check_file_sizes.py` (живой код зовёт kit-копию).
  test_findings_isolation MODULES: extract_findings убран.
- Верификация: 584 passed, 1 skipped, 73 subtests; manifest 126 (−1 файл); doctor 14
  GREEN; prod-smoke: search/stats/doctor живы через ro; prod-drill rc=0 (204/204,
  rank=1 passed, token 'User' → 10 hits); warmup по документированному пути
  (`~/.memory/scripts/memory-warmup.py`) = Wiki 33, findings 224 (запуск warmup через
  kit-путь даёт 0 — warmup резолвит db относительно СВОЕГО файла, это его
  пре-существующий контракт deployed-копии, не регрессия P7).

**Фазы 3–4 (P8–P15) — ГОТОВЫ 2026-09-03. Полный набор: 626 passed, 1 skipped,
73 subtests; manifest 126; doctor 14 GREEN; deployed-синк через install.py.**
- **P8** ftsquery: звезда ВСЕГДА снаружи кавычек (`prox*`→`"prox"*`), `.` в спец-символах
  (`5.3`→фраза), `fallback_query()` (dot-split) + один retry в cmd_search except-ветке.
  test_v29 переписан на stem-не-полный-токен (`prox`/`proxies`); tests/test_ftsquery.py
  (behavior-matrix, 6 тестов). Prod: `search 5.3` → rc 0, 8 hits (было rc 1).
- **P9** cmd_search: `ORDER BY bm25(findings_fts,10.0,1.0), f.id DESC`; честный
  «found: N, showing: M» (COUNT отдельно); highlight(topic) в human-строке; --json
  payload + score/file/has_verify/verified_at/superseded_by. P2-ranking-canary
  ПЕРЕПИСАН в after-state (id=1 первым, score монотонен) — согласованно с P9 по плану.
- **P10** prefix-retry на 0 строк (токен len≥4 → `"tok"*`), «(found by prefix (auto))»,
  честный COUNT и в prefix-ветке. Prod: `search workfl` → 9 hits с пометкой.
- **P11** (воркер P11SearchAllUnion): search_all.py переписан — findings-union
  (`[research] finding#<id> <topic> …snippet` + хинт `findings.py show <id>`) +
  глобальный bm25 merge-sort (те же веса 10.0/1.0 = единый ранкинг поверхностей);
  trigram-нога bm25 нативно. tests/test_search_all.py переписан (25 тестов, включая
  литеральную команду AGENTS.md §4). Prod: `search_all.py workflowz` → rc 0, 5 research-строк.
- **P12** (воркер P12WarmupUnsureFeed): warmup recent_findings → unsure_feed: открытые
  contradicts (LIMIT 2) + last-7d без verify_cmd И source (LIMIT 3) + ШАБЛОН
  `pull: search_all.py "<your topic>"` (фикс-запрос был бы junk-push);
  ro bare-SELECT, connect() не зовётся (dual-personality).
  Prod-вывод: 2 contradiction + 3 unanchored + pull-хинт, блок ~150 токенов.
- **P13** `add --supersedes` (link kind='supersedes') + бейдж «⚠ superseded by #N» в
  search/list (--json: superseded_by) — бейдж = скалярный подзапрос MIN(from_id),
  НЕ LEFT JOIN: второй `--supersedes N` не размножает строку (пин
  test_second_supersedes_does_not_fan_out_rows); `_check_ids` валидация
  --related/--supersedes (rc 2 вместо silent orphan). cmd_show печатает file:symbol.
- **P14** `_norm_tags` (comma→space, lowercase, collapse) на add/edit + разовый свип
  prod: 40 comma-строк → 0; `_norm_topic` dedup-key (lower(trim), SQL-нормализация
  stored) + «edit id=N instead»; topic-style warn (date/>60char); auto-promote первого
  **URL** из text в пустой source (только URL-форма: dotted-token ветка промоутила
  прозу и глушила provenance-hint; rstrip хвостовой пунктуации);
  `idx_findings_topic` в SCHEMA.
  Comma-canary ПЕРЕПИСАН в after-state (видимы оба фильтра).
- **P15** cmd_verify: shell=True через `_compat.run(shell=…)` (shlex.split убран, D-F);
  quote-balance reject на add (rc 2); edit-whitelist + verify_cmd/file/symbol.
  `_compat.run` расширен параметром shell.
- **Deployed-parity (blocker-advisory)**: `scripts/` copy2-deployed, НЕ junction —
  kit-only правка `_compat.run` оставила prod на TypeError. Фикс: install.py re-sync +
  tests/test_findings_lifecycle.py::DeployedParityTest (byte-identity sha256
  scripts/_compat.py+memory-warmup.py И deployed verify shell-line). Доктор-пин
  engine-sync поймал ВТОРОЙ дубль _compat (db-tools/ vs scripts/) — синхронизирован.
- **Marker-guard (blocker-advisory)**: core-бэкап не несёт root-маркеры, search_all
  валидирует MEMORY_ROOT на импорте → drill probe падал traceback'ом на здоровом
  restore. Probe SKIP без маркеров (`skipped: true` в JSON, main() трактует как ok);
  findings-половина drill покрывает research.db независимо. Регресс-тест + prod-drill
  на НОВОМ core-бэкапе 20260903T013128: rc 0, probe skipped, findings ok (token → hits).
- **Doc-sweep**: eval/scenarios/memory-routing.md mock обновлён под union-формат
  (trap-деталь «Thursday» осталась ТОЛЬКО в разговоре); search.py hint больше не шлёт
  в «research.db — findings.py search» (union покрывает); AGENTS.md/OPS.md/README/
  SKILL-доки учат search_all — маршрут теперь корректен, правок не требуют.
- Эквивалентность/cli-тесты обновлены под highlight-форму human-строки (P9).

**Advisory-раунд 2026-09-03 (после закрытия P1–P15) — всё закрыто кодом+пинами:**
- **superseded_by**: LEFT JOIN → скалярный подзапрос MIN(from_id) в SELECT-списках
  cmd_search/cmd_list (дубли строк и рассинхрон found/showing при 2+ supersedes).
- **auto-promote**: только URL-форма + rstrip(".,;:)"); dotted-token ветка удалена
  (промоутила прозу «Sec. A» и глушила provenance-hint).
- **pull-хинт**: шаблон `"<your topic>"` вместо литерала "memory".
- **log.py**: executescript(SCHEMA) только при отсутствии search_log (search пишет
  ОДИН INSERT-телеметрию за вызов; D-K сформулирован честно: list/show/stats —
  lock-free reads, search пишет телеметрию).
- **findings_db.connect()**: presence-check включает ТРИГГЕРЫ ai/ad/au — упавший
  findings_au раньше лечился каждым connect(), tables-only guard терял это
  (silent drift на UPDATE); пин test_connect_restores_dropped_sync_trigger.
- **restore() safety-контракт**: (a) pre-snapshot: CORRUPT-скип деградирует в
  `pre_restore_skipped`, LOCKED-скип = abort + rmtree полого снапшота (снапшот без
  store не safety-копия); (b) replace-ветка: `_is_corruption` (malformed/not a
  database/disk image) — busy НЕ corrupt, abort с живым файлом; sidecars удаляются
  ПОСЛЕ успешной замены (до — потеря committed-не-чекпоинтнутых строк на busy-пути);
  (c) `_backup_db`: preflight-проба statement'ом (timeout=5s) — backup API игнорирует
  busy timeout и CPython крутит BUSY вечно; пин mock-ом + реальный held-EXCLUSIVE-тест
  (~5с, детерминирован).
- **--restore non-tty**: rc 2 «refused: pass --yes» вместо EOFError.
- **marker-тест**: seed теперь несёт настоящий search_all.py → probe exists=True,
  skipped=True, без returncode (контракт «инструмент есть, маркеров нет → skip»).
- **drill-покрытие честно**: core-бэкапы не несут маркеров → search_all-probe на них
  всегда skipped; сертификация search_all = drill на FULL-бэкапе 20260902T085826
  (rc 0, probe returncode 0) + findings-половина на core.
- Верификация раунда: 636 passed, 1 skipped, 73 subtests; manifest 126; doctor 14
  GREEN; install.py sync (no-op для backup_memory: deployed-копии у него нет);
  prod: warmup-шаблон, search_all workflowz, core-drill rc 0, full-drill rc 0,
  --list без DEGRADED-тегов на здоровых бэкапах.
- **Degraded-бэкапы не restore-point (blocker-advisory)**: backup() со non-empty
  skipped пишет `.degraded` (содержимое = skipped-строки) ВМЕСТО `.complete` и не
  шлёт offsite; `_prune_completed` чистит degraded ОТДЕЛЬНЫМ проходом со своим
  cap=3 (DR-улики), не трогая бюджет хороших бэкапов (keep=10); `--list` тегирует
  «DEGRADED»; restore() отказывает (RuntimeError → main rc 3) без явного
  `--include-degraded`; restore_drill на degraded fail-fast (integrity_ok False +
  `degraded`-поле) — раньше findings-probe сертифицировал НЕТОНУТУЮ live-БД и drill
  был зелёным над ничем; override печатает «[!] store is NOT restored». Пин:
  held-EXCLUSIVE → backup → нет .complete / offsite None / restore RuntimeError /
  main rc 3 / drill fail / override без db в restored.
