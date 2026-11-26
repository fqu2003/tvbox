# -*- coding: utf-8 -*-
# ᵀ⁴星帆 —— 星帆影视（www.xingfan.cc）TVBox / 羊壳 Python 源 v1
#
# 站点画像（2026-11-23 实测，样本见工程目录 probe_xf/）：
#   自研主题影视站（/tpl/meiju/，Alpine.js + 自研 proto-*/rim-card 类名），后端是 ThinkPHP 风格 ?s=/home/...
#   路由：分类 /{拼音目录}/、翻页 /{拼音目录}/index-{n}.html（尾页在页尾真实给出，如 index-391.html）
#         详情 /{拼音目录}/{slug}/、播放 /{拼音目录}/{slug}/{sid}-{nid}.html
#         搜索 GET /search/?wd={关键词}（另有 /search/{关键词}.html 形态）
#   播放链路：播放页 → `var zanpiancms_player = {...}` → src = apiurl + url（赞片CMS 播放器壳）
#             → 该壳页返回 YunPlayer HTML，内含 4 条 m3u8（不同上游 CDN），全部实测 #EXTM3U。
#
# vod_id 协议：详情用相对路径（/oumeiju/xxx/），播放用相对播放页路径（/oumeiju/xxx/1-1.html）。
#              换域时不需改写任何 id，这是多域设计的核心。
#
# 已知限制：
#   1) 站点只挂磁力/网盘、尚未上在线线路的新片，详情页播放列表为空（例：/oumeiju/boxijiekexundisanji/），
#      这类条目本源返回空线路，并在简介里标注「暂无在线播放」，不拿磁力链冒充可播地址。
#   2) 播放页偶发 500（PHP 报错，170B 空壳），必须重试；本源在 _play_page 里做 3 次重试 + 路径级冷却。
#   3) 该站没有公开发布页/回家里地址：https 变体（.com/.cn/.tv/.top/.vip/.xyz、m.xingfan.cc）全部不通，
#      页脚唯一外链 kunluntv.net 是另一套站（1475B 跳转壳，assets 指向 ddl.qpqzw.cn），
#      xingfan.me 虽叫"星帆影视"但模板/路由都不同（同 slug 详情 404），都不能当备用域。
#      所以域池只有 www.xingfan.cc 与裸域两种形态；换域能力保留（冷却 + 成功域置顶 + 页内新域双判学习 +
#      extend={"hosts":[...]} 手工加域），站点哪天换域名并在页面上留下新地址，这里会自动收进来。

import json
import re
import time
from html import unescape
from urllib.parse import quote, urljoin

import requests
from base.spider import Spider

# 默认域：用户指定，实测 200 / 184KB / 1.2s
DEF_HOST = 'www.xingfan.cc'

# 同站域名形态：带 www 与裸域都能直出同一套页面（实测两者 title 都是「星帆影视」、都带 /tpl/meiju/）。
# 只放实测过的两个，不塞没验证的猜测域名——猜错域只会让首屏白等超时。
HOSTS = (
    'www.xingfan.cc',
    'xingfan.cc',
)

# 播放壳兜底：播放页里的 apiurl 正常会自带，这里留一份实测值，页面结构变动时还能拼出地址
PLAY_API = 'https://php.playerla.com/mjplay/?id='


class Spider(Spider):
    """星帆影视源。所有页面请求都走 _page 一条入口，便于统一超时、冷却、换域与留痕。"""

    DEF_HOST = DEF_HOST
    HOSTS = HOSTS
    PLAY_API = PLAY_API
    # 手机 UA：站点是移动优先模板，桌面 UA 会拿到另一套（更重的）排版
    UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36')
    # 分类页每页实测 24 张卡（/oumeiju/ 200 / 125KB，24 卡 + 页尾页码）
    LIMIT = 24
    TTL = 300          # 页面缓存 5 分钟：首屏 + 推荐区会撞同一路径
    COOL = 30          # 失败域名 30s 冷却，冷却期内直接跳过，避免整页卡死重试
    SEG_BYTES = 1900   # 单条 vod_play_url 的 UTF-8 字节上限（客户端 2048B 会截断）
    BUDGET = 14        # 单次取页墙钟预算，慢站不把首屏拖死
    PLAY_TRY = 3       # 播放页 500 重试次数（实测首次请求约三成概率 500）
    # 站点导航里有 19 个拼音目录，但其中 xianggangju（香港剧）、donghuapian（动画片）、zongyi（综艺）
    # 的列表页实测只有 50~54KB 且 0 张卡（栏目空置占位），这里不暴露——空分类在客户端点进去就是白屏。
    CATS = (
        ('guocanju', '国产剧'), ('oumeiju', '欧美剧'),
        ('ribenju', '日本剧'), ('haiwaiju', '海外剧'), ('taiwanju', '台湾剧'),
        ('hanguoju', '韩国剧'), ('taiguoju', '泰国剧'), ('dongzuopian', '动作片'),
        ('xijupian', '喜剧片'), ('aiqingpian', '爱情片'), ('kehuanpian', '科幻片'),
        ('kongbupian', '恐怖片'), ('zhanzhengpian', '战争片'), ('juqingpian', '剧情片'),
        ('jilupian', '纪录片'), ('dongman', '动漫'),
    )
    # 手机上常见的本地代理端口，直连全失败时才探测（顺序按使用频率）
    PROXY_PORTS = (7890, 10809, 10808, 8118, 8889, 1080)

    # 类属性缓存：跨实例共享，init 里只做 setdefault 绑定，禁止重置清空
    _CACHE = {}
    _FAIL = {}
    _PF = {}
    _LEARN = {}
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
        self._key = 'xf'
        # 运行时学到的备用域放类属性，跨实例保留（换域后客户端重启仍记得新域）
        self._LEARN = type(self)._LEARN.setdefault(self._key, [])
        for h in self._LEARN:
            if h not in self.hosts and len(self.hosts) < 8:
                self.hosts.append(h)
        self._CACHE = type(self)._CACHE.setdefault(self._key, {})
        self._FAIL = type(self)._FAIL.setdefault(self._key, {})
        self._PF = type(self)._PF.setdefault(self._key, {})
        self._POOL = type(self)._POOL.setdefault(self._key, {'last': '', 'ok': [], 'bad': []})
        self._DET = type(self)._DET.setdefault(self._key, {})
        self._MEDIA = type(self)._MEDIA.setdefault(self._key, {})
        self._LOG = type(self)._LOG.setdefault(self._key, [])
        self._HEAD = {
            'User-Agent': self.UA,
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            # 必须显式只声明 gzip/deflate：不写这行前置 CDN 可能回 zstd，手机壳的 requests 多数解不了
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
        return 'ᵀ⁴星帆'

    # 域池种子：extend 指定的 host 优先，其次 extend.hosts，最后补内置实测域
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
        return out or [self.DEF_HOST]

    # 域名规范化：去掉协议、路径与空白
    def _norm_host(self, h):
        h = str(h or '').strip()
        h = re.sub(r'^https?://', '', h, flags=re.I)
        h = h.split('/', 1)[0].split('?', 1)[0].strip().strip('.')
        return h if h and '.' in h else ''

    # ---------------------------------------------------------------- 六接口

    # 首页：分类走站点导航（19 个真实拼音目录），视频走首页推荐卡（rim-card）
    def homeContent(self, filter):
        classes = [{'type_id': t, 'type_name': n} for t, n in self.CATS]
        if self.diag:
            classes = classes + [{'type_id': 'diag', 'type_name': '诊断'}]
        text = self._page('/', ref='/', ttl=self.TTL)
        vods = self._cards(text)[:60] if text else []
        return {'class': classes, 'list': vods}

    # 首页推荐：与 homeContent 同源，单独返回一次列表（羊壳部分版本只调这个）
    def homeVideoContent(self):
        text = self._page('/', ref='/', ttl=self.TTL)
        return {'list': self._cards(text)[:60] if text else []}

    # 分类：/{拼音目录}/ 首屏、/{拼音目录}/index-{pg}.html 翻页。
    # pagecount 取页尾真实尾页页码（本站会显式给出 index-391.html，不是窗口页码）。
    def categoryContent(self, tid, pg, filter, extend):
        page = self._pg(pg)
        tid = str(tid or '').strip() or 'guocanju'
        if tid == 'diag':
            single = 1
            return {'page': single, 'pagecount': single, 'limit': single, 'total': single,
                    'list': [self._diag_vod()]}
        if page <= 1:
            paths = ['/%s/' % tid]
        else:
            paths = ['/%s/index-%s.html' % (tid, page), '/%s/index-%s.htm' % (tid, page)]
        text = self._multi(paths, ref='/%s/' % tid, ttl=120)
        vods = self._cards(text) if text else []
        pc = self._last_page(text, tid, page)
        if pc < page:
            pc = page
        if not vods and page > 1:
            # 越界页：站点返回空列表，把 pagecount 收到上一页，避免客户端无限翻
            pc = page - 1
        return {'page': page, 'pagecount': pc, 'limit': self.limit,
                'total': len(vods), 'list': vods}

    # 详情：一次请求解析整页（线路面板与选集同页，不逐线路再拉）
    def detailContent(self, ids):
        path = self._path(ids)
        if not path:
            return {'list': []}
        text = self._page(path, ref='/', ttl=180)
        if not text:
            return {'list': []}
        vod = self._vod_fields(text, path)
        lines = self._lines(text, path)
        if not vod:
            return {'list': []}
        froms, urls = [], []
        for label, eps in lines:
            if not eps:
                continue
            body = '#'.join('%s$%s' % (name, item) for name, item in eps)
            for sub_label, sub_body in self._seg(label, body):
                froms.append(sub_label)
                urls.append(sub_body)
        vod['vod_play_from'] = '$$$'.join(froms)
        vod['vod_play_url'] = '$$$'.join(urls)
        if not froms:
            # 只挂了磁力/网盘的新片：播放列表为空，这里如实标注，不拿磁力链冒充可播地址
            vod['vod_content'] = (vod.get('vod_content') or '') + '｜该条目暂无在线播放源（站点只提供磁力/网盘下载）'
            vod['vod_remarks'] = (vod.get('vod_remarks') or '') + ' 仅下载'
        # 详情缓存给播放回退用：同一部片的其它集/线路
        self._DET[vod['vod_id']] = {'lines': lines, 'path': path}
        return {'list': [vod]}

    # 搜索：/search/?wd= 返回同款 rim-card 卡片；/search/{kw}.html 为第二形态。
    # 搜索页只有一页（实测 48 张卡上限内），多出部分按本地切片分页。
    def searchContent(self, key, quick, pg='1'):
        page = self._pg(pg)
        q = str(key or '').strip()
        if not q:
            single = 1
            return {'page': single, 'pagecount': single, 'limit': self.limit, 'total': 0, 'list': []}
        paths = ['/search/?wd=%s' % quote(q), '/search/%s.html' % quote(q)]
        text = self._multi(paths, ref='/', ttl=120)
        vods = self._cards(text) if text else []
        total = len(vods)
        start = (page - 1) * self.limit
        part = vods[start:start + self.limit]
        pc = 1
        if total > self.limit:
            pc = (total + self.limit - 1) // self.limit
        return {'page': page, 'pagecount': pc, 'limit': self.limit, 'total': total, 'list': part}

    # 播放：播放页 zanpiancms_player → apiurl+url → 壳页多路 m3u8，逐条验真。
    # 本线路死了就按同片其它集自动回退，比黑屏好。
    def playerContent(self, flag, id, vipFlags):
        raw = str(id or '').strip()
        head = json.dumps({'User-Agent': self.UA, 'Referer': 'https://%s/' % self._host_hint()})
        path = self._path(raw)
        if not path or not path.endswith('.html'):
            return {'parse': 1, 'jx': 0, 'url': raw, 'playUrl': '', 'header': head}
        cand = [path]
        # 回退：同片其它集（详情页解析时的线路缓存），最多再试 4 条
        for label, eps in (self._DET.get(self._video_of(path)) or {}).get('lines') or []:
            for name, item in eps:
                if item and item != path and item not in cand:
                    cand.append(item)
        cand = cand[:5]
        first = ''
        deadline = time.time() + self.BUDGET
        for item in cand:
            if time.time() > deadline:
                break
            for url in self._play_url(item):
                if not first:
                    first = url
                if self._media_ok(url):
                    return {'parse': 0, 'jx': 0, 'url': url, 'playUrl': '', 'header': head}
        if first:
            # 直链解析成功但本轮没验通（多为网络抖动）：仍按直链给壳，日志留痕
            self._log('播放未验证 %s' % first[-42:])
            return {'parse': 0, 'jx': 1, 'url': first, 'playUrl': '', 'header': head}
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
    # ttl=None 走默认 5 分钟；force=True 跳过缓存（播放页重试用）；try_ 是播放页的重试预算
    def _page(self, path, ref='', ttl=None, force=False, try_=1):
        ttl = self.TTL if ttl is None else ttl
        now = time.time()
        hit = self._CACHE.get(path)
        if hit and not force and now - hit[0] < ttl:
            return hit[1]
        # 路径级冷却：同一条播放页刚失败过就别在 30s 内反复打（该站播放页会连续 500）
        pt = self._PF.get(path) or 0
        if pt and now - pt < self.COOL and not force:
            return ''
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
                self._learn_hosts(text)
                return text
            self._mark_bad(host, code, path)
            time.sleep(0.5)
        # 播放页专门的重试路径：该站首次请求约三成概率 500，重试比立刻判死更划算
        if try_ > 1:
            time.sleep(1.0)
            return self._page(path, ref=ref, ttl=ttl, force=True, try_=try_ - 1)
        if not self._proxies and len(self._POOL.get('ok') or []) == 0:
            # 一圈域都没通：手机壳里常见的本地代理再试一次，避免直接判死
            self._pick_proxy()
        self._log('取页失败 %s' % path[:60])
        return ''

    # 域池自学习：成功页里若出现含站点关键词的域名（站点换域后常在页脚/公告留新地址），收进池子。
    # 入池前必须过"同模板双判"（探一次首页，200 且带 /tpl/meiju/ 资讯），
    # 否则会误收 cdn.04pic.com、php.playerla.com 这类图片/播放器域，或同名不同站（xingfan.me 就是别家站）。
    def _learn_hosts(self, text):
        if not text or len(self.hosts) >= 8:
            return
        for h in re.findall(r'https?://([a-z0-9.\-]*xingfan[a-z0-9.\-]*)', text, re.I):
            h = self._norm_host(h)
            if not h or h in self.hosts or h in self._LEARN:
                continue
            code, probe = self._pull('https://%s/' % h, ref='/')
            if code != 200 or '/tpl/meiju/' not in (probe or ''):
                self._log('候选域未过双判 %s %s' % (h, code))
                continue
            self.hosts.append(h)
            self._LEARN.append(h)
            self._log('学习新域 %s' % h)

    # 候选 URL 序列：成功域优先，再轮内置域
    def _urls(self, path):
        if not path.startswith('/'):
            path = '/' + path
        return ['https://%s%s' % (h, path) for h in self._order_hosts()]

    # 域顺序：上次成功的域置顶，其余按池内顺序
    def _order_hosts(self):
        last = self._POOL.get('last')
        ok = [h for h in (self._POOL.get('ok') or []) if h in self.hosts]
        if last and last in self.hosts and last not in ok:
            ok.insert(0, last)
        rest = [h for h in self.hosts if h not in ok]
        return (ok + rest) or [self.DEF_HOST]

    # 单次请求：session + 超时 + 代理；返回 (状态码, 文本或空)
    def _pull(self, url, ref=''):
        try:
            r = self.session.get(url, headers={'Referer': ref or url, 'Accept': 'text/html,*/*;q=0.8'},
                                 timeout=8, verify=False, proxies=self._proxies, allow_redirects=True)
            code = r.status_code
            if code < 400 and r.content:
                ctype = (r.headers.get('Content-Type') or '').lower()
                return code, self._decode(r.content, ctype, r)
            return code, ''
        except Exception:
            return 0, ''

    # 响应解码：优先按 Content-Type/头部声明走，gzip 由 requests 自动处理，这里兜底乱码
    def _decode(self, data, ctype, resp=None):
        enc = ''
        if resp is not None:
            enc = (resp.encoding or '').lower()
        for cand in (enc, 'utf-8', 'gbk'):
            if not cand or cand in ('iso-8859-1',):
                continue
            try:
                return data.decode(cand, 'strict')
            except Exception:
                continue
        return data.decode('utf-8', 'ignore')

    # 部分站会把整页塞进 JSON 字符串（前端 eval 用），这里解一层
    def _unwrap(self, text):
        s = (text or '').lstrip()
        if s.startswith('"') and s.endswith('"') and len(s) > 200:
            try:
                return json.loads(s)
            except Exception:
                return text
        return text

    # 失败留痕：只有「连不上 / 被拦 / 网关层 5xx」才给整个域打 30s 冷却；
    # 该站播放页会偶发 PHP 500、失效资源会 404，这类是单路径问题，只冷却该路径，
    # 否则一条播放失败会把整站域名冷掉，后面所有详情都 0.00s 空返回（实测踩过）。
    HARD = (0, 403, 407, 429, 502, 503, 504, 520, 521, 522, 523, 524)

    def _mark_bad(self, host, code, path=''):
        if code in self.HARD:
            self._FAIL[host] = time.time()
            bad = self._POOL.setdefault('bad', [])
            if host not in bad:
                bad.append(host)
        if path:
            self._PF[path] = time.time()
            if len(self._PF) > 300:
                self._PF.clear()
        self._log('失败 %s %s %s' % (host, code, (path or '')[:36]))

    # 冷却判断
    def _cooling(self, host):
        t = self._FAIL.get(host) or 0
        return t and (time.time() - t) < self.COOL

    # 留痕（诊断卡与调试用，不 print）
    def _log(self, msg):
        if len(self._LOG) > 200:
            del self._LOG[:-100]
        self._LOG.append('%s %s' % (time.strftime('%H:%M:%S'), msg))

    # 域名提取
    def _host_of(self, url):
        m = re.match(r'https?://([^/]+)', str(url or ''))
        return m.group(1) if m else ''

    # 当前域（header 里给 Referer 用）
    def _host_hint(self):
        return self._POOL.get('last') or self.hosts[0]

    # 本地代理探测：只探常见端口，探到就用，探不到就算了
    def _pick_proxy(self):
        for p in self.PROXY_PORTS:
            url = 'http://127.0.0.1:%s' % p
            try:
                s = requests.Session()
                s.trust_env = False
                s.get('https://%s/' % self.DEF_HOST, proxies={'http': url, 'https': url},
                      timeout=4, verify=False)
                self.proxy = url
                self._proxies = {'http': url, 'https': url}
                self._log('本地代理解析成功 %s' % url)
                return True
            except Exception:
                continue
        return False

    # ---------------------------------------------------------------- 解析

    # 卡片解析：三种卡片（分类页 proto-rim、首页更新日历 proto-sched-card、搜索页 rim-card）共用一套提取。
    # 切分锚用 `<a href="`：卡片段首就紧跟 href 值，段头 700 字内必须出现卡片 class，
    # 这样首页 hero 区那种"标题链接 + 背景大图"的错位锚点会被自然跳过（实测按 href 悬浮切分会让名字整体错一格）。
    def _cards(self, text, base=''):
        out = []
        if not text:
            return out
        seen = set()
        for seg in (text or '').split('<a href="')[1:]:
            head = seg[:700]
            if not re.search(r'class="(?:proto-rim|proto-sched-card|rim-card)', head):
                continue
            m = re.match(r'(/([a-z]+)/([a-z0-9\-]+)/)"', seg)
            if not m:
                continue
            path = m.group(1)
            if path in seen:
                continue
            seg = seg[:1600]
            if '<img' not in seg:
                continue
            # 名字优先 alt：三种卡片的 alt 都是卡片自身的片名（实测与 href 一一对应）
            name = ''
            am = re.search(r'<img[^>]+alt="([^"]*)"', seg)
            if am:
                name = self._clean(am.group(1))
            if not name:
                pm = re.findall(r'<p class="text-(?:sm|xs)[^"]*">(.*?)</p>', seg, re.S)
                name = self._clean(pm[0]) if pm else ''
            if not name:
                continue
            pic = ''
            im = re.search(r'<img[^>]+src="([^"]+)"', seg)
            if im:
                pic = im.group(1)
            if pic.startswith('//'):
                pic = 'https:' + pic
            elif pic.startswith('/'):
                pic = urljoin('https://%s' % self._host_hint(), pic)
            # 角标按卡片类型分别取：
            #   proto-rim（分类/首页网格）：封面左下 span 是题材，底栏 11px 小字是"第2集 / 共8集"
            #   proto-sched-card（首页日历）：proto-vtag 是分类，white/40 小字是更新进度
            #   rim-card（搜索）：vtag 是分类，white/35 小字是年份
            note = ''
            # 注意 span 内容带换行与缩进，字符类要放宽到 40 再交给 _clean 压空白，卡 24 会整条落空
            tm = re.search(r'bottom-2 left-2 right-2">\s*<span[^>]*>([^<]{2,40})<', seg)
            if not tm:
                tm = re.search(r'class="[^"]*(?:proto-vtag|vtag)[^"]*"[^>]*>([^<]{2,40})<', seg)
            if tm:
                note = self._clean(tm.group(1))
            sm = re.search(r'class="text-amber-400[^"]*">([^<]+)<', seg)
            if sm:
                note = (note + ' ' + self._clean(sm.group(1))).strip()
            extra = ''
            em = re.search(r'<p class="text-\[11px\][^"]*">([^<]{1,20})</p>', seg)
            if em:
                extra = self._clean(em.group(1))
            if not extra:
                ym2 = re.search(r'<p class="text-xs text-white/(?:40|35)[^"]*">([^<]{1,16})</p>', seg)
                if ym2:
                    extra = self._clean(ym2.group(1))
            year = extra if (extra.isdigit() and len(extra) == 4) else ''
            # 角标顺序：更新进度/年份在前、题材在后（客户端角标宽度有限，进度比题材更值得先露出来）
            note = ((extra if not year else '') + ' ' + note).strip()
            seen.add(path)
            out.append({
                'vod_id': path,
                'vod_name': name,
                'vod_pic': self._pic(pic),
                'vod_remarks': note[:26],
                'vod_tag': '',
                'vod_year': year,
            })
        return out

    # 详情字段：og:title/og:image + 剧情简介 + 导演/主演/年份/地区/类型/语言
    def _vod_fields(self, text, path):
        name = ''
        tm = re.search(r'<meta property="og:title" content="(.*?)"', text, re.S)
        if tm:
            bt = re.findall(r'《(.*?)》', unescape(tm.group(1)))
            name = bt[0] if bt else unescape(tm.group(1)).split('-')[0]
        if not name:
            tm2 = re.search(r'<title>(.*?)</title>', text, re.S)
            if tm2:
                bt = re.findall(r'《(.*?)》', unescape(tm2.group(1)))
                name = bt[0] if bt else self._clean(tm2.group(1)).split('-')[0]
        name = self._clean(name)
        if not name:
            return {}
        pic = ''
        pm = re.search(r'<meta property="og:image" content="(.*?)"', text, re.S)
        if pm:
            pic = pm.group(1)
        desc = ''
        dm = re.search(r'<meta property="og:description" content="(.*?)"', text, re.S)
        if dm:
            desc = self._clean(dm.group(1))
        if not desc:
            sm = re.search(r'<p class="text-sm text-white/60 leading-relaxed">(.*?)</p>', text, re.S)
            desc = self._clean(sm.group(1)) if sm else ''
        info = {}
        for label in ('导演', '主演', '年份', '地区', '类型', '语言'):
            m = re.search(r'>%s</span><p[^>]*>(.*?)</p>' % label, text, re.S)
            if m:
                info[label] = self._clean(m.group(1))
        year = info.get('年份', '')
        if not year:
            ym = re.search(r'<span class="[^"]*">(\d{4}) · ', text)
            year = ym.group(1) if ym else ''
        remarks = info.get('类型', '')
        rm = re.search(r'<span class="[^"]*">\d{4}[^<]*· (\d+集|[^<]*)</span>', text)
        if rm:
            remarks = (remarks + ' ' + self._clean(rm.group(1)).strip()).strip()
        score = ''
        sc = re.search(r'style="font-size:4rem[^"]*">(\d+\.\d+)</div>', text)
        if sc and sc.group(1) not in ('0.0', '0'):
            score = sc.group(1)
        return {
            'vod_id': path,
            'vod_name': name,
            'vod_pic': self._pic(pic),
            'vod_year': year,
            'vod_area': info.get('地区', ''),
            'vod_lang': info.get('语言', ''),
            'vod_actor': info.get('主演', '').replace(',', ' / '),
            'vod_director': info.get('导演', '').replace(',', ' / '),
            'vod_remarks': remarks[:24],
            'vod_content': desc,
            'vod_douban_score': score,
            'type_name': info.get('类型', ''),
        }

    # 线路与选集：data-tab-target="detail_line_{sid}" 给线路名，episode-link 给 sid-nid + 集名
    def _lines(self, text, path):
        names = {}
        for m in re.finditer(r'data-tab-target="detail_line_(\d+)">([^<]*)<', text):
            names[m.group(1)] = self._clean(m.group(2)) or ('线路%s' % m.group(1))
        groups = {}
        cid = ''
        pm = re.match(r'/([a-z]+)/', path)
        if pm:
            cid = pm.group(1)
        for m in re.finditer(r'<a href="(/([a-z]+)/([a-z0-9\-]+)/(\d+)-(\d+)\.html)" class="episode-link">([^<]*)</a>', text):
            sid, nid, label = m.group(4), m.group(5), self._clean(m.group(6))
            groups.setdefault(sid, []).append((label or ('第%s集' % nid), m.group(1)))
        out = []
        for sid in sorted(groups.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            eps = groups[sid]
            label = names.get(sid) or ('线路%s' % sid)
            if len(eps) > 1 and label in [x[0] for x in out]:
                label = '%s%s' % (label, len(out) + 1)
            out.append((label, eps))
        if not out:
            # 部分详情页（未上在线线路）只在"进入播放页"按钮给出 1-1.html，这里不当真线路
            self._log('无选集 %s' % path[:50])
        return out

    # 播放页：重试取页 → 解析 zanpiancms_player → 取壳页 → 多路 m3u8
    def _play_url(self, path):
        text = self._page(path, ref='/', ttl=120, try_=self.PLAY_TRY)
        if not text:
            return []
        m = re.search(r'zanpiancms_player\s*=\s*(\{.*?\})\s*;', text, re.S)
        if not m:
            return []
        try:
            cfg = json.loads(m.group(1).replace('\\/', '/'))
        except Exception:
            return []
        api = str(cfg.get('apiurl') or '').strip() or self.PLAY_API
        if api.startswith('//'):
            api = 'https:' + api
        elif api.startswith('/'):
            api = 'https://%s%s' % (self._host_hint(), api)
        u = str(cfg.get('url') or '').strip()
        if not u:
            return []
        src = api + u
        body = self._page_abs(src, ref='https://%s%s' % (self._host_hint(), path))
        if not body:
            return []
        urls = []
        for x in re.findall(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', body):
            x = unescape(x).replace('&amp;', '&')
            if x not in urls:
                urls.append(x)
        if not urls:
            # 少数壳页把地址写成转义串，再解一层
            for x in re.findall(r'https?:\\/\\/[^\s"\'<>]+\.m3u8[^\s"\'<>]*', body):
                x = x.replace('\\/', '/').replace('\\u0026', '&')
                if x not in urls:
                    urls.append(x)
        return urls

    # 绝对地址取页（播放壳页不在本站域名下，绕开域池直接请求）
    def _page_abs(self, url, ref=''):
        key = 'ABS:' + url
        hit = self._CACHE.get(key)
        if hit and time.time() - hit[0] < self.TTL:
            return hit[1]
        for _ in range(2):
            code, text = self._pull(url, ref)
            if code == 200 and text:
                self._CACHE[key] = (time.time(), text)
                return text
            time.sleep(0.8)
        self._log('壳页失败 %s' % url[-38:])
        return ''

    # 媒体验真：只认 #EXTM3U / ftyp / 视频 MIME，300s 缓存同一地址的结论
    def _media_ok(self, url):
        t = self._MEDIA.get(url)
        if t and time.time() - t[0] < 300:
            return t[1]
        ok = False
        try:
            r = self.session.get(url, headers={'User-Agent': self.UA, 'Accept': '*/*',
                                               'Referer': 'https://%s/' % self._host_hint()},
                                 timeout=6, verify=False, stream=True, proxies=self._proxies)
            head = b''
            for ch in r.iter_content(512):
                head += ch
                if len(head) > 600:
                    break
            r.close()
            ctype = (r.headers.get('Content-Type') or '').lower()
            # 注意：head 是 bytes，字符串字面量必须写成 bytes，否则 `in` 直接抛 TypeError 会被吞成 False
            ok = (b'#EXTM3U' in head) or (b'ftyp' in head[:64]) or ('video/' in ctype) \
                 or ('application/vnd.apple.mpegurl' in ctype) or ('application/x-mpegurl' in ctype)
        except Exception:
            ok = False
        self._MEDIA[url] = (time.time(), ok)
        return ok

    # ---------------------------------------------------------------- 工具

    # 分段：单条 vod_play_url 超 1900B 就切段，同名加序号（客户端 2048B 截断）
    def _seg(self, label, body):
        if len(body.encode('utf-8')) <= self.SEG_BYTES:
            return [(label, body)]
        parts, cur, n = [], [], 1
        for item in body.split('#'):
            if not item:
                continue
            cand = cur + [item]
            if len('#'.join(cand).encode('utf-8')) > self.SEG_BYTES and cur:
                parts.append(cur)
                cur = [item]
            else:
                cur = cand
        if cur:
            parts.append(cur)
        out = []
        for i, p in enumerate(parts):
            name = label if i == 0 else '%s(%d)' % (label, i + 1)
            out.append((name, '#'.join(p)))
        return out

    # 尾页页码：分类页页尾会给出 /{tid}/index-{last}.html
    def _last_page(self, text, tid, page):
        if not text:
            return page
        nums = [int(x) for x in re.findall(r'href="/%s/index-(\d+)\.html"' % re.escape(tid), text)]
        if nums:
            return max(nums)
        return page + 1 if len(self._cards(text)) >= self.limit else page

    # ids → 相对路径：兼容裸数字以外的所有形态（/oumeiju/x/、oumeiju/x/、完整 URL）
    # 客户端有的传字符串、有的传 list、有的传 JSON 串（"['/oumeiju/x/']"），三种都要吃下
    def _path(self, ids):
        s = ids
        if isinstance(s, (list, tuple)):
            s = s[0] if s else ''
        s = str(s or '').strip()
        if s.startswith('['):
            try:
                v = json.loads(s.replace("'", '"'))
                s = str((v or [''])[0])
            except Exception:
                s = s.strip("[]'\" ")
        s = s.strip().strip("'\"")
        # 客户端偶尔把整段 "第01集$/oumeiju/x/1-1.html" 一起传进来，取 $ 之后的部分
        if '$' in s:
            s = s.split('$')[-1].strip()
        if not s:
            return ''
        s = re.sub(r'https?://[^/]+', '', s, flags=re.I)
        s = s.split('?', 1)[0].split('#', 1)[0]
        if not s.startswith('/'):
            s = '/' + s
        if s.endswith('.html') or s.endswith('/'):
            return s
        return s + '/'

    # 播放路径 → 视频相对路径（去掉末尾 {sid}-{nid}.html）
    def _video_of(self, path):
        return re.sub(r'/\d+-\d+\.html$', '/', path)

    # 页码规整
    def _pg(self, pg):
        try:
            n = int(pg)
        except Exception:
            n = 1
        return n if n > 0 else 1

    # 文本清洗：去标签、反转义、压空白
    def _clean(self, s):
        s = re.sub(r'<[^>]+>', '', str(s or ''))
        s = unescape(s).replace('\u00a0', ' ')
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    # 封面：站点图片走 cdn.04pic.com，实测直出可用；需要代理时给 localProxy 链接
    def _pic(self, p):
        p = str(p or '').strip()
        if not p:
            return ''
        if p.startswith('//'):
            p = 'https:' + p
        if not p.startswith('http'):
            return ''
        if self.img_proxy:
            return '%s?p=%s' % (self._proxy_base(), quote(p, safe=''))
        return p

    # localProxy 入口地址（羊壳注入）
    def _proxy_base(self):
        try:
            return self.getProxyUrl() + '&p='
        except Exception:
            return 'http://127.0.0.1:9978/proxy?do=py&p='

    # 图片代理：返回真实 MIME + 二进制，空 body 返 404，不返回 200 空图
    def localProxy(self, param):
        p = str((param or {}).get('p') or '')
        if not p.startswith('http'):
            return [404, 'text/plain', '']
        try:
            r = self.session.get(p, headers={'User-Agent': self.UA, 'Referer': 'https://%s/' % self._host_hint()},
                                 timeout=8, verify=False, proxies=self._proxies)
            if r.status_code == 200 and r.content:
                return [200, r.headers.get('Content-Type') or 'image/jpeg', r.content]
        except Exception:
            pass
        return [404, 'text/plain', '']

    # 诊断卡：域池、缓存、失败、最近日志，用来判断是站点挂了还是选择器错了
    def _diag_vod(self):
        try:
            import importlib.util
            zstd = '有' if importlib.util.find_spec('zstandard') else '无'
        except Exception:
            zstd = '无'
        try:
            import ctypes.util
            lib = '有' if ctypes.util.find_library('zstd') else '无'
        except Exception:
            lib = '无'
        lines = [
            '域名池: %s' % ', '.join(self.hosts),
            '当前域: %s' % self._host_hint(),
            '成功域: %s' % (', '.join(self._POOL.get('ok') or []) or '无'),
            '失败域: %s' % (', '.join(self._POOL.get('bad') or []) or '无'),
            '缓存条目: %d' % len(self._CACHE),
            '详情缓存: %d' % len(self._DET),
            'zstandard=%s libzstd=%s' % (zstd, lib),
            '代理: %s' % (self.proxy or '直连'),
        ]
        for x in (self._LOG or [])[-10:]:
            lines.append(x)
        body = ' '.join(lines)
        return {
            'vod_id': 'diag',
            'vod_name': '诊断报告',
            'vod_pic': '',
            'vod_remarks': '%d条' % len(self._LOG or []),
            'vod_content': body,
        }
