import yt_dlp
import json

video_id = "m8WdKlWMgvQ"
url = f"https://www.youtube.com/watch?v={video_id}"

ydl_opts = {
    'skip_download': True,
    'writeautomaticsub': True,
    'writesubtitles': True,
    'subtitleslangs': ['ko', 'en'],
    'quiet': True,
    'no_warnings': True,
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        subtitles = info.get('subtitles', {})
        auto_captions = info.get('automatic_captions', {})
        
        print("Subtitles:", list(subtitles.keys()))
        print("Auto Captions:", list(auto_captions.keys()))
        
        if 'ko' in auto_captions:
            print("Korean auto-caption found!")
            print("URL sample:", auto_captions['ko'][0]['url'][:100])
        else:
            print("Korean auto-caption NOT found.")
            
except Exception as e:
    print("Error:", e)
