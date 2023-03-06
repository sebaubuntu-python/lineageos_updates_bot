#
# Copyright (C) 2023 Sebastiano Barezzi
#
# SPDX-License-Identifier: MIT
#

from asyncio import CancelledError, Task, get_event_loop
from datetime import datetime
from humanize import naturalsize
from liblineage.device import Device
from liblineage.ota.full_update_info import FullUpdateInfo
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackContext, CommandHandler
from telegram.helpers import escape_markdown
from typing import Optional, Union

import config
from lineageos_updates_bot.utils.observer import Observer
from lineageos_updates_bot.utils.poster import Poster

class LineageOSUpdatesBot:
	def __init__(self, token: str, chat_id: Optional[Union[str, int]]) -> None:
		self.chat_id = chat_id

		self.application = (Application.builder()
		                    .token(token)
		                    .build())
		self.poster = Poster()
		self.observer: Optional[Observer] = None

		self.commands = [
			(k, v) for k, v in {
				"device_info": "Get device informations and specs",
				"lineageos": "Get the latest LineageOS build for a device",
				"when": "Get when the next update for a device will be available",
			}.items()
		]

		self.lineageos_updates_commands = {
			"disable": self.disable,
			"enable": self.enable,
			"dump": self.dump,
			"set_start_date": self.set_start_date,
			"test_post": self.test_post,
		}
		self.lineageos_updates_help_text = "\n".join([
			"Available commands:",
			*self.lineageos_updates_commands.keys()
		])

	def run(self):
		loop = get_event_loop()

		# Start the bot
		loop.run_until_complete(self.application.initialize())

		# Add handlers
		self.application.add_handler(CommandHandler(["start"], self.start))
		self.application.add_handler(CommandHandler(["device_info"], self.device_info))
		self.application.add_handler(CommandHandler(["lineageos"], self.lineageos))
		self.application.add_handler(CommandHandler(["lineageos_updates"], self.lineageos_updates))
		self.application.add_handler(CommandHandler(["when"], self.when))

		# Finish initialization
		loop.run_until_complete(self.application.bot.set_my_commands(self.commands)) # type: ignore
		loop.run_until_complete(self.application.start())
		assert self.application.updater is not None
		loop.run_until_complete(self.application.updater.start_polling())

		# Start the observer
		observer_task: Optional[Task] = None
		if self.chat_id is not None:
			self.observer = Observer(self.poster, self.application.bot, self.chat_id)
			self.observer.event.set()
			observer_task = loop.create_task(self.observer.observe())

		# Make the loop run forever
		loop.run_forever()

		# Stop the observer
		if observer_task:
			observer_task.cancel()
			try:
				loop.run_until_complete(observer_task)
			except CancelledError:
				pass

		# Stop the bot
		loop.run_until_complete(self.application.updater.stop())
		loop.run_until_complete(self.application.stop())
		loop.run_until_complete(self.application.shutdown())

	def user_is_admin(self, user_id: int):
		return user_id in config.ADMINS

	# Command handlers

	async def start(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		await update.message.reply_text("LineageOS updates bot up and running")

	async def device_info(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not context.args or len(context.args) < 1:
			await update.message.reply_text("Device codename not specified")
			return

		device = Device(context.args[0])
		try:
			device_data = device.get_device_data()
		except Exception:
			await update.message.reply_text("Error: Device not found")
			return

		await update.message.reply_text(f"{device_data}", disable_web_page_preview=True)

	async def lineageos(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not context.args or len(context.args) < 1:
			await update.message.reply_text("Device codename not specified")
			return

		device = Device(context.args[0])
		nightlies = device.get_nightlies()
		if not nightlies:
			await update.message.reply_text(f"Error: no updates found for {device.codename}")
			return

		last_update = nightlies[-1]
		await update.message.reply_text(f"Last update for {escape_markdown(device.codename, 2)}:\n"
										f"Version: {escape_markdown(last_update.version, 2)}\n"
										f"Date: {last_update.datetime.strftime('%Y/%m/%d')}\n"
										f"Size: {escape_markdown(naturalsize(last_update.size), 2)}\n"
										f"Download: [{escape_markdown(last_update.filename, 2)}]({escape_markdown(last_update.url, 2)})",
										parse_mode=ParseMode.MARKDOWN_V2)

	async def lineageos_updates(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not update.message.from_user or not self.user_is_admin(update.message.from_user.id):
			await update.message.reply_text("Error: You are not authorized to use this command")
			return

		if not context.args:
			await update.message.reply_text(
				"Error: No argument provided\n\n"
				f"{self.lineageos_updates_help_text}"
			)
			return

		command = context.args[0]

		if command not in self.lineageos_updates_commands:
			await update.message.reply_text(
				f"Error: Unknown command {command}\n\n"
				f"{self.lineageos_updates_help_text}"
			)
			return

		func = self.lineageos_updates_commands[command]

		await func(update, context)

	async def when(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not context.args or len(context.args) < 1:
			await update.message.reply_text("Device codename not specified")
			return

		device = Device(context.args[0])

		try:
			device_data = device.get_device_data()
		except Exception:
			device_data = None

		try:
			build_target = device.get_hudson_build_target()
		except Exception:
			await update.message.reply_text(f"Error: Device {'unmaintained' if device_data else 'not found'}")
			return

		device_info = (f"{device_data.vendor} {device_data.name} ({device_data.codename})"
					if device_data
					else f"{device.codename}")

		await update.message.reply_text(
			f"The next build for {device_info} will be on {build_target.get_next_build_date()}"
		)

	# lineageos_update functions
	async def disable(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not self.observer:
			await update.message.reply_text("Observer not ready yet")
			return

		self.observer.event.clear()
		await update.message.reply_text("Observer disabled")

	async def enable(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not self.observer:
			await update.message.reply_text("Observer not ready yet")
			return

		self.observer.event.set()
		await update.message.reply_text("Observer enabled")

	async def dump(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not self.observer:
			await update.message.reply_text("Observer not ready yet")
			return

		alive = self.observer.event.is_set()
		caption = (
			"Status:\n"
			f"Enabled: {str(alive)}\n"
		)
		text = ""
		if alive:
			caption += "List of devices:\n"
			text += (
				"Device | Last post\n"
			)
			for device in self.observer.last_device_post:
				date = self.observer.last_device_post[device]
				text += f"{device} | {date.strftime('%Y/%m/%d, %H:%M:%S')}\n"

		if text:
			await update.message.reply_document(document=text.encode("UTF-8", errors="ignore"),
												filename="output.txt", caption=caption)
		else:
			await update.message.reply_text(caption)

	async def set_start_date(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not self.observer:
			await update.message.reply_text("Observer not ready yet")
			return

		if not context.args or len(context.args) < 2:
			await update.message.reply_text("Error: No timestamp provided")
			return

		try:
			date = datetime.fromtimestamp(int(context.args[1]))
		except Exception:
			await update.message.reply_text(f"Error: Invalid timestamp: {context.args[1]}")
			return

		self.observer.set_start_date(date)

		await update.message.reply_text(f"Start date set to {date.strftime('%Y/%m/%d, %H:%M:%S')}")

	async def test_post(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not context.args or len(context.args) < 2:
			await update.message.reply_text("Error: No device provided")
			return

		device = context.args[1]
		chat_id = update.message.chat_id

		try:
			response = FullUpdateInfo.get_nightlies(device)
		except Exception:
			response = []

		if not response:
			await update.message.reply_text(f"No updates for {device}")
			return

		last_update = response[-1]

		build_date = last_update.datetime

		try:
			await self.poster.post(device, last_update, self.application.bot, chat_id)
		except Exception:
			pass
		else:
			return

		await update.message.reply_text(f"Error: Could not post {device} {build_date}")
