#
# Copyright (C) 2023 Sebastiano Barezzi
#
# SPDX-License-Identifier: MIT
#

from asyncio import CancelledError, Task, get_event_loop, new_event_loop, set_event_loop
from datetime import datetime
from humanize import naturalsize
from liblineage.hudson.build_target import BuildTarget
from liblineage.updater.v2 import AsyncV2Api
from liblineage.wiki.device_data import DeviceData
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackContext, CommandHandler
from telegram.helpers import escape_markdown
from typing import Dict, Optional, Union

import config
from lineageos_updates_bot.utils.error_handler import error_handler
from lineageos_updates_bot.utils.logging import log
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
		try:
			loop = get_event_loop()
		except RuntimeError:
			loop = new_event_loop()
			set_event_loop(loop)

		# Start the bot
		loop.run_until_complete(self.application.initialize())

		# Add handlers
		self.application.add_handler(CommandHandler(["start"], self.start))
		self.application.add_handler(CommandHandler(["device_info"], self.device_info))
		self.application.add_handler(CommandHandler(["lineageos"], self.lineageos))
		self.application.add_handler(CommandHandler(["lineageos_updates"], self.lineageos_updates))
		self.application.add_handler(CommandHandler(["when"], self.when))

		self.application.add_error_handler(error_handler)

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

	async def log(self, message: str):
		await log(self.application.bot, message)

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

		codename = context.args[0]

		device_data: Optional[DeviceData] = None
		variants: Dict[str, DeviceData] = {}

		try:
			device_data = DeviceData.get_device_data(codename)
		except Exception:
			pass

		if not device_data:
			# Retry with 'variant_1'
			try:
				variant_index = 1
				while True:
					variant_codename = f"{codename}_variant{variant_index}"
					variant = DeviceData.get_device_data(variant_codename)
					variants[variant_codename] = variant
					variant_index += 1
			except Exception:
				pass

		if device_data:
			await update.message.reply_text(f"{device_data}", disable_web_page_preview=True)
		elif len(variants) > 0:
			text = "\n".join([
				"There are multiple variants for this device:",
				*[
					f"\\- {escape_markdown(codename, 2)}: {escape_markdown(f'{device_data.vendor} {device_data.name}', 2)}"
					for codename, device_data in variants.items()
				],
				"Please use the variant codename instead of the device codename"
			])
			await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
		else:
			await update.message.reply_text("Error: Device not found")

	async def lineageos(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not context.args or len(context.args) < 1:
			await update.message.reply_text("Device codename not specified")
			return

		codename = context.args[0]

		try:
			device_info = await AsyncV2Api.get_device(codename)
		except Exception:
			await update.message.reply_text("Error: Device not found")
			return
		
		if not device_info.versions:
			await update.message.reply_text(f"No LineageOS versions found for {codename}")
			return

		builds = await AsyncV2Api.get_device_builds(codename)
		if not builds:
			await update.message.reply_text(f"Error: no updates found for {codename}")
			return

		last_update = builds[0]
		for build in builds:
			if build.datetime > last_update.datetime:
				last_update = build

		text = (
			f"Last build for {escape_markdown(device_info.oem, 2)} {escape_markdown(device_info.name, 2)} {escape_markdown(f'({codename})', 2)}:\n"
			f"Date: {escape_markdown(last_update.date, 2)}\n"
			f"Type: {escape_markdown(last_update.build_type, 2)}\n"
			f"OS patch level: `{escape_markdown(last_update.os_patch_level, 2)}`\n"
			f"Download: [{escape_markdown(last_update.ota_zip.filename, 2)}]({escape_markdown(last_update.ota_zip.url, 2)}) {escape_markdown(f'({naturalsize(last_update.ota_zip.size)})', 2)}\n"
		)

		additional_files = last_update.files[1:]

		if additional_files:
			text += (
				"\n"
				"Additional files:\n"
			)

		for file in additional_files:
			text += (
				f"[{escape_markdown(file.filename, 2)}]({escape_markdown(file.url, 2)}) {escape_markdown(f'({naturalsize(file.size)})', 2)}\n"
			)

		await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

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

		codename = context.args[0]

		try:
			device_data = await AsyncV2Api.get_device(codename)
		except Exception:
			await update.message.reply_text(f"Error: Device not found")
			return

		try:
			build_target = BuildTarget.get_device(codename)
		except Exception:
			await update.message.reply_text(f"Error: Device not found")
			return

		device_info = (
			f"{device_data.oem} {device_data.name} ({codename})"
			if device_data
			else f"{codename}"
		)

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

		text = "Observer disabled"

		await update.message.reply_text(text)

		await self.log(text)

	async def enable(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not self.observer:
			await update.message.reply_text("Observer not ready yet")
			return

		self.observer.event.set()

		text = "Observer enabled"

		await update.message.reply_text(text)

		await self.log(text)

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

		text = f"Start date set to {date.strftime('%Y/%m/%d, %H:%M:%S')}"

		await update.message.reply_text(text)

		await self.log(text)

	async def test_post(self, update: Update, context: CallbackContext):
		if not update.message:
			return

		if not context.args or len(context.args) < 2:
			await update.message.reply_text("Error: No device provided")
			return

		device = context.args[1]
		chat_id = update.message.chat_id

		try:
			response = await AsyncV2Api.get_device_builds(device)
		except Exception:
			response = []

		if not response:
			await update.message.reply_text(f"No updates for {device}")
			return

		last_update = response[0]
		for build in response:
			if build.datetime > last_update.datetime:
				last_update = build

		build_date = last_update.datetime

		try:
			await self.poster.post(device, last_update, self.application.bot, chat_id)
		except Exception:
			pass
		else:
			return

		await update.message.reply_text(f"Error: Could not post {device} {build_date}")
