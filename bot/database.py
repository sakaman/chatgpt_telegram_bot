import asyncio
import uuid
from datetime import datetime
from typing import Optional, Any

import pymongo

import config


class Database:
    def __init__(self):
        self.client = pymongo.MongoClient(config.mongodb_uri)
        self.db = self.client["chatgpt_telegram_bot"]

        self.user_collection = self.db["user"]
        self.dialog_collection = self.db["dialog"]

    def check_if_user_exists(self, user_id: int, raise_exception: bool = False):
        if self.user_collection.count_documents({"_id": user_id}) > 0:
            return True
        else:
            if raise_exception:
                raise ValueError(f"User {user_id} does not exist")
            else:
                return False
        
    def add_new_user(
        self,
        user_id: int,
        chat_id: int,
        username: str = "",
        first_name: str = "",
        last_name: str = "",
    ):
        user_dict = {
            "_id": user_id,
            "chat_id": chat_id,

            "username": username,
            "first_name": first_name,
            "last_name": last_name,

            "last_interaction": datetime.now(),
            "first_seen": datetime.now(),

            "current_dialog_id": None,
            "current_chat_mode": "normal",

            "n_used_tokens": 0
        }

        if not self.check_if_user_exists(user_id):
            self.user_collection.insert_one(user_dict)
            
        # TODO: maybe start a new dialog here?

    def start_new_dialog(self, user_id: int):
        self.check_if_user_exists(user_id, raise_exception=True)

        dialog_id = str(uuid.uuid4())
        conversation_id = None
        dialog_dict = {
            "_id": dialog_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "chat_mode": self.get_user_attribute(user_id, "current_chat_mode"),
            "start_time": datetime.now(),
            "messages": []
        }

        # add new dialog
        self.dialog_collection.insert_one(dialog_dict)

        # update user's current dialog
        self.user_collection.update_one(
            {"_id": user_id},
            {"$set": {"current_dialog_id": dialog_id}}
        )

        return dialog_id

    def get_user_attribute(self, user_id: int, key: str):
        self.check_if_user_exists(user_id, raise_exception=True)
        user_dict = self.user_collection.find_one({"_id": user_id})

        if key not in user_dict:
            raise ValueError(f"User {user_id} does not have a value for {key}")

        return user_dict[key]

    def set_user_attribute(self, user_id: int, key: str, value: Any):
        self.check_if_user_exists(user_id, raise_exception=True)
        self.user_collection.update_one({"_id": user_id}, {"$set": {key: value}})

    def get_dialog_messages(self, user_id: int, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")
        # self.check_if_user_exists()

        dialog_dict = self.dialog_collection.find_one({"_id": dialog_id, "user_id": user_id})
        if dialog_dict is None:
            raise ValueError("Please start a new dialog")

        return dialog_dict["messages"]

    def get_dialog_attribute(self, user_id: int, key: str, dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        dialog_dict = self.dialog_collection.find_one({"_id": dialog_id, "user_id": user_id})
        if key not in dialog_dict:
            raise ValueError(f"User {user_id} does not have a value for {key} in dialog")

        return dialog_dict[key]

    def set_dialog_messages(self, user_id: int, dialog_messages: list, conversation_id: str,
                            dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        self.dialog_collection.update_one(
            {"_id": dialog_id, "user_id": user_id},
            {"$set": {"conversation_id": conversation_id, "messages": dialog_messages}}
        )

    async def async_set_dialog_messages(self, user_id: int, dialog_messages: list, conversation_id: str,
                                        dialog_id: Optional[str] = None):
        self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = self.get_user_attribute(user_id, "current_dialog_id")

        await asyncio.get_event_loop().run_in_executor(
            None,
            self.dialog_collection.update_one,
            {"_id": dialog_id, "user_id": user_id},
            {"$set": {"conversation_id": conversation_id, "messages": dialog_messages}}
        )
