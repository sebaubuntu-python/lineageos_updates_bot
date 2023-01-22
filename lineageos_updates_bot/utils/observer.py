#
# Copyright (C) 2023 Sebastiano Barezzi
#
# SPDX-License-Identifier: MIT
#

from asyncio import Event, sleep
from datetime import datetime
from liblineage.hudson.build_target import BuildTarget
from liblineage.ota.full_update_info import FullUpdateInfo
from sebaubuntu_libs.libexception import format_exception
from sebaubuntu_libs.liblogging import LOGE, LOGI
from telegram import Bot
from typing import Dict, Union

from lineageos_updates_bot.utils.poster import Poster

class Observer:
	def __init__(self, poster: Poster, bot: Bot, chat_id: Union[str, int]) -> None:
		self.poster = poster
		self.bot = bot
		self.chat_id = chat_id

		self.event = Event()
		self.last_device_post: Dict[str, datetime] = {}

		now = datetime.now()
		for build_target in BuildTarget.get_lineage_build_targets():
			self.last_device_post[build_target.device] = now

	async def observe(self):
		while True:
			await self.event.wait()

			try:
				build_targets = BuildTarget.get_lineage_build_targets()
			except Exception as e:
				LOGE(f"Can't get build targets: {format_exception(e)}")
				continue

			for device in [build_target.device for build_target in build_targets]:
				try:
					response = FullUpdateInfo.get_nightlies(device)
				except Exception:
					response = []

				if not response:
					LOGI(f"No updates for {device}")
					continue

				last_update = response[-1]

				build_date = last_update.datetime
				if device in self.last_device_post and build_date <= self.last_device_post[device]:
					continue

				self.last_device_post[device] = build_date

				try:
					await self.poster.post(device, last_update, self.bot, self.chat_id)
				except Exception as e:
					LOGE(f"Failed to post {device} {build_date} build\n"
					     f"{format_exception(e)}")

			# Wait 10 minutes
			await sleep(10 * 60)

	def set_start_date(self, date: datetime):
		for build_target in BuildTarget.get_lineage_build_targets():
			self.last_device_post[build_target.device] = date
