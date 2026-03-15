from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

video_id = "m8WdKlWMgvQ"

print(f"Checking subtitles for {video_id}...")

try:
    # Intentionally ask for a non-existent language to trigger the error
    # The error message content is what we want -- it lists available transcripts!
    YouTubeTranscriptApi.get_transcript(video_id, languages=['xz'])
    print("Found 'xz' transcript (unexpected).")
except NoTranscriptFound as e:
    print("\n--- Available Transcripts found in Error ---")
    print(e)
except TranscriptsDisabled:
    print("\n--- Transcripts are DISABLED for this video ---")
except Exception as e:
    print(f"\n--- Other Error: {type(e)} ---")
    print(e)
