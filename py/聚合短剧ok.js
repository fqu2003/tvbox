/*
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '聚合短剧',
  lang: 'cat'
})
*/

import { Crypto as CryptoJS } from 'assets://js/lib/cat.js';

let shuaCache = [];
let siteName = '聚合短剧';
let xingya_headers = {};
let niuniu_headers = {}; 
let niuniu_token = '';
let niuniu_access_token = ''; 
let hema_headers = {};

// ==================== 51短剧 专属配置与变量 ====================
let HOST_51 = 'https://51hub.com';
let OAUTH_ID_51 = '';
let TOKEN_51 = '';
function getProxyUrl_51(url) {
    return getProxy(true) + '&type=img&url=' + encodeURIComponent(url);
}
const HEADER_51 = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Connection": "keep-alive",
    "X-Requested-With": "XMLHttpRequest"
};
const AES_CONFIG_51 = {
    video: { key: '2acf7e91e9864673', iv: '1c29882d3ddfcfd6' },
    img: { key: 'f5d965df75336270', iv: '97b60394abc2fbe1' }
};

// 分类排除规则（已移除失效平台）
const cate_remove = ['分类排除'];

const aggConfig = {
  keys: 'd3dGiJc651gSQ8w1',
  charMap: {
    '+': 'P', '/': 'X', '0': 'M', '1': 'U', '2': 'l', '3': 'E', '4': 'r', '5': 'Y', '6': 'W', '7': 'b', '8': 'd', '9': 'J',
    'A': '9', 'B': 's', 'C': 'a', 'D': 'I', 'E': '0', 'F': 'o', 'G': 'y', 'H': '_', 'I': 'H', 'J': 'G', 'K': 'i', 'L': 't',
    'M': 'g', 'N': 'N', 'O': 'A', 'P': '8', 'Q': 'F', 'R': 'k', 'S': '3', 'T': 'h', 'U': 'f', 'V': 'R', 'W': 'q', 'X': 'C',
    'Y': '4', 'Z': 'p', 'a': 'm', 'b': 'B', 'c': 'O', 'd': 'u', 'e': 'c', 'f': '6', 'g': 'K', 'h': 'x', 'i': '5', 'j': 'T',
    'k': '-', 'l': '2', 'm': 'z', 'n': 'S', 'o': 'Z', 'p': '1', 'q': 'V', 'r': 'v', 's': 'j', 't': 'Q', 'u': '7', 'v': 'D',
    'w': 'w', 'x': 'n', 'y': 'L', 'z': 'e'
  },
  headers: {
    default: {
        'User-Agent': 'okhttp/5.1.0',
        'Content-Type': 'application/json'
    },
    niuniu: {'Cache-Control':'no-cache','Content-Type':'application/json;charset=UTF-8','User-Agent':'okhttp/4.12.0'},
    baidu: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; 22081212C Build/PQ3B.190801.002) Talos/1.8.13 SP-engine/3.47.0 bd_dvt/1 baiduboxapp/15.21.0.10 (Baidu; P1 9)'
    },
    haokan: {
      'User-Agent': 'Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/87.0.4280.141 Mobile Safari/537.36 haokan/7.80.0.18 (Baidu; P1 11)/imoaiX_03_11_C01K2102M/1043677m/5ACDB023CFB9D64743B08E51953F7C76%7CVSAJ32AVA/1/7.80.0.18/780001/1/immersiveMode/modeV4PlusWhite/isFirstInstall/bbqMode/bbqModeV2/blackStyle/isPlaylet Talos/1.8.7',
      'Talos-Module-Name': 'shortDrama',
      'Talos-Module-Version': '1.0.71.1',
      'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
      'Cookie': 'BAIDUCUID=giHCu0azv80G8SfQ0avU8gaaH8jfiv86ju2MugiR2i8-k3a35avAa1_mA'
    },
    hema: {
      'datas': 'e5f22c6e2c82fe001738cb9ce4696eab0556d064a55aef402e0fbe6b29a083f6538e4567de38e67de2071a49d9751526bfba45314e1fd4702b11c76ab9a3b5f873262854ba66e6715ed51364dbc6ee62c7180e047fcbcdbfd49874fc8f28674b16d90ca71a02de76c70598e0b75e647c37c2c19287e49be5f2a259d727dfc4df3d28802388bf3c356576b342e17e30a2ab74859263dba4d1c8eba79990d22d60d60927fdacb2addf2f0eaadd8887585ca2eb87f603faf0c207dda18cf67dc25b2199d303baff9e6605b3314a7d2631f62864f48619daceb9452f2b7b0667773553741856df030cca68af3c57810f983d452bb428ef5fc32206aef4865ae06c629bee7f5135547304acc7ef4e7c6df887308f2e79c493fd2ee03488722861b5bb51b09cb8911dfc92c288d94e601c066d2f9d612ad2c8d4eeb4920b1d44aff3e13fd75229b857f64925df1cf12f75a00d438c422ec1726462b915903f1dd1f4bb7cdf82cc15a6d507f80c789903e710f39a62aef073f3f93a6c681e75d295428aa290d7e98f82e7e9ad6e2b23d9086dfe8c63c5d8550b13fd61a77291473a8bdd43c7c2639f264be69d9d07f0585de4342a399275a64e7d1d4400b8ed4421a2f289f622e40cdd1cfc916a0b9ce747c924ac33e32d24b91ed5d64772d6ad6896412f52724006eabf12aaecfd6e81dad432c7b3800bbf793a1c375e3e7b4fb3b097724b5fc88a8c9bcf3dbc10cbdb252965',
      'user-agent': 'okhttp/4.10.0'
    },
    xingxing: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36'
    }
  }
};

// ==================== URL配置集中管理 ====================
const rule = {
  51: {
    host: 'https://51hub.com'
  },
  百度: {
    host: 'https://mbd.baidu.com',
    detailHost: 'https://sv.baidu.com',
    list: '/feedapi/v1/videoserver/playlets/list?service=bdbox',
    search: '/feedapi/v1/videoserver/playlets/search?service=bdbox',
    detail: '/haokan/ui-video/playlet/rec/detail?log=vhk&tn=1020970b&ctn=1008350n&blur=1',
    play: '/appui/api?cmd=video/relate&log=vhk&tn=1020970b&ctn=1008350n&blur=1'
  },
  星芽: {
    host: 'https://app.whjzjx.cn',
    list: '/cloud/v2/theater/home_page?theater_class_id',
    detail: '/v2/theater_parent/detail',
    search: '/v3/search',
    login: 'https://u.shytkjgs.com/user/v1/account/login'
  },
  西饭: {
    host: 'https://xifan-api-cn.youlishipin.com',
    list: '/xifan/drama/portalPage',
    detail: '/xifan/drama/getDuanjuInfo',
    search: '/xifan/search/getSearchList'
  },
  七猫: {
    host: 'https://api-store.qmplaylet.com',
    list: '/api/v1/playlet/index',
    detail: 'https://api-read.qmplaylet.com/player/api/v1/playlet/info',
    search: '/api/v1/playlet/search'
  },
  牛牛: {
    host: 'https://new.tianjinzhitongdaohe.com',
    list: '/api/v1/app/screen/screenMovie',
    detail: '/api/v1/app/play/movieDetails',
    search: '/api/v1/app/search/searchMovie',
    desc: '/api/v1/app/play/movieDesc',
    visitor: '/api/v1/app/user/visitorInfo',
    login: 'https://csj-sp.csjdeveloper.com/csj_sp/api/v1/user/login?siteid=5627189',
    detail2: 'https://csj-sp.csjdeveloper.com/csj_sp/api/v1/shortplay/detail?siteid=5627189',
    unlock: 'https://csj-sp.csjdeveloper.com/csj_sp/api/v1/pay/ad_unlock?siteid=5627189'
  },
  围观: {
    host: 'https://api.drama.9ddm.com',
    list: '/drama/home/shortVideoTags?version_code=1500&os_type=1',
    detail: '/drama/home/shortVideoDetail?version_code=1000&os_type=1',
    search: '/drama/home/search?version_code=1500&os_type=1'
  },
  河马: {
    host: 'https://freevideo.zqqds.cn',
    list: '/free-video-portal/portal/1121',
    detail: '/free-video-portal/portal/1131',
    episode: '/free-video-portal/portal/1132',
    play: '/free-video-portal/portal/1133',
    search: '/free-video-portal/portal/1803'
  },
  好看: {
    host: 'https://sv.baidu.com',
    list: '/haokan/ui-feed/playletTagsFeed?osbranch=a0',
    home: '/haokan/ui-feed/playletShelfFeed?osbranch=a0',
    detail_list: '/appui/api?osbranch=a0',
    detail: '/haokan/ui-video/playlet/rec/detail?osbranch=a0',
    play: '/appui/api?osbranch=a0',
    search: '/haokan/ui-interact/playlet/search/sugs?osbranch=a0'
  },
  星星: {
    host: 'http://read.api.duodutek.com',
    list: '/novel-api/app/pageModel/getResourceById',
    detail: '/novel-api/basedata/book/getChapterList'
  }
};

const platformList = [
  { name: '51短剧', id: '51' },
  { name: '河马短剧', id: '河马' },
  { name: '星芽短剧', id: '星芽' }, 
  { name: '七猫短剧', id: '七猫' },
  { name: '牛牛短剧', id: '牛牛' },
  { name: '百度短剧', id: '百度' },
  { name: '围观短剧', id: '围观' },
  { name: '西饭短剧', id: '西饭' },
  { name: '好看短剧', id: '好看' },
  { name: '星星短剧', id: '星星' }
];

const ruleFilterDef = {
  51: { area: '0-0-0-0-0-0' },
  百度: { area: '新剧' },
  星芽: { area: '1' },
  西饭: { area: '' },
  七猫: { area: '0' },
  牛牛: { area: '现言' },
  围观: { area: '' },
  河马: { area: '308' },
  好看: { area: '1' },
  星星: { area: '1287' }
};

const filterOptions = {
  "51": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "全部短剧", "v": "0-0-0-0-0-0"},
      {"n": "男频", "v": "0-0-0-1-0-0"},
      {"n": "女频", "v": "0-0-0-2-0-0"}
    ]
  }],
  "星芽": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "剧场", "v": "1"},
      {"n": "热播剧", "v": "2"},
      {"n": "会员专享", "v": "8"},
      {"n": "星选好剧", "v": "7"},
      {"n": "新剧", "v": "3"},
      {"n": "阳光剧场", "v": "5"}
    ]
  }],
  "西饭": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "全部", "v": ""},
      {"n": "都市", "v": "68@都市"},
      {"n": "青春", "v": "68@青春"},
      {"n": "现代言情", "v": "81@现代言情"},
      {"n": "豪门", "v": "81@豪门"},
      {"n": "大女主", "v": "80@大女主"},
      {"n": "逆袭", "v": "79@逆袭"},
      {"n": "打脸虐渣", "v": "79@打脸虐渣"},
      {"n": "穿越", "v": "81@穿越"}
    ]
  }],
  "七猫": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "全部", "v": ""}, {"n": "推荐", "v": "0"}, {"n": "新剧", "v": "-1"}, {"n": "都市情感", "v": "1273"}, {"n": "古装", "v": "1272"}, {"n": "都市", "v": "571"}, {"n": "玄幻仙侠", "v": "1286"}, {"n": "奇幻", "v": "570"}, {"n": "乡村", "v": "590"}, {"n": "民国", "v": "573"}, {"n": "年代", "v": "572"}, {"n": "青春校园", "v": "1288"}, {"n": "武侠", "v": "371"}, {"n": "科幻", "v": "594"}, {"n": "末世", "v": "556"}, {"n": "二次元", "v": "1289"}, {"n": "逆袭", "v": "400"}, {"n": "穿越", "v": "373"}, {"n": "复仇", "v": "795"}, {"n": "系统", "v": "787"}, {"n": "权谋", "v": "790"}, {"n": "重生", "v": "784"}, {"n": "女性成长", "v": "1294"}, {"n": "打脸虐渣", "v": "716"}, {"n": "闪婚", "v": "480"}, {"n": "强者回归", "v": "402"}, {"n": "追妻火葬场", "v": "715"}, {"n": "家庭", "v": "670"}, {"n": "马甲", "v": "558"}, {"n": "职场", "v": "724"}, {"n": "宫斗", "v": "343"}, {"n": "高手下山", "v": "1299"}, {"n": "娱乐明星", "v": "1295"}, {"n": "异能", "v": "727"}, {"n": "宅斗", "v": "342"}, {"n": "替身", "v": "712"}, {"n": "穿书", "v": "338"}, {"n": "商战", "v": "723"}, {"n": "种田经商", "v": "1291"}, {"n": "伦理", "v": "1293"}, {"n": "社会话题", "v": "1290"}, {"n": "致富", "v": "492"}, {"n": "偷听心声", "v": "1258"}, {"n": "脑洞", "v": "526"}, {"n": "豪门总裁", "v": "624"}, {"n": "萌宝", "v": "356"}, {"n": "战神", "v": "527"}, {"n": "真假千金", "v": "812"}, {"n": "赘婿", "v": "36"}, {"n": "神医", "v": "1269"}, {"n": "神豪", "v": "37"}, {"n": "小人物", "v": "1296"}, {"n": "团宠", "v": "545"}, {"n": "欢喜冤家", "v": "464"}, {"n": "女帝", "v": "617"}, {"n": "银发", "v": "1297"}, {"n": "兵王", "v": "28"}, {"n": "虐恋", "v": "16"}, {"n": "甜宠", "v": "21"}, {"n": "悬疑", "v": "27"}, {"n": "搞笑", "v": "793"}, {"n": "灵异", "v": "1287"}
    ]
  }],
  "牛牛": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "全部", "v": ""}, {"n": "现言", "v": "现言"}, {"n": "古言", "v": "古言"}, {"n": "历史", "v": "历史"}, {"n": "都市", "v": "都市"}, {"n": "活动", "v": "活动"}, {"n": "逆袭", "v": "逆袭"}, {"n": "豪门", "v": "豪门"}, {"n": "现代言情", "v": "现代言情"}, {"n": "战神", "v": "战神"}, {"n": "甜宠", "v": "甜宠"}, {"n": "穿越", "v": "穿越"}, {"n": "古装", "v": "古装"}, {"n": "虐心", "v": "虐心"}, {"n": "神医", "v": "神医"}, {"n": "赘婿", "v": "赘婿"}, {"n": "亲情", "v": "亲情"}, {"n": "复仇", "v": "复仇"}, {"n": "玄幻", "v": "玄幻"}, {"n": "古代言情", "v": "古代言情"}, {"n": "热血", "v": "热血"}, {"n": "动作", "v": "动作"}, {"n": "喜剧", "v": "喜剧"}, {"n": "悬疑", "v": "悬疑"}, {"n": "军事", "v": "军事"}, {"n": "二次元", "v": "二次元"}, {"n": "未来", "v": "未来"}, {"n": "快速穿越", "v": "快速穿越"}, {"n": "烧脑", "v": "烧脑"}, {"n": "治愈", "v": "治愈"}, {"n": "其他剧情", "v": "其他剧情"}
    ]
  }],
  "百度": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "新剧", "v": "新剧"}, {"n": "限时免费", "v": "限时免费"}, {"n": "精选", "v": "精选"}, {"n": "独播", "v": "独播"}, {"n": "全部", "v": "全部题材"}, {"n": "神医", "v": "神医"}, {"n": "连续剧", "v": "连续剧"}, {"n": "都市", "v": "都市"}, {"n": "现代言情", "v": "现代言情"}, {"n": "异能", "v": "异能"}, {"n": "逆袭", "v": "逆袭"}, {"n": "甜宠", "v": "甜宠"}, {"n": "总裁", "v": "总裁"}, {"n": "萌宝", "v": "萌宝"}, {"n": "战神", "v": "战神"}, {"n": "宫斗宅斗", "v": "宫斗宅斗"}, {"n": "神豪", "v": "神豪"}, {"n": "虐恋", "v": "虐恋"}, {"n": "闪婚", "v": "闪婚"}, {"n": "玄幻", "v": "玄幻"}, {"n": "穿越重生", "v": "穿越重生"}, {"n": "年代", "v": "年代"}, {"n": "家庭伦理", "v": "家庭伦理"}, {"n": "古代言情", "v": "古代言情"}, {"n": "武侠武打", "v": "武侠武打"}, {"n": "赘婿", "v": "赘婿"}, {"n": "单元剧", "v": "单元剧"}, {"n": "青春校园", "v": "青春校园"}, {"n": "历史架空", "v": "历史架空"}, {"n": "王妃", "v": "王妃"}, {"n": "鉴宝", "v": "鉴宝"}, {"n": "科幻", "v": "科幻"}, {"n": "军旅战争", "v": "军旅战争"}, {"n": "种田", "v": "种田"}
    ]
  }],
  "围观": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "全部", "v": ""}
    ]
  }],
  "河马": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "推荐", "v": "308"}, {"n": "新剧", "v": "309"}, {"n": "逆袭", "v": "310"}, {"n": "恋爱", "v": "311"}, {"n": "强者回归", "v": "312"}, {"n": "豪门恩怨", "v": "313"}, {"n": "古装", "v": "314"}, {"n": "重生", "v": "315"}, {"n": "萌宝", "v": "316"}, {"n": "复仇", "v": "317"}, {"n": "神医", "v": "318"}, {"n": "高手下山", "v": "319"}, {"n": "超能悬疑", "v": "320"}, {"n": "传承觉醒", "v": "321"}, {"n": "神豪", "v": "322"}, {"n": "民国", "v": "323"}
    ]
  }],
  "好看": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "热播剧", "v": "1"}, {"n": "新剧", "v": "2"}, {"n": "战神", "v": "1001"}, {"n": "神豪", "v": "2001"}, {"n": "神医", "v": "1002"}, {"n": "甜宠", "v": "1007"}, {"n": "赘婿", "v": "1003"}, {"n": "穿越重生", "v": "2004"}, {"n": "异能", "v": "2005"}, {"n": "虐恋", "v": "1006"}, {"n": "宫斗宅斗", "v": "2006"}, {"n": "玄幻", "v": "2009"}
    ]
  }],
  "星星": [{
    "key": "area",
    "name": "分类",
    "value": [
      {"n": "甜宠", "v": "1287"}, {"n": "逆袭", "v": "1288"}, {"n": "热血", "v": "1289"}, {"n": "现代", "v": "1290"}, {"n": "古代", "v": "1291"}
    ]
  }]
};

const hemaTagIds = {
  "308": "", "309": "", "310": "417,473,474,464", "311": "462,466", "312": "476", "313": "585,616", "314": "444,468", "315": "417,439,464,465", "316": "589", "317": "416,439,463,465", "318": "438", "319": "417,474,464", "320": "439,442,443,445,465,470", "321": "417,473,474,464", "322": "472,475,585", "323": "590"
};

// ==================== 初始化 ====================
async function init(cfg) {
  console.log(`【${siteName}】初始化开始`);
  
  // 51短剧 初始化
  if (cfg && cfg.HOST_51) HOST_51 = cfg.HOST_51;
  await fetchOauthId_51();
  
  // 星芽登录
  try {
    const loginData = { device: '24250683a3bdb3f118dff25ba4b1cba1a' };
    const response = await request(rule.星芽.login, {
      method: 'POST',
      headers: { 'User-Agent': 'okhttp/4.10.0', 'platform': '1', 'Content-Type': 'application/json' },
      data: loginData
    });
    const res = JSON.parse(response || '{}');
    const token = res?.data?.token || res?.data?.data?.token || res?.token || res?.result?.token || res?.access_token;
    if (token) {
      xingya_headers = { ...aggConfig.headers.default, authorization: token };
      console.log(`【${siteName}】星芽登录成功`);
    } else {
      xingya_headers = aggConfig.headers.default;
    }
  } catch (e) {
    console.log(`【${siteName}】星芽登录失败: ${e.message}`);
    xingya_headers = aggConfig.headers.default;
  }
  
  // 牛牛登录
  try {
    let tkhtml = await request(rule.牛牛.host + rule.牛牛.visitor, {
      headers: { "deviceid": "aa11fc54-ba9c-3980-add5-447d3fa5b939", "token": "", "User-Agent": "okhttp/4.12.0", "client": "app", "devicetype": "Android" }
    });
    let tkRes = JSON.parse(tkhtml || '{}');
    niuniu_token = tkRes.data?.token || '';
    
    let t = String(Math.floor(new Date().getTime() / 1000));
    let body = `ac=wifi&os=Android&vod_version=1.10.21.6-tob&os_version=9&type=1&clientVersion=v5.2.5&uuid=Y4WNZ3SAWK7MAJMH7CXCDHJ4VMPVFRZQTBSIA4XTYO4AWEUHIK6Q01&resolution=1280*2618&openudid=889edced38f1069b&dt=Pixel%204&sha1=46121F77CE2FCAD3DBC3B9EC8A24908C1A8AD6D9&os_api=28&install_id=1549688030634536&device_brand=google&sdk_version=1.1.3.0&package_name=com.niuniu.ztdh.app&siteid=5627189&dev_log_aid=667431&oaid=&timestamp=${t}`;
    let nonce = "VX1KKGtoBDCi1fB1";
    let Signature = t + nonce + body;
    let signature = hmacSHA256(Signature, 'aceaa47f96b4875d446b2e1d97e03bbb');
    let encbdoy = aesEncryptECB(body, 'dafdb3d2a5c343d6');
    
    let loginpost = await request(rule.牛牛.login, {
      headers: { 'X-Salt': '786774955F', 'X-Nonce': nonce, 'X-Timestamp': t, 'X-Signature': signature, 'Content-Type': 'application/x-www-form-urlencoded' },
      data: encbdoy,
      method: "POST"
    });
    let logindata = aesDecryptECB(loginpost, 'dafdb3d2a5c343d6');
    let accesstoken = JSON.parse(logindata || '{}');
    niuniu_access_token = accesstoken.data?.access_token || '';
    console.log(`【${siteName}】牛牛登录成功`);
    
    niuniu_headers = { ...aggConfig.headers.niuniu, "token": niuniu_token, "deviceid": "aa11fc54-ba9c-3980-add5-447d3fa5b939" };
  } catch (e) {
    console.log(`【${siteName}】牛牛登录失败: ${e.message}`);
    niuniu_headers = aggConfig.headers.niuniu;
  }
  
  // 河马初始化
  try {
    hema_headers = { ...aggConfig.headers.hema };
    console.log(`【${siteName}】河马初始化成功`);
  } catch (e) {
    console.log(`【${siteName}】河马初始化失败: ${e.message}`);
    hema_headers = aggConfig.headers.hema;
  }
  
  return true;
}

// ==================== 首页分类 ====================
function home(filter) {
  const platForms = getPlatList();
  const classes = platForms.map(item => ({
    type_name: item.name, 
    type_id: item.id,
    type_flag: '[CFS][SUBSITE2][FILTERBAR]'
  }));
  const filters = {};
  platForms.forEach(item => {
    if (filterOptions[item.id]) filters[item.id] = filterOptions[item.id];
  });
  return JSON.stringify({ class: classes, filters: filters });
}

// ==================== 首页推荐 ====================
async function homeVod() {
  const platForms = getPlatList();
  const randomPlat = platForms[Math.floor(Math.random() * platForms.length)];
  const randomArea = ruleFilterDef[randomPlat.id]?.area || '';
  let categoryList = [];
  try {
    const categoryResult = await category(randomPlat.id, 1, { area: randomArea }, {});
    categoryList = JSON.parse(categoryResult).list || [];
  } catch (e) { }
  return JSON.stringify({ list: categoryList });
}

// ==================== 分类列表 ====================
async function category(tid, pg, filter, extend) {
  const page = pg || 1;
  extend = extend || {};
  const area = filter?.area || extend?.area || ruleFilterDef[tid]?.area || '';
  const videos = [];
  const platRule = rule[tid];

  switch (tid) {
    case '51': {
      let url = `${HOST_51}/new-theater-category/${area}`;
      if (page > 1) url += `/page/${page}`;
      let res = await request_51(url);
      let list51 = parseHomeVideos_51(res.content || '');
      list51.forEach(v => videos.push(v));
      break;
    }
    case '百度': {
      let sub = ["新剧","限时免费","精选","独播"].includes(area) ? area : "新剧";
      let tcsub = area === "全部" || area === "全部题材" ? "" : area;
      let t = Math.floor(Date.now() / 1000);
      let version = await md5(t + "v2");
      let postData = {
        'data': JSON.stringify({
          "data": {
            "extRequest": { "flow_tabid": "13" }, "from": "feed", "page": "channel_video_landing", "pd": "feed", "refreshIndex": parseInt(page), "cursor": "", "theme": "", "timestamp": t, "version": version,
            "themes": [{ "kind": "综合", "names": [sub] }, { "kind": "题材", "names": [tcsub] }]
          }
        })
      };
      let html = await request(`${platRule.host}${platRule.list}`, { method: 'POST', headers: aggConfig.headers.baidu, data: postData });
      let res = JSON.parse(html || '{}');
      let items = res.data?.items || [];
      items.slice(0, 20).forEach(it => {
        videos.push({ vod_id: `百度@${it.collId}`, vod_name: it.title || '未知短剧', vod_pic: it.img || '', vod_remarks: '百度短剧 | ' + (it.updateStatus || "更新中"), vod_content: it.description || '' });
      });
      break;
    }
    case '星芽': {
      const url = `${platRule.host}${platRule.list}=${area}&type=1&class2_ids=0&page_num=${page}&page_size=24`;
      const response = await request(url, { headers: xingya_headers });
      const res = JSON.parse(response || '{}');
      (res.data?.list || []).forEach(it => {
        videos.push({ vod_id: `星芽@${it.theater.id}`, vod_name: it.theater.title || '', vod_pic: it.theater.cover_url || '', vod_remarks: '星芽短剧 | ' + (it.theater.total ? `${it.theater.total}集` : ''), vod_content: `播放量:${it.theater.play_amount_str || 0}` });
      });
      break;
    }
    case '西饭': {
      const [typeId, typeName] = area.split('@');
      const ts = Math.floor(Date.now() / 1000);
      const url = `${platRule.host}${platRule.list}?reqType=aggregationPage&offset=${(page-1)*30}&categoryId=${typeId}&quickEngineVersion=-1&scene=&categoryNames=${encodeURIComponent(typeName)}&categoryVersion=1&density=1.5&pageID=page_theater&version=2001001&androidVersionCode=28&requestId=${ts}aa498144140ef297&appId=drama&teenMode=false&userBaseMode=false&session=eyJpbmZvIjp7InVpZCI6IiIsInJ0IjoiMTc0MDY1ODI5NCIsInVuIjoiT1BHXzFlZGQ5OTZhNjQ3ZTQ1MjU4Nzc1MTE2YzFkNzViN2QwIiwiZnQiOiIxNzQwNjU4Mjk0In19&feedssession=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1dHlwIjowLCJidWlkIjoxNjMzOTY4MTI2MTQ4NjQxNTM2LCJhdWQiOiJkcmFtYSIsInZlciI6MiwicmF0IjoxNzQwNjU4Mjk0LCJ1bm0iOiJPUEdfMWVkZDk5NmE2NDdlNDUyNTg3NzUxMTZjMWQ3NWI3ZDAiLCJpZCI6IjNiMzViZmYzYWE0OTgxNDQxNDBlZjI5N2JkMDY5NGNhIiwiZXhwIjoxNzQxMjYzMDk0LCJkYyI6Imd6cXkifQ.JS3QY6ER0P2cQSxAE_OGKSMIWNAMsYUZ3mJTnEpf-Rc`;
      const response = await request(url, { headers: aggConfig.headers.default });
      const res = JSON.parse(response || '{}');
      (res.result?.elements || []).forEach(soup => {
        (soup.contents || []).forEach(vod => {
          const dj = vod.duanjuVo || {};
          videos.push({ vod_id: `西饭@${dj.duanjuId}#${dj.source}`, vod_name: dj.title || '', vod_pic: dj.coverImageUrl || '', vod_remarks: '西饭短剧 | ' + (dj.total ? `${dj.total}集` : ''), vod_content: dj.desc || '' });
        });
      });
      break;
    }
    case '七猫': {
      let signStr = `operation=1playlet_privacy=1tag_id=${area}${aggConfig.keys}`;
      const sign = await md5(signStr);
      const url = `${platRule.host}${platRule.list}?tag_id=${area}&playlet_privacy=1&operation=1&sign=${sign}`;
      const headers = await getQiMaoHeaders();
      const response = await request(url, { method: 'GET', headers });
      const res = JSON.parse(response || '{}');
      (res.data?.list || []).forEach(item => {
        videos.push({ vod_id: `七猫@${encodeURIComponent(item.playlet_id)}`, vod_name: item.title || '', vod_pic: item.image_link || '', vod_remarks: '七猫短剧 | ' + (item.total_episode_num ? `${item.total_episode_num}集` : ''), vod_content: item.tags || '' });
      });
      break;
    }
    case '牛牛': {
      let condition = { typeId: 'S1' };
      if (area && area !== '全部') condition.classify = area;
      const postData = { condition: condition, pageNum: page, pageSize: 24 };
      const response = await request(`${platRule.host}${platRule.list}`, { method: 'POST', headers: niuniu_headers, data: postData });
      const res = JSON.parse(response || '{}');
      (res.data?.records || []).forEach(item => {
        videos.push({ vod_id: `牛牛@${item.id}`, vod_name: item.name || '', vod_pic: item.cover || '', vod_remarks: '牛牛短剧 | ' + (item.totalEpisode ? `${item.totalEpisode}集` : ''), vod_content: item.description || '' });
      });
      break;
    }
    case '围观': {
      const postData = { audience: "全部受众", page: page, pageSize: 30, searchWord: "", subject: "全部主题" };
      const response = await request(`${platRule.host}${platRule.search}`, { method: 'POST', headers: aggConfig.headers.default, data: postData });
      const res = JSON.parse(response || '{}');
      if (res.code === 200 && res.data) {
        (res.data || []).forEach(it => {
          videos.push({ vod_id: `围观@${it.oneId}`, vod_name: it.title || '未知短剧', vod_pic: it.vertPoster || it.horizonPoster || '', vod_remarks: '围观短剧 | ' + `集数:${it.episodeCount || 0}`, vod_content: it.description || '' });
        });
      }
      break;
    }
    case '河马': {
      try {
        const sub = area || '308';
        const tagIds = hemaTagIds[sub] || '';
        const bodys = JSON.stringify({ "recSwitch": true, "channelId": sub, "tagIds": tagIds, "cnxhFlag": page - 1, "playListFlag": true, "watchRecords": ["41000103722_572752006"] });
        const body = hemaEncrypt(bodys);
        const response = await request(`${platRule.host}${platRule.list}`, { method: 'POST', headers: hema_headers, data: body });
        if (response) {
          const res = JSON.parse(response);
          if (res.data) {
            const dehtml = hemaDecrypt(res.data);
            if (dehtml && dehtml !== '{}') {
              const hmdata = JSON.parse(dehtml);
              const hmlist = hmdata.columnData || hmdata.data || hmdata.list || [];
              if (Array.isArray(hmlist)) {
                hmlist.forEach(videoDataArray => {
                  if (videoDataArray && videoDataArray.videoData) {
                    (videoDataArray.videoData || []).forEach(video => {
                      if (video && video.bookId) {
                        videos.push({
                          vod_id: `河马@${video.bookId}`, vod_name: video.bookName || '', vod_pic: video.coverWap || video.coverCutWap || '', vod_remarks: `河马短剧 | 更新${video.updateNum || 0}集`, vod_content: video.introduction || '', vod_actor: video.author || '',
                          extra: { bookId: video.bookId, chapterId: video.chapterId, chapterMin: video.updateNum, chapterMax: video.chapterIndex }
                        });
                      }
                    });
                  }
                });
              }
            }
          }
        }
      } catch (e) { console.log(`【${siteName}】河马分类失败: ${e.message}`); }
      break;
    }
    case '好看': {
      const url = `${platRule.host}${platRule.list}`;
      const data = `tag_id=${area}&rn=20&pn=${page}`;
      const response = await request(url, { method: 'POST', headers: aggConfig.headers.haokan, data: data });
      try {
        const res = JSON.parse(response || '{}');
        (res.data?.list || []).forEach(item => {
          videos.push({ vod_id: `好看@${item.playlet_id}`, vod_name: item.playlet_title || '', vod_pic: item.playlet_poster || '', vod_remarks: `好看短剧 | ${item.episodes_num_text || ''}`, vod_content: item.tags ? item.tags.join('·') : '' });
        });
      } catch(e) {}
      break;
    }
    case '星星': {
      const url = `${platRule.host}${platRule.list}`;
      const params = { productId: "2a8c14d1-72e7-498b-af23-381028eb47c0", vestId: "2be070e0-c824-4d0e-a67a-8f688890cadb", channel: "oppo19", osType: "android", version: "20", token: "202509271001001446030204698626", resourceId: area, pageNum: String(page), pageSize: "20" };
      const response = await request(`${url}?${buildUrlQuery(params)}`, { headers: aggConfig.headers.xingxing });
      try {
        const res = JSON.parse(response || '{}');
        (res.data?.datalist || []).forEach(vod => {
          videos.push({ vod_id: `星星@${vod.id}@${encodeURIComponent(vod.introduction || '')}`, vod_name: vod.name || '', vod_pic: vod.icon || '', vod_remarks: `星星短剧 | ${vod.heat || 0}万播放`, vod_content: vod.introduction || '' });
        });
      } catch(e) {}
      break;
    }
  }
  
  return JSON.stringify({
    list: videos, page: page, pagecount: page + 1, limit: videos.length, total: videos.length * (page + 1)
  });
}

// ==================== 详情 ====================
async function detail(id) {
  const parts = id.split('@');
  const platform = parts[0];
  const did = parts.slice(1).join('@');
  const platRule = rule[platform];
  let vod = {};
  
  switch (platform) {
    case '51': {
      let res = await request_51(HOST_51 + '/video/videolist', {
        method: 'POST',
        data: { id: parseInt(did), page: 0, oauth_id: OAUTH_ID_51, token: TOKEN_51 }
      });
      if (!res.content) break;
      let resJson = JSON.parse(res.content);
      if (!resJson.data) break;
      let decrypted = aesDecrypt_51(resJson.data, 'video');
      if (!decrypted) break;
      let videoInfo = decrypted.data?.list?.[0] || decrypted.list?.[0];
      if (!videoInfo) break;
      let playUrls = (videoInfo.episodeAll || []).map(ep => {
        let title = ep.episode_title || ('第' + ep.sort + '集');
        return title + '$' + ep.video_url;
      }).filter(Boolean);
      if (playUrls.length === 0) break;
      
      vod = {
        vod_id: id,
        vod_name: videoInfo.drama_name || videoInfo.video_title || '短剧',
        vod_pic: (videoInfo.cover_img || videoInfo.first_img || '').replace(/^/, u => getProxyUrl_51(u)),
        vod_content: videoInfo.description || '',
        vod_actor: (videoInfo.actorList || []).map(a => a.name).join(' '),
        vod_play_from: '51短剧',
        vod_play_url: playUrls.join('#')
      };
      break;
    }
    case '百度': {
      const postData = { playlet_id: did, vid: "undefined" };
      let html = await request(`${platRule.detailHost}${platRule.detail}`, { method: 'POST', headers: { "Content-Type": "application/x-www-form-urlencoded" }, data: postData });
      let res = JSON.parse(html || '{}');
      let dthtml = res.data || {};
      let vids = dthtml.vid_list || [];
      let playArr = vids.map((vid, index) => `第${index+1}集$${vid}`);
      vod = {
        vod_id: id, vod_name: dthtml.playlet_title || '未知短剧', vod_pic: dthtml.playlet_poster || '', vod_content: `热度值:${dthtml.hot_value||0}\n题材:${dthtml.tag_text||''}\n集数:${dthtml.episodes_num||0}\n简介:${dthtml.description||''}`, vod_remarks: `共${vids.length||0}集`, vod_director: dthtml.tag_text || '', vod_year: dthtml.create_time || '', vod_play_from: "百度短剧", vod_play_url: playArr.join('#')
      };
      break;
    }
    case '星芽': {
      const detailUrl = `${platRule.host}${platRule.detail}?theater_parent_id=${did}`;
      const response = await request(detailUrl, { headers: xingya_headers });
      const res = JSON.parse(response || '{}');
      if (res.code === 'ok' && res.data) {
        const data = res.data;
        const playUrls = [];
        if (data.theaters && Array.isArray(data.theaters)) {
          data.theaters.forEach((item) => {
            if (item.son_video_url) playUrls.push(`第${item.num}集$${item.son_video_url}`);
          });
        }
        vod = {
          vod_id: id, vod_name: data.title || '未知剧名', vod_type: data.class_two?.map(c => c.class_name).join(',') || '', vod_pic: data.cover_url || '', vod_area: `收藏${data.collect_number || 0}`, vod_actor: `点赞${data.like_num || 0}`, vod_director: `评分${data.score || 0}`, vod_remarks: data.is_over === 2 ? '连载中' : '已完结', vod_content: data.introduction || data.desc || '', vod_play_from: '星芽短剧', vod_play_url: playUrls.length > 0 ? playUrls.join('#') : '暂无播放地址$0'
        };
      }
      break;
    }
    case '西饭': {
      const [duanjuId, source] = did.split('#');
      const url = `${platRule.host}${platRule.detail}?duanjuId=${duanjuId}&source=${source}`;
      const response = await request(url, { headers: aggConfig.headers.default });
      const res = JSON.parse(response || '{}');
      const data = res.result || {};
      const playUrls = (data.episodeList || []).map(ep => `${ep.index}$${ep.playUrl}`).join('#');
      vod = {
        vod_id: id, vod_name: data.title || '', vod_pic: data.coverImageUrl || '', vod_content: data.desc || '未知', vod_remarks: data.updateStatus === 'over' ? `${data.total || 0}集 已完结` : `更新${data.total || 0}集`, vod_play_from: '西饭短剧', vod_play_url: playUrls
      };
      break;
    }
    case '七猫': {
      const didDecoded = decodeURIComponent(did);
      const sign = await md5(`playlet_id=${didDecoded}${aggConfig.keys}`);
      const url = `${platRule.detail}?playlet_id=${didDecoded}&sign=${sign}`;
      const headers = await getQiMaoHeaders();
      const response = await request(url, { method: 'GET', headers });
      const res = JSON.parse(response || '{}');
      const data = res.data || {};
      vod = {
        vod_id: id, vod_name: data.title || '未知标题', vod_pic: data.image_link || '未知图片', vod_actor: '', vod_remarks: `${data.tags || ''} ${data.total_episode_num || 0}集`, vod_content: data.intro || '未知剧情', vod_play_from: '七猫短剧', vod_play_url: (data.play_list || []).map(it => `${it.sort}$${it.video_url}`).join('#')
      };
      break;
    }
    case '牛牛': {
      const descData = await request(`${platRule.host}${platRule.desc}`, { method: 'POST', headers: niuniu_headers, data: { id: did, typeId: 'S1' } });
      const descRes = JSON.parse(descData || '{}');
      const descInfo = descRes.data || {};
      const listData = await request(`${platRule.host}${platRule.detail}`, { method: 'POST', headers: niuniu_headers, data: { id: did, source: 0, typeId: 'S1', userId: '546932' } });
      const listRes = JSON.parse(listData || '{}');
      const listInfo = listRes.data || {};
      let playUrls = '';
      if (listInfo.url && listInfo.episodeList && listInfo.episodeList.length > 0) {
        playUrls = (listInfo.episodeList || []).map(ep => `${ep.episode}$${did}+${ep.id}`).join('#');
      } else if (listInfo.thirdPlayId) {
        let thirdPlayId = listInfo.thirdPlayId;
        let data1 = "not_include=0&lock_free=1&type=1&clientVersion=v5.2.5&uuid=6IDYUSASPQY5BBVACWQW3LLTPV4V7DE26UOCX5TZTVUGX4VUJNXQ01&resolution=1080*2320&openudid=82f4175d577a2939&dt=22021211RC&os_api=31&install_id=1496879012031075&sdk_version=1.1.3.0&siteid=5627189&dev_log_aid=667431&oaid=abec0dfff623201b&timestamp=1752498494&direction=0&ac=mobile&os=Android&vod_version=1.10.21.6-tob&os_version=12&count=1&index=1&shortplay_id="+thirdPlayId+"&sha1=46121F77CE2FCAD3DBC3B9EC8A24908C1A8AD6D9&device_brand=Redmi&package_name=com.niuniu.ztdh.app";
        try {
          let html1 = await niuniuPost(rule.牛牛.detail2, data1, "1");
          if (html1 && html1.data && html1.data.episode_right_list) {
            playUrls = html1.data.episode_right_list.map(it => {
              let lockType = it.lock_type || 'free';
              return `第${it.index}集$${it.index}+${lockType}+${thirdPlayId}`;
            }).join('#');
          }
        } catch (e) { console.log("获取加密剧集失败:", e.message); }
      }
      vod = {
        vod_id: id, vod_name: descInfo.name || listInfo.name || '未知名称', vod_pic: descInfo.cover || listInfo.cover || '', vod_content: `类型：${descInfo.classify || ''}\n评分：${descInfo.score || ''}\n简介：${descInfo.introduce || ''}`, vod_remarks: `共${descInfo.totalEpisode || listInfo.totalEpisode || 0}集`, vod_play_from: '牛牛短剧', vod_play_url: playUrls || '暂无播放地址$0'
      };
      break;
    }
    case '围观': {
      const response = await request(`${platRule.host}${platRule.detail}&oneId=${did}&page=1&pageSize=1000`, { headers: aggConfig.headers.default });
      const res = JSON.parse(response || '{}');
      if (res.code === 200 && res.data) {
        const data = res.data || [];
        const firstEpisode = data[0] || {};
        vod = {
          vod_id: id, vod_name: firstEpisode.title || '', vod_pic: firstEpisode.vertPoster || firstEpisode.horizonPoster || '', vod_remarks: `共${data.length || 0}集`, vod_content: `播放量:${firstEpisode.viewCount || 0} 收藏:${firstEpisode.collectionCount || 0} 评论:${firstEpisode.commentCount || 0}`, vod_play_from: '围观短剧',
          vod_play_url: data.map(ep => {
            let playSetting = ep.playSetting || ep.videoClarityList || [];
            try { if (typeof playSetting === 'string') playSetting = JSON.parse(playSetting); } catch (e) {}
            if (!Array.isArray(playSetting)) playSetting = [];
            const url = playSetting.find(item => item.name === '1080P')?.url || playSetting.find(item => item.name === '720P')?.url || playSetting.find(item => item.name === '480P')?.url || '';
            return `第${ep.playOrder || 1}集$${url}`;
          }).filter(ep => ep.split('$')[1]).join('#')
        };
      }
      break;
    }
    case '河马': {
      try {
        const detailBody = hemaEncrypt(JSON.stringify({ "bookId": did }));
        const detailResponse = await request(`${platRule.host}${platRule.detail}`, { method: 'POST', headers: hema_headers, data: detailBody });
        if (detailResponse) {
          const detailRes = JSON.parse(detailResponse);
          if (detailRes.data) {
            const postdata = hemaDecrypt(detailRes.data);
            if (postdata && postdata !== '{}') {
              const videoInfo = JSON.parse(postdata).videoInfo || {};
              const episodeBody = hemaEncrypt(JSON.stringify({ "bookId": did, "chapterMin": videoInfo.updateNum || 0, "chapterMax": videoInfo.chapterIndex || 0 }));
              const episodeResponse = await request(`${platRule.host}${platRule.episode}`, { method: 'POST', headers: hema_headers, data: episodeBody });
              if (episodeResponse) {
                const episodeRes = JSON.parse(episodeResponse);
                if (episodeRes.data) {
                  const playdata = hemaDecrypt(episodeRes.data);
                  if (playdata && playdata !== '{}') {
                    const chapterList = JSON.parse(playdata).chapterList || [];
                    const playUrls = chapterList.map(item => `${item.chapterName || '第' + item.chapterSort + '集'}$${item.chapterId}++${item.chapterIndex}++${did}`).join('#');
                    vod = {
                      vod_id: id, vod_name: videoInfo.bookName || '未知剧名', vod_type: Array.isArray(videoInfo.bookTags) ? videoInfo.bookTags.join(',') : (videoInfo.bookTags || ''), vod_pic: videoInfo.coverWap || '', vod_remarks: videoInfo.finishStatusCn || `更新至${videoInfo.updateNum || 0}集`, vod_content: videoInfo.introduction || '暂无简介', vod_actor: Array.isArray(videoInfo.protagonist) ? videoInfo.protagonist.join(',') : (videoInfo.protagonist || ''), vod_director: videoInfo.author || '', vod_year: videoInfo.updateTime || '', vod_play_from: '河马短剧', vod_play_url: playUrls || '暂无播放地址$0'
                    };
                  }
                }
              }
            }
          }
        }
      } catch (e) { console.log(`【${siteName}】河马详情失败: ${e.message}`); }
      break;
    }
    case '好看': {
      const commonlistId = Date.now().toString().substring(0, 13);
      const innerParams = `enable_enter_playlet=0&seek_time=0&hotspot=0&auto_show_hot_point_panel=0&type=playlet&commonlist_id=${commonlistId}&scene=&vid=&enable_atlas=0&mark_pn=&uk=&ctime=0&from=playlet_new&id=${did}&rn=10&pn=1&direction=3`;
      const listResponse = await request(`${platRule.host}${platRule.detail_list}`, { method: 'POST', headers: aggConfig.headers.haokan, data: `video/commonlist=${encodeURIComponent(innerParams)}` });
      try {
        const resObj = JSON.parse(listResponse || '{}');
        const firstVideo = resObj['video/commonlist']?.data?.results?.[0];
        const vid = firstVideo?.vid;
        const detailResponse = await request(`${platRule.host}${platRule.detail}`, { method: 'POST', headers: aggConfig.headers.haokan, data: `vid=${vid}&playlet_id=${did}` });
        const detailDataObj = JSON.parse(detailResponse || '{}').data || {};
        let vidList = detailDataObj.vid_list || [];
        if (vidList.length === 0 && detailDataObj.results) vidList = detailDataObj.results.map(item => item.vid);
        const playList = vidList.map((v, i) => `第${i + 1}集$${did}@${v}`).join('#');
        vod = {
          vod_id: id, vod_name: detailDataObj.playlet_title || '', vod_pic: detailDataObj.playlet_poster || '', vod_remarks: (detailDataObj.hot_value || '') + '播放·' + (detailDataObj.episodes_num || '') + '集', vod_director: firstVideo?.content?.author || '', vod_content: detailDataObj.description || '', vod_play_from: '好看短剧', vod_play_url: playList
        };
      } catch(e) {}
      break;
    }
    case '星星': {
      const partsArr = did.split('@');
      const bookId = partsArr[0];
      const contentDesc = decodeURIComponent(partsArr[1] || '');
      const url = `${platRule.host}${platRule.detail}`;
      const params = { bookId: bookId, productId: "2a8c14d1-72e7-498b-af23-381028eb47c0", vestId: "2be070e0-c824-4d0e-a67a-8f688890cadb", channel: "oppo19", osType: "android", version: "20", token: "202509271001001446030204698626" };
      const response = await request(`${url}?${buildUrlQuery(params)}`, { headers: aggConfig.headers.xingxing });
      try {
        const res = JSON.parse(response || '{}');
        const data = res.data || [];
        const playUrls = data.map((vodItem, index) => {
          const playUrl = vodItem.shortPlayList?.[0]?.chapterShortPlayVoList?.[0]?.shortPlayUrl || '';
          return playUrl ? `第${index + 1}集$${playUrl}` : null;
        }).filter(Boolean).join('#');
        vod = { vod_id: id, vod_name: '星星短剧', vod_content: contentDesc, vod_play_from: '星星短剧', vod_play_url: playUrls || '暂无播放地址$0' };
      } catch(e) {}
      break;
    }
  }
  return JSON.stringify({ list: [vod] });
}

// ==================== 播放 ====================
async function play(flag, id, flags) {
  if (/51/.test(flag)) {
    let playUrl = '';
    if (id && id.includes('$')) {
      let parts = id.split('$');
      if (parts.length >= 2) playUrl = parts[1];
    } else if (id && (id.startsWith('http://') || id.startsWith('https://'))) {
      playUrl = id;
    }
    return JSON.stringify({ parse: playUrl ? 0 : 1, url: playUrl });
  }

  if (/百度/.test(flag)) {
    const postData = { method: "post", vid: id };
    let html = await request(`${rule.百度.detailHost}${rule.百度.play}`, { method: 'POST', headers: aggConfig.headers.baidu, data: postData });
    let res = JSON.parse(html || '{}');
    let json = res["video/relate"]?.data?.cur_video || {};
    if (!json?.clarityUrl) return JSON.stringify({ parse: 0, url: id });
    let urls = json.clarityUrl.filter(item => item.url && item.title).map(item => ({ title: item.title, url: item.url, order: { '蓝光': 1, '超清': 2, '标清': 3 }[item.title] || 999 })).sort((a, b) => a.order - b.order).flatMap(item => [item.title, item.url]);
    return JSON.stringify({ parse: urls.length > 0 ? 0 : 1, url: urls.length > 0 ? urls : id, header: { 'User-Agent': aggConfig.headers.baidu['User-Agent'], 'Referer': 'https://mbd.baidu.com/' } });
  }
  
  if (/星芽/.test(flag) || /星星/.test(flag)) {
    return JSON.stringify({ parse: 0, url: id });
  }
  
  if (/牛牛/.test(flag)) {
    const inputArr = id.split('+');
    if (inputArr.length === 2) {
      var match = inputArr[0].match(/\d+/);
      var ep = match ? match[0] : "";
      var postData = { id: inputArr[1], source: 0, typeId: "S1", userId: "546932", episodeId: ep };
      var response = await request(`${rule.牛牛.host}/api/v1/app/play/movieDetails`, { method: 'POST', headers: niuniu_headers, data: postData });
      var result = JSON.parse(response || '{}');
      return (result.code == 200 && result.data && result.data.url) ? JSON.stringify({ parse: 0, url: result.data.url }) : JSON.stringify({ parse: 0, url: id });
    } else if (inputArr.length === 3) {
      var index = inputArr[0], lock_type = inputArr[1], thirdPlayId = inputArr[2];
      if (lock_type === "free") {
        let frdata = "not_include=0&lock_free=1&type=1&clientVersion=v5.2.5&uuid=6IDYUSASPQY5BBVACWQW3LLTPV4V7DE26UOCX5TZTVUGX4VUJNXQ01&resolution=1080*2320&openudid=82f4175d577a2939&dt=22021211RC&os_api=31&install_id=1496879012031075&sdk_version=1.1.3.0&siteid=5627189&dev_log_aid=667431&oaid=abec0dfff623201b&timestamp=1752498494&direction=0&ac=mobile&os=Android&vod_version=1.10.21.6-tob&os_version=12&count=1&index=1&shortplay_id="+thirdPlayId+"&sha1=46121F77CE2FCAD3DBC3B9EC8A24908C1A8AD6D9&device_brand=Redmi&package_name=com.niuniu.ztdh.app";
        let frhtml = await niuniuPost(rule.牛牛.detail2, frdata, index);
        if (frhtml && frhtml.data && frhtml.data.list && frhtml.data.list[0]) return JSON.stringify({ parse: 0, url: base64Decode(frhtml.data.list[0].video_model.video_list.video_1.main_url) });
      } else {
        let unlockData = "ac=mobile&os=Android&vod_version=1.10.21.6-tob&os_version=12&lock_ad=3&lock_free=3&type=1&clientVersion=v5.2.5&uuid=6IDYUSASPQY5BBVACWQW3LLTPV4V7DE26UOCX5TZTVUGX4VUJNXQ01&resolution=1080*2320&openudid=82f4175d577a2939&shortplay_id=" + thirdPlayId + "&dt=22021211RC&sha1=46121F77CE2FCAD3DBC3B9EC8A24908C1A8AD6D9&lock_index=21&os_api=31&install_id=1496879012031075&device_brand=Redmi&sdk_version=1.1.3.0&package_name=com.niuniu.ztdh.app&siteid=5627189&dev_log_aid=667431&oaid=abec0dfff623201b&timestamp=1752498493";
        await niuniuPost(rule.牛牛.unlock, unlockData, index);
        let udata = "not_include=0&lock_free=1&type=1&clientVersion=v5.2.5&uuid=6IDYUSASPQY5BBVACWQW3LLTPV4V7DE26UOCX5TZTVUGX4VUJNXQ01&resolution=1080*2320&openudid=82f4175d577a2939&dt=22021211RC&os_api=31&install_id=1496879012031075&sdk_version=1.1.3.0&siteid=5627189&dev_log_aid=667431&oaid=abec0dfff623201b&timestamp=1752498494&direction=0&ac=mobile&os=Android&vod_version=1.10.21.6-tob&os_version=12&count=1&index=1&shortplay_id="+thirdPlayId+"&sha1=46121F77CE2FCAD3DBC3B9EC8A24908C1A8AD6D9&device_brand=Redmi&package_name=com.niuniu.ztdh.app";
        let unhtml = await niuniuPost(rule.牛牛.detail2, udata, index);
        if (unhtml && unhtml.data && unhtml.data.list && unhtml.data.list[0]) return JSON.stringify({ parse: 0, url: base64Decode(unhtml.data.list[0].video_model.video_list.video_1.main_url) });
      }
    }
    return JSON.stringify({ parse: 0, url: id });
  }
  
  if (/围观/.test(flag)) {
    try {
      let playSetting = typeof id === 'string' ? JSON.parse(id) : id;
      let urls = [];
      if (playSetting.super) urls.push("超清", playSetting.super);
      if (playSetting.high) urls.push("高清", playSetting.high);
      if (playSetting.normal) urls.push("流畅", playSetting.normal);
      return JSON.stringify({ parse: 0, url: urls.length ? urls : id });
    } catch (e) { return JSON.stringify({ parse: 0, url: id }); }
  }
  
  if (/河马/.test(flag)) {
    try {
      let arr = id.split("++"), chapterId = arr[0], bookId = arr[2];
      let fsbody = JSON.stringify({ "bookId": bookId, "chapterId": chapterId, "unClockType": "pay", "confirmPay": 2, "autoPayFlag": true, "omap": { "channelName": "精选", "logId": "17a6500357709bb2547e1e122b438cfc", "originName": "书城", "recId": "bigdata_rec", "scene": "nsc_727", "sceneId": "dzmf_video_sc_reco", "strategyId": "g6y6b5sq" } });
      let response = await request(rule.河马.host + rule.河马.play, { method: 'POST', headers: hema_headers, data: hemaEncrypt(fsbody) });
      if (response) {
        let res = JSON.parse(response);
        if (res.data) {
          let fsdata = hemaDecrypt(res.data);
          if (fsdata && fsdata !== '{}') {
            let parsed = JSON.parse(fsdata);
            if (parsed.chaptersPayType == '免费' && parsed.chapterInfo?.length > 0) {
              let url = parsed.chapterInfo[0].content?.m3u8720p || parsed.chapterInfo[0].content?.url || '';
              if (url) return JSON.stringify({ parse: 0, url: url });
            }
          }
        }
      }
      return JSON.stringify({ parse: 0, url: "https://api.cenguigui.cn/api/duanju/hema.php?book_id=" + bookId + "&video_id=" + chapterId + "&type=mp4" + '#isVideo=true#' });
    } catch (e) { return JSON.stringify({ parse: 0, url: id }); }
  }
  
  if (/好看/.test(flag)) {
    const parts = id.split('@'), playletId = parts[0], vid = parts[1];
    const innerParams = `method=post&vid=${vid}&immersive_mode=v4_5&tplname=feed_small_video&tag=playlet_talos&tab=detail&external_from=&is_dp_video=0&immersive_square_type=3&video_set_id=${playletId}&play_screen_type=1&play_volume_type=2&play_external_device_type=1`;
    const response = await request(`${rule.好看.host}${rule.好看.play}`, { method: 'POST', headers: aggConfig.headers.haokan, data: `video/relate=${encodeURIComponent(innerParams)}` });
    try {
      const videoData = JSON.parse(response || '{}')['video/relate']?.data?.cur_video || {};
      const urlMap = {};
      if (videoData.clarityUrl) videoData.clarityUrl.forEach(c => { if (c.title && c.url) urlMap[c.title] = c.url; });
      if (videoData.video_list) Object.entries(videoData.video_list).forEach(([k, v]) => { if (!urlMap[k]) urlMap[k] = v; });
      const sortedQualities = Object.keys(urlMap).sort((a, b) => {
        const order = { '4k': 0, '2k': 1, '高清': 2, '蓝光': 3, '超清': 4, '标清': 5 };
        return (order[a] ?? 999) - (order[b] ?? 999);
      });
      const playUrls = [];
      sortedQualities.forEach(q => playUrls.push(q, urlMap[q]));
      return JSON.stringify({ parse: 0, url: playUrls.length > 0 ? playUrls : id });
    } catch(e) {}
  }
  
  return JSON.stringify({ parse: 0, url: id });
}

// ==================== 搜索 ====================
async function cfs(siteId, wd, pg) {
  const page = pg || 1;
  const searchLimit = 20;
  const searchTimeout = 6000;
  let results = [];
  const platRule = rule[siteId];
  
  switch (siteId) {
    case '51': {
      let searchUrl = `${HOST_51}/search/${encodeURIComponent(wd)}`;
      if (page > 1) searchUrl += `/page/${page}`;
      let res = await request_51(searchUrl, { method: 'GET', timeout: searchTimeout });
      if (!res || !res.content) break;
      results = parseSearchVideos_51(res.content);
      break;
    }
    case '百度': {
      let innerData = { query: wd, page: page, attribute: ["title"], fe_page_type: "search", extra: { tab_id: "216", flow_tabid: "13", shortplay_source: "feed", from: "feed", tab_type: "搜索", sub_template: "playlet_search_result" } };
      let html = await request(`${platRule.host}${platRule.search}`, { method: 'POST', headers: aggConfig.headers.baidu, data: { 'data': { "data": innerData } }, timeout: searchTimeout });
      let res = JSON.parse(html || '{}');
      results = (res.data?.itemList || []).map(it => ({ vod_id: `百度@${it.nid?.split("_")[1] || ''}`, vod_name: it.title || '未知短剧', vod_pic: it.img || '', vod_remarks: '百度短剧 | ' + (it.collNum || "搜索短剧"), vod_content: it.description || '' }));
      break;
    }
    case '星芽': {
      const response = await request(`${platRule.host}${platRule.search}`, { method: 'POST', headers: xingya_headers, data: { text: wd }, timeout: searchTimeout });
      const res = JSON.parse(response || '{}');
      results = (res.data?.theater?.search_data || []).map(item => ({ vod_id: `星芽@${item.id}`, vod_name: item.title || '', vod_pic: item.cover_url || '', vod_remarks: '星芽短剧 | ' + (item.total ? `${item.total}集` : ''), vod_content: item.introduction || '' }));
      break;
    }
    case '西饭': {
      const ts = Math.floor(Date.now() / 1000);
      const url = `${platRule.host}${platRule.search}?reqType=search&offset=${(page-1)*searchLimit}&keyword=${encodeURIComponent(wd)}&quickEngineVersion=-1&scene=&categoryVersion=1&density=1.5&pageID=page_theater&version=2001001&androidVersionCode=28&requestId=${ts}aa498144140ef297&appId=drama&teenMode=false&userBaseMode=false&session=eyJpbmZvIjp7InVpZCI6IiIsInJ0IjoiMTc0MDY1ODI5NCIsInVuIjoiT1BHXzFlZGQ5OTZhNjQ3ZTQ1MjU4Nzc1MTE2YzFkNzViN2QwIiwiZnQiOiIxNzQwNjU4Mjk0In19&feedssession=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1dHlwIjowLCJidWlkIjoxNjMzOTY4MTI2MTQ4NjQxNTM2LCJhdWQiOiJkcmFtYSIsInZlciI6MiwicmF0IjoxNzQwNjU4Mjk0LCJ1bm0iOiJPUEdfMWVkZDk5NmE2NDdlNDUyNTg3NzUxMTZjMWQ3NWI3ZDAiLCJpZCI6IjNiMzViZmYzYWE0OTgxNDQxNDBlZjI5N2JkMDY5NGNhIiwiZXhwIjoxNzQxMjYzMDk0LCJkYyI6Imd6cXkifQ.JS3QY6ER0P2cQSxAE_OGKSMIWNAMsYUZ3mJTnEpf-Rc`;
      const response = await request(url, { headers: aggConfig.headers.default, timeout: searchTimeout });
      const res = JSON.parse(response || '{}');
      results = (res.result?.elements || []).map(vod => {
        const dj = vod.duanjuVo || {};
        return { vod_id: `西饭@${dj.duanjuId || ''}#${dj.source || ''}`, vod_name: dj.title || '未知标题', vod_pic: dj.coverImageUrl || '', vod_remarks: '西饭短剧 | ' + (dj.total ? `${dj.total}集` : ''), vod_content: '' };
      });
      break;
    }
    case '七猫': {
      let signStr = `operation=2playlet_privacy=1search_word=${wd}${aggConfig.keys}`;
      const sign = await md5(signStr);
      const url = `${platRule.host}${platRule.search}?search_word=${encodeURIComponent(wd)}&playlet_privacy=1&operation=2&sign=${sign}`;
      const response = await request(url, { method: 'GET', headers: await getQiMaoHeaders(), timeout: searchTimeout });
      results = (JSON.parse(response || '{}').data?.list || []).map(item => ({ vod_id: `七猫@${encodeURIComponent(item.playlet_id)}`, vod_name: item.title || '未知标题', vod_pic: item.image_link || '', vod_remarks: '七猫短剧 | ' + (item.tags || '') + ' ' + (item.total_episode_num ? `${item.total_episode_num}集` : ''), vod_content: '' }));
      break;
    }
    case '牛牛': {
      const response = await request(`${platRule.host}${platRule.search}`, { method: 'POST', headers: niuniu_headers, data: { condition: { typeId: "S1", value: wd }, pageNum: page, pageSize: searchLimit }, timeout: searchTimeout });
      results = (JSON.parse(response || '{}').data?.records || []).map(item => ({ vod_id: `牛牛@${item.id}`, vod_name: item.name || '', vod_pic: item.cover || '', vod_remarks: '牛牛短剧 | ' + (item.totalEpisode ? `${item.totalEpisode}集` : ''), vod_content: '' }));
      break;
    }
    case '围观': {
      const response = await request(`${platRule.host}${platRule.search}`, { method: 'POST', data: { audience: "", page: page, pageSize: searchLimit, searchWord: wd, subject: "" }, timeout: searchTimeout });
      const res = JSON.parse(response || '{}');
      if (res.code === 200 && res.data) {
        results = (res.data || []).map(it => ({ vod_id: `围观@${it.oneId || ''}`, vod_name: it.title || '未知标题', vod_pic: it.vertPoster || it.horizonPoster || '', vod_remarks: '围观短剧 | ' + `集数:${it.episodeCount || 0}`, vod_content: it.description || '' }));
      }
      break;
    }
    case '河马': {
      try {
        const response = await request(`${platRule.host}${platRule.search}`, { method: 'POST', headers: hema_headers, data: hemaEncrypt(JSON.stringify({ "keyword": wd, "page": page, "size": searchLimit })), timeout: searchTimeout });
        if (response && JSON.parse(response).data) {
          const xmlist = JSON.parse(hemaDecrypt(JSON.parse(response).data)).searchVos || [];
          results = xmlist.map(video => ({ vod_id: `河马@${video.bookId}`, vod_name: video.bookName || '', vod_pic: (video.coverWap || '') + '@Referer=', vod_remarks: `河马短剧 | 共${video.updateNum || 0}集`, vod_content: video.introduction || '', extra: { bookId: video.bookId, chapterId: video.chapterId, chapterMin: video.updateNum, chapterMax: video.chapterIndex } }));
        }
      } catch (e) { console.log(`【${siteName}】河马搜索失败: ${e.message}`); }
      break;
    }
    case '好看': {
      const response = await request(`${platRule.host}${platRule.search}`, { method: 'POST', headers: aggConfig.headers.haokan, data: `search_word=${encodeURIComponent(wd)}`, timeout: searchTimeout });
      try {
        (JSON.parse(response || '{}').data || []).forEach(item => {
          results.push({ vod_id: `好看@${item.id}`, vod_name: item.title || '', vod_pic: item.cover_url || '', vod_remarks: '好看 | ' + (item.tag ? item.tag.replace(/\//g, '·') : '') });
        });
      } catch(e) {}
      break;
    }
    case '星星': {
      const response = await request(`${platRule.host}${platRule.search}`, { method: 'POST', headers: aggConfig.headers.xingxing, data: { keyword: wd, page: page, pageSize: 20 }, timeout: searchTimeout });
      try {
        (JSON.parse(response || '{}').data || []).forEach(vod => {
          results.push({ vod_id: `星星@${vod.id}@${encodeURIComponent(vod.introduction || '')}`, vod_name: vod.name || '', vod_pic: vod.icon || '', vod_remarks: `星星短剧 | ${vod.heat || 0}万播放`, vod_content: vod.introduction || '' });
        });
      } catch(e) {}
      break;
    }
  }
  return JSON.stringify({ list: results, page: page, pagecount: page + 1, limit: results.length, total: results.length * (page + 1) });
}

async function search(wd, quick, pg) {
  const videos = [];
  const page = pg || 1;
  const platForms = getPlatList();
  const searchPromises = platForms.map(async (platform) => {
    const result = await cfs(platform.id, wd, page);
    return JSON.parse(result || '{}').list || [];
  });
  const searchResults = await Promise.all(searchPromises);
  searchResults.forEach(list => videos.push(...list));
  const filteredResults = videos.filter(item => (item.vod_name || '').toLowerCase().includes(wd.toLowerCase()));
  return JSON.stringify({ list: filteredResults, page: page, pagecount: page + 1, limit: filteredResults.length, total: filteredResults.length * (page + 1) });
}

async function action(action, value) {
  if (action === 'shuaPlay') return JSON.stringify({ action: { actionId: '__detail__', ids: value, keep: true } });
}

// ==================== 51短剧 辅助解析与加解密 ====================
async function fetchOauthId_51() {
    if (OAUTH_ID_51) return OAUTH_ID_51;
    OAUTH_ID_51 = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        let r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
    return OAUTH_ID_51;
}
function toUrlEncoded_51(obj) {
    let params = [];
    for (let key in obj) {
        if (obj.hasOwnProperty(key)) {
            let value = obj[key];
            if (value !== undefined && value !== null) params.push(encodeURIComponent(key) + '=' + encodeURIComponent(value));
        }
    }
    return params.join('&');
}
async function request_51(url, options = {}) {
    const defaultOptions = { method: 'GET', headers: Object.assign({}, HEADER_51, options.headers || {}) };
    const finalOptions = Object.assign(defaultOptions, options);
    if (finalOptions.method === 'POST' && finalOptions.data) {
        finalOptions.body = typeof finalOptions.data === 'object' ? toUrlEncoded_51(finalOptions.data) : finalOptions.data;
    }
    return await req(url, finalOptions);
}
function aesDecrypt_51(encryptedData, type = 'video') {
    try {
        if (!encryptedData) return null;
        const config = AES_CONFIG_51[type];
        const key = CryptoJS.enc.Utf8.parse(config.key);
        const iv = CryptoJS.enc.Utf8.parse(config.iv);
        let wordArray;
        if (typeof encryptedData === 'string') wordArray = CryptoJS.enc.Base64.parse(encryptedData);
        else if (encryptedData instanceof Uint8Array) wordArray = CryptoJS.lib.WordArray.create(encryptedData);
        else return null;
        const decrypted = CryptoJS.AES.decrypt({ ciphertext: wordArray }, key, { iv: iv, mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7 });
        let decryptedBytes = new Uint8Array(decrypted.sigBytes);
        for (let i = 0; i < decrypted.sigBytes; i++) decryptedBytes[i] = (decrypted.words[i >>> 2] >>> (24 - (i % 4) * 8)) & 0xFF;
        if (type === 'video') return JSON.parse(CryptoJS.enc.Utf8.stringify(CryptoJS.lib.WordArray.create(decryptedBytes)));
        return decryptedBytes;
    } catch(e) { return null; }
}
function parseHomeVideos_51(html) {
    let videos = [];
    if (!html) return videos;
    let regex = /<a[^>]*href="\/(?:video|play)(?:\?id=|\/)(\d+)"[^>]*>[\s\S]*?<img[^>]*src="([^"]+)"[^>]*>[\s\S]*?<h3[^>]*>([\s\S]*?)<\/h3>/gi;
    let match;
    while ((match = regex.exec(html)) !== null) {
        let id = match[1], pic = match[2], name = match[3].replace(/<[^>]+>/g, '').trim();
        if (pic && pic.startsWith('blob:')) {
            let dataSrcMatch = html.substring(match.index, match.index + 500).match(/data-src="([^"]+)"/);
            if (dataSrcMatch) pic = dataSrcMatch[1]; else continue;
        }
        if (name) videos.push({ vod_id: '51@' + id, vod_name: name, vod_pic: getProxyUrl_51(pic), vod_remarks: '51短剧' });
    }
    return videos;
}
function parseSearchVideos_51(html) {
    let videos = [];
    if (!html) return videos;
    let cards = html.match(/<div class="video-card[\s\S]*?<\/div>\s*<\/div>\s*(?=<div class="video-card|$)/gi);
    if (!cards) return videos;
    for (let card of cards) {
        let linkMatch = card.match(/href="\/video\/(\d+)"/);
        if (!linkMatch) continue;
        let vod_name = card.match(/<h3[^>]*>([\s\S]*?)<\/h3>/i) ? card.match(/<h3[^>]*>([\s\S]*?)<\/h3>/i)[1].trim() : '未知标题';
        let pic = card.match(/<img[^>]*src="([^"]+)"/) && !card.match(/<img[^>]*src="([^"]+)"/)[1].startsWith('blob:') ? card.match(/<img[^>]*src="([^"]+)"/)[1] : (card.match(/data-src="([^"]+)"/) ? card.match(/data-src="([^"]+)"/)[1] : '');
        let hotMatch = card.match(/<span class="text-white[^"]*">([\d.]+万?热度)<\/span>/);
        let vod_remarks = hotMatch ? '51短剧 | ' + hotMatch[1] : (card.match(/收藏(\d+)/) ? `51短剧 | 收藏${card.match(/收藏(\d+)/)[1]}` : '51短剧');
        if (vod_name) videos.push({ vod_id: '51@' + linkMatch[1], vod_name, vod_pic: getProxyUrl_51(pic), vod_remarks });
    }
    return videos;
}

// ==================== 河马/通用加密与工具函数 ====================
function hemaEncrypt(plaintext) {
  var ciphertext = CryptoJS.AES.encrypt(plaintext, CryptoJS.enc.Hex.parse("647a6b6a67667978677368796c677a6d"), { iv: CryptoJS.enc.Hex.parse("6170697570646f776e65646372797074"), mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7 }).ciphertext.toString(CryptoJS.enc.Hex);
  return ciphertext.toUpperCase();
}
function hemaDecrypt(word) {
  try {
    return CryptoJS.AES.decrypt(CryptoJS.enc.Base64.stringify(CryptoJS.enc.Hex.parse(word)), CryptoJS.enc.Hex.parse("647a6b6a67667978677368796c677a6d"), { iv: CryptoJS.enc.Hex.parse("6170697570646f776e65646372797074"), mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7 }).toString(CryptoJS.enc.Utf8);
  } catch (e) { return '{}'; }
}
function isSkipPlat(platformItem) { return cate_remove.some(word => new RegExp(word, 'i').test(platformItem.name) || new RegExp(word, 'i').test(platformItem.id)); }
function getPlatList() { return platformList.filter(item => !isSkipPlat(item)); }
function buildUrlQuery(params) { return Object.keys(params).map(k => encodeURIComponent(k) + '=' + encodeURIComponent(params[k])).join('&'); }
async function getAndSign() {
  const sessionId = Math.floor(Date.now()).toString();
  let data = { "static_score": "0.8", "uuid": "00000000-7fc7-08dc-0000-000000000000", "device-id": "20250220125449b9b8cac84c2dd3d035c9052a2572f7dd0122edde3cc42a70", "mac": "", "sourceuid": "aa7de295aad621a6", "refresh-type": "0", "model": "22021211RC", "wlb-imei": "", "client-id": "aa7de295aad621a6", "brand": "Redmi", "oaid": "", "oaid-no-cache": "", "sys-ver": "12", "trusted-id": "", "phone-level": "H", "imei": "", "wlb-uid": "aa7de295aad621a6", "session-id": sessionId };
  const base64Str = base64Encode(unescape(encodeURIComponent(JSON.stringify(data))));
  let qmParams = '';
  for (const c of base64Str) qmParams += aggConfig.charMap[c] || c;
  return { qmParams, sign: await md5(`AUTHORIZATION=app-version=10001application-id=com.duoduo.readchannel=unknownis-white=net-env=5platform=androidqm-params=${qmParams}reg=${aggConfig.keys}`) };
}
async function getQiMaoHeaders() {
  const { qmParams, sign } = await getAndSign();
  return { 'net-env': '5', 'reg': '', 'channel': 'unknown', 'is-white': '', 'platform': 'android', 'application-id': 'com.duoduo.read', 'authorization': '', 'app-version': '10001', 'user-agent': 'webviewversion/0', 'qm-params': qmParams, 'sign': sign, ...aggConfig.headers.default };
}
async function md5(str) { return CryptoJS.MD5(str).toString(CryptoJS.enc.Hex).toLowerCase(); }
function base64Encode(text) { return CryptoJS.enc.Base64.stringify(CryptoJS.enc.Utf8.parse(text)); }
function base64Decode(text) { return CryptoJS.enc.Utf8.stringify(CryptoJS.enc.Base64.parse(text)); }
function aesEncryptECB(text, keyStr) { return CryptoJS.AES.encrypt(text, CryptoJS.enc.Utf8.parse(keyStr), { mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7 }).toString(); }
function aesDecryptECB(ciphertext, keyStr) { return CryptoJS.AES.decrypt(ciphertext, CryptoJS.enc.Utf8.parse(keyStr), { mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7 }).toString(CryptoJS.enc.Utf8); }
function hmacSHA256(message, secretKey) { return CryptoJS.HmacSHA256(message, secretKey).toString(CryptoJS.enc.Hex); }
async function niuniuPost(url1, data1, index) {
  let t10 = String(Math.floor(new Date().getTime() / 1000)), X_Nonce = "X9UknYKtLa3DmtjC";
  let body1 = data1.replace(/&lock_free=\d+/, "&lock_free=1").replace(/&timestamp=\d+/, "&timestamp="+t10).replace(/&count=\d+/, "&count=1").replace(/&index=\d+/, "&index="+index).replace(/&lock_ad=\d+/, "&lock_ad=1").replace(/&lock_index=\d+/, "&lock_index="+index);
  let res = await request(url1, { headers: { 'X-Salt': 'FD8188A8D5', 'X-Nonce': X_Nonce, 'X-Timestamp': t10, 'X-Access-Token': niuniu_access_token, 'X-Signature': hmacSHA256(t10 + X_Nonce + body1, 'aceaa47f96b4875d446b2e1d97e03bbb'), 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'okhttp/4.12.0' }, data: aesEncryptECB(body1, 'ce49b18dd4e0a4d8'), method: "POST" });
  try { return JSON.parse(aesDecryptECB(res, 'ce49b18dd4e0a4d8')); } catch (e) { return {}; }
}
async function request(url, options = {}) {
  try {
    let requestConfig = { method: options.method || 'GET', headers: { ...aggConfig.headers.default, ...options.headers }, timeout: options.timeout || 8000 };
    if (options.data) {
      if (typeof options.data === 'string') requestConfig.body = options.data;
      else if ((requestConfig.headers['Content-Type'] || '').includes('json')) requestConfig.body = JSON.stringify(options.data);
      else {
        const parts = [];
        for (let key in options.data) { parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(typeof options.data[key] === 'object' ? JSON.stringify(options.data[key]) : options.data[key])); }
        requestConfig.body = parts.join('&');
      }
    }
    return (await req(url, requestConfig)).content || '';
  } catch (e) { return ''; }
}

// ==================== 图片代理处理器（处理51加密海报）====================
async function proxy(params) {
    let { type, url } = params;
    if (type === 'img' && url) {
        try {
            let imgUrl = url;
            try { if (url.includes('%')) imgUrl = decodeURIComponent(url); } catch(e) {}
            let response = await req(imgUrl, {
                method: 'GET',
                headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'image/avif,image/webp,image/*,*/*;q=0.8', 'Referer': HOST_51, 'Accept-Language': 'zh-CN,zh;q=0.9' },
                timeout: 30000, buffer: 1
            });
            if (response.code == 200 && response.content) {
                let encryptedBytes;
                if (response.content instanceof ArrayBuffer) encryptedBytes = new Uint8Array(response.content);
                else if (response.content instanceof Uint8Array) encryptedBytes = response.content;
                else if (Array.isArray(response.content)) encryptedBytes = new Uint8Array(response.content);
                else if (typeof response.content === 'string') {
                    encryptedBytes = new Uint8Array(response.content.length);
                    for (let i = 0; i < response.content.length; i++) encryptedBytes[i] = response.content.charCodeAt(i) & 0xFF;
                } else return [500, 'text/plain', 'Unknown content type'];
                
                if (!encryptedBytes || encryptedBytes.length === 0) return [404, 'text/plain', 'Empty image data'];
                if ((encryptedBytes[0] === 0xFF && encryptedBytes[1] === 0xD8) || (encryptedBytes[0] === 0x89 && encryptedBytes[1] === 0x50)) return [200, 'image/jpeg', encryptedBytes];
                
                let decryptedBytes = aesDecrypt_51(encryptedBytes, 'img');
                if (!decryptedBytes || decryptedBytes.length === 0) return [500, 'text/plain', 'Decrypt failed'];
                let finalBytes = decryptedBytes;
                if (decryptedBytes[0] !== 0xFF || decryptedBytes[1] !== 0xD8) {
                    for (let i = 0; i < Math.min(100, decryptedBytes.length - 2); i++) {
                        if (decryptedBytes[i] === 0xFF && decryptedBytes[i+1] === 0xD8) { finalBytes = decryptedBytes.slice(i); break; }
                    }
                }
                return [200, 'image/jpeg', Array.from(finalBytes)];
            }
            return [404, 'text/plain', 'Image not found'];
        } catch (e) { return [500, 'text/plain', `Proxy error: ${e.message}`]; }
    }
    return params.url ? [302, '', '', { 'Location': params.url }] : [404, 'text/plain', 'not found'];
}

// ==================== CatVod 注册 ====================
export function __jsEvalReturn() {
  return {
    init: init,
    home: home,
    homeVod: homeVod,
    category: category,
    detail: detail,
    play: play,
    search: search,
    proxy: proxy
  };
}