# Add forum CLI option

> modify the python script myboerse_release_importer.py
>
> the script should have an optional CLI parameter "--forum DOMAIN" which accepts a domain name like mygully.com, to select the HTML files from "archive/{args.forum}", for example from "archive/mygully.com"

<details><summary>2 previous messages</summary>

> I’ll check how the importer finds its HTML files and add `--forum DOMAIN` while preserving the current default.
>
> <details><summary>Edited a file, ran 5 commands</summary>
>
> - Ran `git status --short && rg --files --hidden -g '!.git' -g 'AGENTS.md' -g 'myboerse_release_importer.py' && rg -n 'archive|argparse|args\.' myboerse_release_importer.py`
> - Ran `sed -n '310,345p;1010,1098p' myboerse_release_importer.py; rg -n 'parse_archive\(' -g '*.py'; ls -d archive/*`
> - Wrote `./myboerse_release_importer.py` (+9 -0)
> - Ran `PYTHONDONTWRITEBYTECODE=1 python myboerse_release_importer.py --help && git diff --check`
> - Ran `rg --files -g '*filecrypt*' -g '*.nix'; sed -n '24,50p;1094,1125p' myboerse_release_importer.py; git diff --check`
> - Ran `PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
> import subprocess, sys, tempfile
> from pathlib import Path
> runner = """
> import runpy, sys, types
> stub = types.ModuleType('filecrypt_scraper')
> stub.decrypt_packages = stub.unique = None
> sys.modules[stub.__name__] = stub
> runpy.run_path(sys.argv.pop(1), run_name='__main__')
> """
> script = Path("myboerse_release_importer.py").resolve()
> with tempfile.TemporaryDirectory() as temp:
>     root = Path(temp)
>     for forum, count in [('mygully.com', 1), ('myboerse.bz', 2)]:
>         folder = root / 'archive' / forum
>         folder.mkdir(parents=True)
>         for n in range(count):
>             (folder / f'{n}.html').write_text('<html></html>')
>     def run(*args):
>         return subprocess.run([sys.executable, '-c', runner, str(script), '--dry-run', *args], cwd=temp, capture_output=True, text=True)
>     for args, count in [([], 3), (['--forum', 'mygully.com'], 1), (['--archive', str(root / 'archive'), '--forum', 'myboerse.bz'], 2)]:
>         result = run(*args)
>         assert result.returncode == 0 and f'parsing HTML files: N={count}' in result.stdout, (result.stdout, result.stderr)
>     result = run('--forum', 'missing.example')
>     assert result.returncode == 2 and 'archive/missing.example' in result.stderr
>     result = run('--forum', '../mygully.com')
>     assert result.returncode == 2 and 'must be a domain name' in result.stderr
> print('Archive selection and validation passed')
> PY
> git diff --check`
>
> </details>
</details>

Added `--forum DOMAIN` to [myboerse_release_importer.py](./myboerse_release_importer.py).

```sh
python myboerse_release_importer.py --forum mygully.com --dry-run
```

This scans `archive/mygully.com` recursively. The option also works with a custom `--archive` path. Omitting `--forum` preserves the existing behavior of scanning the entire archive.

Verified archive selection in dry runs with a stub for the missing `filecrypt_scraper` dependency.
