# Add first-post link parsing

> modify the python script myboerse_release_importer.py
>
> add the CLI flag "--first-post-links". with that flag, from each forum thread HTML file, only the first post is used to extract download links, which are then added to pyload
>
> maybe you have to update the "parsed threads" cache, to also cache the post ID
>
> post IDs are stored like...
>
> archive/myboerse/2706379.html
>
> example post ID: 7129418
> ```xml
>
> 	<article class="message message--post js-post js-inlineModContainer  " data-author="Team VECTOR" data-content="post-7129418" id="js-post-7129418">
>
> 		<span class="u-anchorTarget" id="post-7129418"></span>
>
> 		...
>
> </article>
> ```
>
> archive/mygully.com/8750797.html
>
> example post ID: 55737163
> ```xml
> <table id="post55737163" class="tborder" cellpadding="4" cellspacing="0" border="0" width="100%" align="center">
> ...
> </table>
> ```

<details><summary>2 previous messages</summary>

> I’ll trace how the importer parses and caches links, then add the flag and verify it against both forum formats.
>
> <details><summary>Edited a file, ran 6 commands</summary>
>
> - Ran `rg --files --hidden -g AGENTS.md -g myboerse_release_importer.py; git status --short; rg -n 'cache|argparse|def |pyload' myboerse_release_importer.py`
> - Ran `sed -n '25,80p;175,449p;1057,1078p;1110,1198p' myboerse_release_importer.py; ls -d archive/*; rg -n 'HTML_PARSE|post_message' myboerse_release_importer.py`
> - Ran `rg -n -m 5 'id="post[0-9]+"|data-content="post-' archive/myboerse/2706379.html archive/mygully.com/8750797.html; ls -a; sed -n '1,25p;79,125p' myboerse_release_importer.py; python myboerse_release_importer.py --help`
> - Wrote `./myboerse_release_importer.py` (+27 -7)
> - Wrote `./myboerse_release_importer.py` (+10 -3)
> - Ran `sed -n '1537,1546p' archive/myboerse/2706379.html; sed -n '965,980p' archive/mygully.com/8750797.html; git diff --check`
> - Ran `sed -n '858,900p;1205,1235p' myboerse_release_importer.py
> python - <<'PY'
> from pathlib import Path
> from tempfile import TemporaryDirectory
> from types import SimpleNamespace
> from myboerse_release_importer import parse_archive, parse_html_file
> from bs4 import BeautifulSoup
>
> paths = [Path('archive/myboerse/2706379.html'), Path('archive/mygully.com/8750797.html')]
> for path in paths:
>     full = parse_html_file(path)
>     first = parse_html_file(path, first_post_links=True)
>     assert first and full and set(first.download_links) <= set(full.download_links)
>     print(path, len(first.download_links), len(full.download_links))
>
> post_formats = [
>     ('article', 'class="message--post" data-content="post-{}"', 'class="bbWrapper"'),
>     ('table', 'class="tborder" id="post{}"', 'id="post_message_{}"'),
> ]
> with TemporaryDirectory() as directory:
>     root = Path(directory)
>     args = SimpleNamespace(archive=root, subforum=[], cache_db=root / 'cache.sqlite', first_post_links=False)
>     for index, (tag, attrs, body) in enumerate(post_formats, start=1):
>         def post(post_id, content):
>             return f'<{tag} {attrs.format(post_id)}><div {body.format(post_id)}>{content}</div></{tag}>'
>         outside = '<a href="https://rapidgator.net/file/outside">outside</a>'
>         first = '<a href="https://filecrypt.cc/Container/first.html">first</a> https://rapidgator.net/file/first'
>         reply = '<a href="https://rapidgator.net/file/reply">reply</a>'
>         (root / f'{index}.html').write_text('<title>Example</title>' + outside + post(99, first) + post(1, reply))
>         (root / f'{index+2}.html').write_text('<title>Example</title>' + post(99, 'No links') + post(1, reply))
>     for mode in (False, True, True, False):
>         args.first_post_links = mode
>         releases = parse_archive(args)
>         assert len(releases) == (2 if mode else 4)
>         for release in releases[:2]:
>             assert set(release.download_links) == ({
>                 'https://filecrypt.cc/Container/first.html', 'https://rapidgator.net/file/first'
>             } | (set() if mode else {'https://rapidgator.net/file/outside', 'https://rapidgator.net/file/reply'}))
> PY`
> - Wrote `./myboerse_release_importer.py` (+2 -1)
> - Ran `python - <<'PY'
> from pathlib import Path
> from tempfile import TemporaryDirectory
> from unittest.mock import patch
> import myboerse_release_importer as importer
>
> with TemporaryDirectory() as directory:
>     root = Path(directory)
>     base = 'https://rapidgator.net/file/'
>     (root / '1.html').write_text(
>         '<title>Example</title>'
>         f'<article class="message--post" data-content="post-20"><a href="{base}first">first</a></article>'
>         f'<article class="message--post" data-content="post-21"><a href="{base}reply">reply</a></article>'
>     )
>     argv = ['importer', '--archive', directory, '--cache-db', str(root / 'cache.sqlite'),
>             '--history', str(root / 'history.jsonl'), '--first-post-links']
>     with patch.object(importer.sys, 'argv', argv), patch.object(
>         importer, 'submit_links_to_pyload', return_value='OK'
>     ) as submit:
>         assert importer.main() == 0
>         submit.assert_called_once()
>         assert submit.call_args.args[0] == [base + 'first']
> PY
> git diff --check
> git status --short`
>
> </details>
</details>

Added `--first-post-links` to [myboerse_release_importer.py](./myboerse_release_importer.py). With the flag, the importer extracts Rapidgator links and Filecrypt containers only from the first post in each MyBoerse or myGully HTML file. Threads whose first post has no supported links are skipped.

The parsed-thread cache uses mode-specific versions. Switching modes reparses each file once.

Verified both archive examples, tested that reply links are excluded, and confirmed that a mocked pyLoad submission received only the first post’s link. No live submission was made.
