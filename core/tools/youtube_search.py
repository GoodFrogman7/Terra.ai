"""
YouTube Video Search Tool
Searches YouTube and returns relevant video suggestions with thumbnails.
"""
import requests
import re
from typing import List, Dict
from urllib.parse import quote_plus


def search_youtube(query: str, max_results: int = 6) -> List[Dict]:
    """
    Search YouTube for videos matching the query.
    Returns list of video metadata (title, url, thumbnail, video_id).
    """
    if not query or not query.strip():
        return []

    try:
        search_query = query
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(search_query)}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        response = requests.get(search_url, headers=headers, timeout=5)  # Short timeout - YouTube is auxiliary
        response.raise_for_status()
        html = response.text

        videos = []
        seen_ids = set()

        # Try to extract from ytInitialData JSON (most reliable)
        json_match = re.search(r'var ytInitialData = ({.*?});</script>', html, re.DOTALL)
        if json_match:
            try:
                import json
                data = json.loads(json_match.group(1))
                contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
                for section in contents:
                    items = section.get('itemSectionRenderer', {}).get('contents', [])
                    for item in items:
                        video = item.get('videoRenderer', {})
                        if video:
                            video_id = video.get('videoId', '')
                            title_runs = video.get('title', {}).get('runs', [])
                            title = title_runs[0].get('text', '') if title_runs else ''
                            if video_id and title and video_id not in seen_ids and len(videos) < max_results:
                                seen_ids.add(video_id)
                                videos.append({
                                    "title": title[:80] + "..." if len(title) > 80 else title,
                                    "url": f"https://youtube.com/watch?v={video_id}",
                                    "video_id": video_id,
                                    "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                                    "thumbnail_hq": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                                })
            except:
                pass

        # Fallback regex patterns if JSON parsing fails
        if len(videos) < max_results:
            # Pattern for videoId and title in JSON structure
            pattern = r'"videoId":"([a-zA-Z0-9_-]{11})","thumbnail".*?"title":\{"runs":\[\{"text":"([^"]+)"\}'
            matches = re.findall(pattern, html)
            for video_id, title in matches:
                if video_id not in seen_ids and len(videos) < max_results:
                    seen_ids.add(video_id)
                    title = title.replace("\\u0026", "&").replace("\\n", " ").strip()
                    if len(title) > 5:
                        videos.append({
                            "title": title[:80] + "..." if len(title) > 80 else title,
                            "url": f"https://youtube.com/watch?v={video_id}",
                            "video_id": video_id,
                            "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                            "thumbnail_hq": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                        })

        return videos

    except Exception as e:
        print(f"[YOUTUBE] Search error: {e}")
        return []


def get_youtube_suggestions_structured(query: str, max_results: int = 6) -> List[Dict]:
    """
    Get YouTube video suggestions as structured data for UI rendering.
    Returns list of video objects with required fields for 6-card layout.
    """
    # Clean query for better results
    clean_query = re.sub(r'^(how to|what is|who is|explain|tell me about)\s+', '', query, flags=re.IGNORECASE)

    videos = search_youtube(clean_query, max_results)

    if not videos:
        return []

    # Return exactly top 6 (or all if <6) with UI-expected schema
    structured = []
    for v in videos[:6]:
        structured.append({
            "video_id": v.get("video_id", ""),
            "title": v.get("title", ""),
            "channel_name": "",  # Not available from scraping, UI should handle gracefully
            "thumbnail_url": v.get("thumbnail", ""),
            "video_url": v.get("url", ""),
        })

    return structured


if __name__ == "__main__":
    # Test
    result = search_youtube("personal finance budgeting tips", 6)
    for v in result:
        print(f"{v['title']}\n  {v['url']}\n  {v['thumbnail']}\n")
