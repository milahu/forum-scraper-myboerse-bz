# Add mygully.com scraping support

> make the scraper also work with the forum at mygully.com
>
> i have attached a HAR file with HTTP requests of a login to mygully.com, and with browing to the subforum "audiobooks", then opening a thread, and clicking a download link (rapidgator.net)
>
> as before, the scraper should support scraping all threads from a subforum, when the user passes a start URL like [`https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/?pp=50&daysprune=-1&prefixid=SachbuchEbooks`](https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/?pp=50\&daysprune=-1\&prefixid=SachbuchEbooks) -- then the script should scrape all 146 pages, with page 2 at [`https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/forumdisplay.php?f=104&pp=50&prefixid=SachbuchEbooks&order=desc&daysprune=-1&page=2`](https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/forumdisplay.php?f=104\&pp=50\&prefixid=SachbuchEbooks\&order=desc\&daysprune=-1\&page=2), page 3 at [`https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/forumdisplay.php?f=104&pp=50&prefixid=SachbuchEbooks&order=desc&daysprune=-1&page=3`](https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/forumdisplay.php?f=104\&pp=50\&prefixid=SachbuchEbooks\&order=desc\&daysprune=-1\&page=3), etc. as before, the scaper should write each scraped thread to a HTML file at "archive/mygully.com/{thread_id}.html"
>
> User context
>
> Attachments:
> - mygully.com.har: `~/Downloads/mygully.com.har`

<details><summary>4 previous messages</summary>

> I’ll inspect the scraper and use the HAR as a record of MyGully’s requests and page structure. I’ll keep login values out of the output.
>
> <details><summary>Ran 6 commands, searched the web</summary>
>
> - Ran `ls -la && rg --files | head -60 && git status --short && ls -lh /home/user/Downloads/mygully.com.har`
>
> - Ran `cat myboerse_scraper.py readme.md doc/config.json; ls -ld archive/ archive/*`
>
> - Ran `python3 - <<'PY'
> import json,urllib.parse as u
> for i,e in enumerate(json.load(open('/home/user/Downloads/mygully.com.har'))['log']['entries']):
>  r=e['request']; p=u.urlsplit(r['url']); s=e['response']; c=s['content']
>  if p.hostname in ('mygully.com','www.mygully.com') and ('html' in c['mimeType'] or r['method']=='POST'):
>   print(i,r['method'],p.path,[x[0] for x in u.parse_qsl(p.query)],s['status'],c.get('size'),[x['name'] for x in r.get('postData',{}).get('params',[])])
> PY`
>
> - Ran `python3 - <<'PY'
> import json,re
> a=json.load(open('/home/user/Downloads/mygully.com.har'))['log']['entries']
> for i in [23,65,78,119,169,222]:
>  h=a[i]['response']['content']['text']
>  print(i)
>  for pat in [r'<form[^>]*login[^>]*>',r'<input[^>]*(?:vb_login_username|type="submit")[^>]*>',r'<a[^>]*logout[^>]*>[^<]*',r'<a[^>]*(?:id="thread_title_\d+"|rel="next"|page=2(?:["&]))[^>]*>[^<]*',r'id="(?:posts|post\d+)"',r'Seite \d+ von \d+']:
>   for s in re.findall(pat,h,re.I)[:3]:
>    print(re.sub(r'(?<=s=)[0-9a-f]{15,}', '[redacted]',s))
> PY
> rg -n 'subforum|scrape_subforum' doc/Codex-Add-subforum-CLI-filtering.md | head -20
> git log -5 --oneline
> python3 -c 'import camoufox'`
>
> - Ran `python3 - <<'PY'
> import json,re,base64
> a=json.load(open('/home/user/Downloads/mygully.com.har'))['log']['entries']
> for i in [23,65,78,119,169,222]:
>  c=a[i]['response']['content']; h=c.get('text',''); h=base64.b64decode(h).decode(errors='replace') if c.get('encoding')=='base64' else h
>  print(i,list(c),len(h))
>  for pat in [r'<form[^>]*login[^>]*>',r'<input[^>]*(?:vb_login_username|type="submit")[^>]*>',r'<a[^>]*logout[^>]*>[^<]*',r'<a[^>]*(?:id="thread_title_\d+"|rel="next"|page=2(?:["&]))[^>]*>[^<]*',r'id="(?:posts|post\d+)"',r'Seite \d+ von \d+']:
>   for s in re.findall(pat,h,re.I)[:3]: print(re.sub(r'(?<=s=)[0-9a-f]{15,}', '[redacted]',s))
> PY
> ls -ld archive archive/.; git ls-files`
>
> Searched the web for `https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/?pp=50&daysprune=-1&prefixid=SachbuchEbooks`
>
> - Ran `python3 - <<'PY'
> import json,re, urllib.parse as u
> a=json.load(open('/home/user/Downloads/mygully.com.har'))['log']['entries']
> h=a[222]['response']['content']['text']
> for line in h.splitlines():
>  if re.search(r'pag(enav|eNav)|vb_login|thread_title_|rel="next"|showthread\.php\?t=',line,re.I):
>   if 'securitytoken' in line:continue
>   print(re.sub(r'(?i)(logouthash=)[^"& ]+',r'\1[redacted]',line.strip())[:250])
> for i in (65,167,169,220,222):
>  r=a[i]['request']; print(i,u.urlsplit(r['url']).path,[(k,v) for k,v in u.parse_qsl(u.urlsplit(r['url']).query) if k in {'do','f','page','pp','sort','order','daysprune','prefixid','t'}])
> PY
> git show --stat HEAD
> ls -ld /home/user/src/milahu/forum-scraper-myboerse-bz/archive`
>
> </details>
>
> The HAR confirms the login endpoint and thread redirect, and it includes the thread HTML. It omits the listing response bodies, so I’ll verify the pagination logic against your URL examples and use the captured thread HTML to test archive validation.
>
> <details><summary>Edited 2 files, ran 2 commands</summary>
>
> - Wrote `./myboerse_scraper.py` (+84 -5)
> - Wrote `./myboerse_scraper.py` (+74 -16)
> - Wrote `./readme.md` (+15 -6)
> - Ran `python3 -B - <<'PY'
> import asyncio, json, re, tempfile
> from pathlib import Path
> from urllib.parse import urlsplit, parse_qs
> from types import SimpleNamespace
> import myboerse_scraper as s
>
> root = 'https://mygully.com'
> forum = root + '/forum/104-ha-rba-cher-und-ha-rspiele/'
> start = forum + '?pp=50&daysprune=-1&prefixid=SachbuchEbooks'
> har = json.loads(Path('/home/user/Downloads/mygully.com.har').read_text())
> entry = har['log']['entries'][222]
> html = entry['response']['content']['text']
> assert s.thread_id_from_url(entry['request']['url']) == '7999447'
> assert s.thread_id_from_url('https://myboerse.bz/threads/example.123/') == '123'
> class Page:
>     def __init__(self):
>         self.visited = []
>     async def goto(self, url, **kwargs):
>         self.visited.append(url)
>         self.url = url
>         if '/showthread.php' in url:
>             self.url = root + '/showthread.php?' + urlsplit(url).query
>         return SimpleNamespace(ok=True)
>     def locator(self, selector):
>         number = s.mygully_page_number(self.url)
>         if selector.startswith('a[id'):
>             hrefs = [forum + 'showthread.php?t=7999447', forum + f'showthread.php?t={number}']
>         elif selector.startswith('a[href*="forumdisplay'):
>             hrefs = [forum + f'forumdisplay.php?f=104&pp=10&prefixid=Wrong&order=desc&daysprune=30&page={number+1}'] if number < 146 else []
>             hrefs.insert(0, root + f'/forumdisplay.php?f=105&page={number+1}')
>         else:
>             assert selector == '#posts'
>             hrefs = re.findall(r'id="posts"', html)
>         async def count(): return len(hrefs)
>         async def evaluate_all(script): return hrefs
>         return SimpleNamespace(count=count, evaluate_all=evaluate_all)
>     async def content(self):
>         return html
> async def check():
>     with tempfile.TemporaryDirectory() as directory:
>         output = Path(directory)
>         (output / '2.html').write_text('cached')
>         page = Page()
>         await s.scrape_mygully_subforum(page, start, output, 0)
>         listings = [url for url in page.visited if '/showthread.php' not in url]
>         assert [s.mygully_page_number(url) for url in listings] == list(range(1, 147))
>         for n, url in enumerate(listings[1:], 2):
>             assert urlsplit(url).path == urlsplit(forum).path + 'forumdisplay.php'
>             assert parse_qs(urlsplit(url).query) == {'f':['104'], 'pp':['50'], 'prefixid':['SachbuchEbooks'], 'order':['desc'], 'daysprune':['-1'], 'page':[str(n)]}
>         assert len(page.visited) == 292
>         assert {p.name for p in output.iterdir()} == {f'{i}.html' for i in range(1,147)} | {'7999447.html'}
>         assert (output / '7999447.html').read_text() == html
>         assert (output / '2.html').read_text() == 'cached'
> asyncio.run(check())
> print('146 listing pages, filters, redirect, captured HTML, and cache verified')
> PY
> python3 -B myboerse_scraper.py --help
> git diff --check
> git status --short`
> - Ran `python3 -B - <<'PY'
> import asyncio, json, tempfile
> from pathlib import Path
> from types import SimpleNamespace
> from urllib.parse import parse_qs, urlsplit
> import myboerse_scraper as s
>
> site = 'https://mygully.com'
> forum = site + '/forum/104-ha-rba-cher-und-ha-rspiele/'
> start = forum + '?pp=50&daysprune=-1&prefixid=SachbuchEbooks'
> entry = json.loads(Path('/home/user/Downloads/mygully.com.har').read_bytes())['log']['entries'][222]
> html = entry['response']['content']['text']
> assert s.thread_id_from_url(entry['request']['url']) == '7999447'
> assert s.thread_id_from_url('https://myboerse.bz/threads/example.123/') == '123'
>
> class Page:
>     def __init__(self):
>         self.visited = []
>     async def goto(self, url, **kwargs):
>         self.visited.append(url)
>         self.url = site + '/showthread.php?' + urlsplit(url).query if '/showthread.php' in url else url
>         return SimpleNamespace(ok=True)
>     def locator(self, selector):
>         number = s.mygully_page_number(self.url)
>         if selector.startswith('a[id'):
>             values = [forum + 'showthread.php?t=7999447', forum + f'showthread.php?t={number}']
>         elif selector.startswith('a[href*="forumdisplay'):
>             values = [site + f'/forumdisplay.php?f=105&page={number+1}']
>             if number < 146:
>                 values.append(forum + f'forumdisplay.php?f=104&pp=10&prefixid=Wrong&order=desc&daysprune=30&page={number+1}')
>         else:
>             assert selector == '#posts'
>             values = ['posts'] if 'id="posts"' in html else []
>         async def count():
>             return len(values)
>         async def evaluate_all(script):
>             return values
>         return SimpleNamespace(count=count, evaluate_all=evaluate_all)
>     async def content(self):
>         return html
>
> async def check():
>     with tempfile.TemporaryDirectory() as directory:
>         output = Path(directory)
>         (output / '2.html').write_text('cached')
>         page = Page()
>         await s.scrape_mygully_subforum(page, start, output, 0)
>         listings = [url for url in page.visited if '/showthread.php' not in url]
>         assert [s.mygully_page_number(url) for url in listings] == list(range(1, 147))
>         for number, url in enumerate(listings[1:], 2):
>             assert urlsplit(url).path == urlsplit(forum).path + 'forumdisplay.php'
>             assert parse_qs(urlsplit(url).query) == {'f':['104'], 'pp':['50'], 'prefixid':['SachbuchEbooks'], 'order':['desc'], 'daysprune':['-1'], 'page':[str(number)]}
>         assert len(page.visited) == 292
>         assert {p.name for p in output.iterdir()} == {f'{i}.html' for i in range(1,147)} | {'7999447.html'}
>         assert (output / '7999447.html').read_bytes() == html.encode()
>         assert (output / '2.html').read_bytes() == b'cached'
> asyncio.run(check())
> print('Verified 146 listing pages, filters, thread redirects, archived HTML bytes, and cache reuse')
> PY
> git diff --check`
>
> </details>
</details>

The [scraper](./myboerse_scraper.py) now accepts MyGully subforum URLs. It signs in with your MyGully credentials, keeps the start URL’s filters across listing pages, and saves each thread to `archive/mygully.com/<thread-id>.html`. Existing archives are reused, and Rapidgator links stay in the saved HTML. MyBoerse member URLs still work through the same command.

```bash
python myboerse_scraper.py \
  --config mygully-config.json \
  --start-url 'https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/?pp=50&daysprune=-1&prefixid=SachbuchEbooks'
```

I verified traversal of 146 simulated listing pages, filter preservation, thread redirects, and cache reuse using the captured thread HTML. Live login and pagination remain unverified.
