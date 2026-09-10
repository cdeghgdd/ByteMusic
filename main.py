import asyncio
import os
import re
import shutil
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from yt_dlp import YoutubeDL


DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 48 * 1024 * 1024


def is_youtube_url(text: str) -> bool:
    return bool(re.search(
        r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)",
        text or "",
        re.IGNORECASE
    ))


def download_audio(url: str):
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
        mp3_file = str(Path(filename).with_suffix(".mp3"))

    return mp3_file, info


def download_video(url: str):
    output = str(DOWNLOAD_DIR / "%(title).80s.%(ext)s")

    options = {
        "format": "best[ext=mp4][height<=720]/best[height<=720]/best",
        "outtmpl": output,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    mp4_file = str(Path(filename).with_suffix(".mp4"))

    if not Path(mp4_file).exists():
        candidates = list(DOWNLOAD_DIR.glob("*"))
        if candidates:
            mp4_file = str(max(candidates, key=lambda p: p.stat().st_mtime))

    return mp4_file, info


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 ByteMusic\n\n"
        "لینک YouTube رو بفرست تا برات دانلود کنم.\n\n"
        "مثال:\n"
        "https://youtube.com/watch?v=..."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 ByteMusic\n\n"
        "فقط لینک YouTube بفرست.\n"
        "بات صدا را به صورت MP3 برایت ارسال می‌کند."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    if not is_youtube_url(url):
        await update.message.reply_text(
            "❌ لطفاً یک لینک معتبر YouTube بفرست."
        )
        return

    status = await update.message.reply_text(
        "⏳ در حال دریافت اطلاعات و دانلود..."
    )

    try:
        file_path, info = await asyncio.to_thread(
            download_audio,
            url
        )

        path = Path(file_path)

        if not path.exists():
            raise RuntimeError("فایل دانلود نشد.")

        size = path.stat().st_size

        if size > MAX_FILE_SIZE:
            path.unlink(missing_ok=True)
            await status.edit_text(
                "❌ حجم فایل برای ارسال در تلگرام زیاد است."
            )
            return

        title = info.get("title", "ByteMusic")
        artist = info.get("artist") or info.get("uploader") or "YouTube"

        await status.edit_text("📤 در حال ارسال فایل...")

        with path.open("rb") as audio:
            await update.message.reply_audio(
                audio=audio,
                title=title[:64],
                performer=artist[:64],
                caption=f"🎵 {title}\n\n@ByteTunnel"
            )

        await status.delete()

        path.unlink(missing_ok=True)

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")

        await status.edit_text(
            "❌ دانلود انجام نشد.\n"
            "ممکن است ویدیو محدود، حذف‌شده یا قابل دسترسی نباشد."
        )

        # پاک کردن فایل‌های باقی‌مانده
        for file in DOWNLOAD_DIR.glob("*"):
            try:
                file.unlink()
            except Exception:
                pass


def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError("BOT_TOKEN is not set.")

    if not shutil.which("ffmpeg"):
        print("WARNING: ffmpeg not found.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("ByteMusic Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
