# Featured Telegram Bot (Zip / Unzip / Video Compress + Channel Forward Cleaner)

## Features
- DM/Group:
  - `/zip` (reply to media message or media group) → returns .zip
  - `/unzip` (reply to .zip doc) → extracts up to `MAX_UNZIP_FILES`
  - `/compress [low|medium|high]` (reply to a video/file) → compress video via ffmpeg
  - Progress updates shown while downloading/uploading
- Channel:
  - Automatically remove "Forwarded from..." by copying message and deleting original (bot must be admin)
  - If message has inline buttons (reply_markup) → repost with caption/text bolded (buttons preserved)
  - Optional mirror channel via `DEST_CHANNEL`

## Requirements
- Python 3.9+
- ffmpeg installed on host (Debian/Ubuntu: `sudo apt update && sudo apt install ffmpeg -y`)

## Setup (local)
1. Copy repo files.
2. Create `.env` with required values (see `sample.env`).
3. Install deps:
