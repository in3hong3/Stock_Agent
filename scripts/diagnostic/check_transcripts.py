from youtube_transcript_api import YouTubeTranscriptApi
import json

video_id = "dQw4w9WgXcQ"
print(f"Testing transcript for {video_id}")

try:
    if hasattr(YouTubeTranscriptApi, 'get_transcript'):
        print("Using static get_transcript")
        t = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
    else:
        print("Using instance list().fetch()")
        api = YouTubeTranscriptApi()
        t = api.list(video_id).find_transcript(['ko', 'en']).fetch()
        
    print("Success. First 100 chars:", " ".join([item.get('text', item.get('utf8', '')) for item in t])[:100])
except Exception as e:
    print("Error:", e)
