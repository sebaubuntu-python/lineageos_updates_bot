#
# Copyright (C) 2023 Sebastiano Barezzi
#
# SPDX-License-Identifier: MIT
#

from liblineage.constants.versions import LINEAGEOS_TO_ANDROID_VERSION
from liblineage.ota.full_update_info import FullUpdateInfo
from liblineage.wiki.device_data import DeviceData
from sebaubuntu_libs.liblogging import LOGE
from telegram import Bot
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from typing import Union

class Poster:
	async def post(self, codename: str, update: FullUpdateInfo, bot: Bot, chat_id: Union[str, int]):
		chat = await bot.get_chat(chat_id=chat_id)
		device_data = DeviceData.get_device_data(codename)
		text = (
			f"{escape_markdown(f'#{codename}', 2)} {escape_markdown(f'#{LINEAGEOS_TO_ANDROID_VERSION[update.version].version_short.lower()}', 2)}\n"
			f"*LineageOS {escape_markdown(update.version, 2)} for {escape_markdown(device_data.vendor, 2)} {escape_markdown(device_data.name, 2)} {escape_markdown(f'({codename})', 2)}*\n"
			f"\n"
			f"Build date: {escape_markdown(update.datetime.strftime('%Y/%m/%d'), 2)}\n"
			f"Download: [Here]({escape_markdown(f'https://download.lineageos.org/{codename}', 2)})\n"
			f"Device wiki page: [Here]({escape_markdown(f'https://wiki.lineageos.org/devices/{codename}', 2)})\n"
			f"Installation instructions: [Here]({escape_markdown(f'https://wiki.lineageos.org/devices/{codename}/install', 2)})\n"
			f"\n"
		)
		if chat.username:
			text += (
				f"@{escape_markdown(chat.username, 2)}\n"
			)

		try:
			await chat.send_message(text, parse_mode=ParseMode.MARKDOWN_V2)
		except Exception as e:
			LOGE(
				f"Error: {e}\n"
				f"{text}\n"
			)
			# Reraise exception
			raise e
