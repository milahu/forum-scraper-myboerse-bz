# Classify links by filehoster

> add a feature to myboerse_release_importer.py
>
> the script should try to classify download links by filehoster
>
> for example, a filecrypt container link with file links hosted on rapidgator.net looks like this:
>
> ```xml
> <a href="https://filecrypt.cc/Container/422505D81F.html" target="_blank" class="link link--external" rel="nofollow ugc noopener"><img src="https://i.imgur.com/DrqaS42.png" data-url="https://i.imgur.com/DrqaS42.png" class="bbImage " loading="lazy" style="" width="" height=""><br>
> https://filecrypt.cc/Container/422505D81F.html<br>
> <img src="https://filecrypt.cc/Stat/EA779E6498.png" data-url="https://filecrypt.cc/Stat/EA779E6498.png" class="bbImage " loading="lazy" style="" width="" height=""></a>
> ```
>
> for example, a filecrypt container link with file links hosted on ddownload.com looks like this:
> ```xml
> <a href="https://filecrypt.cc/Container/60B787A573.html" target="_blank" class="link link--external" rel="nofollow ugc noopener"><img src="https://i.imgur.com/DrqaS42.png" data-url="https://i.imgur.com/DrqaS42.png" class="bbImage " loading="lazy" style="" width="" height=""> <img src="https://i.imgur.com/lQ55QX4.png" data-url="https://i.imgur.com/lQ55QX4.png" class="bbImage " loading="lazy" style="" width="" height=""><br>
> https://filecrypt.cc/Container/60B787A573.html<br>
> <img src="https://filecrypt.cc/Stat/BF9F88EC6E.png" data-url="https://filecrypt.cc/Stat/BF9F88EC6E.png" class="bbImage " loading="lazy" style="" width="" height=""></a>
> ```
>
> the image [https://i.imgur.com/DrqaS42.png](https://i.imgur.com/DrqaS42.png) has the text "rapidgator"
>
> the image [https://i.imgur.com/lQ55QX4.png](https://i.imgur.com/lQ55QX4.png) has the text "ddl.to" (the filehoster is ddownload.com)
>
> the HTML files in the archive directory contain only these two images:
>
> ```
> $ rg -I -o '<img src="https://i.imgur.com/.{7}.png"' archive/ | sort -u
> <img src="https://i.imgur.com/DrqaS42.png"
> <img src="https://i.imgur.com/lQ55QX4.png"
> ```
>
> to me, the filehoster is relevant, because i have a premium account only at rapidgator.net, so i want to process only filecrypt containers with rapidgator links
>
> the script should have an optional CLI parameter "filehoster" where i can filter the filecrypt containers by the filehoster, if the parser detected the filecrypt container "type"... if the parser failed to detect the container "type" then it should decrypt the container anyway (so the filter should not exclude containers with unknown type)

<details><summary>4 previous messages</summary>

> I’ll trace how the importer collects Filecrypt links and add a `--filehoster` filter that keeps containers whose hoster is unknown.
>
> <details><summary>Edited a file, explored 3 searches, 2 lists, ran 6 commands</summary>
>
> - Ran `git status --short; rg --files -g 'AGENTS.md' -g '*importer*' -g '*test*' -g 'pyproject.toml'; rg -n 'filecrypt|argparse|add_argument' myboerse_release_importer.py`
>
> <details><summary>Explored a search, a list</summary>
>
> - Listed files
> - Searched for `release_id|load_releases` in `myboerse_release_importer.py`
>
> </details>
>
> - Ran `sed -n '215,310p;575,685p;810,950p' myboerse_release_importer.py; rg --files --hidden .agents .codex; rg -l -m1 'lQ55QX4' archive | head -5; python3 -c 'import bs4, guessit, rapidfuzz'`
>
> - Ran `rg -m 1 -o '.{0,220}lQ55QX4.{0,200}' archive/myboerse/{1736996,2464998,1387423,2232416,2064709}.html | cut -c1-475
> rg -n 'myboerse_release_importer|nix-shell' readme.md
> command -v nix-shell; /usr/bin/python3 -c 'import bs4, guessit, rapidfuzz'
> ls /tmp | head -30
> for p in AGENTS.md ../AGENTS.md ../../AGENTS.md; do if test -f "$p"; then cat "$p"; fi; done`
>
> - Wrote `./myboerse_release_importer.py` (+23 -7)
>
> - Wrote `./myboerse_release_importer.py` (+32 -0)
>
> - Ran `git diff --check; cat shell.nix; ls -d /nix/store/*-python3-*-{beautifulsoup4,guessit,rapidfuzz,lxml,requests}-* 2>/dev/null | tail -25`
>
> <details><summary>Explored 2 searches, a list</summary>
>
> - Listed files in `store`
> - Searched for `beautifulsoup4|guessit|rapidfuzz|python3.*lxml|camoufox`
> - Searched for `extract_filecrypt_links`
>
> </details>
>
> - Ran `ls /nix/store | rg 'python3?-3\.1[34]\.[0-9]+-env$' | tail -25
> head -70 src/filecrypt-scraper-camoufox/src/filecrypt_scraper.py`
>
> - Ran `for d in /nix/store/*-python3-3.14.*-env; do
>   if test -d "$d/lib/python3.14/site-packages/guessit" && test -d "$d/lib/python3.14/site-packages/bs4"; then
>     if PYTHONDONTWRITEBYTECODE=1 "$d/bin/python" myboerse_release_importer.py --help >/dev/null 2>/dev/null; then
>       printf '%s\n' "$d/bin/python"
>       break
>     fi
>   fi
> done`
>
> </details>
>
> The archive examples confirm that DDownload links can display both badges. I’ve made the DDownload badge take precedence and will verify that unknown containers still reach the decryption queue.
>
> <details><summary>Ran a command</summary>
>
> - Ran `PYTHONDONTWRITEBYTECODE=1 /nix/store/kpw7mwz109qi5dxmrnw7318d371lrcgk-python3-3.14.7-env/bin/python - <<'PY'
> import json
> from pathlib import Path
> import sqlite3
> import sys
> from tempfile import TemporaryDirectory
> from unittest.mock import patch
> import myboerse_release_importer as m
>
> rapid, ddl, unknown, conflict = [f"https://filecrypt.cc/Container/{i}.html" for i in range(4)]
> def link(url, *badges):
>     return f'<a href="{url}">' + ''.join(f'<img src="{badge}">' for badge in badges) + '</a>'
> def html(*links):
>     return '<title>Example.2024.1080p</title>' + ''.join(links)
>
> with TemporaryDirectory() as directory:
>     root = Path(directory)
>     archive = root / "archive"
>     archive.mkdir()
>     (archive / "1.html").write_text(html(
>         link(rapid, m.RAPIDGATOR_BADGE), link(ddl, m.RAPIDGATOR_BADGE, m.DDOWNLOAD_BADGE),
>         link(unknown), link(conflict, m.RAPIDGATOR_BADGE), link(conflict, m.DDOWNLOAD_BADGE),
>         link(rapid),
>     ))
>     (archive / "2.html").write_text(html(link(ddl, m.DDOWNLOAD_BADGE)))
>     db = root / "cache"
>     inventory = root / "inventory.json"
>     argv = ["importer", "--archive", str(archive), "--cache-db", str(db),
>             "--history", str(root / "history"), "--json-out", str(inventory)]
>     for options, expected in [
>         (["--filehoster", "RapidGator.NET"], [rapid, unknown, conflict]),
>         (["--filehoster", "ddl.to"], [ddl, unknown, conflict]),
>         ([], [rapid, ddl, unknown, conflict]),
>     ]:
>         queued = []
>         def decrypt(packages, args):
>             queued.extend(item["filecrypt_url"] for item in packages)
>             return iter(())
>         with patch.object(sys, "argv", argv + options), patch.object(m, "decrypt_packages", decrypt):
>             assert m.main() == 0
>         assert queued == expected, queued
>         data = json.loads(inventory.read_text())
>         assert data[0]["filecrypt_links"] == [rapid, ddl, unknown, conflict]
>         assert data[0]["filecrypt_hosters"] == {rapid: "rapidgator.net", ddl: "ddownload.com"}
>         if options and options[-1] == "RapidGator.NET":
>             with sqlite3.connect(db) as conn:
>                 conn.execute("UPDATE html_parse_cache SET parser_version = 1, release_json = NULL")
>     print("CLI filtering, queue contents, complete inventory, and parser-cache refresh passed")
> PY
> git diff --check`
>
> </details>
</details>

Added `--filehoster` to [myboerse_release_importer.py](./myboerse_release_importer.py).

```sh
python myboerse_release_importer.py --filehoster rapidgator.net --dry-run
```

The importer classifies containers from the badges in archived links. When both badges appear on a link, it classifies the container as DDownload. With the Rapidgator filter, containers with missing or conflicting hoster information still qualify for decryption. Omit `--dry-run` to process the selected containers.

Verified Rapidgator and DDownload filtering, unknown-container fallback, and cache refresh with a mocked decryption queue.

> no, "When both badges appear on a link", it should classify the container as "unknown", or better, it should be classified as "rapidgator and ddownload", because such filecrypt containers actually contain links from both filehosters, where the user can select from multiple "mirrors" (in this case, the "mirrors" are rapidgator and ddownload)
>
> Response annotation
>
> > When both badges appear on a link, it classifies the container as DDownload.

<details><summary>2 previous messages</summary>

> I’ll update the classifier so a container with both badges matches either hoster filter.
>
> <details><summary>Edited a file, ran a command</summary>
>
> - Wrote `./myboerse_release_importer.py` (+8 -8)
> - Ran `git diff --check
> PYTHONDONTWRITEBYTECODE=1 /nix/store/kpw7mwz109qi5dxmrnw7318d371lrcgk-python3-3.14.7-env/bin/python - <<'PY'
> import json
> import sqlite3
> from pathlib import Path
> from tempfile import TemporaryDirectory
> from types import SimpleNamespace
> import myboerse_release_importer as m
>
> base = "https://filecrypt.cc/Container/"
> both, rapid, ddl, unknown = [base + name + ".html" for name in ("both", "rapid", "ddl", "unknown")]
> def anchor(url, *badges):
>     return f'<a href="{url}">' + ''.join(f'<img src="{badge}">' for badge in badges) + '</a>'
>
> with TemporaryDirectory() as tmp:
>     path = Path(tmp) / "1.html"
>     path.write_text("<title>Example.2024.1080p</title>" + "".join([
>         anchor(both, m.RAPIDGATOR_BADGE, m.DDOWNLOAD_BADGE),
>         anchor(rapid, m.RAPIDGATOR_BADGE),
>         anchor(ddl, m.DDOWNLOAD_BADGE),
>         anchor(unknown),
>     ]))
>     args = SimpleNamespace(archive=tmp, cache_db=Path(tmp) / "cache", release_group=None,
>                            resolution=None, wanted_movies=[], unwanted_movies=[])
>     first = m.parse_archive(args)
>     assert first[0].filecrypt_hosters[both] == ["ddownload.com", "rapidgator.net"]
>     with sqlite3.connect(args.cache_db) as db:
>         old = json.loads(db.execute("SELECT release_json FROM html_parse_cache").fetchone()[0])
>         old["filecrypt_hosters"][both] = "ddownload.com"
>         db.execute("UPDATE html_parse_cache SET parser_version=2, release_json=?", (json.dumps(old),))
>     for host, expected in [("rapidgator.net", [both, rapid, unknown]), ("ddl.to", [both, ddl, unknown]),
>                            (None, [both, rapid, ddl, unknown])]:
>         args.filehoster = m.normalize_filehoster(host) if host else None
>         releases = m.parse_archive(args)
>         assert m.filter_releases(releases, args)[0].filecrypt_links == expected
>         assert releases[0].filecrypt_links == [both, rapid, ddl, unknown]
> print("Dual-host matching, unknown fallback, and old cache refresh passed")
> PY`
>
> </details>
</details>

Containers with both badges are now classified as both Rapidgator and DDownload, so either `--filehoster` filter keeps them. Containers with no recognized badge still qualify for decryption. :codex-annotation{index="1" id="fac4f1ff-f781-45b8-a8fb-8e005a3bc0a7"}

Verified both filters, the unknown-host fallback, and automatic refresh of old parser cache entries.
