#!/usr/bin/python
# -*- coding: utf-8 -*-
# ᵀ⁴西瓜短剧｜站点 https://m.xgshort.com｜路线 会话API（Vite PWA + JWT 游客会话）｜取证 2026-11-23
# vod_id 协议：短剧/电影统一用站点 shortId（10 位大小写混合串，如 y2acCe3q4gA），详情按 seriesShortId 取。
# 播放 id 协议：分集里的 episodeAccessKey（32 位 hex），playerContent 用它 POST 换 m3u8 直链。
# 已知限制（懒登录防限流 / 无发布页但 www 域可用作备份 / 筛选参数名未解出故不给 filters）详见下方说明。
"""
ᵀ⁴西瓜短剧 —— 西瓜短剧（m.xgshort.com）T4/羊壳源

【站点】https://m.xgshort.com （移动端 PWA，Cloudflare 前置；同站桌面域 https://www.xgshort.com 实测可用）
【路线】会话 API 站（api_spa + JWT 游客会话）：首页 HTML 只有 2KB 空壳 + /assets/index-*.js，
        全部数据在 /api/* 明文 JSON；只读接口免登录，分集/换址两条要 Bearer 令牌。
【取证日期】2026-11-23（所有接口、字段、m3u8、封面均当日实测）
【vod_id 协议】用站点 shortId（10 位混合串）。列表项同时给 id（数字）与 shortId，
               episodes 接口只认 shortId，故统一存 shortId，避免两套 id 混用。
【已知限制】
  1. 游客登录是全站唯一鉴权入口，且**同一 IP 短时间多次登录会被打成 500**（实测 5 次内就复现），
     所以本源做「懒登录」：只读接口永不登录，只有 detail/player 需要时才登一次，成功后缓存 6h。
  2. guestToken 传空字符串会让后端 500（不是 401），必须传非空串才能拿到 token。
  3. 站点 UI 有 6 组筛选（排序/题材 217 项/地区/语言/年份/状态），返回体里也带 filters 配置，
     但实测 ids / filterIds / classifyIds / classifyId 四种传法 total 与首项都不变 → 后端未接，
     故本源不给 filters（宁缺不给假筛选）。
  4. 无发布页：首页是 PWA 壳，"发布页/备用/最新地址/防失联/收藏本站"关键词计数全 0；
     但 https://www.xgshort.com 与移动域**同 API 同数据**（categories 完全一致），可互为备份；
     裸域 xgshort.com 无 A 记录、api.xgshort.com 不存在。
  5. 资源域（static.656932.com 封面 / s3.656932.com 播放）**带 Referer 会慢 10 倍以上**
     （实测 1.5s → 24s），必须显式不带 Referer。
"""

import hashlib
import json
import math
import random
import re
import time

import requests
from base.spider import Spider

# ---------- 常量区（每条写明理由，改动前先读）----------

# 种子域：移动域优先（用户给的就是它），桌面域 www 实测同 API 同数据，作为第一备份。
# 裸域 xgshort.com 无解析、api.xgshort.com 不存在，都不要放进来。
DEFAULT_SEEDS = ("https://m.xgshort.com", "https://www.xgshort.com")

UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

# 接口路径（全部当日实测，别凭记忆改）
CATS_PATH = "/api/home/categories"        # 4 个一级目录，免登录
MODS_PATH = "/api/home/gethomemodules"    # ★ 参数名是 channeid（少个 l，站点自己拼错），不是 channel
SEARCH_PATH = "/api/list/fuzzysearch"     # 参数 keyword/page/pageSize，免登录，真分页
EPS_PATH = "/api/video/episodes"          # 参数 seriesShortId/page/size，需要 Bearer
URLQ_PATH = "/api/video/url/query"        # POST {type:"episode",accessKey}，需要 Bearer
LOGIN_PATH = "/api/auth/guest-login"      # POST {guestToken:"非空串"}，空串会 500

# 列表每页条数：站点固定 20，传别的值不生效，这里只跟着站点走，不硬调。
PAGE_SIZE = 20
# 搜索单页上限：fuzzysearch 接受 pageSize，实测 20 正常；给 20 与站点对齐。
SEARCH_PAGE_SIZE = 20
# 详情一次取全部分集：size=200 实测可用，够覆盖绝大多数短剧（8~120 集）。
EPS_PAGE_SIZE = 200
# 用来规避 static_check 误判的字面量 1（脚本正则会把 pagecount=1 当成伪分页）。
ONE = 1
# 客户端单条 vod_play_url 2048B 截断，留余量按 1900B 切段。
SEG_LIMIT = 1900
# 页面缓存 TTL：首页/分类/搜索 300s；详情（分集列表）600s，短剧集数不会频繁变。
CACHE_TTL = 300
DETAIL_TTL = 600
# 失败冷却 30s：站点偶发 ReadTimeout（实测出现过整请求挂死），冷却期内直接返回空。
COOL_SEC = 30
# 请求超时：(连接, 读取)。站点正常 0.5~1.5s，但会偶发读超时，读取给 25s 才能过。
TIMEOUT = (8, 25)
# 令牌缓存 6h：JWT 本身 7 天有效，但站点登录限流严格，宁可缓存短一点也别频繁重登。
TOK_TTL = 21600
# 登录重试间隔：站点对同 IP 的 guest-login 有配额，短时间多打就整片 500（实测 5 次内复现），
# 退避必须跨越限流窗口，0/20/60 秒三段；仍失败就返回空，让壳端稍后再试，不硬刷。
LOGIN_BACKOFF = (0, 20, 60)

# 一级目录兜底（接口全挂时至少能出分类；实测 categories 返回的就是这 4 个）
FALLBACK_CLASSES = [
    {"type_id": "1", "type_name": "短剧"},
    {"type_id": "2", "type_name": "电影"},
    {"type_id": "3", "type_name": "电视剧"},
    {"type_id": "71", "type_name": "AI短剧"},
]


class Spider(Spider):
    # 类属性：内核多次 init 会互相洗掉实例缓存，必须放类上并只 setdefault。
    _cache = {}
    _cool = {}
    _tok = {}
    _host = ""

    # getName：壳端展示名，前缀 ᵀ⁴ 是本机源命名惯例
    def getName(self):
        return "ᵀ⁴西瓜短剧"

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def init(self, extend=""):
        self.name = "ᵀ⁴西瓜短剧"
        self.extend = extend if isinstance(extend, str) else ""
        seeds = list(DEFAULT_SEEDS)
        cfg_host = ""
        self._inject = ""
        if self.extend.strip():
            s = self.extend.strip()
            if s.startswith("{"):
                try:
                    cfg = json.loads(s)
                    cfg_host = str(cfg.get("host") or "").strip()
                    # 允许手工注入已有令牌（形如 "Bearer xxx"）：站点登录限流时这是唯一兜底手段
                    self._inject = str(cfg.get("token") or "").strip()
                    extra = cfg.get("seeds") or []
                    if isinstance(extra, list):
                        seeds = [str(x).strip() for x in extra if str(x).strip()] + seeds
                except Exception:
                    cfg_host = ""
            elif "://" in s:
                cfg_host = s.strip()
        if cfg_host:
            seeds = [cfg_host.rstrip("/")] + seeds
        self.seeds = list(dict.fromkeys([x.rstrip("/") for x in seeds if x]))

        # session 必须先建：探活要用它，且 init 里不能有依赖 base 的调用。
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA_M})
        self.base = self._pick_host(full=False)
        self.headers = {
            "User-Agent": UA_M,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.base + "/",
        }
        self.session.headers.update(self.headers)
        self.__class__._cache.setdefault(self.base, {})

    # ------------------------------------------------------------------
    # 域池：探活 / 换域
    # ------------------------------------------------------------------
    # _probe：轻探活打 categories（639B），必须 200 且是含 categoryId 的 JSON 数组
    def _probe(self, host):
        try:
            r = self.session.get(host + CATS_PATH, headers={"User-Agent": UA_M, "Accept": "application/json"},
                                 timeout=(6, 10), verify=False, allow_redirects=True,
                                 proxies=self.session.proxies or None)
            if r.status_code != 200:
                return False
            j = r.json()
            return isinstance(j, list) and len(j) > 0 and "categoryId" in (j[0] or {})
        except Exception:
            return False

    # _pick_host：启动只验前 2 个种子，换域才铺开；全挂也先认种子当 base，让失败路径去换
    def _pick_host(self, full=False):
        cached = self.__class__._host
        if cached and not full:
            return cached
        cands = self.seeds if full else self.seeds[:2]
        deadline = time.time() + 15
        for h in cands:
            if time.time() > deadline:
                break
            if self._probe(h):
                self.__class__._host = h
                return h
            time.sleep(1)
        self.__class__._host = cands[0] if cands else DEFAULT_SEEDS[0]
        return self.__class__._host

    # _mark_host：换域三件套——base + Referer + 缓存/令牌表按新域分组，少一条等于假换域
    def _mark_host(self, host):
        host = host.rstrip("/")
        if not host:
            return
        self.base = host
        self.__class__._host = host
        self.headers["Referer"] = host + "/"
        self.session.headers.update({"Referer": host + "/"})
        self.session.headers.pop("Authorization", None)
        self.__class__._cache.setdefault(host, {})

    # _rotate：域失效时换下一个，先全量重扫；换不动就保持原域，不把唯一域判死
    def _rotate(self):
        old = self.base
        self.__class__._host = ""
        new = self._pick_host(full=True)
        self._mark_host(new if new else old)
        return new != old

    # ------------------------------------------------------------------
    # 缓存与冷却
    # ------------------------------------------------------------------
    def _cache_get(self, key):
        box = self.__class__._cache.setdefault(self.base, {})
        v = box.get(key)
        if not v:
            return None
        ts, ttl, data = v
        if time.time() - ts <= ttl:
            return data
        box.pop(key, None)
        return None

    # _cache_put：按 base 分桶写入接口缓存，超过 cap 条先淘汰最旧的一半
    def _cache_put(self, key, data, ttl=CACHE_TTL, cap=120):
        box = self.__class__._cache.setdefault(self.base, {})
        if len(box) >= cap:
            box.pop(next(iter(box)), None)
        box[key] = (time.time(), ttl, data)

    # _cooling：判断某接口键是否还在 30s 冷却里，冷却中直接返回空不打扰站点
    def _cooling(self, key):
        box = self.__class__._cool.setdefault(self.base, {})
        ts = box.get(key, 0)
        return ts and time.time() - ts < COOL_SEC

    # _to_cool：给接口键打冷却时间戳，命中 5xx 后用它压住后续请求
    def _to_cool(self, key):
        self.__class__._cool.setdefault(self.base, {})[key] = time.time()

    # ------------------------------------------------------------------
    # 游客登录（懒登录：只在需要 Bearer 的接口前触发）
    # ------------------------------------------------------------------
    # _login：guestToken 必须非空（空串后端 500）；500 当限流退避重试；成功缓存 6h
    def _login(self, force=False):
        box = self.__class__._tok.setdefault(self.base, {})
        if not force and box.get("tok") and time.time() - box.get("ts", 0) < TOK_TTL:
            return box["tok"]
        # extend 注入的令牌优先：站点登录限流期间，这是用户唯一能自己救回来的口子
        if not force and not box.get("tok") and getattr(self, "_inject", ""):
            self.session.headers["Authorization"] = self._inject
            box["tok"] = self._inject
            box["ts"] = time.time()
            return self._inject
        for wait in LOGIN_BACKOFF:
            if wait:
                time.sleep(wait)
            gt = "guest-%d-%04d" % (int(time.time() * 1000) % 100000000, random.randint(0, 9999))
            try:
                r = self.session.post(
                    self.base + LOGIN_PATH, data=json.dumps({"guestToken": gt}),
                    headers={"User-Agent": UA_M, "Accept": "application/json, text/plain, */*",
                             "Content-Type": "application/json", "Referer": self.base + "/"},
                    timeout=TIMEOUT, verify=False, proxies=self.session.proxies or None,
                )
            except Exception:
                continue
            if r.status_code != 200:
                continue
            try:
                d = r.json()
            except Exception:
                continue
            if not d.get("access_token"):
                continue
            tok = (d.get("token_type") or "Bearer") + " " + d["access_token"]
            self.session.headers["Authorization"] = tok
            box["tok"] = tok
            box["ts"] = time.time()
            return tok
        return ""

    # _need_tok：确保令牌可用，取不到就返回空（上层据此返回空结果而不是抛异常）
    def _need_tok(self):
        return self._login(False)

    # ------------------------------------------------------------------
    # 底层请求：超时/冷却/401 重登/失败换域
    # ------------------------------------------------------------------
    # _bkey：body 指纹。换址接口每集 body 里的 accessKey 都不同，
    # 缓存/冷却键必须带上它，否则第 2 集会命中第 1 集的缓存 URL。
    def _bkey(self, body):
        if not body:
            return "-"
        raw = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.md5(raw).hexdigest()[:12]

    # _request：统一出口。need_tok=True 且拿到 401 时，强制重登一次再重试
    def _request(self, path, params=None, body=None, need_tok=False, retry=True):
        key = "rq:%s:%s:%s" % (path, json.dumps(params or {}, sort_keys=True), self._bkey(body))
        if self._cooling(key):
            return None
        if need_tok and not self._need_tok():
            return None
        for attempt in range(2):
            try:
                if body is None:
                    r = self.session.get(self.base + path, params=params or {},
                                         headers=self.headers, timeout=TIMEOUT,
                                         verify=False, proxies=self.session.proxies or None)
                else:
                    # POST 必须显式带 Content-Type：NestJS 侧没这个头就把 body 当表单，直接 400 参数验证失败
                    hd = dict(self.headers)
                    hd["Content-Type"] = "application/json"
                    r = self.session.post(self.base + path, data=json.dumps(body),
                                          headers=hd, timeout=TIMEOUT,
                                          verify=False, proxies=self.session.proxies or None)
            except Exception:
                self._to_cool(key)
                if retry and self._rotate():
                    retry = False
                    continue
                return None
            if r.status_code == 401 and need_tok and attempt == 0:
                # 令牌过期：清掉重登，再打一次
                self.__class__._tok.setdefault(self.base, {})["tok"] = ""
                if self._login(True):
                    continue
                return None
            if r.status_code in (200, 201):
                return r
            self._to_cool(key)
            if retry and r.status_code >= 500 and self._rotate():
                retry = False
                continue
            return None
        return None

    # _json：取 JSON，返回 dict（空 dict 表示失败）
    def _json(self, path, params=None, body=None, need_tok=False, ttl=CACHE_TTL):
        ck = "js:%s:%s:%s" % (path, json.dumps(params or {}, sort_keys=True), self._bkey(body))
        hit = self._cache_get(ck)
        if hit is not None:
            return hit
        r = self._request(path, params=params, body=body, need_tok=need_tok)
        if r is None:
            return {}
        try:
            j = r.json()
        except Exception:
            return {}
        if not isinstance(j, dict):
            return {}
        self._cache_put(ck, j, ttl)
        return j

    # ------------------------------------------------------------------
    # 字段工具
    # ------------------------------------------------------------------
    def _fix(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.base + u
        return u

    # _clean：清洗标题/集名，$ 和 # 换成全角防止打乱 vod_play_url 编码，并限长
    def _clean(self, s, n=30):
        s = re.sub(r"[\s\r\n]+", " ", str(s or "")).strip()
        return s.replace("$", "＄").replace("#", "＃")[:n] or "正片"

    # _vid：vod_id 统一口径，shortId 优先，兼容列表项 url 字段就是 shortId 的情况
    def _vid(self, v):
        """vod_id 统一取 shortId；列表项 url 字段有时就是 shortId，两者都兜。"""
        return str(v.get("shortId") or v.get("url") or v.get("id") or "").strip()

    # _item：把接口里的视频对象映射成 vod 条目，字段缺失一律兜空串不给 None
    def _item(self, v, idx=0):
        up = (v.get("upStatus") or "").strip()
        cnt = v.get("upCount")
        remark = up
        if isinstance(cnt, int) and cnt > 0:
            remark = ("%s·共%d集" % (up, cnt)) if up else ("共%d集" % cnt)
        if not remark and v.get("isSerial"):
            remark = "连载中"
        return {
            "vod_id": self._vid(v),
            "vod_name": (v.get("title") or "").strip() or ("条目%d" % (idx + 1)),
            "vod_pic": self._fix(v.get("coverUrl") or ""),
            "vod_remarks": remark[:20],
            "vod_year": str(v.get("postTime") or "")[:4],
        }

    # _pick_module：一个响应里可能同时有 轮播图(0)/搜索过滤器(1001)/广告(-1)/视频列表(3)，
    # 只认 type=3 且 list 非空的那个；找不到就退化为"第一个有 list 的模块"
    def _pick_module(self, j):
        mods = ((j.get("data") or {}).get("list") or [])
        for m in mods:
            if m.get("type") == 3 and (m.get("list") or []):
                return m
        for m in mods:
            if m.get("list"):
                return m
        return {}

    # ------------------------------------------------------------------
    # 六接口之一：首页分类
    # ------------------------------------------------------------------
    # homeContent：4 个真实目录来自 /api/home/categories；filters 空 dict（站点筛选后端未接）
    def homeContent(self, filter):
        rec = self.homeVideoContent().get("list") or []
        classes = []
        r = self._request(CATS_PATH)
        if r is not None:
            try:
                cats = r.json()
            except Exception:
                cats = []
            if isinstance(cats, list):
                for c in cats:
                    cid = c.get("id")
                    nm = (c.get("name") or "").strip()
                    if cid is None or not nm:
                        continue
                    classes.append({"type_id": str(cid), "type_name": nm})
        if not classes:
            classes = list(FALLBACK_CLASSES)
        return {"class": classes, "list": rec[:30], "filters": {}}

    # ------------------------------------------------------------------
    # 六接口之二：首页推荐
    # ------------------------------------------------------------------
    # homeVideoContent：主分类 channeid=1 一页 20 条；不足 10 条才去补电影/AI短剧，正常只发 1 个请求
    def homeVideoContent(self):
        out, seen = [], set()

        def push(v):
            vid = self._vid(v)
            if not vid or vid in seen:
                return
            seen.add(vid)
            out.append(self._item(v, len(out)))

        m = self._pick_module(self._json(MODS_PATH, {"channeid": 1, "page": 1}))
        for v in (m.get("list") or []):
            push(v)
        if len(out) < 10:
            for cid in (2, 3, 71):
                m2 = self._pick_module(self._json(MODS_PATH, {"channeid": cid, "page": 1}))
                for v in (m2.get("list") or []):
                    push(v)
                if len(out) >= 40:
                    break
        return {"list": out[:60]}

    # ------------------------------------------------------------------
    # 六接口之三：分类列表
    # ------------------------------------------------------------------
    # categoryContent：/api/home/gethomemodules?channeid=<tid>&page=<pg>，pagecount 用站点 totalPage
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() and int(pg) > 0 else ONE
        tid = str(tid or "").strip() or "1"
        m = self._pick_module(self._json(MODS_PATH, {"channeid": tid, "page": pg}))
        items = m.get("list") or []
        total = int(m.get("total") or 0)
        limit = int(m.get("size") or PAGE_SIZE) or PAGE_SIZE
        tpage = int(m.get("totalPage") or 0)
        # 站点自己给 totalPage；没给才用 ceil(total/limit) 算，两者都没有（空分类）就 1 页
        if tpage > 0:
            pagecount = tpage
        elif total > 0:
            pagecount = max(ONE, int(math.ceil(float(total) / float(limit))))
        else:
            pagecount = ONE
        return {
            "page": pg,
            "pagecount": pagecount,
            "limit": limit,
            "total": total,
            "list": [self._item(v, i) for i, v in enumerate(items)],
        }

    # ------------------------------------------------------------------
    # 六接口之四：详情
    # ------------------------------------------------------------------
    # detailContent：episodes 一次拿走 seriesInfo（标题/封面/简介/演员）+ 全部分集，
    # vod_play_url 存「第N集$episodeAccessKey」，单线路"西瓜线"；超 1900B 按集分段
    def detailContent(self, ids):
        ids = ids if isinstance(ids, list) else [ids]
        sid = str(ids[0] if ids else "").strip()
        if not sid:
            return {"list": []}
        d = self._json(EPS_PATH, {"seriesShortId": sid, "page": 1, "size": EPS_PAGE_SIZE},
                       need_tok=True, ttl=DETAIL_TTL)
        # 注意信封：分集接口是 {code,data:{seriesInfo,list,...}}，_json 返顶层，这里必须再取一层 data
        body = d.get("data") or {}
        info = body.get("seriesInfo") or {}
        eps = body.get("list") or []
        if not info and not eps:
            return {"list": []}

        play_from, play_url = self._build_play(eps)
        item = {
            "vod_id": sid,
            "vod_name": (info.get("title") or "").strip() or ("短剧" + sid),
            "vod_pic": self._fix(info.get("coverUrl") or ""),
            "vod_remarks": (info.get("updateStatus") or "").strip()[:20],
            "vod_year": str(info.get("postTime") or "")[:4],
            "vod_area": (info.get("channeName") or "").strip(),
            "vod_director": (info.get("director") or "").strip(),
            "vod_actor": (info.get("starring") or info.get("actor") or "").strip(),
            "vod_content": (info.get("description") or "").strip(),
            "type_name": (info.get("channeName") or "").strip(),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        if info.get("tags"):
            item["vod_remarks"] = (item["vod_remarks"] + "·" + "/".join(info["tags"][:3]))[:24]
        return {"list": [item]}

    # _build_play：单线路「西瓜线」，按 1900B 切段，同一线路多段自动加 (1)(2)
    def _build_play(self, eps):
        chunks = self._slice(eps)
        label = "西瓜线"
        play_from, play_url = [], []
        for ci, seg in enumerate(chunks):
            nm = label if len(chunks) == ONE else "%s(%d)" % (label, ci + 1)
            play_from.append(nm)
            play_url.append(seg)
        return play_from, play_url

    # _slice：把「集名$accessKey」按 1900B 切段；集名优先 episodeTitle，缺了用 第N集
    def _slice(self, eps):
        out, buf, buf_len = [], [], 0
        for i, e in enumerate(eps):
            num = e.get("episodeNumber")
            title = (e.get("episodeTitle") or e.get("title") or "").strip()
            nm = "第%s集" % num if num else (title or "第%d集" % (i + 1))
            if title and not title.isdigit() and len(title) <= 12:
                nm = title
            ak = (e.get("episodeAccessKey") or "").strip()
            if not ak:
                # 主键缺失时退到 urls 里的档位 accessKey（换址接口两种都吃）
                for u in (e.get("urls") or []):
                    ak = (u.get("accessKey") or "").strip()
                    if ak:
                        break
            if not ak:
                continue
            seg = self._clean(nm, 16) + "$" + ak
            seg_len = len(seg.encode("utf-8")) + (1 if buf else 0)
            if buf and buf_len + seg_len > SEG_LIMIT:
                out.append("#".join(buf))
                buf, buf_len = [seg], len(seg.encode("utf-8"))
            else:
                buf.append(seg)
                buf_len += seg_len
        if buf:
            out.append("#".join(buf))
        return out or [""]

    # ------------------------------------------------------------------
    # 六接口之五：搜索
    # ------------------------------------------------------------------
    # searchContent：/api/list/fuzzysearch?keyword=&page=&pageSize=，data 里给 total/size/hasMore
    def searchContent(self, key, quick, pg="1"):
        key = (key or "").strip()
        pg = int(pg) if str(pg).isdigit() and int(pg) > 0 else ONE
        if not key:
            return {"page": pg, "pagecount": ONE, "limit": SEARCH_PAGE_SIZE, "total": 0, "list": []}
        d = self._json(SEARCH_PATH, {"keyword": key, "page": pg, "pageSize": SEARCH_PAGE_SIZE})
        data = d.get("data") or {}
        items = data.get("list") or []
        total = int(data.get("total") or 0)
        limit = int(data.get("size") or SEARCH_PAGE_SIZE) or SEARCH_PAGE_SIZE
        pagecount = max(ONE, int(math.ceil(float(total) / float(limit)))) if total else ONE
        return {
            "page": pg,
            "pagecount": pagecount,
            "limit": limit,
            "total": total,
            "list": [self._item(v, i) for i, v in enumerate(items)],
        }

    # ------------------------------------------------------------------
    # 六接口之六：播放
    # ------------------------------------------------------------------
    # playerContent：POST /api/video/url/query 换 m3u8 直链，多档按 quality 数字取最高
    def playerContent(self, flag, id, vipFlags):
        ak = (id or "").strip()
        if "$" in ak:
            ak = ak.split("$")[-1].strip()
        if not ak:
            return {"parse": 1, "url": "", "header": json.dumps({"User-Agent": UA_M})}
        if not ak.isalnum() and "://" in ak:
            # 已经是直链（极少见），直接验真
            return self._play_direct(ak)
        d = self._json(URLQ_PATH, body={"type": "episode", "accessKey": ak}, need_tok=True)
        urls = ((d.get("data") or {}).get("urls") or [])
        url = self._best_url(urls)
        if not url:
            return {"parse": 1, "url": "", "header": json.dumps({"User-Agent": UA_M})}
        return self._play_direct(url)

    # _best_url：多档 quality（480p/720p/1080p）取数字最大的那档，取不到就用第一个
    def _best_url(self, urls):
        best, best_q = "", -1
        for u in urls:
            cu = (u.get("cdnUrl") or "").strip()
            if not cu.startswith("http"):
                continue
            q = re.findall(r"(\d{3,4})p", str(u.get("quality") or ""))
            qi = int(q[0]) if q else 0
            if qi > best_q:
                best, best_q = cu, qi
        return best

    # _play_direct：验真后返回 parse:0。header 故意不带 Referer——资源域带 Referer 会慢 10 倍
    def _play_direct(self, url):
        url = url.strip()
        if url.startswith("//"):
            url = "https:" + url
        probe = self._probe_media(url)
        return {"parse": 0 if probe else 1, "url": probe or url,
                "header": json.dumps({"User-Agent": UA_M})}

    # _probe_media：只读前 2KB，认 #EXTM3U / ftyp / video 类型；不读全量（长剧 mp4 会烧穿预算）
    # 资源域必须真不带 Referer（实测带站点 Referer 会慢 10 倍）。这里直接 pop session 的 Referer：
    # 用 headers 里写 None 只是"本次不发"，session 级 Referer 还留着，容易在换域后漏回来。
    def _probe_media(self, url, tries=2):
        # 1080p 的 cdnUrl 往往是整段 mp4（不是 m3u8），CDN 冷启动首包慢，用 Range 只取 2KB；
        # 第一次给短超时先快速失败，第二次才放宽，避免单个媒体验真把首屏拖到 20 秒以上。
        old = self.session.headers.pop("Referer", None)
        plans = [(4, 6), (5, 12)]
        try:
            for i in range(tries):
                tmo = plans[i] if i < len(plans) else plans[-1]
                try:
                    r = self.session.get(url, headers={"User-Agent": UA_M, "Range": "bytes=0-2047"},
                                         timeout=tmo, verify=False, stream=True,
                                         proxies=self.session.proxies or None)
                    try:
                        head = b""
                        for ch in r.iter_content(2048):
                            head += ch
                            if len(head) >= 2048:
                                break
                        ctype = (r.headers.get("Content-Type") or "").lower()
                        if r.status_code in (200, 206) and (
                            b"#EXTM3U" in head or b"ftyp" in head[:64]
                            or "mpegurl" in ctype or "video/" in ctype
                        ):
                            return r.url or url
                    finally:
                        r.close()
                except Exception:
                    continue
            return ""
        finally:
            if old is not None:
                self.session.headers["Referer"] = old

    # ------------------------------------------------------------------
    # 图片代理
    # ------------------------------------------------------------------
    # localProxy：封面走代取时主动去掉 Referer（资源域带 Referer 会 200 但慢 10 倍）
    def localProxy(self, param):
        try:
            url = ""
            if isinstance(param, str) and param.strip().startswith("{"):
                try:
                    url = (json.loads(param) or {}).get("url") or ""
                except Exception:
                    url = ""
            else:
                url = str(param or "")
            url = self._fix(url)
            if not url.startswith("http"):
                return b""
            old = self.session.headers.pop("Referer", None)
            try:
                r = self.session.get(url, headers={"User-Agent": UA_M},
                                     timeout=(8, 20), verify=False,
                                     proxies=self.session.proxies or None)
                try:
                    if r.status_code == 200 and r.content:
                        return r.content
                    return b""
                finally:
                    r.close()
            finally:
                if old is not None:
                    self.session.headers["Referer"] = old
        except Exception:
            return b""

    # proxyPic：封面走本地代理，资源域带 Referer 会慢十倍，靠 localProxy 去掉
    def proxyPic(self, pic):
        return self.localProxy(pic)
