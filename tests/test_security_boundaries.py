"""Saved-source launch and CSV regressions using inert, synthetic fixtures."""
from contextlib import closing
import csv
import hashlib
import http.client
import io
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import PropertyMock, patch
from urllib.parse import urlencode
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_policy_review import temporary
from wacc.analysis import analyse
from wacc.model import Corpus
from wacc.policy import SCHEMA_VERSION, store
from wacc.policy.contracts import PolicyError, canonical, canonical_payload, fingerprint, validate_run
from wacc.policy.desktop import Desktop
from wacc.render import export
from wacc.serve import State, _handler, bind_server


def source(path, **changes):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(id=digest, sha256=digest, name=path.name, path=str(path),
                format=path.suffix.lower(), passages=[], **changes)


def run_for(doc):
    run = dict(schemaVersion=SCHEMA_VERSION, runId='synthetic', createdAt='2026-09-25',
               versions={}, scope={}, documents=[doc], requirements=[], mappings=[])
    run['canonicalHash'] = fingerprint(canonical_payload(run))
    return run


class SourceOpeningTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(temporary())

    def file(self, name, data=b'Inert source fixture'):
        path = self.root / name
        path.write_bytes(data)
        return path

    def open_document(self, doc):
        errors = []
        def guarded(action):
            try:
                return action()
            except PolicyError as error:
                errors.append(str(error))
        app = SimpleNamespace(state={'run': run_for(doc)},
                              doc_tree=SimpleNamespace(selection=lambda: [doc['id']]), guarded=guarded)
        with patch('wacc.policy.desktop.os.startfile', create=True) as launch, \
                patch('wacc.policy.desktop.messagebox.showerror'):
            Desktop.open_original(app)
        return launch

    def test_executables_and_disguised_names_never_launch(self):
        for name in ('payload.cmd', 'payload.bat', 'payload.exe', 'policy.txt.lnk', 'policy.pdf.exe', 'policy.url'):
            with self.subTest(name=name):
                doc = source(self.file(name))
                doc.update(format='.txt', name='Policy.txt')
                self.open_document(doc).assert_not_called()

    def test_forged_saved_comparison_rejected_despite_matching_hashes(self):
        saved = self.root / 'comparison.wacc'
        run = run_for(source(self.file('policy.txt')))
        store.save(saved, run)
        forged = run_for(source(self.file('payload.cmd')))
        forged['documents'][0].update(format='.txt', name='Policy.txt')
        forged['canonicalHash'] = fingerprint(canonical_payload(forged))
        with closing(sqlite3.connect(saved)) as db, db:
            db.execute('UPDATE runs SET payload=?', (canonical(forged),))
        with self.assertRaises(PolicyError):
            store.load(saved)

    def test_ambiguous_windows_paths_and_metadata_are_rejected(self):
        doc = source(self.file('policy.txt'))
        for path in ('C:/files/program.exe:policy.txt', 'C:/files/policy.txt.',
                     'C:/files/policy.txt ', '//server/share/policy.txt',
                     '//?/C:/files/policy.txt', 'C:/files/policy.txt\x00.exe'):
            with self.subTest(path=path):
                forged = dict(doc, path=path)
                with self.assertRaises(PolicyError):
                    validate_run(run_for(forged))
        with self.assertRaises(PolicyError):
            validate_run(run_for(dict(doc, format='.pdf')))
        with self.assertRaises(PolicyError):
            validate_run(run_for(dict(doc, archiveHash=doc['sha256'])))

    def test_supported_originals_and_failed_extractions_still_open(self):
        for name in ('policy.txt', 'policy.md', 'policy.PDF', 'policy.docx'):
            with self.subTest(name=name):
                path = self.file(name)
                doc = source(path, status='Failed', included=False)
                validate_run(run_for(doc))
                self.open_document(doc).assert_called_once_with(str(path.absolute()))

    def test_zip_opens_verified_outer_archive_only(self):
        path = self.root / 'policies.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('folder/policy.md', 'Inert source fixture')
        doc = source(path)
        doc.update(format='.md', archiveMember='folder/policy.md', archiveHash=doc['sha256'],
                   sha256=hashlib.sha256(b'Inert source fixture').hexdigest())
        validate_run(run_for(doc))
        self.open_document(doc).assert_called_once_with(str(path.absolute()))
        doc['archiveMember'] = 'folder/program.cmd'
        self.open_document(doc).assert_not_called()

    def test_changed_missing_and_directory_sources_never_launch(self):
        path = self.file('policy.txt')
        doc = source(path)
        path.write_bytes(b'Changed fixture')
        self.assertIn('Changed', store.verify_sources({'run': run_for(doc)})[0]['status'])
        self.open_document(doc).assert_not_called()
        path.unlink()
        self.open_document(doc).assert_not_called()
        path.mkdir()
        self.open_document(doc).assert_not_called()

    def test_linked_sources_never_launch(self):
        doc = source(self.file('policy.txt'))
        with patch.object(Path, 'is_symlink', return_value=True):
            self.open_document(doc).assert_not_called()

    def test_relative_source_launches_the_checked_absolute_path(self):
        path = self.file('policy.txt')
        doc = source(path)
        doc['path'] = str(path.relative_to(ROOT))
        self.open_document(doc).assert_called_once_with(str(path.absolute()))

    def test_saved_comparison_still_loads_when_original_is_unavailable(self):
        path = self.file('policy.txt')
        saved = self.root / 'comparison.wacc'
        store.save(saved, run_for(source(path)))
        path.unlink()
        state = store.load(saved)
        self.assertEqual(state['run']['runId'], 'synthetic')
        self.assertEqual(store.verify_sources(state)[0]['status'], 'Unavailable')
        self.open_document(state['run']['documents'][0]).assert_not_called()


class CsvSafetyTests(unittest.TestCase):
    FORMULAS = ('=1+1', '+SUM(1,1)', '-1+1', '@SUM(1,1)', '  =1+1', '\t=1+1', '\r=1+1', '\n=1+1')

    def test_search_subject_and_other_dynamic_cells_are_literal(self):
        for value in self.FORMULAS:
            with self.subTest(value=value):
                corpus = Corpus()
                result = analyse(corpus, value, [])
                result.lookup_note = value
                with patch.object(type(result), 'attributions', new_callable=PropertyMock, return_value=[(value, value)]):
                    rows = list(csv.reader(io.StringIO(export.to_csv(corpus, result), newline='')))
                self.assertEqual(rows[0], ['subject', "'" + value])
                self.assertEqual(rows[1], ['identifier status', "'" + value])
                self.assertIn(["'" + value, "'" + value], rows)

    def test_plain_text_quotes_commas_and_multiline_values_round_trip(self):
        for value in ('Privileged access', 'He said "review", then approved', 'First line\nSecond line',
                      'Plain text\r=1+1', 'Plain text\n=1+1', ''):
            result = analyse(Corpus(), value, [])
            self.assertEqual(next(csv.reader(io.StringIO(export.to_csv(Corpus(), result), newline=''))),
                             ['subject', value])

    def test_http_export_does_not_preserve_formula_syntax(self):
        with patch('wacc.serve.build', return_value=(Corpus(), None)):
            state = State()
        server = bind_server('127.0.0.1', 0, _handler(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            try:
                client.request('GET', '/export.csv?' + urlencode({'q': '=1+1'}))
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(next(csv.reader(io.StringIO(response.read().decode('utf-8')))),
                                 ['subject', "'=1+1"])
            finally:
                client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
