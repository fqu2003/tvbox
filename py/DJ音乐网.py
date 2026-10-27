#coding=utf-8
#!/usr/bin/python

# ============================================================
# CONFIG
# ============================================================
ENABLE_LOG_FILE       = False
ENABLE_HTML_DUMP      = False
ENABLE_CONSOLE_LOG    = True
LOG_DIR               = "/storage/emulated/0/Download/djnet_debug"
MAX_HTML_DUMPS        = 100

# Streaming tuning
AUDIO_URL_TTL         = 300      # detik — cache URL audio
HEALTH_CHECK_ENABLED  = True     # test URL sebelum play
HEALTH_CHECK_TIMEOUT  = 1.5      # detik per kandidat
AUDIO_REFERER         = "https://m.dj.net/"
DEFAULT_CDN           = "https://preview-src.dj.net:4431/"

# Tampilan
MAX_TITLE_LEN         = 25       # batas judul sebelum dipotong "…"
PREFER_AVATAR_SIZE    = "middle" # small / middle / big

# ============================================================

import re
import os
import json
import time
import requests
import traceback
from datetime import datetime
from urllib.parse import quote_plus, unquote, quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "DJ音乐网"

    def init(self, extend):
        self.console_log = False
        self._log_file = None
        self.dump_html = False
        self._dump_count = 0
        self.log_dir = LOG_DIR

        try:
            self.extendDict = json.loads(extend) if extend else {}
        except:
            self.extendDict = {}

        self.debug_enabled = self._as_bool(self.extendDict.get('enable_debug', ENABLE_LOG_FILE))
        self.dump_html = self._as_bool(self.extendDict.get('dump_html', ENABLE_HTML_DUMP))
        self.console_log = self._as_bool(self.extendDict.get('console_log', ENABLE_CONSOLE_LOG))
        self.max_dumps = int(self.extendDict.get('max_dumps', MAX_HTML_DUMPS))
        self.log_dir = self.extendDict.get('log_dir') or LOG_DIR
        self.max_title_len = int(self.extendDict.get('max_title_len', MAX_TITLE_LEN))

        # Cache URL audio
        self._url_cache = {}
        self._url_ttl = int(self.extendDict.get('audio_url_ttl', AUDIO_URL_TTL))
        self._health_check = self._as_bool(self.extendDict.get('health_check', HEALTH_CHECK_ENABLED))
        self._health_timeout = float(self.extendDict.get('health_timeout', HEALTH_CHECK_TIMEOUT))

        # Cache hash per halaman (deteksi duplikat pagination)
        self._page_hashes = {}   # cid -> list of hash

        if self.debug_enabled or self.dump_html:
            if not self._ensure_log_dir():
                fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'djnet_debug')
                self.log_dir = fallback
                self._ensure_log_dir()

            if self.debug_enabled:
                log_name = f"djnet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                self._log_file = os.path.join(self.log_dir, log_name)
                self._log_raw(f"=== DJ.net Spider v11 (pagination fix) initiated at {datetime.now().isoformat()} ===")
                self._log_raw(f"debug_dir: {self.log_dir}")
                print(f"[DJNET] Log: {self._log_file}")

        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=20, pool_maxsize=40,
            max_retries=Retry(
                total=3,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=["GET", "POST"],
            )
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self.header = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://m.dj.net/",
        }

        self.avatar_header = {
            "User-Agent": self.header["User-Agent"],
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.dj.net/",
        }

        self.audio_header = {
            "User-Agent": self.header["User-Agent"],
            "Accept": "audio/mpeg,audio/*;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
            "Range": "bytes=0-",
            "Connection": "keep-alive",
            "Referer": AUDIO_REFERER,
            "Origin": AUDIO_REFERER.rstrip('/'),
        }

        self._probe_session = requests.Session()

        self.base_url = "https://m.dj.net"
        self.www_url = "https://www.dj.net"

        self.categories = [
            {'type_id': 'mtop',   'type_name': '排行榜'},
            {'type_id': 'mclass', 'type_name': '分类'},
        ]

        self.sub_categories = {
            'mtop': [
                {'n': '慢摇',  'v': '13'},
                {'n': '劲爆',  'v': '80'},
                {'n': '专业',  'v': '81'},
                {'n': '连版',  'v': '83'},
                {'n': '流行',  'v': '94'},
                {'n': '单曲',  'v': '17'},
            ],
            'mclass': [
                {'n': '酒吧串烧',   'v': '51'},
                {'n': '包房串烧',   'v': '1'},
                {'n': '中文串烧',   'v': '2'},
                {'n': '喊麦现场',   'v': '99'},
                {'n': '越鼓串烧',   'v': '3'},
                {'n': '的高串烧',   'v': '100'},
                {'n': '加快串烧',   'v': '101'},
                {'n': '慢歌连版',   'v': '5'},
                {'n': '专业串烧',   'v': '82'},
                {'n': '外文Electro','v': '57'},
                {'n': '外文House',  'v': '61'},
                {'n': '外文Mashup', 'v': '62'},
                {'n': 'Hardstyle',  'v': '63'},
                {'n': '越南电鼓',   'v': '42'},
                {'n': '3D环绕',     'v': '54'},
                {'n': '中文Electro','v': '85'},
                {'n': '中文House',  'v': '86'},
                {'n': '中文Dance',  'v': '89'},
                {'n': '流行Pop',    'v': '55'},
                {'n': '流行Rock',   'v': '71'},
            ],
        }

    # ==================== DEBUG HELPERS ====================
    def _as_bool(self, v):
        if isinstance(v, bool): return v
        if isinstance(v, str): return v.lower() in ('1', 'true', 'yes', 'on')
        return bool(v)

    def _ensure_log_dir(self):
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            return True
        except Exception as e:
            print(f"[DJNET] Cannot access {self.log_dir}: {e}")
            return False

    def _log_raw(self, msg):
        if not self._log_file: return
        try:
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(msg + '\n')
        except: pass

    def _log(self, msg, level="INFO"):
        line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [{level}] {msg}"
        if self.console_log: print(f"[DJNET] {msg}")
        if self._log_file:
            try:
                with open(self._log_file, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
            except: pass

    def _dump(self, name, content):
        if not self.dump_html: return
        if self._dump_count >= self.max_dumps: return
        try:
            safe = re.sub(r'[^\w\-\.]', '_', name)[:80]
            ts = datetime.now().strftime('%H%M%S')
            fname = f"{ts}_{safe}.html"
            path = os.path.join(self.log_dir, fname)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            self._dump_count += 1
            self._log(f"Dumped -> {fname} ({len(content)}b)")
        except Exception as e:
            self._log(f"Dump failed: {e}", "WARN")

    # ==================== HTTP ====================
    def _http(self, method, url, timeout=12, **kwargs):
        max_attempts = 3
        last_exc = None
        for attempt in range(max_attempts):
            t0 = time.time()
            try:
                if method.upper() == 'POST':
                    r = self.session.post(url, timeout=timeout, **kwargs)
                else:
                    r = self.session.get(url, timeout=timeout, **kwargs)
                elapsed = (time.time() - t0) * 1000
                self._log(f"{method.upper()} {url} -> {r.status_code} ({len(r.content)}b, {elapsed:.0f}ms)")
                return r
            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError) as e:
                last_exc = e
                elapsed = (time.time() - t0) * 1000
                self._log(f"{method.upper()} {url} -> RETRY {attempt+1}/{max_attempts} ({elapsed:.0f}ms): {e}", "WARN")
                if attempt < max_attempts - 1:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                raise
            except Exception as e:
                self._log(f"{method.upper()} {url} -> FATAL: {e}", "ERROR")
                raise
        if last_exc:
            raise last_exc

    def _fix_url(self, u):
        if not u:
            return ""
        u = u.replace('&amp;', '&').strip()
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('http'):
            return u
        if 'uc_server/avatar.php' in u:
            return self.www_url + '/' + u.lstrip('/')
        if u.startswith('/'):
            return self.base_url + u
        return self.base_url + '/' + u

    def _fix_avatar(self, u):
        """Paksa avatar size konsisten + skip default noavatar."""
        if not u:
            return ""
        u = self._fix_url(u)
        # Skip default noavatar (biar OK影视 pakai placeholder rapi)
        if 'noavatar' in u:
            return ""
        # Paksa size=middle untuk konsistensi dimensi
        if 'size=small' in u:
            u = u.replace('size=small', f'size={PREFER_AVATAR_SIZE}')
        elif 'size=' not in u and 'avatar.php' in u:
            u = u + f'&size={PREFER_AVATAR_SIZE}'
        return u

    def _proxy_image(self, u):
        if not u:
            return ""
        try:
            base = str(self.getProxyUrl() or '').strip()
        except Exception:
            base = ''
        if not base:
            base = 'http://127.0.0.1:9978/proxy?do=py'
        return base + ('&' if '?' in base else '?') + 'type=pic&url=' + quote(u, safe='')

    def _decode_html(self, content):
        for enc in ('gbk', 'gb2312', 'gb18030', 'utf-8'):
            try:
                return content.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return content.decode('utf-8', errors='replace')

    def _clean_title(self, name):
        """Strip .mp3, rapikan spasi, dan batasi panjang."""
        name = re.sub(r'\.mp3$', '', name, flags=re.IGNORECASE).strip()
        name = re.sub(r'\s+', ' ', name)
        if len(name) > self.max_title_len:
            name = name[:self.max_title_len] + "…"
        return name

    # ==================== PARSER LIST ====================
    def _extract_items(self, html, cat_name=""):
        items = []
        seen = set()

        li_pattern = re.compile(r'<li>(.*?)</li>', re.DOTALL)
        mplay_pattern = re.compile(
            r'<a\s+href="[^"]*mod=mplay[^"]*id=(\d+)[^"]*"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )
        img_pattern = re.compile(r'<img\s+src="([^"]+)"', re.IGNORECASE)

        for li_match in li_pattern.finditer(html):
            li_html = li_match.group(1)
            mplay_match = mplay_pattern.search(li_html)
            if not mplay_match:
                continue
            sid, name_html = mplay_match.groups()
            if sid in seen:
                continue
            seen.add(sid)

            raw_name = re.sub(r'<[^>]+>', '', name_html).strip()
            name = self._clean_title(raw_name)
            if not name or len(name) < 2:
                continue

            img = ""
            img_match = img_pattern.search(li_html)
            if img_match:
                raw = self._fix_avatar(img_match.group(1))
                if raw:
                    img = self._proxy_image(raw)

            # Remarks pendek — biar tinggi item konsisten
            short_remark = (cat_name or "")[:8]

            items.append({
                "vod_id": sid,
                "vod_name": name,
                "vod_pic": img,
                "vod_remarks": short_remark,
            })

        self._log(f"  regex found {len(items)} items")
        return items

    def _page_hash(self, items):
        """Hash dari daftar vod_id — untuk deteksi halaman duplikat."""
        if not items:
            return 0
        return hash(tuple(sorted(i['vod_id'] for i in items)))

    # ==================== OK影视 INTERFACE ====================
    def homeContent(self, filter):
        self._log(f"homeContent(filter={filter})")
        result = {'class': self.categories, 'filters': {}}
        if filter:
            for cid, subs in self.sub_categories.items():
                result['filters'][cid] = [{
                    'key': 'sub_id',
                    'name': '分类',
                    'value': [{'n': s['n'], 'v': s['v']} for s in subs],
                }]
        return result

    def homeVideoContent(self):
        return self.categoryContent('mindex', 1, False, {})

    def categoryContent(self, cid, page, filter, ext):
        page = int(page)
        self._log(f"categoryContent START cid={cid} page={page} ext={ext}")
        result = {'list': [], 'page': page, 'pagecount': page, 'limit': 0, 'total': 0}

        cat_name = next((c['type_name'] for c in self.categories if c['type_id'] == cid), "DJ")
        url = None
        per_page = 20

        if cid == 'mclass':
            sub_id = '51'
            if ext and ext.get('sub_id'):
                sub_id = str(ext['sub_id'])
            for s in self.sub_categories.get('mclass', []):
                if s['v'] == sub_id:
                    cat_name = s['n']
                    break
            url = f"{self.base_url}/music.php?mod=mclass&op=addtime&id={sub_id}&mobile=2"
            if page > 1:
                url += f"&page={page}"
            per_page = 30

        elif cid == 'mtop':
            top_id = '13'
            if ext and ext.get('sub_id'):
                top_id = str(ext['sub_id'])
            for s in self.sub_categories.get('mtop', []):
                if s['v'] == top_id:
                    cat_name = s['n']
                    break
            url = f"{self.base_url}/music.php?mod=mtop&id={top_id}&mobile=2"
            # ⚠️ mtop = top100 statis, tidak support pagination
            # Jangan kirim &page=N supaya tidak dapat duplikat
            per_page = 100

        else:
            url = f"{self.base_url}/music.php?mod={cid}&mobile=2"
            if page > 1:
                url += f"&page={page}"

        self._log(f"  URL: {url}")

        try:
            r = self._http('GET', url, headers=self.header, timeout=15)
            html = self._decode_html(r.content)
            self._dump(f"list_{cid}_{cat_name}_p{page}", html)

            items = self._extract_items(html, cat_name)
            self._log(f"  Extracted {len(items)} items")

            # ✅ Deteksi halaman duplikat (untuk cid yang support pagination)
            if cid != 'mtop' and page > 1:
                h = self._page_hash(items)
                prev = self._page_hashes.get(cid, [])
                if h in prev:
                    self._log(f"  ⚠️ DUPLICATE page detected — server returns same content", "WARN")
                    result['list'] = []
                    result['pagecount'] = page  # stop
                    return result
                prev.append(h)
                self._page_hashes[cid] = prev

            result['list'] = items[:per_page]
            result['limit'] = len(result['list'])

            if cid == 'mtop':
                # mtop = 1 page saja
                result['pagecount'] = 1
                result['total'] = len(items)
            else:
                # mindex & mclass — lanjut selama masih penuh
                result['pagecount'] = page + 1 if len(items) >= per_page else page

        except Exception as e:
            self._log(f"  FATAL: {type(e).__name__}: {e}", "ERROR")
            self._log(traceback.format_exc(), "ERROR")
        finally:
            self._log(f"categoryContent END")

        return result

    def detailContent(self, did):
        sid = did[0] if isinstance(did, (list, tuple)) else did
        sid = str(sid)
        self._log(f"detailContent START sid={sid}")
        result = {'list': []}
        try:
            url = f"{self.base_url}/music.php?mod=mplay&id={sid}&mobile=2"
            r = self._http('GET', url, headers=self.header, timeout=12)
            html = self._decode_html(r.content)
            self._dump(f"detail_{sid}", html)

            # --- Title ---
            m = re.search(r'<title>([^<]+)</title>', html)
            title = m.group(1).strip() if m else f"DJ {sid}"
            title = re.sub(r'\s*[-_|].*$', '', title).strip()
            title = re.sub(r'\.mp3$', '', title, flags=re.IGNORECASE).strip()

            # --- Cover ---
            m_cover = re.search(r'\.cd\s*\{[^}]*background:\s*url\("([^"]+)"\)', html, re.DOTALL)
            if not m_cover:
                m_cover = re.search(r'<img\s+src="([^"]+)"[^>]*class="[^"]*avatar', html)
            cover_raw = self._fix_avatar(m_cover.group(1)) if m_cover else ""
            cover = self._proxy_image(cover_raw) if cover_raw else ""

            # --- Metadata ---
            m_cat = re.search(r'舞曲分类：([^<]+)', html)
            category = m_cat.group(1).strip() if m_cat else ""

            m_size = re.search(r'下载音质：</b>\s*([^<]+)', html)
            quality = m_size.group(1).strip() if m_size else ""

            m_date = re.search(r'更新时间：</b>\s*([^<]+)', html)
            update_date = m_date.group(1).strip() if m_date else ""

            m_hits = re.search(r'试听总数：</b>\s*<span[^>]*>([^<]+)', html)
            hits = m_hits.group(1).strip() if m_hits else ""

            # --- Audio URLs ---
            audio_urls = self._fetch_audio_urls(sid)
            self._log(f"  audio candidates: {len(audio_urls)}")

            if audio_urls:
                best = self._pick_alive_url(audio_urls) if self._health_check else audio_urls[0]

                ordered = [best] + [u for u in audio_urls if u != best]
                play_lines = []
                for i, u in enumerate(ordered):
                    label = "推荐" if i == 0 else f"线路{i+1}"
                    play_lines.append(f"{label}${u}")
                play_url = '#'.join(play_lines)

                # Remarks pendek — buang tanggal biar tidak terlalu panjang
                remark_parts = [p for p in [quality, category] if p]
                remark_str = " · ".join(remark_parts)
                if len(remark_str) > 30:
                    remark_str = remark_str[:30] + "…"

                result['list'] = [{
                    "vod_id": sid,
                    "vod_name": title[:120],
                    "vod_pic": cover,
                    "vod_content": f"{title}\n分类: {category}\n音质: {quality}\n试听: {hits}\n更新: {update_date}",
                    "vod_play_from": "DJ音乐网",
                    "vod_play_url": play_url,
                    "vod_remarks": remark_str,
                }]
            else:
                self._log(f"  no audio URL for {sid}", "WARN")
        except Exception as e:
            self._log(f"detailContent FATAL: {type(e).__name__}: {e}", "ERROR")
            self._log(traceback.format_exc(), "ERROR")
        return result

    # ==================== AUDIO URL FETCH ====================
    def _fetch_audio_urls(self, sid):
        cached = self._url_cache.get(sid)
        if cached and (time.time() - cached[1]) < self._url_ttl:
            self._log(f"  cache hit ({int(time.time() - cached[1])}s old) -> {len(cached[0])} url(s)")
            return list(cached[0])

        endpoint = f"{self.base_url}/template/zhzh_dzmusic/ajax/?action=geturl"
        self._log(f"  fetching audio via {endpoint}")

        urls = []
        try:
            r = self._http('POST', endpoint, data={'id': sid},
                          headers=self.header, timeout=8)
            text = r.text
            self._log(f"  response: {text[:300]}")

            try:
                j = r.json()
                if j.get('error') == '0' and j.get('data'):
                    item = j['data'][0]
                    src = item.get('src', '')
                    ser = item.get('ser', []) or []

                    hosts = []
                    for s in ser:
                        if isinstance(s, dict) and s.get('u'):
                            hosts.append(s['u'].rstrip('/') + '/')
                    if not hosts:
                        hosts = [DEFAULT_CDN]

                    if src.startswith('http'):
                        urls = [src]
                    else:
                        path = src.lstrip('/')
                        urls = [h + path for h in hosts]

                    urls = list(dict.fromkeys(urls))
                    self._log(f"  built {len(urls)} candidate URL(s)")
            except Exception as e:
                self._log(f"  JSON parse error: {e}", "WARN")

            if not urls:
                m = re.search(r'"(?:url|src)"\s*:\s*"([^"]+\.(?:mp3|m4a|wav|aac)[^"]*)"', text, re.I)
                if m:
                    urls = [self._fix_url(m.group(1))]

        except Exception as e:
            self._log(f"  audio fetch error: {e}", "WARN")

        if urls:
            self._url_cache[sid] = (urls, time.time())
        return urls

    def _pick_alive_url(self, urls):
        if not urls:
            return None

        for u in urls:
            try:
                t0 = time.time()
                r = self._probe_session.head(
                    u,
                    headers={**self.audio_header, "Range": "bytes=0-1"},
                    timeout=self._health_timeout,
                    allow_redirects=True,
                )
                ms = (time.time() - t0) * 1000

                if r.status_code in (405, 501):
                    r = self._probe_session.get(
                        u,
                        headers={**self.audio_header, "Range": "bytes=0-1023"},
                        timeout=self._health_timeout,
                        allow_redirects=True,
                    )
                    ms = (time.time() - t0) * 1000

                if r.status_code in (200, 206, 416):
                    self._log(f"  alive [{r.status_code}] {ms:.0f}ms {u[:70]}...")
                    return u

                self._log(f"  dead [{r.status_code}] {ms:.0f}ms {u[:70]}...", "WARN")
            except Exception as e:
                self._log(f"  dead ({type(e).__name__}) {u[:70]}...", "WARN")

        self._log(f"  no alive URL, fallback to first", "WARN")
        return urls[0]

    # ==================== SEARCH ====================
    def searchContent(self, key, quick, pg=1):
        page = int(pg)
        result = {'list': [], 'page': page, 'pagecount': page, 'limit': 0, 'total': 0}
        encoded = quote_plus((key or '').strip())
        if not encoded:
            return result

        try:
            r0 = self._http('GET', f"{self.base_url}/music.php?mod=mindex&mobile=2",
                           headers=self.header, timeout=10)
            html0 = self._decode_html(r0.content)
            m_hash = re.search(r'name="formhash"\s+value="([a-f0-9]+)"', html0)
            formhash = m_hash.group(1) if m_hash else ""

            url = f"{self.base_url}/search.php?mod=music&mobile=2"
            data = {
                'srchtxt': key,
                'searchsubmit': 'yes',
                'formhash': formhash,
            }
            r = self._http('POST', url, data=data, headers=self.header, timeout=12)
            html = self._decode_html(r.content)
            self._dump(f"search_{encoded[:20]}_p{page}", html)

            items = self._extract_items(html, "搜索")
            result['list'] = items[:20]
            result['limit'] = len(result['list'])
            result['pagecount'] = page
        except Exception as e:
            self._log(f"search error: {e}", "ERROR")
            self._log(traceback.format_exc(), "ERROR")
        return result

    # ==================== PLAYER ====================
    def playerContent(self, flag, pid, vipFlags):
        header = {
            "User-Agent": self.header["User-Agent"],
            "Accept": "audio/mpeg,audio/*;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity",
            "Range": "bytes=0-",
            "Connection": "keep-alive",
            "Referer": AUDIO_REFERER,
            "Origin": AUDIO_REFERER.rstrip('/'),
        }
        self._log(f"playerContent pid={pid[:80]}...")
        return {
            "parse": 0,
            "url": pid,
            "header": header,
        }

    # ==================== LOCAL PROXY ====================
    def localProxy(self, param):
        p = param if isinstance(param, dict) else {}
        u = str(p.get('url') or '')
        if not u:
            return [403, 'text/plain', b'', None]
        try:
            u = unquote(u)
        except Exception:
            pass
        u = u.replace('&amp;', '&')
        if u.startswith('//'):
            u = 'https:' + u

        try:
            r = self.session.get(u, headers=self.avatar_header, timeout=6, allow_redirects=True)
            if r.status_code < 400 and r.content:
                return [200, r.headers.get('Content-Type', 'image/jpeg'), r.content, None]
            self._log(f"  proxy {u} -> HTTP {r.status_code}", "WARN")
        except Exception as e:
            self._log(f"  proxy error {u}: {e}", "WARN")
        return [403, 'text/plain', b'', None]

    def removeHtmlTags(self, src):
        return re.sub(r'<[^>]+>', '', src)

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        try:
            self.session.close()
        except:
            pass
        try:
            self._probe_session.close()
        except:
            pass