#!/usr/bin/env python3

"""
Parse archived MyBoerse release threads and optionally submit Filecrypt links to pyLoad.

It recursively parses `*.html` files,
extracts the first bold/strong release title from `.message-body .bbWrapper`,
falls back to the `<title>` prefix before `| MyBoerse.bz`,
extracts all Filecrypt Container links,
and parses release metadata with GuessIt.
Add custom rules in `filter_releases(releases, args)`.

Each release becomes one pyLoad package named after the parsed title.
Successfully accepted submissions are appended to JSONL history;
matching releases are skipped on later runs.
Failed submissions are not logged and will be retried.
The history confirms pyLoad accepted the handler request, not that the downloads completed.
Review candidates with `--dry-run` before submitting.
"""

from __future__ import annotations
import argparse, hashlib, json, logging, re, sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from guessit import guessit

LOG = logging.getLogger("myboerse_release_importer")
FILECRYPT_HOSTS = {"filecrypt.cc", "www.filecrypt.cc"}

@dataclass
class Release:
    source_file: str
    title: str
    title_source: str
    filecrypt_links: list[str]
    guessit: dict[str, Any] = field(default_factory=dict)
    @property
    def key(self) -> str:
        title = re.sub(r"\s+", " ", self.title).strip().casefold()
        material = title + "\n" + "\n".join(sorted(set(self.filecrypt_links)))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
    @property
    def package_name(self) -> str:
        return self.title.strip()

def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n|")

def is_filecrypt_container(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in {"http", "https"} and (p.hostname or "").lower() in FILECRYPT_HOSTS and "/container/" in p.path.lower()

def extract_release_title(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    for article in soup.select("article.message-body.js-selectToQuote, article.message-body"):
        wrapper = article.select_one(".bbWrapper")
        if not wrapper: continue
        for node in wrapper.select("b, strong"):
            # print(f"extract_release_title: node.get_text: " + repr(node.get_text(" ", strip=True)))
            candidate = clean_title(node.get_text(" ", strip=True))
            if candidate and len(candidate) >= 3 and not re.search(r"^(?:download|screenshots?|nfo|mediainfo|passwort|password)\\s*:?$", candidate, re.I):
                return candidate, "message-bold"
    title_tag = soup.find("title")
    if title_tag:
        full = clean_title(title_tag.get_text(" ", strip=True))
        candidate = clean_title(re.split(r"\s*\|\s*MyBoerse\.bz\b", full, maxsplit=1, flags=re.I)[0])
        if candidate: return candidate, "page-title"
    return None, None

def extract_filecrypt_links(soup: BeautifulSoup) -> list[str]:
    links = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if is_filecrypt_container(href) and href not in links: links.append(href)
    return links

def parse_html_file(path: Path) -> Release | None:
    try: html = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        LOG.exception("Cannot read %s", path); return None
    soup = BeautifulSoup(html, "html.parser")
    title, source = extract_release_title(soup)
    # print(f"parse_html_file: title={title!r}, source={source!r}")
    links = extract_filecrypt_links(soup)
    if not title:
        LOG.warning("No release title found in %s", path); return None
    if not links:
        LOG.debug("No Filecrypt container link in %s", path); return None
    try: parsed = guessit(title); guessit_data = {str(k): str(v) for k, v in parsed.items()}
    except Exception:
        LOG.exception("GuessIt failed for %r", title); guessit_data = {}
    # print(f"parse_html_file: title={title!r}")
    return Release(str(path), title, source or "unknown", links, guessit_data)

def parse_archive(root: Path) -> list[Release]:
    releases = []
    for path in sorted(root.rglob("*.html")):
        release = parse_html_file(path)
        if release: releases.append(release)
    return releases

def load_history(path: Path) -> dict[str, dict[str, Any]]:
    history = {}
    if not path.exists(): return history
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip(): continue
            try:
                item = json.loads(line)
                if item.get("key"): history[item["key"]] = item
            except json.JSONDecodeError: LOG.warning("Ignoring malformed history line %d", n)
    return history

def append_history(path: Path, release: Release, response: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"key": release.key, "title": release.title, "source_file": release.source_file,
              "filecrypt_links": release.filecrypt_links, "pyload_response": response,
              "added_at": datetime.now(timezone.utc).isoformat()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

def submit_links_to_pyload(links: Sequence[str], package: str, *, base_url: str = "http://localhost:9666",
                           passwords: str | None = None, timeout: float = 15) -> str:
    clean_links = [x.strip() for x in links if x and x.strip()]
    if not clean_links: raise ValueError("links must contain at least one URL")
    data = {"urls": "\n".join(clean_links), "package": package.strip()}
    if passwords: data["passwords"] = passwords
    response = requests.post(base_url.rstrip("/") + "/flash/add", data=data, timeout=timeout)
    response.raise_for_status()
    body = response.text.strip()
    if body.startswith("failed"): raise RuntimeError(f"pyLoad rejected the links: {body}")
    return body

def filter_releases(releases: list[Release], args) -> list[Release]:
    """Customization point: add user-specific filters here."""
    selected = releases
    if args.resolution:
        wanted = args.resolution.casefold()
        selected = [r for r in selected if str(r.guessit.get("screen_size", "")).casefold() == wanted or wanted in r.title.casefold()]
    return selected

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", default="archive", help="Directory containing archived thread HTML")
    p.add_argument("--history", default="pyload_added.jsonl", help="JSONL history of successful submissions")
    p.add_argument("--pyload-url", default="http://localhost:9666")
    p.add_argument("--resolution", help="Optional filter, e.g. 720p")
    p.add_argument("--dry-run", action="store_true", help="List candidates without submitting")
    p.add_argument("--passwords", help="Optional archive password string passed to pyLoad")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--json-out", help="Write parsed release inventory as JSON")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    archive = Path(args.archive).expanduser()
    if not archive.is_dir(): p.error(f"archive directory does not exist: {archive}")
    # Stage 1: parse the entire archive.
    releases = parse_archive(archive)
    LOG.info("Parsed %d releases.", len(releases))
    if args.json_out:
        out = Path(args.json_out).expanduser(); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([asdict(r) | {"key": r.key, "package_name": r.package_name} for r in releases], ensure_ascii=False, indent=2), encoding="utf-8")
        LOG.info("Wrote inventory to %s", out)
    # Stage 2: apply customizable filters.
    selected = filter_releases(releases, args)
    LOG.info("%d releases remain after filtering.", len(selected))
    # Stage 3: omit prior successful submissions.
    history_path = Path(args.history).expanduser()
    history = load_history(history_path)
    pending = [r for r in selected if r.key not in history]
    LOG.info("%d releases not in submission history.", len(pending))
    for r in pending: LOG.info("Candidate: %s | GuessIt=%s | links=%s", r.title, r.guessit, ", ".join(r.filecrypt_links))
    if args.dry_run:
        LOG.info("Dry run: nothing submitted."); return 0
    # Stage 4: one pyLoad package per release, log after handler accepts it.
    for r in pending:
        try:
            response = submit_links_to_pyload(r.filecrypt_links, r.package_name, base_url=args.pyload_url,
                                               passwords=args.passwords, timeout=args.timeout)
        except Exception:
            LOG.exception("Failed to submit %r; it will be retried next run.", r.title); continue
        append_history(history_path, r, response)
        LOG.info("Added to pyLoad: %s", r.title)
    return 0

if __name__ == "__main__":
    sys.exit(main())
