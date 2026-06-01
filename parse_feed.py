import xml.etree.ElementTree as ET
import json, re, os, urllib.request, urllib.parse
from datetime import datetime

NS = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

YOUTUBE_API_KEY    = os.environ.get('YOUTUBE_API_KEY', '')
YOUTUBE_HANDLE     = '@StPetersHornsby'
SERMON_PLAYLIST_ID = 'PLHaDvAO4RKLI3ffTMQHlhStmJVCrywJxt'  # real sermon videos only

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
        print(f'  Warning: {e}')
    return None

def get_playlist_videos(api_key, playlist_id):
    """Fetch all videos from the sermon playlist. Returns {title_lower: video_id}."""
    videos = {}
    page_token = ''
    while True:
        params = urllib.parse.urlencode({
            'part': 'snippet',
            'playlistId': playlist_id,
            'maxResults': 50,
            'key': api_key,
            **({'pageToken': page_token} if page_token else {}),
        })
        try:
            data = api_get('https://www.googleapis.com/youtube/v3/playlistItems?' + params)
        except Exception as e:
            print(f'  Warning: playlist fetch error: {e}')
            break
        for item in data.get('items', []):
            snip   = item['snippet']
            vid_id = snip['resourceId']['videoId']
            title  = snip['title'].strip()
            videos[vid_id] = title
        page_token = data.get('nextPageToken', '')
        if not page_token:
            break
    return videos

def best_match(query, playlist_videos):
    """
    Find the best matching video in the playlist for a given sermon title.
    Strips common suffixes/prefixes and does a fuzzy word-overlap match.
    Returns (video_url, video_id) or ('', '').
    """
    def normalise(s):
        s = s.lower()
        s = re.sub(r'\|.*', '', s)          # remove series part after pipe
        s = re.sub(r'[^\w\s]', ' ', s)     # strip punctuation
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    q_words = set(normalise(query).split())
    # Remove very common words that would cause false matches
    stopwords = {'the','a','an','of','in','on','at','to','and','or','is','it','be','as','by','for','with','this','that','from','we','our','his','her','my','your'}
    q_words -= stopwords

    if not q_words:
        return '', ''

    best_score = 0
    best_id    = ''
    best_title = ''

    for vid_id, title in playlist_videos.items():
        t_words = set(normalise(title).split()) - stopwords
        if not t_words:
            continue
        overlap = len(q_words & t_words)
        # Jaccard similarity
        score = overlap / len(q_words | t_words)
        if score > best_score:
            best_score = score
            best_id    = vid_id
            best_title = title

    # Only accept if similarity is high enough
    if best_score >= 0.3:
        print(f'    Matched "{best_title}" (score {best_score:.2f})')
        return f'https://www.youtube.com/watch?v={best_id}', best_id

    print(f'    No match found (best score {best_score:.2f})')
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

# ── Load sermon playlist ──────────────────────────────────────────────────
playlist_videos = {}
if YOUTUBE_API_KEY:
    print(f'Fetching sermon playlist ({SERMON_PLAYLIST_ID})...')
    playlist_videos = get_playlist_videos(YOUTUBE_API_KEY, SERMON_PLAYLIST_ID)
    print(f'  {len(playlist_videos)} videos in playlist')
else:
    print('No YOUTUBE_API_KEY — skipping YouTube matching')

# ── Load cached matches ───────────────────────────────────────────────────
cached_videos = {}
try:
    with open('feed.json') as f:
        old = json.load(f)
    # Only keep cache entries whose video ID is still in the playlist
    playlist_ids = set(playlist_videos.keys())
    for item in old.get('items', []):
        vid_id = item.get('videoId', '')
        if vid_id and (not playlist_ids or vid_id in playlist_ids):
            cached_videos[item['title']] = {
                'videoUrl': item.get('videoUrl', ''),
                'videoId':  vid_id,
            }
    print(f'Loaded {len(cached_videos)} cached matches')
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
    # Keep raw HTML so the browser can parse structured fields (Speaker:, Series:, Service:)
    raw_desc  = gi('summary') or gt('description')
    desc      = re.sub(r'<[^>]+>', ' ', raw_desc).strip()
    raw_html  = raw_desc  # passed to feed.json for JS extraction
    duration  = gi('duration')
    ep_img    = item.find('itunes:image', NS)
    image     = ep_img.get('href', '') if ep_img is not None else ''

    video_url = ''
    video_id  = ''
    if title in cached_videos:
        video_url = cached_videos[title]['videoUrl']
        video_id  = cached_videos[title]['videoId']
        print(f'Cached: "{title}"')
    elif playlist_videos:
        print(f'Matching: "{title}"')
        video_url, video_id = best_match(title, playlist_videos)

    items.append({
        'id': idx, 'title': title, 'titleSeries': title_series,
        'desc': desc, 'pubDate': gt('pubDate'),
        'audioUrl': audio_url, 'link': gt('link'),
        'duration': duration, 'speaker': gi('author'),
        'image': image, 'videoUrl': video_url, 'videoId': video_id, 'rawHtml': raw_html,
    })

output = {
    'channelImage': channel_image,
    'items': items,
    'updated': datetime.utcnow().isoformat() + 'Z',
}

with open('feed.json', 'w') as f:
    json.dump(output, f)

matched = sum(1 for i in items if i['videoId'])
print(f'\nDone. {len(items)} sermons, {matched} matched to playlist videos.')
