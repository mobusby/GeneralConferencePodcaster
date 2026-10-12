#!/bin/python
# 
# publish_list.py
#
# Call publish_talk.py for each line in the file provided as a command line argument

import sys
import time
from publish_talk import fetch_talk_data, publish_to_wordpress

def process_url_list_file(file_path: str):
    """
    Reads a file containing lines formatted as:
    <TALK_URL> <MP3_URL>
    or just:
    <TALK_URL>
    """
    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    total = len(lines)
    print(f"Loaded {total} talk entries from '{file_path}'. Processing...\n")

    for idx, line in enumerate(lines, 1):
        parts = line.split()
        talk_url = parts[0]
        mp3_url = parts[1] if len(parts) > 1 else None

        print(f"[{idx}/{total}] Processing: {talk_url}")
        if mp3_url:
            print(f" -> Provided MP3: {mp3_url}")

        try:
            talk_info = fetch_talk_data(talk_url, manual_audio_url=mp3_url)
            publish_to_wordpress(talk_info, status="draft")
        except Exception as e:
            print(f" ERROR processing {talk_url}: {e}")

        print("-" * 60)
        time.sleep(1)  # Polite delay between requests


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python batch_publish.py <URLS_FILE>")
        print("Example: python batch_publish.py urls.txt")
        sys.exit(1)

    file_path = sys.argv[1]
    process_url_list_file(file_path)
