# -*- coding: utf-8 -*-
# ᵀ⁴七五 —— 七五站族（www.qwfun.com 系）TVBox / 羊壳 Python 源 v1
# 站点画像：苹果CMS v10 + 自研 piankuwap 模板；分类 /vt/{tid}-{pg}.html；详情 /mv/{id}.html；
#           播放 /py/{vid}-{sid}-{nid}.html，页内 player_aaaa（encrypt=0）直出 m3u8 直链。
# 多域：默认 www.qwfun.com，域池含发布页登记的全部同站域名，任一域失败自动换下一域。
# vod_id 协议：详情用裸数字 id（508759）；播放 id 用相对路径（/py/508759-10-1.html），换域时无需改写。
# 搜索：站内 HTML 搜索被「系统安全验证」算术验证拦住，改走 /ajax/suggest JSON（返回 id/名称/封面）。
# 已知限制：分页只有「满页 +1 滑动窗口」这一条真来源（页尾窗口只列前后 5 页，拿不到总页数）。
# 站点实况：最新入库的片子常只挂磁力/网盘、暂无在线线路；这类条目线路为空，简介里会标注资源状态。
# 取证日期 2026-11-23，实测样本见工程目录 probe_qw/。

import json
import re
import socket
import time
from html import unescape
from urllib.parse import quote, unquote, urljoin

import requests
from base.spider import Spider

# 默认域：用户指定，也是发布页列表里实测最稳的一个
DEF_HOST = 'www.qwfun.com'

# 同站域名池：前 8 个来自用户给的数组，第 9 个来自发布页 check.js（实测同体量同站）
HOSTS = (
    'www.qwfun.com', 'www.qnnull.com', 'www.qwshow.com', 'www.qwmp4.com',
    'www.qwmkv.com', 'www.qwfilm.com', 'www.qnhot.com', 'www.qncool.com',
    'www.gmp4.com',
)

# 回家地址发布页：页面本身只是壳，域池写在 check.js 的 urlData 里
PUB_HOST = 'www.qn63.com'


class Spider(Spider):
    """七五站族源。所有网络请求都经过 _page/_raw 两条入口，便于统一冷却、换域与留痕。"""

    DEF_HOST = DEF_HOST
    HOSTS = HOSTS
    PUB_HOST = PUB_HOST
    # 移动端 UA：站点是手机模板，桌面 UA 会拿到另一套排版
    UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36')
    # 分类页每页实测 36 张卡
    LIMIT = 36
    TTL = 300          # 页面缓存 5 分钟，同一路径不重复抓
    COOL = 30          # 失败域名 / 失败路径冷却 30s，冷却期内直接跳过
    SEG_BYTES = 1900   # 单条 vod_play_url 的 UTF-8 字节上限（客户端 2048B 会截断）
    BUDGET = 14        # 单次取页墙钟预算，慢站不把首屏拖死
    MAX_PROBE = 10     # 域池候选上限，串行探太多域首屏必然超时
    # 站点真实一级目录（首页导航实测）：短剧 tid=30 不是连续编号，不能按 1..5 猜
    CATS = (('1', '电影'), ('2', '剧集'), ('3', '综艺'), ('4', '动漫'), ('30', '短剧'))
    # 手机上常见的本地代理端口，直连全失败时才探测（顺序按使用频率）
    PROXY_PORTS = (7890, 10809, 10808, 8118, 8889, 1080)

    # 类属性缓存：跨实例共享，init 里只做 setdefault 绑定，禁止重置清空
    _CACHE = {}
    _FAIL = {}
    _POOL = {}
    _DET = {}
    _MEDIA = {}
    _LOG = {}

    # ---------------------------------------------------------------- 生命周期

    # 初始化：解析 extend（host/hosts/proxy/diag/limit/imgProxy），绑定类属性缓存，建 session
    def init(self, extend=''):
        cfg = {}
        s = (extend or '').strip()
        if s.startswith('{'):
            try:
                cfg = json.loads(s)
            except Exception:
                cfg = {}
        elif s.startswith('http'):
            cfg = {'host': s}
        self.diag = bool(cfg.get('diag'))
        self.img_proxy = bool(cfg.get('imgProxy') or cfg.get('img'))
        self.proxy = str(cfg.get('proxy') or '').strip()
        try:
            self.limit = int(cfg.get('limit') or self.LIMIT)
        except Exception:
            self.limit = self.LIMIT
        self.hosts = self._seed_hosts(cfg)
        self._key = 'qw'
        self._CACHE = type(self)._CACHE.setdefault(self._key, {})
        self._FAIL = type(self)._FAIL.setdefault(self._key, {})
        self._POOL = type(self)._POOL.setdefault(self._key, {'last': '', 'ok': [], 'learn': 0})
        self._DET = type(self)._DET.setdefault(self._key, {})
        self._MEDIA = type(self)._MEDIA.setdefault(self._key, {})
        self._LOG = type(self)._LOG.setdefault(self._key, [])
        self._HEAD = {
            'User-Agent': self.UA,
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            # 必须显式只声明 gzip/deflate：不写这行 CF 会回 zstd，手机壳的 requests 多数解不了
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.6',
            'Cache-Control': 'no-cache',
        }
        self.session = requests.Session()
        self.session.headers.update(self._HEAD)
        # 关掉 trust_env：手机壳里的系统代理变量常把明文请求带歪，代理只认 extend/本地端口探测
        self.session.trust_env = False
        self._proxies = {'http': self.proxy, 'https': self.proxy} if self.proxy else None
        return None

    # 源名（壳端列表显示）
    def getName(self):
        return 'ᵀ⁴七五'

    # 域池种子：extend 指定的 host 优先，其次用户域名表，最后补发布页额外域，去重后截断
    def _seed_hosts(self, cfg):
        raw = []
        host = str(cfg.get('host') or '').strip()
        if host:
            raw.append(host)
        for h in (cfg.get('hosts') or []):
            raw.append(str(h or ''))
        raw.extend([self.DEF_HOST] + list(self.HOSTS))
        out = []
        for h in raw:
            h = self._norm_host(h)
            if h and h not in out:
                out.append(h)
            if len(out) >= self.MAX_PROBE:
                break
        return out or [self.DEF_HOST]

    # 域名规范化：去掉协议、路径与空白
    def _norm_host(self, h):
        h = str(h or '').strip()
        h = re.sub(r'^https?://', '', h, flags=re.I)
        h = h.split('/', 1)[0].split('?', 1)[0].strip().strip('.')
        return h if h and '.' in h else ''

    # ---------------------------------------------------------------- 六接口

    # 首页：分类走站点导航（nav 里 /vt/{tid}.html），视频走首页四块推荐卡
    def homeContent(self, filter):
        classes = self._classes()
        text = self._page('/', ref='/', ttl=self.TTL)
        vods = self._cards(text)[:60] if text else []
        if self.diag:
            classes = classes + [{'type_id': 'diag', 'type_name': '诊断'}]
        return {'class': classes, 'list': vods}

    # 首页推荐：与 homeContent 同源，单独返回一次列表（羊壳部分版本只调这个）
    def homeVideoContent(self):
        text = self._page('/', ref='/', ttl=self.TTL)
        return {'list': self._cards(text)[:60] if text else []}

    # 分类：/vt/{tid}.html 首屏、/vt/{tid}-{pg}.html 翻页；/ms/{tid}-…-.html 为同内容的筛选页第二形态
    def categoryContent(self, tid, pg, filter, extend):
        page = self._pg(pg)
        tid = str(tid or '').strip() or '1'
        if tid == 'diag':
            single = 1
            return {'page': single, 'pagecount': single, 'limit': single, 'total': single,
                    'list': [self._diag_vod()]}
        if page <= 1:
            paths = ['/vt/%s.html' % tid, '/ms/%s-----------.html' % tid]
        else:
            # 第二形态是 /vt/{tid}.html?page=N：站点原生翻页是 -N.html，?page 只在第一形态整批失败时兜底
            paths = ['/vt/%s-%s.html' % (tid, page), '/vt/%s.html?page=%s' % (tid, page)]
        text = self._multi(paths, ref='/vt/%s.html' % tid, ttl=120)
        vods = self._cards(text) if text else []
        pc = page
        if len(vods) >= self.limit:
            # 满页 +1 滑动窗口：页尾只列前后 5 页，站点没暴露总页数，这是唯一真来源
            pc = page + 1
        if pc < page:
            pc = page
        return {'page': page, 'pagecount': pc, 'limit': self.limit,
                'total': len(vods), 'list': vods}

    # 详情：一次请求解析整页（线路面板与选集同页，不逐线路再拉）
    def detailContent(self, ids):
        vid = self._vid(ids)
        if not vid:
            return {'list': []}
        vod, lines = self._detail(vid)
        if not vod:
            return {'list': []}
        froms, urls = [], []
        for label, eps in lines:
            if not eps:
                continue
            body = '#'.join('%s$%s' % (name, path) for name, path in eps)
            for sub_label, sub_body in self._seg(label, body):
                froms.append(sub_label)
                urls.append(sub_body)
        vod['vod_play_from'] = '$$$'.join(froms)
        vod['vod_play_url'] = '$$$'.join(urls)
        if not froms:
            # 新片常常只挂了磁力/网盘、还没有在线线路：把资源状态写进简介，避免用户点进去一头雾水
            hint = self._res_hint(vod.get('vod_id'))
            if hint:
                vod['vod_content'] = (vod.get('vod_content') or '') + '｜' + hint
        return {'list': [vod]}

    # 搜索：/ajax/suggest?mid=1&wd= 返回 JSON（id/name/pic），单项即可拼详情链接；单页结果本地切片
    def searchContent(self, key, quick, pg='1'):
        page = self._pg(pg)
        q = str(key or '').strip()
        if not q:
            single = 1
            return {'page': single, 'pagecount': single, 'limit': self.limit, 'total': 0, 'list': []}
        paths = ['/ajax/suggest?mid=1&wd=%s&limit=60' % quote(q),
                 '/index.php/ajax/suggest?mid=1&wd=%s' % quote(q),
                 '/vs/-------------.html?wd=%s' % quote(q)]
        vods = []
        text = self._multi(paths, ref='/', ttl=120)
        if text:
            data = self._json(text)
            if isinstance(data, dict):
                for it in (data.get('list') or []):
                    vid = str(it.get('id') or it.get('vod_id') or '').strip()
                    if not vid:
                        continue
                    vods.append({'vod_id': vid,
                                 'vod_name': self._clean(it.get('name') or it.get('vod_name') or ''),
                                 'vod_pic': self._pic(it.get('pic') or ''),
                                 'vod_remarks': ''})
            if not vods:
                # 第三形态是 HTML 搜索页：命中「系统安全验证」时拿不到结果，按空返回处理
                vods = self._cards(text)
        total = len(vods)
        start = (page - 1) * self.limit
        part = vods[start:start + self.limit]
        pc = 1
        if total > self.limit:
            pc = (total + self.limit - 1) // self.limit
        return {'page': page, 'pagecount': pc, 'limit': self.limit, 'total': total, 'list': part}

    # 播放：取播放页 player_aaaa，拿直链并验真；该线路死了就按同片其它线路自动回退
    def playerContent(self, flag, id, vipFlags):
        raw = str(id or '').strip()
        m = re.search(r'(\d+)-(\d+)-(\d+)', raw)
        head = json.dumps({'User-Agent': self.UA, 'Referer': 'https://%s/' % self._host_hint()})
        if not m:
            return {'parse': 1, 'jx': 0, 'url': raw, 'playUrl': '', 'header': head}
        vid, sid, nid = m.group(1), m.group(2), m.group(3)
        # 候选顺序：用户点的这条 → 同片其它线路首集（老资源直链会 404，自动换线比黑屏好）
        cand = [self._play_path(vid, sid, nid)]
        lines = (self._DET.get(vid) or {}).get('lines') or []
        for label, eps in lines:
            for name, path in eps:
                if path not in cand:
                    cand.append(path)
        cand = cand[:5]
        first_url = ''
        deadline = time.time() + self.BUDGET
        for path in cand:
            if time.time() > deadline:
                break
            text = self._page(path, ref='/mv/%s.html' % vid, ttl=120)
            url = self._player_url(text)
            if not url:
                continue
            if not first_url:
                first_url = url
            if self._media_ok(url):
                return {'parse': 0, 'jx': 0, 'url': url, 'playUrl': '', 'header': head}
        if first_url:
            # 直链存在但本轮没验通（多为手机网络抖动）：仍按直链给壳，日志留痕
            self._log('播放未验证 %s' % first_url[-42:])
            return {'parse': 0, 'jx': 1, 'url': first_url, 'playUrl': '', 'header': head}
        return {'parse': 1, 'jx': 0, 'url': raw, 'playUrl': '', 'header': head}

    # ---------------------------------------------------------------- 取页与域池

    # 多形态取页：同一资源的若干路径形态依次试，每条形态内部再走域池
    def _multi(self, paths, ref='', ttl=None):
        for path in paths:
            text = self._page(path, ref=ref, ttl=ttl)
            if text:
                return text
        return ''

    # 取页主入口：缓存 → 冷却判断 → 域池逐域 → 全失败留痕
    def _page(self, path, ref='', ttl=None, force=False):
        ttl = self.TTL if ttl is None else ttl
        now = time.time()
        hit = self._CACHE.get(path)
        if hit and not force and now - hit[0] < ttl:
            return hit[1]
        deadline = now + self.BUDGET
        for url in self._urls(path):
            if time.time() > deadline:
                break
            host = self._host_of(url)
            if self._cooling(host):
                continue
            code, text = self._pull(url, ref)
            if code == 200 and text:
                text = self._unwrap(text)
                if len(self._CACHE) > 240:
                    self._CACHE.clear()
                self._CACHE[path] = (time.time(), text)
                self._POOL['last'] = host
                if host not in self._POOL['ok']:
                    self._POOL['ok'].append(host)
                return text
            self._mark_bad(host, code)
            # 换域之间留半秒间隔：站点前置 Cloudflare，同 IP 高频跨域请求容易吃 403
            time.sleep(0.5)
        if not self._proxies and len(self._POOL.get('ok') or []) == 0:
            # 一圈域都没通：手机壳里常见的本地代理再试一次，避免直接判死
            self._pick_proxy()
        self._log('取页失败 %s' % path[:60])
        return ''

    # 候选 URL 序列：好域优先，https 全部失败后才轮同域明文 http（个别网络只放行 80）
    def _urls(self, path):
        if not path.startswith('/'):
            path = '/' + path
        hosts = self._order_hosts()
        out = ['https://%s%s' % (h, path) for h in hosts]
        for h in hosts[:3]:
            out.append('http://%s%s' % (h, path))
        return out

    # 域顺序：上次成功域置顶，其次已探活域，其余按种子顺序（换域只在失败路径发生）
    def _order_hosts(self):
        last = self._POOL.get('last') or ''
        ok = list(self._POOL.get('ok') or [])
        rest = [h for h in self.hosts if h not in ok]
        order = ([last] if last in self.hosts else []) + [h for h in ok if h != last] + rest
        return order[:self.MAX_PROBE] or [self.DEF_HOST]

    # 单次请求：显式 timeout、proxies、verify=False；非 200 视为该域失败
    def _pull(self, url, ref=''):
        head = dict(self._HEAD)
        head['Referer'] = ref if ref and ref.startswith('http') else ('https://%s/' % self._host_of(url))
        try:
            r = self.session.get(url, headers=head, timeout=(6, 12), verify=False,
                                 allow_redirects=True, proxies=self._proxies)
            data = r.content or b''
            data = self._inflate(data, r.headers.get('Content-Type') or '')
            if r.status_code != 200 or not data:
                self._note('%s -> %s' % (self._short(url), r.status_code))
                return r.status_code, ''
            return 200, self._decode(data, r.headers.get('Content-Type') or '')
        except Exception as e:
            self._note('%s -> %s' % (self._short(url), type(e).__name__))
            return 0, ''

    # 二进制取流（封面、m3u8、片段都走这里）：与 _pull 同参数，只差不解码
    def _raw(self, url, ref='', timeout=10):
        head = dict(self._HEAD)
        head['Accept'] = '*/*'
        head['Referer'] = ref or ('https://%s/' % self._host_of(url))
        try:
            r = self.session.get(url, headers=head, timeout=(5, timeout), verify=False,
                                 allow_redirects=True, proxies=self._proxies)
            data = self._inflate(r.content or b'', r.headers.get('Content-Type') or '')
            return r.status_code, (r.headers.get('Content-Type') or ''), data
        except Exception as e:
            self._note('%s -> %s' % (self._short(url), type(e).__name__))
            return 0, '', b''

    # 解压兜底：gzip / deflate / zstd 三种压缩体都尽量还原成明文
    def _inflate(self, data, ctype):
        if not data:
            return data
        if data[:2] == b'\x1f\x8b':
            try:
                import gzip
                return gzip.decompress(data)
            except Exception:
                return bytes(data)
        if data[:4] == b'\x28\xb5\x2f\xfd':
            # 该站族前置 CF 会按 Accept-Encoding 回 zstd；明文取页已声明 gzip，这里只做兜底
            out = self._unzstd(data)
            if not out:
                self._log('zstd 压缩体无法解压')
            return out
        if 'deflate' in (ctype or '').lower():
            try:
                import zlib
                return zlib.decompressobj(-15).decompress(data)
            except Exception:
                return bytes(data)
        return data

    # zstd 解压：先试 zstandard 模块，再 ctypes 直调 libzstd（安卓壳里模块常缺、库常在）
    def _unzstd(self, data):
        try:
            import zstandard
            return zstandard.ZstdDecompressor().decompress(data, max_output_size=16 << 20)
        except Exception:
            pass
        try:
            import ctypes
            import ctypes.util
            lib = None
            for name in ('libzstd.so', 'libzstd.so.1', ctypes.util.find_library('zstd') or ''):
                if not name:
                    continue
                try:
                    lib = ctypes.CDLL(name)
                    break
                except Exception:
                    continue
            if lib is None:
                return b''
            lib.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
            size = int(lib.ZSTD_getFrameContentSize(data, len(data)))
            if size <= 0 or size > (16 << 20):
                size = 4 << 20
            buf = ctypes.create_string_buffer(size)
            lib.ZSTD_decompress.restype = ctypes.c_size_t
            got = int(lib.ZSTD_decompress(buf, size, data, len(data)))
            if got <= 0 or got > size:
                return b''
            return buf.raw[:got]
        except Exception:
            return b''

    # 编码判定：站点 charset=utf-8，这里只兜 utf-8/gbk 两种，避免乱码
    def _decode(self, data, ctype):
        for enc in ('utf-8', 'gb18030'):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode('utf-8', 'ignore')

    # 去壳：极少数情况下（Accept 头被改成 JSON 优先）站点会把整页 HTML 塞进 JSON 字符串返回
    def _unwrap(self, text):
        s = str(text or '').strip()
        if len(s) > 2 and s[0] == '"' and s[-1] == '"' and '\\u' in s[:400]:
            try:
                v = json.loads(s)
                if isinstance(v, str) and '<' in v:
                    return v
            except Exception:
                return text
        return text

    # 冷却登记：连续失败 2 次的域进冷却，避免整页在坏域上反复重试
    def _mark_bad(self, host, code):
        rec = self._FAIL.get(host) or {'n': 0, 'ts': 0}
        rec['n'] = int(rec.get('n') or 0) + 1
        if rec['n'] >= 2 or code == 403:
            rec['ts'] = time.time()
        self._FAIL[host] = rec
        self._log('坏域 %s(%s)' % (host, code or '-'))

    # 冷却判断：30s 内不再碰这个域
    def _cooling(self, host):
        rec = self._FAIL.get(host) or {}
        ts = float(rec.get('ts') or 0)
        return bool(ts) and time.time() - ts < self.COOL

    # 事件日志：只留最近 18 条，诊断卡直接读
    def _log(self, msg):
        try:
            self._LOG.append('%s %s' % (time.strftime('%H:%M:%S'), msg))
            del self._LOG[:-18]
        except Exception:
            pass

    # 简短备注：只进日志，不打印
    def _note(self, msg):
        self._log(msg)

    # URL 取域
    def _host_of(self, url):
        m = re.match(r'https?://([^/]+)/?', str(url or ''), re.I)
        return m.group(1).lower() if m else ''

    # 取域（日志/头信息用）：优先上次成功域
    def _host_hint(self):
        return self._POOL.get('last') or self.DEF_HOST

    # 缩短 URL 便于日志阅读
    def _short(self, url):
        u = re.sub(r'https?://', '', str(url or ''), flags=re.I)
        return u[:56]

    # 本地代理探测：直连连续失败时，试常见本地端口（壳端自带 clash/v2ray 很常见）
    def _pick_proxy(self):
        if self._proxies:
            return self._proxies
        for port in self.PROXY_PORTS:
            try:
                s = socket.create_connection(('127.0.0.1', port), timeout=1)
                s.close()
                p = 'http://127.0.0.1:%d' % port
                self._proxies = {'http': p, 'https': p}
                self.session = requests.Session()
                self.session.headers.update(self._HEAD)
                self.session.trust_env = False
                self._log('本地代理 %s' % p)
                return self._proxies
            except Exception:
                continue
        return None

    # ---------------------------------------------------------------- 解析

    # 分类导航：从首页 nav 的 /vt/{tid}.html 取真实目录，抓不到就用实测兜底表
    def _classes(self):
        hit = self._CACHE.get('classes')
        if hit and time.time() - hit[0] < 86400:
            return hit[1]
        text = self._page('/', ref='/', ttl=self.TTL)
        out, seen = [], set()
        for tid, name in re.findall(r'href="/vt/(\d+)\.html"[^>]*>([^<]{1,12})<', text or ''):
            name = self._clean(name)
            if not name or tid in seen or name in ('留言',):
                continue
            seen.add(tid)
            out.append({'type_id': tid, 'type_name': name})
        if len(out) < 3:
            out = [{'type_id': t, 'type_name': n} for t, n in self.CATS]
        self._CACHE['classes'] = (time.time(), out)
        return out

    # 卡片解析：以 /mv/{id}.html 为锚，首页 a.pic+a.tit 与分类页 article 两套排版共用一条路
    def _cards(self, text, base=''):
        text = str(text or '')
        if not text:
            return []
        out, seen = [], set()
        for m in re.finditer(r'<a[^>]*href="/mv/(\d+)\.html"[^>]*>', text):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            tag = m.group(0)
            body = text[m.start():m.start() + 700]
            name = ''
            t = re.search(r'title="([^"]{1,80})"', tag)
            if t:
                name = unescape(t.group(1)).strip()
            if not name:
                t = re.search(r'<a[^>]*class="tit"[^>]*>(.*?)</a>', body, re.S)
                if t:
                    # 轮播卡的 a.tit 里带 <span class="indicator-info"><em>1</em>/6</span> 轮播序号，先摘掉再取标题
                    name = self._clean(re.sub(r'<span class="indicator-info".*?</span>', '', t.group(1), flags=re.S))
            if not name:
                t = re.search(r'<h3[^>]*>(.*?)</h3>', body, re.S)
                if t:
                    name = self._clean(t.group(1))
            if not name:
                name = '影片%s' % vid
            pic = ''
            t = re.search(r'<img[^>]+src="([^"]+)"', body)
            if t:
                pic = t.group(1)
            if not pic:
                pre = text[max(0, m.start() - 220):m.start()]
                t = re.search(r'<img[^>]+src="([^"]+)"', pre)
                if t:
                    pic = t.group(1)
            remarks = ''
            t = re.search(r'<span class="s1"[^>]*>(.*?)</span>', body, re.S)
            if t:
                remarks = self._clean(t.group(1))
            out.append({'vod_id': vid, 'vod_name': name, 'vod_pic': self._pic(pic),
                        'vod_remarks': remarks[:16]})
        return out

    # 详情解析（带 5 分钟缓存）：同片详情给播放回退用，lines 一并缓存
    def _detail(self, vid):
        hit = self._DET.get(vid)
        if hit and time.time() - hit['ts'] < self.TTL:
            return hit['vod'], hit['lines']
        text = self._page('/mv/%s.html' % vid, ref='/', ttl=self.TTL)
        if not text or ('/py/' not in text and '<h1' not in text):
            return {}, []
        vod = self._vod_fields(text, vid)
        lines = self._lines(text, vid)
        self._DET[vid] = {'ts': time.time(), 'vod': vod, 'lines': lines}
        if len(self._DET) > 120:
            self._DET.clear()
        return vod, lines

    # 详情字段：h1 取名称/年份，info 区取状态/导演/主演/类型/地区，简介取 meta description
    def _vod_fields(self, text, vid):
        # 模板里大量 <!-- --> 注释夹在信息点中间（导演/地区/类型都被夹过），先整体摘掉再解析
        text = re.sub(r'<!--.*?-->', '', text, flags=re.S)

        def para(kw, span=700):
            i = text.find(kw)
            if i < 0:
                return ''
            j = text.find('</p>', i)
            return text[i:(j if j > i else i + span)]

        h1 = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
        raw_name = self._clean(h1.group(1)) if h1 else ''
        year = ''
        if h1:
            # 年份藏在 h1 里的 <span class="year"> (2026)</span>，在原始片段里取四位数字
            t = re.search(r'\b(19|20)\d{2}\b', h1.group(1))
            if t:
                year = t.group(0)
        raw_name = re.sub(r'[（(]\s*[0-9]{4}\s*[)）]', '', raw_name).strip() or ('影片%s' % vid)
        pic = ''
        t = re.search(r'<div class="img">.*?<img[^>]+src="([^"]+)"', text, re.S)
        if t:
            pic = t.group(1)
        if not pic:
            t = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|png|webp))"', text)
            if t:
                pic = t.group(1)
        remarks = ''
        t = re.search(r'状态[：:]\s*</span>(.*?)</p>', text, re.S)
        if t:
            remarks = self._clean(t.group(1)).split(' ')[0][:12]

        # 导演/主演各占一个 <p>，只在段内取 <a> 文本，避免把下面主演串进导演
        def names(kw):
            seg = para(kw)
            items = [self._clean(x) for x in re.findall(r'<a[^>]*>(.*?)</a>', seg, re.S)]
            items = [x for x in items if x and len(x) <= 24]
            return ' / '.join(items[:12])

        def tag_value(kw):
            seg = para(kw, 300)
            if not seg:
                return ''
            v = re.sub(r'<[^>]+>', ' ', seg).replace('\u00a0', ' ').replace('&nbsp;', ' ')
            v = re.sub(r'^(导演|编剧|主演|类型|地区|年份|语言|时长|状态|别名|简介)\s*[：:]\s*', '', v.strip())
            items = [x.strip() for x in re.split(r'[ /、，]+', v) if x.strip()]
            return ','.join(items[:6])

        area = tag_value('地区：')
        kind = tag_value('类型：')
        content = ''
        t = re.search(r'<meta name="description" content="([^"]*)"', text)
        if t:
            content = unescape(t.group(1)).strip()
            if '剧情' in content:
                content = content.split('剧情', 1)[1].lstrip('：: ')
        return {'vod_id': str(vid), 'vod_name': raw_name, 'vod_pic': self._pic(pic),
                'vod_year': year, 'vod_area': area, 'vod_type': kind,
                'vod_remarks': remarks,
                'vod_actor': names('主演：'),
                'vod_director': names('导演：'),
                'vod_content': content}

    # 线路面板：select 的 option 顺序与 li[style=display] 分块一一对应，块内 a 即选集
    def _lines(self, text, vid):
        opts = [self._clean(x) for x in re.findall(r'<option[^>]*>(.*?)</option>', text, re.S)]
        opts = [re.sub(r'[（(]\d+[)）]$', '', o).strip() for o in opts if o and o.strip()]
        lines = []
        chunks = str(text).split('<li style="display:')
        for idx, chunk in enumerate(chunks[1:]):
            eps = []
            for sid, nid, name in re.findall(
                    r'/py/%s-(\d+)-(\d+)\.html"[^>]*>(.*?)</a>' % vid, chunk, re.S):
                label = self._clean(name) or ('第%s集' % nid)
                eps.append((label, self._play_path(vid, sid, nid)))
            if not eps:
                continue
            raw = opts[idx] if idx < len(opts) else ''
            label = raw or ('线路%d' % (len(lines) + 1))
            lines.append((label, eps))
        if not lines:
            # 兜底：面板切分失效时按 sid 分组直取全部 /py/ 链接
            pool = {}
            for sid, nid, name in re.findall(r'/py/%s-(\d+)-(\d+)\.html"[^>]*>(.*?)</a>' % vid, text, re.S):
                pool.setdefault(sid, []).append((self._clean(name) or ('第%s集' % nid),
                                                 self._play_path(vid, sid, nid)))
            for sid in sorted(pool, key=lambda x: int(x)):
                lines.append(('线路%d' % (len(lines) + 1), pool[sid]))
        # 线路重名去重：同名加序号，保证 froms 段不重复
        out, seen = [], {}
        for label, eps in lines:
            label = re.sub(r'[\s\xa0]+', '', label)[:12] or '线路'
            if label in seen:
                seen[label] += 1
                label = '%s%d' % (label, seen[label])
            else:
                seen[label] = 1
            out.append((label, eps))
        return out[:14]

    # 1900B 分段：客户端单条 play_url 超 2048B 会截断，长剧必须切段并加 (1)(2)
    def _seg(self, label, body):
        eps = [x for x in str(body or '').split('#') if x.strip()]
        chunks, cur, size = [], [], 0
        for seg in eps:
            b = len(seg.encode('utf-8')) + 1
            if cur and size + b > self.SEG_BYTES:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(seg)
            size += b
        if cur:
            chunks.append(cur)
        if len(chunks) <= 1:
            return [(label, body)]
        return [('%s(%d)' % (label, i + 1), '#'.join(c)) for i, c in enumerate(chunks)]

    # 播放页取直链：player_aaaa 的 url 字段；encrypt 非 0 先按 base64 解一层
    def _player_url(self, text):
        if not text:
            return ''
        m = re.search(r'player_aaaa\s*=\s*\{', text) or re.search(r'player_data\s*=\s*\{', text)
        if not m:
            return ''
        raw = self._brace(text, text.find('{', m.end() - 1))
        if not raw:
            return ''
        data = self._json(raw)
        if not isinstance(data, dict):
            return ''
        url = str(data.get('url') or '').strip().replace('\\/', '/')
        if not url.startswith('http'):
            return ''
        if str(data.get('encrypt') or '0') not in ('0', '', 'None'):
            url = self._b64(url)
        if not url.startswith('http'):
            return ''
        return url

    # 括号配平取 JSON 原文：播放配置里有转义引号，正则截取会切坏
    def _brace(self, text, start):
        depth, quote_ch, esc = 0, '', False
        for i in range(start, len(text)):
            ch = text[i]
            if quote_ch:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == quote_ch:
                    quote_ch = ''
                continue
            if ch in '"\'':
                quote_ch = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return ''

    # base64 兜底解码（encrypt=1/2 的站常见，本站在用 0）
    def _b64(self, s):
        try:
            import base64
            raw = base64.b64decode(str(s) + '=' * (-len(str(s)) % 4))
            t = raw.decode('utf-8', 'ignore')
            return t if t.startswith('http') else str(s)
        except Exception:
            return str(s)

    # JSON 宽松解析：先直解，失败再去掉首尾杂字符
    def _json(self, text):
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r'\{.*\}', str(text or ''), re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None

    # 直链验真：m3u8 认 #EXTM3U，mp4 认 ftyp/视频 MIME；结果缓存 5 分钟避免重复拉清单
    def _media_ok(self, url):
        now = time.time()
        hit = self._MEDIA.get(url)
        if hit and now - hit[0] < self.TTL:
            return hit[1]
        code, ctype, data = self._raw(url, timeout=9)
        good = False
        if code in (200, 206) and data:
            head = data[:2048]
            low = (ctype or '').lower()
            if b'#EXTM3U' in head or b'ftyp' in data[:64] or 'mpegurl' in low or 'video/' in low:
                good = True
        self._MEDIA[url] = (now, good)
        if len(self._MEDIA) > 200:
            self._MEDIA.clear()
        if not good:
            self._log('直链不可用 %s(%s)' % (url[-40:], code))
        return good

    # 播放相对路径：换域时只用相对路径，壳端无需重写域名
    def _play_path(self, vid, sid, nid):
        return '/py/%s-%s-%s.html' % (vid, sid, nid)

    # 资源状态提示：无在线线路的条目统计磁力/网盘数量，写进简介让用户知道该片只有下载
    def _res_hint(self, vid):
        text = self._page('/mv/%s.html' % vid, ref='/', ttl=self.TTL)
        if not text:
            return ''
        magnet = text.count('magnet:?')
        ed2k = text.count('ed2k://')
        pans = []
        for name, kw in (('百度', 'pan.baidu.com'), ('夸克', 'pan.quark.cn'),
                         ('迅雷', 'pan.xunlei.com'), ('阿里', 'aliyundrive.com')):
            if kw in text:
                pans.append(name)
        bits = []
        if magnet:
            bits.append('磁力 %d 条' % magnet)
        if ed2k:
            bits.append('电驴 %d 条' % ed2k)
        if pans:
            bits.append('网盘 ' + '/'.join(pans))
        if not bits:
            return ''
        return '该片暂无在线线路，站内提供：' + '、'.join(bits) + '（需网盘/下载工具）'

    # vod_id 归一：接受 list、裸数字、带 /mv/ 或 -sid-nid 的各种写法
    def _vid(self, ids):
        raw = ids
        if isinstance(ids, (list, tuple)):
            raw = ids[0] if ids else ''
        raw = str(raw or '').strip()
        m = re.search(r'(\d{3,})', raw)
        return m.group(1) if m else ''

    # 页码归一：非法/负数/空都回到 1
    def _pg(self, pg):
        try:
            page = int(str(pg).strip())
        except Exception:
            page = 1
        return page if page > 0 else 1

    # 文本清洗：去标签、还原实体、压空白
    def _clean(self, s):
        s = re.sub(r'<[^>]+>', ' ', str(s or ''))
        s = unescape(s).replace('\u00a0', ' ')
        return re.sub(r'\s+', ' ', s).strip()

    # 封面补全 + 可选本地代理（壳端直连不了 i1.vvmp4.com 时用 extend {"imgProxy":1}）
    def _pic(self, p):
        p = str(p or '').strip()
        if not p:
            return ''
        if p.startswith('//'):
            p = 'https:' + p
        elif p.startswith('/'):
            p = 'https://' + self._host_hint() + p
        elif not p.startswith('http'):
            return ''
        if self.img_proxy and 'vvmp4.com' in p:
            return self._proxy_base() + '?do=img&url=' + quote(p, '')
        return p

    # 本地代理前缀：优先壳端 Proxy.getUrl，拿不到就退回 9978
    def _proxy_base(self):
        try:
            from com.github.catvod import Proxy as JProxy
            u = JProxy.getUrl(True)
            if u:
                return str(u)
        except Exception:
            pass
        return 'http://127.0.0.1:9978/proxy'

    # 图片/m3u8 代理：返回真实 MIME 与二进制，空 body 一律 404，绝不回 200 空图
    def localProxy(self, param):
        text = str(param or '')
        m = re.search(r'(?:^|[?&])url=([^&]+)', text)
        if not m:
            return [404, 'text/plain', b'']
        url = unquote(m.group(1))
        if not url.startswith('http'):
            return [404, 'text/plain', b'']
        code, ctype, data = self._raw(url, timeout=12)
        if code not in (200, 206) or not data:
            return [404, 'text/plain', b'']
        if 'do=m3u8' in text or data[:7] == b'#EXTM3U':
            body = self._abs_playlist(data.decode('utf-8', 'ignore'), url).encode('utf-8')
            return [200, 'application/vnd.apple.mpegurl', body]
        low = (ctype or '').lower()
        if 'do=img' in text or low.startswith('image/'):
            if not (data[:2] in (b'\xff\xd8', b'\x89P') or data[:3] == b'GIF' or data[:4] == b'RIFF'):
                return [404, 'text/plain', b'']
            return [200, ctype or 'image/jpeg', data]
        return [200, ctype or 'application/octet-stream', data]

    # m3u8 绝对化：把相对的分片/密钥地址补成绝对 URL，避免壳端按错基址取流
    def _abs_playlist(self, text, base_url):
        out = []
        for line in str(text or '').splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith('#'):
                if 'URI="' in s:
                    a = s.split('URI="', 1)[1].split('"', 1)[0]
                    s = s.replace('URI="%s"' % a, 'URI="%s"' % urljoin(base_url, a))
                out.append(s)
                continue
            out.append(urljoin(base_url, s))
        return '\n'.join(out)

    # 诊断卡：用户手机壳出问题时，把域池/冷却/日志摊开，一眼看出是域挂了还是解析挂了
    def _diag_vod(self):
        cooling = [h for h in self.hosts if self._cooling(h)]
        ok = self._POOL.get('ok') or []
        last = self._POOL.get('last') or '-'
        state = '正常' if (ok or last != '-') else '未连通'
        tip = '直连可用' if not self.proxy else ('已用代理 %s' % self.proxy)
        body = '｜'.join([
            '①状态 %s' % state,
            '②当前域 %s' % last,
            '③域池 %d 个（已通 %s）' % (len(self.hosts), '/'.join(ok) if ok else '无'),
            '④冷却 %s' % ('/'.join(cooling) if cooling else '无'),
            '⑤缓存 %d 页 / 详情 %d / 直链 %d' % (len(self._CACHE), len(self._DET), len(self._MEDIA)),
            '⑥%s' % tip,
            '⑦最近事件 ' + ('；'.join(self._LOG[-5:]) if self._LOG else '无'),
        ])
        self._log('诊断卡输出')
        return {'vod_id': 'diag', 'vod_name': '诊断·七五源', 'vod_pic': '',
                'vod_remarks': state, 'vod_type': '诊断', 'vod_content': body,
                'vod_play_from': '', 'vod_play_url': ''}
