import xml.etree.ElementTree as ET
import json, re
from datetime import datetime

NS = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

tree = ET.parse('feed.xml')
root = tree.getroot()
channel = root.find('channel')

# Channel-level artwork (fallback for all episodes)
channel_image = ''
ch_img = channel.find('image')
if ch_img is not None:
    url_el = ch_img.find('url')
    if url_el is not None:
        channel_image = (url_el.text or '').strip()
# iTunes channel art (higher res, takes priority)
itunes_ch_img = channel.find('itunes:image', NS)
if itunes_ch_img is not None:
    channel_image = itunes_ch_img.get('href', channel_image)

items = []
for idx, item in enumerate(channel.findall('item')):
    def gt(tag):
        el = item.find(tag)
        return (el.text or '').strip() if el is not None else ''

    def gi(tag):
        el = item.find('itunes:' + tag, NS)
        return (el.text or '').strip() if el is not None else ''

    raw_title = gt('title')
    pipe_parts = raw_title.split('|')
    title = pipe_parts[0].strip()
    title_series = pipe_parts[-1].strip() if len(pipe_parts) > 1 else ''

    enc = item.find('enclosure')
    audio_url = enc.get('url', '') if enc is not None else ''

    desc = re.sub(r'<[^>]+>', '', gi('summary') or gt('description')).strip()

    # Episode-level artwork (itunes:image href attr)
    episode_image = ''
    ep_img = item.find('itunes:image', NS)
    if ep_img is not None:
        episode_image = ep_img.get('href', '')

    items.append({
        'id': idx,
        'title': title,
        'titleSeries': title_series,
        'desc': desc,
        'pubDate': gt('pubDate'),
        'audioUrl': audio_url,
        'link': gt('link'),
        'duration': gi('duration'),
        'speaker': gi('author'),
        'image': episode_image,   # episode-specific art (may be empty)
    })

output = {
    'channelImage': channel_image,  # podcast cover art
    'items': items,
    'updated': datetime.utcnow().isoformat() + 'Z'
}

with open('feed.json', 'w') as f:
    json.dump(output, f)

has_ep_art = sum(1 for i in items if i['image'])
print(f'Saved {len(items)} sermons. Channel art: {"yes" if channel_image else "no"}. Episode art: {has_ep_art}/{len(items)}')
