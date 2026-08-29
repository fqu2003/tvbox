# -*- coding: utf-8 -*-
# 电影天堂 maccms 采集源适配 MV / FongMi Python Spider
# 支持自定义分类合并、子分类筛选、搜索、详情、m3u8 直链播放

import json
from datetime import datetime

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""):
            pass


MV_PLUGIN = {
    "id": "dytt",
    "name": "电影天堂",
    "version": "1.0.0",
    "profile": "python-spider-v1",
    "capabilities": {
        "content": True,
        "network": True,
    },
    "content_sources": [
        {
            "id": "main",
            "name": "电影天堂",
            "searchable": True,
            "quick_search": True,
            "filterable": True,
            "changeable": False,
        }
    ],
    "compatibility": {
        "upstream": "fongmi-spider-v1",
    },
}

SITE_API_FALLBACKS = [
    "https://dyttzy.tv/api.php/provide/vod",
    "https://www.dyttzy.tv/api.php/provide/vod",
    "http://dyttzy.tv/api.php/provide/vod",
    "http://www.dyttzy.tv/api.php/provide/vod",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

PAGE_LIMIT = 20

CATEGORY_CONFIG = {
    "1": {
        "name": "电影",
        "allIds": ["6", "7", "8", "9", "10", "11", "12", "20", "37", "34"],
        "types": [
            {"n": "全部", "v": "all"},
            {"n": "动作片", "v": "6"},
            {"n": "喜剧片", "v": "7"},
            {"n": "爱情片", "v": "8"},
            {"n": "科幻片", "v": "9"},
            {"n": "恐怖片", "v": "10"},
            {"n": "剧情片", "v": "11"},
            {"n": "战争片", "v": "12"},
            {"n": "记录片", "v": "20"},
            {"n": "动画片", "v": "37"},
            {"n": "伦理片", "v": "34"},
        ],
    },
    "2": {
        "name": "电视剧",
        "allIds": ["13", "16", "15", "22", "24", "14", "21", "23"],
        "types": [
            {"n": "全部", "v": "all"},
            {"n": "国产剧", "v": "13"},
            {"n": "欧美剧", "v": "16"},
            {"n": "韩剧", "v": "15"},
            {"n": "日剧", "v": "22"},
            {"n": "泰剧", "v": "24"},
            {"n": "港剧", "v": "14"},
            {"n": "台剧", "v": "21"},
            {"n": "海外剧", "v": "23"},
        ],
    },
    "3": {
        "name": "动漫",
        "allIds": ["29", "30", "31", "32", "33"],
        "types": [
            {"n": "全部", "v": "all"},
            {"n": "国产动漫", "v": "29"},
            {"n": "日韩动漫", "v": "30"},
            {"n": "欧美动漫", "v": "31"},
            {"n": "港台动漫", "v": "32"},
            {"n": "海外动漫", "v": "33"},
        ],
    },
    "4": {
        "name": "综艺",
        "allIds": ["25", "26", "27", "28"],
        "types": [
            {"n": "全部", "v": "all"},
            {"n": "大陆综艺", "v": "25"},
            {"n": "港台综艺", "v": "26"},
            {"n": "日韩综艺", "v": "27"},
            {"n": "欧美综艺", "v": "28"},
        ],
    },
    "5": {
        "name": "短剧",
        "allIds": ["36"],
        "types": [],
    },
}

EXCLUDE_CLASS_NAMES = ["伦理片"]


def _to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _format_videos(list_data):
    if not isinstance(list_data, list):
        return []
    result = []
    for item in list_data:
        if not isinstance(item, dict):
            continue
        vod_id = str(item.get("vod_id") or "")
        if not vod_id:
            continue
        result.append({
            "vod_id": vod_id,
            "vod_name": str(item.get("vod_name") or ""),
            "vod_pic": str(item.get("vod_pic") or ""),
            "type_id": str(item.get("type_id") or ""),
            "type_name": str(item.get("type_name") or ""),
            "vod_year": str(item.get("vod_year") or ""),
            "vod_remarks": str(item.get("vod_remarks") or ""),
        })
    return result


def _format_detail(list_data):
    if not isinstance(list_data, list):
        return []
    result = []
    for item in list_data:
        if not isinstance(item, dict):
            continue
        vod_id = str(item.get("vod_id") or "")
        if not vod_id:
            continue
        vod = {
            "vod_id": vod_id,
            "vod_name": str(item.get("vod_name") or ""),
            "vod_pic": str(item.get("vod_pic") or ""),
            "type_name": str(item.get("type_name") or ""),
            "vod_year": str(item.get("vod_year") or ""),
            "vod_area": str(item.get("vod_area") or ""),
            "vod_remarks": str(item.get("vod_remarks") or ""),
            "vod_actor": str(item.get("vod_actor") or ""),
            "vod_director": str(item.get("vod_director") or ""),
            "vod_content": str(item.get("vod_content") or "").strip(),
            "vod_play_from": str(item.get("vod_play_from") or ""),
            "vod_play_url": str(item.get("vod_play_url") or ""),
        }
        result.append(vod)
    return result


def _sort_key(item):
    time_str = str(item.get("vod_time") or item.get("vod_addtime") or item.get("vod_pubdate") or "")
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _safe_sort_time(item):
    key = _sort_key(item)
    return key if key is not None else None


class Spider(BaseSpider):
    def init(self, extend=""):
        self.config = self._parse_config(extend)

    @staticmethod
    def _parse_config(extend):
        if isinstance(extend, dict):
            return dict(extend)
        if isinstance(extend, str) and extend.strip():
            try:
                parsed = json.loads(extend)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _api_base(self):
        config = getattr(self, "config", {}) or {}
        base = str(config.get("api_url") or "").strip().rstrip("/")
        if base:
            return [base]
        return list(SITE_API_FALLBACKS)

    def _exclude_names(self):
        config = getattr(self, "config", {}) or {}
        value = str(config.get("exclude") or "").strip()
        if value:
            return [x.strip() for x in value.replace("|", ",").split(",") if x.strip()]
        return list(EXCLUDE_CLASS_NAMES)

    def fetch(self, url, timeout=3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code != 200:
                return ""
            return r.text
        except BaseException:
            return ""

    def _request_api(self, params, fast=False):
        parts = []
        for key, value in params.items():
            if value is None or value == "":
                continue
            parts.append(f"{key}={value}")
        query = "&".join(parts)
        bases = self._api_base()
        if fast:
            bases = bases[:1]
        for base in bases:
            url = f"{base}?{query}"
            html = self.fetch(url)
            if not html:
                continue
            try:
                data = json.loads(html)
                if data.get("code") == 1:
                    return data
            except Exception:
                pass
        return {}

    def _fetch_merged(self, group, page):
        exclude = self._exclude_names()

        def _should_exclude(name):
            name = str(name or "").strip()
            if not name:
                return False
            return any(kw in name for kw in exclude)

        all_ids = group.get("allIds", [])
        items = []

        def _fetch_one(type_id):
            data = self._request_api({
                "ac": "videolist",
                "t": type_id,
                "pg": str(page),
            }, fast=True)
            return data.get("list") or []

        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(all_ids))) as pool:
                results = list(pool.map(_fetch_one, all_ids))
            for sub in results:
                items.extend(sub)
        except Exception:
            for type_id in all_ids:
                items.extend(_fetch_one(type_id))

        filtered = [item for item in items if item and not _should_exclude(item.get("type_name"))]

        valid = []
        for item in filtered:
            key = _safe_sort_time(item)
            valid.append((key, item))
        valid.sort(key=lambda pair: (pair[0] is not None, pair[0]), reverse=True)
        sorted_items = [pair[1] for pair in valid]

        start = (page - 1) * PAGE_LIMIT
        end = start + PAGE_LIMIT
        slice_items = sorted_items[start:end]

        return {
            "page": page,
            "pagecount": max(1, -(-len(sorted_items) // PAGE_LIMIT)),
            "total": len(sorted_items),
            "list": _format_videos(slice_items),
        }

    def homeContent(self, filter):
        classes = [
            {"type_id": tid, "type_name": cfg["name"]}
            for tid, cfg in CATEGORY_CONFIG.items()
        ]

        filters = {}
        for tid, cfg in CATEGORY_CONFIG.items():
            types = cfg.get("types") or []
            if not types:
                continue
            filters[tid] = [{
                "key": "cate",
                "name": "类型",
                "value": types,
            }]

        try:
            data = self._request_api({
                "ac": "videolist",
                "pg": "1",
                "pagesize": "60",
                "limit": "60",
            }, fast=True)
            return {
                "class": classes,
                "list": _format_videos(data.get("list") or []),
                "filters": filters,
            }
        except BaseException:
            return {"class": classes, "list": [], "filters": filters}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1

        try:
            group = CATEGORY_CONFIG.get(tid)
            if not group:
                data = self._request_api({
                    "ac": "videolist",
                    "t": tid,
                    "pg": str(page),
                })
                return {
                    "list": _format_videos(data.get("list") or []),
                    "page": _to_int(data.get("page")) or page,
                    "pagecount": _to_int(data.get("pagecount")) or 1,
                    "total": _to_int(data.get("total")),
                }

            if isinstance(extend, dict):
                selected = str(extend.get("cate") or "").strip()
            else:
                selected = ""
            if selected and selected != "all" and selected in group.get("allIds", []):
                data = self._request_api({
                    "ac": "videolist",
                    "t": selected,
                    "pg": str(page),
                })
                return {
                    "list": _format_videos(data.get("list") or []),
                    "page": _to_int(data.get("page")) or page,
                    "pagecount": _to_int(data.get("pagecount")) or 1,
                    "total": _to_int(data.get("total")),
                }

            return self._fetch_merged(group, page)
        except Exception:
            return {
                "list": [],
                "page": page,
                "pagecount": 1,
                "total": 0,
            }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1

        data = self._request_api({
            "ac": "list",
            "wd": key,
            "pg": str(page),
        })
        videos = _format_videos(data.get("list") or [])
        if videos and not videos[0].get("vod_pic"):
            ids = ",".join(v["vod_id"] for v in videos)
            detail = self._request_api({"ac": "detail", "ids": ids})
            videos = _format_videos(detail.get("list") or [])

        return {
            "list": videos,
            "page": page,
            "pagecount": _to_int(data.get("pagecount")) or 1,
            "limit": PAGE_LIMIT,
            "total": _to_int(data.get("total")),
        }

    def detailContent(self, ids):
        if isinstance(ids, list):
            ids = ids[0] if ids else ""
        if not ids:
            return {"list": []}
        data = self._request_api({"ac": "detail", "ids": ids})
        videos = _format_detail(data.get("list") or [])
        if not videos:
            return {"list": []}
        vod = videos[0]
        vod_id = vod["vod_id"]
        if not vod.get("vod_play_from"):
            return {"list": [vod]}

        froms = [x for x in vod["vod_play_from"].split("$$$") if x]
        urls = [x for x in vod["vod_play_url"].split("$$$") if x]
        if len(froms) != len(urls):
            return {"list": [vod]}

        pairs = list(zip(froms, urls))

        selected_from = []
        selected_url = []
        for src, content in pairs:
            content = content.replace("\r", "").replace("\n", "")
            selected_from.append(src)
            selected_url.append(content)

        vod["vod_play_from"] = "$$$".join(selected_from)
        vod["vod_play_url"] = "$$$".join(selected_url)
        vod["vod_id"] = vod_id
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        url = str(id or "").strip()
        if url and url.startswith("http"):
            if "/share/" in url:
                sniffed = self._sniff_m3u8(url)
                if sniffed:
                    url = sniffed
            final_url = self._resolve_redirect(url)
            if final_url:
                url = final_url
        return {
            "parse": 0,
            "jx": 0,
            "playUrl": "",
            "url": url,
            "header": HEADERS,
        }

    def _sniff_m3u8(self, share_url, timeout=3):
        try:
            r = requests.get(share_url, headers=HEADERS, timeout=timeout)
            if r.status_code != 200:
                return ""
            html = r.text
            marker = 'const url = "'
            pos = html.find(marker)
            if pos < 0:
                return ""
            start = pos + len(marker)
            end = html.find('"', start)
            if end < 0:
                return ""
            rel = html[start:end]
            if not rel.startswith("/"):
                return ""
            base = share_url.split("/share/")[0]
            return base + rel
        except BaseException:
            return ""

    def _resolve_redirect(self, url, timeout=3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=False, stream=True)
            r.close()
            if r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location", "")
                if location.startswith("http"):
                    return location
            return url
        except BaseException:
            return ""