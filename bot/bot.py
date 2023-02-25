import asyncio
import html
import json
import logging
import traceback
from datetime import datetime

import telegram
from revChatGPT.V1 import Chatbot
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

import chatgpt
import config
import database

# setup
db = database.Database()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

email = config.openai_email
password = config.openai_password
chatgpt_bot = Chatbot(config={"email": email, "password": password})

# Disable certificate verification
# ssl._create_default_https_context = ssl._create_unverified_context

HELP_MESSAGE = """Commands:
⚪ /new – Start new dialog
⚪ /retry – Regenerate last bot answer
⚪ /mode – Select chat mode
⚪ /help – Show help
"""


async def register_user_if_not_exists(update: Update, context: CallbackContext, user: User):
    if not db.check_if_user_exists(user.id):
        db.add_new_user(
            user.id,
            update.message.chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )


async def start_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.start_new_dialog(user_id)

    reply_text = "Hi! I'm **ChatGPT** bot implemented with GPT-3.5 OpenAI API 🤖\n\n"
    reply_text += HELP_MESSAGE

    reply_text += "\nAnd now... ask me anything!"

    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)


async def help_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.MARKDOWN)


async def retry_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    dialog_id = db.get_user_attribute(user_id, "current_dialog_id")
    conversation_id = db.get_dialog_attribute(user_id, "conversation_id", dialog_id)
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    dialog_messages = db.get_dialog_messages(user_id, dialog_id)
    if len(dialog_messages) == 0:
        await update.message.reply_text("No message to retry 🤷‍♂️")
        return

    last_dialog_message = dialog_messages.pop()

    # last message was removed from the context
    db.set_dialog_messages(user_id, dialog_messages, conversation_id, dialog_id)

    await message_handle(update, context, message=last_dialog_message["user"], use_new_dialog_timeout=False)


async def message_handle(update: Update, context: CallbackContext, message=None, use_new_dialog_timeout=False):
    # check if message is edited
    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return

    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    # new dialog timeout
    if use_new_dialog_timeout:
        if (datetime.now() - db.get_user_attribute(user_id, "last_interaction")).seconds > config.new_dialog_timeout:
            db.start_new_dialog(user_id)
            await update.message.reply_text("Starting new dialog due to timeout ✅")
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    # send typing action
    await update.message.chat.send_action(action=ChatAction.TYPING)
    # Send "Typing..." action periodically every 4 seconds until the response is received
    # typing_task = context.application.create_task(send_typing_periodically(update, context, 4))

    try:
        message = message or update.message.text

        dialog_id = db.get_user_attribute(user_id, "current_dialog_id")
        dialog_messages = db.get_dialog_messages(user_id, dialog_id)
        conversation_id = db.get_dialog_attribute(user_id, "conversation_id", dialog_id)
        parent_id = None
        if len(dialog_messages) > 0:
            parent_id = dialog_messages[-1]['parent_id']
        answer, prompt, conversation_id, parent_id, n_first_dialog_messages_removed = chatgpt.ChatGPT(
            gpt_bot=chatgpt_bot).send_message(
            message,
            dialog_messages=db.get_dialog_messages(user_id, dialog_id),
            chat_mode=db.get_user_attribute(user_id, "current_chat_mode"),
            conversation_id=conversation_id,
            parent_id=parent_id
        )

        # update user data
        new_dialog_message = {"user": message, "bot": answer, "date": datetime.now(), "parent_id": parent_id}
        db.set_dialog_messages(
            user_id,
            db.get_dialog_messages(user_id, dialog_id) + [new_dialog_message],
            conversation_id,
            dialog_id
        )
    except Exception as e:
        error_text = f"Something went wrong during completion. Reason: {e}"
        logger.error(error_text)
        # typing_task.cancel()
        await update.message.reply_text(error_text)
        return

    # typing_task.cancel()
    # send message if some messages were removed from the context
    if n_first_dialog_messages_removed > 0:
        if n_first_dialog_messages_removed == 1:
            text = "✍️ __Note:__ Your current dialog is too long, so your **first message** was removed from the " \
                   "context.\n Send /new command to start new dialog"
        else:
            text = f"✍️ __Note:__ Your current dialog is too long, so **{n_first_dialog_messages_removed} first " \
                   f"messages** were removed from the context.\n Send /new command to start new dialog"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    try:
        await update.message.reply_text(answer, parse_mode=ParseMode.MARKDOWN)
    except telegram.error.BadRequest:
        # answer has invalid characters, so we send it without parse_mode
        await update.message.reply_text(answer)


async def send_typing_periodically(update: Update, context: CallbackContext, every_seconds: float):
    """
    Sends the typing action periodically to the chat
    """
    while True:
        # await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await update.message.chat.send_action(action=ChatAction.TYPING)
        await asyncio.sleep(every_seconds)


async def new_dialog_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    db.start_new_dialog(user_id)
    await update.message.reply_text("Starting new dialog ✅")

    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")
    await update.message.reply_text(f"{chatgpt.CHAT_MODES[chat_mode]['welcome_message']}",
                                    parse_mode=ParseMode.MARKDOWN)


async def show_chat_modes_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    keyboard = []
    for chat_mode, chat_mode_dict in chatgpt.CHAT_MODES.items():
        keyboard.append([InlineKeyboardButton(chat_mode_dict["name"], callback_data=f"set_chat_mode|{chat_mode}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Select chat mode:", reply_markup=reply_markup)


async def set_chat_mode_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.callback_query.from_user)
    user_id = update.callback_query.from_user.id

    query = update.callback_query
    await query.answer()

    chat_mode = query.data.split("|")[1]

    db.set_user_attribute(user_id, "current_chat_mode", chat_mode)
    db.start_new_dialog(user_id)

    await query.edit_message_text(
        f"**{chatgpt.CHAT_MODES[chat_mode]['name']}** chat mode is set",
        parse_mode=ParseMode.MARKDOWN
    )

    await query.edit_message_text(f"{chatgpt.CHAT_MODES[chat_mode]['welcome_message']}",
                                  parse_mode=ParseMode.MARKDOWN)


async def edited_message_handle(update: Update, context: CallbackContext):
    text = "🥲 Unfortunately, message **editing** is not supported"
    await update.edited_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def error_handle(update: object, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    try:
        # collect error message
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)[:2000]
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        message = (
            f"An exception was raised while handling an update\n"
            f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
            "</pre>\n\n"
            f"<pre>{html.escape(tb_string)}</pre>"
        )

        # split text into multiple messages due to 4096 character limit
        message_chunk_size = 4000
        message_chunks = [message[i:i + message_chunk_size] for i in range(0, len(message), message_chunk_size)]
        for message_chunk in message_chunks:
            await context.bot.send_message(update.effective_chat.id, message_chunk, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Some error happened: {str(e)}")
        await context.bot.send_message(update.effective_chat.id, "Some error in error handler")


def run_bot() -> None:
    application = (
        ApplicationBuilder()
        .token(config.telegram_token)
        .connect_timeout(60)
        .read_timeout(60)
        .write_timeout(60)
        .pool_timeout(60)
        .build()
    )

    # add handlers
    if len(config.allowed_telegram_usernames) == 0:
        user_filter = filters.ALL
    else:
        user_filter = filters.User(username=config.allowed_telegram_usernames)

    application.add_handler(CommandHandler("start", start_handle, filters=user_filter))
    application.add_handler(CommandHandler("help", help_handle, filters=user_filter))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, message_handle))
    application.add_handler(CommandHandler("retry", retry_handle, filters=user_filter))
    application.add_handler(CommandHandler("new", new_dialog_handle, filters=user_filter))

    application.add_handler(CommandHandler("mode", show_chat_modes_handle, filters=user_filter))
    application.add_handler(CallbackQueryHandler(set_chat_mode_handle, pattern="^set_chat_mode"))

    application.add_error_handler(error_handle)

    # start the bot
    logger.info("Booting ChatGPT bot successfully")
    application.run_polling()


if __name__ == "__main__":
    run_bot()
