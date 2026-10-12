# publish_talk.py
#
# Automates publishing a General Conference Talk to Wordpress

import sys
import re
import io
import json
import requests
from bs4 import BeautifulSoup
from PIL import Image

# ==========================================
# CONFIGURATION
# ==========================================
from wordPressSecrets import WP_URL, WP_USERNAME, WP_APP_PASSWORD

# Custom taxonomy/fields used by Seriously Simple Podcasting
# Standard RSS media enclosures use '_ss_podcasting_audio_file'
SSP_POST_TYPE = "podcast"  
SERIES_NAME = "General Conference"
# ==========================================

def clean_text(text: str) -> str:
    """Removes UTF-8 non-breaking space artifacts (like 'Â') and normalizes whitespace."""
    if not text:
        return ""
    # Replace non-breaking space Unicode character (\xa0) and rogue 'Â' characters
    text = text.replace('\xa0', ' ').replace('Â', '')
    # Collapse multiple spaces into a single space
    return re.sub(r'\s+', ' ', text).strip()

def process_and_crop_image(img_url: str, min_size: int = 300) -> bytes:
    """Downloads image, crops it into a square centered on the speaker, and resizes."""
    res = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"})
    res.raise_for_status()

    img = Image.open(io.BytesIO(res.content)).convert("RGB")
    width, height = img.size

    # Centered square crop
    square_size = min(width, height)
    left = (width - square_size) // 2
    top = (height - square_size) // 2
    right = left + square_size
    bottom = top + square_size

    cropped = img.crop((left, top, right, bottom))

    # Resize to at least min_size x min_size for podcast RSS standard feeds
    target_dim = max(square_size, min_size)
    if square_size < target_dim:
        cropped = cropped.resize((target_dim, target_dim), Image.LANCZOS)

    img_byte_arr = io.BytesIO()
    cropped.save(img_byte_arr, format='JPEG', quality=92)
    return img_byte_arr.getvalue()


def upload_wp_media(image_bytes: bytes, filename: str) -> int:
    """Uploads cropped image bytes to WordPress Media Library and returns Attachment ID."""
    endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media"
    
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "image/jpeg"
    }

    response = requests.post(
        endpoint,
        data=image_bytes,
        headers=headers,
        auth=(WP_USERNAME, WP_APP_PASSWORD)
    )

    if response.status_code in (200, 201):
        media_id = response.json().get("id")
        print(f" Image uploaded successfully (Media ID: {media_id})")
        return media_id
    else:
        print(f" Failed to upload image. Status: {response.status_code}")
        print(response.text)
        return None


def get_or_create_series_id(series_name: str) -> int:
    """Retrieves or creates the taxonomy term ID for the SSP podcast series across candidate REST endpoints."""
    # Candidate endpoints used by Seriously Simple Podcasting
    candidate_endpoints = [
        f"{WP_URL.rstrip('/')}/wp-json/wp/v2/podcast_series",
        f"{WP_URL.rstrip('/')}/wp-json/wp/v2/series"
    ]
    
    for endpoint in candidate_endpoints:
        try:
            # 1. Search for existing series by name
            res = requests.get(endpoint, params={"search": series_name}, auth=(WP_USERNAME, WP_APP_PASSWORD))
            if res.status_code == 200:
                terms = res.json()
                for term in terms:
                    if term.get("name", "").lower() == series_name.lower():
                        return term.get("id")

                # 2. If endpoint exists (200 OK) but term wasn't found, try creating it
                create_res = requests.post(
                    endpoint,
                    json={"name": series_name},
                    auth=(WP_USERNAME, WP_APP_PASSWORD)
                )
                if create_res.status_code in (200, 201):
                    term_id = create_res.json().get("id")
                    print(f" Created new Podcast Series: '{series_name}' (ID: {term_id})")
                    return term_id
        except Exception:
            continue

    print(f" Warning: Could not retrieve/create podcast_series '{series_name}'. Assigning default feed.")
    return None


def find_mp3_in_obj(obj):
    """Recursively searches nested dicts and lists for strings ending with .mp3 or containing audio CDN URLs."""
    if isinstance(obj, str):
        if ('.mp3' in obj or 'audio' in obj or '.mp3?download=true' in obj) and obj.startswith('http'):
            if obj.endswith('.mp3') or obj.endswith('.mp3?') or obj.endswith('.mp3?download=true'):
                print(f" Found the mp3 link: '{obj}'.")
                return obj
    elif isinstance(obj, dict):
        for key in ['audio', 'downloadUrl', 'media', 'audioUrl', 'src', 'href', 'downloadLink-Bzfm4', 'download', 'downloadLink']:
            if key in obj:
                res = find_mp3_in_obj(obj[key])
                if res:
                    return res
        for k, v in obj.items():
            res = find_mp3_in_obj(v)
            if res:
                return res
    elif isinstance(obj, list):
        for item in obj:
            res = find_mp3_in_obj(item)
            if res:
                return res
    return None


def extract_audio_from_all_scripts(soup: BeautifulSoup) -> str:
    """Scans all <script> blocks on the page for inline JSON data containing MP3 links."""
    for script in soup.find_all('script'):
        if script.string and '{' in script.string and '}' in script.string:
            try:
                json_matches = re.findall(r'\{.*\}', script.string)
                for match in json_matches:
                    try:
                        data = json.loads(match)
                        mp3 = find_mp3_in_obj(data)
                        if mp3:
                            return mp3
                    except Exception:
                        continue
            except Exception:
                continue
    return None


def fetch_audio_from_api(url: str) -> str:
    """Queries Church API endpoints directly based on URI path structure."""
    match = re.search(r'/study/([^?]+)', url)
    if not match:
        return None

    path_part = match.group(1).rstrip('/')
    api_urls = [
        f"https://www.churchofjesuschrist.org/study/api/v1/eng/content/bulk/{path_part}",
        f"https://www.churchofjesuschrist.org/study/api/v1/eng/content/article/{path_part}"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

    for api_url in api_urls:
        try:
            res = requests.get(api_url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                mp3 = find_mp3_in_obj(data)
                if mp3:
                    return mp3
        except Exception:
            continue
    return None


def fetch_talk_data(url: str, manual_audio_url: str = None) -> dict:
    """Scrapes metadata, MP3 link (or uses direct input), and speaker artwork from the talk page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    # CRITICAL: Force UTF-8 decoding to prevent non-breaking space (0xC2 0xA0) from rendering as 'Â'
    response.encoding = 'utf-8'
    
    soup = BeautifulSoup(response.text, 'html.parser')

    # 1. Title
    title_el = soup.find('h1')
    title = clean_text(title_el.get_text()) if title_el else "Conference Talk"

    # 2. Byline & Kicker
    byline_el = soup.find('p', attrs={'class': re.compile(r'byline')}) or soup.find(attrs={'class': re.compile(r'author')})
    byline = clean_text(byline_el.get_text()) if byline_el else ""

    kicker_el = soup.find('p', attrs={'class': re.compile(r'kicker')}) or soup.find('p', attrs={'class': re.compile(r'subtitle')})
    kicker = clean_text(kicker_el.get_text()) if kicker_el else ""

    # 3. Audio Link Determination
    audio_url = manual_audio_url

    if audio_url:
        print("Using explicitly provided MP3 link from command line.")
    else:
        audio_url = fetch_audio_from_api(url)
        if not audio_url:
            audio_url = extract_audio_from_all_scripts(soup)
        if not audio_url:
            audio_el = soup.find('a', attrs={'class': re.compile(r'downloadLink')})
            if audio_el and audio_el.get('href'):
                audio_url = audio_el['href']
        if not audio_url:
            cdn_matches = re.findall(r'https?://[^\s"\'<>]*(?:media2\.ldscdn\.org|bcove|cloudfront)[^\s"\'<>]+\.mp3[^\s"\'<>]*', response.text)
            if cdn_matches:
                audio_url = cdn_matches[0]
            else:
                generic_mp3s = re.findall(r'https?://[^\s"\'<>]+\.mp3[^\s"\'<>]*', response.text)
                if generic_mp3s:
                    audio_url = generic_mp3s[0]

    if not audio_url:
        raise ValueError("Could not locate the MP3 download link. Please pass it explicitly as the second argument.")

    # 4. Poster Image Extraction
    poster_img_url = None
    poster_el = (
        soup.find('img', attrs={'class': re.compile(r'posterFallback')}) or 
        soup.find('meta', attrs={'property': 'og:image'})
    )

    if poster_el:
        if poster_el.name == 'meta':
            poster_img_url = poster_el.get('content')
        else:
            poster_img_url = poster_el.get('src') or poster_el.get('data-src')

    # Format Body Content
    body_content = f"<h1>{title}</h1>\n"
    if kicker:
        body_content += f"<p><em>{kicker}</em></p>\n"
    if byline:
        body_content += f"<p><strong>{byline}</strong></p>\n"
    body_content += f'<p><a href="{url}" target="_blank" rel="noopener">Read the full talk on ChurchOfJesusChrist.org</a></p>'

    return {
        "title": title,
        "content": body_content,
        "audio_url": audio_url,
        "poster_url": poster_img_url,
        "source_url": url
    }


def publish_to_wordpress(talk_data: dict, status: str = "draft"):
    """Publishes episode to WordPress as a Draft assigned to 'General Conference' podcast series."""
    featured_media_id = None

    if talk_data.get("poster_url"):
        print(f"Processing artwork from: {talk_data['poster_url']}")
        try:
            image_bytes = process_and_crop_image(talk_data["poster_url"], min_size=300)
            safe_slug = re.sub(r'[^a-zA-Z0-9]', '_', talk_data['title'].lower())[:30]
            filename = f"episode_{safe_slug}.jpg"
            featured_media_id = upload_wp_media(image_bytes, filename)
        except Exception as img_err:
            print(f" Warning: Failed to process image ({img_err}). Continuing without image.")

    # Resolve podcast_series taxonomy term ID for "General Conference"
    series_id = get_or_create_series_id(SERIES_NAME)

    endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{SSP_POST_TYPE}"
    
    payload = {
        "title": talk_data["title"],
        "content": talk_data["content"],
        "status": status,  # Created as Draft
        "comment_status": "closed",  # Disables comments on the post
        "meta": {
            "audio_file": talk_data["audio_url"],
            "_ss_podcasting_audio_file": talk_data["audio_url"]
        }
    }

    if featured_media_id:
        payload["featured_media"] = featured_media_id

    # Assign to "General Conference" podcast series taxonomy
    if series_id:
        payload["series"] = [series_id]

    response = requests.post(
        endpoint,
        json=payload,
        auth=(WP_USERNAME, WP_APP_PASSWORD)
    )

    if response.status_code in (200, 201):
        post = response.json()
        print(f" Successfully saved as DRAFT: '{talk_data['title']}'")
        print(f" Draft Post Edit Link: {WP_URL}/wp-admin/post.php?post={post.get('id')}&action=edit")
    else:
        print(f" Failed to save draft. Status: {response.status_code}")
        print(f"Response: {response.text}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python publish_talk.py <TALK_URL> [DIRECT_MP3_URL]")
        sys.exit(1)

    talk_url = sys.argv[1]
    manual_mp3_url = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Fetching talk data from {talk_url}...")
    
    try:
        talk_info = fetch_talk_data(talk_url, manual_audio_url=manual_mp3_url)
        print(f"Title: {talk_info['title']}")
        print(f"Audio MP3: {talk_info['audio_url']}")
        publish_to_wordpress(talk_info, status="draft")
    except Exception as e:
        print(f" Error: {e}")
