#
# Copyright (C) 2023 Sebastiano Barezzi
#
# SPDX-License-Identifier: MIT
#

from sebaubuntu_libs.libexception import format_exception
from sebaubuntu_libs.liblogging import LOGE
from telegram import Update
from telegram.ext import CallbackContext
from typing import Optional

from lineageos_updates_bot.utils.logging import log


async def error_handler(update: Optional[object], context: CallbackContext):
    if not update:
        LOGE("Error encountered, but no update is available.")
        LOGE(f"Error: {format_exception(context.error)}")
        return

    if not isinstance(update, Update):
        LOGE("Error encountered, but update is not of type Update.")
        LOGE(f"Error: {format_exception(context.error)}")
        return

    formatted_error = "Error encountered!\n"
    if update:
        if update.effective_chat:
            chat_name = (
                update.effective_chat.title
                if update.effective_chat.title
                else update.effective_chat.full_name
                if update.effective_chat.full_name
                else "Unknown chat"
            )
            if update.effective_chat.username:
                chat_name += f" (@{update.effective_chat.username})"
            else:
                chat_name += f" ({update.effective_chat.id})"

            formatted_error += f"Chat: {chat_name}\n"

        if update.effective_user:
            user_name = update.effective_user.full_name
            if update.effective_user.username:
                user_name += f" (@{update.effective_user.username})"
            else:
                user_name += f" ({update.effective_user.id})"

            formatted_error += f"User: {user_name}\n"

        if update.effective_message:
            formatted_error += f"Message: {update.effective_message.text}\n"

    formatted_error += f"\n{format_exception(context.error)}"

    await log(context.bot, formatted_error)

    LOGE("End error handling")
