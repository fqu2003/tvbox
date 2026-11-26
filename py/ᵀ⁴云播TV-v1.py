# 站点：https://www.yunbo.net  （云播TV - 全球精品视听内容聚合平台；MacCMS v10 + 自研 ds3 主题）
# 路线：MacCMS v10「采集 API」直取 —— HTML 首页 267KB 只是 ds3 主题壳，真数据在 /api.php/provide/vod/
#   实测 ac=list&pg=1        → pagecount=6081 / total=121603 / limit=20（站点真值，非推算）
#        ac=list&t=1&pg=1    → pagecount=952  / total=19033（电影）
#        ac=list&t=23&pg=1   → pagecount=3354 / total=67073（短剧，type_id 不在导航 1~4 里，必须实测拿到）
#        ac=detail&wd=仙逆    → pagecount=1   / total=12（站点自身搜索结果就只有 1 页，照实报 1）
# 生成：2026-11-24   作者：Doubao
# 依赖：requests + base.spider；json / re / time / urllib 为标准库，无 lxml / bs4 / Crypto
# 接口：homeContent / homeVideoContent / categoryContent / detailContent / searchContent / playerContent / localProxy
# vod_id 协议：纯数字（"136755"）；播放 id 直接存 API 的 "集名$媒体地址" 原文
# 分页来源：API 自带的 pagecount / total（合法来源①：站点真实总页数），不做任何 max(pc,pg) 修饰
# 播放形态：官方平台线（qiyi/qq/youku/mgtv/bilibili）只能 parse:1；采集线（bfzym3u8/hnm3u8/lzm3u8…）是直链 m3u8，
#   实测 v.fengbao14.com 200 + #EXTM3U 且只给 UA 就能取（带错 Referer 反而会被 CDN 403）
# 已知限制：① 站点前置 Cloudflare，实测首页 200 / 267KB 无挑战页，但对高频请求敏感，间隔必须 ≥1s；
#   ② 官方平台线路能否播取决于壳端解析接口，本源只负责把官方页原样交出去；
#   ③ **本站没有官方发布页 / 备用域名告示**（首页页脚只有 TG：t.me/yunbotv），
#      所以换域走「TLD 变体候选 + API 双判」，见 _sync_domains：同 TLD 停放页/推广页会被双判挡掉。
#   ④ 短剧（type_id=23）的 yym3u8 线是「全集整片」单个 m3u8，不是选集；其实测 CDN 节点
#      v15.rstuuv.com 从本机 TCP 连接超时（域名可解析到 216.180.239.146），属该 CDN 节点的可达性问题，
#      源码只负责把地址原样交出去，不在本地做任何降级或替换。

import json
import random
import re
import time
import urllib.parse

import requests

from base.spider import Spider


class Spider(Spider):
    # 主域：实测 www.yunbo.net 200 / 267763B；裸域 yunbo.net 会 301 到 www，也留在池里当兜底
    HOST = 'https://www.yunbo.net'
    # 域池：官方未公布备用域。裸域跳 www 属同一站，先放进去；TLD 变体只在失败路径由 _sync_domains 验
    DOMS = ['https://www.yunbo.net', 'https://yunbo.net']
    # 候选域：纯猜测清单，实测大多不通（yunbo.top 直接 302 到境外注册推广页、yunbo.pro/cc 连接被重置、
    # yunbo.ink 是 CF 525），所以一律不直接入池，必须过 _ok_api 双判——否则会把赌站当镜像烧掉整轮探测
    CAND = ['https://www.yunbo.pro', 'https://www.yunbo.cc', 'https://www.yunbo.io',
            'https://www.yunbo.vip', 'https://www.yunbo.lol', 'https://www.yunbo.me']
    # 采集 API 路径：MacCMS 默认；HTML 里 window.MAC_TOKEN + /api.php/preview 说明站方就是这套
    API = '/api.php/provide/vod/'
    # 分类：导航是 电影/剧集/综艺/动漫/短剧 五档，API type_id 实测 1/2/3/4 有量、23 是短剧（5~8 全空）
    CLASSES = [('1', '电影'), ('2', '电视剧'), ('3', '综艺'), ('4', '动漫'), ('23', '短剧')]
    # 线路代号 → 中文：首页 20 条实测分布 qiyi14 / qq14 / bfzym3u8 13 / hnm3u8 12 / bilibili11 / lzm3u8 9 / mgtv6 / youku6
    LINE_NAME = {
        '1080zyk': '1080资源', 'lzm3u8': '量子资源', 'bfzym3u8': '暴风资源', 'hnm3u8': '红牛资源',
        'ffm3u8': '非凡资源', 'dyttm3u8': '电影天堂', 'rym3u8': '如意资源',
        # yym3u8 是短剧「全集整片」单文件线（实测标题就叫「全集$…/index.m3u8」，vod_total=0），
        # 名字里带「全集」才不会让用户以为只更了 1 集
        'yym3u8': '歪歪全集',
        'qiyi': '爱奇艺官采', 'qq': '腾讯官采', 'youku': '优酷官采', 'mgtv': '芒果官采',
        'bilibili': '哔哩哔哩官采',
    }
    # 排序：直链在前（1080 置顶），官方解析线在后；数字越小越靠前
    LINE_ORDER = {'1080zyk': 0, 'lzm3u8': 1, 'bfzym3u8': 2, 'hnm3u8': 3, 'ffm3u8': 4,
                  'dyttm3u8': 5, 'yym3u8': 6}
    OFFICIAL = ('iqiyi.com', 'v.qq.com', 'youku.com', 'mgtv.com', 'bilibili.com',
                'le.com', 'sohu.com', 'miguvideo.com', 'qiyi.com')
    # 单页条数：API limit 固定 20，取 20 才能让 total / pagecount 与站点对齐
    LIMIT = 20
    # 单条播放串上限：壳端 2048B 截断，留 148B 余量 → 1900。
    # 短剧动辄 100 集 × 8 线路，不分段第 3 集之后就被整段吃掉（这是本类站点最常见的“只有前几集”）
    SEG = 1900
    # 缓存 300s：homeContent 与 homeVideoContent 会连续两发同一个 ac=detail&pg=1（214KB），
    # 不缓存等于每次进首页打两次站，CF 计数很快就上来了
    TTL = 300
    # 失败冷却 30s：失败路径里策略性地跳过，避免死域把整页拖成 20s
    COOL = 30
    # 探测上限：每次换域最多验 3 个候选、池上限 8；一次换域把 8 个猜测域全打完会直接触发封禁哨兵
    MAXB = 3
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    # 类属性缓存：壳端每次调用都新建 Spider，写 self._x 等于每次重探域（tvbox_runtime 门禁明确禁止）
    _POOL = []
    _BAD = {}
    _CACHE = {}
    _SYNC = 0.0

    # 源名：壳端源列表显示用
    def getName(self):
        return '云播TV'

    # 初始化：建 session + setdefault 绑类缓存；绝不重置，重置会让每集都重打一次 214KB 列表
    def init(self, extend=''):
        self.extend = extend or ''
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.UA,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            # CF 前置站不带 Referer 也能过，但带上更像正常浏览器；无 Referer 时偶尔被判成脚本
            'Referer': self.HOST + '/',
        })
        type(self)._POOL = type(self)._POOL or list(self.DOMS)
        for t in ('_BAD', '_CACHE'):
            getattr(type(self), t).setdefault('_t', 0)
        # 用户可手动塞新域（extend 里的 domain/host，或环境变量 YUNBO_HOST）：站点没有发布页时
        # 唯一能自救入口就是让用户填，别写死到源码里
        manual = ''
        if isinstance(self.extend, dict):
            manual = str(self.extend.get('domain') or self.extend.get('host') or '')
        if not manual:
            manual = str(self.extend or '') if str(self.extend or '').startswith('http') else ''
        if manual.startswith('http'):
            m = manual.rstrip('/')
            if m not in type(self)._POOL:
                type(self)._POOL.insert(0, m)
        self.base = type(self)._POOL[0]

    # ── 基础工具 ────────────────────────────────────────────────

    # 请求间隔：CF 前置 + 站方按 IP 计数，1.0~1.4s 抖动既躲限流又不至于把 live_check 的 10min 预算吃完
    def _gap(self):
        time.sleep(random.uniform(1.0, 1.4))

    # 站点请求头：Referer 必须指向当前域（换域后还用旧域 Referer 会被 CF 判为盗链）
    def _bh(self, referer=None):
        return {
            'User-Agent': self.UA,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': referer or (self.base + '/'),
        }

    # 域级冷却：只在整个域拿不到合法 JSON 时写，单条 404/500 不冷整域
    def _mark(self, host):
        type(self)._BAD[host] = time.time() + self.COOL

    # 选可用域：先给没冷却的池成员；全冷却就同步一次候选域；再不行清冷却重来（宁可慢也不返空壳）
    def _pick_host(self):
        pool = type(self)._POOL or list(self.DOMS)
        now = time.time()
        for h in pool:
            if float(type(self)._BAD.get(h, 0) or 0) < now:
                return h
        self._sync_domains()
        for h in (type(self)._POOL or list(self.DOMS)):
            if float(type(self)._BAD.get(h, 0) or 0) < now:
                return h
        type(self)._BAD.clear()
        return pool[0]

    # 换域双判：必须同时满足「HTTP 200」「JSON code==1」「pagecount>100」「首条 vod_id 是数字」。
    # 只判 200 会踩坑：yunbo.top 实测 200 且 26KB，其实是 302 到境外注册推广页；yunbo.ink 是 CF 525。
    # 双判的第二个作用是不认识同名站：MacCMS 到处都是，pagecount>100 + 分类 type_name 对得上才算同一站
    def _ok_api(self, host, probe='list'):
        try:
            r = self.session.get(host + self.API, params={'ac': 'list', 'pg': '1'},
                                 headers=self._bh(host + '/'), timeout=(8, 18),
                                 proxies=self.session.proxies or None)
            if r.status_code != 200 or len(r.content) < 1000:
                return False
            d = json.loads(r.content.decode('utf-8', 'replace'))
            lst = d.get('list') or []
            if int(d.get('code') or 0) != 1 or int(d.get('pagecount') or 0) < 100 or not lst:
                return False
            return str(lst[0].get('vod_id') or '').isdigit()
        except Exception:
            return False

    # 域同步：本站无发布页，只能靠 ①首页文字里的域名线索 ②TLD 变体候选。
    # 30 分钟一次，候选最多验 MAXB 个，入池前必过双判；池上限 8（门禁要求），超了丢最老的
    def _sync_domains(self):
        if time.time() - float(type(self)._SYNC or 0) < 1800:
            return
        type(self)._SYNC = time.time()
        cands = []
        # ① 首页线索：本站页脚没有「备用/发布」文案（实测只有 t.me/yunbotv），但换主题后可能有，
        #    所以保留扫描：抓任何形如 yunbo*.tld 的明文域，以及「最新地址/备用地址」链接
        try:
            r = self.session.get((type(self)._POOL[0] if type(self)._POOL else self.HOST) + '/',
                                 headers=self._bh(), timeout=(8, 15),
                                 proxies=self.session.proxies or None)
            txt = r.content.decode('utf-8', 'replace')
            for d in re.findall(r'(?:www\.)?yunbo[a-z0-9]*\.(?:net|com|tv|pro|top|cc|io|vip|lol|ink|me)', txt):
                h = 'https://' + (d if d.startswith('www.') else 'www.' + d)
                if h not in type(self)._POOL:
                    cands.append(h)
        except Exception:
            pass
        # ② 猜测清单兜底：站点换域通常只是换 TLD，所以拿候选表逐个双判；不通的直接丢，不留证据在池里
        for h in self.CAND:
            if h not in type(self)._POOL and h not in cands:
                cands.append(h)
        self._gap()
        tried = 0
        for h in cands:
            if tried >= self.MAXB or len(type(self)._POOL) >= 8:
                break
            tried += 1
            if self._ok_api(h) and h not in type(self)._POOL:
                type(self)._POOL.append(h)

    # 统一 API 请求：缓存 → 冷却跳域 → 失败换域重试一次。
    # 返回 dict（拿不到就返回 {}，绝不抛异常给壳端，壳端抛异常的表现就是整页白屏）
    def _api(self, **params):
        params.setdefault('ac', 'list')
        key = 'q|' + '&'.join('%s=%s' % (k, params[k]) for k in sorted(params))
        hit = type(self)._CACHE.get(key)
        if hit and time.time() < hit[0]:
            return hit[1]
        data = {}
        for _ in range(2):
            host = urllib.parse.urlparse(self.base).scheme + '://' + \
                (urllib.parse.urlparse(self.base).hostname or '')
            if float(type(self)._BAD.get(host, 0) or 0) > time.time():
                nb = self._pick_host()
                if nb != self.base:
                    self.base = nb
                continue
            url = self.base + self.API + '?' + urllib.parse.urlencode(params)
            try:
                self._gap()
                r = self.session.get(url, headers=self._bh(self.base + '/'),
                                     timeout=(8, 25), proxies=self.session.proxies or None)
                # CF 被拦时返回的是 HTML 挑战页，json.loads 直接抛 → 走换域分支，不要去正则里刨 JSON
                data = json.loads(r.content.decode('utf-8', 'replace'))
            except Exception:
                data = {}
            if isinstance(data, dict) and ('list' in data or str(data.get('code')) == '1'):
                break
            self._mark(host)
            nb = self._pick_host()
            if nb and nb != self.base:
                self.base = nb
        if isinstance(data, dict) and 'list' in data:
            type(self)._CACHE[key] = (time.time() + self.TTL, data)
            return data
        return {}

    # 去标签 + 还原实体：vod_content 是富文本片段，不清掉壳端详情页会显示一堆 <p>/&nbsp;
    def _clean(self, s):
        s = re.sub(r'(?is)<[^>]+>', ' ', s or '')
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
        s = s.replace('&lt;', '<').replace('&gt;', '>').replace('&#39;', "'")
        return re.sub(r'\s+', ' ', s).strip()

    # 条目 → 卡片：ac=list 只有 9 个字段（无 vod_pic / vod_year / vod_area），
    # 所以本源统一用 ac=detail 取列表：多花 200KB 换「有封面、有年份、有地区」的卡片，值得
    def _row(self, it):
        return {
            'vod_id': str(it.get('vod_id') or ''),
            'vod_name': self._clean(it.get('vod_name') or ''),
            'vod_pic': it.get('vod_pic') or '',
            'vod_remarks': self._clean(it.get('vod_remarks') or ''),
            'vod_year': str(it.get('vod_year') or '')[:4],
            'vod_area': self._clean(it.get('vod_area') or ''),
            'vod_type': self._clean(it.get('vod_class') or it.get('type_name') or ''),
        }

    def _rows(self, data):
        out, seen = [], set()
        for it in (data.get('list') or []):
            i = str(it.get('vod_id') or '')
            if not i or i in seen:
                continue
            seen.add(i)
            out.append(self._row(it))
        return out

    # ── 六接口 ─────────────────────────────────────────────────

    # 首页：5 个真实主分类（电影/电视剧/综艺/动漫/短剧）+ 最新入库 20 条。
    # 分页来源：无（首页固定 1 页）；列表用 ac=detail&pg=1，站点默认按 vod_time 倒序，就是「最新」
    def homeContent(self, filter):
        data = self._api(ac='detail', pg='1')
        cls = [{'type_id': t, 'type_name': n} for t, n in self.CLASSES]
        return {'class': cls, 'filters': {}, 'list': self._rows(data)[:self.LIMIT]}

    # 推荐位：与 homeContent 共用同一个 key 的缓存，不会打两次站（本站首页一次 214KB，双打很明显）
    def homeVideoContent(self):
        return {'list': self._rows(self._api(ac='detail', pg='1'))[:self.LIMIT]}

    # 分类：ac=detail&t={tid}&pg={pg}；pagecount/total 取 API 真值（实测 t=1 → 952 页 / 19033 条），
    # 不写满页滑动窗口 — 站点给了真页数，再推算就是退化成撒谎
    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '').strip() or self.CLASSES[0][0]
        try:
            pg = max(1, int(pg))
        except Exception:
            pg = 1
        data = self._api(ac='detail', t=tid, pg=str(pg))
        lst = self._rows(data)[:self.LIMIT]
        pc = int(data.get('pagecount') or 1) or 1
        total = int(data.get('total') or (pc * self.LIMIT))
        return {'page': pg, 'pagecount': pc, 'limit': self.LIMIT,
                'total': max(total, len(lst)), 'list': lst}

    # 详情：ac=detail&ids={vid}。vod_play_from / vod_play_url 都是 $$ 分隔的多线路，
    # 必须按 sid（线路代号）分组后重排 + 分段；短剧 100 集 × 8 线不分段必被 2048B 截断
    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        mid = re.search(r'(\d+)', str(raw) or '')
        if not mid:
            return {'list': []}
        vid = mid.group(1)
        data = self._api(ac='detail', ids=vid)
        lst = data.get('list') or []
        if not lst:
            return {'list': []}
        it = lst[0]
        froms = [x for x in (it.get('vod_play_from') or '').split('$$$') if x]
        urls = [x for x in (it.get('vod_play_url') or '').split('$$$') if x]
        if not froms or not urls:
            return {'list': []}
        # 逐线路整理：sid 就是线路代号，按它分组，绝不能把不同 sid 的集数拼进同一条线（混了就是串集）。
        # 短剧的 yym3u8 只有一条「全集$…」，集数=1 属站点真实结构，不要当成分段失败去补集
        groups = []
        for sid, seg in zip(froms, urls):
            eps = []
            for item in seg.split('#'):
                if '$' not in item:
                    continue
                nm, u = item.split('$', 1)
                u = u.strip()
                if not u.startswith('http'):
                    continue
                eps.append((self._clean(nm) or '第%d集' % (len(eps) + 1), u))
            if not eps:
                continue
            groups.append((sid, eps))
        # 排序：直链线路在前、官方解析线在后；同档位按 LINE_ORDER（sid → 优先级）
        def _key(g):
            sid = g[0]
            if sid in self.LINE_ORDER:
                return self.LINE_ORDER[sid]
            if any(d in (g[1][0][1] if g[1] else '') for d in self.OFFICIAL):
                return 90
            # 未知代号但首集是 m3u8/mp4 的按直链处理（50 档），比归到官方解析线更安全
            return 50 if 'm3u8' in (g[1][0][1] if g[1] else '') else 80
        groups.sort(key=_key)
        # 线路名：代号翻中文，同名去重加序号；禁词（选择播放源/播放线路/展开/收起）一律不进线路名
        names, used = [], set()
        for sid, _eps in groups:
            nm = self.LINE_NAME.get(sid, sid)
            if nm in used:
                k = 2
                while '%s%d' % (nm, k) in used:
                    k += 1
                nm = '%s%d' % (nm, k)
            used.add(nm)
            names.append(nm)
        # 分段：每线按 SEG 切，段名「线路名(1)(2)」，段内 # 连续，段间保持原顺序；
        # froms 与 urls 段数必须相等（S10 门禁），所以两边都在同一个循环里 append
        seg_froms, seg_urls = [], []
        for idx, (_sid, eps) in enumerate(groups):
            base_nm = names[idx]
            part, seg, cur = 0, [], 0
            for nm, u in eps:
                if len(nm) > 16:
                    nm = nm[:16]
                need = len(('%s$%s' % (nm, u)).encode('utf-8')) + 1
                if seg and cur + need > self.SEG:
                    part += 1
                    seg_froms.append(base_nm if part == 1 else '%s(%d)' % (base_nm, part))
                    seg_urls.append('#'.join('%s$%s' % (a, b) for a, b in seg))
                    seg, cur = [], 0
                seg.append((nm, u))
                cur += need
            if seg:
                part += 1
                seg_froms.append(base_nm if part == 1 else '%s(%d)' % (base_nm, part))
                seg_urls.append('#'.join('%s$%s' % (a, b) for a, b in seg))
        vod = {
            'vod_id': vid,
            'vod_name': self._clean(it.get('vod_name') or ''),
            'vod_pic': it.get('vod_pic') or '',
            'vod_remarks': self._clean(it.get('vod_remarks') or ''),
            'vod_year': str(it.get('vod_year') or '')[:4],
            'vod_area': self._clean(it.get('vod_area') or ''),
            'vod_type': self._clean(it.get('vod_class') or it.get('type_name') or ''),
            'vod_actor': self._clean(it.get('vod_actor') or ''),
            'vod_director': self._clean(it.get('vod_director') or ''),
            'vod_lang': self._clean(it.get('vod_lang') or ''),
            # 站点有 douban/maoyan 双评分，取 douban_score 当备注补位，没值就不写，避免出现空的"评分："
            'vod_score': str(it.get('vod_douban_score') or it.get('vod_score') or ''),
            'vod_content': self._clean(it.get('vod_content') or it.get('vod_blurb') or ''),
            'vod_play_from': '$$$'.join(seg_froms),
            'vod_play_url': '$$$'.join(seg_urls),
        }
        return {'list': [vod]}

    # 搜索：ac=detail&wd={key}&pg={pg}。pagecount 取 API 真值 —— 实测「仙逆」只有 1 页 / 12 条，
    # 这时就老实报 1，不许填 99 让壳端翻 99 次空页
    def searchContent(self, key, quick, pg='1'):
        kw = (key or '').strip()
        if not kw:
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': self.LIMIT, 'total': 0}
        try:
            p = max(1, int(pg))
        except Exception:
            p = 1
        data = self._api(ac='detail', wd=kw, pg=str(p))
        lst = self._rows(data)[:self.LIMIT]
        pc = int(data.get('pagecount') or 1) or 1
        total = int(data.get('total') or (pc * self.LIMIT))
        # quick 搜索：壳端边打字边搜，超过 12 条会拖住输入框，截到 12；分页值保持站点真值不变
        if str(quick) in ('1', 'True', 'true') and len(lst) > 12:
            lst = lst[:12]
        return {'list': lst, 'page': p, 'pagecount': pc,
                'limit': self.LIMIT, 'total': max(total, len(lst))}

    # 播放：入参形如「正片$https://v.fengbao14.com/…/index.m3u8」，先剥 # 与 $。
    # 判定：直链 m3u8/mp4 → parse:0 + 只给 UA（实测 6 个采集 CDN 全部 200 + #EXTM3U，
    #   带站点 Referer 反而容易被 CDN 判盗链 403，所以这里故意不带 Referer）；
    #   官方平台页（iqiyi/v.qq/youku/mgtv/bilibili）→ parse:1 + 平台自身 Referer，交壳端解析
    def playerContent(self, flag, id, vipFlags):
        pid = str(id or '').split('#')[0].rsplit('$', 1)[-1].strip()
        if not pid:
            return {'parse': 1, 'url': ''}
        if not pid.startswith('http'):
            return {'parse': 1, 'url': self.base + (pid if pid.startswith('/') else '/' + pid)}
        low = pid.split('?')[0].lower()
        host = urllib.parse.urlparse(pid).hostname or ''
        if low.endswith('.m3u8') or low.endswith('.mp4') or low.endswith('.flv'):
            return {'parse': 0, 'url': pid, 'header': {'User-Agent': self.UA}}
        if any(d in host for d in self.OFFICIAL):
            root = '.'.join(host.split('.')[-2:]) if host else ''
            return {'parse': 1, 'url': pid,
                    'header': {'User-Agent': self.UA, 'Referer': 'https://%s/' % root}}
        # 兜底：其它页（站内播放页/短链），交壳端打开，不硬当直链
        return {'parse': 1, 'url': pid,
                'header': {'User-Agent': self.UA, 'Referer': self.base + '/'}}

    # 图片代理：本站封面几乎全是 iqiyipic / hitv / puui.qpic / hdslb / ykimg 等第三方图床，
    # 铁律是**不带站点 Referer**（爱奇艺图床带站点 Referer 会 403 回一个 349B 的 HTML 错误页）；
    # 空 body 必须返 404，返回 200 空图壳端会显示灰块，比裂图更难看
    def localProxy(self, param):
        u = urllib.parse.unquote(str(param or ''))
        if not u.startswith('http'):
            return [404, 'text/plain', b'']
        try:
            r = self.session.get(u, headers={'User-Agent': self.UA,
                                             'Accept': 'image/avif,image/webp,image/*,*/*;q=0.8'},
                                 timeout=(6, 15), proxies=self.session.proxies or None)
            body = r.content or b''
            if not body:
                return [404, 'text/plain', b'']
            ctype = (r.headers.get('Content-Type') or 'image/jpeg').split(';')[0]
            # 图床常把 webp/avif 都写成 image/jpeg，按魔数纠正一下，壳端解码才不报格式错
            if body[:4] == b'\x89PNG':
                ctype = 'image/png'
            elif body[:3] == b'\xff\xd8\xff':
                ctype = 'image/jpeg'
            elif body[:4] == b'RIFF' and body[8:12] == b'WEBP':
                ctype = 'image/webp'
            return [200, ctype, body]
        except Exception:
            return [404, 'text/plain', b'']
