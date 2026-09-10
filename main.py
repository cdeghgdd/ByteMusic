import os
import asyncio
import shutil
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from yt_dlp import YoutubeDL

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except ImportError:
    spotipy = None

BOT_TOKEN = os.getenv("BOT_TOKEN")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 48 * 1024 * 1024


def spotify_client():
    if not spotipy:
        return None

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    try:
        auth = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
        return spotipy.Spotify(auth_manager=auth)
    except Exception as e:
        print("[Spotify]", type(e).__name__, e)
        return None


def search_youtube(query):
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "playlistend": 8,
    }

    with YoutubeDL(options) as ydl:
        data = ydl.extract_info(
            f"ytsearch8:{query}",
            download=False,
        )

    results = []

    for item in data.get("entries", []):
        if not item:
            continue

        video_id = item.get("id")
        url = item.get("webpage_url")

        if not url and video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"

        if not url:
            continue

        results.append({
            "title": item.get("title", "Unknown"),
            "url": url,
            "duration": item.get("duration_string", ""),
        })

    return results


def search_spotify(query):
    sp = spotify_client()

    if not sp:
        return []

    try:
        data = sp.search(
            q=query,
            type="track",
            limit=5,
        )

        results = []

        for track in data["tracks"]["items"]:
            artists = ", ".join(
                artist["name"]
                for artist in track["artists"]
            )

            results.append({
                "name": track["name"],
                "artist": artists,
                "album": track["album"]["name"],
                "url": track["external_urls"]["spotify"],
                "query": f"{track['name']} {artists}",
            })

        return results

    except Exception as e:
        print("[Spotify Search]", type(e).__name__, e)
        return []


def download_mp3(url):
    output = str(
        DOWNLOAD_DIR /
        "%(id)s.%(ext)s"
    )

    options = {
        "format": "bestaudio/best",
        "outtmpl": output,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "socket_timeout": 25,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    mp3 = Path(filename).with_suffix(".mp3")

    if not mp3.exists():
        raise RuntimeError("MP3 file was not created")

    return mp3, info


def cleanup_downloads():
    for file in DOWNLOAD_DIR.iterdir():
        try:
            if file.is_file():
                file.unlink()
        except Exception:
            pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 ByteMusic\n\n"
        "اسم آهنگ یا خواننده رو بفرست.\n\n"
        "مثال:\n"
        "The Weeknd Blinding Lights\n\n"
        "🔎 در حال جستجو..."
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "مثال:\n/search The Weeknd Blinding Lights"
        )
        return

    query = " ".join(context.args)
    await handle_search(update, context, query)


async def handle_search(update, context, query):
    msg = await update.message.reply_text(
        f"🔎 در حال جستجو برای:\n"
        f"🎵 {query}"
    )

    try:
        spotify_results = await asyncio.to_thread(
            search_spotify,
            query,
        )

        youtube_results = await asyncio.to_thread(
            search_youtube,
            query,
        )

    except Exception as e:
        print("[SEARCH]", type(e).__name__, e)

        await msg.edit_text(
            "❌ جستجو انجام نشد.\n"
            "لطفاً دوباره امتحان کن."
        )
        return

    context.user_data["spotify_results"] = spotify_results
    context.user_data["youtube_results"] = youtube_results

    buttons = []

    for i, item in enumerate(spotify_results[:3]):
        buttons.append([
            InlineKeyboardButton(
                f"🟢 {item['name'][:35]}",
                callback_data=f"sp:{i}",
            )
        ])

    for i, item in enumerate(youtube_results[:5]):
        title = item["title"][:35]

        buttons.append([
            InlineKeyboardButton(
                f"▶️ {title}",
                callback_data=f"yt:{i}",
            )
        ])

    if not buttons:
        await msg.edit_text(
            "❌ چیزی پیدا نشد.\n"
            "اسم آهنگ یا خواننده را دوباره امتحان کن."
        )
        return

    await msg.edit_text(
        f"🎵 نتایج برای:\n"
        f"{query}\n\n"
        f"🟢 Spotify\n"
        f"▶️ YouTube\n\n"
        f"یکی را انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()

    if not query:
        return

    if len(query) > 150:
        await update.message.reply_text(
            "❌ عبارت جستجو خیلی طولانی است."
        )
        return

    await handle_search(update, context, query)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("sp:"):
        index = int(data.split(":")[1])

        results = context.user_data.get(
            "spotify_results",
            [],
        )

        if index >= len(results):
            await query.message.reply_text(
                "❌ این نتیجه دیگر موجود نیست."
            )
            return

        track = results[index]

        await query.message.edit_text(
            f"🟢 {track['name']}\n"
            f"👤 {track['artist']}\n\n"
            f"🔎 پیدا کردن نسخه قابل دریافت..."
        )

        try:
            youtube_results = await asyncio.to_thread(
                search_youtube,
                track["query"],
            )

            if not youtube_results:
                await query.message.edit_text(
                    "❌ نسخه قابل دریافت پیدا نشد."
                )
                return

            context.user_data["download_results"] = youtube_results
            context.user_data["download_title"] = track["name"]
            context.user_data["download_artist"] = track["artist"]

            buttons = []

            for i, item in enumerate(youtube_results[:5]):
                buttons.append([
                    InlineKeyboardButton(
                        f"▶️ {item['title'][:38]}",
                        callback_data=f"spyt:{i}",
                    )
                ])

            await query.message.edit_text(
                f"🎵 {track['name']}\n"
                f"👤 {track['artist']}\n\n"
                f"نسخه موردنظر را انتخاب کن:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

        except Exception as e:
            print("[SPOTIFY SEARCH]", type(e).__name__, e)

            await query.message.edit_text(
                "❌ جستجوی نسخه آهنگ انجام نشد."
            )

        return

    if data.startswith("spyt:"):
        index = int(data.split(":")[1])

        results = context.user_data.get(
            "download_results",
            [],
        )

        if index >= len(results):
            await query.message.reply_text(
                "❌ نتیجه دیگر موجود نیست."
            )
            return

        selected = results[index]

        title = context.user_data.get(
            "download_title",
            selected["title"],
        )

        artist = context.user_data.get(
            "download_artist",
            "ByteMusic",
        )

        await download_selected(
            query,
            selected["url"],
            title,
            artist,
        )

        return

    if data.startswith("yt:"):
        index = int(data.split(":")[1])

        results = context.user_data.get(
            "youtube_results",
            [],
        )

        if index >= len(results):
            await query.message.reply_text(
                "❌ نتیجه دیگر موجود نیست."
            )
            return

        selected = results[index]

        await download_selected(
            query,
            selected["url"],
            selected["title"],
            "ByteMusic",
        )


async def download_selected(query, url, title, artist):
    await query.message.edit_text(
        f"🎵 {title}\n\n"
        f"⏳ در حال دریافت و تبدیل به MP3..."
    )

    try:
        path, info = await asyncio.to_thread(
            download_mp3,
            url,
        )

        await send_audio(
            query.message,
            path,
            title,
            artist,
        )

    except Exception as e:
        print(
            "[DOWNLOAD]",
            type(e).__name__,
            e,
        )

        # جلوگیری از باقی ماندن فایل‌های ناقص
        cleanup_downloads()

        error_text = str(e).lower()

        if (
            "sign in to confirm" in error_text
            or "not a bot" in error_text
        ):
            await query.message.edit_text(
                "❌ YouTube این نتیجه را برای سرور مسدود کرده.\n\n"
                "یک نتیجه دیگر را امتحان کن."
            )
        elif "ffmpeg" in error_text:
            await query.message.edit_text(
                "❌ تبدیل MP3 انجام نشد؛ FFmpeg روی سرور در دسترس نیست."
            )
        else:
            await query.message.edit_text(
                "❌ دانلود این نتیجه انجام نشد.\n\n"
                "یک نتیجه دیگر را امتحان کن."
            )


async def send_audio(message, path, title, artist):
    path = Path(path)

    if not path.exists():
        raise RuntimeError("MP3 file not found")

    size = path.stat().st_size

    if size > MAX_FILE_SIZE:
        path.unlink(missing_ok=True)

        await message.edit_text(
            "❌ حجم فایل برای ارسال زیاد است."
        )
        return

    try:
        with path.open("rb") as audio:
            await message.reply_audio(
                audio=audio,
                title=str(title)[:64],
                performer=str(artist)[:64],
                caption="🎵 ByteMusic\n\n@ByteTunnel",
            )

        await message.delete()

    finally:
        path.unlink(missing_ok=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 ByteMusic\n\n"
        "اسم آهنگ یا خواننده را بفرست.\n"
        "مثال:\n"
        "The Weeknd Blinding Lights\n\n"
        "بات نتایج Spotify و YouTube را جستجو می‌کند."
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("search", search_command)
    )

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_message,
        )
    )

    print("ByteMusic started")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
