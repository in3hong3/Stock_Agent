import yt_dlp

def get_video_info(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title'),
                'description': info.get('description'),
                'upload_date': info.get('upload_date'),
            }
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    print(get_video_info("m8WdKlWMgvQ"))
