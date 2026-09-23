"""Versioned SQLite assessments; application-owned schema and transactional writes."""
from contextlib import contextmanager, closing
import json
import os
from pathlib import Path
import sqlite3
import uuid
from functools import wraps

from .contracts import PolicyError, canonical, validate_run
from .documents import local_file
from .service import review_event, now

APPLICATION_ID = 1463894851
SCHEMA = {
    "metadata": "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "runs": "CREATE TABLE runs (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL)",
    "events": "CREATE TABLE events (sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL)",
    "exports": "CREATE TABLE exports (sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL)",
}
MAX_FILE = 128 * 1024 * 1024


def write_guard(action):
    @wraps(action)
    def guarded(*args, **kwargs):
        try:
            return action(*args, **kwargs)
        except (OSError, sqlite3.Error):
            raise PolicyError('Assessment write failed or is locked. Check permissions, free space and other writers; the previous committed run is preserved.', 6)
    return guarded


def connect(path, read_only=False):
    path = local_file(path)
    if path.exists() and path.stat().st_size > MAX_FILE:
        raise PolicyError("Assessment exceeds the 128 MiB limit.")
    if path.exists():
        with path.open('rb') as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                raise PolicyError("This is not a SQLite .wacc assessment.")
    uri = path.as_uri() + ("?mode=ro" if read_only else "?mode=rw")
    connection = sqlite3.connect(uri, uri=True, timeout=0.5)
    connection.enable_load_extension(False)
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_FILE)
    connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 10000)
    try:
        if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID or connection.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise PolicyError("Unsupported assessment schema. Keep the original and use its originating version.")
        objects = connection.execute("SELECT type,name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if {name: sql for kind, name, sql in objects if kind == "table"} != SCHEMA or any(kind != "table" for kind, _, _ in objects):
            raise PolicyError("Assessment contains unexpected tables, views, indexes or triggers.")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise PolicyError("Assessment database integrity check failed.")
        return connection
    except Exception:
        connection.close()
        raise


@contextmanager
def locked(path):
    path = local_file(path)
    lock = path.with_name(path.name + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise PolicyError("Assessment is in use. If the writer crashed, confirm it has stopped before removing its .lock file.", 6)
    except OSError:
        raise PolicyError("Cannot write to the selected assessment folder.", 6)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def load(path, run_id=None):
    try:
        with closing(connect(path, True)) as db, db:
            meta = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM metadata")}
            history = [dict(id=i, createdAt=t) for i, t in db.execute("SELECT id,created FROM runs ORDER BY rowid")]
            selected = run_id or meta["currentRun"]
            record = db.execute("SELECT payload FROM runs WHERE id=?", (selected,)).fetchone()
            if not record:
                raise PolicyError("Requested run is not present in this assessment.")
            run = json.loads(record[0])
            validate_run(run)
            meta['historical'] = selected != meta['currentRun']
            meta['selectedFinalised'] = selected in meta.get('finalisedRuns',[]) or (not meta['historical'] and meta['finalised'])
            events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY sequence")]
            for event in events:
                if event["runId"] == selected:
                    checked = review_event(run, event["requirementId"], event["finding"], event["reason"], event["reviewer"],
                                 event["confirmedObligations"], event["selectedEvidence"], event.get("comment", ""), event.get('manualEvidence', []))
                    if checked['manualEvidence'] != event.get('manualEvidence',[]):
                        raise PolicyError('Reviewer-linked evidence does not match the saved source passage.')
            return dict(run=run, events=events, history=history, metadata=meta)
    except PolicyError:
        raise
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, RecursionError):
        raise PolicyError("Assessment could not be read or failed contract validation.")
    finally:
        if "db" in locals():
            db.close()


@write_guard
def save(path, run):
    validate_run(run)
    path = local_file(path)
    if path.suffix.lower() != ".wacc":
        raise PolicyError("Assessment filenames must end in .wacc.", 6)
    with locked(path):
        if path.exists():
            previous = load(path)
            if any(h["id"] == run["runId"] for h in previous["history"]):
                return
            with closing(connect(path)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO runs VALUES (?,?,?)", (run["runId"], run["createdAt"], canonical(run)))
                db.execute("UPDATE metadata SET value=? WHERE key='currentRun'", (canonical(run["runId"]),))
                db.execute("UPDATE metadata SET value='false' WHERE key='finalised'")
            db.close()
        else:
            stage = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                with closing(sqlite3.connect(stage)) as db, db:
                    db.execute("PRAGMA application_id=%d" % APPLICATION_ID)
                    db.execute("PRAGMA user_version=1")
                    for sql in SCHEMA.values():
                        db.execute(sql)
                    db.executemany("INSERT INTO metadata VALUES (?,?)", [("currentRun", canonical(run["runId"])), ("finalised", "false"), ("createdAt", canonical(now()))])
                    db.execute("INSERT INTO runs VALUES (?,?,?)", (run["runId"], run["createdAt"], canonical(run)))
                db.close()
                load(stage)
                os.replace(stage, path)
            finally:
                if stage.exists():
                    stage.unlink()


@write_guard
def append_review(path, event):
    with locked(path):
        state = load(path)
        if state["metadata"]["finalised"] or event["runId"] != state["run"]["runId"]:
            raise PolicyError("This run is finalised or no longer current. Create a new revision to review it.", 6)
        review_event(state["run"], event["requirementId"], event["finding"], event["reason"], event["reviewer"],
                     event["confirmedObligations"], event["selectedEvidence"], event.get("comment", ""), event.get('manualEvidence', []))
        with closing(connect(path)) as db, db:
            db.execute("INSERT INTO events(payload) VALUES (?)", (canonical(event),))
        db.close()


@write_guard
def finalise(path, run_id=None):
    with locked(path):
        state=load(path)
        if run_id and run_id != state['run']['runId']:
            raise PolicyError('Historical runs are read-only. Finalise the current run or export this snapshot.',6)
        finalised=set(state['metadata'].get('finalisedRuns',[])) | {state['run']['runId']}
        with closing(connect(path)) as db, db:
            db.execute("UPDATE metadata SET value='true' WHERE key='finalised'")
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('finalisedRuns',?)",(canonical(sorted(finalised)),))
        db.close()


@write_guard
def snapshot(source, target, force=False):
    source, target = local_file(source), local_file(target)
    if source == target:
        raise PolicyError("Choose a different snapshot path.", 6)
    load(source)
    with locked(target):
        if target.exists() and not force:
            raise PolicyError("Output already exists; use --force to replace it.", 6)
        stage = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            original = connect(source, True)
            copy = sqlite3.connect(stage)
            try:
                original.backup(copy)
            finally:
                original.close()
                copy.close()
            load(stage)
            if target.exists():
                backup = target.with_name(target.name + ".backup-" + uuid.uuid4().hex)
                # The target is a saved snapshot, not an active database.
                prior = connect(target, True)
                backup_db = sqlite3.connect(backup)
                try:
                    prior.backup(backup_db)
                finally:
                    prior.close()
                    backup_db.close()
            os.replace(stage, target)
        finally:
            if stage.exists():
                stage.unlink()


def verify_sources(state):
    import hashlib
    output = []
    for doc in state["run"]["documents"]:
        try:
            path = local_file(doc["path"])
            matches = path.stat().st_size <= documents_limit() and hashlib.sha256(path.read_bytes()).hexdigest() == doc["sha256"]
            status = "Unchanged" if matches else "Changed — source location is stale"
        except (OSError, PolicyError):
            status = "Unavailable"
        output.append(dict(documentId=doc["id"], status=status))
    return output


def documents_limit():
    from .documents import MAX_BYTES
    return MAX_BYTES
