from fastapi import FastAPI, Request, Response, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from datetime import timedelta
from cache import Cache
from anime import kitsu, mal
from anime import anime_mapping
import meta_merger
import meta_builder
import translator
import asyncio
import httpx
from api import tmdb
import base64
import json
import os

# Settings
translator_version = 'v0.1.5'
FORCE_PREFIX = False
FORCE_META = False
USE_TMDB_ID_META = True
USE_TMDB_ADDON = False
REQUEST_TIMEOUT = 120
COMPATIBILITY_ID = ['tt', 'kitsu', 'mal']

# ENV file
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

# Load languages
with open("languages.json", "r", encoding="utf-8") as f:
    LANGUAGES = json.load(f) 

# Cache set
meta_cache = {}
for language in LANGUAGES:
    meta_cache[language] = Cache(f"./cache/{language}/meta/tmp",  timedelta(hours=12).total_seconds())
    meta_cache[language].clear()


# Server start
@asynccontextmanager
async def lifespan(app: FastAPI):
    print('Started')
    # Load anime mapping lists
    await anime_mapping.download_maps()
    kitsu.load_anime_map()
    mal.load_anime_map()
    yield
    print('Shutdown')

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


stremio_headers = {
    'connection': 'keep-alive', 
    'user-agent': 'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/5.15.2 Chrome/83.0.4103.122 Safari/537.36 StremioShell/4.4.168', 
    'accept': '*/*', 
    'origin': 'https://app.strem.io', 
    'sec-fetch-site': 'cross-site', 
    'sec-fetch-mode': 'cors', 
    'sec-fetch-dest': 'empty', 
    'accept-encoding': 'gzip, deflate, br'
}

tmdb_addons_pool = [
    'https://tmdb.elfhosted.com/%7B%22provide_imdbId%22%3A%22true%22%2C%22language%22%3A%22it-IT%22%7D', # Elfhosted
    'https://94c8cb9f702d-tmdb-addon.baby-beamup.club/%7B%22provide_imdbId%22%3A%22true%22%2C%22language%22%3A%22it-IT%22%7D', # Official
    'https://tmdb-catalog.madari.media/%7B%22provide_imdbId%22%3A%22true%22%2C%22language%22%3A%22it-IT%22%7D' # Madari
]

tmdb_addon_meta_url = tmdb_addons_pool[0]
cinemeta_url = 'https://v3-cinemeta.strem.io'

def json_response(data):
    response = JSONResponse(data)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Surrogate-Control"] = "no-store"
    return response


@app.get('/', response_class=HTMLResponse)
@app.get('/configure', response_class=HTMLResponse)
async def home(request: Request):
    response = templates.TemplateResponse("configure.html", {"request": request})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Surrogate-Control"] = "no-store"
    return response

@app.get('/{addon_url}/{user_settings}/configure')
async def configure(addon_url):
    addon_url = decode_base64_url(addon_url) + '/configure'
    return RedirectResponse(addon_url)

@app.get('/link_generator', response_class=HTMLResponse)
async def link_generator(request: Request):
    response = templates.TemplateResponse("link_generator.html", {"request": request})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Surrogate-Control"] = "no-store"
    return response


@app.get("/manifest.json")
async def get_manifest():
    with open("manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    return json_response(manifest)


@app.get('/{addon_url}/{user_settings}/manifest.json')
async def get_manifest(addon_url, user_settings):
    addon_url = decode_base64_url(addon_url)
    user_settings = parse_user_settings(user_settings)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(f"{addon_url}/manifest.json")
        manifest = response.json()

    is_translated = manifest.get('translated', False)
    if not is_translated:
        manifest['translated'] = True
        manifest['t_language'] = user_settings.get('language', 'it-IT')
        manifest['name'] += f" {translator.LANGUAGE_FLAGS[user_settings.get('language', 'it-IT')]}"

        if 'description' in manifest:
            manifest['description'] += f" | Translated by Toast Translator. {translator_version}"
        else:
            manifest['description'] = f"Translated by Toast Translator. {translator_version}"
    
    if FORCE_PREFIX:
        if 'idPrefixes' in manifest:
            if 'tmdb:' not in manifest['idPrefixes']:
                manifest['idPrefixes'].append('tmdb:')
            if 'tt' not in manifest['idPrefixes']:
                manifest['idPrefixes'].append('tt')

    if FORCE_META:
        if 'meta' not in manifest['resources']:
            manifest['resources'].append('meta')

    return json_response(manifest)


@app.get("/{addon_url}/{user_settings}/catalog/{type}/{path:path}")
async def get_catalog(response: Response, addon_url, type: str, user_settings: str, path: str):
    user_settings = parse_user_settings(user_settings)
    language = user_settings['language']
    tmdb_key = user_settings['tmdb_key']
    addon_url = decode_base64_url(addon_url)

    async with httpx.AsyncClient(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(f"{addon_url}/catalog/{type}/{path}")

        # Cinemeta last-videos and calendar
        if 'last-videos' in path or 'calendar-videos' in path:
            return json_response(response.json())
        
        try:
            catalog = response.json()
        except:
            print(response.text)
            return json_response({})

        if 'metas' in catalog:
            if type == 'anime':
                await remove_duplicates(catalog)
                tasks = [
                    tmdb.get_tmdb_data(client, item.get('imdb_id', item.get('id')), "imdb_id", language, tmdb_key)
                    if item.get("animeType") == "TV" or item.get("animeType") == "movie" else asyncio.sleep(0, result={})
                    for item in catalog['metas']
                ]
            else:
                tasks = [
                    tmdb.get_tmdb_data(client, item.get('imdb_id', item.get('id')), "imdb_id", language, tmdb_key) for item in catalog['metas']
                ]
            tmdb_details = await asyncio.gather(*tasks)
        else:
            return json_response({})

    new_catalog = translator.translate_catalog(catalog, tmdb_details, user_settings['sp'], user_settings['tr'], language)
    return json_response(new_catalog)


@app.get('/{addon_url}/{user_settings}/meta/{type}/{id}.json')
async def get_meta(request: Request,response: Response, addon_url, user_settings: str, type: str, id: str):
    global tmdb_addon_meta_url

    headers = dict(request.headers)
    del headers['host']

    addon_url = decode_base64_url(addon_url)
    user_settings = parse_user_settings(user_settings)
    language = user_settings['language']
    tmdb_key = user_settings['tmdb_key']

    async with httpx.AsyncClient(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:

        # Get from cache
        meta = meta_cache[language].get(id)

        # Return cached meta
        if meta != None:
            return json_response(meta)

        # Not in cache
        else:
            # Handle imdb ids
            if 'tt' in id:
                tmdb_id = await tmdb.convert_imdb_to_tmdb(id, language, tmdb_key)
                tasks = [
                    client.get(f"{tmdb_addon_meta_url}/meta/{type}/{tmdb_id}.json") if USE_TMDB_ADDON else meta_builder.build_metadata(id, type, language, tmdb_key),
                    client.get(f"{cinemeta_url}/meta/{type}/{id}.json")
                ]
                metas = await asyncio.gather(*tasks)
                
                if USE_TMDB_ADDON:
                    # TMDB addon retry and switch addon
                    for retry in range(6):
                        if metas[0].status_code == 200:
                            tmdb_meta = metas[0].json()
                            break
                        else:
                            index = tmdb_addons_pool.index(tmdb_addon_meta_url)
                            tmdb_addon_meta_url = tmdb_addons_pool[(index + 1) % len(tmdb_addons_pool)]
                            metas[0] = await client.get(f"{tmdb_addon_meta_url}/meta/{type}/{tmdb_id}.json")
                            if metas[0].status_code == 200:
                                tmdb_meta = metas[0].json()
                                break
                else:
                    tmdb_meta = metas[0]

                if metas[1].status_code == 200:
                    cinemeta_meta = metas[1].json()
                else:
                    cinemeta_meta = {}
                
                # Not empty tmdb meta
                if len(tmdb_meta.get('meta', [])) > 0:
                    # Not merge anime
                    if id not in kitsu.imdb_ids_map:
                        tasks = []
                        meta, merged_videos = meta_merger.merge(tmdb_meta, cinemeta_meta)
                        tmdb_description = tmdb_meta['meta'].get('description', '')
                        
                        if tmdb_description == '':
                            tasks.append(translator.translate_with_api(client, meta['meta'].get('description', ''), language))

                        if type == 'series' and (len(meta['meta']['videos']) < len(merged_videos)):
                            tasks.append(translator.translate_episodes(client, merged_videos, language, tmdb_key))

                        translated_tasks = await asyncio.gather(*tasks)
                        for task in translated_tasks:
                            if isinstance(task, list):
                                meta['meta']['videos'] = task
                            elif isinstance(task, str):
                                meta['meta']['description'] = task
                    else:
                        meta = tmdb_meta

                # Empty tmdb_data
                else:
                    if len(cinemeta_meta.get('meta', [])) > 0:
                        meta = cinemeta_meta
                        description = meta['meta'].get('description', '')
                        
                        if type == 'series':
                            tasks = [
                                translator.translate_with_api(client, description, language, tmdb_key),
                                translator.translate_episodes(client, meta['meta']['videos'], language, tmdb_key)
                            ]
                            description, episodes = await asyncio.gather(*tasks)
                            meta['meta']['videos'] = episodes

                        elif type == 'movie':
                            description = await translator.translate_with_api(client, description, language)

                        meta['meta']['description'] = description
                    
                    # Empty cinemeta and tmdb return empty meta
                    else:
                        return json_response({})
                    
                
            # Handle kitsu and mal ids
            elif 'kitsu' in id or 'mal' in id:
                # Get meta from kitsu addon
                id = id.replace('_',':')
                response = await client.get(f"{kitsu.kitsu_addon_url}/meta/{type}/{id.replace(':','%3A')}.json")
                meta = response.json()

                # Extract imdb id, anime type and check convertion to imdb id
                if 'kitsu' in meta['meta']['id']:
                    imdb_id, is_converted = await kitsu.convert_to_imdb(meta['meta']['id'], meta['meta']['type'])
                elif 'mal_' in meta['meta']['id']:
                    imdb_id, is_converted = await mal.convert_to_imdb(meta['meta']['id'].replace('_',':'), meta['meta']['type'])
                meta['meta']['imdb_id'] = imdb_id
                anime_type = meta['meta'].get('animeType', None)
                is_converted = imdb_id != None and (anime_type == 'TV' or anime_type == 'movie')

                # Handle converted ids (TV and movies)
                if is_converted:
                    if USE_TMDB_ADDON:
                        tmdb_id = await tmdb.convert_imdb_to_tmdb(imdb_id, language, tmdb_key)
                        # TMDB Addons retry
                        for retry in range(6):
                            response = await client.get(f"{tmdb_addon_meta_url}/meta/{type}/{tmdb_id}.json")
                            if response.status_code == 200:
                                meta = response.json()
                                break
                            else:
                                # Loop addon pool
                                index = tmdb_addons_pool.index(tmdb_addon_meta_url)
                                tmdb_addon_meta_url = tmdb_addons_pool[(index + 1) % len(tmdb_addons_pool)]
                                print(f"Switch to {tmdb_addon_meta_url}")
                    else:
                        meta = await meta_builder.build_metadata(imdb_id, type, language, tmdb_key)

                    if len(meta['meta']) > 0:
                        if type == 'movie':
                            meta['meta']['behaviorHints']['defaultVideoId'] = id
                        elif type == 'series':
                            videos = kitsu.parse_meta_videos(meta['meta']['videos'], imdb_id)
                            meta['meta']['videos'] = videos
                    else:
                        # Get meta from kitsu addon
                        response = await client.get(f"{kitsu.kitsu_addon_url}/meta/{type}/{id.replace(':','%3A')}.json")
                        meta = response.json()

                # Handle not corverted and ONA OVA Specials
                else:
                    tasks = []
                    description = meta['meta'].get('description', '')
                    videos = meta['meta'].get('videos', [])

                    if description:
                        tasks.append(translator.translate_with_api(client, description, language))

                    if type == 'series' and videos:
                        tasks.append(translator.translate_episodes_with_api(client, videos, language))

                    translations = await asyncio.gather(*tasks)

                    idx = 0
                    if description:
                        meta['meta']['description'] = translations[idx]
                        idx += 1

                    if type == 'series' and videos:
                        meta['meta']['videos'] = translations[idx]

            # Not compatible id -> redirect to original addon
            else:
                return RedirectResponse(f"{addon_url}/meta/{type}/{id}.json")


            meta['meta']['id'] = id
            meta_cache[language].set(id, meta)
            return json_response(meta)


# Subs redirect
@app.get('/{addon_url}/{user_settings}/subtitles/{path:path}')
async def get_subs(addon_url, path: str):
    addon_url = decode_base64_url(addon_url)
    return RedirectResponse(f"{addon_url}/subtitles/{path}")

# Stream redirect
@app.get('/{addon_url}/{user_settings}/stream/{path:path}')
async def get_subs(addon_url, path: str):
    addon_url = decode_base64_url(addon_url)
    return RedirectResponse(f"{addon_url}/stream/{path}")


# Anime map reloader
@app.get('/map_reload')
async def reload_anime_mapping(password: str = Query(...)):
    if password == ADMIN_PASSWORD:
        await anime_mapping.download_maps()
        kitsu.load_anime_map()
        mal.load_anime_map()
        return json_response({"status": "Anime map updated."})
    else:
        return json_response({"Error": "Access delined"})
    

# Cache expires
@app.get('/clean_cache')
async def clean_cache(password: str = Query(...)):
    if password == ADMIN_PASSWORD:
        tmdb.tmp_cache.expire()
        meta_cache.expire()
        return json_response({"status": "Cache cleaned."})
    else:
        return json_response({"Error": "Access delined"})
    
    
# Toast Translator Logo
@app.get('/favicon.ico')
@app.get('/addon-logo.png')
async def get_poster_placeholder():
    return FileResponse("static/img/toast-translator-logo.png", media_type="image/png")


def decode_base64_url(encoded_url):
    padding = '=' * (-len(encoded_url) % 4)
    encoded_url += padding
    decoded_bytes = base64.b64decode(encoded_url)
    return decoded_bytes.decode('utf-8')


# Anime only
async def remove_duplicates(catalog) -> None:
    unique_items = []
    seen_ids = set()
    
    for item in catalog['metas']:

        # Get imdb id and animetype from catalog data
        anime_type = item.get('animeType', None)
        if 'kitsu' in item['id']:
            imdb_id, is_converted = await kitsu.convert_to_imdb(item['id'], item['type'])
        elif 'mal_' in item['id']:
            imdb_id, is_converted = await mal.convert_to_imdb(item['id'].replace('_',':'), item['type'])
        item['imdb_id'] = imdb_id

        # Add special, ona, ova, movies
        if imdb_id == None or anime_type != 'TV':
            unique_items.append(item)

        # Incorporate seasons
        elif imdb_id not in seen_ids:
            unique_items.append(item)
            seen_ids.add(imdb_id)

    catalog['metas'] = unique_items


def parse_user_settings(user_settings: str) -> dict:
    settings = user_settings.split(',')
    _user_settings = {}

    for setting in settings:
        key, value = setting.split('=')
        _user_settings[key] = value
    
    return _user_settings


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
