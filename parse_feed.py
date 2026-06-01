import xml.etree.ElementTree as ET
import json, re, os, urllib.request, urllib.parse
from datetime import datetime

NS = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

YOUTUBE_API_KEY      = os.environ.get('YOUTUBE_API_KEY', '')
YOUTUBE_HANDLE       = '@StPetersHornsby'
EXCLUDE_PLAYLIST_ID  = 'PLHaDvAO4RKLLgYFLSYeFAaAwpNDURh-ml'  # audiogram/RSS uploads

def iso8601_to_seconds(d):
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', d or '')
    if not m: return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + s

def duration_str_to_seconds(d):
    if not d: return 0
    parts = d.strip().split(':')
    try:
        parts = [int(p) for p in parts]
        if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2: return parts[0]*60 + parts[1]
        return parts[0]
    except: return 0

def api_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())

def resolve_channel_id(api_key):
    url = ('https://www.googleapis.com/youtube/v3/search'
           '?part=snippet&type=channel&q=' + urllib.parse.quote(YOUTUBE_HANDLE) +
           '&maxResults=1&key=' + api_key)
    try:
        items = api_get(url).get('items', [])
        if items:
            return items[0]['snippet']['channelId']
    except Exception as e:
        print(f'  Warning: could not resolve channel ID: {e}')
    return None

def get_excluded_video_ids(api_key, playlist_id):
    """Fetch all video IDs from the exclusion playlist (handles pagination)."""
    excluded = set()
    page_token = ''
    while True:
        params = urllib.parse.urlencode({
            'part': 'contentDetails',
            'playlistId': playlist_id,
            'maxResults': 50,
            'key': api_key,
            **({'pageToken': page_token} if page_token else {}),
        })
        try:
            data = api_get('https://www.googleapis.com/youtube/v3/playlistItems?' + params)
        except Exception as e:
            print(f'  Warning: could not fetch exclusion playlist: {e}')
            break
        for item in data.get('items', []):
            vid_id = item['contentDetails'].get('videoId')
            if vid_id:
                excluded.add(vid_id)
        page_token = data.get('nextPageToken', '')
        if not page_token:
            break
    return excluded

def search_youtube(api_key, channel_id, query, excluded_ids):
    """Search channel for a real sermon video, skipping any in the exclusion playlist."""
    params = urllib.parse.urlencode({
        'part': 'snippet',
        'channelId': channel_id,
        'q': query,
        'type': 'video',
        'maxResults': 5,
        'key': api_key,
    })
    try:
        candidates = api_get('https://www.googleapis.com/youtube/v3/search?' + params).get('items', [])
    except Exception as e:
        print(f'    Search error: {e}')
        return '', ''

    if not candidates:
        return '', ''

    vid_ids = ','.join(i['id']['videoId'] for i in candidates)
    detail_params = urllib.parse.urlencode({
        'part': 'snippet,contentDetails',
        'id': vid_ids,
        'key': api_key,
    })
    try:
        videos = api_get('https://www.googleapis.com/youtube/v3/videos?' + detail_params).get('items', [])
    except Exception as e:
        print(f'    Detail fetch error: {e}')
        return '', ''

    for video in videos:
        vid_id   = video['id']
        title    = video['snippet']['title']
        duration = iso8601_to_seconds(video['contentDetails']['duration'])

        # Skip if in the excluded playlist
        if vid_id in excluded_ids:
            print(f'    Skipping (in excluded playlist): "{title}"')
            continue

        # Skip anything under 5 minutes
        if duration < 300:
            print(f'    Skipping short video: "{title}" ({duration}s)')
            continue

        print(f'    Matched: "{title}" ({duration}s)')
        return f'https://www.youtube.com/watch?v={vid_id}', vid_id

    return '', ''

# ── Parse RSS ─────────────────────────────────────────────────────────────
tree = ET.parse('feed.xml')
root = tree.getroot()
channel_el = root.find('channel')

channel_image = ''
ch_img = channel_el.find('image')
if ch_img is not None:
    url_el = ch_img.find('url')
    if url_el is not None:
        channel_image = (url_el.text or '').strip()
itunes_ch_img = channel_el.find('itunes:image', NS)
if itunes_ch_img is not None:
    channel_image = itunes_ch_img.get('href', channel_image)

# ── Setup YouTube ─────────────────────────────────────────────────────────
yt_channel_id = None
excluded_ids  = set()

if YOUTUBE_API_KEY:
    print(f'Resolving YouTube channel for {YOUTUBE_HANDLE}...')
    yt_channel_id = resolve_channel_id(YOUTUBE_API_KEY)
    if yt_channel_id:
        print(f'  Channel ID: {yt_channel_id}')
        print(f'Fetching exclusion playlist ({EXCLUDE_PLAYLIST_ID})...')
        excluded_ids = get_excluded_video_ids(YOUTUBE_API_KEY, EXCLUDE_PLAYLIST_ID)
        print(f'  {len(excluded_ids)} videos will be excluded')
    else:
        print('  Could not resolve channel — YouTube skipped')
else:
    print('No YOUTUBE_API_KEY — skipping YouTube search')

# ── Load cached matches ───────────────────────────────────────────────────
cached_videos = {}
try:
    with open('feed.json') as f:
        old = json.load(f)
    for item in old.get('items', []):
        if item.get('videoId'):
            # Only keep cache entry if it's not in the exclusion playlist
            if item['videoId'] not in excluded_ids:
                cached_videos[item['title']] = {
                    'videoUrl': item.get('videoUrl', ''),
                    'videoId':  item.get('videoId', ''),
                }
    print(f'Loaded {len(cached_videos)} cached video matches')
except Exception:
    pass

# ── Parse items ───────────────────────────────────────────────────────────
items = []
for idx, item in enumerate(channel_el.findall('item')):
    def gt(tag):
        el = item.find(tag)
        return (el.text or '').strip() if el is not None else ''
    def gi(tag):
        el = item.find('itunes:' + tag, NS)
        return (el.text or '').strip() if el is not None else ''

    raw_title    = gt('title')
    pipe_parts   = raw_title.split('|')
    title        = pipe_parts[0].strip()
    title_series = pipe_parts[-1].strip() if len(pipe_parts) > 1 else ''

    enc       = item.find('enclosure')
    audio_url = enc.get('url', '') if enc is not None else ''
    desc      = re.sub(r'<[^>]+>', '', gi('summary') or gt('description')).strip()
    duration  = gi('duration')
    ep_img    = item.find('itunes:image', NS)
    image     = ep_img.get('href', '') if ep_img is not None else ''

    video_url = ''
    video_id  = ''
    if title in cached_videos:
        video_url = cached_videos[title]['videoUrl']
        video_id  = cached_videos[title]['videoId']
    elif yt_channel_id and YOUTUBE_API_KEY:
        print(f'Searching YouTube: "{title}"')
        video_url, video_id = search_youtube(
            YOUTUBE_API_KEY, yt_channel_id, title, excluded_ids
        )

    items.append({
        'id': idx, 'title': title, 'titleSeries': title_series,
        'desc': desc, 'pubDate': gt('pubDate'),
        'audioUrl': audio_url, 'link': gt('link'),
        'duration': duration, 'speaker': gi('author'),
        'image': image, 'videoUrl': video_url, 'videoId': video_id,
    })

output = {
    'channelImage': channel_image,
    'items': items,
    'updated': datetime.utcnow().isoformat() + 'Z',
}

with open('feed.json', 'w') as f:
    json.dump(output, f)

matched = sum(1 for i in items if i['videoId'])
print(f'\nDone. {len(items)} sermons, {matched} real YouTube videos matched.')
