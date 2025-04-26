from cache import Cache
from datetime import timedelta
import httpx
import anime.anime_mapping as anime_mapping

kitsu_addon_url = 'https://anime-kitsu.strem.fun'

# Cache load
kitsu_cache = Cache(maxsize=float('inf'), ttl=timedelta(days=30).total_seconds())
kitsu_cache.clear()

# Load kitsu -> imdb converter
imdb_map = anime_mapping.load_kitsu_map()
for kitsu_id, imdb_id in imdb_map.items():
	kitsu_cache.set(f"kitsu:{kitsu_id}", imdb_id)

# Load season / episode map
imdb_ids_map = anime_mapping.load_imdb_map()


async def convert_to_imdb(kitsu_id: str, type: str) -> str:
	is_converted = False
	imdb_id = kitsu_cache.get(kitsu_id)
	if imdb_id == None:
		async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
			response = await client.get(f"{kitsu_addon_url}/meta/{type}/{kitsu_id.replace(':','%3A')}.json")
			try:
				imdb_id = response.json()['meta']['imdb_id']
				kitsu_cache.set(kitsu_id, imdb_id)
				is_converted = True
			except:
				# If imdb_id not found save kitsu_id as imdb_id (better performance)
				kitsu_cache.set(kitsu_id, kitsu_id)
				return kitsu_id, is_converted
	else:
		is_converted = True

	return imdb_id, is_converted


def parse_meta_videos(videos: dict, imdb_id: str) -> dict:
	kitsu_ids = imdb_ids_map[imdb_id]['kitsu_ids']
	special_offset = 0
	videos = sorted(videos, key=lambda x: (x["season"], x["episode"]))
	
	for i, video in enumerate(videos):
		if video['season'] != 0:
			for item in kitsu_ids:
				kitsu_id = next(iter(item.keys()))
				if (item[kitsu_id]['season'] == video['season'] or item[kitsu_id]['season'] == -1) and item[kitsu_id]['epoffset'] < video['episode']:
					if item[kitsu_id]['season'] == -1:
						videos[i]['id'] = f"kitsu:{kitsu_id}:{(i - special_offset) + 1}"
					else:
						videos[i]['id'] = f"kitsu:{kitsu_id}:{video['episode'] - item[kitsu_id]['epoffset']}"
		else:
			special_offset += 1

	return videos




"""
Esempio Attacco dei giganti

{
	"kitsu_ids":[
		{
			"7442":{
				"season":1,
				"epoffset":0
			}
		},
		{
			"8671":{
				"season":2,
				"epoffset":0
			}
		},
		{
			"13569":{
				"season":3,
				"epoffset":0
			}
		},
		{
			"41982":{
				"season":3,
				"epoffset":12
			}
		},
		{
			"42422":{
				"season":4,
				"epoffset":0
			}
		},
		{
			"46038":{
				"season":4,
				"epoffset":28
			}
		},
		{
			"44240":{
				"season":4,
				"epoffset":16
			}
		}
	],
	"anidb_ids":[
		"9541",
		"10944",
		"13241",
		"14444",
		"14977",
		"17303",
		"16177"
	],
	"mal_ids":[
		"16498",
		"25777",
		"35760",
		"38524",
		"40028",
		"51535",
		"48583"
	]
}
"""
