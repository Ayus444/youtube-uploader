import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ParseMode

# ===== CONFIGURATION =====
API_ID = 22581733  # Your Telegram API ID
API_HASH = '1db7bdcf908100cc641c6a5276765c3d'  # Your Telegram API Hash
BOT_TOKEN = '7613437933:AAFIy6AnStWX6RjYz8zfHvDmnMYrvZkIMV4'  # Your Bot Token
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Session storage
user_data = {}

# Initialize Pyrogram Client
app = Client(
    "yt_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ===== CORE FUNCTIONS =====
async def get_video_info(url: str):
    """Fetch video information using yt-dlp"""
    try:
        cmd = [
            'yt-dlp',
            '--get-title',
            '--get-thumbnail',
            '--list-formats',
            '--no-warnings',
            '--cookies', 'cookies.txt' if os.path.exists('cookies.txt') else '/dev/null',
            url
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            raise Exception(f"❌ YouTube-DL Error: {error_msg}")
        
        output = stdout.decode().split('\n')
        return output[0].strip(), output[1].strip(), output[2:]
    except Exception as e:
        raise Exception(f"❌ Failed to get video info: {str(e)}")

async def parse_formats(raw_formats: list):
    """Parse available formats from yt-dlp output"""
    formats = []
    for line in raw_formats:
        if not line.strip() or not line[0].isdigit():
            continue
            
        parts = re.split(r'\s+', line.strip())
        if len(parts) < 9:
            continue
            
        format_id = parts[0]
        extension = parts[1]
        resolution = parts[2] if parts[2] != "unknown" else "audio"
        note = "video only" if "video only" in line else "audio only" if "audio only" in line else ""
        
        formats.append({
            'id': format_id,
            'ext': extension,
            'res': resolution,
            'note': note
        })
    return formats[:20]  # Limit to 20 formats

async def download_media(url: str, format_id: str, format_note: str):
    """Download and process media file with comprehensive error handling"""
    try:
        # Build download command
        cmd = [
            'yt-dlp',
            '-f', f"{format_id}+bestaudio" if format_note == "video only" else format_id,
            '-o', f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            '--write-thumbnail',
            '--merge-output-format', 'mp4',
            '--no-warnings',
            '--cookies', 'cookies.txt' if os.path.exists('cookies.txt') else '/dev/null',
            url
        ]
        
        if format_note == "audio only":
            cmd.extend(['--extract-audio', '--audio-format', 'mp3'])
        
        # Execute download
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise Exception(f"Download failed: {stderr.decode()}")
        
        # Find downloaded files
        media_files = []
        thumb_files = []
        
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(('.mp4', '.mkv', '.webm', '.mp3')):
                media_files.append(f)
            elif f.endswith(('.jpg', '.webp')):
                thumb_files.append(f)
        
        if not media_files:
            raise Exception("No media file found after download")
        
        # Get most recent files
        media_path = os.path.join(
            DOWNLOAD_DIR,
            max(media_files, key=lambda f: os.path.getmtime(os.path.join(DOWNLOAD_DIR, f)))
        )
        
        thumb_path = os.path.join(
            DOWNLOAD_DIR,
            max(thumb_files, key=lambda f: os.path.getmtime(os.path.join(DOWNLOAD_DIR, f)))
        ) if thumb_files else None
        
        # Extract title from filename
        title = os.path.splitext(os.path.basename(media_path))[0]
        
        return media_path, thumb_path, title
        
    except Exception as e:
        # Cleanup any partial downloads
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.jpg', '.webp')):
                os.remove(os.path.join(DOWNLOAD_DIR, f))
        raise

# ===== MESSAGE HANDLERS =====
@app.on_message(filters.command(["start", "help"]))
async def start_handler(_, message: Message):
    """Handle /start and /help commands"""
    await message.reply_text(
        "🎬 YouTube Video Downloader Bot\n\n"
        "Send me a YouTube URL to download videos\n\n"
        "Features:\n"
        "- Multiple format options\n"
        "- Automatic video+audio merging\n"
        "- Thumbnail support\n"
        "- No file size limits",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def url_handler(_, message: Message):
    """Handle YouTube URLs"""
    url = message.text.strip()
    
    # Validate URL
    if not ("youtube.com" in url or "youtu.be" in url):
        return await message.reply_text("❌ Please send a valid YouTube URL")
    
    try:
        # Get video info
        title, thumb_url, raw_formats = await get_video_info(url)
        formats = await parse_formats(raw_formats)
        
        # Store URL in session
        user_data[message.chat.id] = url
        
        # Create format buttons
        buttons = [
            [InlineKeyboardButton(
                f"{f['id']}: {f['ext']} ({f['res']}) {f['note']}",
                callback_data=f"dl_{f['id']}_{f['note']}"
            )]
            for f in formats
        ]
        
        await message.reply_text(
            f"📺 **{title}**\n\nSelect download format:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        await message.reply_text(str(e))

@app.on_callback_query(filters.regex(r"^dl_"))
async def format_handler(_, query: CallbackQuery):
    """Handle format selection"""
    await query.answer()
    
    # Get data from callback
    data = query.data.split('_')
    format_id = data[1]
    format_note = data[2]
    chat_id = query.message.chat.id
    
    # Get URL from session storage
    url = user_data.get(chat_id)
    if not url:
        return await query.message.edit_text("❌ Session expired. Please send the URL again")
    
    try:
        # Update status
        msg = await query.message.edit_text(f"⏳ Downloading format {format_id}...")
        
        # Download media
        media_path, thumb_path, title = await download_media(url, format_id, format_note)
        
        # Send to Telegram
        if media_path.endswith('.mp3'):
            await query.message.reply_audio(
                audio=media_path,
                caption=f"🎵 {title}",
                thumb=thumb_path,
                title=title[:64],  # Telegram limits title to 64 chars
                performer="YouTube"
            )
        else:
            await query.message.reply_video(
                video=media_path,
                caption=f"🎬 {title}",
                thumb=thumb_path,
                width=1280,
                height=720,
                supports_streaming=True
            )
        
        # Cleanup
        for f in [media_path, thumb_path]:
            if f and os.path.exists(f):
                os.remove(f)
        await msg.delete()
        
    except Exception as e:
        await query.message.edit_text(f"❌ Download failed: {str(e)}")
        # Ensure cleanup even if error occurs
        if 'media_path' in locals() and media_path and os.path.exists(media_path):
            os.remove(media_path)
        if 'thumb_path' in locals() and thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

# ===== MAIN =====
if __name__ == '__main__':
    print("✅ Bot is running...")
    app.run()
