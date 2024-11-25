# musicvideo.py
Script to download music videos from Lidarr

This was only tested in Ubuntu Linux, fell free to send me feedback for other systems.

Python3 and sqlite3 are required.

Edit musicvideo.py with the following:

Address of Lidarr in LIDARR_API_URL. It could be in another computer.
Connect to your Lidarr, Settings, General, search for API Key, copy the value in API_KEY.
If you want, change the value of the database file DB_FILE.
Change the path of downloaded videos in BASE_DOWNLOAD_PATH.
Get the latest release of yt-dlp in https://github.com/yt-dlp/yt-dlp/releases, save in the same folder of musicvideo.py. I've tried using youtube-dl, but I got errors when downloading the best quality. It's possible to change executable and path inside download_video_bash function.
Install a browser extension such as Get cookies.txt LOCALLY for Chrome or cookies.txt for Firefox. Open youtube.com and export youtube cookies to a file. Put path and name of this file in COOKIES_FILE.
