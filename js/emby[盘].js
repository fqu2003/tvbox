


let emby_img = '';
let servers = [];

const defaultHeaders = {
  'User-Agent': 'Yamby/1.0.2(Android)',
  'Content-Type': 'application/json; charset=UTF-8'
};

async function init(cfg) {
    servers = [];
    
    if (cfg.ext) {
        if (Array.isArray(cfg.ext)) {
            for (let i = 0; i < cfg.ext.length; i++) {
                const serverConfig = cfg.ext[i];
                
                if (serverConfig && typeof serverConfig === 'object') {
                    const serverUrl = serverConfig.baseURL || serverConfig.server;
                    const serverName = serverConfig.name || `Emby服务器_${i + 1}`;
                    
                    if (serverUrl) {
                        servers.push({
                            name: serverName,
                            baseURL: serverUrl.trim(),
                            username: serverConfig.username || '',
                            password: serverConfig.password || '',
                            index: i
                        });
                    }
                }
            }
        } else if (typeof cfg.ext === 'object' && cfg.ext !== null) {
            const serverUrl = cfg.ext.baseURL || cfg.ext.server;
            const serverName = cfg.ext.name || 'Emby服务器';
            
            if (serverUrl) {
                servers.push({
                    name: serverName,
                    baseURL: serverUrl.trim(),
                    username: cfg.ext.username || '',
                    password: cfg.ext.password || '',
                    index: 0
                });
            }
        } else if (typeof cfg.ext === 'string' && cfg.ext.trim() !== '') {
                const parsedConfig = JSON.parse(cfg.ext);
                if (Array.isArray(parsedConfig)) {
                    for (let i = 0; i < parsedConfig.length; i++) {
                        const serverConfig = parsedConfig[i];
                        if (serverConfig && typeof serverConfig === 'object') {
                            const serverUrl = serverConfig.baseURL || serverConfig.server;
                            const serverName = serverConfig.name || `Emby服务器_${i + 1}`;
                            
                            if (serverUrl) {
                                servers.push({
                                    name: serverName,
                                    baseURL: serverUrl.trim(),
                                    username: serverConfig.username || '',
                                    password: serverConfig.password || '',
                                    index: i
                                });
                            }
                        }
                    }
                } else if (typeof parsedConfig === 'object') {
                    const serverUrl = parsedConfig.baseURL || parsedConfig.server;
                    const serverName = parsedConfig.name || 'Emby服务器';
                    
                    if (serverUrl) {
                        servers.push({
                            name: serverName,
                            baseURL: serverUrl.trim(),
                            username: parsedConfig.username || '',
                            password: parsedConfig.password || '',
                            index: 0
                        });
                    }
                }
        }
    }
    
    cfg.skey = '';
    cfg.stype = '3';
    return true;
}

async function home(filter) {
  let result = {};
  let classList = [];
  
  for (let i = 0; i < servers.length; i++) {
    let server = servers[i];
    let serverConfig = parseConfig(server);
    
    classList.push({
      type_name: serverConfig.displayName,
      type_id: `server_${i}`
    });
  }
  
  result.class = classList;
  return JSON.stringify(result);
}

async function homeVod(params) {
  if (servers.length === 0) {
    return JSON.stringify({
      list: []
    });
  }
  
  let server = servers[0];
  let serverConfig = parseConfig(server);
  let embyInfos = await getToken(serverConfig.baseURL, server.username, server.password);
  
  // 显示服务器0的媒体库列表
  let data = await showLibs(serverConfig.baseURL, embyInfos, 1, 0);
  return JSON.stringify(data);
}


async function category(tid, pg, filter, extend) {
  let result = [];
  let page = parseInt(pg) || 1;
  
  let serverIndex = 0;
  let currentPath = '';
  let libraryId = '';
  
  if (tid) {
    if (tid.startsWith('server_')) {
      serverIndex = parseInt(tid.replace('server_', ''));
      currentPath = 'server';
    } else if (tid.startsWith('library_')) {
      let parts = tid.split('_');
      if (parts.length >= 3) {
        serverIndex = parseInt(parts[1]) || 0;
        libraryId = parts[2] || '';
      }
      currentPath = 'library';
    } else if (tid.startsWith('folder_')) {
      let parts = tid.split('_');
      if (parts.length >= 3) {
        serverIndex = parseInt(parts[1]) || 0;
        libraryId = parts[2] || '';
      }
      currentPath = 'folder';
    } else if (tid.startsWith('empty_')) {
      return JSON.stringify({
        list: [],
        page: 1,
        pagecount: 1,
        limit: 0,
        total: 0
      });
    } else {
      serverIndex = parseInt(tid) || 0;
      currentPath = 'server';
    }
  } else {
    serverIndex = 0;
    currentPath = 'server';
  }
  
  let server = getServer(serverIndex);
  if (!server) {
    return JSON.stringify({
      list: [],
      page: 1,
      pagecount: 1,
      limit: 0,
      total: 0
    });
  }

  let serverConfig = parseConfig(server);
  let embyInfos = await getToken(serverConfig.baseURL, server.username, server.password);
  
  if (currentPath === 'server' || !currentPath) {
    if (serverConfig.pathFilter) {
      let data = await showPath(serverConfig.baseURL, embyInfos, serverConfig.pathFilter, page, serverIndex);
      return JSON.stringify(data);
    } else {
      if (page > 1) {
        return JSON.stringify({
          list: [],
          page: 1,
          pagecount: 1,
          limit: 0,
          total: 0
        });
      }
      let data = await showLibs(serverConfig.baseURL, embyInfos, page, serverIndex);
      return JSON.stringify(data);
    }
    
  } else if (currentPath === 'library') {
    let data = await getLibContent(serverConfig.baseURL, embyInfos, libraryId, page, serverIndex);
    return JSON.stringify(data);
    
  } else if (currentPath === 'folder') {
    let data = await getFolder(serverConfig.baseURL, embyInfos, libraryId, page, serverIndex);
    return JSON.stringify(data);
  }

  return JSON.stringify({
    list: result,
    page: page,
    pagecount: 1,
    limit: result.length,
    total: result.length
  });
}

async function detail(id) {
  if (id.startsWith('library_') || id.startsWith('folder_') || id.startsWith('empty_') || id === 'error') {
    return JSON.stringify({
      list: []
    });
  }
  
  let parts = id.split('_');
  if (parts.length < 2) {
    return JSON.stringify({
      list: []
    });
  }
  
  let serverIndex = parseInt(parts[0]);
  let vod_id = parts[1];
  
  let server = getServer(serverIndex);
  if (!server) {
    return JSON.stringify({
      list: []
    });
  }

  try {
    let serverConfig = parseConfig(server);
    let embyInfos = await getToken(serverConfig.baseURL, server.username, server.password);

    let url = `${serverConfig.baseURL}/emby/Users/${embyInfos.User.Id}/Items/${vod_id}?` +
      `X-Emby-Client=${embyInfos.SessionInfo.Client}` +
      `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
      `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
      `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
      `&X-Emby-Token=${embyInfos.AccessToken}`;

    let r = await req(url, { 
      timeout: 8000,
      headers: defaultHeaders
    });
    let videoInfos = JSON.parse(r.content);
    let playUrl = '';

    if (!videoInfos.IsFolder) {
      playUrl += `${videoInfos.Name.trim()}$${serverIndex}_${videoInfos.Id}#`;
    } else {
      let showUrl = `${serverConfig.baseURL}/emby/Shows/${vod_id}/Seasons?` +
        `X-Emby-Client=${embyInfos.SessionInfo.Client}` +
        `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
        `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
        `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
        `&X-Emby-Token=${embyInfos.AccessToken}` +
        `&UserId=${embyInfos.User.Id}` +
        `&EnableImages=true` +
        `&Fields=BasicSyncInfo,CanDelete,Container,PrimaryImageAspectRatio,ProductionYear,CommunityRating` +
        `&EnableUserData=true` +
        `&EnableTotalRecordCount=false`;

      let showR = await req(showUrl, { headers: defaultHeaders });
      if (showR && JSON.parse(showR.content).Items) {
        let playInfos = JSON.parse(showR.content).Items;
        
        for (let playInfo of playInfos) {
          let episodeUrl = `${serverConfig.baseURL}/emby/Shows/${playInfo.Id}/Episodes?` +
            `X-Emby-Client=${embyInfos.SessionInfo.Client}` +
            `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
            `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
            `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
            `&X-Emby-Token=${embyInfos.AccessToken}` +
            `&SeasonId=${playInfo.Id}` +
            `&Fields=BasicSyncInfo,CanDelete,CommunityRating,PrimaryImageAspectRatio,ProductionYear,Overview`;

          let episodeR = await req(episodeUrl, { headers: defaultHeaders });
          let videoList = JSON.parse(episodeR.content).Items;
          
          for (let video of videoList) {
            let seasonName = playInfo.Name.replace(/#/g, '-').replace(/\$/g, '|').trim();
            playUrl += `${seasonName}|${video.Name.trim()}$${serverIndex}_${video.Id}#`;
          }
        }
      } else {
        let folderUrl = `${serverConfig.baseURL}/emby/Users/${embyInfos.User.Id}/Items?` +
          `ParentId=${vod_id}` +
          `&Fields=BasicSyncInfo,CanDelete,Container,PrimaryImageAspectRatio,ProductionYear,CommunityRating,CriticRating` +
          `&ImageTypeLimit=1` +
          `&StartIndex=0` +
          `&EnableUserData=true` +
          `&X-Emby-Client=${embyInfos.SessionInfo.Client}` +
          `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
          `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
          `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
          `&X-Emby-Token=${embyInfos.AccessToken}`;

        let folderR = await req(folderUrl, { headers: defaultHeaders });
        let videoList = JSON.parse(folderR.content).Items;
        for (let video of videoList) {
          let videoName = video.Name.replace(/#/g, '-').replace(/\$/g, '|').trim();
          playUrl += `${videoName}$${serverIndex}_${video.Id}#`;
        }
      }
    }

    let pic = '';
    if (videoInfos.ImageTags && videoInfos.ImageTags.Primary) {
      pic = `${serverConfig.baseURL}/emby/Items/${vod_id}/Images/Primary?maxWidth=400&tag=${videoInfos.ImageTags.Primary}&quality=90`;
    } else {
      pic = emby_img;
    }

    let vod = {
      vod_id: `${serverIndex}_${vod_id}`,
      vod_name: `${videoInfos.Name}`,
      vod_pic: pic,
      type_name: videoInfos.Genres && videoInfos.Genres.length > 0 ? videoInfos.Genres[0] : '',
      vod_year: videoInfos.ProductionYear || '',
      vod_content: videoInfos.Overview ?
        videoInfos.Overview.replace(/\xa0/g, ' ').replace(/\n\n/g, '\n').trim() : '',
      vod_play_from: 'EMBY',
      vod_play_url: playUrl.replace(/#$/, '')
    };
    
    return JSON.stringify({
      list: [vod]
    });

  } catch (e) {
    return JSON.stringify({
      list: []
    });
  }
}

async function play(flag, id, flags) {
  let parts = id.split('_');
  if (parts.length < 2) {
    return JSON.stringify({
      parse: 0,
      url: ''
    });
  }
  
  let serverIndex = parseInt(parts[0]);
  let pid = parts[1];
  
  let server = getServer(serverIndex);
  if (!server) {
    return JSON.stringify({
      parse: 0,
      url: ''
    });
  }
  
  try {
    let serverConfig = parseConfig(server);
    let embyInfos = await getToken(serverConfig.baseURL, server.username, server.password);
    
    let apiUrl = `${serverConfig.baseURL}/emby/Items/${pid}/PlaybackInfo?` +
      `UserId=${embyInfos.User.Id}` +
      `&IsPlayback=true` +
      `&AutoOpenLiveStream=true` +
      `&StartTimeTicks=0` +
      `&MaxStreamingBitrate=2147483647` +
      `&X-Emby-Client=${embyInfos.SessionInfo.Client}` +
      `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
      `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
      `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
      `&X-Emby-Token=${embyInfos.AccessToken}`;

    let data = JSON.stringify({
      "DeviceProfile": {
        "SubtitleProfiles": [
          {"Method": "Embed", "Format": "ass"},
          {"Format": "ssa", "Method": "Embed"},
          {"Format": "subrip", "Method": "Embed"},
          {"Format": "sub", "Method": "Embed"},
          {"Method": "Embed", "Format": "pgssub"},
          {"Format": "subrip", "Method": "External"},
          {"Method": "External", "Format": "sub"},
          {"Method": "External", "Format": "ass"},
          {"Format": "ssa", "Method": "External"},
          {"Method": "External", "Format": "vtt"},
          {"Method": "External", "Format": "ass"},
          {"Format": "ssa", "Method": "External"}
        ],
        "CodecProfiles": [
          {
            "Codec": "h264",
            "Type": "Video",
            "ApplyConditions": [
              {"Property": "IsAnamorphic", "Value": "true", "Condition": "NotEquals", "IsRequired": false},
              {"IsRequired": false, "Value": "high|main|baseline|constrained baseline", "Condition": "EqualsAny", "Property": "VideoProfile"},
              {"IsRequired": false, "Value": "80", "Condition": "LessThanEqual", "Property": "VideoLevel"},
              {"IsRequired": false, "Value": "true", "Condition": "NotEquals", "Property": "IsInterlaced"}
            ]
          },
          {
            "Codec": "hevc",
            "ApplyConditions": [
              {"Property": "IsAnamorphic", "Value": "true", "Condition": "NotEquals", "IsRequired": false},
              {"IsRequired": false, "Value": "high|main|main 10", "Condition": "EqualsAny", "Property": "VideoProfile"},
              {"Property": "VideoLevel", "Value": "175", "Condition": "LessThanEqual", "IsRequired": false},
              {"IsRequired": false, "Value": "true", "Condition": "NotEquals", "Property": "IsInterlaced"}
            ],
            "Type": "Video"
          }
        ],
        "MaxStreamingBitrate": 40000000,
        "TranscodingProfiles": [
          {
            "Container": "ts",
            "AudioCodec": "aac,mp3,wav,ac3,eac3,flac,opus",
            "VideoCodec": "hevc,h264,mpeg4",
            "BreakOnNonKeyFrames": true,
            "Type": "Video",
            "MaxAudioChannels": "6",
            "Protocol": "hls",
            "Context": "Streaming",
            "MinSegments": 2
          }
        ],
        "DirectPlayProfiles": [],
        "ResponseProfiles": [
          {"MimeType": "video/mp4", "Type": "Video", "Container": "m4v"}
        ],
        "ContainerProfiles": [],
        "MusicStreamingTranscodingBitrate": 40000000,
        "MaxStaticBitrate": 40000000
      }
    });

    let r = await req(apiUrl, {
      method: 'POST',
      headers: defaultHeaders,
      body: data,
      timeout: 8000
    });
    
    let playInfo = JSON.parse(r.content);
    let media_sources = [];
    
    if (playInfo.MediaSources && playInfo.MediaSources.length > 0) {
      for (let i = 0; i < playInfo.MediaSources.length; i++) {
        let source = playInfo.MediaSources[i];
        
        // 只保留转码
        if (source.TranscodingUrl) {
          let transcodeUrl = serverConfig.baseURL + source.TranscodingUrl;
          media_sources.push(`转码#${i + 1}`);
          media_sources.push(transcodeUrl);
        }
      }
    }

    let result = {
      "parse": 0,
      "url": media_sources,
      "header": {'User-Agent': 'Yamby/1.0.2(Android)'}
    };

    return JSON.stringify(result);

  } catch (e) {
    return JSON.stringify({
      parse: 0,
      url: ''
    });
  }
}

async function search(wd, quick, pg) {
  let result = [];
  let page = parseInt(pg) || 1;
  
  if (!wd || wd.trim() === '') {
    return JSON.stringify({
      list: result,
      page: page,
      pagecount: 1,
      limit: 0,
      total: 0
    });
  }
  
  try {
    let searchPromises = [];
    
    for (let i = 0; i < servers.length; i++) {
      let server = servers[i];
      let serverConfig = parseConfig(server);
      
      let searchPromise = (async () => {
        try {
          let embyInfos = await getToken(serverConfig.baseURL, server.username, server.password);
          
          let searchUrl = `${serverConfig.baseURL}/emby/Users/${embyInfos.User.Id}/Items?` +
            `SearchTerm=${encodeURIComponent(wd)}` +
            `&Recursive=true` +
            `&Fields=PrimaryImageAspectRatio,ProductionYear,CommunityRating` +
            `&ImageTypeLimit=1` +
            `&EnableImageTypes=Primary` +
            `&Limit=20` +
            `&X-Emby-Client=${embyInfos.SessionInfo.Client}` +
            `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
            `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
            `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
            `&X-Emby-Token=${embyInfos.AccessToken}`;

          let r = await req(searchUrl, { 
            timeout: 5000,
            headers: defaultHeaders
          });
          let data = JSON.parse(r.content);
          let items = data.Items || [];
          
          let serverResults = [];
          for (let item of items) {
            let remarks = item.ProductionYear || '';
            if (item.CommunityRating) {
              remarks = remarks ? `${remarks} · ⭐${item.CommunityRating}` : `⭐${item.CommunityRating}`;
            }
            
            let pic = '';
            if (item.ImageTags && item.ImageTags.Primary) {
              pic = `${serverConfig.baseURL}/emby/Items/${item.Id}/Images/Primary?maxWidth=300&tag=${item.ImageTags.Primary}&quality=80`;
            } else {
              pic = emby_img;
            }

            serverResults.push({
              vod_id: `${i}_${item.Id}`,
              vod_name: `${cleanText(item.Name)}`,
              vod_pic: pic,
              vod_remarks: `[${server.name}] ${remarks}`,
              vod_content: item.Overview ? cleanText(item.Overview) : '',
              vod_tag: 'video'
            });
          }
          
          return serverResults;
          
        } catch (e) {
          return [];
        }
      })();
      
      searchPromises.push(searchPromise);
    }
    
    let allResults = await Promise.allSettled(searchPromises);
    
    for (let promiseResult of allResults) {
      if (promiseResult.status === 'fulfilled') {
        result = result.concat(promiseResult.value);
      }
    }
    
  } catch (e) {
  }
  
  return JSON.stringify({
    list: result,
    page: page,
    pagecount: page + 1,
    limit: result.length,
    total: result.length * (page + 1)
  });
}

function getServer(index) {
  if (index >= 0 && index < servers.length) {
    return servers[index];
  }
  return null;
}

function parseConfig(server) {
  const url = server.baseURL;
  
  if (!url.includes('/') || url.split('/').length <= 3) {
    return {
      baseURL: url,
      pathFilter: null,
      displayName: server.name
    };
  }
  
  const urlParts = url.split('/');
  const baseURL = `${urlParts[0]}//${urlParts[2]}`;
  
  const pathParts = urlParts.slice(3);
  const pathFilter = pathParts.join('/');
  
  return {
    baseURL: baseURL,
    pathFilter: pathFilter,
    displayName: server.name
  };
}

async function showPath(baseURL, embyInfos, pathFilter, page, serverIndex) {
  let viewsUrl = `${baseURL}/emby/Users/${embyInfos.User.Id}/Views?X-Emby-Client=${embyInfos.SessionInfo.Client}&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}&X-Emby-Token=${embyInfos.AccessToken}`;

  let viewsResponse = await req(viewsUrl, { 
    timeout: 10000,
    headers: defaultHeaders
  });
  let views = JSON.parse(viewsResponse.content).Items;
  
  let targetLibrary = null;
  for (let view of views) {
    const libraryPath = view.Path || '';
    const libraryName = view.Name || '';
    
    if (libraryPath.includes(pathFilter) || libraryName.includes(pathFilter)) {
      targetLibrary = view;
      break;
    }
  }
  
  if (targetLibrary) {
    return await getLibContent(baseURL, embyInfos, targetLibrary.Id, page, serverIndex);
  } else {
    for (let view of views) {
      if (view.Name.includes('播放列表') || view.Name.includes('相机')) {
        continue;
      }
      
      try {
        let searchUrl = `${baseURL}/emby/Users/${embyInfos.User.Id}/Items?` +
          `ParentId=${view.Id}` +
          `&Recursive=true` +
          `&IncludeItemTypes=Folder` +
          `&Fields=Path` +
          `&Limit=50` +
          `&X-Emby-Client=${embyInfos.SessionInfo.Client}` +
          `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
          `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
          `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
          `&X-Emby-Token=${embyInfos.AccessToken}`;

        let searchResponse = await req(searchUrl, { 
          timeout: 8000,
          headers: defaultHeaders
        });
        let searchData = JSON.parse(searchResponse.content);
        let folders = searchData.Items || [];
        
        for (let folder of folders) {
          const folderPath = folder.Path || '';
          const folderName = folder.Name || '';
          
          if (folderPath.includes(pathFilter) || folderName.includes(pathFilter)) {
            return await getFolder(baseURL, embyInfos, folder.Id, page, serverIndex);
          }
        }
      } catch (e) {
      }
    }
    
    return await showLibs(baseURL, embyInfos, page, serverIndex);
  }
}

async function showLibs(baseURL, embyInfos, page, serverIndex) {
  let result = [];
  
  try {
    let viewsUrl = `${baseURL}/emby/Users/${embyInfos.User.Id}/Views?X-Emby-Client=${embyInfos.SessionInfo.Client}&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}&X-Emby-Token=${embyInfos.AccessToken}`;

    let viewsResponse = await req(viewsUrl, { 
      timeout: 10000,
      headers: defaultHeaders
    });
    let views = JSON.parse(viewsResponse.content).Items;
    
    let mediaLibraries = views.filter(view => 
      !view.Name.includes('播放列表') && !view.Name.includes('相机')
    );

    let libraryPromises = mediaLibraries.map(async (library) => {
      try {
        let statsUrl = `${baseURL}/emby/Users/${embyInfos.User.Id}/Items?` +
          `ParentId=${library.Id}` +
          `&Recursive=true` +
          `&IncludeItemTypes=Movie,Series` +
          `&Fields=PrimaryImageAspectRatio` +
          `&Limit=1` +
          `&X-Emby-Client=${embyInfos.SessionInfo.Client}` +
          `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
          `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
          `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
          `&X-Emby-Token=${embyInfos.AccessToken}`;

        let statsResponse = await req(statsUrl, { 
          timeout: 5000,
          headers: defaultHeaders
        });
        let statsData = JSON.parse(statsResponse.content);
        let totalCount = statsData.TotalRecordCount || 0;
        
        let pic = '';
        if (library.ImageTags && library.ImageTags.Primary) {
          pic = `${baseURL}/emby/Items/${library.Id}/Images/Primary?maxWidth=300&tag=${library.ImageTags.Primary}&quality=80`;
        } else {
          pic = emby_img;
        }

        return {
          vod_id: `library_${serverIndex}_${library.Id}`,
          vod_name: `${library.Name}`,
          vod_pic: pic,
          vod_remarks: `${totalCount}个项目`,
          vod_content: '',
          vod_tag: 'folder'
        };
      } catch (e) {
        return {
          vod_id: `library_${serverIndex}_${library.Id}`,
          vod_name: `${library.Name}`,
          vod_pic: emby_img,
          vod_remarks: `媒体库`,
          vod_content: '',
          vod_tag: 'folder'
        };
      }
    });

    let libraryResults = await Promise.allSettled(libraryPromises);
    
    for (let promiseResult of libraryResults) {
      if (promiseResult.status === 'fulfilled') {
        result.push(promiseResult.value);
      }
    }

    if (mediaLibraries.length === 0) {
      result.push({
        vod_id: `empty_${serverIndex}`,
        vod_name: '暂无媒体库',
        vod_pic: emby_img,
        vod_remarks: '该服务器没有可用的媒体库',
        vod_content: '',
        vod_tag: 'folder'
      });
    }
    
  } catch (e) {
  }
  
  return {
    list: result,
    page: page,
    pagecount: 1,
    limit: result.length,
    total: result.length
  };
}

async function getLibContent(baseURL, embyInfos, libraryId, page, serverIndex) {
  let result = [];
  
  try {
    let url = `${baseURL}/emby/Users/${embyInfos.User.Id}/Items?` +
      `X-Emby-Client=${embyInfos.SessionInfo.Client}` +
      `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
      `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
      `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
      `&X-Emby-Token=${embyInfos.AccessToken}` +
      `&SortBy=SortName` +
      `&IncludeItemTypes=Movie,Series` +
      `&SortOrder=Ascending` +
      `&ParentId=${libraryId}` +
      `&Recursive=true` +
      `&Limit=24` +
      `&ImageTypeLimit=1` +
      `&StartIndex=${(page - 1) * 24}` +
      `&EnableImageTypes=Primary` +
      `&Fields=PrimaryImageAspectRatio,ProductionYear,CommunityRating,MediaType` +
      `&EnableUserData=false`;

    let r = await req(url, { 
      timeout: 10000,
      headers: defaultHeaders
    });
    let data = JSON.parse(r.content);
    let videoList = data.Items || [];

    for (let vod of videoList) {
      let name = cleanText(vod.Name);
      let pic = '';
      
      if (vod.ImageTags && vod.ImageTags.Primary) {
        pic = `${baseURL}/emby/Items/${vod.Id}/Images/Primary?maxWidth=300&tag=${vod.ImageTags.Primary}&quality=80`;
      } else {
        pic = emby_img;
      }
      
      let remarks = vod.ProductionYear || '';
      if (vod.CommunityRating) {
        remarks = remarks ? `${remarks} · ⭐${vod.CommunityRating}` : `⭐${vod.CommunityRating}`;
      }
      
      result.push({
        vod_id: `${serverIndex}_${vod.Id}`,
        vod_name: `${name}`,
        vod_pic: pic,
        vod_remarks: remarks,
        vod_content: '',
        vod_tag: 'video'
      });
    }
    
  } catch (e) {
  }
  
  return {
    list: result,
    page: page,
    pagecount: 1,
    limit: result.length,
    total: result.length
  };
}

async function getFolder(baseURL, embyInfos, folderId, page, serverIndex) {
  let result = [];
  
  try {
    let url = `${baseURL}/emby/Users/${embyInfos.User.Id}/Items?` +
      `X-Emby-Client=${embyInfos.SessionInfo.Client}` +
      `&X-Emby-Device-Name=${embyInfos.SessionInfo.DeviceName}` +
      `&X-Emby-Device-Id=${embyInfos.SessionInfo.DeviceId}` +
      `&X-Emby-Client-Version=${embyInfos.SessionInfo.ApplicationVersion}` +
      `&X-Emby-Token=${embyInfos.AccessToken}` +
      `&SortBy=SortName` +
      `&SortOrder=Ascending` +
      `&ParentId=${folderId}` +
      `&Recursive=false` +
      `&Limit=24` +
      `&ImageTypeLimit=1` +
      `&StartIndex=${(page - 1) * 24}` +
      `&EnableImageTypes=Primary` +
      `&Fields=PrimaryImageAspectRatio,ProductionYear,CommunityRating,MediaType,IsFolder` +
      `&EnableUserData=false`;

    let r = await req(url, { 
      timeout: 10000,
      headers: defaultHeaders
    });
    let data = JSON.parse(r.content);
    let items = data.Items || [];

    for (let item of items) {
      let name = cleanText(item.Name);
      let pic = '';
      
      if (item.ImageTags && item.ImageTags.Primary) {
        pic = `${baseURL}/emby/Items/${item.Id}/Images/Primary?maxWidth=300&tag=${item.ImageTags.Primary}&quality=80`;
      } else {
        pic = emby_img;
      }
      
      let remarks = item.ProductionYear || '';
      if (item.CommunityRating) {
        remarks = remarks ? `${remarks} · ⭐${item.CommunityRating}` : `⭐${item.CommunityRating}`;
      }
      
      if (item.IsFolder) {
        result.push({
          vod_id: `folder_${serverIndex}_${item.Id}`,
          vod_name: `${name}`,
          vod_pic: pic,
          vod_remarks: `文件夹 · ${remarks}`,
          vod_content: '',
          vod_tag: 'folder'
        });
      } else {
        result.push({
          vod_id: `${serverIndex}_${item.Id}`,
          vod_name: `${name}`,
          vod_pic: pic,
          vod_remarks: remarks,
          vod_content: '',
          vod_tag: 'video'
        });
      }
    }
    
  } catch (e) {
  }
  
  return {
    list: result,
    page: page,
    pagecount: 1,
    limit: result.length,
    total: result.length
  };
}

async function getToken(baseURL, username, password) {
  let key = `emby_${baseURL}_${username}_${password}`;

  if (typeof global._cache === 'undefined') {
    global._cache = {};
  }

  if (global._cache[key] && global._cache[key].AccessToken) {
    return global._cache[key];
  }

  let url = `${baseURL}/emby/Users/authenticatebyname?X-Emby-Client=Emby+Web&X-Emby-Device-Id=53a12faa-1577-4d1e-90f8-d6fc9cfcf3b2&X-Emby-Client-Version=4.9.1.80`;

  const maxRetries = 2;
  let retryDelay = 1000; 
  let lastError;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const options = {
        method: 'POST',
        headers: {
          'User-Agent': 'Yamby/1.0.2(Android)',
          'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: `Username=${encodeURIComponent(username)}&Pw=${encodeURIComponent(password)}`,
        timeout: 8000
      };

      let r = await req(url, options);
      let embyInfos = JSON.parse(r.content);

      if (!embyInfos.User || !embyInfos.User.Id) {
        throw new Error('登录响应缺少必要字段');
      }

      global._cache[key] = embyInfos;
      return embyInfos;

    } catch (error) {
      lastError = error;
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, retryDelay));
      }
    }
  }

  throw lastError;
}

function cleanText(text) {
  if (!text) return '';
  return text.replace(/[\r\n\t]/g, '').replace(/\s+/g, ' ').trim();
}

export function __jsEvalReturn() {
  return {
    init: init,
    home: home,
    homeVod: homeVod,
    category: category,
    detail: detail,
    play: play,
    proxy: null,
    search: search
  };
}