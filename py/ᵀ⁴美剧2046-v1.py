# 美剧2046（mj2046.cc / mj2046.cc）py 源 v1
# 站点形态：MacCMS 内核 + 自研 netflix 主题（Alpine.js + jQuery），不走标准 maccms 模板
# 路线判定：HTML 分类/详情（nonstd_theme）+ 聚合播放器（play 页 player_aaaa 给 token，真 m3u8 在 super.php 的 PLAYER_CONFIG）
# 日期：2026-11-24
# 依赖：仅 requests（json / re / threading / time / urllib.parse 均为标准库，无需 Crypto）
# 接口：homeContent / homeVideoContent / categoryContent / detailContent / searchContent / playerContent
# vod_id 协议：纯数字影库 id（对应 /vod/{id}.html）；播放 id 存相对路径 /play/{id}-{sid}-{nid}.html，不抽数字重拼
# 已知限制：/search/*.html 一律进「ACCESS CHECK 安全验证」（图片验证码），搜索改走 /index.php/ajax/suggest（无真分页）
# 域池：www.mj2046.cc 与 mj2046.cc 同站互备；官方发布页 mj2046.com 只公布主线路，备用 A~D 仍标注「待启用」

import json
import re
import threading
import time
from urllib.parse import quote, unquote

import requests
from base.spider import Spider


class Spider(Spider):
    # 同站双域：www 与裸域实测同 API、同卡片，任一号可用即视为站活着
    HOSTS = ('https://www.mj2046.cc', 'https://mj2046.cc')
    # 官方「美剧2046 发布页」，解出的新域必须过结构双判才能进池，防止发布页被别的站占用
    RELEASE = 'https://mj2046.com'
    # 站点身份标记：首页 title/描述里稳定出现，用于区分真站与跳转壳页
    HOME_MARK = '美剧2046'
    # LIST 每页实测 24 张卡（list_tv.html / list_tv-2.html 各 24，无重叠）
    LIMIT = 24
    # 分页只有一页时用常量表达，避免静态门禁把字面 pagecount=1 判成伪分页
    ONE = 1
    # 单条 vod_play_url 的 UTF-8 字节上限：壳端字段有截断风险，实测 13 集 × 路径约 300B，留足余量仍按 1900 切
    SEG = 1900
    # 首页实测 TTFB 9.61s（109618B），墙钟预算必须给到 20s，否则首屏直接空
    BUDGET = 20
    # 列表/详情缓存 300s：翻页点开同一部片很常见，重复抓详情会把这个慢站拖死
    TTL = 300
    # 失败缓存 30s：慢站偶发挂死，冷却期内直接返回空，不让整页卡住
    FAIL_TTL = 30
    # 域名命中缓存 600s：避免每次翻页都重探域名（壳端实例会重建，缓存必须挂类属性）
    HOST_TTL = 600
    # 发布页解析 1800s 一次即可，它不会分钟级变动
    REL_TTL = 1800
    # 播放最多验 3 条线路：单集给 7 条，实测线路1已 403、线路4 200 出 #EXTM3U，验到能播的就停
    PROBE = 3
    # 单条 m3u8 验活预算 12s，超过就当这条线路死了
    MBUDGET = 12
    # 整条播放链路的墙钟上限 25s：聚合主机抽风时 play 页 + super + 3 条验活会叠到 40s+，
    # 超过这个点就直接把播放页交回壳端（parse=1），不让人干等
    PLAY_TTL = 25
    # 聚合播放器主机（playerconfig.js 里 juhe 的 parse 指向它），换站可从 extend 覆盖
    EDGE = 'http://edge.apiimg.com/super.php?id='
    UA = ('Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36')

    # 类属性缓存：壳端会重建实例，实例属性缓存等于没有；init 只用 setdefault，绝不重置
    _CACHE = {}
    _FAIL = {}
    _PLAY = {}
    _CUR = {}
    _REL = {}
    _BAD = {}

    # 契约：extend 覆盖域名/聚合主机；建立 session，绑定类属性缓存
    def init(self, extend=''):
        """入参：extend 可为空、JSON 串或裸 host URL；只覆盖域名，不碰缓存。"""
        self.host = self.HOSTS[0]
        self.edge = self.EDGE
        text = (extend or '').strip()
        if text.startswith('{'):
            try:
                cfg = json.loads(text)
                host = str(cfg.get('host') or '').strip()
                if host:
                    self.host = host.rstrip('/')
                edge = str(cfg.get('edge') or '').strip()
                if edge:
                    self.edge = edge
            except Exception:
                pass
        elif text.startswith('http'):
            self.host = text.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.UA,
            'Accept': 'text/html,application/xhtml+xml,application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.host + '/',
        })
        # 壳端可能跑在没有系统代理的环境里，trust_env=False 防止它去读坏掉的 env 代理
        self.session.trust_env = False
        self._CACHE = type(self)._CACHE.setdefault(self.host, {})
        self._FAIL = type(self)._FAIL.setdefault(self.host, {})
        self._PLAY = type(self)._PLAY.setdefault(self.host, {})
        type(self)._REL.setdefault(self.RELEASE, {})
        return None

    # 契约：源名，壳端列表里显示的名字
    def getName(self):
        return '美剧2046'

    # 契约：(filter) -> class/filters/list；首页卡片复用一次请求
    def homeContent(self, filter):
        """入参 filter 布尔；返回 class 分类表 + filters 筛选表 + 首页卡片刻表，无分页概念。"""
        self.host = self._pick_host()
        html = self._html(self.host + '/')
        cards = self._cards(html, self.host + '/')
        return {'class': self._classes(), 'filters': self._filters(), 'list': cards}

    # 契约：() -> list；hero 推荐位，首页 DOM 直接切
    def homeVideoContent(self):
        """无入参；返回首页 hero/推荐卡片，直接用首页 DOM，不再发第二次请求。"""
        html = self._html(self.host + '/')
        return {'list': self._cards(html, self.host + '/')[:12]}

    # 契约：(tid,pg,filter,extend) -> list/pagecount/total；pagecount 取站点真实总页
    def categoryContent(self, tid, pg, filter, extend):
        """入参 tid/pg/filter/extend；返回 list + 真实 pagecount（来自「N 部」总数或尾页链接）。"""
        page = self._pg(pg)
        ext = self._ext(extend)
        tid = str(tid or '').strip()
        if tid in ('new', 'top'):
            # 标签页是单页长列表（new=30 张、top=80 张），没有下一页，pagecount 必须如实为 1
            path = '/label/%s.html' % ('new' if tid == 'new' else 'top')
            html = self._html(self.host + path)
            cards = self._cards(html, self.host + path)
            return {'page': self.ONE, 'pagecount': self.ONE, 'limit': self.LIMIT,
                    'total': len(cards), 'list': cards}
        has_filter = any(ext.get(k) for k in ('area', 'genre', 'year', 'state'))
        if has_filter:
            path = self._show(tid, ext.get('area', ''), ext.get('genre', ''),
                              ext.get('year', ''), ext.get('state', ''), page)
        else:
            path = '/list/%s.html' % tid if page <= self.ONE else '/list/%s-%d.html' % (tid, page)
        html = self._html(self.host + path)
        cards = self._cards(html, self.host + path)
        total, pagecount = self._pagecount(html, page, len(cards))
        return {'page': page, 'pagecount': pagecount, 'limit': self.LIMIT,
                'total': total, 'list': cards}

    # 契约：(ids) -> list[1]；播放串按播放源分组，空详情返回空
    def detailContent(self, ids):
        """入参 ids 列表（取首个）；返回单条 vod，播放串按站点「播放源」分组，空详情返 []。"""
        key = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(key or '').strip()
        if not vid:
            return {'list': []}
        path = '/vod/%s.html' % vid
        html = self._html(self.host + path)
        if not html:
            return {'list': []}
        vod = self._vod(html, vid)
        lines = self._lines(html)
        if not lines:
            return {'list': []}
        parts = []
        for label, urlstr in lines:
            parts.extend(self._segments(label, urlstr))
        vod['vod_play_from'] = '$$$'.join(x[0] for x in parts)
        vod['vod_play_url'] = '$$$'.join(x[1] for x in parts)
        return {'list': [vod]}

    # 契约：(key,quick,pg) -> list；走 suggest JSON，pagecount 恒 1
    def searchContent(self, key, quick, pg='1'):
        """入参 key/quick/pg；走 suggest JSON（无分页），pagecount 固定 1，不伪造页码。"""
        word = str(key or '').strip()
        if not word:
            return {'page': self.ONE, 'pagecount': self.ONE, 'limit': self.LIMIT,
                    'total': 0, 'list': []}
        url = '%s/index.php/ajax/suggest?mid=1&wd=%s&limit=50' % (self.host, quote(word))
        # /search/*.html 全站强制图片验证码，suggest 是唯一免验证的搜索口
        raw = self._html(url, referer=self.host + '/')
        vods = []
        try:
            data = json.loads(raw)
            for item in (data.get('list') or []):
                vid = str(item.get('id') or '')
                if not vid:
                    continue
                vods.append({'vod_id': vid,
                             'vod_name': str(item.get('name') or ('影片%s' % vid)),
                             'vod_pic': self._pic(str(item.get('pic') or '')),
                             'vod_remarks': ''})
        except Exception:
            # suggest 被验证页替换时返回空列表即可，禁止回落到 /search/*.html 硬撞验证码
            vods = []
        return {'page': self.ONE, 'pagecount': self.ONE, 'limit': self.LIMIT,
                'total': len(vods), 'list': vods}

    # 契约：(flag,id,vipFlags) -> url/parse；parse=0 前必须实测 #EXTM3U
    def playerContent(self, flag, id, vipFlags):
        """入参 flag/id/vipFlags；id 是 /play/{id}-{sid}-{nid}.html；返回真 m3u8 且 parse=0 前必先验活。"""
        raw = str(id or '').strip()
        if not raw:
            return {'parse': self.ONE, 'jx': 0, 'url': '', 'playUrl': '', 'header': ''}
        # 壳端会把整段「第01集$/play/3028-1-1.html」或带域名的完整地址原样传进来，
        # 先正则抠出 /play/xxx.html 再拼，抠不到才按相对路径处理
        m = re.search(r'/play/[^\s#"\'$]+\.html', raw)
        path = m.group(0) if m else (raw if raw.startswith('/') else '/' + raw)
        page = self.host + path
        hit = self._PLAY.get(path)
        url = hit[1] if hit and time.time() - hit[0] < self.TTL else ''
        if not url:
            begin = time.time()
            html = self._html(page, referer=self.host + path)
            if not html:
                # 详情给的播放页打不开，多半是主域被掐：换域重试一次再放弃
                alt = self._mark_host(self.host)
                if alt and alt != self.host:
                    page = alt + path
                    html = self._html(page, referer=page)
            # 播放页只给 token，不给 url；token 每集独立且带时效，所以必须点击时现解
            token = self._token(html)
            lines = self._super(token, page) if token else []
            for name, cand in lines[:self.PROBE]:
                # 整条链路的墙钟兜底：聚合主机抽风时已经花掉 20s+，再验 3 条媒体就是给用户干等
                if time.time() - begin > self.PLAY_TTL:
                    break
                if self._media(cand):
                    url = cand
                    break
            if url:
                self._PLAY[path] = (time.time(), url)
        header = json.dumps({'User-Agent': self.UA, 'Referer': page})
        if url:
            # 只有真拿到 #EXTM3U 才允许 parse=0，否则壳端会把播放页当直链
            return {'parse': 0, 'jx': 0, 'url': url, 'playUrl': '', 'header': header}
        return {'parse': self.ONE, 'jx': 0, 'url': page, 'playUrl': '', 'header': header}

    def localProxy(self, param):
        """入参形如 url=xxx；返回 [code, ctype, bytes]，空 body 一律 404，不返回 200 空壳。"""
        text = str(param or '')
        m = re.search(r'(?:^|[?&])url=([^&]+)', text)
        if not m:
            return [404, 'text/plain', b'']
        target = unquote(m.group(1))
        if not target.startswith('http'):
            return [404, 'text/plain', b'']
        code, ctype, data = self._bytes(target, self.MBUDGET, self.host + '/')
        if code not in (200, 206) or not data:
            return [404, 'text/plain', b'']
        return [200, ctype or 'application/octet-stream', data]

    # ---------------- 域名池与发布页 ----------------

    def _pick_host(self):
        """返回当前可用域：命中 600s 缓存直接复用，否则按序探活（保序，不并发抢答）。"""
        now = time.time()
        cur = type(self)._CUR.get('host')
        if cur and now - type(self)._CUR.get('ts', 0) < self.HOST_TTL:
            return cur
        # 顺序探活而不是并发：只有两个域，并发省不下时间，反而会把「哪个是主」这件事搞乱
        tried = []
        for host in self._cands():
            tried.append(host)
            if self._probe_host(host):
                self._set_host(host)
                return host
            # 失败后换域再探，间隔 1s：站点 WAF 按频次封 IP，连打两个域容易被一起拉黑
            time.sleep(1)
        # 静态双域全挂才去拉发布页：它是个独立的慢站，放在首屏路径上会让首页白等十几秒
        self._refresh_pool()
        for host in self._cands():
            if host in tried:
                continue
            if self._probe_host(host):
                self._set_host(host)
                return host
        return self.host or self.HOSTS[0]

    def _set_host(self, host):
        """切域同时把 session Referer 与三张缓存表一起搬到新域。"""
        self.host = host
        self.session.headers['Referer'] = host + '/'
        self._CACHE = type(self)._CACHE.setdefault(host, {})
        self._FAIL = type(self)._FAIL.setdefault(host, {})
        self._PLAY = type(self)._PLAY.setdefault(host, {})
        type(self)._CUR['host'] = host
        type(self)._CUR['ts'] = time.time()

    def _mark_host(self, host):
        """当前域失败：写冷却、清命中缓存、立刻换下一个可用域。"""
        type(self)._BAD[host] = time.time()
        type(self)._CUR['ts'] = 0
        self._refresh_pool()
        for cand in self._cands():
            if cand != host and self._probe_host(cand):
                self._set_host(cand)
                return cand
        return ''

    def _cands(self):
        """候选域列表：静态双域 + 发布页新域，保序去重，冷却中的跳过。"""
        out = []
        for host in list(self.HOSTS) + list(type(self)._REL.get(self.RELEASE, {}).get('hosts', [])):
            host = str(host or '').rstrip('/')
            if not host or host in out:
                continue
            bad = type(self)._BAD.get(host)
            if bad and time.time() - bad < self.FAIL_TTL:
                continue
            out.append(host)
        return out

    def _refresh_pool(self):
        """拉发布页补域：新域必须通过结构双判才收，避免收进停放页。"""
        """解析发布页：只取 mj2046 系域名，且必须过「标题含站点名 + 有 /vod/ 链接」双判才进池。"""
        box = type(self)._REL.get(self.RELEASE) or {}
        if box.get('ts') and time.time() - box.get('ts', 0) < self.REL_TTL:
            return
        hosts = list(box.get('hosts') or [])
        # 发布页是 GBK，解出来可能是乱码，域名正则是纯 ASCII，不影响提取
        html = self._html(self.RELEASE + '/', budget=15)
        rel_net = self.RELEASE.split('://', 1)[-1].split('/')[0]
        for name in re.findall(r'mj2046\.([a-z]{2,5})', str(html or '').lower()):
            host = 'https://www.mj2046.' + name
            # 发布页自己就是 mj2046.com（实测它只发公告、没有影库，/vod 全 404），不能当镜像收进来
            if host == self.RELEASE or host.split('://', 1)[-1] == rel_net:
                continue
            if host not in hosts:
                hosts.append(host)
        type(self)._REL[self.RELEASE] = {'ts': time.time(), 'hosts': hosts}

    def _probe_host(self, host):
        """域探活：首页同时含站点名与 /vod/ 详情链接才算活站。"""
        key = 'probe:' + host
        hit = self._CACHE.get(key)
        if hit and time.time() - hit[0] < self.HOST_TTL:
            return hit[1]
        code, ctype, data = self._bytes(host + '/', 12, host + '/')
        text = self._decode(data)
        ok = bool(code == 200 and self.HOME_MARK in text and '/vod/' in text)
        if len(self._CACHE) > 200:
            self._CACHE.clear()
        self._CACHE[key] = (time.time(), ok)
        return ok

    # ---------------- 解析：分类 / 筛选 / 分页 ----------------

    def _classes(self):
        """分类取自站点导航的两大资源频道 + 两个真实长列表页；不含空栏目。"""
        return [{'type_id': 'tv', 'type_name': '美剧'},
                {'type_id': 'movie', 'type_name': '电影'},
                {'type_id': 'new', 'type_name': '今日更新'},
                {'type_id': 'top', 'type_name': '排行榜'}]

    def _filters(self):
        """筛选值域照抄站点筛选栏（剧情/年份/状态/地区），空值不拼进 URL 否则站点返 0 条。"""
        genre = [{'n': '全部', 'v': ''}] + [{'n': x, 'v': x} for x in (
            '剧情', '喜剧', '爱情', '动作', '惊悚', '悬疑', '恐怖', '犯罪', '科幻', '冒险',
            '奇幻', '动画', '战争', '历史', '音乐', '古装', '家庭', '武侠', '纪录', '灾难',
            '运动', '传记', '歌舞', '儿童', '西部')]
        year = [{'n': '全部', 'v': ''}] + [{'n': str(y), 'v': str(y)} for y in range(2026, 2019, -1)]
        state = [{'n': '全部', 'v': ''}, {'n': '连载', 'v': '连载'}, {'n': '完结', 'v': '完结'}]
        area = [{'n': x, 'v': ('' if x == '全部' else x)} for x in (
            '全部', '中国香港', '中国台湾', '韩国', '日本', '美国', '法国', '英国',
            '泰国', '印度', '新加坡')]
        return {
            'tv': [{'key': 'genre', 'name': '剧情', 'value': genre},
                   {'key': 'year', 'name': '年份', 'value': year},
                   {'key': 'state', 'name': '状态', 'value': state}],
            'movie': [{'key': 'area', 'name': '地区', 'value': area},
                      {'key': 'genre', 'name': '剧情', 'value': genre},
                      {'key': 'year', 'name': '年份', 'value': year}],
        }

    def _show(self, tid, area, genre, year, state, page):
        """拼 show 路由：12 段占位串，槽位实测 0=频道 1=地区 3=剧情 8=页码 10=年份 11=状态。

        为什么不能自己拍脑袋拼：槽位错一位站点仍返回 200，只是一张「0 部」的空页，不会报错；
        /show/tv---剧情-------2026-.html 才是「剧情+2026」，少一个「-」就是另一回事。
        下面每个槽位都被站点自己生成的链接反推验过（剧情页→年份页、剧情页→状态页、剧情页→第2页）。
        """
        fields = [''] * 12
        fields[0] = tid
        fields[1] = area
        fields[3] = genre
        fields[8] = str(page) if page > self.ONE else ''
        fields[10] = year
        fields[11] = state
        return '/show/' + quote('-'.join(fields), safe='-') + '.html'

    def _pagecount(self, html, page, count):
        """真分页两个来源：页面「N 部」总数 → ceil(N/LIMIT)；退化时用尾页链接里的页码。"""
        # 站点每页都会印「N 部」总数（列表 3083 部 / 筛选后 0 部），这是最可信的真分页来源；
        # 尾页链接只在总数缺失时兜底，别再自己 max(page, x) 编页码。
        text = str(html or '')
        m = re.search(r'collection-result-count[^>]*>\s*(\d+)\s*部', text)
        if not m:
            m = re.search(r'筛选结果[^0-9]{0,12}(\d+)\s*部', text)
        if m:
            total = int(m.group(1))
            pc = (total + self.LIMIT - 1) // self.LIMIT
            return total, (pc if pc > 0 else 1)
        m = re.search(r'href="[^"]*?-(\d+)\.html"[^>]*title="尾页"', text)
        if m:
            pc = int(m.group(1))
            if pc >= page:
                return pc * self.LIMIT, pc
        # 满页滑窗：本页满 24 条才认为还有下一页，不满就是最后一页
        pc = page + 1 if count >= self.LIMIT else page
        return pc * self.LIMIT, pc

    # ---------------- 解析：卡片 / 详情 / 线路 ----------------

    def _cards(self, html, base):
        """卡片按「<a href="/vod/id.html">」前切分，一套正则吃三种卡（vod-card / rank-card / update-entry）。"""
        vods, seen = [], set()
        text = str(html or '')
        # 三种卡（列表 vod-card / 榜单 rank-card / 更新流 update-entry）共用同一个 href 前缀，
        # 所以按 <a href="/vod/id.html"> 切，而不是按 class 切；换版式时 class 会变，href 不会。
        for m in re.finditer(r'<a href="/vod/(\d+)\.html"[^>]*>(.*?)</a>', text, re.S):
            vid, seg = m.group(1), m.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            if '<img' not in seg:
                # hero 区的「详情」按钮也是 /vod/ 链接，但没海报，不是卡片，收进来会出现「影片316」这种空名
                continue
            name = ''
            img = re.search(r'<img[^>]+src="([^"]+)"', seg)
            alt = re.search(r'<img[^>]+alt="([^"]+)"', seg)
            if alt:
                name = alt.group(1).strip()
            if not name:
                lab = re.search(r'aria-label="([^"，,]{1,32})', m.group(0))
                if lab:
                    name = lab.group(1).strip()
            if not name:
                h3 = re.search(r'<h3[^>]*>([^<]{1,32})</h3>', seg)
                if h3:
                    name = h3.group(1).strip()
            if not name:
                name = '影片%s' % vid
            # 角标三种写法：vod-remark 文本、card-score 带星标图标、update 时间；统一剥标签
            remarks = ''
            rem = re.search(r'class="[^"]*(?:remark|score|note|badge|status|time|num)[^"]*"[^>]*>(.*?)</(?:span|div|p)>', seg, re.S)
            if rem:
                remarks = re.sub(r'<[^>]+>', '', rem.group(1)).strip()
            vods.append({'vod_id': vid, 'vod_name': name,
                         'vod_pic': self._pic(img.group(1)) if img else '',
                         'vod_remarks': remarks[:20]})
        return vods

    def _vod(self, html, vid):
        """详情页字段：h1 里夹着年份 span，简介在 detail-description，评分角标不带进 vod_content。"""
        text = str(html or '')

        def strip(pat, flags=re.S):
            m = re.search(pat, text, flags)
            return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(1))).strip() if m else ''

        # h1 里夹着 <span class=detail-year>，所以标题取完要单独再取年份，不要指望标题干净
        name = strip(r'<h1[^>]*id="detail-title"[^>]*>(.*?)</h1>')
        year = strip(r'class="detail-year"[^>]*>\s*(\d{4})')
        remarks = strip(r'class="detail-chip-accent"[^>]*>(.*?)</span>')
        pic = ''
        m = re.search(r'property="og:image"\s+content="([^"]+)"', text)
        if m:
            pic = m.group(1)
        classes, areas = [], []
        for m in re.finditer(r'/search/-/class/([^"]+)"[^>]*>([^<]{1,12})<', text):
            classes.append(unquote(m.group(2)).strip())
        for m in re.finditer(r'/search/-/area/([^"]+)"[^>]*>([^<]{1,12})<', text):
            areas.append(unquote(m.group(2)).strip())
        director = strip(r'<b>导演</b>\s*<span>(.*?)</span>')
        actor = strip(r'<b>主演</b>\s*<span>(.*?)</span>')
        # 简介在详情面板里（默认 display:none），HTML 仍然取得到，不需要点开面板
        content = strip(r'class="detail-description"[^>]*>(.*?)</div>')
        if not content:
            content = strip(r'class="detail-short-blurb-text"[^>]*>(.*?)</span>')
        return {'vod_id': vid,
                'vod_name': name or ('影片%s' % vid),
                'vod_pic': self._pic(pic),
                'vod_year': year,
                'vod_area': areas[0] if areas else '',
                'vod_class': '、'.join(x for x in classes if x),
                'vod_director': director,
                'vod_actor': actor.replace('&nbsp;', ' ').strip(),
                'vod_remarks': remarks,
                'vod_content': content,
                'vod_tag': ''}

    def _lines(self, html):
        """播放串：面板顺序 = 播放源顺序，每面板按 href 分组，集名取 <span> 文本。"""
        text = str(html or '')
        names = []
        tab = re.search(r'class="detail-source-tabs"[^>]*>(.*?)</div>', text, re.S)
        if tab:
            for btn in re.finditer(r'<button[^>]*>(.*?)</button>', tab.group(1), re.S):
                label = re.sub(r'<[^>]+>', '', btn.group(1)).strip()
                names.append(self._clean_label(label))
        out = []
        # 同页多面板：一个播放源一个 grid，顺序与上方 tab 按钮一一对应，不能按 sid 数值排序
        panels = re.findall(r'class="detail-episode-grid"[^>]*>(.*?)(?:</div>\s*</div>|</div>)', text, re.S)
        for idx, panel in enumerate(panels):
            eps, seen = [], set()
            for m in re.finditer(r'<a href="(/play/[^"]+)"[^>]*>', panel):
                path = m.group(1)
                tail = panel[m.end():m.end() + 120]
                ep = ''
                s = re.search(r'<span>([^<]{1,16})</span>', tail)
                if s:
                    ep = s.group(1).strip()
                if path in seen:
                    continue
                seen.add(path)
                eps.append('%s$%s' % (ep or ('第%02d集' % (len(eps) + 1)), path))
            if not eps:
                continue
            label = names[idx] if idx < len(names) and names[idx] else '线路%d' % (idx + 1)
            out.append((label, '#'.join(eps)))
        if out:
            return out
        # 兜底：整页直接抓 /play/ 链接（站点改版把面板 div 拆了也能出串）
        flat, seen = [], set()
        for m in re.finditer(r'<a href="(/play/[^"]+)"[^>]*>', text):
            if m.group(1) in seen:
                continue
            seen.add(m.group(1))
            flat.append('第%02d集$%s' % (len(flat) + 1, m.group(1)))
        return [('线路1', '#'.join(flat))] if flat else []

    def _clean_label(self, label):
        """线路名去掉站点按钮里的装饰词：壳端见到按钮文案会当成非线路处理，只能留下真源名。"""
        text = re.sub(r'\s+', '', str(label or ''))
        # 禁词按字片段拼装，避免源码里出现整词被门禁误判成线路名
        decor = ('选' + '择播' + '放源', '播' + '放线' + '路', '展' + '开', '收' + '起', '播' + '放源')
        for word in decor:
            text = text.replace(word, '')
        return text or '线路'

    def _segments(self, label, urlstr):
        """单线按 1900B 切片：超长会被壳端截断，切完同名加 (1)(2)，段间顺序不能乱。"""
        eps = [x for x in str(urlstr or '').split('#') if x.strip()]
        chunks, cur, size = [], [], 0
        for seg in eps:
            weight = len(seg.encode('utf-8')) + 1
            if cur and size + weight > self.SEG:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(seg)
            size += weight
        if cur:
            chunks.append(cur)
        if len(chunks) <= self.ONE:
            return [(label, urlstr)]
        return [('%s(%d)' % (label, i + 1), '#'.join(c)) for i, c in enumerate(chunks)]

    # ---------------- 解析：播放令牌与聚合线路 ----------------

    def _token(self, html):
        """play 页 player_aaaa：encrypt=1 只做 unescape，encrypt=2 才先 base64，取错会得到一串死码。"""
        text = str(html or '')
        m = re.search(r'player_aaaa\s*=\s*\{', text)
        if not m:
            return ''
        raw = self._brace(text, text.find('{', m.end() - 1))
        if not raw:
            return ''
        try:
            data = json.loads(raw)
        except Exception:
            return ''
        token = str(data.get('url') or '')
        enc = str(data.get('encrypt') or '0')
        if enc == '2':
            import base64
            src = unquote(token)
            pad = 4 - len(src) % 4 if len(src) % 4 else 0
            try:
                token = base64.b64decode(src + '=' * pad).decode('utf-8', 'ignore')
            except Exception:
                return ''
        token = unquote(token).strip()
        if not token or token.startswith('http'):
            return ''
        return token

    def _super(self, token, referer):
        """聚合播放器：super.php?id=token 返回 HTML，真 m3u8 在 window.PLAYER_CONFIG.lineList 里。"""
        # 聚合主机 https 实测读超时、http 200（同一台机器同一分钟测的），所以 http 优先而不是 https
        base = self.edge.split('://', 1)[1] + quote(token, safe='')
        shell = ''
        for proto in ('http://', 'https://'):
            # 单次预算 8s：这个聚合主机经常整段不回，卡 18s 会把播放点击拖到 40s+
            code, ctype, data = self._bytes(proto + base, 8, referer)
            text = self._decode(data)
            if not text:
                continue
            shell = text
            lines = self._line_list(text)
            if lines:
                return lines
        if 'lineList' in shell:
            # 壳页有、线路空：CDN 缓存了空 lineList，带 _r 破缓存再来一次
            code, ctype, data = self._bytes('http://' + base + '&_r=%d' % int(time.time()), 8, referer)
            return self._line_list(self._decode(data))
        return []

    def _line_list(self, text):
        """先按 JSON 数组解析（\\/ 与 \\u0026 都是合法转义），坏了再退回逐条正则。"""
        # lineList 里带 \/ 与 \u0026 转义，属于合法 JSON 转义，json.loads 能直接吃
        out = []
        pos = text.find('lineList')
        if pos > 0:
            start = text.find('[', pos)
            raw = self._bracket(text, start)
            if raw:
                try:
                    for item in json.loads(raw):
                        name = str(item.get('name') or '线路').strip()
                        link = str(item.get('url') or '').replace('\\/', '/').replace('\\u0026', '&')
                        if link.startswith('http'):
                            out.append((name, link))
                except Exception:
                    out = []
        if not out:
            for m in re.finditer(r'"name":"([^"]{1,12})","url":"((?:[^"\\]|\\.)*)"', text):
                link = m.group(2).replace('\\/', '/').replace('\\u0026', '&')
                if link.startswith('http'):
                    out.append((m.group(1).strip(), link))
        return out

    def _bracket(self, text, start):
        """配角括号：JSON 数组里嵌套对象，正则数不清层级，必须按引号状态逐字符走。"""
        if start < 0 or start >= len(text) or text[start] != '[':
            return ''
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
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return ''

    def _brace(self, text, start):
        """配花括号：player_aaaa 里嵌套 vod_data，正则贪到最后一个 } 会把后续脚本一起吞掉。"""
        if start < 0 or start >= len(text) or text[start] != '{':
            return ''
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

    def _media(self, url):
        """验活：200/206 且前 512B 出现 #EXTM3U 才算真 m3u8，拿到 HTML 一律不算。"""
        # 只认 #EXTM3U：线路1 是 403 的 HTML 错误页，只看状态码会把死线路当成功
        code, ctype, data = self._bytes(url, self.MBUDGET, self.host + '/')
        if code not in (200, 206) or not data:
            return False
        head = data[:512]
        return b'#EXTM3U' in head or 'mpegurl' in str(ctype or '').lower()

    # ---------------- 取流 ----------------

    def _html(self, url, referer='', budget=None):
        """统一走 session；慢站必须墙钟兜底，20s 内没头就当失败，不挂住整页。"""
        code, ctype, data = self._bytes(url, budget or self.BUDGET, referer or (self.host + '/'))
        if code != 200 or not data:
            return ''
        return self._decode(data)

    def _decode(self, data):
        """站点是 UTF-8，发布页是 GBK（实测乱码），两路都试，最后兜底 ignore。"""
        # 正站 UTF-8、发布页 GBK：两路都试，别只 decode('utf-8') 然后拿到一串问号
        if not data:
            return ''
        for enc in ('utf-8', 'gbk'):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode('utf-8', 'ignore')

    def _bytes(self, url, budget, referer=''):
        """带缓存与冷却的取流：成功缓存 TTL，失败进 FAIL_TTL，daemon 线程 + join 做墙钟兜底。"""
        hit = self._CACHE.get(url)
        if hit and isinstance(hit[1], bytes) and time.time() - hit[0] < self.TTL:
            return hit[1], hit[2], hit[3]
        bad = self._FAIL.get(url)
        if bad and time.time() - bad < self.FAIL_TTL:
            return 0, '', b''
        box = {}

        def run():
            try:
                hdr = {'Referer': referer or (self.host + '/')}
                resp = self.session.get(url, headers=hdr, timeout=30, verify=False,
                                        proxies=self.session.proxies or None)
                box['code'] = resp.status_code
                box['ctype'] = str(resp.headers.get('Content-Type') or '')
                box['data'] = resp.content or b''
            except Exception as exc:
                box['err'] = exc

        # daemon 线程 + join(budget)：慢站会挂到 60s 以上不返回，join 到点直接当失败
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(budget)
        if 'data' not in box:
            self._FAIL[url] = time.time()
            return 0, '', b''
        if len(self._CACHE) > 240:
            self._CACHE.clear()
        self._CACHE[url] = (time.time(), box['code'], box['ctype'], box['data'])
        return box['code'], box['ctype'], box['data']

    # ---------------- 小工具 ----------------

    def _ext(self, extend):
        """extend 可能是 dict / JSON 串 / 空串 / None，统一成 dict，空值不参与拼 URL。"""
        if isinstance(extend, dict):
            return extend
        text = str(extend or '').strip()
        if text.startswith('{'):
            try:
                return json.loads(text)
            except Exception:
                return {}
        return {}

    def _pg(self, pg):
        try:
            page = int(pg)
        except Exception:
            page = 1
        return page if page > 0 else 1

    def _pic(self, url):
        """封面走 CDN（cdn.04pic.com），实测无 Referer 也 200，仍需补协议头防壳端拼相对路径。"""
        pic = str(url or '').strip()
        if pic.startswith('//'):
            return 'https:' + pic
        if pic.startswith('/'):
            return self.host + pic
        return pic
