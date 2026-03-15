import youtube_transcript_api
print(f"Module: {youtube_transcript_api}")
print(f"Dir of module: {dir(youtube_transcript_api)}")
if hasattr(youtube_transcript_api, 'YouTubeTranscriptApi'):
    print(f"YouTubeTranscriptApi class: {youtube_transcript_api.YouTubeTranscriptApi}")
    print(f"Dir of class: {dir(youtube_transcript_api.YouTubeTranscriptApi)}")
else:
    print("YouTubeTranscriptApi NOT found in module")
