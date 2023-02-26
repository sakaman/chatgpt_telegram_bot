import asyncio
import logging

from httpx import HTTPError
from revChatGPT.V1 import Chatbot, AsyncChatbot
from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter
from telegram.ext import ContextTypes

import utils

logger = logging.getLogger(__name__)

CHAT_MODES = {
    "normal": {
        "name": "🤖 Normal Bot",
        "welcome_message": "🤖 Hi, I'm **ChatGPT Bot**. How can I help you?",
        "prompt_start": ""
    },
    "assistant": {
        "name": "👩🏼‍🎓 Assistant",
        "welcome_message": "👩🏼‍🎓 Hi, I'm **ChatGPT assistant**. How can I help you?",
        "prompt_start": "As an advanced chatbot named ChatGPT, your primary goal is to assist users to the best of your ability. This may involve answering questions, providing helpful information, or completing tasks based on user input. In order to effectively assist users, it is important to be detailed and thorough in your responses. Use examples and evidence to support your points and justify your recommendations or solutions. Remember to always prioritize the needs and satisfaction of the user. Your ultimate goal is to provide a helpful and enjoyable experience for the user."
    },

    "code_assistant": {
        "name": "👩🏼‍💻 Code Assistant",
        "welcome_message": "👩🏼‍💻 Hi, I'm **ChatGPT code assistant**. How can I help you?",
        "prompt_start": "As an advanced chatbot named ChatGPT, your primary goal is to assist users to write code. This may involve designing/writing/editing/describing code or providing helpful information. Where possible you should provide code examples to support your points and justify your recommendations or solutions. Make sure the code you provide is correct and can be run without errors. Be detailed and thorough in your responses. Your ultimate goal is to provide a helpful and enjoyable experience for the user. Write code inside <code>, </code> tags."
    },

    "text_improver": {
        "name": "📝 Text Improver",
        "welcome_message": "📝 Hi, I'm **ChatGPT text improver**. Send me any text – I'll improve it and correct all the mistakes",
        "prompt_start": "As an advanced chatbot named ChatGPT, your primary goal is to correct spelling, fix mistakes and improve text sent by user. Your goal is to edit text, but not to change it's meaning. You can replace simplified A0-level words and sentences with more beautiful and elegant, upper level words and sentences. All your answers strictly follows the structure (keep html tags):\n<b>Edited text:</b>\n{EDITED TEXT}\n\n<b>Correction:</b>\n{NUMBERED LIST OF CORRECTIONS}"
    },

    "movie_expert": {
        "name": "🎬 Movie Expert",
        "welcome_message": "🎬 Hi, I'm **ChatGPT movie expert**. How can I help you?",
        "prompt_start": "As an advanced movie expert chatbot named ChatGPT, your primary goal is to assist users to the best of your ability. You can answer questions about movies, actors, directors, and more. You can recommend movies to users based on their preferences. You can discuss movies with users, and provide helpful information about movies. In order to effectively assist users, it is important to be detailed and thorough in your responses. Use examples and evidence to support your points and justify your recommendations or solutions. Remember to always prioritize the needs and satisfaction of the user. Your ultimate goal is to provide a helpful and enjoyable experience for the user."
    },
}


class ChatGPT:
    def __init__(self, gpt_bot: Chatbot = None, async_gpt_bot: AsyncChatbot = None):
        self.gpt_bot = gpt_bot
        self.async_gpt_bot = async_gpt_bot

    def send_message(self, message, dialog_messages=[], chat_mode="normal", conversation_id: str = None,
                     parent_id: str = None):
        if chat_mode not in CHAT_MODES.keys():
            raise ValueError(f"Chat mode {chat_mode} is not supported")

        answer = None
        prompt = None
        while answer is None:
            prompt = self._generate_prompt(message, dialog_messages, chat_mode)
            logger.info(f"Ask ChatGPT: {prompt}")
            try:
                for data in self.gpt_bot.ask(prompt, conversation_id=conversation_id, parent_id=parent_id):
                    answer = data['message']
                    conversation_id = data['conversation_id']
                    parent_id = data['parent_id']
                answer = self._postprocess_answer(answer)

            except Exception as e:
                logger.error(f"Ask ChatGPT error: {str(e)}")
                if len(dialog_messages) == 0:
                    raise ValueError(f"ChatGPT Bot error: {str(e)}") from e

                # forget first message in dialog_messages
                dialog_messages = dialog_messages[1:]

        return answer, prompt, conversation_id, parent_id,

    async def async_send_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, dialog_messages=[],
                                 chat_mode="normal", conversation_id: str = None,
                                 parent_id: str = None):
        if chat_mode not in CHAT_MODES.keys():
            raise ValueError(f"Chat mode {chat_mode} is not supported")

        # Send "Typing..." action periodically every 4 seconds until the response is received
        typing_task = context.application.create_task(utils.send_typing_periodically(update, context, 4))

        prompt = self._generate_prompt(update.message.text, dialog_messages, chat_mode)

        initial_message: Message or None = None
        chunk_index, chunk_text = (0, '')

        async def message_update(every_seconds: float):
            while True:
                try:
                    if initial_message is not None and chunk_text != initial_message.text:
                        await initial_message.edit_text(chunk_text)
                except (BadRequest, HTTPError, RetryAfter):
                    pass
                except Exception as e:
                    typing_task.cancel()
                    logger.error(f"Error while editing the message: {str(e)}")

                await asyncio.sleep(every_seconds)

        message_update_task = context.application.create_task(message_update(every_seconds=0.5))
        async for chunk in self.async_gpt_bot.ask(prompt, conversation_id=conversation_id, parent_id=parent_id):
            if chunk_index == 0 and initial_message is None:
                conversation_id = chunk['conversation_id']
                parent_id = chunk['parent_id']
                initial_message = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    reply_to_message_id=update.message.message_id,
                    text=chunk['message'] + '...'
                )
            chunk_index, chunk_text = (chunk_index + 1, chunk['message'])

        message_update_task.cancel()
        typing_task.cancel()
        await initial_message.edit_text(chunk_text, parse_mode=ParseMode.MARKDOWN)
        return chunk_text, prompt, conversation_id, parent_id

    @staticmethod
    def _generate_prompt(message, dialog_messages, chat_mode):
        if chat_mode != "normal":
            prompt = CHAT_MODES[chat_mode]["prompt_start"]
            prompt += "\n\n"

            # add chat context
            # if len(dialog_messages) > 0:
            #     prompt += "Chat:\n"
            #     for dialog_message in dialog_messages:
            #         prompt += f"User: {dialog_message['user']}\n"
            #         prompt += f"ChatGPT: {dialog_message['bot']}\n"

            # current message
            prompt += f"User: {message}\n"
            prompt += "ChatGPT: "

            return prompt
        return message

    @staticmethod
    def _postprocess_answer(answer):
        answer = answer.strip()
        return answer
