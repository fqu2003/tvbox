# coding = utf-8
#!/usr/bin/python
# 新时代青年 2025.06.25 getApp第三版  后续平凡哥 七月大姐等大佬魔改 最后更新2025.08.30七月版  请勿非法盈利，下载24小时后请删除！不删除雨滴大佬晚上会在你窗前
import re,sys,uuid,json,base64,urllib3,random,time,hashlib
from Crypto.Cipher import AES
from base.spider import Spider
from Crypto.Util.Padding import pad,unpad
sys.path.append('..')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Spider(Spider):
    xurl,key,iv,init_data,search_verify = '','','','',''
    username, password, device_id = '', '', ''
    header = {}
    sort_rule = []
    playua = ''
    playcookie = ''
    playreferer = ''
    line_specific_settings = {}
    vip_duration = ''
    vip_config = {}
    enable_delay = False  # 延迟请求开关，默认关闭
    
    # 外置UA参数
    host_ua = ''
    config_ua = ''
    home_ua = ''
    category_ua = ''
    search_ua = ''
    parse_ua = ''
    player_ua = ''
    
    # 新增：自动生成参数相关
    auto_params_level = 0  # 自动生成参数级别：0关闭，1生成32位ID，2生成32位ID+时间戳签名，3生成全部
    ext_timestamp = ''  # 外置时间戳
    ext_sign = ''  # 外置签名
    ext_android_id = ''  # 外置安卓ID
    ext_device_id = ''  # 外置设备ID
    
    # 新增：签到相关参数
    sign_url = ''  # 签到页面URL
    sign_api = ''  # 签到API地址
    sign_username = ''  # 签到用户名
    sign_enabled = False  # 是否启用签到
    sign_interval_hours = 3  # 签到间隔小时数，默认3小时
    
    def __init__(self):
        self.header = {'User-Agent': self._generate_random_ua()}

    def getName(self):
        return "首页"

    def init(self, extend=''):
        # 汉字参数映射（兼容大小写）
        chinese_param_map = {
            '域名': 'host',
            '指定域名': 'host_index',
            '数据密钥': 'datakey',
            '数据向量': 'dataiv',
            '接口版本': 'api',
            '用户代理': 'ua',
            '设备标识': 'deviceid',
            '登录类型': 'login_type',
            '登录账号': 'username',
            '登录密码': 'password',
            '令牌': 'token',
            'cookie': 'cookie',
            '认证令牌': 'auth_token',
            '用户id': 'user_id',
            '刷新令牌': 'refresh_token',
            '令牌过期': 'token_expire',
            'host': 'host',
            'host_index': 'host_index',
            'datakey': 'datakey',
            'dataiv': 'dataiv',
            'api': 'api',
            'ua': 'ua',
            'deviceid': 'deviceid',
            'login_type': 'login_type',
            'username': 'username',
            'password': 'password',
            'token': 'token',
            'auth_token': 'auth_token',
            'user_id': 'user_id',
            'refresh_token': 'refresh_token',
            'token_expire': 'token_expire'
        }
        
        # UA相关汉字参数映射
        ua_chinese_map = {
            '首页ua': 'homeua',
            '首页UA': 'homeua',
            '配置ua': 'configua',
            '配置UA': 'configua',
            '分类ua': 'categoryua',
            '分类UA': 'categoryua',
            '搜索ua': 'searchua',
            '搜索UA': 'searchua',
            '解析ua': 'parseua',
            '解析UA': 'parseua',
            '播放ua': 'playerua',
            '播放UA': 'playerua',
            'hostua': 'hostua',
            'hostUA': 'hostua',
            'configua': 'configua',
            'configUA': 'configua',
            'homeua': 'homeua',
            'homeUA': 'homeua',
            'categoryua': 'categoryua',
            'categoryUA': 'categoryua',
            'searchua': 'searchua',
            'searchUA': 'searchua',
            'parseua': 'parseua',
            'parseUA': 'parseua',
            'playerua': 'playerua',
            'playerUA': 'playerua'
        }
        
        ext = json.loads(extend.strip())
        
        # 转换汉字参数为英文键名
        english_ext = {}
        for key, value in ext.items():
            # 处理大小写
            lower_key = key.lower()
            if lower_key in chinese_param_map:
                english_ext[chinese_param_map[lower_key]] = value
            elif key in ua_chinese_map:
                english_ext[ua_chinese_map[key]] = value
            else:
                english_ext[key] = value
        
        # 使用转换后的参数
        host = english_ext['host']
        
        # 读取延迟请求配置，默认关闭
        self.enable_delay = english_ext.get('延迟', english_ext.get('enable_delay', '0')) == '1'
        
        # 新增：读取自动生成参数级别，默认关闭(0)
        auto_params_str = english_ext.get('auto_params', english_ext.get('自动参数', '0'))
        try:
            self.auto_params_level = int(auto_params_str)
        except ValueError:
            self.auto_params_level = 0
        
        # 新增：读取外置参数
        self.ext_timestamp = english_ext.get('timestamp', english_ext.get('时间戳', ''))
        self.ext_sign = english_ext.get('sign', english_ext.get('签名', ''))
        self.ext_android_id = english_ext.get('android_id', english_ext.get('安卓ID', ''))
        self.ext_device_id = english_ext.get('deviceid', english_ext.get('devideid', ''))
        
        # 新增：读取签到配置
        self.sign_url = english_ext.get('sign_url', english_ext.get('签到地址', ''))
        self.sign_username = english_ext.get('sign_username', english_ext.get('签到用户', ''))
        self.sign_enabled = english_ext.get('sign_enable', english_ext.get('启用签到', '0')) == '1'
        
        # 新增：读取签到间隔参数
        sign_interval_str = english_ext.get('sign_interval', english_ext.get('签到间隔', '3'))
        try:
            self.sign_interval_hours = int(sign_interval_str)
            if self.sign_interval_hours < 1:
                self.sign_interval_hours = 1  # 最小1小时
            print(f"设置签到间隔: {self.sign_interval_hours}小时")
        except ValueError:
            self.sign_interval_hours = 3  # 默认3小时
            print(f"签到间隔参数错误，使用默认值: 3小时")
        
        # 修改：直接使用外置签到地址作为API地址，不添加任何后缀
        self.sign_api = self.sign_url
        
        host_index_str = str(english_ext.get('host_index', '1')).strip()
        try:
            host_index = int(host_index_str) if host_index_str else 1
        except ValueError:
            host_index = 1
        
        if not re.match(r'^https?:\/\/[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*(:\d+)?(\/)?$', host):
            response = self.fetch(host, headers=self.header, timeout=10, verify=False)
            text = response.text.strip()
            addresses = [line.strip() for line in text.splitlines() if line.strip()]
            
            if len(addresses) > 0:
                index = host_index - 1
                if 0 <= index < len(addresses):
                    host = addresses[index]
                else:
                    host = addresses[0]
            
        host = host.rstrip('/')
        
        ua = english_ext.get('ua')
        if ua:
            self.header['User-Agent'] = ua
        
        # 初始化外置UA参数（兼容中文和大写、小写）
        self.host_ua = self._get_ua_param(english_ext, ['hostua', 'hostUA', '首页ua', '首页UA'])
        self.config_ua = self._get_ua_param(english_ext, ['configua', 'configUA', '配置ua', '配置UA'])
        self.home_ua = self._get_ua_param(english_ext, ['homeua', 'homeUA', '首页ua', '首页UA'])
        self.category_ua = self._get_ua_param(english_ext, ['categoryua', 'categoryUA', '分类ua', '分类UA'])
        self.search_ua = self._get_ua_param(english_ext, ['searchua', 'searchUA', '搜索ua', '搜索UA'])
        self.parse_ua = self._get_ua_param(english_ext, ['parseua', 'parseUA', '解析ua', '解析UA'])
        self.player_ua = self._get_ua_param(english_ext, ['playerua', 'playerUA', '播放ua', '播放UA'])
        
        # 初始化会员配置
        self.vip_config = {
            'type': english_ext.get('login_type', 'auto'),  # auto, login, duration, token, cookie, device, guest, sign, token_login
            'duration': english_ext.get('会员时长', ''),
            'username': english_ext.get('username', ''),
            'password': english_ext.get('password', ''),
            'token': english_ext.get('token', ''),
            'cookie': english_ext.get('cookie', ''),
            'device_only': english_ext.get('device_only', '0') == '1',
            'sign_username': self.sign_username,  # 添加签到用户名
            'auth_token': english_ext.get('auth_token', ''),  # 抓包获取的auth_token
            'user_id': english_ext.get('user_id', ''),  # 用户ID
            'refresh_token': english_ext.get('refresh_token', ''),  # 刷新token
            'token_expire': english_ext.get('token_expire', '0')  # token过期时间
        }
        
        # 处理设备ID生成（根据自动参数级别）
        self._handle_device_id_generation()
        
        if self.device_id:
            self.header['app-user-device-id'] = self.device_id
        
        # 处理会员验证
        self._handle_vip_verification()
        
        # 兼容播放相关参数（支持中文）
        self.playua = self._get_ua_param(english_ext, ['playua', 'playUA', '播放ua', '播放UA'], 'Dalvik/2.1.0 (Linux; U; Android 14; 23113RK12C Build/SKQ1.231004.001)')
        self.playcookie = self._get_param(english_ext, ['playcookie', 'playCookie', '播放cookie', '播放Cookie'], '')
        self.playreferer = self._get_param(english_ext, ['playreferer', 'playReferer', '播放referer', '播放Referer'], '')
        
        self.line_specific_settings = {}
        for key, value in english_ext.items():
            if key.startswith('line_'):
                line_key = key.replace('line_', '')
                if '|' in value:
                    parts = value.split('|', 1)
                    ua_part = ''
                    referer_part = ''
                    for part in parts:
                        part = part.strip()
                        if part:
                            if part.startswith('http://') or part.startswith('https://'):
                                referer_part = part
                            else:
                                ua_part = part
                    if line_key not in self.line_specific_settings:
                        self.line_specific_settings[line_key] = {}
                    if ua_part:
                        self.line_specific_settings[line_key]['ua'] = ua_part
                    if referer_part:
                        self.line_specific_settings[line_key]['referer'] = referer_part
                elif '_ua' in key or '_UA' in key:
                    line_name = key.replace('line_', '').replace('_ua', '').replace('_UA', '')
                    if line_name not in self.line_specific_settings:
                        self.line_specific_settings[line_name] = {}
                    self.line_specific_settings[line_name]['ua'] = value
                elif '_referer' in key or '_Referer' in key:
                    line_name = key.replace('line_', '').replace('_referer', '').replace('_Referer', '')
                    if line_name not in self.line_specific_settings:
                        self.line_specific_settings[line_name] = {}
                    self.line_specific_settings[line_name]['referer'] = value
                else:
                    if line_key not in self.line_specific_settings:
                        self.line_specific_settings[line_key] = {}
                    if value.startswith('http://') or value.startswith('https://'):
                        self.line_specific_settings[line_key]['referer'] = value
                    else:
                        self.line_specific_settings[line_key]['ua'] = value
        
        api = english_ext.get('api', '/api.php/getappapi')
        if str(api) == '2':
            api = '/api.php/qijiappapi'
        self.xurl = host + api
        self.key = english_ext['datakey']
        self.iv = english_ext.get('dataiv', self.key)
        
        sort_rule_str = english_ext.get('排序', '')
        if sort_rule_str:
            self.sort_rule = [s.strip().lower() for s in sort_rule_str.split(',')]
        else:
            self.sort_rule = []
        
        # 使用配置的UA获取初始化数据
        init_headers = self.header.copy()
        if self.config_ua:
            init_headers['User-Agent'] = self.config_ua
            
        # 为初始化请求添加自动参数
        init_payload = {}
        init_payload, init_headers = self._add_auto_params_to_request(init_payload, init_headers)
            
        res = self.fetch(self.xurl + '.index/initV119', headers=init_headers, verify=False).json()
        encrypted_data = res['data']
        response = self.decrypt(encrypted_data)
        init_data = json.loads(response)
        self.init_data = init_data
        self.search_verify = init_data['config'].get('system_search_verify_status', False)

    def _handle_device_id_generation(self):
        """处理设备ID生成逻辑"""
        # 如果有外置设备ID，优先使用
        if self.ext_device_id:
            self.device_id = self.ext_device_id
            print(f"使用外置设备ID: {self.device_id}")
            return
        
        # 根据自动参数级别决定是否生成设备ID
        if self.auto_params_level >= 1:
            self.device_id = str(uuid.uuid4()).replace('-', '')  # 移除横杠，生成32位ID
            print(f"自动生成设备ID(级别{self.auto_params_level}): {self.device_id}")
        else:
            # 级别0：不自动生成，使用空值
            self.device_id = ''
            print("自动参数级别0，不生成设备ID")

    def _get_ua_param(self, ext, param_names, default=''):
        """获取UA参数，支持多种命名格式"""
        for name in param_names:
            value = ext.get(name)
            if value:
                return value
        return default

    def _get_param(self, ext, param_names, default=''):
        """获取普通参数，支持多种命名格式"""
        for name in param_names:
            value = ext.get(name)
            if value:
                return value
        return default

    def _apply_request_delay(self):
        """应用请求延迟，如果开启的话"""
        if self.enable_delay:
            delay_time = random.uniform(1, 3)  # 1到3秒随机延迟
            time.sleep(delay_time)

    def fetch(self, url, **kwargs):
        """重写fetch方法，添加延迟控制"""
        # 播放相关请求不加延迟
        if 'playerContent' not in sys._getframe(2).f_code.co_name:
            self._apply_request_delay()
        return super().fetch(url, **kwargs)

    def post(self, url, **kwargs):
        """重写post方法，添加延迟控制"""
        # 播放相关请求不加延迟
        if 'playerContent' not in sys._getframe(2).f_code.co_name:
            self._apply_request_delay()
        return super().post(url, **kwargs)

    def _handle_vip_verification(self):
        """处理会员验证 - 支持9种模式（新增token_login和sign模式）"""
        vip_type = self.vip_config['type']
        
        if vip_type == 'auto':
            # 自动检测优先级：token_login > token > cookie > 时长 > 账号密码 > 签到 > 设备 > 游客
            if self.vip_config['auth_token']:
                success = self._token_login()
                if success:
                    print("自动选择: Token直接登录模式")
                else:
                    print("Token登录失败，尝试其他模式")
                    self._fallback_to_other_modes()
            elif self.vip_config['token']:
                self.header['app-user-token'] = self.vip_config['token']
                self.vip_duration = self.vip_config['duration']
                print("自动选择: Token验证模式")
            elif self.vip_config['cookie']:
                self.header['Cookie'] = self.vip_config['cookie']
                self.vip_duration = self.vip_config['duration']
                print("自动选择: Cookie验证模式")
            elif self.vip_config['duration']:
                self.vip_duration = self.vip_config['duration']
                print("自动选择: 直接时长模式")
            elif self.vip_config['username'] and self.vip_config['password']:
                self.login()
                print("自动选择: 账号密码模式")
            elif self.sign_enabled and self.sign_username:
                self.vip_duration = self._auto_sign_vip()
                print("自动选择: 签到模式")
            elif self.vip_config['device_only']:
                self.vip_duration = self._generate_device_vip()
                print("自动选择: 设备验证模式")
            else:
                self.vip_duration = ''
                print("自动选择: 游客模式")
        
        elif vip_type == 'token_login':
            if self.vip_config['auth_token']:
                success = self._token_login()
                if not success:
                    print("Token直接登录失败")
                    self._fallback_to_other_modes()
            else:
                print("Token登录模式但未提供auth_token")
                self._fallback_to_other_modes()
        
        elif vip_type == 'login':
            if self.vip_config['username'] and self.vip_config['password']:
                self.login()
                print("手动选择: 账号密码模式")
            else:
                print("账号密码模式但未提供用户名密码")
                self.vip_duration = ''
        
        elif vip_type == 'duration':
            self.vip_duration = self.vip_config['duration']
            print("手动选择: 直接时长模式")
        
        elif vip_type == 'token':
            if self.vip_config['token']:
                self.header['app-user-token'] = self.vip_config['token']
                self.vip_duration = self.vip_config['duration']
                print("手动选择: Token验证模式")
            else:
                print("Token模式但未提供token")
                self.vip_duration = ''
        
        elif vip_type == 'cookie':
            if self.vip_config['cookie']:
                self.header['Cookie'] = self.vip_config['cookie']
                self.vip_duration = self.vip_config['duration']
                print("手动选择: Cookie验证模式")
            else:
                print("Cookie模式但未提供cookie")
                self.vip_duration = ''
        
        elif vip_type == 'sign':
            if self.sign_enabled and self.sign_username:
                self.vip_duration = self._auto_sign_vip()
                print("手动选择: 签到模式")
            else:
                print("签到模式但未启用或未提供用户名")
                self.vip_duration = ''
        
        elif vip_type == 'device':
            self.vip_duration = self._generate_device_vip()
            print("手动选择: 设备验证模式")
        
        elif vip_type == 'guest':
            self.vip_duration = ''
            print("手动选择: 游客模式")
        
        else:
            print(f"未知的登录模式: {vip_type}, 使用游客模式")
            self.vip_duration = ''

    def _token_login(self):
        """使用抓包获取的Token直接登录"""
        try:
            auth_token = self.vip_config['auth_token']
            if not auth_token:
                print("未提供auth_token，无法进行Token登录")
                return False
            
            # 检查Token是否需要刷新
            current_time = int(time.time())
            token_expire = int(self.vip_config.get('token_expire', 0))
            
            if token_expire > 0 and current_time >= token_expire - 300:  # 提前5分钟刷新
                print("Token即将过期，尝试刷新...")
                if not self._refresh_token():
                    print("Token刷新失败，使用原有Token")
            
            # 设置Token到header
            self.header['app-user-token'] = auth_token
            
            # 验证Token是否有效
            if self._verify_token():
                # 生成VIP信息
                vip_data = {
                    'auth_token': auth_token[:20] + '...',  # 只存储部分token
                    'user_id': self.vip_config.get('user_id', ''),
                    'login_type': 'token_login',
                    'login_time': current_time,
                    'token_expire': token_expire
                }
                self.vip_duration = base64.b64encode(json.dumps(vip_data).encode()).decode()
                
                print("Token登录成功")
                if token_expire > 0:
                    expire_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(token_expire))
                    print(f"Token有效期至: {expire_time}")
                
                return True
            else:
                print("Token验证失败")
                return False
                
        except Exception as e:
            print(f"Token登录异常: {e}")
            return False

    def _verify_token(self):
        """验证Token是否有效"""
        try:
            # 通过访问用户信息接口验证Token
            headers = self.header.copy()
            payload = {}
            
            # 添加自动参数
            payload, headers = self._add_auto_params_to_request(payload, headers)
            
            response = self.post(f'{self.xurl}.index/userInfo', headers=headers, data=payload, verify=False)
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('code') == 1:  # 假设1表示成功
                    return True
                else:
                    print(f"Token验证失败: {response_data.get('msg', '未知错误')}")
            else:
                print(f"Token验证请求失败: {response.status_code}")
                
        except Exception as e:
            print(f"Token验证异常: {e}")
            
        return False

    def _refresh_token(self):
        """刷新Token"""
        try:
            refresh_token = self.vip_config.get('refresh_token')
            if not refresh_token:
                print("未提供refresh_token，无法刷新")
                return False
            
            payload = {
                'refresh_token': refresh_token,
                'device_id': self.device_id
            }
            
            headers = self.header.copy()
            # 添加自动参数
            payload, headers = self._add_auto_params_to_request(payload, headers)
            
            response = self.post(f'{self.xurl}.index/refreshToken', headers=headers, data=payload, verify=False)
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('code') == 1:
                    encrypted_data = response_data['data']
                    decrypted_data = self.decrypt(encrypted_data)
                    token_info = json.loads(decrypted_data)
                    
                    # 更新Token信息
                    new_auth_token = token_info.get('auth_token')
                    new_refresh_token = token_info.get('refresh_token')
                    expire_time = token_info.get('expire_time', 0)
                    
                    if new_auth_token:
                        self.vip_config['auth_token'] = new_auth_token
                        self.header['app-user-token'] = new_auth_token
                        
                    if new_refresh_token:
                        self.vip_config['refresh_token'] = new_refresh_token
                    
                    self.vip_config['token_expire'] = str(expire_time)
                    
                    print("Token刷新成功")
                    return True
                else:
                    print(f"Token刷新失败: {response_data.get('msg', '未知错误')}")
            else:
                print(f"Token刷新请求失败: {response.status_code}")
                
        except Exception as e:
            print(f"Token刷新异常: {e}")
            
        return False

    def _fallback_to_other_modes(self):
        """Token登录失败时回退到其他模式"""
        print("Token登录失败，尝试回退到其他模式...")
        
        if self.vip_config['duration']:
            self.vip_duration = self.vip_config['duration']
            print("回退到直接时长模式")
        elif self.sign_enabled and self.sign_username:
            self.vip_duration = self._auto_sign_vip()
            print("回退到签到模式")
        else:
            self.vip_duration = ''
            print("回退到游客模式")

    def _auto_sign_vip(self):
        """自动签到获取VIP - 适配新的VIP兑换系统，支持间隔控制"""
        try:
            if not self.sign_api or not self.sign_username:
                print("签到配置不完整，无法自动签到")
                return ''
            
            # 检查上次签到时间，避免频繁签到
            current_time = int(time.time())
            last_sign_time = getattr(self, '_last_sign_time', 0)
            sign_interval = self.sign_interval_hours * 3600  # 使用外置参数控制间隔
            
            # 如果距离上次签到不足指定间隔，检查VIP是否还有效
            if current_time - last_sign_time < sign_interval:
                if hasattr(self, '_last_vip_duration') and self._last_vip_duration:
                    try:
                        vip_data = json.loads(base64.b64decode(self._last_vip_duration).decode())
                        end_time = vip_data.get('end_time', 0)
                        if end_time > current_time:
                            remaining_hours = (end_time - current_time) // 3600
                            remaining_minutes = ((end_time - current_time) % 3600) // 60
                            print(f"距离上次签到不足{self.sign_interval_hours}小时，VIP剩余{remaining_hours}小时{remaining_minutes}分钟，跳过本次签到")
                            return self._last_vip_duration
                    except Exception as e:
                        print(f"检查VIP状态失败: {e}")
                # VIP已过期或无效，继续签到
                print(f"VIP已过期，继续执行签到")
            
            print(f"开始自动签到，用户名: {self.sign_username}，签到间隔: {self.sign_interval_hours}小时")
            
            # 准备签到数据 - 根据页面源码，使用表单格式
            payload = f'username={self.sign_username}'
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Origin': self.sign_url.rstrip('/') if self.sign_url else '',
                'Referer': self.sign_url
            }
            
            # 发送签到请求
            response = self.post(self.sign_api, data=payload, headers=headers, verify=False)
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"签到响应: {result}")
                    
                    if result.get('success'):
                        # 根据页面显示，成功时返回end_time
                        end_time = result.get('end_time')
                        if not end_time:
                            # 如果没有返回end_time，默认6小时
                            end_time = int(time.time()) + 6 * 3600
                        
                        # 计算剩余时长（小时）
                        current_time = int(time.time())
                        if end_time > current_time:
                            duration_hours = (end_time - current_time) // 3600
                        else:
                            duration_hours = 6  # 默认6小时
                        
                        # 生成VIP时长参数
                        vip_data = {
                            'sign_success': True,
                            'username': self.sign_username,
                            'end_time': end_time,
                            'duration_hours': duration_hours,
                            'sign_time': current_time,
                            'source': 'auto_sign'
                        }
                        
                        vip_duration = base64.b64encode(json.dumps(vip_data).encode()).decode()
                        
                        # 记录本次签到时间和VIP信息
                        self._last_sign_time = current_time
                        self._last_vip_duration = vip_duration
                        
                        expire_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))
                        print(f"签到成功！获得{duration_hours}小时VIP，到期时间: {expire_str}")
                        return vip_duration
                    else:
                        error_msg = result.get('message', '未知错误')
                        print(f"签到失败: {error_msg}")
                        
                        # 尝试从HTML响应中提取错误信息
                        if 'html' in response.headers.get('Content-Type', '').lower():
                            html_content = response.text
                            if '兑换成功' in html_content:
                                # 从HTML中提取到期时间
                                import re
                                end_time_match = re.search(r'id="endTime">([^<]+)</span>', html_content)
                                if end_time_match:
                                    end_time_str = end_time_match.group(1)
                                    # 转换时间格式 2025/9/25 下午7:23:10 -> 时间戳
                                    from datetime import datetime
                                    try:
                                        end_time_dt = datetime.strptime(end_time_str, '%Y/%m/%d 下午%I:%M:%S')
                                        end_time = int(end_time_dt.timestamp())
                                    except:
                                        try:
                                            end_time_dt = datetime.strptime(end_time_str, '%Y/%m/%d %H:%M:%S')
                                            end_time = int(end_time_dt.timestamp())
                                        except:
                                            end_time = int(time.time()) + 6 * 3600
                                    
                                    duration_hours = (end_time - int(time.time())) // 3600
                                    
                                    vip_data = {
                                        'sign_success': True,
                                        'username': self.sign_username,
                                        'end_time': end_time,
                                        'duration_hours': duration_hours,
                                        'sign_time': int(time.time()),
                                        'source': 'auto_sign_html'
                                    }
                                    
                                    vip_duration = base64.b64encode(json.dumps(vip_data).encode()).decode()
                                    
                                    # 记录本次签到时间和VIP信息
                                    self._last_sign_time = int(time.time())
                                    self._last_vip_duration = vip_duration
                                    
                                    print(f"HTML解析成功！获得{duration_hours}小时VIP，到期时间: {end_time_str}")
                                    return vip_duration
                
                except json.JSONDecodeError:
                    # 如果返回的是HTML而不是JSON，尝试解析HTML
                    html_content = response.text
                    print("响应为HTML格式，尝试解析...")
                    
                    if '兑换成功' in html_content or 'success-message' in html_content:
                        # 从HTML中提取会员信息
                        import re
                        
                        # 提取用户名
                        username_match = re.search(r'id="displayUsername">([^<]+)</span>', html_content)
                        display_username = username_match.group(1) if username_match else self.sign_username
                        
                        # 提取到期时间
                        end_time_match = re.search(r'id="endTime">([^<]+)</span>', html_content)
                        if end_time_match:
                            end_time_str = end_time_match.group(1)
                            # 转换时间格式 2025/9/25 下午7:23:10 -> 时间戳
                            from datetime import datetime
                            try:
                                # 处理下午/上午时间
                                if '下午' in end_time_str:
                                    end_time_str = end_time_str.replace('下午', '')
                                    time_parts = end_time_str.split(' ')
                                    if len(time_parts) >= 2:
                                        date_part = time_parts[0]
                                        time_part = time_parts[1]
                                        hour, minute, second = time_part.split(':')
                                        hour = str(int(hour) + 12) if int(hour) < 12 else hour
                                        end_time_str = f"{date_part} {hour}:{minute}:{second}"
                                
                                end_time_dt = datetime.strptime(end_time_str, '%Y/%m/%d %H:%M:%S')
                                end_time = int(end_time_dt.timestamp())
                            except Exception as e:
                                print(f"时间格式解析错误: {e}, 使用默认6小时")
                                end_time = int(time.time()) + 6 * 3600
                        else:
                            end_time = int(time.time()) + 6 * 3600
                        
                        duration_hours = (end_time - int(time.time())) // 3600
                        
                        vip_data = {
                            'sign_success': True,
                            'username': display_username,
                            'end_time': end_time,
                            'duration_hours': duration_hours,
                            'sign_time': int(time.time()),
                            'source': 'auto_sign_html'
                        }
                        
                        vip_duration = base64.b64encode(json.dumps(vip_data).encode()).decode()
                        
                        # 记录本次签到时间和VIP信息
                        self._last_sign_time = int(time.time())
                        self._last_vip_duration = vip_duration
                        
                        expire_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))
                        print(f"HTML解析成功！用户{display_username}获得{duration_hours}小时VIP，到期时间: {expire_str}")
                        return vip_duration
                    else:
                        print("HTML中未找到成功信息，签到可能失败")
            else:
                print(f"签到请求失败，状态码: {response.status_code}")
                
        except Exception as e:
            print(f"自动签到异常: {e}")
        
        # 签到失败时使用备用时长
        if self.vip_config['duration']:
            print("签到失败，使用备用时长参数")
            return self.vip_config['duration']
        
        return ''

    def _generate_device_vip(self):
        """生成基于设备的会员验证参数"""
        if not self.device_id:
            self.device_id = str(uuid.uuid4()).replace('-', '')  # 移除横杠，生成32位ID
        device_hash = hashlib.md5(self.device_id.encode()).hexdigest()[:16]
        timestamp = int(time.time())
        vip_data = {
            'device_id': self.device_id,
            'device_hash': device_hash,
            'timestamp': timestamp,
            'vip_type': 'device'
        }
        return base64.b64encode(json.dumps(vip_data).encode()).decode()

    def login(self):
        """账号密码登录"""
        try:
            payload = {
                'password': self.vip_config['password'],
                'code': "",
                'device_id': self.device_id,
                'user_name': self.vip_config['username'],
                'invite_code': "",
                'is_emulator': "0"
            }
            
            headers = self.header.copy()
            # 添加自动参数
            payload, headers = self._add_auto_params_to_request(payload, headers)
            
            response = self.post(f'{self.xurl}.index/appLogin', data=payload, headers=headers)
            if response.status_code == 200:
                response_data = response.json()
                encrypted_data = response_data['data']
                decrypted_data = self.decrypt(encrypted_data)
                user_info = json.loads(decrypted_data)
                
                auth_token = user_info['user']['auth_token']
                self.header['app-user-token'] = auth_token
                
                # 提取会员信息
                self._extract_vip_info(user_info)
                
        except Exception as e:
            print(f"登录失败: {e}")
            if self.vip_config['duration']:
                self.vip_duration = self.vip_config['duration']
                print("登录失败，使用备用时长参数")

    def _extract_vip_info(self, user_info):
        """从登录响应提取会员信息"""
        user_data = user_info.get('user', {})
        vip_status = user_data.get('vip_status', user_data.get('is_vip', 0))
        
        if vip_status == 1:
            if self.vip_config['duration']:
                self.vip_duration = self.vip_config['duration']
            else:
                # 生成基础会员参数
                vip_data = {
                    'user_id': user_data.get('user_id', ''),
                    'vip_level': user_data.get('vip_level', 1),
                    'login_time': int(time.time()),
                    'auth_token': self.header.get('app-user-token', '')[:20]
                }
                self.vip_duration = base64.b64encode(json.dumps(vip_data).encode()).decode()
            print("会员登录成功")
        else:
            self.vip_duration = ''
            print("当前账号不是会员")

    def homeContent(self, filter):
        kjson = self.init_data
        result = {"class": [], "filters": {}}
        for i in kjson['type_list']:
            if not(i['type_name'] in {'全部', 'QQ', 'juo.one'} or '企鹅群' in i['type_name']):
                result['class'].append({
                    "type_id": i['type_id'],
                    "type_name": i['type_name']
                })
            name_mapping = {'class': '类型', 'area': '地区', 'lang': '语言', 'year': '年份', 'sort': '排序'}
            filter_items = []
            for filter_type in i.get('filter_type_list', []):
                filter_name = filter_type.get('name')
                values = filter_type.get('list', [])
                if not values:
                    continue
                value_list = [{"n": value, "v": value} for value in values]
                display_name = name_mapping.get(filter_name, filter_name)
                key = 'by' if filter_name == 'sort' else filter_name
                filter_items.append({
                    "key": key,
                    "name": display_name,
                    "value": value_list
                })
            type_id = i.get('type_id')
            if filter_items:
                result["filters"][str(type_id)] = filter_items
        return result

    def homeVideoContent(self):
        # 使用home UA
        headers = self.header.copy()
        if self.home_ua:
            headers['User-Agent'] = self.home_ua
            
        videos = []
        kjson = self.init_data
        for i in kjson['type_list']:
            for item in i['recommend_list']:
                vod_id = item['vod_id']
                name = item['vod_name']
                pic = item['vod_pic']
                remarks = item['vod_remarks']
                video = {
                    "vod_id": vod_id,
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": remarks
                }
                videos.append(video)
        return {'list': videos}

    def categoryContent(self, cid, pg, filter, ext):
        # 使用category UA
        headers = self.header.copy()
        if self.category_ua:
            headers['User-Agent'] = self.category_ua
            
        videos = []
        payload = {
            'area': ext.get('area','全部'),
            'year': ext.get('year','全部'),
            'type_id': cid,
            'page': str(pg),
            'sort': ext.get('sort','最新'),
            'lang': ext.get('lang','全部'),
            'class': ext.get('class','全部')
        }
        
        payload, headers = self._add_vip_to_request(payload, headers)
        # 新增：添加自动生成参数
        payload, headers = self._add_auto_params_to_request(payload, headers)
        
        url = f'{self.xurl}.index/typeFilterVodList'
        res = self.post(url=url, headers=headers, data=payload, verify=False).json()
        encrypted_data = res['data']
        kjson = self.decrypt(encrypted_data)
        kjson1 = json.loads(kjson)
        for i in kjson1['recommend_list']:
            id = i['vod_id']
            name = i['vod_name']
            pic = i['vod_pic']
            remarks = i['vod_remarks']
            video = {
                "vod_id": id,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks
            }
            videos.append(video)
        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def detailContent(self, ids):
        did = ids[0]
        payload = {'vod_id': did}
        
        payload, headers = self._add_vip_to_request(payload)
        # 新增：添加自动生成参数
        payload, headers = self._add_auto_params_to_request(payload, headers)
        
        api_endpoints = ['vodDetail', 'vodDetail2']

        for endpoint in api_endpoints:
            url = f'{self.xurl}.index/{endpoint}'
            response = self.post(url=url, headers=headers, data=payload, verify=False)

            if response.status_code == 200:
                response_data = response.json()
                if '到期' in response_data.get('msg', '') or response_data.get('code', 1) == 0:
                    return None
                encrypted_data = response_data['data']
                kjson1 = self.decrypt(encrypted_data)
                kjson = json.loads(kjson1)
                break
        
        videos = []
        play_form = ''
        play_url = ''
        lineid = 1
        name_count = {}
        
        if self.sort_rule:
            def sort_key(line):
                line_name = line['player_info']['show'].lower()
                for idx, rule in enumerate(self.sort_rule):
                    if rule in line_name:
                        return idx
                return len(self.sort_rule)
            kjson['vod_play_list'].sort(key=sort_key)
        
        for line in kjson['vod_play_list']:
            keywords = {'防走丢', '群', '防失群', '官网'}
            player_show = line['player_info']['show']
            if any(keyword in player_show for keyword in keywords):
                player_show = f'{lineid}线'
                line['player_info']['show'] = player_show
            count = name_count.get(player_show, 0) + 1
            name_count[player_show] = count
            if count > 1:
                line['player_info']['show'] = f"{player_show}{count}"
            play_form += line['player_info']['show'] + '$$$'
            parse = line['player_info']['parse']
            parse_type = line['player_info']['parse_type']
            player_parse_type = line['player_info']['player_parse_type']
            kurls = ""
            for vod in line['urls']:
                token = 'token+' + vod['token']
                kurls += f"{str(vod['name'])}${parse},{vod['url']},{token},{player_parse_type},{parse_type}#"
            kurls = kurls.rstrip('#')
            play_url += kurls + '$$$'
            lineid += 1
        
        play_form = play_form.rstrip('$$$')
        play_url = play_url.rstrip('$$$')
        videos.append({
            "vod_id": did,
            "vod_name": kjson['vod']['vod_name'],
            "vod_actor": kjson['vod']['vod_actor'].replace('演员', ''),
            "vod_director": kjson['vod'].get('vod_director', '').replace('导演', ''),
            "vod_content": kjson['vod']['vod_content'],
            "vod_remarks": kjson['vod']['vod_remarks'],
            "vod_year": kjson['vod']['vod_year'] + '年',
            "vod_area": kjson['vod']['vod_area'],
            "vod_play_from": play_form,
            "vod_play_url": play_url
        })
        return {'list': videos}

    def playerContent(self, flag, id, vipFlags):
        line_name = flag
        # 使用player UA（兼容中文和大写参数）
        play_header = {'User-Agent': self.player_ua or self.playua}
        
        # 优化线路匹配逻辑 - 精确匹配优先
        line_settings = self.line_specific_settings.get(line_name, {})
        
        # 处理UA
        if 'ua' in line_settings:
            play_header['User-Agent'] = line_settings['ua']
        else:
            # 备用：尝试包含匹配（处理可能的名称变化）
            for line_key, settings in self.line_specific_settings.items():
                if line_key in line_name and 'ua' in settings:
                    play_header['User-Agent'] = settings['ua']
                    break
        
        # 处理Cookie
        if self.playcookie:
            play_header['Cookie'] = self.playcookie
            
        # 处理Referer
        referer = self.playreferer
        if 'referer' in line_settings:
            referer = line_settings['referer']
        else:
            # 备用：尝试包含匹配
            for line_key, settings in self.line_specific_settings.items():
                if line_key in line_name and 'referer' in settings:
                    referer = settings['referer']
                    break
        
        if referer:
            play_header['Referer'] = referer
            
        if self.vip_duration:
            play_header['vip-duration'] = self.vip_duration
        
        # 新增：为播放请求添加自动生成参数
        play_header = self._add_auto_params_to_request(headers=play_header)[1]
            
        url = ''
        aid = id.split(',')
        uid = aid[0]
        kurl = aid[1]
        token = aid[2].replace('token+', '')
        player_parse_type = aid[3]
        parse_type = aid[4]
        
        if parse_type == '0':
            res =  {"parse": 0, "url": kurl, "header": play_header}
        elif parse_type == '2':
            res = {"parse": 1, "url": uid+kurl, "header": play_header}
        elif player_parse_type == '2':
            response = self.fetch(url=f'{uid}{kurl}', headers=play_header, verify=False)
            if response.status_code == 200:
                kjson1 = response.json()
                res = {"parse": 0, "url": kjson1['url'], "header": play_header}
        else:
            id1 = self.encrypt(kurl)
            payload = {
                'parse_api': uid,
                'url': id1,
                'player_parse_type': player_parse_type,
                'token': token
            }
            
            if self.vip_duration:
                payload['vip_duration'] = self.vip_duration
                
            # 新增：为解析请求添加自动生成参数
            payload, parse_headers = self._add_auto_params_to_request(payload, self.header.copy())
                
            # 使用parse UA
            if self.parse_ua:
                parse_headers['User-Agent'] = self.parse_ua
                
            url1 = f"{self.xurl}.index/vodParse"
            response = self.post(url=url1, headers=parse_headers, data=payload, verify=False)
            if response.status_code == 200:
                response_data = response.json()
                encrypted_data = response_data['data']
                kjson = self.decrypt(encrypted_data)
                kjson1 = json.loads(kjson)
                kjson2 = kjson1['json']
                kjson3 = json.loads(kjson2)
                url = kjson3['url']
            res = {"parse": 0, "playUrl": '', "url": url, "header": play_header}
        return res

    def searchContent(self, key, quick, pg=1):
        # 使用search UA
        headers = self.header.copy()
        if self.search_ua:
            headers['User-Agent'] = self.search_ua
            
        videos = []
        if 'xiaohys.com' in self.xurl:
            host = self.xurl.split('api.php')[0]
            data = self.fetch(f'{host}index.php/ajax/suggest?mid=1&wd={key}').json()
            for i in data['list']:
                videos.append({
                    "vod_id": i['id'],
                    "vod_name": i['name'],
                    "vod_pic": i.get('pic')
                })
        else:
            payload = {
                'keywords': key,
                'type_id': "0",
                'page': str(pg)
            }
            
            payload, headers = self._add_vip_to_request(payload, headers)
            # 新增：添加自动生成参数
            payload, headers = self._add_auto_params_to_request(payload, headers)
            
            if self.search_verify:
                verifi = self.verification()
                if verifi is None:
                    return {'list':[]}
                payload['code'] = verifi['code']
                payload['key'] = verifi['uuid']
            
            url = f'{self.xurl}.index/searchList'
            res = self.post(url=url, data=payload, headers=headers, verify=False).json()
            if not res.get('data'):
                return {'list':[] ,'msg': res.get('msg')}
            encrypted_data = res['data']
            kjson = self.decrypt(encrypted_data)
            kjson1 = json.loads(kjson)
            for i in kjson1['search_list']:
                id = i['vod_id']
                name = i['vod_name']
                pic = i['vod_pic']
                remarks = i['vod_year'] + ' ' + i['vod_class']
                videos.append({
                    "vod_id": id,
                    "vod_name": name,
                    "vod_pic": pic,
                    "vod_remarks": remarks
                })
        return {'list': videos, 'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 999999}

    def verification(self):
        random_uuid = str(uuid.uuid4())
        dat = self.fetch(f'{self.xurl}.verify/create?key={random_uuid}', headers=self.header, verify=False).content
        base64_img = base64.b64encode(dat).decode('utf-8')
        if not dat:
            return None
        code = self.ocr(base64_img)
        if not code:
            return None
        code = self.replace_code(code)
        if not (len(code) == 4 and code.isdigit()):
            return None
        return {'uuid': random_uuid, 'code': code}

    def replace_code(self, text):
        replacements = {'y': '9', '口': '0', 'q': '0', 'u': '0', 'o': '0', '>': '1', 'd': '0', 'b': '8', '已': '2','D': '0', '五': '5'}
        if len(text) == 3:
            text = text.replace('566', '5066')
            text = text.replace('066', '1666')
        return ''.join(replacements.get(c, c) for c in text)

    def ocr(self, base64img):
        dat2 = self.post("https://api.nn.ci/ocr/b64/text", data=base64img, headers=self.header, verify=False).text
        if dat2:
            return dat2
        else:
            return None

    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def decrypt(self, encrypted_data_b64):
        key_bytes = self.key.encode('utf-8')
        iv_bytes = self.iv.encode('utf-8')
        encrypted_data = base64.b64decode(encrypted_data_b64)
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
        decrypted_padded = cipher.decrypt(encrypted_data)
        decrypted = unpad(decrypted_padded, AES.block_size)
        return decrypted.decode('utf-8')

    def encrypt(self, sencrypted_data):
        key_bytes = self.key.encode('utf-8')
        iv_bytes = self.iv.encode('utf-8')
        data_bytes = sencrypted_data.encode('utf-8')
        padded_data = pad(data_bytes, AES.block_size)
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
        encrypted_bytes = cipher.encrypt(padded_data)
        encrypted_data_b64 = base64.b64encode(encrypted_bytes).decode('utf-8')
        return encrypted_data_b64

    def _generate_random_ua(self):
        """生成随机安卓App User-Agent"""
        android_app_ua_templates = [
            "Dalvik/2.1.0 (Linux; U; Android {android_version}; {device} Build/{build})",
            "okhttp/3.14.9",
            "Mozilla/5.0 (Linux; Android {android_version}; {device}) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/{chrome_version} Mobile Safari/537.36"
        ]
        
        android_versions = ["14", "13", "12", "11", "10", "9.0", "8.1"]
        devices = [
            "SM-G9910", "SM-G9980", "SM-G9960", "SM-G7810", "SM-G9860", 
            "Mi 10", "Mi 11", "Mi 12", "Redmi K40", "Redmi K50",
            "V2148A", "V2217A", "V2220A", "V2309A", "V2314A",
            "PCT-AL10", "JEF-AN00", "HLK-AL00", "CDY-AN95", "OXF-AN00"
        ]
        builds = ["SKQ1.211006.001", "RP1A.200720.012", "TP1A.220624.014", "SP1A.210812.016"]
        chrome_versions = ["114.0.5735.196", "115.0.5790.166", "116.0.5845.163", "117.0.5938.92"]
        
        template = random.choice(android_app_ua_templates)
        android_version = random.choice(android_versions)
        device = random.choice(devices)
        build = random.choice(builds)
        chrome_version = random.choice(chrome_versions)
        
        return template.format(
            android_version=android_version,
            device=device,
            build=build,
            chrome_version=chrome_version
        )

    def _generate_android_id(self):
        """生成安卓ID"""
        # 生成16位十六进制字符串（安卓ID格式）
        return ''.join(random.choice('0123456789abcdef') for _ in range(16))

    def _add_auto_params_to_request(self, payload=None, headers=None):
        """添加自动生成参数到请求（核心修复）"""
        if headers is None:
            headers = self.header.copy()
        if payload is None:
            payload = {}
            
        # 如果自动参数级别为0，直接返回
        if self.auto_params_level == 0:
            return payload, headers
            
        print(f"自动参数级别{self.auto_params_level}，开始添加参数...")
            
        # 级别1-3都需要设备ID
        if self.auto_params_level >= 1 and self.device_id:
            headers['app-user-device-id'] = self.device_id
            payload['device_id'] = self.device_id
            print(f"添加设备ID: {self.device_id}")
            
        # 级别2和3需要时间戳和签名
        if self.auto_params_level >= 2:
            # 优先使用外置时间戳，否则自动生成
            if self.ext_timestamp:
                timestamp = self.ext_timestamp
                print("使用外置时间戳")
            else:
                timestamp = str(int(time.time()))
                print("自动生成时间戳")
                
            # 优先使用外置签名，否则自动生成
            if self.ext_sign:
                sign = self.ext_sign
                print("使用外置签名")
            else:
                sign = self.encrypt(timestamp)
                print("自动生成签名")
                
            headers['app-api-verify-time'] = timestamp
            headers['app-api-verify-sign'] = sign
            payload['timestamp'] = timestamp
            payload['sign'] = sign
            
            print(f"添加时间戳: {timestamp}")
            print(f"添加签名: {sign[:20]}...")
            
        # 级别3需要安卓ID
        if self.auto_params_level >= 3:
            # 优先使用外置安卓ID，否则自动生成
            if self.ext_android_id:
                android_id = self.ext_android_id
                print("使用外置安卓ID")
            else:
                android_id = self._generate_android_id()
                print("自动生成安卓ID")
                
            headers['app-android-id'] = android_id
            payload['android_id'] = android_id
            print(f"添加安卓ID: {android_id}")
            
        print("自动参数添加完成")
        return payload, headers

    def _add_vip_to_request(self, payload=None, headers=None):
        """添加会员验证参数到请求"""
        if headers is None:
            headers = self.header.copy()
        if payload is None:
            payload = {}
            
        if self.vip_duration:
            payload['vip_duration'] = self.vip_duration
            headers['vip-duration'] = self.vip_duration
            
        return payload, headers

if __name__ == '__main__':
    pass