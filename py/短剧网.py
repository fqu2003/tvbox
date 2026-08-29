# coding=utf-8
"""
目标站: 短剧网 (www.duanju.win)
MacCMS 内核，短剧按 /vod/ 详情、/play/ 播放页组织
支持二级分类筛选(题材/年份/排序)、搜索分页、多播放线路解析
加载优化: lxml 解析器 + 预编译正则 + 精准 CSS 选择器 + 播放页纯正则提取
"""
import re
import sys
import json
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    # ==================== 预编译正则（避免每次调用重新编译）====================
    _RE_VOD_ID = re.compile(r'/vod/(\d+)\.html')
    _RE_PLAY_URL = re.compile(r'/play/(\d+)-(\d+)-(\d+)\.html')
    _RE_PLAYER_AAAA = re.compile(r'var\s+player_aaaa\s*=\s*(\{.*?\})')
    _RE_M3U8 = re.compile(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*')
    _RE_PAGE_TOTAL = re.compile(r'(\d+)\s*/\s*(\d+)')
    _RE_PLAY_SORT = re.compile(r'sort-list\s+px(\d+)')

    def init(self, extend=""):
        self.site_url = "https://www.duanju.win"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }

        # 一级分类
        self.categories = [
            {"type_id": "duanju", "type_name": "短剧"},
        ]

        # 二级分类筛选器（MacCMS show 页面参数）
        # URL 格式: /show/{type}---{class}--{by}-------{year}---{page}.html
        self.filters_config = {
            "duanju": [
                {
                    "key": "class",
                    "name": "题材",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "女频恋爱", "v": "女频恋爱"},
                        {"n": "脑洞悬疑", "v": "脑洞悬疑"},
                        {"n": "年代穿越", "v": "年代穿越"},
                        {"n": "古装仙侠", "v": "古装仙侠"},
                        {"n": "现代都市", "v": "现代都市"},
                        {"n": "反转", "v": "反转"},
                        {"n": "爽文", "v": "爽文"},
                        {"n": "短剧", "v": "短剧"},
                    ]
                },
                {
                    "key": "year",
                    "name": "年份",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "2026", "v": "2026"},
                        {"n": "2025", "v": "2025"},
                        {"n": "2024", "v": "2024"},
                        {"n": "2023", "v": "2023"},
                        {"n": "2022", "v": "2022"},
                        {"n": "2021", "v": "2021"},
                        {"n": "2020", "v": "2020"},
                        {"n": "2019", "v": "2019"},
                        {"n": "2018", "v": "2018"},
                    ]
                },
                {
                    "key": "by",
                    "name": "排序",
                    "value": [
                        {"n": "按时间", "v": "time"},
                        {"n": "按人气", "v": "hits"},
                        {"n": "按评分", "v": "score"},
                    ]
                },
            ]
        }

    # ==================== 解析器选择 ====================
    def _make_soup(self, html):
        """优先使用 lxml（C 实现，比 html.parser 快 3-5 倍），不可用时回退"""
        try:
            return BeautifulSoup(html, 'lxml')
        except Exception:
            return BeautifulSoup(html, 'html.parser')

    # ==================== 通用视频列表解析 ====================
    def _parse_video_list(self, soup, max_count=0):
        """
        通用列表解析器，兼容首页/分类/筛选/搜索页的 article 卡片
        MacCMS 模板结构: article > a[href*="/vod/"] > img + span.remark
        """
        video_list = []
        seen = set()

        # 主选择器: article 内的 vod 链接
        for a in soup.select('a[href*="/vod/"]'):
            href = a.get('href', '')
            m = self._RE_VOD_ID.search(href)
            if not m:
                continue
            vod_id = m.group(1)
            if vod_id in seen:
                continue

            # 只取带图片的链接（卡片入口），跳过纯文本链接
            img = a.select_one('img')
            if not img:
                continue

            seen.add(vod_id)
            title = a.get('title', '') or img.get('alt', '') or a.get_text(strip=True)
            if not title:
                continue

            pic = img.get('data-original') or img.get('data-src') or img.get('src', '')

            # 提取备注（完结/更新至/集数等）
            remark = ''
            for sel in ['.hl-remarks', '.remarks', '.label', '.tag']:
                rm = a.select_one(sel)
                if rm:
                    remark = rm.get_text(strip=True)
                    break
            if not remark:
                # 从 a 标签内的文本节点提取状态
                texts = a.find_all(string=True, recursive=False)
                for t in texts:
                    t = t.strip()
                    if t and t not in ('', title):
                        remark = t
                        break

            video_list.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark
            })

            if 0 < max_count <= len(video_list):
                break

        return video_list

    # ==================== 首页 ====================
    def homeContent(self, filter):
        url = self.site_url + "/"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            soup = self._make_soup(resp.text)
            video_list = self._parse_video_list(soup, max_count=36)
        return {
            "class": self.categories,
            "list": video_list,
            "filters": self.filters_config
        }

    def homeVideoContent(self):
        url = self.site_url + "/"
        resp = self.fetch(url, headers=self.headers)
        video_list = []
        if resp:
            soup = self._make_soup(resp.text)
            video_list = self._parse_video_list(soup, max_count=20)
        return {"list": video_list}

    # ==================== 分类页（含二级筛选）====================
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        extend = extend or {}

        # 从筛选参数构造 URL
        cls = extend.get('class', '')
        by = extend.get('by', '')
        year = extend.get('year', '')

        # 无筛选时使用 /type/ 分类页（服务器负载更低、响应更快）
        # 有筛选时使用 /show/ 筛选页
        # show URL 格式: /show/{type}-{area}-{by}-{class}-{lang}-{letter}-{?}-{?}-{page}-{?}-{?}-{year}.html
        if not cls and not by and not year:
            if page <= 1:
                url = f"{self.site_url}/type/{tid}.html"
            else:
                url = f"{self.site_url}/type/{tid}-{page}.html"
        else:
            cls_enc = urllib.parse.quote(cls) if cls else ''
            page_str = str(page) if page > 1 else ''
            segments = [tid, '', by, cls_enc, '', '', '', '', page_str, '', '', year]
            url = f"{self.site_url}/show/" + '-'.join(segments) + '.html'

        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        html = resp.text
        soup = self._make_soup(html)
        video_list = self._parse_video_list(soup)

        # 分页信息: <span>1/275</span>
        pagecount = page
        m = self._RE_PAGE_TOTAL.search(html)
        if m:
            pagecount = int(m.group(2))

        # 兜底: 从分页链接提取最大页码
        if pagecount <= page:
            for a in soup.select('a[href*="/type/"], a[href*="/show/"]'):
                href = a.get('href', '')
                pm = re.search(r'-(\d+)\.html', href)
                if pm:
                    pagecount = max(pagecount, int(pm.group(1)))

        total = len(video_list) * pagecount if video_list else 0
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": total
        }

    # ==================== 详情页 ====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        url = f"{self.site_url}/vod/{vod_id}.html"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": []}

        html = resp.text
        soup = self._make_soup(html)

        # 标题
        vod_name = vod_id
        h1 = soup.select_one('h1')
        if h1:
            vod_name = h1.get_text(strip=True)
            # 去除状态后缀（完结/更新至xx集等）
            vod_name = re.sub(r'\s+(完结|更新至.*?|全\d+集).*$', '', vod_name)

        # 封面: .img-box img 或首个带 alt 的 img
        vod_pic = ''
        img = soup.select_one('.img-box img') or soup.select_one('img[alt]')
        if img:
            vod_pic = img.get('data-original') or img.get('data-src') or img.get('src', '')

        # 元数据: 从 ul li 提取
        vod_actor = vod_director = vod_area = vod_year = vod_content = ''
        for li in soup.select('li'):
            text = li.get_text(strip=True)
            if text.startswith('导演'):
                vod_director = text.split('：', 1)[-1].strip() if '：' in text else ''
            elif text.startswith('主演'):
                vod_actor = text.split('：', 1)[-1].strip() if '：' in text else ''
            elif text.startswith('地区'):
                vod_area = text.split('：', 1)[-1].strip() if '：' in text else ''
            elif text.startswith('年份'):
                vod_year = text.split('：', 1)[-1].strip() if '：' in text else ''
            elif text.startswith('剧情') or text.startswith('简介'):
                vod_content = text.split('：', 1)[-1].strip() if '：' in text else ''
                if vod_content in ('暂无简介',):
                    vod_content = ''

        # 播放列表: #pills-tabContent > .tab-pane
        play_from_list = []
        play_url_list = []

        tab_content = soup.select_one('#pills-tabContent')
        if tab_content:
            # 获取播放源名称
            source_names = []
            for tab_a in soup.select('.nav-tabs a[id^="pills-"]'):
                name = tab_a.get_text(strip=True)
                source_names.append(name if name else f'线路{len(source_names)+1}')

            panes = tab_content.select('.tab-pane[id^="pills-"]')
            for idx, pane in enumerate(panes):
                # 提取该播放源下的所有剧集
                episodes = []
                for a in pane.select('a[href*="/play/"]'):
                    href = a.get('href', '')
                    m = self._RE_PLAY_URL.search(href)
                    if not m:
                        continue
                    ep_name = a.get('title', '') or a.get_text(strip=True)
                    if not ep_name:
                        continue
                    if not href.startswith('http'):
                        href = self.site_url + href
                    episodes.append(f"{ep_name}${href}")

                if episodes:
                    name = source_names[idx] if idx < len(source_names) else f'线路{idx+1}'
                    play_from_list.append(name)
                    play_url_list.append('#'.join(episodes))

        # 兜底: 任意 /play/ 链接
        if not play_url_list:
            for a in soup.select('a[href*="/play/"]'):
                href = a.get('href', '')
                m = self._RE_PLAY_URL.search(href)
                if not m:
                    continue
                ep_name = a.get('title', '') or a.get_text(strip=True)
                if not ep_name:
                    continue
                if not href.startswith('http'):
                    href = self.site_url + href
                play_from_list = ['默认线路']
                play_url_list = [f"{ep_name}${href}"]
                break

        vod_play_from = '$$$'.join(play_from_list)
        vod_play_url = '$$$'.join(play_url_list)

        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_area": vod_area,
            "vod_year": vod_year,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        encoded_key = urllib.parse.quote(key)

        if page <= 1:
            url = f"{self.site_url}/search/-------------.html?wd={encoded_key}"
        else:
            url = f"{self.site_url}/search/{encoded_key}----------{page}---.html"

        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"list": [], "page": page, "pagecount": 1}

        html = resp.text
        soup = self._make_soup(html)
        video_list = self._parse_video_list(soup)

        # 分页
        pagecount = page
        m = self._RE_PAGE_TOTAL.search(html)
        if m:
            pagecount = int(m.group(2))

        return {"list": video_list, "page": page, "pagecount": pagecount}

    # ==================== 播放解析 ====================
    def playerContent(self, flag, id, vipFlags):
        # id 可能是完整 URL / 相对路径 / play路径
        if id.startswith('http'):
            play_url = id
        elif id.startswith('/'):
            play_url = self.site_url + id
        else:
            play_url = f"{self.site_url}/play/{id}.html"

        resp = self.fetch(play_url, headers=self.headers)
        if not resp:
            return {"parse": 1, "url": play_url, "header": self.headers}

        html = resp.text

        # 优先: 从 player_aaaa 变量提取 m3u8（纯正则，不解析 DOM，最快）
        m = self._RE_PLAYER_AAAA.search(html)
        if m:
            try:
                player_data = json.loads(m.group(1))
                video_url = player_data.get('url', '')
                if video_url and video_url.startswith('http'):
                    # m3u8 直连，无需嗅探
                    if '.m3u8' in video_url:
                        return {"parse": 0, "url": video_url, "header": self.headers}
                    # 其他格式也尝试直连
                    return {"parse": 0, "url": video_url, "header": self.headers}
            except (json.JSONDecodeError, KeyError):
                pass

        # 兜底1: 直接搜索 m3u8 链接
        m = self._RE_M3U8.search(html)
        if m:
            return {"parse": 0, "url": m.group(0), "header": self.headers}

        # 兜底2: iframe 内寻找播放地址
        iframe_m = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe_m:
            iframe_url = iframe_m.group(1)
            if not iframe_url.startswith('http'):
                iframe_url = self.site_url + iframe_url if iframe_url.startswith('/') else self.site_url + '/' + iframe_url
            # 仅当 iframe URL 包含播放参数时才请求
            if 'url=' in iframe_url or 'm3u8' in iframe_url:
                m = self._RE_M3U8.search(iframe_url)
                if m:
                    return {"parse": 0, "url": m.group(0), "header": self.headers}

                iframe_resp = self.fetch(iframe_url, headers=self.headers)
                if iframe_resp:
                    m = self._RE_M3U8.search(iframe_resp.text)
                    if m:
                        return {"parse": 0, "url": m.group(0), "header": self.headers}

        # 最终兜底: 交给播放器嗅探
        return {"parse": 1, "url": play_url, "header": self.headers}

    # ==================== 推荐内容（可选）====================
    def isChineseCategory(self):
        return True
