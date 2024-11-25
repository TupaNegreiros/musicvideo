#!/usr/bin/python

import requests
import sqlite3
import os
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import subprocess

# Lidarr API configuration
LIDARR_API_URL = "http://127.0.0.1:8686/api/v1"
API_KEY = "{copy API from lidarr}"

# SQLite3 database configuration
DB_FILE = "musicvideo.db"

BASE_DOWNLOAD_PATH = "~/Music Videos"

COOKIES_FILE = "~/youtube.com_cookies.txt"

def create_database():
    """
    Creates the SQLite3 database and tables if they don't exist.
    - 'artists' table stores artist data.
    - 'videos' table stores video details for each artist.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create the artists table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_name TEXT NOT NULL,
            musicbrainz_id TEXT NOT NULL UNIQUE,
            imvdb_link TEXT,
            imvdb_link TEXT
        )
    """)

    # Create the videos table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id INTEGER NOT NULL,
            video_name TEXT NOT NULL,
            imvdb_url TEXT NOT NULL,
            youtube_url TEXT,
            downloaded BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (artist_id) REFERENCES artists (id)
        )
    """)

    conn.commit()
    conn.close()

def get_artists_from_lidarr():
    """
    Fetches all artists from the Lidarr instance.
    """
    endpoint = f"{LIDARR_API_URL}/artist"
    headers = {"X-Api-Key": API_KEY}

    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Lidarr API: {e}")
        return []

def sync_with_database(lidarr_artists):
    """
    Synchronizes the SQLite3 database with the artists from Lidarr.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Convert Lidarr artist data to a set of (artistName, foreignArtistId)
    lidarr_artist_data = {(artist["artistName"], artist["foreignArtistId"]) for artist in lidarr_artists}

    # Get all artists currently in the database
    cursor.execute("SELECT artist_name, musicbrainz_id FROM artists")
    db_artists = set(cursor.fetchall())

    # Find artists to add and remove
    artists_to_add = lidarr_artist_data - db_artists
    artists_to_remove = db_artists - lidarr_artist_data

    # Add new artists
    for artist_name, musicbrainz_id in artists_to_add:
        cursor.execute("INSERT INTO artists (artist_name, musicbrainz_id) VALUES (?, ?)", (artist_name, musicbrainz_id))

    # Remove missing artists
    for artist_name, musicbrainz_id in artists_to_remove:
        cursor.execute("DELETE FROM artists WHERE artist_name = ? AND musicbrainz_id = ?", (artist_name, musicbrainz_id))

    # Commit changes and close connection
    conn.commit()
    conn.close()

    print(f"Added {len(artists_to_add)} new artist(s) to the database.")
    print(f"Removed {len(artists_to_remove)} artist(s) from the database.")

def get_imvdb_link(musicbrainz_id):
    """
    Makes a request to MusicBrainz to get the IMVDb link for an artist.
    """
    url = f"https://musicbrainz.org/ws/2/artist/{musicbrainz_id}?inc=url-rels&fmt=json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Search for IMVDb link in URL relationships
        for rel in data.get("relations", []):
            url_data = rel.get("url", {}).get("resource", "")
            if "imvdb.com" in url_data:
                return url_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching IMVDb link for MusicBrainz ID {musicbrainz_id}: {e}")
    return None

def update_imvdb_links():
    """
    Fetches the IMVDb link for each artist in the database and updates the table
    only if the 'imvdb_link' field is empty.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get all artists with an empty 'imvdb_link' field
    cursor.execute("SELECT id, artist_name, musicbrainz_id FROM artists WHERE imvdb_link IS NULL OR imvdb_link = ''")
    artists = cursor.fetchall()
    
    for artist_id, artist_name, musicbrainz_id in artists:
        if musicbrainz_id:
            imvdb_link = get_imvdb_link(musicbrainz_id)
            if imvdb_link:
                cursor.execute("UPDATE artists SET imvdb_link = ? WHERE id = ?", (imvdb_link, artist_id))
                conn.commit()
                print(f"Updated IMVDb link for {artist_name}: {imvdb_link}")
            else:
                print(f"No IMVDb link found for {artist_name} (MusicBrainz ID: {musicbrainz_id})")
    
    conn.close()

def get_all_imvdb_links():
    """
    Retrieves all IMVDb links from the database.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Select all rows with a non-empty 'imvdb_link'
    cursor.execute("SELECT artist_name, imvdb_link FROM artists WHERE imvdb_link IS NOT NULL AND imvdb_link != ''")
    imvdb_links = cursor.fetchall()
    conn.close()

    return imvdb_links


def scrape_videography_links(imvdb_url):
    """
    Scrapes the videography links and video names from an IMVDb URL using BeautifulSoup.
    Looks for <div id="artist-credits"> and extracts the first link and video name from the second column of the table.
    """
    try:
        response = requests.get(imvdb_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the <div id="artist-credits">
        artist_credits_div = soup.find('div', id='artist-credits')
        if not artist_credits_div:
            print(f"'artist-credits' section not found on {imvdb_url}")
            return []

        # Find the <table> inside artist-credits
        table = artist_credits_div.find('table')
        if not table:
            print(f"No <table> found inside 'artist-credits' on {imvdb_url}")
            return []

        # Extract links and video names
        video_details = []
        rows = table.find_all('tr')
        for row in rows:
            # Get the first link in the row
            first_link = row.find('a', href=True)
            if not first_link:
                continue
            video_url = first_link['href']
            video_url = video_url if video_url.startswith('http') else f"https://imvdb.com{video_url}"

            # Get the video name from the second column
            second_column = row.find_all('td')[1] if len(row.find_all('td')) > 1 else None
            if second_column:
                # Extract the raw HTML content of the <td>
                video_name = second_column.get_text(strip=True)

                video_name = video_name.replace("(", " (").replace("  (", " (")

                # Append video URL and name
                video_details.append((video_url, video_name))

        return video_details

    except Exception as e:
        print(f"Error scraping videography links from {imvdb_url}: {e}")
        return []

def scrape_youtube_link(video_url):
    """
    Scrapes the YouTube URL from an individual video page on IMVDb
    and formats it to a simpler version.
    """
    try:
        response = requests.get(video_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for the YouTube embed iframe
        youtube_iframe = soup.find('iframe', src=lambda x: x and 'youtube.com' in x)
        if youtube_iframe:
            # Extract the video ID and format the URL
            youtube_src = youtube_iframe['src']
            parsed_url = urlparse(youtube_src)
            query_params = parse_qs(parsed_url.query)
            video_id = parsed_url.path.split('/')[-1] if 'embed' in parsed_url.path else query_params.get('v', [None])[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"

        # Alternatively, check for direct YouTube link
        youtube_link = soup.find('a', href=lambda x: x and 'youtube.com/watch' in x)
        if youtube_link:
            # Extract video ID from the direct YouTube link
            parsed_url = urlparse(youtube_link['href'])
            video_id = parse_qs(parsed_url.query).get('v', [None])[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"

    except Exception as e:
        print(f"Error scraping YouTube link from {video_url}: {e}")

    return None

def process_all_video_links():
    """
    Scrapes video links and video details for all artists with IMVDb links,
    adds them to the database if not already present, and fetches the YouTube URL.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Fetch all artists with IMVDb links
    cursor.execute("SELECT id, artist_name, imvdb_link FROM artists WHERE imvdb_link IS NOT NULL AND imvdb_link != ''")
    artists = cursor.fetchall()

    for artist_id, artist_name, imvdb_link in artists:
        print(f"Scraping video links for artist '{artist_name}' from {imvdb_link}...")
        video_details = scrape_videography_links(imvdb_link)

        if video_details:
            for imvdb_url, video_name in video_details:
                # Check if the video is already in the database
                cursor.execute("""
                    SELECT id, youtube_url, downloaded FROM videos WHERE imvdb_url = ?
                """, (imvdb_url,))
                existing_video = cursor.fetchone()

                if not existing_video:
                    # Fetch YouTube URL
                    youtube_url = scrape_youtube_link(imvdb_url)

                    # Add new video to the database
                    cursor.execute("""
                        INSERT INTO videos (artist_id, video_name, imvdb_url, youtube_url, downloaded)
                        VALUES (?, ?, ?, ?, ?)
                    """, (artist_id, video_name, imvdb_url, youtube_url, False))
                    conn.commit()
                    print(f"Added video '{video_name}' with YouTube URL: {youtube_url or 'N/A'}")
                else:
                    # If YouTube URL is missing, update it
                    video_id, existing_youtube_url, downloaded = existing_video
                    if not existing_youtube_url or not downloaded:
                        youtube_url = scrape_youtube_link(imvdb_url)
                        if youtube_url and (not existing_youtube_url or youtube_url != existing_youtube_url):
                            cursor.execute("""
                                UPDATE videos SET youtube_url = ? WHERE id = ?
                            """, (youtube_url, video_id))
                            conn.commit()
                            print(f"Updated YouTube URL for video '{video_name}' to: {youtube_url}")

        else:
            print(f"No video links found for '{artist_name}'.")

    conn.close()
def get_videos_not_downloaded():
    """
    Fetch all videos with downloaded = FALSE, including artist name, video name, and YouTube URL.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    query = """
        SELECT videos.id, artists.artist_name, videos.video_name, videos.youtube_url
        FROM videos
        JOIN artists ON videos.artist_id = artists.id
        WHERE videos.downloaded = FALSE AND videos.youtube_url IS NOT NULL;
    """
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()
    return results


def download_video_bash(video_id, artist_name, video_name, youtube_url):
    """
    Downloads the YouTube video using youtube-dl in bash and saves it to the specified path.
    """
    # Create artist directory if it doesn't exist
    artist_path = os.path.join(BASE_DOWNLOAD_PATH, artist_name.replace("/", "⧸"))
    os.makedirs(artist_path, exist_ok=True)

    video_name = video_name.replace("/", "⧸")

    # Define the output file path
    output_path = os.path.join(artist_path, f"{video_name} [%(title)s - %(id)s].%(ext)s")

    # Run youtube-dl command via subprocess
    command = [
        "./yt-dlp",
#        "youtube-dl",
        "-f", "bestvideo+bestaudio/best",  # Best quality
        "--abort-on-unavailable-fragment",
        "--extractor-args", "youtube:player_client=mweb",
        "--cookies", COOKIES_FILE,
        "--merge-output-format", "mp4",   # Save as .mp4
        "-o", output_path,                # Output file path
        youtube_url                       # YouTube URL
    ]

    try:
        print(f"Downloading: {video_name} by {artist_name} from {youtube_url}")
        subprocess.run(command, check=True)
        print(f"Successfully downloaded: {video_name}")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading {video_name} by {artist_name}: {e}")
        raise

def mark_video_as_downloaded(video_id):
    """
    Updates the database to mark a video as downloaded.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE videos SET downloaded = TRUE WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()
    
def remove_empty_subfolders():
    """
    Recursively removes all empty subfolders in the specified base path.
    """
    for dirpath, dirnames, filenames in os.walk(BASE_DOWNLOAD_PATH, topdown=False):
        # If the directory is empty (no files or subdirectories), remove it
        if not dirnames and not filenames:
            try:
                os.rmdir(dirpath)
                print(f"Removed empty folder: {dirpath}")
            except OSError as e:
                print(f"Failed to remove {dirpath}: {e}")
    
def main():
    """
    Main function to fetch artists from Lidarr and sync them with the database.
    """
    # Ensure the database and table exist
    create_database()

    # Get artists from Lidarr
    lidarr_artists = get_artists_from_lidarr()

    # Sync artists with the database
    sync_with_database(lidarr_artists)

    # Update IMVDb links for all artists
    update_imvdb_links()

    process_all_video_links()
    
    
    # Fetch all videos with downloaded = FALSE
    videos = get_videos_not_downloaded()

    if not videos:
        print("No videos to download.")
        return

    for video_id, artist_name, video_name, youtube_url in videos:
        try:
            # Download the video
            download_video_bash(video_id, artist_name, video_name, youtube_url)

            # Mark the video as downloaded in the database
            mark_video_as_downloaded(video_id)
            print(f"Marked as downloaded: {video_name}")
        except Exception as e:
            print(f"Error processing {video_name} by {artist_name}: {e}")
    remove_empty_subfolders()

if __name__ == "__main__":
    main()
