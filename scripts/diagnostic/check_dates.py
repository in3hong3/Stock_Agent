from main import YouTubeManager
import os
from dotenv import load_dotenv

load_dotenv()

yt = YouTubeManager(os.getenv('YOUTUBE_API_KEY'))
videos = yt.get_videos_in_range('UCwSSqi-s0wcH6pJbH3YPZqQ', '2026-01-01', None, max_results=100)

print(f'Total: {len(videos)} videos')
print()
print('First 5:')
for i, v in enumerate(videos[:5]):
    print(f'{i+1}. {v["publish_time"]} - {v["title"][:50]}')

print()
print('Last 5:')
for i, v in enumerate(videos[-5:]):
    print(f'{len(videos)-4+i}. {v["publish_time"]} - {v["title"][:50]}')
