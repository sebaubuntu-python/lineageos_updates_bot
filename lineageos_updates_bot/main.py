#
# Copyright (C) 2023 Sebastiano Barezzi
#
# SPDX-License-Identifier: MIT
#

import config
from lineageos_updates_bot.utils.bot import LineageOSUpdatesBot

def main():
	bot = LineageOSUpdatesBot(config.TELEGRAM_API_KEY, config.TELEGRAM_CHAT_ID)
	bot.run()
