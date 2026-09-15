import sys
import re
import requests
import base64
import json
import time
import random
import hashlib
import hmac
import requests
from urllib.parse import urlparse, parse_qs, urlencode, quote
from urllib3 import disable_warnings
from base.spider import Spider

disable_warnings()


class Spider(Spider):
    """
    酷开TV直播 Spider - 兼容 OK影视/FongMi/TVBox 点播线路
    """
    
    # ==================== 频道ID映射 ====================
    CHANNEL_MAP = {
        'cctv1': 165, 'cctv2': 166, 'cctv4': 167, 'cctv7': 168,
        'cctv9': 169, 'cctv10': 170, 'cctv11': 171, 'cctv12': 172,
        'cctv13': 173, 'cctv14': 174, 'cctv15': 175, 'cctv17': 176,
        'cetv1': 204, 'cetv2': 206, 'cetv4': 218,
        'bjws': 196, 'dfws': 179, 'tjws': 191, 'cqws': 195,
        'hljws': 188, 'jlws': 210, 'lnws': 194, 'nmws': 213,
        'nxws': 203, 'gsws': 212, 'qhws': 202, 'sxws': 201,
        'hbws': 183, 'sxiws': 211, 'sdws': 185, 'ahws': 190,
        'hnws': 198, 'hubws': 186, 'hunws': 180, 'jxws': 193,
        'jsws': 181, 'zjws': 182, 'dnws': 155, 'hxws': 163,
        'xmws': 164, 'gdws': 184, 'szws': 187, 'gxws': 200,
        'ynws': 197, 'gzws': 189, 'scws': 192, 'xjws': 214,
        'btws': 215, 'xzws': 216, 'hinws': 199, 'ssws': 217,
        'kkse': 209, 'dfcj': 227, 'dmxc': 222, 'dsjc': 220,
        'dcwt': 219, 'fztd': 226, 'ly': 225, 'jsxt': 40,
        'shss': 230, 'yxfy': 224, 'jykt': 208, 'klcd': 229,
        'fjzh': 154, 'fjxw': 157, 'fjwt': 159, 'fjse': 162,
        'jjkt': 223
    }
    
    # ==================== 频道名称映射 ====================
    CHANNEL_NAMES = {
        'cctv1': 'CCTV-1', 'cctv2': 'CCTV-2', 'cctv4': 'CCTV-4',
        'cctv7': 'CCTV-7', 'cctv9': 'CCTV-9', 'cctv10': 'CCTV-10',
        'cctv11': 'CCTV-11', 'cctv12': 'CCTV-12', 'cctv13': 'CCTV-13',
        'cctv14': 'CCTV-14', 'cctv15': 'CCTV-15', 'cctv17': 'CCTV-17',
        'cetv1': 'CETV-1', 'cetv2': 'CETV-2', 'cetv4': 'CETV-4',
        'bjws': '北京卫视', 'dfws': '东方卫视', 'tjws': '天津卫视',
        'cqws': '重庆卫视', 'hljws': '黑龙江卫视', 'jlws': '吉林卫视',
        'lnws': '辽宁卫视', 'nmws': '内蒙古卫视', 'nxws': '宁夏卫视',
        'gsws': '甘肃卫视', 'qhws': '青海卫视', 'sxws': '陕西卫视',
        'hbws': '湖北卫视', 'sxiws': '山西卫视', 'sdws': '山东卫视',
        'ahws': '安徽卫视', 'hnws': '湖南卫视', 'hubws': '湖北卫视',
        'hunws': '湖南卫视', 'jxws': '江西卫视', 'jsws': '江苏卫视',
        'zjws': '浙江卫视', 'dnws': '东南卫视', 'hxws': '海峡卫视',
        'xmws': '厦门卫视', 'gdws': '广东卫视', 'szws': '深圳卫视',
        'gxws': '广西卫视', 'ynws': '云南卫视', 'gzws': '贵州卫视',
        'scws': '四川卫视', 'xjws': '新疆卫视', 'btws': '兵团卫视',
        'xzws': '西藏卫视', 'hinws': '海南卫视', 'ssws': '三沙卫视',
        'kkse': '卡酷少儿', 'dfcj': '东方财经', 'dmxc': '动漫秀场',
        'dsjc': '都市剧场', 'dcwt': '东方卫视', 'fztd': '法治天地',
        'ly': '旅游卫视', 'jsxt': '金色学堂', 'shss': '生活时尚',
        'yxfy': '游戏风云', 'jykt': '教育课堂', 'klcd': '快乐成长',
        'fjzh': '福建综合', 'fjxw': '福建新闻', 'fjwt': '福建文体',
        'fjse': '福建少儿', 'jjkt': '经济课堂'
    }
    
    # ==================== 分类定义 ====================
    CATS = [
        {'name': '央视', 'ids': ['cctv1', 'cctv2', 'cctv4', 'cctv7', 'cctv9',
                               'cctv10', 'cctv11', 'cctv12', 'cctv13', 'cctv14',
                               'cctv15', 'cctv17']},
        {'name': '卫视', 'ids': ['bjws', 'dfws', 'tjws', 'cqws', 'hljws', 'jlws',
                               'lnws', 'nmws', 'nxws', 'gsws', 'qhws', 'sxws',
                               'hbws', 'sxiws', 'sdws', 'ahws', 'hnws', 'hubws',
                               'hunws', 'jxws', 'jsws', 'zjws', 'dnws', 'hxws',
                               'xmws', 'gdws', 'szws', 'gxws', 'ynws', 'gzws',
                               'scws', 'xjws', 'btws', 'xzws', 'hinws', 'ssws']},
        {'name': '数字/付费', 'ids': ['kkse', 'dfcj', 'dmxc', 'dsjc', 'dcwt',
                                  'fztd', 'ly', 'jsxt', 'shss', 'yxfy',
                                  'jykt', 'klcd']},
        {'name': '福建', 'ids': ['fjzh', 'fjxw', 'fjwt', 'fjse']},
        {'name': '教育', 'ids': ['cetv1', 'cetv2', 'cetv4', 'jjkt']},
    ]
    
    # ==================== 常量 ====================
    SALT = "557f1d838112de4fc349b8558781fe17"
    
    # ==================== 初始化 ====================
    
    def init(self, extend=""):
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def getName(self):
        return "酷开TV直播"

    # ==================== 蜘蛛壳接口 ====================

    def homeContent(self, filter=False):
        classes = [
            {'type_id': str(i), 'type_name': c['name']}
            for i, c in enumerate(self.CATS)
        ]
        result = {'class': classes}
        if filter:
            result['filters'] = {}
        return result

    def homeVideoContent(self):
        return self.categoryContent('0', '1', False, {})

    def categoryContent(self, tid, pg='1', filter=False, extend=None):
        try:
            cat_index = int(str(tid))
        except (TypeError, ValueError):
            cat_index = 0
        if cat_index < 0 or cat_index >= len(self.CATS):
            return self._empty_page()

        cat = self.CATS[cat_index]
        vod_list = []
        for cid in cat['ids']:
            name = self.CHANNEL_NAMES.get(cid, cid)
            vod_list.append({
                'vod_id': cid,
                'vod_name': name,
                'vod_pic': '',
                'vod_remarks': '直播',
            })
        return {
            'page': 1,
            'pagecount': 1,
            'limit': len(vod_list),
            'total': len(vod_list),
            'list': vod_list,
        }

    def detailContent(self, ids):
        if not ids:
            return {'list': []}
        cid = str(ids[0]).strip()
        name = self.CHANNEL_NAMES.get(cid, cid)
        vod = {
            'vod_id': cid,
            'vod_name': name,
            'vod_pic': '',
            'type_name': '电视直播',
            'vod_remarks': '直播',
            'vod_play_from': 'TV',
            'vod_play_url': f'直播${cid}',
            'vod_content': f'{name} 高清直播',
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags=None):
        cid = str(id).split('$$$')[-1].strip()
        
        # 获取频道ID
        channel_id = self.CHANNEL_MAP.get(cid)
        if not channel_id:
            return {'parse': 0, 'url': '', 'header': {}}
        
        # 获取播放地址
        play_url = self._get_play_url(channel_id)
        if play_url:
            return {
                'parse': 0,
                'url': play_url,
                'header': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://kylinapi.bbtv.cn/',
                }
            }
        return {'parse': 0, 'url': '', 'header': {}}

    def searchContent(self, key, quick=False, pg='1'):
        keyword = str(key or '').strip().lower()
        if not keyword:
            return {'list': []}
        videos = []
        for cid, name in self.CHANNEL_NAMES.items():
            if keyword in cid.lower() or keyword in name.lower():
                videos.append({
                    'vod_id': cid,
                    'vod_name': name,
                    'vod_pic': '',
                    'vod_remarks': '直播',
                })
        return {'list': videos}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def _empty_page(self):
        return {
            'page': 1,
            'pagecount': 1,
            'limit': 0,
            'total': 0,
            'list': [],
        }

    # ==================== 辅助方法 ====================

    def _generate_device_id(self):
        """生成设备ID (COOCAA_ + UUID v4)"""
        def random_hex(length):
            return ''.join(random.choice('0123456789abcdef') for _ in range(length))
        
        parts = [
            random_hex(8),
            random_hex(4),
            '4' + random_hex(3),
            hex(random.randint(8, 11))[2:] + random_hex(3),
            random_hex(12)
        ]
        return 'COOCAA_' + '-'.join(parts)

    def _hmac_md5(self, data, key):
        """HMAC-MD5 加密"""
        return hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.md5).hexdigest()

    # ==================== 播放地址获取 ====================

    def _get_play_url(self, channel_id):
        """获取播放地址"""
        try:
            timestamp = int(time.time())
            device_id = self._generate_device_id()
            
            # 第一步：获取 clientID
            param = f"deviceid={device_id}&market=coocaa&timestamp={timestamp}"
            signature = self._hmac_md5(param, self.SALT)
            
            url1 = f"https://kylinapi.bbtv.cn/5g/v1/client-id-by-region?{param}&signature={signature}"
            
            resp1 = self.session.get(url1, timeout=15)
            if resp1.status_code != 200:
                return None
            
            data1 = resp1.json()
            client_id = data1.get('clientID')
            if not client_id:
                return None
            
            # 第二步：获取播放地址
            url2 = f"https://kylinapi.bbtv.cn/5g/v1/tv/now/{channel_id}?client={client_id}"
            
            # 生成签名
            sign2 = hashlib.md5(f"{timestamp}{self.SALT}".encode()).hexdigest()
            
            headers2 = {
                "timestamp": str(timestamp),
                "sign": sign2
            }
            
            resp2 = self.session.get(url2, headers=headers2, timeout=15)
            if resp2.status_code != 200:
                return None
            
            data2 = resp2.json()
            play_url = data2.get('playUrl')
            if not play_url:
                return None
            
            # 提取 m3u8 地址（去掉 &userid 及其后参数）
            if '&userid' in play_url:
                m3u8_url = play_url.split('&userid')[0]
            else:
                m3u8_url = play_url
            
            return m3u8_url
            
        except Exception as e:
            print(f"[酷开TV] 获取播放地址失败: {e}")
            return None
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