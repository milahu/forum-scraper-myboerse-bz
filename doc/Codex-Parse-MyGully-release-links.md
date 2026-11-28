# Parse MyGully release links

> modify the python script myboerse_release_importer.py to make it work with forum threads scraped from mygully.com
>
> currently the script fails to parse the thread HTML files:
> ```
> 2026-11-28 17:18:59,440 INFO Parsed 0 releases.
> ```
>
> you can use the HTML files `archive/mygully.com/*.html`
>
> for example, the HTML file `archive/mygully.com/8740588.html` contains the rapidgator.net download link [`https://rapidgator.net/file/40dc4bf309f96f6c365e6a7638bce5e2`](https://rapidgator.net/file/40dc4bf309f96f6c365e6a7638bce5e2)
>
> for example, the HTML file `archive/mygully.com/7907598.html` contains the rapidgator.net download link [`https://rg.to/file/05b42fe92dd87dbe37359865b16c8df1/hrbr2980.rar.html`](https://rg.to/file/05b42fe92dd87dbe37359865b16c8df1/hrbr2980.rar.html)
>
> in the parsing stage, the script should try to extract all download links to rapidgator.net (or filecrypt.cc), and later i want to select which download links to add to pyload

<details><summary>4 previous messages</summary>

> I’ll inspect the importer and the two sample threads, then verify that the parser exposes their download links for selection before sending anything to pyLoad.
>
> <details><summary>Edited a file, explored a file, 3 searches, a list, ran 5 commands</summary>
>
> - Ran `git status --short && rg --files -g 'AGENTS.md' -g '*importer*' && rg -n '^(class|def) |rapidgator|filecrypt|pyload' myboerse_release_importer.py`
>
> - Ran `sed -n '45,420p;613,643p;807,1008p;1055,1165p' myboerse_release_importer.py
> rg -in -m 8 '40dc4bf|05b42fe|post_message|navbar|<title' archive/mygully.com/{8740588,7907598}.html | cut -c1-450
> ls -a`
>
> - Ran `rg -in '40dc4bf|05b42fe|id="post_message|id="navbar|class="navbar"' archive/mygully.com/{8740588,7907598}.html | cut -c1-350 | tail -45
> sed -n '1,45p;1005,1055p' myboerse_release_importer.py
> ls src; ls archive; python3 -c 'import bs4,guessit,lxml'`
>
> - Ran `rg -n 'forumdisplay.php\?f=|navbit' archive/mygully.com/8740588.html | cut -c1-250 | head -22; sed -n '1040,1055p' archive/mygully.com/8740588.html; rg -oih 'https?://([^/" <]+\.)?(rapidgator\.net|rg\.to|filecrypt\.cc)/[^" <]+' archive/mygully.com -m 2 | head -15; python3 myboerse_release_importer.py --help >/dev/null`
>
> <details><summary>Explored a file, 3 searches, a list</summary>
>
> - Searched for `AGENTS.md` in `..`
> - Searched for `https?://(?:www\.)?(?:rapidgator\.net|rg\.to|filecrypt\.cc)/[^" <]+` in `mygully.com`
> - Searched for `https?://(?:www\.)?filecrypt\.cc/[^" <]+` in `mygully.com`
> - Read `./myboerse_release_importer.py`
> - Listed files in `mygully.com`
>
> </details>
>
> - Wrote `./myboerse_release_importer.py` (+49 -11)
>
> - Wrote `./myboerse_release_importer.py` (+33 -16)
>
> - Ran `test_dir=$(mktemp -d) && python3 myboerse_release_importer.py --forum mygully.com --dry-run --cache-db "$test_dir/cache.sqlite3" --json-out "$test_dir/inventory.json" --select-link 'https://rapidgator.net/file/40dc4bf309f96f6c365e6a7638bce5e2' --select-link 'https://rg.to/file/05b42fe92dd87dbe37359865b16c8df1/hrbr2980.rar.html' 2>&1 | tail -35
> git diff --check`
>
> </details>
>
> The dry run found 99 releases across 100 archived pages and matched both example URLs. I’ll now verify that selected Rapidgator links reach the pyLoad submission function directly and selected Filecrypt containers still go through decryption.
>
> <details><summary>Ran 2 commands</summary>
>
> - Ran `PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
> from pathlib import Path
> from tempfile import TemporaryDirectory
> from types import SimpleNamespace
> from unittest.mock import patch
> from bs4 import BeautifulSoup
> import myboerse_release_importer as m
>
> direct = "https://rg.to/file/example/test.rar.html"
> container = "https://filecrypt.cc/Container/ABC.html"
> html = f'<div id="post_message_1"><a href="{direct}">short URL</a><pre>{direct}\n{container}</pre></div>'
> assert m.extract_download_links(BeautifulSoup(html, "lxml")) == ([direct], [container], {})
> with TemporaryDirectory() as tmp:
>     root = Path(tmp)
>     args = SimpleNamespace(cache_db=root / "cache.db", pyload_url="unused", passwords=None, timeout=60)
>     release = m.Release("thread.html", 1, "Example", "page-h1", [], direct_links=[direct])
>     with patch.object(m, "decrypt_packages") as decrypt, patch.object(m, "submit_links_to_pyload", return_value="ok") as submit:
>         assert m.process_releases([release], args, root / "history.jsonl", {}) == 0
>         decrypt.assert_not_called()
>         assert submit.call_args.args[0] == [direct]
>
>     def decrypt_one(packages, args):
>         assert [entry["filecrypt_url"] for entry in packages] == [container]
>         yield {"filecrypt_url": container, "decrypted_urls": [direct]}
>
>     release = m.Release("thread.html", 2, "Example", "page-h1", [container], direct_links=[direct])
>     with patch.object(m, "decrypt_packages", side_effect=decrypt_one), patch.object(m, "submit_links_to_pyload", return_value="ok") as submit:
>         assert m.process_releases([release], args, root / "history.jsonl", {}) == 0
>         assert submit.call_args.args[0] == [direct]
>
> archive = Path("archive/myboerse")
> sample = next(archive.rglob("*.html"), None)
> if sample:
>     print("MyBoerse archive sample:", sample)
> print("Extraction and mocked submission checks passed")
> PY
> git diff --check
> git status --short`
> - Ran `PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
> from pathlib import Path
> import myboerse_release_importer as m
> for path in sorted(Path("archive/myboerse").rglob("*.html"))[:20]:
>     release = m.parse_html_file(path)
>     if release and release.filecrypt_links:
>         print(f"MyBoerse Filecrypt parsing passed for {path}")
>         break
> else:
>     raise AssertionError("No MyBoerse sample with Filecrypt links")
> PY
> git diff --stat`
>
> </details>
</details>

Updated [myboerse_release_importer.py](./myboerse_release_importer.py) to extract `rapidgator.net`, `rg.to`, and Filecrypt container links from archived myGully threads, including replies. The dry run found 99 releases across 100 pages and matched both example URLs.

Preview all discovered links and save them to JSON:

```bash
python3 myboerse_release_importer.py --forum mygully.com --dry-run --json-out mygully-releases.json
```

Add `--select-link 'URL'` once per URL you want to submit, then remove `--dry-run`. Rapidgator links go directly to pyLoad, and selected Filecrypt containers are decrypted first.

Submission was verified with mocks. The history still tracks submissions by thread, so a successful submission causes later runs to skip that thread.
