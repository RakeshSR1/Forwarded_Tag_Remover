import math
import time
import os
from pyrogram.types import Message

async def format_progress_bar(current: int, total: int) -> str:
    """Create a bold Unicode progress bar with percentage."""
    if total == 0:
        percent = 0
    else:
        percent = (current / total) * 100
    filled_blocks = math.floor(percent / 10)
    empty_blocks = 10 - filled_blocks
    bar = "▓" * filled_blocks + "░" * empty_blocks
    return bar, f"{percent:.1f}%"


async def update_progress(
    current: int,
    total: int,
    task_type: str,
    file_count: int,
    user_name: str,
    message: Message
):
    """Send bold Unicode progress bar updates to Telegram."""
    bar, percent_str = await format_progress_bar(current, total)

    text = (
        f"𝐓𝐚𝐬𝐤 𝐒𝐭𝐚𝐫𝐭𝐞𝐝\n\n"
        f"𝐓𝐲𝐩𝐞 :- {task_type}\n"
        f"𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠 :- {bar} {percent_str}\n"
        f"𝐅𝐢𝐧𝐢𝐬𝐡𝐞𝐝 :- {percent_str}\n"
        f"𝐅𝐢𝐥𝐞𝐬 :- {file_count}\n"
        f"𝐁𝐲 :- {user_name}"
    )

    try:
        await message.edit_text(text)
    except Exception:
        pass


async def tg_progress(current, total, message, task_type, file_count, user_name):
    """Universal progress handler for Telegram uploads/downloads."""
    await update_progress(current, total, task_type, file_count, user_name, message)


# Example simulation (for testing without real download)
async def fake_task(message, user_name):
    total_size = 100
    file_count = 3
    for current_size in range(0, total_size + 1, 5):
        await update_progress(current_size, total_size, "Downloading", file_count, user_name, message)
        time.sleep(0.5)  # simulate task delay
