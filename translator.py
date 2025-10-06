from cache import Cache
import api.tmdb as tmdb
import urllib.parse
import asyncio
import httpx
import json
import os

# Cache set
#translations_cache = Cache(maxsize=float('inf'), ttl=float('inf'))
translations_cache = Cache('./cache/translation/tmp')
translations_cache.clear()

# Load languages
with open("languages.json", "r", encoding="utf-8") as f:
    LANGUAGES = json.load(f) 

# Cache set
translations_cache = {}
for language in LANGUAGES:
    translations_cache[language] = Cache(f"./cache/{language}/translation/tmp")
    translations_cache[language].clear()

# Poster ratings
RATINGS_SERVER = os.getenv('TR_SERVER', 'https://ca6771aaa821-toast-ratings.baby-beamup.club')

# Language flags converter
LANGUAGE_FLAGS = {
    "it-IT": "🇮🇹",
    "es-ES": "🇪🇸",
    "fr-FR": "🇫🇷",
    "de-DE": "🇩🇪",
    "pt-PT": "🇵🇹",
    "pt-BR": "🇧🇷",
    "ru-RU": "🇷🇺",
    "ja-JP": "🇯🇵",
    "zh-CN": "🇨🇳",
    "ko-KR": "🇰🇷",
    "ar-SA": "🇸🇦",
    "hi-IN": "🇮🇳"
}

# For metabuilder
EPISODE_TRANSLATIONS = {
    "it-IT": "Episodio",
    "es-ES": "Episodio",
    "fr-FR": "Épisode",
    "de-DE": "Episode",
    "pt-PT": "Episódio",
    "pt-BR": "Episódio",
    "ru-RU": "Эпизод",
    "ja-JP": "エピソード",
    "zh-CN": "集",
    "ko-KR": "에피소드",
    "ar-SA": "حلقة",
    "hi-IN": "एपिसोड"
}


async def translate_with_api(client: httpx.AsyncClient, text: str, language: str, source='en') -> str:

    translation = translations_cache[language].get(text)
    target = language.split('-')[0]
    if translation == None and text != None and text != '':
        api_url = f"https://lingva-translate-azure.vercel.app/api/v1/{source}/{target}/{urllib.parse.quote(text)}"

        response = await client.get(api_url)
        translated_text = response.json().get('translation', '')
        translations_cache[language].set(text, translated_text)
    else:
        translated_text = translation

    return translated_text


async def translate_episodes_with_api(client: httpx.AsyncClient, episodes: list[dict], language: str):
    tasks = []

    for episode in episodes:
        tasks.append(translate_with_api(client, episode.get('title', ''), language)),
        tasks.append(translate_with_api(client, episode.get('overview', ''), language))

    translations = await asyncio.gather(*tasks)

    for i, episode in enumerate(episodes):
        episode['title'] = translations[2 * i]
        episode['overview'] = translations[2 * i + 1]

    return episodes


def translate_catalog(original: dict, tmdb_meta: dict, skip_poster, toast_ratings, language: str) -> dict:
    new_catalog = original

    for i, item in enumerate(new_catalog['metas']):
        try:
            type = item['type']
            type_key = 'movie' if type == 'movie' else 'tv'
            detail = tmdb_meta[i][f"{type_key}_results"][0]
        except:
            # Set poster if contend not have tmdb informations
            if toast_ratings == '1':
                if 'tt' in tmdb_meta[i].get('imdb_id', ''):
                    item['poster'] = f"{RATINGS_SERVER}/{item['type']}/get_poster/{tmdb_meta[i]['imdb_id']}.jpg"

        else:
            try: item['name'] = detail['title'] if type == 'movie' else detail['name']
            except: pass

            try: item['description'] = detail['overview']
            except: pass

            try: item['background'] = tmdb.TMDB_BACK_URL + detail['backdrop_path']
            except: pass

            if skip_poster == '0':
                try: 
                    if toast_ratings == '1':
                        item['poster'] = f"{RATINGS_SERVER}/{item['type']}/get_poster/{language}/{tmdb_meta[i]['imdb_id']}.jpg"
                    else:
                        item['poster'] = tmdb.TMDB_POSTER_URL + detail['poster_path']
                except Exception as e: 
                    print(e)

    return new_catalog


async def translate_episodes(client: httpx.AsyncClient, original_episodes: list[dict], language: str, tmdb_key: str):
    translate_index = []
    tasks = []
    new_episodes = original_episodes

    # Select not translated episodes
    for i, episode in enumerate(original_episodes):
        if 'tvdb_id' in episode:
            tasks.append(tmdb.get_tmdb_data(client, episode['tvdb_id'], "tvdb_id", language, tmdb_key))
            translate_index.append(i)

    translations = await asyncio.gather(*tasks)

    # Translate episodes 
    for i, t_index in enumerate(translate_index):
        try: detail = translations[i][f"tv_episode_results"][0]
        except: pass
        else:
            try: new_episodes[t_index]['name'] = detail['name']
            except: pass
            try: new_episodes[t_index]['overview'] = detail['overview']
            except: pass
            try: new_episodes[t_index]['description'] = detail['overview']
            except: pass
            try: new_episodes[t_index]['thumbnail'] = tmdb.TMDB_BACK_URL + detail['still_path']
            except: pass

    return new_episodes
