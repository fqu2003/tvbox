/*
@header({
  title: '网抑云[听]',
  author: '',
  more: {
    sourceTag: "音乐,MV",
    errorPlayNext: true
  },
  '类型': '音乐',
  logo: 'https://s1.music.126.net/style/favicon.ico?v20180823',
  lang: 'cat'
})
*/

import { _ } from 'assets://js/lib/cat.js';

let host = 'https://music.163.com';
let play_api = 'https://api.cenguigui.cn/api/netease/music_v1.php';
// 搜索代理（稳定，有封面）
let search_proxy = 'http://mc.alger.fun/api/cloudsearch';

let headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.95 Safari/537.36',
    'Referer': 'https://music.163.com/'
};

// 音质优先级从高到低（用于降级尝试）
const qualities = [
    ["超清母带", "jymaster"],
    ["沉浸环绕声", "sky"],
    ["高清环绕声", "jyeffect"],
    ["Hi-Res", "hires"],
    ["无损", "lossless"],
    ["极高", "exhigh"],
    ["标准", "standard"]
];

const init = async () => {};

const generateFilters = () => {
    return {
        "hot_playlist": [{
            "key": "cat",
            "name": "类型",
            "value": [
                {"n": "全部", "v": "全部"}, {"n": "华语", "v": "华语"}, {"n": "流行", "v": "流行"},
                {"n": "摇滚", "v": "摇滚"}, {"n": "民谣", "v": "民谣"}, {"n": "电子", "v": "电子"},
                {"n": "轻音乐", "v": "轻音乐"}, {"n": "ACG", "v": "ACG"}, {"n": "怀旧", "v": "怀旧"},
                {"n": "治愈", "v": "治愈"}
            ]
        }]
    };
};

function safeStr(val, suffix) {
    let s = (val !== undefined && val !== null) ? String(val) : '';
    return s ? (s + (suffix || '')) : '';
}

// 构建多音质播放链接（用于歌单、歌手详情等）
function buildPlayUrls(songs) {
    let playFrom = [];
    let playUrls = [];
    for (let q of qualities) {
        playFrom.push(q[0]);
        let eps = [];
        for (let s of songs) {
            let artists = (s.ar || s.artists || []).map(a => a.name).join('/');
            let title = s.name || s.title || '';
            // 有艺术家才拼接 " - "
            let displayName = artists ? (title + ' - ' + artists) : title;
            eps.push(displayName + '$$' + s.id + '|' + q[1]);
        }
        playUrls.push(eps.join('#'));
    }
    return {
        vod_play_from: playFrom.join('$$$'),
        vod_play_url: playUrls.join('$$$')
    };
}

// ==================== 首页 ====================
const home = async (filter) => {
    const classes = [
        {type_id: "hot_playlist", type_name: "歌单分类"},
        {type_id: "toplist", type_name: "排行榜"},
        {type_id: "top_artists", type_name: "热门歌手"},
        {type_id: "mv", type_name: "推荐MV"}
    ];
    let list = [];
    try {
        let res = await req(host + '/api/personalized?limit=18', {headers});
        let json = JSON.parse(res.content || res);
        let data = json.result || json.data || [];
        list = data.map(it => ({
            vod_name: it.name || '',
            vod_pic: safeStr(it.picUrl || it.coverImgUrl, '?param=300y300'),
            vod_remarks: it.playCount ? '🎧 ' + formatCount(it.playCount) : '',
            vod_id: 'playlist_' + it.id
        }));
    } catch (e) {}
    return JSON.stringify({ class: classes, filters: generateFilters(), list });
};

const homeVod = async () => { return JSON.stringify({ list: [] }); };

// ==================== 分类 ====================
const category = async (tid, pg, filter, extend) => {
    let limit = 20, offset = (pg - 1) * limit;
    let url = '';
    let rawList = [];

    try {
        if (tid === 'toplist') {
            url = host + '/api/toplist';
        } else if (tid === 'hot_playlist') {
            let cat = (extend && extend.cat) || '全部';
            let order = (extend && extend.order) || 'hot';
            url = host + '/api/playlist/list?cat=' + encodeURIComponent(cat) + '&order=' + order + '&limit=' + limit + '&offset=' + offset;
        } else if (tid === 'top_artists') {
            url = host + '/api/artist/list?limit=' + limit + '&offset=' + offset;
        } else if (tid === 'mv') {
            url = host + '/api/mv/all?limit=' + limit + '&offset=' + offset;
        }

        let res = await req(url, {headers});
        let json = JSON.parse(res.content || res);
        rawList = json.list || json.playlists || json.artists || json.data || [];
    } catch (e) {}

    let list = rawList.map(it => {
        let idPrefix = 'playlist_';
        if (tid === 'toplist') idPrefix = 'toplist_';
        else if (tid === 'top_artists') idPrefix = 'artist_';
        else if (tid === 'mv') idPrefix = 'mv_';
        return {
            vod_name: it.name || it.title || '',
            vod_pic: safeStr(it.coverImgUrl || it.picUrl || it.img1v1Url || it.cover, '?param=300y300'),
            vod_remarks: it.playCount ? formatCount(it.playCount) : (it.artistName || ''),
            vod_id: idPrefix + it.id
        };
    });
    return JSON.stringify({ list, page: +pg, limit });
};

// ==================== 详情页（搜索歌曲生成10首播放列表） ====================
const detail = async (ids) => {
    let id = Array.isArray(ids) ? ids[0] : ids;
    let did = id.toString();
    
    // 搜索结果 @ 分隔的 id
    if (did.includes('@')) {
        let parts = did.split('@');
        // 格式：songId@name@artist@artist@artistId@albumId@albumName@year@mvId
        let songId = parts[0];
        let artistId = parts[4] || '';
        let mvId = parts[8] || '0';
        
        // 从 play_api 获取封面和歌词
        let pic = '';
        let lyric = '';
        try {
            let apiUrl = `${play_api}?id=${songId}&type=json&level=jymaster`;
            let apiRes = await req(apiUrl, {headers});
            let apiJson = JSON.parse(apiRes.content || apiRes);
            if (apiJson.code === 200 && apiJson.data) {
                pic = apiJson.data.pic || '';
                lyric = apiJson.data.lyric || '';
                if (apiJson.data.mv_info && apiJson.data.mv_info.mv) {
                    mvId = songId; // 标记有MV可用
                }
            }
        } catch (e) {}
        
        // 构建歌曲列表：当前歌曲 + 歌手热门歌曲 (取9首)
        let allSongs = [{ id: songId, name: parts[1], ar: [{ name: parts[2] }], al: { picUrl: pic } }];
        if (artistId) {
            try {
                let topRes = await req(`${host}/api/artist/top/song?id=${artistId}`, {headers});
                let topJson = JSON.parse(topRes.content || topRes);
                let topSongs = (topJson.songs || []).filter(s => s.id.toString() !== songId).slice(0, 9);
                allSongs = allSongs.concat(topSongs.map(s => ({
                    id: s.id,
                    name: s.name,
                    ar: s.ar || [],
                    al: s.al || {}
                })));
            } catch (e) {}
        }
        
        // 生成播放列表（所有音质）
        let playFrom = qualities.map(q => q[0]);
        let playUrls = [];
        for (let q of qualities) {
            let eps = allSongs.map(s => {
                let artists = (s.ar || []).map(a => a.name).join('/');
                let title = s.name || '';
                let displayName = artists ? (title + ' - ' + artists) : title;
                return `${displayName}$$${s.id}|${q[1]}`;
            });
            playUrls.push(eps.join('#'));
        }
        
        // 如果有MV，追加MV播放源
        if (mvId && mvId !== '0') {
            playFrom.push('MV');
            let mvEps = [parts[1] + '$$' + songId + '|mv'];
            playUrls.push(mvEps.join('#'));
        }
        
        return JSON.stringify({
            list: [{
                vod_id: songId,
                vod_name: parts[1],
                vod_pic: pic,
                vod_actor: parts[2],
                vod_content: lyric ? lyric.replace(/\n/g, '<br>') : '',
                vod_play_from: playFrom.join('$$$'),
                vod_play_url: playUrls.join('$$$')
            }]
        });
    }

    let realId = did.split('_')[1];

    if (did.startsWith('artist_')) {
        let tracks = [];
        let artistName = '';
        try {
            let res = await req(`${host}/api/artist/top/song?id=${realId}`, {headers});
            let json = JSON.parse(res.content || res);
            tracks = (json.songs || []).map(s => ({ id: s.id, name: s.name, ar: s.ar || [], al: s.al || {} }));
            let infoRes = await req(`${host}/api/artist/detail?id=${realId}`, {headers});
            let infoJson = JSON.parse(infoRes.content || infoRes);
            artistName = (infoJson.data && infoJson.data.artist && infoJson.data.artist.name) || '';
        } catch (e) {}
        let playInfo = buildPlayUrls(tracks);
        return JSON.stringify({
            list: [{
                vod_id: did,
                vod_name: artistName || '',
                vod_pic: safeStr('', '?param=500y500'),
                vod_play_from: playInfo.vod_play_from,
                vod_play_url: playInfo.vod_play_url
            }]
        });
    } else if (did.startsWith('mv_')) {
        // 推荐MV的详情：直接构造一个MV播放源
        return JSON.stringify({
            list: [{
                vod_id: did,
                vod_name: 'MV',
                vod_pic: '',
                vod_play_from: 'MV',
                vod_play_url: 'MV播放$$' + realId + '|mvDirect'
            }]
        });
    } else {
        // 歌单 / 排行榜
        let songs = [];
        let playlistInfo = {};
        try {
            let res = await req(`${host}/api/v3/playlist/detail?id=${realId}&n=500`, {headers});
            let json = JSON.parse(res.content || res);
            let playlist = json.playlist || {};
            playlistInfo = {
                name: playlist.name || '',
                coverImgUrl: playlist.coverImgUrl || '',
                description: playlist.description || ''
            };
            let trackIds = (playlist.trackIds || []).map(t => (typeof t === 'object' ? t.id : t));
            for (let i = 0; i < trackIds.length; i += 200) {
                let batch = trackIds.slice(i, i + 200);
                let sRes = await req(`${host}/api/song/detail?ids=[${batch.join(',')}]`, {headers});
                let sJson = JSON.parse(sRes.content || sRes);
                let batchSongs = (sJson.songs || []).map(s => ({
                    id: s.id,
                    name: s.name,
                    ar: s.ar || [],
                    al: s.al || {}
                }));
                songs = songs.concat(batchSongs);
            }
        } catch (e) {}
        let playInfo = buildPlayUrls(songs);
        return JSON.stringify({
            list: [{
                vod_id: did,
                vod_name: playlistInfo.name || '歌单详情',
                vod_pic: safeStr(playlistInfo.coverImgUrl, '?param=500y500'),
                vod_content: playlistInfo.description || '',
                vod_play_from: playInfo.vod_play_from,
                vod_play_url: playInfo.vod_play_url
            }]
        });
    }
};

// ==================== 搜索（有封面、分页） ====================
const search = async (wd, quick, pg) => {
    let offset = ((parseInt(pg) || 1) - 1) * 30;
    try {
        let url = `${search_proxy}?keywords=${encodeURIComponent(wd)}&type=1&limit=30&offset=${offset}`;
        let res = await req(url, { headers });
        let json = JSON.parse(res.content || res);
        let list = (json.result && json.result.songs ? json.result.songs : []).map(s => {
            let artist = (s.ar || []).map(a => a.name).join('/');
            let parts = [
                s.id,
                s.name,
                artist,
                artist,
                (s.ar[0] || {}).id || '',
                (s.al || {}).id || '',
                (s.al || {}).name || '',
                new Date(s.publishTime).getFullYear(),
                s.mv || 0
            ];
            return {
                vod_name: s.name,
                vod_pic: safeStr(s.al && s.al.picUrl, '?param=300y300'),
                vod_remarks: artist + (s.mv ? ' [MV]' : ''),
                vod_id: parts.join('@')
            };
        });
        return JSON.stringify({ list });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
};

// ==================== 播放（核心：音质降级 + MV支持） ====================
const play = async (flag, id, flags) => {
    // 解析 id：可能是 "数字|jymaster" 或 "数字|mv" 或 "mv_数字|mvDirect"
    const match = id.match(/(\d+)(?:\|(\w+))?/);
    if (!match) return JSON.stringify({ parse: 0, url: '' });
    const songId = match[1];
    const action = match[2] || 'jymaster';

    // 处理MV播放
    if (action === 'mv' || action === 'mvDirect') {
        let mvUrl = '';
        if (action === 'mvDirect') {
            // 推荐MV分类，使用官方接口
            try {
                const res = await req(`https://music.163.com/api/mv/detail?id=${songId}&type=mp4`, {
                    headers: {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Referer': 'https://music.163.com/'
                    }
                });
                const json = JSON.parse(res.content || res);
                if (json.data && json.data.brs) {
                    mvUrl = json.data.brs['1080'] || json.data.brs['720'] || json.data.brs['480'] || '';
                } else if (json.data && json.data.mp4) {
                    mvUrl = json.data.mp4;
                }
            } catch (e) {}
        } else {
            // 歌曲MV：优先从 play_api 获取
            try {
                const apiUrl = `${play_api}?id=${songId}&type=json&level=jymaster`;
                const apiRes = await req(apiUrl, {headers});
                const apiJson = JSON.parse(apiRes.content || apiRes);
                if (apiJson.code === 200 && apiJson.data && apiJson.data.mv_info && apiJson.data.mv_info.mv) {
                    mvUrl = apiJson.data.mv_info.mv;
                }
            } catch (e) {}
            // 若失败，尝试官方接口
            if (!mvUrl) {
                try {
                    const res = await req(`https://music.163.com/api/mv/detail?id=${songId}&type=mp4`, {
                        headers: {
                            'User-Agent': 'Mozilla/5.0',
                            'Referer': 'https://music.163.com/'
                        }
                    });
                    const json = JSON.parse(res.content || res);
                    if (json.data && json.data.brs) {
                        mvUrl = json.data.brs['1080'] || json.data.brs['720'] || json.data.brs['480'] || '';
                    }
                } catch (e) {}
            }
        }
        return JSON.stringify({ parse: 0, url: mvUrl || '', header: headers });
    }

    // 音乐播放：根据 action 尝试音质，降级逻辑
    const targetQuality = action; // 如 'jymaster', 'exhigh' 等
    let playUrl = '', lrc = '', pic = '', title = '', artist = '';

    // 找到 targetQuality 在 qualities 列表中的下标，从该下标开始尝试
    let startIndex = qualities.findIndex(q => q[1] === targetQuality);
    if (startIndex === -1) startIndex = 0;

    for (let i = startIndex; i < qualities.length; i++) {
        const level = qualities[i][1];
        try {
            const apiUrl = `${play_api}?id=${songId}&type=json&level=${level}`;
            const res = await req(apiUrl, { headers });
            const json = JSON.parse(res.content || res);
            if (json.code === 200 && json.data) {
                const data = json.data;
                if (data.url && data.url.length > 10) {
                    playUrl = data.url;
                    lrc = data.lyric || '';
                    pic = data.pic || '';
                    title = data.name || '';
                    artist = data.artist || '';
                    break; // 成功则退出循环
                }
            }
        } catch (e) {
            continue;
        }
    }

    // 如果最终都没获取到，尝试最低音质标准
    if (!playUrl) {
        try {
            const apiUrl = `${play_api}?id=${songId}&type=json&level=standard`;
            const res = await req(apiUrl, { headers });
            const json = JSON.parse(res.content || res);
            if (json.code === 200 && json.data && json.data.url) {
                playUrl = json.data.url;
                lrc = json.data.lyric || '';
                pic = json.data.pic || '';
            }
        } catch (e) {}
    }

    return JSON.stringify({
        parse: 0,
        url: playUrl,
        header: headers,
        lrc: lrc,
        pic: pic,
        cover: pic,
        title: title,
        artist: artist,
        album: '',
        duration: '',
        format: ''
    });
};

function formatCount(count) {
    if (count > 100000000) return (count / 100000000).toFixed(1) + '亿';
    if (count > 10000) return (count / 10000).toFixed(1) + '万';
    return count.toString();
}

export function __jsEvalReturn() {
    return { init, home, homeVod, category, detail, search, play };
}
