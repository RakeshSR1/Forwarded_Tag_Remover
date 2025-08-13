import os
import aiofiles
import asyncio
import zipfile
import ffmpeg
from pyrogram.types import Message

async def progress_bar(current, total, message: Message, start_time):
    percent = current * 100 / total
    await message.edit_text(f"Progress: {percent:.1f}%")

async def zip_file(input_path, output_path):
    with zipfile.ZipFile(output_path, 'w') as zipf:
        if os.path.isdir(input_path):
            for root, dirs, files in os.walk(input_path):
                for file in files:
                    zipf.write(os.path.join(root, file))
        else:
            zipf.write(input_path)

async def unzip_file(zip_path, extract_path):
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        zipf.extractall(extract_path)

async def compress_video(input_path, output_path):
    (
        ffmpeg
        .input(input_path)
        .output(output_path, vcodec='libx265', crf=28)
        .run(overwrite_output=True)
    )
