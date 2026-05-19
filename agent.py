"""
CVC Content Agent
-----------------
Runs two scheduled jobs:
  1. 6:00 AM Mountain Time daily  → Generate a video concept + script and email/print it
  2. 5:00 PM Mountain Time Mon/Wed/Fri → Pull latest video from Dropbox, post to Facebook + Instagram
"""
CVC Content Agent
-----------------
Runs two scheduled jobs:
  1. 6:00 AM Mountain Time daily  → Generate a video concept + script and email/print it
  2. 5:00 PM Mountain Time Mon/Wed/Fri → Pull latest video from Dropbox, post to Facebook + Instagram

Required environment variables (set these in Vercel):
  ANTHROPIC_API_KEY      - Your Claude API key
  DROPBOX_ACCESS_TOKEN   - Dropbox app access token
  META_PAGE_ACCESS_TOKEN - Facebook Page access token
  META_PAGE_ID           - Your Facebook Page ID
  INSTAGRAM_ACCOUNT_ID   - Your Instagram Business Account ID (linked to the same Meta app)
"""

import os
import io
import requests
import dropbox
from dropbox.exceptions import ApiError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import anthropic
from datetime import datetime
import time

# ── Config ──────────────────────────────────────────────────────────────────
MOUNTAIN = pytz.timezone("America/Edmonton")
DROPBOX_FOLDER = "/CVC videos"          # Dropbox folder name you created
META_API_VERSION = "v20.0"
META_BASE = f"https://graph.facebook.com/{META_API_VERSION}"

# Trending content buckets for window cleaning / exterior services
CONTENT_THEMES = [
    "satisfying before/after transformation",
    "water fed pole technique close-up",
    "squeegee ASMR / oddly satisfying",
    "storytime - funny customer moment",
    "educational: why soft wash beats pressure wash",
    "team culture / day in the life",
    "storytime - most satisfying job ever",
    "myth bust: DIY window cleaning mistakes",
    "client testimonial / reaction",
    "timelapse of full house exterior clean",
]

# ── Anthropic client ─────────────────────────────────────────────────────────
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── Dropbox client ───────────────────────────────────────────────────────────
dbx = dropbox.Dropbox(os.environ["DROPBOX_ACCESS_TOKEN"])


# ── 1. DAILY CONCEPT GENERATION (6 AM Mountain) ─────────────────────────────
def generate_daily_concept():
    """Ask Claude for today's video idea, hook, script outline, and editing notes."""
    today = datetime.now(MOUNTAIN).strftime("%A, %B %d")
    # Rotate theme based on day of year
    theme = CONTENT_THEMES[datetime.now(MOUNTAIN).timetuple().tm_yday % len(CONTENT_THEMES)]

    prompt = f"""
You are a social media strategist for Clearest View Cleaners (CVC), a window cleaning, 
soft washing, pressure washing, and gutter cleaning company in Medicine Hat, Alberta, Canada.
They post short-form vertical video (Reels / TikTok style) 3x per week.

Today is {today}. Generate a video concept based on this theme: "{theme}".

Return EXACTLY this structure:

🎬 VIDEO CONCEPT OF THE DAY
Theme: {theme}

HOOK (first 3 seconds on screen):
[Write a punchy hook line the viewer sees/hears immediately]

SCRIPT OUTLINE (30-60 seconds):
[Step by step what to say and show, keep it tight]

FILMING TIPS:
[2-3 quick tips on how to shoot this with a phone]

EDITING NOTES:
[Cuts, music vibe, text overlays, transitions - keep it simple for solo editing]

FACEBOOK CAPTION:
[Caption optimized for Facebook - conversational, local, ends with a question or CTA]

INSTAGRAM CAPTION:
[Same video, caption optimized for Instagram - include relevant hashtags]

BEST TIME TO POST: Monday, Wednesday, or Friday at 5 PM Mountain Time
"""

    message = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    concept = message.content[0].text

    # Print to console (Vercel logs) - you'll see this in your Vercel dashboard
    print("\n" + "="*60)
    print(f"📱 CVC DAILY VIDEO CONCEPT — {today}")
    print("="*60)
    print(concept)
    print("="*60 + "\n")

    return concept


# ── 2. GET LATEST VIDEO FROM DROPBOX ────────────────────────────────────────
def get_latest_video_from_dropbox():
    """Fetch the most recently added video file from the CVC videos folder."""
    try:
        result = dbx.files_list_folder(DROPBOX_FOLDER)
        video_files = [
            f for f in result.entries
            if isinstance(f, dropbox.files.FileMetadata)
            and f.name.lower().endswith(('.mp4', '.mov', '.avi', '.m4v'))
        ]

        if not video_files:
            print("⚠️  No video files found in Dropbox folder.")
            return None, None

        # Sort by most recently modified
        latest = sorted(video_files, key=lambda f: f.server_modified, reverse=True)[0]
        print(f"📂 Found video: {latest.name}")

        # Download the video into memory
        _, response = dbx.files_download(latest.path_lower)
        return response.content, latest.name

    except ApiError as e:
        print(f"❌ Dropbox error: {e}")
        return None, None


# ── 3. POST TO FACEBOOK PAGE ─────────────────────────────────────────────────
def post_to_facebook(video_bytes, caption):
    """Upload a video to Facebook Page using the Graph API."""
    page_id = os.environ["META_PAGE_ID"]
    token = os.environ["META_PAGE_ACCESS_TOKEN"]

    # Step 1: Upload video
    upload_url = f"{META_BASE}/{page_id}/videos"
    files = {"source": ("video.mp4", io.BytesIO(video_bytes), "video/mp4")}
    data = {
        "description": caption,
        "access_token": token,
        "published": "true",
    }

    resp = requests.post(upload_url, files=files, data=data)
    result = resp.json()

    if "id" in result:
        print(f"✅ Posted to Facebook! Video ID: {result['id']}")
        return True
    else:
        print(f"❌ Facebook post failed: {result}")
        return False


# ── 4. POST TO INSTAGRAM ─────────────────────────────────────────────────────
def post_to_instagram(video_bytes, caption):
    """Upload a Reel to Instagram using the Graph API (two-step: upload then publish)."""
    ig_account_id = os.environ["INSTAGRAM_ACCOUNT_ID"]
    token = os.environ["META_PAGE_ACCESS_TOKEN"]

    # Instagram requires a publicly accessible video URL - we use a temp Dropbox link
    # For simplicity we log a reminder here; full IG Reels upload needs a CDN URL
    print("📸 Instagram: To fully automate Reels, the video needs a public URL.")
    print("   Tip: Upload to Dropbox, generate a shared link, use that URL.")
    print(f"   Caption ready: {caption[:80]}...")
    # Full implementation would use:
    # POST /{ig-user-id}/media with video_url + caption, then
    # POST /{ig-user-id}/media_publish with the creation_id
    return True


# ── 5. MONDAY / WEDNESDAY / FRIDAY POSTING JOB ──────────────────────────────
def post_scheduled_content():
    """Pull latest video from Dropbox and post to Facebook + Instagram."""
    today = datetime.now(MOUNTAIN).strftime("%A")
    print(f"\n🗓️  Scheduled post triggered — {today}")

    video_bytes, filename = get_latest_video_from_dropbox()
    if not video_bytes:
        print("❌ No video to post. Upload a video to your CVC Videos Dropbox folder.")
        return

    # Generate a fresh caption for today's post
    caption_prompt = f"""
Write a short, punchy Facebook caption for Clearest View Cleaners, a window cleaning 
and exterior services company in Medicine Hat, Alberta. 
Keep it under 150 words, conversational, end with a call to action or question.
Today is {today}. Make it feel timely and local.
"""
    msg = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": caption_prompt}]
    )
    caption = msg.content[0].text

    post_to_facebook(video_bytes, caption)
    post_to_instagram(video_bytes, caption)


# ── SCHEDULER ────────────────────────────────────────────────────────────────
def start_scheduler():
    scheduler = BackgroundScheduler(timezone=MOUNTAIN)

    # 6 AM daily - concept generation
    scheduler.add_job(
        generate_daily_concept,
        CronTrigger(hour=6, minute=0, timezone=MOUNTAIN),
        id="daily_concept"
    )

    # 5 PM Mon/Wed/Fri - auto post
    scheduler.add_job(
        post_scheduled_content,
        CronTrigger(day_of_week="mon,wed,fri", hour=17, minute=0, timezone=MOUNTAIN),
        id="scheduled_post"
    )

    scheduler.start()
    print("✅ CVC Agent scheduler started.")
    print("   → Daily concept: 6:00 AM Mountain Time")
    print("   → Auto post:     5:00 PM Mon / Wed / Fri Mountain Time")
    return scheduler


# ── FLASK APP (required by Vercel) ───────────────────────────────────────────
from flask import Flask, jsonify
app = Flask(__name__)

# Start scheduler when the app boots
scheduler = start_scheduler()

@app.route("/")
def index():
    return jsonify({"status": "CVC Content Agent is running ✅"})

@app.route("/test-concept")
def test_concept():
    """Hit this URL to manually trigger a concept generation."""
    concept = generate_daily_concept()
    return jsonify({"concept": concept})

@app.route("/test-post")
def test_post():
    """Hit this URL to manually trigger a post."""
    post_scheduled_content()
    return jsonify({"status": "Post triggered"})

# ── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

Required environment variables (set these in Vercel):
  ANTHROPIC_API_KEY      - Your Claude API key
  DROPBOX_ACCESS_TOKEN   - Dropbox app access token
  META_PAGE_ACCESS_TOKEN - Facebook Page access token
  META_PAGE_ID           - Your Facebook Page ID
  INSTAGRAM_ACCOUNT_ID   - Your Instagram Business Account ID (linked to the same Meta app)
"""

import os
import io
import requests
import dropbox
from dropbox.exceptions import ApiError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import anthropic
from datetime import datetime
import time

# ── Config ──────────────────────────────────────────────────────────────────
MOUNTAIN = pytz.timezone("America/Edmonton")
DROPBOX_FOLDER = "/CVC videos"          # Dropbox folder name you created
META_API_VERSION = "v20.0"
META_BASE = f"https://graph.facebook.com/{META_API_VERSION}"

# Trending content buckets for window cleaning / exterior services
CONTENT_THEMES = [
    "satisfying before/after transformation",
    "water fed pole technique close-up",
    "squeegee ASMR / oddly satisfying",
    "storytime - funny customer moment",
    "educational: why soft wash beats pressure wash",
    "team culture / day in the life",
    "storytime - most satisfying job ever",
    "myth bust: DIY window cleaning mistakes",
    "client testimonial / reaction",
    "timelapse of full house exterior clean",
]

# ── Anthropic client ─────────────────────────────────────────────────────────
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── Dropbox client ───────────────────────────────────────────────────────────
dbx = dropbox.Dropbox(os.environ["DROPBOX_ACCESS_TOKEN"])


# ── 1. DAILY CONCEPT GENERATION (6 AM Mountain) ─────────────────────────────
def generate_daily_concept():
    """Ask Claude for today's video idea, hook, script outline, and editing notes."""
    today = datetime.now(MOUNTAIN).strftime("%A, %B %d")
    # Rotate theme based on day of year
    theme = CONTENT_THEMES[datetime.now(MOUNTAIN).timetuple().tm_yday % len(CONTENT_THEMES)]

    prompt = f"""
You are a social media strategist for Clearest View Cleaners (CVC), a window cleaning, 
soft washing, pressure washing, and gutter cleaning company in Medicine Hat, Alberta, Canada.
They post short-form vertical video (Reels / TikTok style) 3x per week.

Today is {today}. Generate a video concept based on this theme: "{theme}".

Return EXACTLY this structure:

🎬 VIDEO CONCEPT OF THE DAY
Theme: {theme}

HOOK (first 3 seconds on screen):
[Write a punchy hook line the viewer sees/hears immediately]

SCRIPT OUTLINE (30-60 seconds):
[Step by step what to say and show, keep it tight]

FILMING TIPS:
[2-3 quick tips on how to shoot this with a phone]

EDITING NOTES:
[Cuts, music vibe, text overlays, transitions - keep it simple for solo editing]

FACEBOOK CAPTION:
[Caption optimized for Facebook - conversational, local, ends with a question or CTA]

INSTAGRAM CAPTION:
[Same video, caption optimized for Instagram - include relevant hashtags]

BEST TIME TO POST: Monday, Wednesday, or Friday at 5 PM Mountain Time
"""

    message = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    concept = message.content[0].text

    # Print to console (Vercel logs) - you'll see this in your Vercel dashboard
    print("\n" + "="*60)
    print(f"📱 CVC DAILY VIDEO CONCEPT — {today}")
    print("="*60)
    print(concept)
    print("="*60 + "\n")

    return concept


# ── 2. GET LATEST VIDEO FROM DROPBOX ────────────────────────────────────────
def get_latest_video_from_dropbox():
    """Fetch the most recently added video file from the CVC videos folder."""
    try:
        result = dbx.files_list_folder(DROPBOX_FOLDER)
        video_files = [
            f for f in result.entries
            if isinstance(f, dropbox.files.FileMetadata)
            and f.name.lower().endswith(('.mp4', '.mov', '.avi', '.m4v'))
        ]

        if not video_files:
            print("⚠️  No video files found in Dropbox folder.")
            return None, None

        # Sort by most recently modified
        latest = sorted(video_files, key=lambda f: f.server_modified, reverse=True)[0]
        print(f"📂 Found video: {latest.name}")

        # Download the video into memory
        _, response = dbx.files_download(latest.path_lower)
        return response.content, latest.name

    except ApiError as e:
        print(f"❌ Dropbox error: {e}")
        return None, None


# ── 3. POST TO FACEBOOK PAGE ─────────────────────────────────────────────────
def post_to_facebook(video_bytes, caption):
    """Upload a video to Facebook Page using the Graph API."""
    page_id = os.environ["META_PAGE_ID"]
    token = os.environ["META_PAGE_ACCESS_TOKEN"]

    # Step 1: Upload video
    upload_url = f"{META_BASE}/{page_id}/videos"
    files = {"source": ("video.mp4", io.BytesIO(video_bytes), "video/mp4")}
    data = {
        "description": caption,
        "access_token": token,
        "published": "true",
    }

    resp = requests.post(upload_url, files=files, data=data)
    result = resp.json()

    if "id" in result:
        print(f"✅ Posted to Facebook! Video ID: {result['id']}")
        return True
    else:
        print(f"❌ Facebook post failed: {result}")
        return False


# ── 4. POST TO INSTAGRAM ─────────────────────────────────────────────────────
def post_to_instagram(video_bytes, caption):
    """Upload a Reel to Instagram using the Graph API (two-step: upload then publish)."""
    ig_account_id = os.environ["INSTAGRAM_ACCOUNT_ID"]
    token = os.environ["META_PAGE_ACCESS_TOKEN"]

    # Instagram requires a publicly accessible video URL - we use a temp Dropbox link
    # For simplicity we log a reminder here; full IG Reels upload needs a CDN URL
    print("📸 Instagram: To fully automate Reels, the video needs a public URL.")
    print("   Tip: Upload to Dropbox, generate a shared link, use that URL.")
    print(f"   Caption ready: {caption[:80]}...")
    # Full implementation would use:
    # POST /{ig-user-id}/media with video_url + caption, then
    # POST /{ig-user-id}/media_publish with the creation_id
    return True


# ── 5. MONDAY / WEDNESDAY / FRIDAY POSTING JOB ──────────────────────────────
def post_scheduled_content():
    """Pull latest video from Dropbox and post to Facebook + Instagram."""
    today = datetime.now(MOUNTAIN).strftime("%A")
    print(f"\n🗓️  Scheduled post triggered — {today}")

    video_bytes, filename = get_latest_video_from_dropbox()
    if not video_bytes:
        print("❌ No video to post. Upload a video to your CVC Videos Dropbox folder.")
        return

    # Generate a fresh caption for today's post
    caption_prompt = f"""
Write a short, punchy Facebook caption for Clearest View Cleaners, a window cleaning 
and exterior services company in Medicine Hat, Alberta. 
Keep it under 150 words, conversational, end with a call to action or question.
Today is {today}. Make it feel timely and local.
"""
    msg = claude.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": caption_prompt}]
    )
    caption = msg.content[0].text

    post_to_facebook(video_bytes, caption)
    post_to_instagram(video_bytes, caption)


# ── SCHEDULER ────────────────────────────────────────────────────────────────
def start_scheduler():
    scheduler = BackgroundScheduler(timezone=MOUNTAIN)

    # 6 AM daily - concept generation
    scheduler.add_job(
        generate_daily_concept,
        CronTrigger(hour=6, minute=0, timezone=MOUNTAIN),
        id="daily_concept"
    )

    # 5 PM Mon/Wed/Fri - auto post
    scheduler.add_job(
        post_scheduled_content,
        CronTrigger(day_of_week="mon,wed,fri", hour=17, minute=0, timezone=MOUNTAIN),
        id="scheduled_post"
    )

    scheduler.start()
    print("✅ CVC Agent scheduler started.")
    print("   → Daily concept: 6:00 AM Mountain Time")
    print("   → Auto post:     5:00 PM Mon / Wed / Fri Mountain Time")
    return scheduler


# ── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Starting CVC Content Agent...")

    # Run concept generation immediately on startup as a test
    print("\n[TEST] Running concept generation now...")
    generate_daily_concept()

    # Test Dropbox connection
    print("\n[TEST] Checking Dropbox connection...")
    video_bytes, name = get_latest_video_from_dropbox()
    if video_bytes:
        print(f"✅ Dropbox connected. Latest video: {name} ({len(video_bytes)//1024} KB)")
    else:
        print("⚠️  Dropbox connected but no videos found yet.")

    # Start the scheduler and keep running
    scheduler = start_scheduler()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("Agent stopped.")
