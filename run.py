import os
import sys
import yt_dlp
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse


# Configuration
MAX_RETRIES = 10 # Maximum number of retries for failed downloads
OUTPUT_DIR = 'downloads' # Output directory for downloaded videos
MAX_WORKERS = 5  # Maximum number of parallel downloads
TIMEOUT = 10  # Timeout for requests in seconds
VIDEO_DOMAINS = ['youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com'] # Supported video domains
FAILED_LOG = "failed.txt"

def extract_video_urls(url):
    """
    Extract all video URLs from a webpage (if possible).
    This function tries to find video tags or other video links.
    """

    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    if any(d in domain for d in VIDEO_DOMAINS):
        print(f"➡️ Detected video domain: {domain}. Using URL directly.")
        return [url]  # Skip parsing, let yt-dlp handle it

    print(f"🔍 Scanning webpage for embedded video links...")
    video_urls = [] # List to store video URLs
    try:
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # From <video> tags
        video_tags = soup.find_all('video')
        video_urls += [tag.get('src') for tag in video_tags if tag.get('src')]

        # <iframe> tags for embedded players
        iframe_tags = soup.find_all('iframe')
        for tag in iframe_tags:
            src = tag.get('src')
            if src and any(domain in src for domain in VIDEO_DOMAINS):
                video_urls.append(src)

        # <a> tags pointing to viedo domains
        a_tags = soup.find_all('a')
        for tag in a_tags:
            href = tag.get('href')
            if href and any(domain in href for domain in VIDEO_DOMAINS):
                video_urls.append(href)
        
        # Clean duplicates and empty entries
        video_urls = list({url for url in video_urls if url})

        # If no video tags are found, return the original URL (let yt-dlp handle it)
        if not video_urls:
            print("No video links found in page. Assuming the URL is a direct video or playlist.")
            return [url]
        
        return video_urls
    
    except Exception as e:
        print(f"[!] Failed to extract video URLs: {e}")
        return []
    
def progress_hook(data, url):
    """
    Callback function to update the progress bar.
    """
    if data['status'] == 'downloading':
        # Get the progress percentage
        if 'total_bytes' in data:
            total = data['total_bytes']
            done = data['downloaded_bytes']
            #progress = (downloaded_bytes / total_bytes) * 100
        elif 'total_bytes_estimate' in data:
            total = data['total_bytes_estimate']
            done = data['downloaded_bytes']
            #progress = (downloaded_bytes / total_bytes) * 100
        else:
           return  # No progress information available
        
        progress = (done / total) * 100 if total else 0
        # Update the progress bar
        progress_bars[url].n = progress
        progress_bars[url].refresh()

def download_video_with_progress(url, output_dir=OUTPUT_DIR, retries=MAX_RETRIES):
    """
    Download a video using yt-dlp with a progress bar and retry mechanism.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Options for yt-dlp
    ydl_opts = {
        'format': 'best',  # Download the best quality available
        'outtmpl': os.path.join(output_dir, '%(title).100B.%(ext)s'),
        # Save file as title.ext, truncating title to 100 characters
        #'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),  # Save file as title.ext
        'quiet': True,  # Suppress output
        'progress_hooks': [lambda d: progress_hook(d, url)],  # Add progress hook
        'noplaylist': False,  # Download the entire playlist if URL is a playlist
    }

    for attempt in range(1,retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            print(f"✅ Download complete: {url}")
            return  # Exit if download is successful
        except Exception as e:
            #print(f"Attempt {attempt + 1} failed for {url}: {e}")
            print(f"[{attempt}/{retries}] ❌ Error for {url}: {e}")
            #if attempt < retries - 1:
            #    print(f"Retrying... ({attempt + 1}/{retries})")
            #else:
            #    print(f"All retries failed for {url}. Skipping...")

            # Log the failed URL to a file
            if attempt == retries:
                with open(FAILED_LOG, 'a') as f:
                    f.write(f"{url}\n")
                print(f"[SKIPPED] All retries failed for {url}.\n")



def download_videos_in_parallel(video_urls):
    """
    Download multiple videos in parallel using ThreadPoolExecutor.
    """
    global progress_bars
    progress_bars = {}  # Dictionary to store progress bars for each URL

    # Initialize progress bars
    for url in video_urls:
        progress_bars[url] = tqdm(total=100, desc=f"Downloading {url}", unit="%", ncols=100)

    # Initialize overall progress bar
    overall = tqdm(total=len(video_urls), desc="Overall Progress", ncols=100)

    # Use ThreadPoolExecutor to download videos in parallel
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_video_with_progress, url): url for url in video_urls}

        # Wait for all downloads to complete
        for future in as_completed(futures):
            url = futures[future]
            try:
                future.result()  # Check for exceptions
            except Exception as e:
                print(f"Error downloading {url}: {e}")
            overall.update(1)
    
    overall.close()  # Close the overall progress bar
    for bar in progress_bars.values():
        bar.close()

    # Close all progress bars
    for pbar in progress_bars.values():
        pbar.close()

def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Input URL from the user
        url = input("Enter the URL (video, playlist, or webpage): ")

    # Extract video URLs (if necessary)
    video_urls = extract_video_urls(url)
    if not video_urls:
        print("No valid video links found.")
        return
    
    print(f"\n🎬 Found {len(video_urls)} video(s). Starting downloads...\n")

    # Download videos in parallel
    download_videos_in_parallel(video_urls)

if __name__ == "__main__":
    main()