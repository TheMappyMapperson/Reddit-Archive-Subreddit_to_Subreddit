import praw
import requests
import os
import time
import logging
from datetime import datetime, timedelta, timezone
from prawcore.exceptions import RequestException, ResponseException
from praw.exceptions import RedditAPIException

# Set up logging
logging.basicConfig(filename='error_log.txt', level=logging.ERROR, 
                    format='%(asctime)s %(levelname)s: %(message)s')

# Reddit API credentials
ufos_reddit = praw.Reddit(
    client_id='',
    client_secret='',
    password='',
    username='',
    user_agent='<Ubuntu>.python:Archive.bot:v2.0.0 (by @saltysomadmin)'
)

archives_reddit = praw.Reddit(
    client_id='',
    client_secret='',
    password='',
    username='',
    user_agent='<Ubuntu>.python:Archive.bot:v2.0.0 (by @saltysomadmin)'
)

# Function to download media (images or videos)
def download_media(url, file_name):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(file_name, 'wb') as out_file:
            for chunk in response.iter_content(chunk_size=1024):
                out_file.write(chunk)
        return file_name
    else:
        logging.error(f"Failed to download media from {url}. Status code: {response.status_code}")
        return None

# Function to handle rate limits and retry after delay
def handle_rate_limit(ex):
    if 'Retry-After' in ex.response.headers:
        wait_time = int(ex.response.headers['Retry-After'])
        print(f"Rate limit reached. Retrying after {wait_time} seconds.")
        time.sleep(wait_time)
    else:
        print("Rate limit reached. Waiting for 60 seconds by default.")
        time.sleep(60)

# Function to split a text into chunks under the character limit
def split_text(text, max_length=10000):
    chunks = []
    while len(text) > max_length:
        split_point = text.rfind("\n", 0, max_length)  # Try splitting at the last newline
        if split_point == -1:  # No newline found, split at max_length
            split_point = max_length
        chunks.append(text[:split_point])
        text = text[split_point:].lstrip()  # Remove leading whitespace for the next chunk
    chunks.append(text)  # Add the remaining text
    return chunks

# Source subreddit
source_subreddit = ufos_reddit.subreddit('ufos')

# Destination subreddit
destination_subreddit = archives_reddit.subreddit('UFOs_Archives')

# Get the current time and calculate the time 30 minutes ago
current_time = datetime.now(timezone.utc)
time_30_minutes_ago = current_time - timedelta(minutes=14)

# Iterate over new submissions in the 'ufos' subreddit with no limit
for submission in source_subreddit.new():
    try:
        # Log submission details for debugging
        logging.info(f"Processing submission: {submission.title}, Flair: {submission.link_flair_text}, Created: {submission.created_utc}")

        # Check if the post was created within the last 30 minutes
        post_time = datetime.fromtimestamp(submission.created_utc, timezone.utc)
        if post_time < time_30_minutes_ago:
            continue

        title = submission.title
        is_self_post = submission.is_self
        media_url = None
        original_media_url = None

        # Handle media posts (images or videos)
        if not is_self_post:
            # Check if it is an image
            if submission.url.endswith(('jpg', 'jpeg', 'png', 'gif')):
                file_name = submission.url.split('/')[-1]
                media_url = download_media(submission.url, file_name)
                original_media_url = submission.url

            # Handle Reddit-hosted videos
            elif 'v.redd.it' in submission.url and submission.media:
                video_url = submission.media['reddit_video']['fallback_url']
                file_name = 'video.mp4'
                media_url = download_media(video_url, file_name)
                original_media_url = video_url

        # Initialize new_post to avoid NameError
        new_post = None

        # Repost to the destination subreddit
        if is_self_post:
            new_post = destination_subreddit.submit(title, selftext=submission.selftext)
        elif media_url and os.path.exists(media_url) and os.path.getsize(media_url) > 0:
            if media_url.endswith(('jpg', 'jpeg', 'png', 'gif')):
                new_post = destination_subreddit.submit_image(title, image_path=media_url, flair_id=None)
            elif media_url.endswith('mp4'):
                new_post = destination_subreddit.submit_video(title, video_path=media_url, flair_id=None)
        else:
            new_post = destination_subreddit.submit(title, url=submission.url)

        # Handle new post commenting
        if new_post:
            comment_body = f"Original post by u/{submission.author}: [Here]({submission.permalink})"
            if original_media_url:
                comment_body += f"\n\nDirect link to media: [Media Here]({original_media_url})"
            if submission.selftext:
                comment_body += f"\n\nOriginal post text: {submission.selftext}"

            # Check if the comment body is too long
            if len(comment_body) > 10000:
                chunks = split_text(comment_body)
                for chunk in chunks:
                    new_post.reply(chunk)
                    time.sleep(5)  # Small delay between replies to avoid rate limits
            else:
                new_post.reply(comment_body)

        print(f"Copied post: {submission.title}")

        # Introduce a delay between requests to avoid rate limits
        time.sleep(10)

    except (RequestException, ResponseException, RedditAPIException) as ex:
        logging.error(f"Error for post {submission.id}: {str(ex)}")
        handle_rate_limit(ex)

    except Exception as e:
        logging.error(f"General error for post {submission.id}: {str(e)}")

    # Clean up downloaded media files
    if media_url and os.path.exists(media_url):
        os.remove(media_url)
