"""Headless policy analysis contract; only 'open' imports the desktop."""
import argparse
import json
import sys

from . import ENGINE_VERSION
from .contracts import PolicyError, envelope
from . import corpus, service, store, reports

COMMANDS = {"frameworks", "analyse", "open", "requirements", "evidence", "gaps", "mappings", "report", "validate", "corpus", "review", "finalise", "snapshot", "--version"}


def parser():
    root = argparse.ArgumentParser(prog="wacc", description="Offline policy coverage and evidence review (pilot)")
    root.add_argument("--version", action="version", version="WACC " + ENGINE_VERSION)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("frameworks", "analyse", "requirements", "evidence", "gaps", "mappings", "validate", "review", "finalise", "snapshot", "corpus"):
        p = commands.add_parser(name)
        p.add_argument("--format", choices=("json", "text"), default="text")
        p.add_argument("--output", default="-")
        p.add_argument("--force", action="store_true")
        if name in ("requirements", "evidence", "gaps", "mappings", "validate", "review", "finalise", "snapshot"):
            p.add_argument("assessment")
            p.add_argument("--run")
        if name in ("requirements", "evidence", "gaps"):
            p.add_argument("--requirement")
            p.add_argument("--status")
        if name == "mappings":
            p.add_argument("--target-framework")
            p.add_argument("--requirement")
        if name == "analyse":
            p.add_argument("inputs", nargs="+")
            p.add_argument("--framework", default="wa-csp")
            p.add_argument("--framework-version")
            p.add_argument("--corpus-version")
            p.add_argument("--also-assess", action="append", default=[])
            p.add_argument("--recurse", action="store_true")
            p.add_argument("--assessment")
            p.add_argument("--name", default="Policy assessment")
            p.add_argument("--organisation", default="")
            p.add_argument("--scope", required=True, help="Describe exactly which documents this assessment covers")
            p.add_argument("--document-status", choices=("approved", "draft", "unknown", "superseded"), default="unknown")
            p.add_argument("--retention", choices=("evidence", "extracted"), default="evidence")
        if name == "review":
            p.add_argument("--requirement", required=True)
            p.add_argument("--finding", required=True)
            p.add_argument("--reason", required=True)
            p.add_argument("--reviewer", required=True)
            p.add_argument("--confirm", action="append", default=[])
            p.add_argument("--evidence", action="append", default=[])
            p.add_argument('--link', action='append', default=[], metavar='DOCUMENT_ID|PASSAGE_ID|OBLIGATION_ID')
        if name == "snapshot":
            p.add_argument("destination")
        if name == "corpus":
            p.add_argument("action", choices=("list", "verify", "install", "update"))
            p.add_argument("package", nargs="?")
            p.add_argument('--framework', dest='update_frameworks', action='append', choices=('wa-csp','ism','aescsf'))
            p.add_argument('--import-file', help='Import one downloaded publisher file for the selected framework.')
    p = commands.add_parser("report")
    p.add_argument("assessment")
    p.add_argument("--run")
    p.add_argument("--format", choices=("json", "csv", "markdown", "html"), default="html")
    p.add_argument("--output", required=True)
    p.add_argument("--summary-only", action="store_true")
    p.add_argument('--framework', action='append', dest='report_frameworks', help='Include only this assessed framework; repeat to select more than one.')
    p.add_argument("--force", action="store_true")
    p = commands.add_parser("open")
    p.add_argument("assessment", nargs="?")
    return root


def execute(args):
    operation = args.command
    if operation == "open":
        from .desktop import launch
        launch(args.assessment)
        return None, 0
    if operation == "frameworks" or operation == "corpus" and args.action == "list":
        return envelope(operation, **corpus.installed()), 0
    if operation == "corpus":
        if args.action == 'update':
            from .updates import update
            results = update(args.update_frameworks, args.import_file)
            result = envelope(operation, updates=results)
            failed = any(r['status'] == 'Failed' for r in results)
            if failed:
                result['status'] = 'CompletedWithLimitations'
                result['warnings'] = [r['framework'] + ': ' + r['message'] for r in results if r['status'] == 'Failed']
            return result, 7 if failed else 0
        from .packages import verify, install
        if not args.package:
            raise PolicyError("Specify a corpus package.", 2)
        result = install(args.package) if args.action == "install" else verify(args.package)
        return envelope(operation, package=result), 0
    if operation == "analyse":
        run = service.analyse(args.inputs, args.name, args.scope, args.organisation, args.framework,
                              args.framework_version, args.corpus_version, args.also_assess, args.recurse,
                              args.document_status, args.retention)
        if args.assessment:
            store.save(args.assessment, run)
        result = envelope(operation, assessmentPath=args.assessment, analysisRunId=run["runId"], scope=run["scope"],
                          versions=run["versions"], summary=service.summary(run), frameworkSummaries=service.framework_summaries(run), requirements=run["requirements"],
                          documents=run["documents"])
        result.update(status="CompletedWithLimitations", warnings=run["limitations"])
        return result, 7
    state = store.load(args.assessment, args.run)
    run = state["run"]
    if operation == "report":
        content = reports.render(state, args.format, not args.summary_only, args.report_frameworks)
        if args.output == "-":
            sys.stdout.write(content + "\n")
        else:
            reports.export_report(state,args.output,args.format,not args.summary_only,args.force,args.assessment,args.report_frameworks)
        return None, 0
    if operation == "review":
        links = []
        for value in args.link:
            parts = value.split('|')
            if len(parts) != 3:
                raise PolicyError('Manual link needs document ID, passage ID and obligation ID separated by |.', 2)
            links.append(dict(zip(('documentId','passageId','obligationId'),parts)))
        event = service.review_event(run, args.requirement, args.finding, args.reason, args.reviewer, args.confirm, args.evidence, manual_evidence=links)
        store.append_review(args.assessment, event)
        return envelope(operation, event=event), 0
    if operation == "finalise":
        store.finalise(args.assessment,run['runId'])
        return envelope(operation, assessmentPath=args.assessment, finalised=True), 0
    if operation == "snapshot":
        store.snapshot(args.assessment, args.destination, args.force)
        return envelope(operation, assessmentPath=args.destination), 0
    if operation == "validate":
        return envelope(operation, valid=True, history=state["history"], sources=store.verify_sources(state)), 0
    if operation == "mappings":
        values = service.neighbourhood(run, args.requirement) if args.requirement else dict(edges=[m for m in run["mappings"] if not args.target_framework or m["target"].startswith(args.target_framework + ":")])
        return envelope(operation, **values), 0
    rows = service.apply_reviews(run, state["events"])
    rows = [r for r in rows if (not args.requirement or r["id"] == args.requirement) and (not args.status or r["automatedFinding"] == args.status)]
    if operation == "gaps":
        rows = [r for r in rows if r["missingObligations"] and r["applicability"] != "NotApplicable"]
    values = dict(evidence=[e for r in rows for e in r["evidence"]]) if operation == "evidence" else dict(requirements=rows)
    return envelope(operation, scope=run["scope"], versions=run["versions"], summary=service.summary(run, state["events"]),
                    frameworkSummaries=service.framework_summaries(run, state['events']), **values), 0


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    args = parser().parse_args(argv)
    try:
        result, code = execute(args)
    except KeyboardInterrupt:
        result, code = envelope(args.command), 130
        result.update(status="Cancelled", errors=["Operation cancelled; previous saved runs remain unchanged."])
    except PolicyError as error:
        result, code = envelope(args.command), error.code
        result.update(status="Failed", errors=[str(error)])
    except Exception:
        result, code = envelope(args.command), 4
        result.update(status="Failed", errors=["Operation failed. Previous saved work is unchanged. Check input format and workspace permissions."])
    if result is not None:
        for error in result["errors"]:
            print(error, file=sys.stderr)
        content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if getattr(args, "format", "text") == "text":
            content = result["status"] + "\n" + content
        if getattr(args, "output", "-") == "-":
            print(content)
        else:
            try:
                reports.write_output(args.output, content, args.force)
            except PolicyError as error:
                print(str(error), file=sys.stderr)
                return error.code
    return code


if __name__ == "__main__":
    sys.exit(main())
