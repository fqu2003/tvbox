# 站点：https://www.xinxiangov.com   新新影院（MacCMS + 魔加 mojia 主题）
# 路线：MacCMS 原生 ajax 数据接口出列表 + 详情页 HTML 出剧集 + 播放页 data-play 加密直链
# 生成：2026-11-23   作者：Doubao
# 依赖：requests（壳端自带）；base.spider
# 接口：homeContent / homeVideoContent / categoryContent
#       detailContent / searchContent / playerContent / localProxy
# vod_id：纯数字 vod_id（站点 /xxtv/{id}.html）
#         剧集 play id = {vid}_{sid}_{nid}，playerContent 再拼 /play/{id}.html——
#         存短 id 是为绕开客户端 2048B 截断线：长剧 100 集用短 id 约 1300B，
#         若改存完整相对路径会到 2200B 以上，后半段集数直接被壳端截掉。
# 已知：站点采集 API /api.php/provide/vod 已关闭（body 只有 6 字节 closed），
#       所以列表走 /index.php/ajax/data；动漫/纪录片两个目录在 ajax 接口里没有 tid
#       （1~40 全试过，只会回退成"综艺/全部"），改走分类页 HTML 取首屏 50 条，
#       该目录本身无分页 UI（页面里 mo-page-sums 恒为 0），故 pagecount=1 为站点真值；
#       封面域 ynztctv.com 已变成停放页（903B "Site is created successfully"），
#       封面统一走 localProxy，可用 extend.img 覆盖成自己的图床。

import base64
import json
import re
import threading
import time
from urllib.parse import quote, unquote, urljoin

import requests
from base.spider import Spider


class Spider(Spider):
    # 主域与裸域：两者实测同一套 API、同一份数据（pagecount=9071 / total=90709 完全一致），
    # 互相备份；其他 TLD 变体（.net/.tv/.vip/.top/.xyz/.cc/.cn/.org/.me/.io/.info/.site/.us）
    # 与 m. 子域全部 ConnectionError，站点没有发布页（首页"发布页/备用/最新地址/回家/永久/防失联"
    # 六个关键词计数全为 0），所以这里如实只放两个真实可用域。
    HOST = 'https://www.xinxiangov.com'
    HOSTS = ('https://www.xinxiangov.com', 'https://xinxiangov.com')
    # ajax 接口固定每页 10 条（返回里 limit=10），不是可以随便改的参数，改大无效
    LIMIT = 10
    # 分类页 HTML 首屏条数（动漫/纪录片走这条路的 limit）
    HTML_LIMIT = 50
    # 单条 vod_play_url 上限：客户端 2048B 截断，留 150B 余量
    SEG = 1900
    # 慢站实测：首页 2.3s、分类页 6.3s、详情页 9.5s、ajax 首请求 7.7s → 预算给 16s
    BUDGET = 16
    TTL = 300
    FAIL_TTL = 30
    # 真实分类：全部用 ajax 实测过 pagecount，语义与站点目录一一对应
    # (tid, 名称, 实测 pagecount)  1=9071 2=13431 4=5129 21=6854 ...
    CATS = (
        ('1', '电影'), ('2', '电视剧'), ('4', '综艺'), ('21', '热门短剧'),
        ('6', '动作片'), ('10', '喜剧片'), ('11', '爱情片'), ('7', '科幻片'),
        ('9', '恐怖片'), ('12', '剧情片'), ('8', '战争片'),
        ('13', '国产剧'), ('14', '港台剧'), ('15', '日韩剧'), ('16', '海外剧'),
        ('20', '伦理剧场'),
        ('h_dongmna', '动漫'), ('h_jilupian', '纪录片'),
    )
    # 域级失败码：只有这些才算"这个域坏了"，单页 404 只冷路径不冷域
    HARD = (0, 403, 407, 429, 502, 503, 504, 520, 521, 522, 523, 524)
    # 类属性：换实例后缓存与域池仍然有效（写进实例属性等于每个新实例都重探一遍）
    _CACHE = {}
    _FAIL = {}
    _PLAY = {}
    _PROBED = {}
    _POOL = {}

    # 接口：init 入参 extend 可为 ''/JSON/URL，只做绑定与轻量选域，不重置缓存
    def init(self, extend=''):
        # 启动：只做绑定与轻量选域，绝不在这里跑全量探活/解析发布页，否则进源要卡 10s+
        self.host = self.HOST
        self.img_tpl = ''
        s = (extend or '').strip()
        if s.startswith('{'):
            try:
                cfg = json.loads(s)
                h = str(cfg.get('host') or '').strip()
                if h:
                    self.host = h if h.startswith('http') else 'https://' + h
                self.img_tpl = str(cfg.get('img') or '')
            except Exception:
                pass
        elif s.startswith('http'):
            self.host = s.rstrip('/')
        self.base = self.host.rstrip('/')
        self.headers = {
            'User-Agent': ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.base + '/',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.trust_env = False
        self._CACHE = type(self)._CACHE.setdefault(self.base, {})
        self._FAIL = type(self)._FAIL.setdefault(self.base, {})
        self._PLAY = type(self)._PLAY.setdefault(self.base, {})
        self.host = self._pick_host(self.base, full=False)
        self.base = self.host
        self.headers['Referer'] = self.base + '/'
        return None

    # 接口：getName 返回站名，壳端标题栏显示用
    def getName(self):
        return 'ᵀ⁴新新影院'

    # 接口：homeContent(filter) 返回 {class, list}，list 取首页 HTML 首屏 50 条
    def homeContent(self, filter):
        # 首页：分类 18 个 + 首屏 50 张卡（取首页 HTML，比 ajax 的 10 条充实）
        # 返回 {class, list}；list 只需 vod_id/vod_name/vod_pic/vod_remarks
        return {'class': self._classes(), 'list': self._home_list()}

    def homeVideoContent(self):
        # 推荐位：与首页首屏共用缓存，壳端不额外付请求
        return {'list': self._home_list()}

    def categoryContent(self, tid, pg, filter, extend):
        # 分类：h_ 前缀（动漫/纪录片）走分类页 HTML，站点该目录无分页，分页数按单页处理
        # 其余走 /index.php/ajax/data，pagecount/total 直接取站点真值（禁 99/9999）
        t = str(tid or '').strip()
        page = self._pg(pg)
        if t.startswith('h_'):
            # 该目录页面里 mo-page-sums 恒为 0、无页码控件，站点本身就只给这一屏；
            # 用本地切片真值 pc=1（不是拿 99/9999 冒充）
            html = self._html('%s/xxyy/%s.html' % (self.base, t[2:]))
            vods = self._list_html(html)
            pc = 1 if vods else 0
            return {'page': 1, 'pagecount': pc or 1, 'limit': self.HTML_LIMIT,
                    'total': len(vods), 'list': vods}
        j = self._json('%s/index.php/ajax/data?mid=1&tid=%s&page=%s' % (
            self.base, quote(t or '1'), page))
        if not j:
            return {'page': page, 'pagecount': page, 'limit': self.LIMIT, 'total': 0, 'list': []}
        vods = self._list_ajax(j)
        pc = int(j.get('pagecount') or 0) or page
        total = int(j.get('total') or 0) or pc * self.LIMIT
        return {'page': page, 'pagecount': pc, 'limit': self.LIMIT, 'total': total, 'list': vods}

    # 接口：searchContent(key, quick, pg='1') 返回分页字典，站点搜索只有一页
    def searchContent(self, key, quick, pg='1'):
        # 搜索：站点把关键词直接拼进路径 /xxso{关键词}.html（中文原样进 href，需 quote）
        # 站点搜索只有一页（没有页码参数），pagecount 固定 1，多页由本地切片兜底
        kw = str(key or '').strip()
        if not kw:
            # 关键词为空直接回空，不拿首页冒充搜索结果
            return {'page': 1, 'pagecount': 0, 'limit': self.LIMIT, 'total': 0, 'list': []}
        html = self._html('%s/xxso%s.html' % (self.base, quote(kw)))
        vods = self._list_html(html)
        page = self._pg(pg)
        if len(vods) > self.LIMIT:
            total = len(vods)
            pc = 1
            start = (page - 1) * self.LIMIT
            vods = vods[start:start + self.LIMIT]
        else:
            total, pc = len(vods), 1
        return {'page': page, 'pagecount': pc, 'limit': self.LIMIT, 'total': total, 'list': vods}

    # 接口：detailContent(ids) 返回 {list:[vod]}，线路来自详情页 mo-sort-head 块
    def detailContent(self, ids):
        # 详情：/xxtv/{vid}.html 一次请求拿全，绝不逐线路再拉详情
        # 线路来自页面里每个 mo-sort-head 块：线路名 data-show/mo-movs-btns，剧集是块内
        # /play/{vid}_{sid}_{nid}.html 链接；按页面出现顺序输出（不按 sid 数值排）
        key = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(key or '').strip()
        m = re.search(r'(\d{3,})', vid)
        vid = m.group(1) if m else ''
        if not vid:
            return {'list': []}
        html = self._html('%s/xxtv/%s.html' % (self.base, vid))
        if not html:
            return {'list': []}
        vod = self._vod(html, vid)
        lines = self._lines(html, vid)
        if not lines:
            return {'list': []}
        parts = []
        for label, eps in lines:
            parts.extend(self._segments(label, eps))
        vod['vod_play_from'] = '$$$'.join(x[0] for x in parts)
        vod['vod_play_url'] = '$$$'.join(x[1] for x in parts)
        return {'list': [vod]}

    # 接口：playerContent(flag, id, vipFlags) 返回 {parse, jx, url, playUrl, header}
    def playerContent(self, flag, id, vipFlags):
        # 播放：/play/{vid}_{sid}_{nid}.html 里没有 player_aaaa，真实地址在 data-play：
        #   形如 "ADyaHR0cHM6Ly8..." = 3 个随机前缀字符 + base64(直链)
        # 6 条线路实测全部能解出 index.m3u8（无需 data-parse 解析接口），故优先 parse:0
        raw = str(id or '').strip()
        # 壳端可能把整段 "集名$播放ID" 原样塞进来，必须先剥掉 $ 前的名字，否则拼出
        # /play/正片$694723_2_1.html 这种 404 地址，direct_play 会恒为 0
        if '$' in raw:
            raw = raw.rsplit('$', 1)[-1].strip()
        if not raw:
            return {'parse': 1, 'jx': 0, 'url': '', 'playUrl': '', 'header': json.dumps(self.headers)}
        ck = 'p:' + raw
        hit = self._PLAY.get(ck)
        url = hit[1] if hit and time.time() - hit[0] < self.TTL else ''
        page = ''
        api = ''
        if not url:
            page = raw if raw.startswith('http') else '%s/play/%s.html' % (self.base, raw)
            html = self._html(page)
            url, api = self._from_play(html)
            if url:
                self._PLAY[ck] = (time.time(), url)
        header = json.dumps(self.headers)
        if not url:
            # 解不出来就交给壳端解析原播放页，别硬塞 parse:0 假直链
            return {'parse': 1, 'jx': 0, 'url': page or raw, 'playUrl': '', 'header': header}
        if self._probe(url):
            return {'parse': 0, 'jx': 0, 'url': url, 'playUrl': '', 'header': header}
        # 直链 CDN 已死（实测 cdn.wlcdn88.com / v1.gggread.com / hd.ijycnd.com 都 ConnectionError）：
        # 站点自己有 data-parse 解析接口，拼成解析页交给壳端，比回退原始播放页更容易被抓到
        if api:
            try:
                return {'parse': 1, 'jx': 1, 'url': api + quote(url, safe=''),
                        'playUrl': '', 'header': header}
            except Exception:
                pass
        return {'parse': 1, 'jx': 0, 'url': page or raw, 'playUrl': '', 'header': header}

    def localProxy(self, param):
        # 图片代理：封面域 ynztctv.com 已停放、pic.* 各站又常拒 Referer，
        # 统一由这里带站点 Referer 取二进制；空 body 必须返 404，不能 200 空图
        text = str(param or '')
        m = re.search(r'(?:^|[?&])url=([^&]+)', text)
        if not m:
            return [404, 'text/plain', b'']
        url = unquote(m.group(1))
        if not url.startswith('http'):
            return [404, 'text/plain', b'']
        code, ctype, data = self._bytes(url)
        if code not in (200, 206) or not data:
            return [404, 'text/plain', b'']
        return [200, ctype or 'image/jpeg', data]

    # ---------------- 域池 / 换域 ----------------

    def _pick_host(self, seed='', full=False):
        # 启动与换域分两条路径：init 只验前 2 个种子，失败也先认种子（离线也能进源）；
        # 只有 _mark_host 判定域坏了才 full=True 全量验。
        now = time.time()
        if not full:
            hit = self._POOL.get('cur')
            if hit and now - hit[0] < 600:
                return hit[1]
        cands = []
        for h in (seed, self.HOST) + tuple(self.HOSTS) + tuple(self._POOL.get('learn') or ()):
            h = (h or '').strip().rstrip('/')
            if h.startswith('http') and h not in cands:
                cands.append(h)
        if not full:
            for h in cands[:2]:
                if self._alive(h):
                    self._POOL['cur'] = (now, h)
                    return h
            h = cands[0] if cands else self.HOST
            self._POOL['cur'] = (now, h)
            return h
        deadline = time.time() + 15
        for h in cands[:6]:
            if time.time() > deadline:
                break
            if self._alive(h):
                self._POOL['cur'] = (time.time(), h)
                return h
            time.sleep(0.6)
        # 全失败也要退回种子：站点可能只是瞬时限流，返回空域会让整源死掉
        return seed or self.HOST

    def _alive(self, host):
        # 探活打首页，必须含站点模板指纹；体量小或只有跳转脚本的一律判死
        t0 = time.time()
        hit = self._PROBED.get(host)
        if hit:
            ok = hit[1]
            if time.time() - hit[0] < (self.TTL if ok else self.FAIL_TTL):
                return ok
        try:
            r = self.session.get(host + '/', timeout=(6, 14), allow_redirects=True)
            ok = r.status_code == 200 and self._is_site(r.text)
        except Exception:
            ok = False
        self._PROBED[host] = (time.time(), ok, round(time.time() - t0, 2))
        return ok

    def _is_site(self, text):
        # 双判：模板指纹（moujia 主题资源）+ 路由指纹（/xxtv/ 详情链接）
        # 只判 title 会被同名不同站骗过，这里两条都要过
        t = str(text or '')
        return ('template/mojia' in t) or ('新新影院' in t and '/xxtv/' in t)

    def _mark_host(self, code):
        # 三件套重绑：只清 base 不改 headers/cache 等于假换域
        if code not in self.HARD:
            return
        bad = self.base
        self._FAIL[bad] = time.time() + self.FAIL_TTL
        self._POOL.pop('cur', None)
        new = self._pick_host(self.HOST, full=True)
        if new and new != bad:
            self.base = new
            self.host = new
            self.headers['Referer'] = new + '/'
            self.session.headers.update({'Referer': new + '/'})
            self._CACHE = type(self)._CACHE.setdefault(new, {})
            self._FAIL = type(self)._FAIL.setdefault(new, {})
            self._PLAY = type(self)._PLAY.setdefault(new, {})
            self._POOL['cur'] = (time.time(), new)
            learn = list(self._POOL.get('learn') or ())
            if bad not in learn:
                learn.append(bad)
            self._POOL['learn'] = tuple(learn[-6:])

    # ---------------- 网络 ----------------

    def _get(self, url, referer='', retry=True):
        # 所有请求走 session + 墙钟预算；慢站半开连接会挂几十秒，timeout 管不住
        ck = 'g:' + url
        hit = self._CACHE.get(ck)
        if hit and time.time() - hit[0] < self.TTL:
            return hit[1]
        fail = self._FAIL.get(ck)
        if fail and time.time() < fail:
            return ''
        box = {}

        def run():
            try:
                h = dict(self.session.headers)
                h['Referer'] = referer or (self.base + '/')
                r = self.session.get(url, headers=h, timeout=(6, self.BUDGET), allow_redirects=True,
                                    proxies=self.session.proxies or None)
                box['r'] = r
            except Exception as e:
                box['e'] = e

        th = threading.Thread(target=run, daemon=True)
        th.start()
        th.join(self.BUDGET)
        r = box.get('r')
        if r is None:
            self._FAIL[ck] = time.time() + self.FAIL_TTL
            # 连接都建立不起来（DNS/拒连/超时）说明这个域已经没了，直接走换域；
            # 不换的话用户得手动改源才能继续用
            self._mark_host(0)
            return ''
        code = r.status_code
        if code not in (200, 206):
            self._FAIL[ck] = time.time() + self.FAIL_TTL
            # 首页/分类页 200 但内容不认识 → 判域失效换域；详情页 404 只是路径问题
            if url.endswith('/') or '/xxyy/' in url:
                self._mark_host(code)
            return ''
        text = r.text
        # 200 也可能是劫持页：只对首页与分类页做内容判定，且排除限流短页
        if (url.endswith('/') or '/xxyy/' in url) and len(text) < 8000 \
                and '系统提示' not in text and not self._is_site(text):
            self._mark_host(0)
            return ''
        self._CACHE[ck] = (time.time(), text)
        return text

    def _html(self, url):
        return self._get(url)

    def _json(self, url):
        text = self._get(url)
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _bytes(self, url, referer=''):
        # localProxy 取图：必须复用 session，且按图片域决定要不要带 Referer
        try:
            h = dict(self.session.headers)
            h['Referer'] = referer or 'https://www.xinxiangov.com/'
            r = self.session.get(url, headers=h, timeout=(5, 12), allow_redirects=True)
            return r.status_code, r.headers.get('Content-Type', ''), r.content
        except Exception:
            return 0, '', b''

    def _probe(self, url):
        # 媒体验真：只读前 2KB 判 #EXTM3U / ftyp，绝不把整条 m3u8 拉下来
        # head 是 bytes，写 '#EXTM3U' in head 会 TypeError 并被 except 吞成 False（假阴性坑）
        ck = 'm:' + url
        hit = self._PLAY.get(ck)
        if hit and time.time() - hit[0] < 60:
            return hit[1]
        ok = False
        try:
            r = self.session.get(url, headers={'User-Agent': self.headers['User-Agent'],
                                               'Referer': None},
                                 timeout=(4, 9), stream=True, allow_redirects=True)
            if r.status_code in (200, 206):
                head = next(r.iter_content(2048), b'') or b''
                ctype = (r.headers.get('Content-Type') or '').lower()
                ok = (b'#EXTM3U' in head or b'ftyp' in head[:64]
                      or 'mpegurl' in ctype or ctype.startswith('video/'))
            r.close()
        except Exception:
            ok = False
        self._PLAY[ck] = (time.time(), ok)
        return ok

    # ---------------- 解析 ----------------

    def _classes(self):
        return [{'type_id': t, 'type_name': n} for t, n in self.CATS]

    def _home_list(self):
        ck = 'home:list'
        hit = self._CACHE.get(ck)
        if hit and time.time() - hit[0] < self.TTL:
            return hit[1]
        vods = self._list_html(self._html(self.base + '/'))
        self._CACHE[ck] = (time.time(), vods)
        return vods

    def _list_ajax(self, j):
        # ajax 返回项已是完整 MacCMS 字段，不需要再补请求
        out = []
        for it in (j.get('list') or []):
            vid = str(it.get('vod_id') or '')
            if not vid:
                continue
            out.append({
                'vod_id': vid,
                'vod_name': str(it.get('vod_name') or '').strip() or ('影片' + vid),
                'vod_pic': self._pic(str(it.get('vod_pic') or '')),
                'vod_remarks': str(it.get('vod_remarks') or '').strip(),
                'vod_year': str(it.get('vod_year') or '').strip(),
                'vod_area': str(it.get('vod_area') or '').strip(),
                'vod_score': str(it.get('vod_score') or '').strip(),
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return out

    def _list_html(self, html):
        # 首页/分类页/搜索页共用：每个卡片 li 里取 xxtv 链接 + 封面 + 名称 + 角标
        # 用 li 块整串切分，不做"链接位置回溯前文"，避免轮播区让名字与 ID 错位一格
        vods, seen = [], set()
        t = str(html or '')
        for m in re.finditer(r'<li class="[^"]*mo-cols-info[^"]*"[^>]*>(.*?)</li>', t, re.S):
            blk = m.group(1)
            dm = re.search(r'href="[^"]*/xxtv/(\d+)\.html"', blk)
            if not dm:
                continue
            vid = dm.group(1)
            if vid in seen:
                continue
            nm = re.search(r'class="mo-situ-name[^"]*"[^>]*>([^<]{1,80})<', blk)
            pc = re.search(r'data-original="([^"]+)"', blk)
            rm = re.search(r'class="mo-situ-rema[^"]*"[^>]*>([^<]{1,24})<', blk)
            seen.add(vid)
            vods.append({
                'vod_id': vid,
                'vod_name': (nm.group(1).strip() if nm else '') or ('影片' + vid),
                'vod_pic': self._pic(pc.group(1) if pc else ''),
                'vod_remarks': rm.group(1).strip() if rm else '',
                'style': {'type': 'rect', 'ratio': 1.33},
            })
        return vods

    def _vod(self, html, vid):
        # 详情页字段：h1 出名称、<dt> 主图出封面、dd 区出主演/导演/年份/地区/简介
        def txt(s):
            return re.sub(r'<[^>]+>', '', s or '').replace('&nbsp;', ' ').strip()

        name = ''
        m = re.search(r'<h1[^>]*class="mo-wrap-arow[^"]*"[^>]*>\s*<a[^>]*>(.*?)</a>', html, re.S)
        if m:
            name = txt(m.group(1))
        if not name:
            m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            name = txt(m.group(1)) if m else ''
        pic = ''
        m = re.search(r'<dt[^>]*>.*?<img[^>]+src="([^"]+)"', html, re.S)
        if m:
            pic = m.group(1)
        if not pic:
            m = re.search(r'<img[^>]+data-original="([^"]+)"', html)
            pic = m.group(1) if m else ''
        actor = director = year = area = ''
        m = re.search(r'主演[:：]?&nbsp;?\s*</span>(.*?)</li>', html, re.S)
        if m:
            actor = ','.join(x for x in re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1)) if x)
        m = re.search(r'导演[:：]?&nbsp;?\s*</span>(.*?)</li>', html, re.S)
        if m:
            director = ','.join(x for x in re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1)) if x)
        m = re.search(r'年份[:：]?&nbsp;?\s*</span>\s*<a[^>]*>(\d{4})</a>', html)
        if m:
            year = m.group(1)
        m = re.search(r'地区[:：]?&nbsp;?\s*</span>\s*<a[^>]*>([^<]{1,12})</a>', html)
        if m:
            area = m.group(1).strip()
        content = ''
        m = re.search(r'短评[:：]?&nbsp;\s*([^<]{1,4000})', html)
        if m:
            content = m.group(1).strip()
        if not content:
            m = re.search(r'<div class="mo-word-info[^"]*"[^>]*>(.*?)</div>', html, re.S)
            content = txt(m.group(1)) if m else ''
        return {
            'vod_id': vid,
            'vod_name': name or ('影片' + vid),
            'vod_pic': self._pic(pic),
            'vod_year': year,
            'vod_area': area,
            'vod_actor': actor,
            'vod_director': director,
            'vod_content': content,
        }

    def _lines(self, html, vid):
        # 站点结构：一个 mo-sort-head 的 h2 里并排放着 N 个 mo-movs-btns（线路切换按钮），
        # 下面紧跟 N 个 mo-movs-item（每个是一路的剧集列表），两者按 HTML 顺序一一对应。
        # 实测电影 10 个按钮 / 10 个剧集块，电视剧 1 个按钮 / 1 个块 —— 所以只能按
        # mo-movs-item 切块，再按序号取按钮文字当线路名；按 mo-sort-head 切会只剩 1 条线路。
        t = str(html or '')
        labels = []
        for m in re.finditer(r'class="mo-movs-btns[^"]*"[^>]*>(.*?)</a>', t, re.S):
            lb = re.sub(r'<[^>]+>', '', m.group(1)).replace('&nbsp;', ' ').strip()
            if lb:
                labels.append(lb)
        lines, seen = [], set()
        for idx, blk in enumerate(t.split('mo-movs-item')[1:]):
            eps = []
            for m in re.finditer(r'href="/play/(\d+)_(\d+)_(\d+)\.html"[^>]*>(.*?)</a>', blk, re.S):
                if m.group(1) != vid:
                    continue
                ep = re.sub(r'<[^>]+>', '', m.group(4)).replace('&nbsp;', ' ').strip()
                pid = '%s_%s_%s' % (m.group(1), m.group(2), m.group(3))
                if pid in [x[1] for x in eps]:
                    continue
                eps.append((ep or ('第%s集' % m.group(3)), pid))
            if not eps:
                continue
            label = labels[idx] if idx < len(labels) else ''
            if not label:
                m = re.search(r'data-show="([^"]{1,20})"', blk)
                label = m.group(1).strip() if m else ''
            label = label or ('线路%d' % (len(lines) + 1))
            # 同名线路加序号，避免壳端把两条线路显示成一条
            base = label
            n = 2
            while label in seen:
                label = '%s(%d)' % (base, n)
                n += 1
            seen.add(label)
            lines.append((label, eps))
        return lines

    def _segments(self, label, eps):
        # 客户端 2048B 截断：单线 UTF-8 超 SEG 就切同名分段，段内 # 连续、段间顺序不变
        chunks, cur, size = [], [], 0
        for name, pid in eps:
            seg = '%s$%s' % (name, pid)
            b = len(seg.encode('utf-8')) + 1
            if cur and size + b > self.SEG:
                chunks.append(cur)
                cur, size = [], 0
            cur.append((name, pid))
            size += b
        if cur:
            chunks.append(cur)
        if len(chunks) <= 1:
            return [(label, '#'.join('%s$%s' % (n, p) for n, p in eps))]
        return [('%s(%d)' % (label, i + 1),
                '#'.join('%s$%s' % (n, p) for n, p in c)) for i, c in enumerate(chunks)]

    def _from_play(self, html):
        # data-play = 3 个随机前缀字符 + base64(直链)。
        # 前缀每次不同（ADy/FPb/YJk/PJq/USe/XOg 都见过），所以不能写死切片位置，
        # 从 0~8 逐个偏移试 base64，取第一个洗出 http 的结果。
        # 同时返回 data-parse 解析接口：CDN 死了时用它拼解析页兜底。
        t = str(html or '')
        api = ''
        m = re.search(r'data-parse="([^"]+)"', t)
        if m:
            api = m.group(1).strip()
        for pat in (r'data-play="([^"]+)"', r'data-play-src="([^"]+)"', r'data-url="([^"]+)"'):
            m = re.search(pat, t)
            if not m:
                continue
            raw = m.group(1).strip()
            if raw.startswith('http'):
                return raw, api
            got = self._b64url(raw)
            if got:
                return got, api
        m = re.search(r'(https?://[^"\'\s]+?\.m3u8[^"\'\s]*)', t)
        if m:
            return m.group(1), api
        return '', api

    def _b64url(self, raw):
        for cut in range(0, 9):
            s = raw[cut:]
            if len(s) < 12:
                break
            try:
                txt = base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8', 'ignore')
            except Exception:
                continue
            m = re.search(r'https?://[^\s"\'\\]+', txt)
            if m:
                return m.group(0)
        return ''

    def _pic(self, url):
        # 封面统一走本地代理：ynztctv.com 已停放、部分图床拒外部 Referer；
        # extend.img 给了模板就直接套（{url} 占位），方便换成自己的图床
        u = str(url or '').strip()
        if not u:
            return ''
        if u.startswith('//'):
            u = 'https:' + u
        if not u.startswith('http'):
            u = urljoin(self.base + '/', u)
        if self.img_tpl and '{url}' in self.img_tpl:
            return self.img_tpl.replace('{url}', quote(u, safe=''))
        return 'http://127.0.0.1:9978/proxy?do=img&ext=.jpg&url=' + quote(u, safe='')

    def _pg(self, pg):
        if isinstance(pg, (int, float)):
            return max(1, int(pg))
        s = str(pg or '1').strip()
        return max(1, int(s)) if s.isdigit() else 1
