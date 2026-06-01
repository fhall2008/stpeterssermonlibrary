import xml.etree.ElementTree as ET
import json, re
from datetime import datetime

NS = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

tree = ET.parse('feed-fa.xml')
root = tree.getroot()
channel_el = root.find('channel')

# Channel artwork
channel_image = ''
ch_img = channel_el.find('image')
if ch_img is not None:
    url_el = ch_img.find('url')
    if url_el is not None:
        channel_image = (url_el.text or '').strip()
itunes_ch_img = channel_el.find('itunes:image', NS)
if itunes_ch_img is not None:
    channel_image = itunes_ch_img.get('href', channel_image)

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
    raw_html  = gi('summary') or gt('description')
    desc      = re.sub(r'<[^>]+>', ' ', raw_html).strip()

    ep_img = item.find('itunes:image', NS)
    image  = ep_img.get('href', '') if ep_img is not None else ''

    items.append({
        'id':          idx,
        'title':       title,
        'titleSeries': title_series,
        'desc':        desc,
        'rawHtml':     raw_html,
        'pubDate':     gt('pubDate'),
        'audioUrl':    audio_url,
        'link':        gt('link'),
        'duration':    gi('duration'),
        'speaker':     gi('author'),
        'image':       image,
        'videoUrl':    '',
        'videoId':     '',
    })

output = {
    'channelImage': channel_image,
    'items':        items,
    'updated':      datetime.utcnow().isoformat() + 'Z',
}

with open('feed-fa.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False)

print(f'Saved {len(items)} Farsi sermons to feed-fa.json')
