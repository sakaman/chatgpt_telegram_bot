import asyncio

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes


async def send_typing_periodically(update: Update, context: ContextTypes.DEFAULT_TYPE, every_seconds: float):
    """
    Sends the typing action periodically to the chat
    """
    while True:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        # await update.message.chat.send_action(action=ChatAction.TYPING)
        await asyncio.sleep(every_seconds)
