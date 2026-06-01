import xml.etree.ElementTree as ET
import json, re
from datetime import datetime

NS = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}

tree = ET.parse('feed.xml')
root = tree.getroot()
channel = root.find('channel')

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
    })

output = {
    'items': items,
    'updated': datetime.utcnow().isoformat() + 'Z'
}

with open('feed.json', 'w') as f:
    json.dump(output, f)

print(f'Saved {len(items)} sermons to feed.json')
