# -*- coding: utf-8 -*-
"""
我的音乐 · TVBox 音乐源 v2
  单列表 / 歌词正文显示 / 播放列表 / 搜索
  数据：https://cdn.jsdelivr.net/gh/zxsla/yingyue@main/music.json
"""
import sys
try:
    from base.spider import Spider as BaseSpider
except:
    class BaseSpider: pass

MUSIC_JSON = 'https://cdn.jsdelivr.net/gh/zxsla/yingyue@c3453aa78e4f0e33c6c928eadff01ce0cb4d5e21/music.json'

class Spider(BaseSpider):
    def getName(self):
        return '我的音乐'

    def init(self, extend=''):
        self.data = None

    def load(self):
        if self.data is None:
            try:
                r = self.fetch(MUSIC_JSON, timeout=15)
                self.data = r.json()
            except Exception:
                self.data = {'singers': []}
        return self.data

    def all_songs(self):
        d = self.load()
        out = []
        for s in d.get('singers', []):
            for i, song in enumerate(s['songs']):
                out.append((s['name'], i, song))
        return out

    def homeContent(self, filter):
        total = len(self.all_songs())
        return {'class': [{'type_id': 'all', 'type_name': f'🎵全部歌曲({total}首)'}]}

    def categoryContent(self, tid, pg, filter, extend):
        lst = []
        # 播放列表入口置顶
        lst.append({
            'vod_id': 'playlist@@0',
            'vod_name': '📋播放列表(连续播放)',
            'vod_pic': 'https://raw.githubusercontent.com/zxsla/yingyue/main/playlist-cover.jpg',
            'vod_remarks': f'共{len(self.all_songs())}首',
        })
        for singer, i, song in self.all_songs():
            tag = '🎬' if song.get('type') == 'mv' else '🎵'
            lst.append({
                'vod_id': f'{singer}@@{i}',
                'vod_name': f'{tag} {song["name"]}',
                'vod_pic': song.get('pic', ''),
                'vod_remarks': singer,
            })
        return {'list': lst, 'page': 1, 'pagecount': 1, 'limit': 99, 'total': len(lst)}

    def detailContent(self, ids):
        # 播放列表详情：所有歌曲作为选集
        if ids[0].startswith('playlist@@'):
            songs = self.all_songs()
            urls = [f"{s[2]['name']}${s[2]['url']}" for s in songs]
            vod = {
                'vod_id': ids[0],
                'vod_name': '📋播放列表',
                'vod_remarks': f'共{len(songs)}首',
                'vod_content': '全部歌曲连续播放',
                'vod_play_from': '播放列表',
                'vod_play_url': '#'.join(urls),
            }
            return {'list': [vod]}

        tid, idx = ids[0].split('@@')
        d = self.load()
        for s in d.get('singers', []):
            if s['name'] == tid:
                song = s['songs'][int(idx)]
                content = f"歌手：{s['name']}"
                if song.get('lyric_text'):
                    content += f"\n\n🎶歌词🎶\n{song['lyric_text']}"
                vod = {
                    'vod_id': ids[0],
                    'vod_name': song['name'],
                    'vod_pic': song.get('pic', ''),
                    'vod_remarks': s['name'],
                    'vod_content': content,
                    'vod_play_from': '播放',
                    'vod_play_url': f"播放${song['url']}",
                }
                return {'list': [vod]}
        return {'list': []}

    def searchContent(self, key, quick, pg='1'):
        out = []
        for singer, i, song in self.all_songs():
            if key.lower() in song['name'].lower() or key.lower() in singer.lower():
                tag = '🎬' if song.get('type') == 'mv' else '🎵'
                out.append({
                    'vod_id': f'{singer}@@{i}',
                    'vod_name': f'{tag} {song["name"]} - {singer}',
                    'vod_pic': song.get('pic', ''),
                    'vod_remarks': singer,
                })
        return {'list': out}

    def playerContent(self, flag, id, vipFlags):
        if 'youtu.be' in id or 'youtube.com' in id:
            return {'parse': 1, 'url': id}
        return {'parse': 0, 'url': id}

    def isVideoFormat(self, url):
        return True
    def manualVideoCheck(self): pass
    def localProxy(self, param): return None
    def liveContent(self, url): return ''
