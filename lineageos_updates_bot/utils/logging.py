#
# Copyright (C) 2023 Sebastiano Barezzi
#
# SPDX-License-Identifier: MIT
#

from typing import Optional, Union
from telegram import Bot
from sebaubuntu_libs.liblogging import LOGE

import config

LOGGING_CHAT_ID: Optional[Union[int, str]] = config.LOGGING_CHAT_ID

async def log_to_logging_chat(bot: Bot, text: str):
	"""Send a message to the logging chat."""
	if LOGGING_CHAT_ID is None:
		return

	try:
		await bot.send_message(chat_id=LOGGING_CHAT_ID, text=text)
	except Exception as e:
		LOGE(f"Failed to send message to logging chat: {e}")

async def log(bot: Bot, text: str):
	"""Print a message to stdout and to the logging chat."""
	LOGE(text)

	await log_to_logging_chat(bot, text)
