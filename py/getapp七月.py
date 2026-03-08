# coding = utf-8
#!/usr/bin/python
# 新时代青年 2025.06.25 getApp第三版  后续平凡哥 七月大姐等大佬魔改 最后更新2025.10.1七月版
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
    enable_delay = False
    current_domain_index = 0
    available_domains = []
    
    host_ua = ''
    config_ua = ''
    home_ua = ''
    category_ua = ''
    search_ua = ''
    parse_ua = ''
    player_ua = ''
    
    auto_params_level = 0
    ext_timestamp = ''
    ext_sign = ''
    ext_android_id = ''
    ext_device_id = ''
    
    app_version_code = ''
    app_verify_sign = ''

    user_token = ''
    auth_token = ''

    # 新增：登录参数存储
    login_timestamp = ''
    login_sign = ''
    login_device_id = ''

    def __init__(self):
        self.header = {'User-Agent': self._generate_random_ua()}
        self.current_domain_index = 0
        self.available_domains = []
        # 初始化登录参数
        self.login_timestamp = ''
        self.login_sign = ''
        self.login_device_id = ''

    def getName(self):
        return "首页"

    def init(self, extend=''):
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
            'token_expire': 'token_expire',
            'appversioncode': 'app_version_code',
            'appverifySign': 'app_verify_sign',
            'AppVersionCode': 'app_version_code',
            'AppverifySign': 'app_verify_sign',
            '签名': 'sign',
            '时间戳': 'timestamp',
            '安卓ID': 'android_id',
            'app版本号': 'app_version_code',
            'app验证签名': 'app_verify_sign'
        }
        
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
        
        english_ext = {}
        for key, value in ext.items():
            lower_key = key.lower()
            if lower_key in chinese_param_map:
                english_ext[chinese_param_map[lower_key]] = value
            elif key in ua_chinese_map:
                english_ext[ua_chinese_map[key]] = value
            else:
                english_ext[key] = value
        
        host = english_ext['host']
        
        self.enable_delay = english_ext.get('延迟', english_ext.get('enable_delay', '0')) == '1'
        
        auto_params_str = english_ext.get('auto_params', english_ext.get('自动参数', '0'))
        try:
            self.auto_params_level = int(auto_params_str)
        except ValueError:
            self.auto_params_level = 0
        
        self.ext_timestamp = english_ext.get('timestamp', english_ext.get('时间戳', ''))
        self.ext_sign = english_ext.get('sign', english_ext.get('签名', ''))
        self.ext_android_id = english_ext.get('android_id', english_ext.get('安卓ID', ''))
        self.ext_device_id = english_ext.get('deviceid', english_ext.get('devideid', ''))
        
        # 只有外置配置了才设置，否则为空
        app_version_raw = english_ext.get('app_version_code', english_ext.get('AppVersionCode', ''))
        self.app_version_code = self._format_version_code(app_version_raw) if app_version_raw else ''
        
        app_verify_raw = english_ext.get('app_verify_sign', english_ext.get('AppverifySign', ''))
        self.app_verify_sign = self._format_verify_sign(app_verify_raw) if app_verify_raw else ''
        
        host_index_str = str(english_ext.get('host_index', '1')).strip()
        try:
            host_index = int(host_index_str) if host_index_str else 1
        except ValueError:
            host_index = 1
        
        self.available_domains = self._get_available_domains(host, host_index)
        if not self.available_domains:
            print("错误：无法获取可用的域名")
            return
            
        host = self.available_domains[0]
        print(f"选择域名: {host}")
        
        ua = english_ext.get('ua')
        if ua:
            self.header['User-Agent'] = ua
        
        self.host_ua = self._get_ua_param(english_ext, ['hostua', 'hostUA', '首页ua', '首页UA'])
        self.config_ua = self._get_ua_param(english_ext, ['configua', 'configUA', '配置ua', '配置UA'])
        self.home_ua = self._get_ua_param(english_ext, ['homeua', 'homeUA', '首页ua', '首页UA'])
        self.category_ua = self._get_ua_param(english_ext, ['categoryua', 'categoryUA', '分类ua', '分类UA'])
        self.search_ua = self._get_ua_param(english_ext, ['searchua', 'searchUA', '搜索ua', '搜索UA'])
        self.parse_ua = self._get_ua_param(english_ext, ['parseua', 'parseUA', '解析ua', '解析UA'])
        self.player_ua = self._get_ua_param(english_ext, ['playerua', 'playerUA', '播放ua', '播放UA'])
        
        self.vip_config = {
            'type': english_ext.get('login_type', 'token'),
            'duration': english_ext.get('会员时长', ''),
            'username': english_ext.get('username', ''),
            'password': english_ext.get('password', ''),
            'token': english_ext.get('token', ''),
            'auth_token': english_ext.get('auth_token', ''),
            'user_id': english_ext.get('user_id', ''),
            'refresh_token': english_ext.get('refresh_token', ''),
            'token_expire': english_ext.get('token_expire', '0')
        }
        
        self._handle_device_id_generation()
        
        if self.device_id:
            self.header['app-user-device-id'] = self.device_id
        
        api = english_ext.get('api', '/api.php/getappapi')
        if str(api) == '2':
            api = '/api.php/qijiappapi'
        self.xurl = host + api
        self.key = english_ext['datakey']
        self.iv = english_ext.get('dataiv', self.key)
        
        sort_rule_str = english_ext.get('排序', '')
        if sort_rule_str:
            self.sort_rule = [s.strip().lower() for s in sort_rule_str.split('>')]
        else:
            self.sort_rule = []
        
        print("=== 初始化阶段开始 ===")
        self._init_login()
        
        self._handle_vip_verification()
        
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
        
        init_headers = self.header.copy()
        if self.config_ua:
            init_headers['User-Agent'] = self.config_ua
            
        init_payload = {}
        init_payload, init_headers = self._add_all_params_to_request(init_payload, init_headers)
        
        success = False
        for domain in self.available_domains:
            try:
                self.xurl = domain + api
                print(f"尝试初始化域名: {domain}")
                
                init_headers = self._build_complete_headers(init_headers)
                
                res = self.fetch(self.xurl + '.index/initV119', headers=init_headers, verify=False)
                
                if res.status_code != 200:
                    print(f"初始化请求失败，状态码: {res.status_code}")
                    continue
                    
                res_data = res.json()
                encrypted_data = res_data['data']
                response = self.decrypt(encrypted_data)
                init_data = json.loads(response)
                
                if init_data:
                    self.init_data = init_data
                    self.search_verify = init_data['config'].get('system_search_verify_status', False)
                    print(f"域名 {domain} 初始化成功")
                    success = True
                    break
            except Exception as e:
                print(f"域名 {domain} 初始化失败: {e}")
                continue
        
        if not success:
            print("所有域名初始化失败，请检查网络或域名配置")

    def _init_login(self):
        print("=== 初始化阶段登录开始 ===")
        
        # 优先使用账号密码登录，可以获取最新token
        if self.vip_config['type'] == 'login' and self.vip_config['username'] and self.vip_config['password']:
            print("检测到登录配置，开始自动登录...")
            success = self.login()
            if success:
                print("=== 初始化阶段登录成功！ ===")
                print(f"获取到的token: {self.user_token}")
                return True
            else:
                print("=== 初始化阶段登录失败，尝试使用配置的token ===")
                # 登录失败后尝试使用配置的token
        
        # 其次使用配置的token
        if self.vip_config.get('token'):
            self.header['app-user-token'] = self.vip_config['token']
            self.user_token = self.vip_config['token']
            print(f"使用配置中的token: {self.user_token[:20]}...")
            return True
            
        # 最后使用认证令牌
        if self.vip_config.get('auth_token'):
            self.header['app-user-token'] = self.vip_config['auth_token']
            self.auth_token = self.vip_config['auth_token']
            print(f"使用配置中的auth_token: {self.auth_token[:20]}...")
            return True
                
        print("未配置登录信息，使用游客模式")
        return False

    def _build_complete_headers(self, headers=None):
        if headers is None:
            headers = self.header.copy()
            
        base_headers = {
            'Accept-Encoding': 'gzip',
            'Connection': 'Keep-Alive',
            'User-Agent': 'okhttp/3.14.9',
            'app-ui-mode': 'light'
        }
        
        headers.update(base_headers)
        
        # 只有外置配置了才添加
        if self.app_version_code:
            headers['app-version-code'] = self.app_version_code
            
        if self.app_verify_sign:
            headers['app-verify-sign'] = self.app_verify_sign
            
        if self.device_id:
            headers['app-user-device-id'] = self.device_id
            
        if self.user_token:
            headers['app-user-token'] = self.user_token
        elif self.auth_token:
            headers['app-user-token'] = self.auth_token
            
        if self.ext_timestamp:
            headers['app-api-verify-time'] = self.ext_timestamp
        if self.ext_sign:
            headers['app-api-verify-sign'] = self.ext_sign
            
        return headers

    def _generate_api_sign(self, timestamp):
        if self.ext_sign:
            print(f"使用外置签名: {self.ext_sign}")
            return self.ext_sign
            
        if self.device_id:
            sign_data = f"{self.device_id}{timestamp}"
            sign_hash = hashlib.md5(sign_data.encode()).digest()
            sign = base64.b64encode(sign_hash).decode()
            print(f"使用设备ID+时间戳生成签名: {sign}")
            return sign
            
        sign = self.encrypt(timestamp)
        print(f"使用时间戳加密生成签名: {sign}")
        return sign

    def _format_version_code(self, version_raw):
        if not version_raw:
            return ''
        
        version_clean = re.sub(r'[^\d]', '', str(version_raw))
        
        if not version_clean:
            return ''
            
        if len(version_clean) > 4:
            version_clean = version_clean[:4]
            
        print(f"版本号格式化: {version_raw} -> {version_clean}")
        return version_clean

    def _format_verify_sign(self, verify_raw):
        if not verify_raw:
            return ''
        
        verify_str = str(verify_raw).strip()
        if verify_str.endswith('.'):
            verify_str = verify_str[:-1]
            
        print(f"验证签名格式化: {verify_raw} -> {verify_str}")
        return verify_str

    def _add_all_params_to_request(self, payload=None, headers=None):
        if headers is None:
            headers = self.header.copy()
        if payload is None:
            payload = {}
            
        print("开始添加请求参数...")
        
        headers, payload = self._add_external_params_to_request(headers, payload)
        
        payload, headers = self._add_auto_params_to_request(payload, headers)
        
        # App版本号和验证签名只有外置配置了才添加
        headers = self._add_app_params_to_headers(headers)
        
        print("所有参数添加完成")
        return payload, headers

    def _add_external_params_to_request(self, headers, payload):
        print("检查外置参数...")
        
        if self.ext_device_id:
            self.device_id = self.ext_device_id
            headers['app-user-device-id'] = self.device_id
            payload['device_id'] = self.device_id
            print(f"使用外置设备ID: {self.device_id}")
        elif self.device_id:
            headers['app-user-device-id'] = self.device_id
            payload['device_id'] = self.device_id
            print(f"使用自动生成设备ID: {self.device_id}")
        
        has_external_ts = bool(self.ext_timestamp)
        has_external_sign = bool(self.ext_sign)
        
        if has_external_ts or has_external_sign:
            print("检测到外置时间戳或签名参数")
            
            if self.ext_timestamp:
                timestamp = self.ext_timestamp
                print(f"使用外置时间戳: {timestamp}")
            else:
                timestamp = str(int(time.time()))
                print(f"自动生成时间戳: {timestamp}")
            
            if self.ext_sign:
                sign = self.ext_sign
                print(f"使用外置签名: {sign}")
            else:
                sign = self._generate_api_sign(timestamp)
                print(f"自动生成签名: {sign[:20]}...")
            
            headers.update({
                'app-api-verify-time': timestamp,
                'app-api-verify-sign': sign,
                'Accept-Encoding': "gzip",
                'app-ui-mode': "light"
            })
            payload.update({
                'timestamp': timestamp,
                'sign': sign
            })
        
        if self.ext_android_id:
            headers['app-android-id'] = self.ext_android_id
            payload['android_id'] = self.ext_android_id
            print(f"使用外置安卓ID: {self.ext_android_id}")
        
        return headers, payload

    def _add_app_params_to_headers(self, headers):
        # 只有外置配置了才添加
        if self.app_version_code:
            headers['app-version-code'] = self.app_version_code
            print(f"添加App版本号: {self.app_version_code}")
        
        if self.app_verify_sign:
            headers['app-verify-sign'] = self.app_verify_sign
            print(f"添加App签名标识: {self.app_verify_sign}")
            
        return headers

    def _get_available_domains(self, host, host_index=1):
        domains = []
        
        if re.match(r'^https?:\/\/[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*(:\d+)?(\/)?$', host):
            domains.append(host.rstrip('/'))
            print(f"使用直接域名: {host}")
            return domains
        
        try:
            print(f"获取动态域名列表: {host}")
            response = self.fetch(host, headers=self.header, timeout=10, verify=False)
            text = response.text.strip()
            
            domain_lines = [line.strip() for line in text.splitlines() if line.strip()]
            print(f"获取到 {len(domain_lines)} 个域名")
            
            for line in domain_lines:
                domain = line.rstrip('/')
                if not domain.startswith(('http://', 'https://')):
                    domain = 'https://' + domain
                domains.append(domain)
                
            if domains:
                try:
                    index = host_index - 1
                    if 0 <= index < len(domains):
                        selected_domain = domains[index]
                        print(f"根据索引选择域名: {selected_domain} (索引: {host_index})")
                        return [selected_domain]
                    else:
                        print(f"索引 {host_index} 超出范围，使用第一个域名")
                        return [domains[0]]
                except ValueError:
                    print("host_index参数错误，使用第一个域名")
                    return [domains[0]]
            else:
                print("未获取到有效域名")
                return []
                
        except Exception as e:
            print(f"获取域名列表失败: {e}")
            return []

    def _switch_domain(self):
        if len(self.available_domains) <= 1:
            print("只有一个域名，无法切换")
            return False
            
        self.current_domain_index = (self.current_domain_index + 1) % len(self.available_domains)
        new_domain = self.available_domains[self.current_domain_index]
        
        api = self.xurl.split('/api.php')[1] if '/api.php' in self.xurl else '/api.php/getappapi'
        self.xurl = new_domain + api
        
        print(f"切换到域名: {new_domain}")
        return True

    def _handle_device_id_generation(self):
        if self.ext_device_id:
            return
        
        if self.auto_params_level >= 1:
            self.device_id = str(uuid.uuid4()).replace('-', '')
            print(f"自动生成设备ID(级别{self.auto_params_level}): {self.device_id}")
        else:
            self.device_id = ''
            print("自动参数级别0，不生成设备ID")

    def _get_ua_param(self, ext, param_names, default=''):
        for name in param_names:
            value = ext.get(name)
            if value:
                return value
        return default

    def _get_param(self, ext, param_names, default=''):
        for name in param_names:
            value = ext.get(name)
            if value:
                return value
        return default

    def _apply_request_delay(self):
        if self.enable_delay:
            delay_time = random.uniform(1, 3)
            time.sleep(delay_time)

    def fetch(self, url, **kwargs):
        if 'playerContent' not in sys._getframe(2).f_code.co_name:
            self._apply_request_delay()
        
        max_retries = 2
        for retry in range(max_retries + 1):
            try:
                if 'headers' in kwargs:
                    kwargs['headers'] = self._build_complete_headers(kwargs['headers'])
                else:
                    kwargs['headers'] = self._build_complete_headers()
                
                response = super().fetch(url, **kwargs)
                if response.status_code == 200:
                    return response
                elif response.status_code >= 500 and retry < max_retries:
                    print(f"请求失败，状态码: {response.status_code}, 重试 {retry + 1}/{max_retries}")
                    self._switch_domain()
                    time.sleep(1)
            except Exception as e:
                if retry < max_retries:
                    print(f"请求异常: {e}, 重试 {retry + 1}/{max_retries}")
                    self._switch_domain()
                    time.sleep(1)
                else:
                    raise e
        return response

    def post(self, url, **kwargs):
        if 'playerContent' not in sys._getframe(2).f_code.co_name:
            self._apply_request_delay()
        
        max_retries = 2
        for retry in range(max_retries + 1):
            try:
                if 'headers' in kwargs:
                    kwargs['headers'] = self._build_complete_headers(kwargs['headers'])
                else:
                    kwargs['headers'] = self._build_complete_headers()
                
                response = super().post(url, **kwargs)
                if response.status_code == 200:
                    return response
                elif response.status_code >= 500 and retry < max_retries:
                    print(f"请求失败，状态码: {response.status_code}, 重试 {retry + 1}/{max_retries}")
                    self._switch_domain()
                    time.sleep(1)
            except Exception as e:
                if retry < max_retries:
                    print(f"请求异常: {e}, 重试 {retry + 1}/{max_retries}")
                    self._switch_domain()
                    time.sleep(1)
                else:
                    raise e
        return response

    def _handle_vip_verification(self):
        vip_type = self.vip_config['type']
        
        if vip_type == 'token':
            if self.vip_config['token']:
                self.header['app-user-token'] = self.vip_config['token']
                self.user_token = self.vip_config['token']
                self.vip_duration = self.vip_config['duration']
                print("手动选择: Token验证模式")
            else:
                print("Token模式但未提供token，使用游客模式")
                self.vip_duration = ''
        
        elif vip_type == 'login':
            if self.vip_config['username'] and self.vip_config['password']:
                if not (self.user_token or self.auth_token):
                    print("登录模式但登录失败，使用游客模式")
                    self.vip_duration = ''
                else:
                    print("账号密码登录成功，使用获取到的token")
                    self.vip_duration = self.vip_config['duration']
            else:
                print("账号密码模式但未提供用户名密码，使用游客模式")
                self.vip_duration = ''
        
        else:
            print(f"未知的登录模式: {vip_type}, 使用游客模式")
            self.vip_duration = ''

    def login(self):
        try:
            if not self.vip_config['username'] or not self.vip_config['password']:
                print("登录失败：未提供用户名或密码")
                return False
                
            print(f"=== 登录调试信息 ===")
            print(f"用户名: {self.vip_config['username']}")
            print(f"设备ID: {self.device_id}")
            
            # 生成登录参数
            timestamp = str(int(time.time()))
            sign = self._generate_api_sign(timestamp)
            
            # 保存登录参数供后续请求使用
            self.login_timestamp = timestamp
            self.login_sign = sign
            self.login_device_id = self.device_id
            
            print(f"登录参数已保存 - 时间戳: {timestamp}, 签名: {sign[:20]}..., 设备ID: {self.device_id}")
            
            payload = {
                'password': self.vip_config['password'],
                'code': "",
                'device_id': self.device_id,
                'user_name': self.vip_config['username'],
                'invite_code': "",
                'is_emulator': "0",
                'timestamp': timestamp,
                'sign': sign,
                'version': '1.0.0',
                'platform': 'android'
            }
            
            headers = self._build_complete_headers()
            headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Content-Length': str(len('&'.join([f'{k}={v}' for k, v in payload.items()])))
            })
            
            print(f"登录请求参数: {payload}")
            
            login_url = f'{self.xurl}.index/appLogin'
            print(f"登录URL: {login_url}")
            
            response = self.post(login_url, data=payload, headers=headers, verify=False)
            
            if response.status_code == 200:
                response_data = response.json()
                print(f"登录响应状态码: {response_data.get('code')}")
                print(f"登录响应消息: {response_data.get('msg')}")
                print(f"完整响应: {response_data}")
                
                if response_data.get('code') == 1:
                    encrypted_data = response_data['data']
                    decrypted_data = self.decrypt(encrypted_data)
                    print(f"解密后的数据: {decrypted_data}")
                    user_info = json.loads(decrypted_data)
                    
                    if 'user' in user_info and 'auth_token' in user_info['user']:
                        auth_token = user_info['user']['auth_token']
                        self.header['app-user-token'] = auth_token
                        self.user_token = auth_token
                        self.auth_token = auth_token
                        
                        print(f"登录成功，获取到token: {auth_token}")
                        
                        user_id = user_info['user'].get('user_id', '')
                        vip_days = user_info['user'].get('vip_days', 0)
                        
                        vip_data = {
                            'user_id': user_id,
                            'auth_token': auth_token,
                            'vip_days': vip_days,
                            'login_time': int(time.time()),
                            'is_vip': user_info['user'].get('is_vip', False)
                        }
                        self.vip_duration = base64.b64encode(json.dumps(vip_data).encode()).decode()
                        
                        print(f"用户ID: {user_id}, VIP天数: {vip_days}")
                        return True
                    else:
                        print("登录响应中未找到auth_token")
                        print(f"用户信息结构: {user_info}")
                        return False
                else:
                    error_msg = response_data.get('msg', '未知错误')
                    print(f"登录失败: {error_msg}")
                    return False
            else:
                print(f"登录请求失败，状态码: {response.status_code}")
                print(f"响应内容: {response.text}")
                return False
                
        except Exception as e:
            print(f"登录异常: {e}")
            import traceback
            print(f"详细异常信息: {traceback.format_exc()}")
            return False

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
        
        payload, headers = self._add_all_params_to_request(payload, headers)
        
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
        
        payload, headers = self._add_all_params_to_request(payload)
        
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
        play_header = {'User-Agent': self.player_ua or self.playua}
        
        line_settings = self.line_specific_settings.get(line_name, {})
        
        if 'ua' in line_settings:
            play_header['User-Agent'] = line_settings['ua']
        else:
            for line_key, settings in self.line_specific_settings.items():
                if line_key in line_name or line_name in line_key:
                    if 'ua' in settings:
                        play_header['User-Agent'] = settings['ua']
                    break
        
        if 'referer' in line_settings:
            play_header['Referer'] = line_settings['referer']
        else:
            for line_key, settings in self.line_specific_settings.items():
                if line_key in line_name or line_name in line_key:
                    if 'referer' in settings:
                        play_header['Referer'] = settings['referer']
                    break
        
        if self.playcookie:
            play_header['Cookie'] = self.playcookie
        
        if self.playreferer and 'Referer' not in play_header:
            play_header['Referer'] = self.playreferer
            
        if self.vip_duration:
            play_header['vip-duration'] = self.vip_duration
        
        play_header = self._add_all_params_to_request(headers=play_header)[1]
            
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
                
            payload, parse_headers = self._add_all_params_to_request(payload, self.header.copy())
                
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
            
            payload, headers = self._add_all_params_to_request(payload, headers)
            
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

    def proxyM3u8(self, params):
        action = {
            'url': params['url'],
            'header': params.get('header', {}),
            'param': params.get('param', ''),
            'type': 'm3u8'
        }
        return action

    def proxyMedia(self, params):
        action = {
            'url': params['url'],
            'header': params.get('header', {}),
            'param': params.get('param', ''),
            'type': 'media'
        }
        return action

    def proxyTs(self, params):
        action = {
            'url': params['url'],
            'header': params.get('header', {}),
            'param': params.get('param', ''),
            'type': 'ts'
        }
        return action

    def isVideoFormat(self, url):
        video_formats = ['.m3u8', '.mp4', '.avi', '.mkv', '.flv', '.ts']
        return any(url.lower().endswith(fmt) for fmt in video_formats)

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
        return ''.join(random.choice('0123456789abcdef') for _ in range(16))

    def _add_auto_params_to_request(self, payload=None, headers=None):
        if headers is None:
            headers = self.header.copy()
        if payload is None:
            payload = {}
            
        # 优先级1：如果存在登录参数且是登录模式，优先使用登录参数
        if (self.vip_config['type'] == 'login' and 
            self.login_timestamp and self.login_sign and self.login_device_id):
            print("使用登录时生成的参数进行后续请求")
            
            headers.update({
                'app-api-verify-time': self.login_timestamp,
                'app-api-verify-sign': self.login_sign,
                'app-user-device-id': self.login_device_id,
                'Accept-Encoding': "gzip",
                'app-ui-mode': "light"
            })
            payload.update({
                'timestamp': self.login_timestamp,
                'sign': self.login_sign,
                'device_id': self.login_device_id
            })
            
            return payload, headers
            
        # 优先级2：外置参数（最高优先级）
        has_external_ts = bool(self.ext_timestamp)
        has_external_sign = bool(self.ext_sign)
        
        if has_external_ts or has_external_sign:
            print("检测到外置时间戳或签名参数")
            
            timestamp = self.ext_timestamp if self.ext_timestamp else str(int(time.time()))
            sign = self.ext_sign if self.ext_sign else self._generate_api_sign(timestamp)
            
            headers.update({
                'app-api-verify-time': timestamp,
                'app-api-verify-sign': sign,
                'Accept-Encoding': "gzip",
                'app-ui-mode': "light"
            })
            payload.update({
                'timestamp': timestamp,
                'sign': sign
            })
            
            # 如果有设备ID也加上
            if self.device_id:
                headers['app-user-device-id'] = self.device_id
                payload['device_id'] = self.device_id
                
            return payload, headers
            
        # 优先级3：自动参数级别
        if self.auto_params_level == 0:
            return payload, headers
            
        print(f"自动参数级别{self.auto_params_level}，开始添加自动生成参数...")
            
        if self.auto_params_level >= 1 and not self.device_id:
            self.device_id = str(uuid.uuid4()).replace('-', '')
            headers['app-user-device-id'] = self.device_id
            payload['device_id'] = self.device_id
            print(f"自动生成设备ID: {self.device_id}")
            
        if self.auto_params_level >= 2:
            timestamp = str(int(time.time()))
            sign = self._generate_api_sign(timestamp)
            
            print(f"自动生成时间戳: {timestamp}")
            print(f"自动生成签名: {sign[:20]}...")
            
            headers.update({
                'app-api-verify-time': timestamp,
                'app-api-verify-sign': sign,
                'Accept-Encoding': "gzip",
                'app-ui-mode': "light"
            })
            payload.update({
                'timestamp': timestamp,
                'sign': sign
            })
            
        print("自动参数添加完成")
        return payload, headers

if __name__ == '__main__':
    pass