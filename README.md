# General Conference Podcaster
Automate the process of pushing individual talks from the General Conferences of the Church of Jesus Christ of Latter-day Saints to a WordPress podcast.

1. Create a local clone of the repo
2. Copy `wordPressSecrets_template.py` to `wordPressSecrets.py` and add your secrets
3. Modify any other parameters to match your podcast setup in `publish_talk.py`
4. Create a single podcast episode: `$ python publish_talk.py [talk_url] [mp3_url]`
5. Batch out several podcast episodes by creating a list of entries in a text file, where each line is `[talk_url] [mp3_url]`, then `$ python publish_list.py [urlList.txt]`

*Free software under the BSD License. Code created with the help of Gemini 3.6 Flash.*
