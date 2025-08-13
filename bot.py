#!/usr/bin/env python3
"""
Featured Bot:
- Channel: Remove forward tag (repost clean), bold if buttons exist, preserve buttons, delete original.
- DM/Group: /zip, /unzip, /compress (video), with progress bars.
"""

import os
import tempfile
import zipfile
import shutil
import asyncio
import logging
import time
import html
from typing import Optional, List

from pyrogram import Client, filters
from pyrogram.types import Message
from dotenv import load_dotenv

load_dotenv()

# ----------- Configuration from env ------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL", "").strip()  # optional -100...
DEST_CHANNEL = os.getenv("DEST_CHANNEL", "").strip()      # optional mirror channel -100...
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
MAX_UNZIP_FILES = int(os.getenv("MAX_UNZIP_FILES") or 30)

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise SystemExit("Please set API_ID, API_HASH and BOT_TOKEN in .env or environment variables")

# Behavior toggles
ALWAYS_BOLD = False   # keep False so bold only when buttons exist
BOLD_HEADER = ""      # optional header to put above bolded text

# Limits
MAX_ZIP_SIZE = 1_000_000_000  # 1GB safety limit for zip/compressed sends

# Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("featured-bot")

app = Client("featured_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ---------- helpers ----------
def safe_bold(text: Optional[str]) -> Optional[str]:
    """Return HTML-safe bolded text with optional header."""
    if not text:
        return None
    esc = html.escape(text)
    if BOLD_HEADER:
        return f"<b>{html.escape(BOLD_HEADER)}</b>\n\n<b>{esc}</b>"
    return f"<b>{esc}</b>"


async def edit_progress(m: Message, prefix: str, current: int, total: int, start: float):
    """Edit progress message (non-blocking calls scheduled)."""
    now = time.time()
    percent = (current / total * 100) if total else 0
    elapsed = now - start
    speed = (current / elapsed) if elapsed > 0 else 0
    text = f"{prefix}\n{percent:5.1f}% — {current}/{total} bytes\n{speed/1024:.1f} KB/s"
    try:
        await m.edit_text(text)
    except Exception:
        pass


def pyrogram_progress_wrapper(prefix: str, status_msg: Message):
    """Create a callback for pyrogram progress reporting (current, total)."""

    start = time.time()

    def progress(current, total):
        try:
            asyncio.get_event_loop().create_task(edit_progress(status_msg, prefix, current, total, start))
        except RuntimeError:
            # event loop not ready: ignore
            pass

    return progress


# ---------- Channel handler ----------
@app.on_message(filters.channel)
async def handle_channel_post(client: Client, message: Message):
    """
    When a channel post arrives:
    - If forwarded: copy to dest (or same channel) then delete original (removes forward header)
    - If not forwarded but has buttons: copy & bold caption/text and delete original
    """
    # Restrict to SOURCE_CHANNEL if set
    if SOURCE_CHANNEL:
        try:
            if message.chat.id != int(SOURCE_CHANNEL):
                return
        except Exception:
            pass

    is_forwarded = bool(
        message.forward_date or message.forward_from or message.forward_from_chat or message.forward_sender_name
    )
    has_buttons = bool(message.reply_markup)

    bold_needed = (ALWAYS_BOLD or has_buttons)

    try:
        target_chat = message.chat.id
        dest = int(DEST_CHANNEL) if DEST_CHANNEL else target_chat

        # Copy (this removes forwarded header)
        copied = await client.copy_message(
            chat_id=dest,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=message.reply_markup
        )

        # Bold if needed
        if bold_needed:
            try:
                if copied.caption is not None:
                    await client.edit_message_caption(
                        chat_id=dest,
                        message_id=copied.message_id,
                        caption=safe_bold(copied.caption),
                        parse_mode="html"
                    )
                elif copied.text is not None:
                    await client.edit_message_text(
                        chat_id=dest,
                        message_id=copied.message_id,
                        text=safe_bold(copied.text),
                        parse_mode="html",
                        disable_web_page_preview=True
                    )
            except Exception as e:
                log.info("Bold edit failed: %s", e)

        # Try delete original to hide forward header
        try:
            await message.delete()
        except Exception as e:
            log.info("Could not delete original (permissions?): %s", e)

    except Exception as e:
        log.exception("Channel handler failed: %s", e)


# ---------- Download helpers for Zip ----------
async def download_media_list(client: Client, messages: List[Message], out_dir: str, status_msg: Message):
    """
    Download one or multiple messages' media into out_dir.
    Returns list of file paths downloaded.
    """
    downloaded = []
    for m in messages:
        try:
            prefix = f"Downloading {m.message_id}"
            progress = pyrogram_progress_wrapper(prefix, status_msg)
            path = await client.download_media(m, file_name=out_dir, progress=progress, progress_args=())
            if path:
                downloaded.append(path)
        except Exception as e:
            log.info("Download failed for %s: %s", getattr(m, "message_id", None), e)
    return downloaded


# ---------- /zip ----------
@app.on_message(filters.private & filters.command("zip"))
@app.on_message(filters.group & filters.command("zip"))
async def cmd_zip(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("Reply to a message with media (or a media group) and send /zip")
        return

    target = message.reply_to_message
    msgs = [target]
    if target.media_group_id:
        # gather media group messages from history (small window)
        msgs = []
        async for m in client.get_history(target.chat.id, limit=100):
            if m.media_group_id == target.media_group_id:
                msgs.append(m)
        msgs = sorted(msgs, key=lambda x: x.message_id)

    status_msg = await message.reply_text("Preparing download...")
    tmpdir = tempfile.mkdtemp(prefix="zip_")
    try:
        downloaded = await download_media_list(client, msgs, tmpdir, status_msg)
        if not downloaded:
            await status_msg.edit_text("No downloadable media found.")
            return

        zip_path = os.path.join(tempfile.gettempdir(), f"files_{message.from_user.id}_{message.message_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in downloaded:
                zf.write(fp, arcname=os.path.basename(fp))

        size = os.path.getsize(zip_path)
        if size > MAX_ZIP_SIZE:
            await status_msg.edit_text("ZIP is too large to send.")
            os.remove(zip_path)
            return

        send_msg = await status_msg.edit_text("Uploading ZIP...")
        progress_cb = pyrogram_progress_wrapper("Uploading ZIP", send_msg)
        await message.reply_document(document=zip_path, caption="Here is your ZIP ✅", progress=progress_cb, progress_args=())
        await send_msg.delete()
    except Exception as e:
        log.exception("Zip failed: %s", e)
        try:
            await status_msg.edit_text(f"ZIP failed: {e}")
        except Exception:
            pass
    finally:
        for f in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, f))
            except Exception:
                pass
        try:
            os.rmdir(tmpdir)
        except Exception:
            pass


# ---------- /unzip ----------
@app.on_message(filters.private & filters.command("unzip"))
@app.on_message(filters.group & filters.command("unzip"))
async def cmd_unzip(client: Client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.document:
        await message.reply_text("Reply to a .zip file and send /unzip")
        return

    doc = message.reply_to_message.document
    fname = doc.file_name or ""
    if not fname.lower().endswith(".zip"):
        await message.reply_text("That file is not a .zip")
        return

    status_msg = await message.reply_text("Downloading ZIP...")
    tmpdir = tempfile.mkdtemp(prefix="unzip_")
    zip_path = os.path.join(tmpdir, fname)
    try:
        progress_cb = pyrogram_progress_wrapper("Downloading ZIP", status_msg)
        await client.download_media(message.reply_to_message, file_name=zip_path, progress=progress_cb, progress_args=())

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            if len(namelist) > MAX_UNZIP_FILES:
                await status_msg.edit_text(f"ZIP contains too many files ({len(namelist)}). Limit is {MAX_UNZIP_FILES}.")
                return

            await status_msg.edit_text(f"Extracting {len(namelist)} files...")
            for member in namelist:
                safe_name = os.path.basename(member)
                if not safe_name:
                    continue
                out_path = os.path.join(tmpdir, safe_name)
                with open(out_path, "wb") as out_f:
                    out_f.write(zf.read(member))

                send_status = await message.reply_text(f"Uploading {safe_name}...")
                up_cb = pyrogram_progress_wrapper(f"Uploading {safe_name}", send_status)
                await message.reply_document(document=out_path, progress=up_cb, progress_args=())
                try:
                    await send_status.delete()
                except Exception:
                    pass
                try:
                    os.remove(out_path)
                except Exception:
                    pass
        await status_msg.delete()
    except Exception as e:
        log.exception("Unzip failed: %s", e)
        try:
            await status_msg.edit_text(f"Unzip failed: {e}")
        except Exception:
            pass
    finally:
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


# ---------- Video compress (ffmpeg) ----------
async def ffmpeg_compress(input_path: str, output_path: str, crf: int = 28, preset: str = "veryfast"):
    """Asynchronously run ffmpeg to compress video."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vcodec", "libx264", "-crf", str(crf), "-preset", preset,
        "-acodec", "aac", "-b:a", "128k",
        output_path
    ]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout, stderr


@app.on_message(filters.private & filters.command("compress"))
@app.on_message(filters.group & filters.command("compress"))
async def cmd_compress(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("Reply to a video (or file) and use /compress [low|medium|high]")
        return

    target = message.reply_to_message
    if not (target.video or target.document):
        await message.reply_text("Reply to a video or a file containing a video.")
        return

    args = message.text.split(maxsplit=1)
    quality = args[1].strip().lower() if len(args) > 1 else "medium"
    crf_map = {"high": 22, "medium": 26, "low": 30}
    crf = crf_map.get(quality, 28)

    status_msg = await message.reply_text("Downloading video...")
    tmpdir = tempfile.mkdtemp(prefix="vcomp_")
    try:
        prog = pyrogram_progress_wrapper("Downloading video", status_msg)
        in_path = await client.download_media(target, file_name=tmpdir, progress=prog, progress_args=())
        if not in_path:
            await status_msg.edit_text("Download failed.")
            return

        await status_msg.edit_text("Compressing video (ffmpeg)...")
        out_path = os.path.join(tmpdir, f"compressed_{os.path.basename(in_path)}")
        rc, so, se = await ffmpeg_compress(in_path, out_path, crf=crf, preset="veryfast")
        if rc != 0:
            await status_msg.edit_text("FFmpeg failed. See logs.")
            log.error("ffmpeg stderr: %s", se.decode(errors="ignore"))
            return

        size = os.path.getsize(out_path)
        if size > MAX_ZIP_SIZE:
            await status_msg.edit_text("Compressed file is too large to send.")
            return

        await status_msg.edit_text("Uploading compressed file...")
        up_msg = await message.reply_text("Uploading...")
        up_cb = pyrogram_progress_wrapper("Uploading compressed video", up_msg)
        await message.reply_document(document=out_path, caption="Compressed video ✅", progress=up_cb, progress_args=())
        try:
            await up_msg.delete()
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        log.exception("Compress failed: %s", e)
        try:
            await status_msg.edit_text(f"Compress failed: {e}")
        except Exception:
            pass
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------- Owner commands ----------
@app.on_message(filters.private & filters.command("status"))
async def cmd_status(client: Client, message: Message):
    if OWNER_ID and message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.")
    await message.reply_text(
        f"Running\nSOURCE_CHANNEL={SOURCE_CHANNEL or '(all)'}\nDEST_CHANNEL={DEST_CHANNEL or '(same)'}\nALWAYS_BOLD={ALWAYS_BOLD}\nBOLD_HEADER={BOLD_HEADER or '(none)'}"
    )


@app.on_message(filters.private & filters.command("set_header"))
async def cmd_set_header(client: Client, message: Message):
    global BOLD_HEADER
    if OWNER_ID and message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.")
    args = message.text.split(maxsplit=1)
    BOLD_HEADER = args[1].strip() if len(args) > 1 else ""
    await message.reply_text(f"BOLD_HEADER set to: {BOLD_HEADER or '(none)'}")


@app.on_message(filters.private & filters.command("set_always_bold"))
async def cmd_set_always_bold(client: Client, message: Message):
    global ALWAYS_BOLD
    if OWNER_ID and message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.")
    args = message.text.split(maxsplit=1)
    val = args[1].strip().lower() if len(args) > 1 else "false"
    ALWAYS_BOLD = (val == "true")
    await message.reply_text(f"ALWAYS_BOLD = {ALWAYS_BOLD}")


# ---------- start ----------
if __name__ == "__main__":
    print("𝐅𝐨𝐫𝐰𝐚𝐫𝐝𝐞𝐝 𝐓𝐚𝐠 𝐑𝐞𝐦𝐨𝐯𝐞𝐫 𝐁𝐨𝐭 𝐈𝐬 𝐒𝐭𝐚𝐫𝐭𝐢𝐧𝐠 𝐓𝐡𝐢𝐬 𝐁𝐨𝐭 𝐇𝐚𝐯𝐞 𝐌𝐚𝐧𝐲 𝐅𝐞𝐚𝐭𝐮𝐫𝐞𝐬 𝐒𝐞𝐞 𝐌𝐞𝐧𝐮 𝐁𝐮𝐭𝐭𝐨𝐧..")
    app.run()
