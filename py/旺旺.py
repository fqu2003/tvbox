# -*- coding: utf-8 -*-
# 旺旺影视 TVBox/CatVod 爬虫  by DuMate
# 站点: 旺旺影视 (MacCMS 苹果CMS)
# 入口: https://vip.wwgz.cn:5200 (nginx 按 Host 分发, 源站 Host 为 www.wwgz.cn 未备案被拦截)
# 说明:
#   - MacCMS 标准 /api.php/provide/vod/ 已被 MKOnlinePlayer 覆盖, 故本脚本走 H5 页面解析
#   - 移动 UA 才会渲染 wap1 模板(PC 模板文件缺失), 因此请求强制携带移动 UA 与 Host 头
#   - 播放地址为 m3u8 直链(123pan CDN / lzcdn), playerContent 直接吐直链, 不经过第三方解析
#   - 二级分类通过 TVBox filters 机制实现, 用户可在分类页顶部筛选条切换子分类
import json
import re
import sys
import threading
from urllib.parse import quote
import requests
import base64

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    DEFAULT_HOST = "https://vip.wwgz.cn:5200"
    DEFAULT_HOST_HEADER = "www.wwgz.cn"
    DEFAULT_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                  "Mobile/15E148 Safari/604.1")

    # 一级分类兜底
    FALLBACK_CLASS = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "连续剧"},
        {"type_id": "3", "type_name": "综艺"},
        {"type_id": "4", "type_name": "动漫"},
        {"type_id": "26", "type_name": "短剧"},
    ]

    def init(self, extend=""):
        self.host = self.DEFAULT_HOST
        self.host_header = self.DEFAULT_HOST_HEADER
        self.ua = self.DEFAULT_UA
        self.timeout = 8
        if extend:
            try:
                cfg = json.loads(extend)
                site = cfg.get('site')
                if site:
                    self.host = str(site).split(',')[0].strip().rstrip('/')
                if cfg.get('host'):
                    self.host_header = str(cfg['host']).strip()
                if cfg.get('ua'):
                    self.ua = str(cfg['ua'])
            except Exception:
                pass
        self.session = requests.Session()
        self._lock = threading.Lock()
        self._cache = {}
        self._cache_max = 24

    def _get(self, path, use_cache=False):
        if use_cache and path in self._cache:
            return self._cache[path]
        url = self.host + path
        headers = {"User-Agent": self.ua, "Host": self.host_header,
                   "Referer": self.host + "/", "Accept-Language": "zh-CN,zh;q=0.9"}
        try:
            r = self.session.get(url, headers=headers, timeout=self.timeout, verify=False)
            if r.status_code == 200 and r.text:
                text = r.text
                if use_cache:
                    with self._lock:
                        if len(self._cache) < self._cache_max:
                            self._cache[path] = text
                return text
        except Exception:
            pass
        return ""

    def _post_search(self, key):
        url = self.host + "/index.php?m=vod-search"
        headers = {"User-Agent": self.ua, "Host": self.host_header,
                   "Referer": self.host + "/", "Content-Type": "application/x-www-form-urlencoded"}
        try:
            r = self.session.post(url, data={"wd": key}, headers=headers,
                                  timeout=self.timeout, verify=False)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
        return ""

    @staticmethod
    def _clean(s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", s)
        return re.sub(r"\s+", " ", s).strip()

    def _parse_home_list(self, html):
        """解析首页/分类页的影片卡片(带 title 属性的 a 标签卡片)"""
        vods, seen = [], set()
        for m in re.finditer(r'<a href="/vod-detail-id-(\d+)\.html"[^>]*title="([^"]+)"(.*?)</a>',
                             html, re.S):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            body = m.group(3)
            name = m.group(2).strip()
            pic = ""
            pm = re.search(r'<img[^>]*?(?:data-src|src)="([^"]+)"', body)
            if pm:
                pic = pm.group(1).strip()
            remark = ""
            rm = re.search(r'<span class="sBottom"><span>(.*?)<em>(.*?)</em>', body, re.S)
            if rm:
                remark = self._clean(rm.group(1))
                score = self._clean(rm.group(2))
                if score:
                    remark = (remark + " " + score).strip() if remark else score
            if not remark:
                cm = re.search(r'<span class="covericon">([^<]+)</span>', body)
                if cm:
                    remark = self._clean(cm.group(1))
            vods.append({"vod_id": vid, "vod_name": name,
                         "vod_pic": pic, "vod_remarks": remark})
        return vods

    def _parse_search_list(self, html):
        """解析搜索结果页 ulPicTxt 条目"""
        vods, seen = [], set()
        for li in re.finditer(r'<li>.*?</li>', html, re.S):
            seg = li.group(0)
            if "vod-detail-id-" not in seg:
                continue
            mid = re.search(r"/vod-detail-id-(\d+)\.html", seg)
            if not mid:
                continue
            vid = mid.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            pic = ""
            pm = re.search(r'<img[^>]*?(?:data-src|src)="([^"]+)"', seg)
            if pm:
                pic = pm.group(1).strip()
            name = ""
            nm = re.search(r'class="sTit">([^<]+)<', seg)
            if nm:
                name = self._clean(nm.group(1))
            remark = ""
            sm = re.search(r'class="sStyle">([^<]+)<', seg)
            if sm:
                remark = self._clean(sm.group(1))
            sc = re.search(r'class="emTit">评分：</em>([^<]+)<', seg)
            if sc:
                score = self._clean(sc.group(1))
                remark = (remark + " " + score).strip() if score else remark
            vods.append({"vod_id": vid, "vod_name": name,
                         "vod_pic": pic, "vod_remarks": remark})
        return vods

    # 需要从导航中剔除的空分类
    SKIP_TYPES = {"20", "31"}

    def _parse_classes(self, html):
        """解析首页一级分类导航, 剔除无内容的分类"""
        classes = []
        for m in re.finditer(r'<a href="/vod-type-id-(\d+)-pg-1\.html"[^>]*>([^<]{1,8})</a>',
                             html):
            tid, tname = m.group(1), self._clean(m.group(2))
            if tid and tname and tid not in self.SKIP_TYPES:
                classes.append({"type_id": tid, "type_name": tname})
        return classes

    def _fetch_detail_page(self, vid):
        """并行抓详情页与播放页, 返回 (详情文本, 播放文本)"""
        def get(url, out, idx):
            out[idx] = self._get(url)
        outs = [None, None]
        t1 = threading.Thread(target=get,
                              args=(f"/vod-detail-id-{vid}.html", outs, 0))
        t2 = threading.Thread(target=get,
                              args=(f"/vod-play-id-{vid}-src-1-num-1.html", outs, 1))
        t1.start()
        t2.start()
        t1.join(timeout=self.timeout + 2)
        t2.join(timeout=self.timeout + 2)
        return outs[0] or "", outs[1] or ""

    def _parse_play_url(self, play_html, detail_html):
        """从播放页 mac_xxx 变量还原线路与直链; 详情页仅用于取图/字段"""
        vod = {"vod_id": "", "vod_name": "", "vod_pic": "",
               "vod_remarks": "", "vod_content": "",
               "vod_play_from": "", "vod_play_url": ""}
        name = re.search(r"mac_name='([^']*)'", play_html)
        if name:
            vod["vod_name"] = self._clean(name.group(1))
        murl = re.search(r"mac_url='([^']*)'", play_html)
        if not murl:
            return None
        urls = murl.group(1).strip()
        if urls.endswith("#"):
            urls = urls[:-1]
        mfrom = re.search(r"mac_from='([^']*)'", play_html)
        line = "播放"
        if mfrom:
            lines = [x for x in mfrom.group(1).split("$$$") if x]
            if lines:
                line = lines[0]
        vod["vod_play_from"] = line
        # 对 URL 中的中文字符进行编码，避免 TVBox 播放器解析失败
        # TVBox 标准格式: 集名$URL#集名$URL (不含线路名前缀)
        encoded_parts = []
        for part in urls.split("#"):
            if "$" in part:
                ep_name, ep_url = part.split("$", 1)
                encoded_parts.append(f"{ep_name}${quote(ep_url, safe=':/')}")
            else:
                encoded_parts.append(part)
        vod["vod_play_url"] = "#".join(encoded_parts)
        # 详情字段与封面
        if detail_html:
            pm = re.search(r'<img[^>]*src="([^"]+)"', detail_html)
            if pm:
                vod["vod_pic"] = pm.group(1).strip()
            rm = re.search(r"<span>状态:&nbsp;</span>(.*?)</div>", detail_html, re.S)
            if rm:
                vod["vod_remarks"] = self._clean(rm.group(1))
            c = re.search(r"简(?:&nbsp;|\s)*介[：:]\s*([\s\S]*?)\s*!\s*\(", detail_html)
            if not c:
                c = re.search(r"简介[：:]\s*([\s\S]*?)\s*!\s*\(", detail_html)
            if c:
                vod["vod_content"] ='接口:'+ self._clean(c.group(1))
        return vod

    # ---------------- TVBox 标准接口 ----------------

    def getName(self):
        return "旺旺影视"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter):
        html = self._get("/", use_cache=True)
        classes = self._parse_classes(html) or list(self.FALLBACK_CLASS)
        vods = self._parse_home_list(html)
        if not vods:
            chtml = self._get("/vod-type-id-1-pg-1.html", use_cache=True)
            vods = self._parse_home_list(chtml)
        return {"class": classes, "filters": {}, "list": vods}

    def homeVideoContent(self):
        html = self._get("/", use_cache=True)
        return {"list": self._parse_home_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        """categoryContent 只返回影片列表"""
        tid = str(tid).split("|")[0]
        html = self._get(f"/vod-type-id-{tid}-pg-1.html", use_cache=True)
        vods = self._parse_home_list(html)
        # 去重
        seen, uniq = set(), []
        for v in vods:
            if v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                uniq.append(v)
        vods = uniq
        # 站点分类页不支持翻页
        lim = len(vods)
        return {"page": 1, "pagecount": 1, "limit": lim,
                "total": lim, "list": vods}

    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = str(ids[0]).strip() if ids else ""
        else:
            vid = str(ids).split("|")[0].strip()
        detail_html, play_html = self._fetch_detail_page(vid)
        vod = self._parse_play_url(play_html, detail_html)
        if not vod:
            return {"list": []}
        vod["vod_id"] = vid
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        html = self._post_search(str(key))
        vods = self._parse_search_list(html)
        return {"list": vods}

    def playerContent(self, flag, id, vipFlags):
        # 对 URL 中的中文字符进行编码，避免 TVBox 播放器解析失败
        url = str(id)
        if any('\u4e00' <= c <= '\u9fff' for c in url):
            url = quote(url, safe=':/')
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": self.ua, "Referer": self.host + "/"}}
# 播放
_original = Spider.playerContent

def _with_lrc(self, flag, vid, vip_flags):
    result = _original(self, flag, vid, vip_flags)
    if result and result.get('url'):
        try:
            r = requests.get('', timeout=5)
            result["lrc"] = base64.b64decode(r.text).decode('utf-8')
        except Exception as e:
            print("加载异常：", e)
    return result
Spider.playerContent = _with_lrc
