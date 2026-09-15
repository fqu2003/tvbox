# -*- coding: utf-8 -*-
"""
TVBox Python Spider for ljvod.com
基于 Pyramid / Chaquopy 方案，标准 base.spider.Spider 接口
"""

import re
import json
import requests
import base64
from urllib.parse import urljoin, quote
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    """ljvod.com 爬虫 - MacCMS V10 SSR 站点"""

    def __init__(self):
        self.host = "https://ljvod.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://ljvod.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def init(self, extend=""):
        """初始化，extend 可传入扩展配置"""
        pass

    def getName(self):
        return "龙江影院"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        """返回首页分类"""
        return {
            "class": [
                {"type_id": "1", "type_name": "电影"},
                {"type_id": "2", "type_name": "连续剧"},
                {"type_id": "3", "type_name": "综艺"},
                {"type_id": "4", "type_name": "动漫"},
                {"type_id": "27", "type_name": "短剧"},
                {"type_id": "20", "type_name": "理论片"},
            ]
        }

    def categoryContent(self, tid, pg, filter, extend):
        """分类页数据"""
        if pg == 1:
            url = f"{self.host}/type-{tid}/"
        else:
            url = f"{self.host}/type-{tid}-{pg}/"

        try:
            r = self.session.get(url, timeout=15)
            r.encoding = "utf-8"
            html = r.text
        except Exception:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        items = self._parse_list(html)
        return {
            "list": items,
            "page": pg,
            "pagecount": 999,
            "limit": 20,
            "total": 9999,
        }

    def searchContent(self, key, quick, pg=1, category=""):
        """搜索"""
        url = f"{self.host}/search--------------/"
        try:
            r = self.session.post(url, data={"wd": key}, timeout=15)
            r.encoding = "utf-8"
            html = r.text
        except Exception:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

        items = self._parse_list(html)
        return {
            "list": items,
            "page": pg,
            "pagecount": 999,
            "limit": 20,
            "total": 9999,
        }

    def detailContent(self, ids):
        """详情页，返回播放列表"""
        vod_id = ids[0]
        url = f"{self.host}/show-{vod_id}/"

        try:
            r = self.session.get(url, timeout=15)
            r.encoding = "utf-8"
            html = r.text
        except Exception:
            return {"list": []}

        detail = self._parse_detail(html, vod_id)
        return {"list": [detail]}

    def playerContent(self, flag, id, vipFlags):
        """解析播放页，返回 m3u8 地址"""
        try:
            r = self.session.get(id, timeout=15, headers=self.headers)
            r.encoding = "utf-8"
            html = r.text
        except Exception:
            return {"parse": 0, "url": "", "header": ""}

        m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S)
        if not m:
            return {"parse": 0, "url": "", "header": ""}

        try:
            data = json.loads(m.group(1))
            play_url = data.get("url", "")
            return {
                "parse": 0,
                "url": play_url,
                "header": json.dumps({
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.host + "/",
                }),
            }
        except Exception:
            return {"parse": 0, "url": "", "header": ""}

    # ---------- 内部解析方法 ----------

    def _parse_list(self, html):
        """解析列表页的影片卡片"""
        items = []
        # 匹配每个 vod-item 里的 /show-XXX/ 链接
        pattern = re.compile(
            r'<a\s+href="(/show-([A-Za-z0-9]+)/)"\s+title="([^"]*)".*?'
            r'data-original="([^"]*)".*?'
            r'<h4[^>]*>.*?<span>([^<]*)</span>',
            re.S
        )
        for m in pattern.finditer(html):
            items.append({
                "vod_id": m.group(2),
                "vod_name": m.group(3),
                "vod_pic": m.group(4),
                "vod_remarks": m.group(5).strip() if m.group(5) else "",
            })

        # 去重
        seen = set()
        uniq = []
        for it in items:
            if it["vod_id"] not in seen:
                seen.add(it["vod_id"])
                uniq.append(it)
        return uniq

    def _parse_detail(self, html, vod_id):
        """解析详情页，提取所有播放源"""
        # 标题
        title_m = re.search(r'<h1[^>]*>.*?<span[^>]*>([^<]*)</span>', html, re.S)
        title = title_m.group(1).strip() if title_m else ""

        # 封面
        pic_m = re.search(r'class="poster".*?data-original="([^"]*)"', html, re.S)
        pic = pic_m.group(1).strip() if pic_m else ""

        # 简介
        intro_m = re.search(r'class="intro-all"[^>]*>.*?<span>([^<]*)</span>', html, re.S)
        intro = intro_m.group(1).strip() if intro_m else ""

        # 播放源：按 .wi-play-list-box 分块
        play_from = []
        play_url = []

        # 找所有播放源容器
        box_pattern = re.compile(
            r'<div\s+class="[^"]*wi-play-list-box[^"]*".*?</div>\s*</div>\s*</div>',
            re.S
        )

        # 更稳定的方法：按源名和集数分别提取
        # 源名：h2.title
        src_names = re.findall(r'<h2\s+class="title">([^<]*)</h2>', html)

        # 所有播放链接，按顺序排列
        all_play_links = re.findall(
            r'<a\s+[^>]*href="(/play-[A-Za-z0-9]+-(\d+)-(\d+)/)"[^>]*>([^<]*)</a>',
            html
        )

        # 按 sid 分组
        grouped = {}
        for href, sid, nid, name in all_play_links:
            sid = int(sid)
            if sid not in grouped:
                grouped[sid] = []
            grouped[sid].append((int(nid), name.strip(), urljoin(self.host, href)))

        # 遍历每个源
        for idx, src_name in enumerate(src_names):
            sid = idx + 1
            if sid not in grouped:
                continue
            eps = sorted(grouped[sid], key=lambda x: x[0])
            ep_list = [f"{name}${url}" for _, name, url in eps]
            if ep_list:
                play_from.append(src_name.strip())
                play_url.append("#".join(ep_list))

        return {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": "接口:"+intro,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
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
