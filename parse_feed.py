import xml.etree.ElementTree as ET
import json, re, os, urllib.request, urllib.parse
from datetime import datetime

NS = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

YOUTUBE_API_KEY    = os.environ.get('YOUTUBE_API_KEY', '')
YOUTUBE_HANDLE     = '@StPetersHornsby'

# Anchor/Spotify auto-uploads podcast audio as YouTube videos.
# These are NOT real sermon videos — they're static image + audio.
# We detect them by checking the video's own channel vs the church channel,
# and by matching duration within a tolerance of the podcast episode.
DURATION_TOLERANCE_SECONDS = 120   # allow 2 min difference for intro/outro

def iso8601_to_seconds(d):
    """Convert YouTube ISO 8601 duration (PT1H2M3S) to seconds."""
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', d or '')
    if not m: return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + s

def duration_str_to_seconds(d):
    """Convert HH:MM:SS or MM:SS podcast duration to seconds."""
    if not d: return 0
    parts = d.strip().split(':')
    try:
        parts = [int(p) for p in parts]
        if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2: return parts[0]*60 + parts[1]
        return parts[0]
    except: return 0

def resolve_channel_id(api_key):
    url = ('https://www.googleapis.com/youtube/v3/search'
           '?part=snippet&type=channel&q=' + urllib.parse.quote(YOUTUBE_HANDLE) +
           '&maxResults=1&key=' + api_key)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        items = data.get('items', [])
        if items:
            return items[0]['snippet']['channelId']
    except Exception as e:
        print(f'  Warning: could not resolve channel ID: {e}')
    return None

def search_youtube(api_key, channel_id, query, podcast_duration_secs):
    """
    Search the church YouTube channel for a real sermon video.
    Returns (video_url, video_id) or ('', '') if no genuine match found.
    """
    # Step 1: search for candidates
    params = urllib.parse.urlencode({
        'part': 'snippet',
        'channelId': channel_id,
        'q': query,
        'type': 'video',
        'maxResults': 5,          # get a few to filter
        'key': api_key,
    })
    try:
        with urllib.request.urlopen('https://www.googleapis.com/youtube/v3/search?' + params, timeout=10) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f'    Search error: {e}')
        return '', ''

    candidates = data.get('items', [])
    if not candidates:
        return '', ''

    # Step 2: fetch video details (duration + channel) for all candidates
    vid_ids = ','.join(i['id']['videoId'] for i in candidates)
    detail_params = urllib.parse.urlencode({
        'part': 'contentDetails,snippet',
        'id': vid_ids,
        'key': api_key,
    })
    try:
        with urllib.request.urlopen('https://www.googleapis.com/youtube/v3/videos?' + detail_params, timeout=10) as r:
            detail_data = json.loads(r.read())
    except Exception as e:
        print(f'    Detail fetch error: {e}')
        return '', ''

    for video in detail_data.get('items', []):
        vid_id   = video['id']
        vid_ch   = video['snippet']['channelId']
        duration = iso8601_to_seconds(video['contentDetails']['duration'])
        title    = video['snippet']['title']

        # Must be on the church channel (not Spotify's auto-upload channel)
        if vid_ch != channel_id:
            print(f'    Skipping "{title}" — wrong channel')
            continue

        # Skip very short videos (< 5 min) — likely not a sermon
        if duration < 300:
            print(f'    Skipping "{title}" — too short ({duration}s)')
            continue

        # Skip Spotify/Anchor auto-uploads:
        # They typically say "... on Spotify" or "Anchor" in the title/description
        desc_lower = video['snippet'].get('description', '').lower()
        title_lower = title.lower()
        if any(kw in desc_lower for kw in ['spotify', 'anchor.fm', 'automatically uploaded']):
            print(f'    Skipping "{title}" — looks like Spotify auto-upload')
            continue

        # If we have a podcast duration, check it's within tolerance
        # Real videos tend to be longer (have intro/outro/worship) or similar
        if podcast_duration_secs > 0:
            diff = abs(duration - podcast_duration_secs)
            # Allow up to DURATION_TOLERANCE_SECONDS difference OR video is longer
            # (church may include extra content in video version)
            if diff > DURATION_TOLERANCE_SECONDS and duration < podcast_duration_secs:
                print(f'    Skipping "{title}" — duration mismatch ({duration}s vs podcast {podcast_duration_secs}s)')
                continue

        print(f'    Matched: "{title}" ({duration}s)')
        return f'https://www.youtube.com/watch?v={vid_id}', vid_id

    return '', ''

# ── Parse RSS ──────────────────────────────────────────────────────────────
tree = ET.parse('feed.xml')
root = tree.getroot()
channel = root.find('channel')

# Channel artwork
channel_image = ''
ch_img = channel.find('image')
if ch_img is not None:
    url_el = ch_img.find('url')
    if url_el is not None:
        channel_image = (url_el.text or '').strip()
itunes_ch_img = channel.find('itunes:image', NS)
if itunes_ch_img is not None:
    channel_image = itunes_ch_img.get('href', channel_image)

# ── Resolve YouTube channel ID ─────────────────────────────────────────────
yt_channel_id = None
if YOUTUBE_API_KEY:
    print(f'Resolving YouTube channel ID for {YOUTUBE_HANDLE}...')
    yt_channel_id = resolve_channel_id(YOUTUBE_API_KEY)
    if yt_channel_id:
        print(f'  Channel ID: {yt_channel_id}')
    else:
        print('  Could not resolve — YouTube search skipped')
else:
    print('No YOUTUBE_API_KEY — skipping YouTube search')

# ── Load cached video matches from existing feed.json ─────────────────────
cached_videos = {}
try:
    with open('feed.json') as f:
        old = json.load(f)
    for item in old.get('items', []):
        if item.get('videoId'):
            cached_videos[item['title']] = {
                'videoUrl': item.get('videoUrl', ''),
                'videoId':  item.get('videoId', ''),
            }
    print(f'Loaded {len(cached_videos)} cached video matches')
except Exception:
    pass

# ── Parse items ───────────────────────────────────────────────────────────
items = []
for idx, item in enumerate(channel.findall('item')):
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

    podcast_secs = duration_str_to_seconds(duration)

    # YouTube match — use cache or search
    video_url = ''
    video_id  = ''
    if title in cached_videos:
        video_url = cached_videos[title]['videoUrl']
        video_id  = cached_videos[title]['videoId']
        print(f'  Cached: {title}')
    elif yt_channel_id and YOUTUBE_API_KEY:
        print(f'Searching YouTube: "{title}"')
        video_url, video_id = search_youtube(YOUTUBE_API_KEY, yt_channel_id, title, podcast_secs)

    items.append({
        'id':          idx,
        'title':       title,
        'titleSeries': title_series,
        'desc':        desc,
        'pubDate':     gt('pubDate'),
        'audioUrl':    audio_url,
        'link':        gt('link'),
        'duration':    duration,
        'speaker':     gi('author'),
        'image':       image,
        'videoUrl':    video_url,
        'videoId':     video_id,
    })

output = {
    'channelImage': channel_image,
    'items':        items,
    'updated':      datetime.utcnow().isoformat() + 'Z',
}

with open('feed.json', 'w') as f:
    json.dump(output, f)

matched = sum(1 for i in items if i['videoId'])
print(f'\nDone. {len(items)} sermons, {matched} YouTube matches.')
