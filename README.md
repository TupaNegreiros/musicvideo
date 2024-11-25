# musicvideo.py
Script to download music videos from Lidarr

This was only tested in Ubuntu Linux, fell free to send me feedback for other systems.

Python3 and sqlite3 are required.

Edit config.json with the following:

- Address of Lidarr in lidarr_api_url. It could be in another computer.
- Connect to your Lidarr, Settings, General, search for API Key, copy the value in api_key.
- If you want, change the value of the database file db_file.
- Change the path of downloaded videos in base_download_path.
- Get the latest release of yt-dlp in https://github.com/yt-dlp/yt-dlp/releases, save in the same folder of musicvideo.py. I've tried using youtube-dl, but I got errors when downloading the best quality. It's possible to change executable and path inside download_video_bash function.
- Install a browser extension such as Get cookies.txt LOCALLY for Chrome or cookies.txt for Firefox. Open youtube.com and export youtube cookies to a file. Put path and name of this file in cookies_file.

Execute musicvideo.py
