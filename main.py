import asyncio
import os
import re
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
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 48 * 1024 * 1024


def spotify_client():
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    try:
        auth = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        return spotipy.Spotify(auth_manager=auth)
    except Exception as e:
        print("[Spotify]", e)
        return None


def search_youtube(query):
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "playlistend": 5,
    }

    with YoutubeDL(options) as ydl:
        data = ydl.extract_info(
            f"ytsearch5:{query}",
            download=False
        )

    results = []

    for item in data.get("entries", []):
        if not item:
            continue

        results.append({
            "title": item.get("title", "Unknown"),
            "url": item.get("webpage_url")
                   or f"https://www.youtube.com/watch?v={item.get('id')}",
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
            limit=5
        )

        results = []

        for track in data["tracks"]["items"]:
            artists = ", ".join(
                artist["name"] for artist in track["artists"]
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
        print("[Spotify Search]", e)
        return []


def download_mp3(url):
    output = str(DOWNLOAD_DIR / "%(title).80s.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
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

    return mp3, info


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 ByteMusic\n\n"
        "اسم آهنگ یا خواننده رو بفرست.\n\n"
        "مثلاً:\n"
        "The Weeknd Blinding Lights\n\n"
        "🔎 خودم برات جستجو می‌کنم."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 ByteMusic\n\n"
        "اسم آهنگ یا خواننده رو بفرست تا جستجو کنم و "
        "نسخه MP3 رو برات آماده کنم."
    )


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()

    if len(query) < 2:
        return

    status = await update.message.reply_text(
        "🔎 در حال جستجوی آهنگ..."
    )

    try:
        youtube_results = await asyncio.to_thread(
            search_youtube,
            query
        )

        spotify_results = await asyncio.to_thread(
            search_spotify,
            query
        )

        if not youtube_results and not spotify_results:
            await status.edit_text(
                "❌ آهنگی پیدا نشد."
            )
            return

        context.user_data["youtube_results"] = youtube_results

        buttons = []

        # نتایج Spotify
        for i, track in enumerate(spotify_results[:3]):
            buttons.append([
                InlineKeyboardButton(
                    f"🎵 {track['name']} — {track['artist']}"[:60],
                    callback_data=f"sp:{i}"
                )
            ])

        # نتایج YouTube
        for i, video in enumerate(youtube_results[:5]):
            duration = video.get("duration") or ""
            label = f"▶️ {video['title']}"
            if duration:
                label += f" [{duration}]"

            buttons.append([
                InlineKeyboardButton(
                    label[:60],
                    callback_data=f"yt:{i}"
                )
            ])

        await status.edit_text(
            "🎵 نتایج پیدا شد\n\n"
            "روی آهنگ موردنظرت بزن تا MP3 آماده بشه:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        print("[SEARCH ERROR]", type(e).__name__, e)

        await status.edit_text(
            "❌ هنگام جستجو خطایی رخ داد."
        )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("sp:"):
        index = int(data.split(":")[1])

        spotify_results = await asyncio.to_thread(
            search_spotify,
            context.user_data.get("last_query", "")
        )

        if index >= len(spotify_results):
            await query.message.reply_text("❌ نتیجه دیگر موجود نیست.")
            return

        track = spotify_results[index]

        youtube_query = track["query"]

        await query.message.edit_text(
            f"🔎 پیدا شد:\n"
            f"🎵 {track['name']}\n"
            f"👤 {track['artist']}\n\n"
            f"⏳ در حال پیدا کردن نسخه صوتی..."
        )

        try:
            results = await asyncio.to_thread(
                search_youtube,
                youtube_query
            )

            if not results:
                await query.message.edit_text(
                    "❌ نسخه قابل دریافت پیدا نشد."
                )
                return

            path, info = await asyncio.to_thread(
                download_mp3,
                results[0]["url"]
            )

            await send_audio(
                query.message,
                path,
                track["name"],
                track["artist"]
            )

        except Exception as e:
            print("[SPOTIFY DOWNLOAD]", type(e).__name__, e)
            await query.message.edit_text(
                "❌ دریافت آهنگ انجام نشد."
            )

        return

    if data.startswith("yt:"):
        index = int(data.split(":")[1])

        results = context.user_data.get("youtube_results", [])

        if index >= len(results):
            await query.message.reply_text(
                "❌ نتیجه دیگر موجود نیست."
            )
            return

        selected = results[index]

        await query.message.edit_text(
            f"🎵 {selected['title']}\n\n"
            f"⏳ در حال دانلود و تبدیل به MP3..."
        )

        try:
            path, info = await asyncio.to_thread(
                download_mp3,
                selected["url"]
            )

            await send_audio(
                query.message,
                path,
                info.get("title", selected["title"]),
                info.get("artist") or info.get("uploader", "ByteMusic")
            )

        except Exception as e:
            print("[YOUTUBE DOWNLOAD]", type(e).__name__, e)

            await query.message.edit_text(
                "❌ دانلود آهنگ انجام نشد."
            )


async def send_audio(message, path, title, artist):
    path = Path(path)

    if not path.exists():
        raise RuntimeError("MP3 file not found")

    if path.stat().st_size > MAX_FILE_SIZE:
        path.unlink(missing_ok=True)
        await message.edit_text(
            "❌ حجم فایل برای ارسال زیاد است."
        )
        return

    with path.open("rb") as audio:
        await message.reply_audio(
            audio=audio,
            title=str(title)[:64],
            performer=str(artist)[:64],
            caption="🎵 ByteMusic\n\n@ByteTunnel"
        )

    path.unlink(missing_ok=True)

    try:
        await message.delete()
    except Exception:
        pass


async def capture_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["last_query"] = update.message.text.strip()
    await handle_search(update, context)


def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    print("ByteMusic starting...")
    print("FFmpeg:", shutil.which("ffmpeg"))
    print("Spotify:", "enabled" if spotify_client() else "disabled")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            capture_query
        )
    )

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
