"""Command line: build the report from a price store and write it the way GitHub Pages will serve it.

    dsereport build --db ~/.dse_pnf/prices.sqlite3 --out out/            # reads a copy of the store
    dsereport build --inputs tests/fixtures/inputs_2026-11-17.json --out out/ --no-papers
    dsereport inputs --db ~/.dse_pnf/prices.sqlite3 --out inputs.json
    dsereport refresh --db prices.sqlite3          # fetch new sessions and news in place (the cloud job's store)
    dsereport build --db prices.sqlite3 --out site --if-newer   # skip when the site already has this session
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile

from . import build, schema

KEEP_REPORTS = 60


def _copy_store(src: str, workdir: str) -> str:
    """The engine may write to its store; work on a consistent copy (sqlite backup), never the live file."""
    dst = os.path.join(workdir, "prices.sqlite3")
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as a, sqlite3.connect(dst) as b:
        a.backup(b)
    return dst


def _inputs(args) -> dict:
    if args.inputs:
        with open(args.inputs, encoding="utf-8") as f:
            return json.load(f)
    from . import source   # the engine is only needed when reading a store
    work = tempfile.mkdtemp(prefix="dsereport-")
    try:
        return source.collect(_copy_store(os.path.expanduser(args.db), work))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _write(report: dict, out: str) -> str:
    v1 = os.path.join(out, "v1")
    os.makedirs(v1, exist_ok=True)
    body = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    for name in ("latest.json", f"{report['asOf']}.json"):
        with open(os.path.join(v1, name), "w", encoding="utf-8") as f:
            f.write(body)
    index_path = os.path.join(v1, "index.json")
    try:
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, ValueError):
        index = []
    index = sorted({*index, report["asOf"]}, reverse=True)[:KEEP_REPORTS]
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f)
    _prune(v1, set(index))
    return os.path.join(v1, "latest.json")


def _prune(v1: str, keep: set) -> None:
    """Dated reports drop out of the site when they drop out of the index."""
    for name in os.listdir(v1):
        stem, ext = os.path.splitext(name)
        if ext == ".json" and len(stem) == 10 and stem[4] == "-" and stem not in keep:
            os.remove(os.path.join(v1, name))


def _published_asof(out: str):
    try:
        with open(os.path.join(out, "v1", "latest.json"), encoding="utf-8") as f:
            return json.load(f).get("asOf")
    except (OSError, ValueError, AttributeError):
        return None


def cmd_build(args) -> int:
    I = _inputs(args)
    published = _published_asof(args.out) if args.if_newer else None
    if published and str(I.get("asof")) <= published:
        print(f"No new session: the site already has {published}; nothing written")
        return 0
    feed = None
    if not args.no_papers:
        from . import papers
        feed = papers.fetch()
    report = build.build_report(I, feed)
    errors = schema.validate(report)
    if errors:
        print("Report not written; it failed validation:", *errors[:20], sep="\n  ", file=sys.stderr)
        return 1
    path = _write(report, args.out)
    print(f"Wrote {path} for {report['asOf']} ({os.path.getsize(path) // 1024} KB)")
    return 0


def cmd_inputs(args) -> int:
    I = _inputs(args)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(I, f, default=str, separators=(",", ":"))
    print(f"Wrote {args.out}")
    return 0


def cmd_refresh(args) -> int:
    from . import refresh   # needs the engine and the network
    r = refresh.refresh(os.path.expanduser(args.db))
    print(f"Refresh {'done' if r['ok'] else 'FAILED'}: {r['before']} -> {r['after']}; {r['detail']}")
    return 0 if r["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dsereport")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the report JSON")
    src = b.add_mutually_exclusive_group(required=True)
    src.add_argument("--db", help="the engine's price store (read through a copy)")
    src.add_argument("--inputs", help="a saved inputs JSON instead of a store")
    b.add_argument("--out", default="out", help="folder that becomes the Pages site (writes v1/...)")
    b.add_argument("--no-papers", action="store_true", help="leave newspaper headlines out (no network)")
    b.add_argument("--if-newer", action="store_true", help="write only when the session is newer than the site's")
    b.set_defaults(func=cmd_build)
    i = sub.add_parser("inputs", help="save the engine inputs as JSON (for tests)")
    i.add_argument("--db", required=True)
    i.add_argument("--out", required=True)
    i.set_defaults(func=cmd_inputs, inputs=None)
    r = sub.add_parser("refresh", help="update a price store in place with the engine's refresh job")
    r.add_argument("--db", required=True)
    r.set_defaults(func=cmd_refresh)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
