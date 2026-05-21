/*
@header({
  title: 'QQ音乐',
  searchable: 1,
  quickSearch: 1,
  filterable: 1,
  lang: 'cat'
})
*/

import { _ } from 'assets://js/lib/cat.js';

const playApi = 'https://api.nki.pw/API/music_open_api.php';
const musicuApi = 'https://u.y.qq.com/cgi-bin/musicu.fcg';
const headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 11)',
    'Referer': 'https://y.qq.com/'
};
const apiKey = 'a85ff7d3fc0aabc9b7e6337e9192c463d98da958fbc00757c104489501f43ab5';

// 统一的歌手接口账号参数
const singerUin = 948168827;
const singerGtk = 948168827;

const init = async () => {};

// ========== 动态获取歌单分类（筛选栏） ==========
let playlistCategories = null;
async function getPlaylistCategories() {
    if (playlistCategories) return playlistCategories;
    let data = {
        tags: {
            module: "playlist.PlaylistAllCategoriesServer",
            method: "get_all_categories",
            param: { qq: "" }
        }
    };
    let url = musicuApi + '?loginUin=0&hostUin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=wk_v15.json&needNewCode=0&data=' + encodeURIComponent(JSON.stringify(data));
    try {
        let res = await req(url, { headers });
        let json = JSON.parse(res.content || res);
        if (json && json.code === 0 && json.tags && json.tags.data && json.tags.data.v_group) {
            playlistCategories = json.tags.data.v_group;
        } else {
            playlistCategories = [];
        }
    } catch (e) {
        playlistCategories = [];
    }
    return playlistCategories;
}

function getFirstCategoryId(categories) {
    for (let group of categories) {
        if (group.v_item && group.v_item.length > 0) {
            return String(group.v_item[0].id);
        }
    }
    return '3388';
}

// ========== 动态获取分类歌单 ==========
async function fetchCategoryPlaylist(catId, page) {
    let reqPage = page - 1;
    let size = 36;
    let data = {
        comm: { cv: 1602, ct: 20, uin: "0" },
        playlist: {
            module: "playlist.PlayListCategoryServer",
            method: "get_category_content",
            param: {
                titleid: parseInt(catId),
                caller: "0",
                category_id: parseInt(catId),
                size: size,
                page: reqPage,
                use_page: 1
            }
        }
    };
    let url = musicuApi + '?loginUin=0&hostUin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=wk_v15.json&needNewCode=0&data=' + encodeURIComponent(JSON.stringify(data));
    try {
        let res = await req(url, { headers });
        let json = JSON.parse(res.content || res);
        if (json && json.code === 0 && json.playlist && json.playlist.code === 0) {
            let content = json.playlist.data?.content;
            if (content) {
                let total = content.total_cnt || 0;
                let items = content.v_item || [];
                let list = items.map(item => {
                    let basic = item.basic;
                    return {
                        vod_id: 'playlist_' + basic.tid,
                        vod_name: basic.title,
                        vod_pic: basic.cover?.default_url || basic.cover?.medium_url || '',
                        vod_remarks: (basic.play_cnt ? formatNum(basic.play_cnt) + '次播放 · ' : '') + basic.song_cnt + '首'
                    };
                });
                return { list, total };
            }
        }
    } catch (e) {}
    return { list: [], total: 0 };
}

// ========== 歌手分类 ==========
let singerTagsCache = null;
async function getSingerTags() {
    if (singerTagsCache) return singerTagsCache;
    let result = await fetchSingerList({}, 1);
    if (result.tags) {
        singerTagsCache = result.tags;
    }
    return singerTagsCache;
}

async function fetchSingerList(params, page) {
    let param = {
        genre: parseInt(params.genre) || -100,
        index: parseInt(params.index) || -100,
        area: parseInt(params.area) || -100,
        sex: parseInt(params.sex) || -100,
        cur_page: page,
        sin: 0,
        num: 30
    };

    let fullData = {
        comm: {
            uin: singerUin,
            g_tk: singerGtk,
            cv: 948168827,
            ct: 11,
            format: "json",
            inCharset: "utf-8",
            outCharset: "utf-8",
            notice: 0,
            platform: "yqq.json",
            needNewCode: 1,
            tmeAppID: "qqmusiclight",
            tmeLoginType: "2"
        },
        data: {
            module: "Music.SingerListServer",
            method: "get_singer_list",
            param: param
        }
    };

    let url = musicuApi + '?data=' + encodeURIComponent(JSON.stringify(fullData));
    try {
        let res = await req(url, { headers });
        let json = JSON.parse(res.content || res);
        if (json && json.code === 0 && json.data && json.data.code === 0) {
            let list = json.data.data.singerlist || [];
            let total = json.data.data.total || 0;
            let tags = json.data.data.tags;
            return { list, total, tags };
        }
    } catch (e) {}
    return { list: [], total: 0, tags: null };
}

// ==================== 首页 ====================
const home = async (filter) => {
    let classes = [
        { type_id: 'toplist', type_name: '排行榜' },
        { type_id: 'playlist', type_name: '歌单筛选' },
        { type_id: 'singer', type_name: '歌手' }
    ];

    let filters = {};
    let categories = await getPlaylistCategories();
    if (categories.length > 0) {
        let cols = [];
        for (let group of categories) {
            let items = group.v_item.map(item => ({
                n: item.name,
                v: item.id.toString()
            }));
            if (items.length > 0) {
                cols.push({
                    key: group.group_name,
                    name: group.group_name,
                    value: items
                });
            }
        }
        if (cols.length > 0) filters['playlist'] = cols;
    }

    let tags = await getSingerTags();
    if (tags) {
        let singerFilter = [];
        if (tags.area) {
            singerFilter.push({
                key: 'area',
                name: '地区',
                value: tags.area.map(t => ({ n: t.name, v: String(t.id) }))
            });
        }
        if (tags.genre) {
            singerFilter.push({
                key: 'genre',
                name: '流派',
                value: tags.genre.map(t => ({ n: t.name, v: String(t.id) }))
            });
        }
        if (tags.sex) {
            singerFilter.push({
                key: 'sex',
                name: '性别',
                value: tags.sex.map(t => ({ n: t.name, v: String(t.id) }))
            });
        }
        if (tags.index) {
            singerFilter.push({
                key: 'index',
                name: '字母',
                value: tags.index.map(t => ({ n: t.name, v: String(t.id) }))
            });
        }
        filters['singer'] = singerFilter;
    }

    let defaultCatId = getFirstCategoryId(categories);
    let { list } = await fetchCategoryPlaylist(defaultCatId, 1);
    return JSON.stringify({ class: classes, filters, list });
};

const homeVod = async () => {
    return JSON.stringify({ list: [] });
};

// ==================== 分类页 ====================
const category = async (tid, pg, filter, extend) => {
    let page = parseInt(pg) || 1;

    if (tid === 'playlist') {
        let categories = await getPlaylistCategories();
        let catId = getFirstCategoryId(categories);
        if (extend) {
            let extObj = typeof extend === 'string' ? JSON.parse(extend) : extend;
            let keys = Object.keys(extObj);
            for (let key of keys) {
                if (key !== 'page' && key !== 'tid' && extObj[key]) {
                    catId = String(extObj[key]);
                    break;
                }
            }
        }
        let { list, total } = await fetchCategoryPlaylist(catId, page);
        let size = 36;
        let pagecount = Math.ceil(total / size) || 1;
        return JSON.stringify({ list, page, pagecount, limit: size, total });
    }

    if (tid === 'toplist') {
        let url = 'https://c.y.qq.com/v8/fcg-bin/fcg_myqq_toplist.fcg?g_tk=5381&uin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=h5&needNewCode=1';
        let list = [];
        try {
            let res = await req(url, { headers: { ...headers, Referer: 'https://y.qq.com/' } });
            let json = JSON.parse(res.content || res);
            if (json && json.code === 0 && json.data && json.data.topList) {
                list = json.data.topList.map(item => ({
                    vod_id: 'toplist_' + item.id,
                    vod_name: item.topTitle,
                    vod_pic: item.picUrl || '',
                    vod_remarks: formatNum(item.listenCount || 0)
                }));
            }
        } catch (e) {}
        return JSON.stringify({ list, page: 1, pagecount: 1, limit: list.length, total: list.length });
    }

    if (tid === 'singer') {
        let params = { genre: -100, index: -100, area: -100, sex: -100 };
        if (extend) {
            let extObj = typeof extend === 'string' ? JSON.parse(extend) : extend;
            if (extObj.area) params.area = extObj.area;
            if (extObj.genre) params.genre = extObj.genre;
            if (extObj.sex) params.sex = extObj.sex;
            if (extObj.index) params.index = extObj.index;
        }
        let { list: singerList, total } = await fetchSingerList(params, page);
        let size = 30;
        let pagecount = Math.ceil(total / size) || 1;
        let list = singerList.map(s => ({
            vod_id: 'singer_' + s.singer_mid + '$' + encodeURIComponent(s.singer_name) + '$' + encodeURIComponent(s.singer_pic || ''),
            vod_name: s.singer_name,
            vod_pic: s.singer_pic || '',
            vod_remarks: s.country || ''
        }));
        return JSON.stringify({ list, page, pagecount, limit: size, total });
    }

    return JSON.stringify({ list: [], page: 1, pagecount: 1, limit: 30, total: 0 });
};

function formatNum(num) {
    if (num >= 10000) return (num / 10000).toFixed(1) + '万';
    if (num >= 1000) return (num / 1000).toFixed(1) + '千';
    return num.toString();
}

// ==================== 详情 ====================
const detail = async (ids) => {
    let id = Array.isArray(ids) ? ids[0] : ids;
    try {
        // 单曲
        if (id.startsWith('song_')) {
            let parts = id.replace('song_', '').split('@');
            let mid = parts[0];
            let singerMid = parts[1] || '';

            let infoRes = await req(playApi + '?mid=' + mid + '&json=1&apikey=' + apiKey, { headers });
            let data = JSON.parse(infoRes.content || infoRes);
            let songName = data.song_name || '未知歌曲';
            let singerName = data.singer_name || '';
            let pic = data.album_pic || '';
            let lyric = data.song_lyric || data.lyric || '';

            let songs = [{ song_name: songName, singer_name: singerName, song_mid: mid }];
            if (singerMid) {
                try {
                    let singerData = {
                        comm: { ct: 24, cv: 0 },
                        singer: { module: "music.artist.ArtistSongList", method: "GetArtistSongList", param: { order: 1, singerMid: singerMid, begin: 0, num: 30 } }
                    };
                    let sUrl = musicuApi + '?loginUin=0&hostUin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=wk_v15.json&needNewCode=0&data=' + encodeURIComponent(JSON.stringify(singerData));
                    let sRes = await req(sUrl, { headers });
                    let sJson = JSON.parse(sRes.content || sRes);
                    if (sJson && sJson.code === 0 && sJson.singer && sJson.singer.data && sJson.singer.data.songList) {
                        let hotSongs = sJson.singer.data.songList
                            .filter(s => s.songInfo && s.songInfo.mid !== mid)
                            .slice(0, 9)
                            .map(s => ({
                                song_name: s.songInfo.name,
                                singer_name: s.songInfo.singer.map(v => v.name).join('/'),
                                song_mid: s.songInfo.mid
                            }));
                        songs = songs.concat(hotSongs);
                    }
                } catch (e) {}
            }
            let playUrls = songs.map(s => s.song_name + '\n' + s.singer_name + '$' + s.song_mid);
            return JSON.stringify({
                list: [{
                    vod_id: mid,
                    vod_name: songName,
                    vod_pic: pic,
                    vod_actor: singerName,
                    vod_content: lyric.replace(/\n/g, '<br>'),
                    vod_play_from: 'QQ音乐',
                    vod_play_url: playUrls.join('#')
                }]
            });
        }

        // 歌单详情
        if (id.startsWith('playlist_')) {
            let tid = id.replace('playlist_', '');
            let url = `https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg?type=1&json=1&utf8=1&onlysong=0&new_format=1&disstid=${tid}&loginUin=0&hostUin=0&format=json&inCharset=utf8&outCharset=utf-8&notice=0&platform=yqq.json&needNewCode=0`;
            try {
                let res = await req(url, { headers: { ...headers, Referer: `https://y.qq.com/n/yqq/playsquare/${tid}.html`, Origin: 'https://y.qq.com' } });
                let json = JSON.parse(res.content || res);
                let songs = [];
                let desc = '';
                if (json && json.code === 0 && json.cdlist && json.cdlist[0]) {
                    let cd = json.cdlist[0];
                    desc = cd.desc || '';
                    if (cd.songlist) {
                        songs = cd.songlist.map(s => ({
                            song_name: s.name,
                            singer_name: s.singer.map(v => v.name).join('/'),
                            song_mid: s.mid,
                            album_pic: s.album.mid ? 'https://y.gtimg.cn/music/photo_new/T002R300x300M000' + s.album.mid + '.jpg' : ''
                        }));
                    }
                }
                let playUrls = songs.map(s => s.song_name + '\n' + s.singer_name + '$' + s.song_mid);
                return JSON.stringify({
                    list: [{
                        vod_id: id,
                        vod_name: json?.cdlist?.[0]?.dissname || '歌单',
                        vod_pic: songs.length > 0 ? songs[0].album_pic : '',
                        vod_content: desc.replace(/\n/g, '<br>'),
                        vod_remarks: songs.length + ' 首',
                        vod_play_from: 'QQ音乐',
                        vod_play_url: playUrls.join('#')
                    }]
                });
            } catch (e) {
                return JSON.stringify({ list: [{ vod_id: id, vod_name: '歌单详情获取失败' }] });
            }
        }

        // 排行榜详情
        if (id.startsWith('toplist_')) {
            let topId = id.replace('toplist_', '');
            let url = `https://c.y.qq.com/v8/fcg-bin/fcg_v8_toplist_cp.fcg?g_tk=5381&uin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=h5&needNewCode=1&tpl=3&page=detail&type=top&topid=${topId}`;
            try {
                let res = await req(url, { headers: { ...headers, Referer: 'https://y.qq.com/' } });
                let json = JSON.parse(res.content || res);
                let songs = [];
                let intro = '';
                if (json && json.code === 0) {
                    intro = json.topinfo?.intro || '';
                    if (json.songlist) {
                        songs = json.songlist.map(s => {
                            let songData = s.data || s;
                            return {
                                song_name: songData.songname || '',
                                singer_name: (songData.singer || []).map(v => v.name).join('/'),
                                song_mid: songData.songmid || '',
                                album_pic: songData.albummid ? 'https://y.gtimg.cn/music/photo_new/T002R300x300M000' + songData.albummid + '.jpg' : ''
                            };
                        });
                    }
                }
                let playUrls = songs.map(s => s.song_name + '\n' + s.singer_name + '$' + s.song_mid);
                return JSON.stringify({
                    list: [{
                        vod_id: id,
                        vod_name: json?.topinfo?.ListName || '排行榜',
                        vod_pic: json?.topinfo?.pic_album || '',
                        vod_content: intro.replace(/\n/g, '<br>'),
                        vod_remarks: songs.length + ' 首',
                        vod_play_from: 'QQ音乐',
                        vod_play_url: playUrls.join('#')
                    }]
                });
            } catch (e) {}
        }

        // 歌手详情（直接解析 id 中的名称和头像，并用搜索接口拉取最多 100 首）
if (id.startsWith('singer_')) {
    let pureId = id.substring(7);
    let parts = pureId.split('$');
    let singerMid = parts[0];
    let singerName = parts[1] ? decodeURIComponent(parts[1]) : '';
    let singerPic = parts[2] ? decodeURIComponent(parts[2]) : '';

    let tracks = [];
    if (singerName) {
        // 循环请求多页，每页 30 首，累计最多 120 首
        for (let p = 1; p <= 4; p++) {
            try {
                let searchData = {
                    comm: { ct: "19", cv: "18090031", v: "18090031", tmeAppID: "qqmusic" },
                    req: { module: "music.search.SearchCgiService", method: "DoSearchForQQMusicMobile", param: { search_type: 0, query: singerName, page_num: p, num_per_page: 30, highlight: 0, nqc_flag: 0, multi_zhida: 0, cat: 2, grp: 1, sin: 0, sem: 0 } }
                };
                let sUrl = musicuApi + '?loginUin=0&hostUin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=wk_v15.json&needNewCode=0&data=' + encodeURIComponent(JSON.stringify(searchData));
                let sRes = await req(sUrl, { headers });
                let sJson = JSON.parse(sRes.content || sRes);
                if (sJson && sJson.req && sJson.req.code === 0 && sJson.req.data && sJson.req.data.body && sJson.req.data.body.item_song) {
                    let items = sJson.req.data.body.item_song;
                    for (let s of items) {
                        tracks.push({
                            song_name: s.name,
                            singer_name: (s.singer || []).map(v => v.name).join('/'),
                            song_mid: s.mid
                        });
                    }
                    if (items.length < 30) break; // 不足一页，停止翻页
                } else break;
            } catch (e) { break; }
        }
        // 去重（按 song_mid）
        let seen = {};
        tracks = tracks.filter(s => {
            if (seen[s.song_mid]) return false;
            seen[s.song_mid] = true;
            return true;
        });
        if (tracks.length > 100) tracks = tracks.slice(0, 100);
    }

    let playUrls = tracks.map(s => s.song_name + '\n' + s.singer_name + '$' + s.song_mid);
    return JSON.stringify({
        list: [{
            vod_id: id,
            vod_name: singerName || '歌手',
            vod_pic: singerPic,
            vod_play_from: 'QQ音乐',
            vod_play_url: playUrls.join('#')
        }]
    });
}

        // 播放全部搜索结果
        if (id.startsWith('searchall:')) {
            let params = id.replace('searchall:', '').split(':');
            let keyword = params[0];
            let page = params[1] || '1';
            let searchData = {
                comm: { ct: "19", cv: "18090031", v: "18090031", tmeAppID: "qqmusic" },
                req: { module: "music.search.SearchCgiService", method: "DoSearchForQQMusicMobile", param: { search_type: 0, query: keyword, page_num: page, num_per_page: 30, highlight: 0, nqc_flag: 0, multi_zhida: 0, cat: 2, grp: 1, sin: 0, sem: 0 } }
            };
            let sUrl = musicuApi + '?loginUin=0&hostUin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=wk_v15.json&needNewCode=0&data=' + encodeURIComponent(JSON.stringify(searchData));
            let sRes = await req(sUrl, { headers });
            let sJson = JSON.parse(sRes.content || sRes);
            let songs = [];
            if (sJson && sJson.req && sJson.req.code === 0 && sJson.req.data && sJson.req.data.body && sJson.req.data.body.item_song) {
                songs = sJson.req.data.body.item_song.map(s => ({
                    song_name: s.name,
                    singer_name: (s.singer || []).map(v => v.name).join('/'),
                    song_mid: s.mid,
                    album_pic: s.album && s.album.mid ? 'https://y.gtimg.cn/music/photo_new/T002R300x300M000' + s.album.mid + '.jpg' : ''
                }));
            }
            if (songs.length === 0) return JSON.stringify({ list: [{ vod_id: id, vod_name: '暂无结果' }] });
            let playUrls = songs.map(s => s.song_name + '\n' + s.singer_name + '$' + s.song_mid);
            return JSON.stringify({
                list: [{
                    vod_id: id,
                    vod_name: '搜索: ' + keyword,
                    vod_pic: 'https://img2.baidu.com/it/u=2057447520,2217166139&fm=253&fmt=auto&app=138&f=JPEG?w=801&h=500',
                    vod_remarks: songs.length + ' 首歌曲',
                    vod_play_from: 'QQ音乐',
                    vod_play_url: playUrls.join('#')
                }]
            });
        }
    } catch (e) {
        return JSON.stringify({ list: [{ vod_id: id, vod_name: '解析失败' }] });
    }
};

// ==================== 搜索 ====================
const search = async (wd, quick, pg) => {
    let page = parseInt(pg) || 1;
    let data = {
        comm: { ct: "19", cv: "18090031", v: "18090031", tmeAppID: "qqmusic" },
        req: { module: "music.search.SearchCgiService", method: "DoSearchForQQMusicMobile", param: { search_type: 0, query: wd, page_num: page, num_per_page: 30, highlight: 0, nqc_flag: 0, multi_zhida: 0, cat: 2, grp: 1, sin: 0, sem: 0 } }
    };
    let url = musicuApi + '?loginUin=0&hostUin=0&format=json&inCharset=utf-8&outCharset=utf-8&notice=0&platform=wk_v15.json&needNewCode=0&data=' + encodeURIComponent(JSON.stringify(data));
    try {
        let res = await req(url, { headers });
        let json = JSON.parse(res.content || res);
        let list = [];
        let totalNum = 0;
        if (json && json.req && json.req.code === 0 && json.req.data && json.req.data.body && json.req.data.body.item_song) {
            totalNum = json.req.data.body.item_song.length;
            list = json.req.data.body.item_song.map(s => {
                let singerMid = s.singer && s.singer[0] ? s.singer[0].mid : '';
                return {
                    vod_id: 'song_' + s.mid + (singerMid ? '@' + singerMid : ''),
                    vod_name: s.name,
                    vod_pic: s.album && s.album.mid ? 'https://y.gtimg.cn/music/photo_new/T002R300x300M000' + s.album.mid + '.jpg' : '',
                    vod_remarks: (s.singer || []).map(v => v.name).join('/')
                };
            });
        }
        if (list.length > 0) {
            list.unshift({
                vod_id: 'searchall:' + wd + ':' + page,
                vod_name: '播放全部搜索结果',
                vod_pic: 'https://img2.baidu.com/it/u=2057447520,2217166139&fm=253&fmt=auto&app=138&f=JPEG?w=801&h=500',
                vod_remarks: '共' + totalNum + '首'
            });
        }
        return JSON.stringify({ list, page, pagecount: list.length < 30 ? page : page + 1, limit: 30, total: 999 });
    } catch (e) {
        return JSON.stringify({ list: [], page, pagecount: 1, limit: 30, total: 0 });
    }
};

// ==================== 播放（音质菜单） ====================
const play = async (flag, id, flags) => {
    let mid = '';
    let songName = '';
    let raw = id;
    
    // 去掉可能存在的 "song_" 前缀
    if (raw.startsWith('song_')) {
        raw = raw.substring(5);
    }
    
    // 尝试从 id 中提取歌名和 mid
    if (raw.includes('$')) {
        let parts = raw.split('$');
        // 尝试解码最后一个部分作为歌名
        if (parts.length >= 2) {
            try {
                songName = decodeURIComponent(parts[parts.length - 1]);
            } catch (e) {
                songName = parts[parts.length - 1];
            }
        }
        // mid 取第一部分
        mid = parts[0];
        // 处理 "歌名\n歌手$mid" 格式
        if (mid.includes('\n')) {
            mid = mid.split('\n').pop();
        }
    } else {
        // 纯 mid
        mid = raw;
    }
    
    // 构建请求 URL：优先用歌名搜索，否则用 mid
    let apiUrl = '';
    if (songName) {
        apiUrl = 'https://api.nki.pw/API/music_open_api.php?msg=' + encodeURIComponent(songName) + '&n=1&json=1&apikey=' + apiKey;
    } else if (mid) {
        apiUrl = 'https://api.nki.pw/API/music_open_api.php?mid=' + mid + '&json=1&apikey=' + apiKey;
    } else {
        return JSON.stringify({ parse: 0, url: '' });
    }
    
    try {
        let playRes = await req(apiUrl, { headers });
        let data = JSON.parse(playRes.content || playRes);
        
        // 构建音质菜单交替数组
        let urls = [];
        if (data.song_play_url_sq) { urls.push('SQ无损'); urls.push(data.song_play_url_sq); }
        if (data.song_play_url_hq) { urls.push('HQ高品质'); urls.push(data.song_play_url_hq); }
        if (data.song_play_url_standard) { urls.push('标准'); urls.push(data.song_play_url_standard); }
        if (data.song_play_url_fq) { urls.push('流畅'); urls.push(data.song_play_url_fq); }
        if (urls.length === 0 && data.song_play_url) {
            urls.push('默认'); urls.push(data.song_play_url);
        }
        if (urls.length === 0) return JSON.stringify({ parse: 0, url: '' });
        
        return JSON.stringify({
            parse: 0,
            url: urls,
            header: headers,
            lrc: data.song_lyric || data.lyric || '',
            pic: data.album_pic || '',
            cover: data.album_pic || '',
            title: data.song_name || '',
            artist: data.singer_name || ''
        });
    } catch (e) {
        return JSON.stringify({ parse: 0, url: '' });
    }
};

export function __jsEvalReturn() {
    return { init, home, homeVod, category, detail, search, play };
}