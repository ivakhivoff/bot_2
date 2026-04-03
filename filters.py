from aiogram.dispatcher.filters import BoundFilter
from aiogram.types import Message
from config import ADMINS


class Admin(BoundFilter):
    key = "is_admin"

    def __init__(self, is_admin: bool):
        self.is_admin = is_admin

    async def check(self, message: Message):
        # user = get_user(message.from_user.id)

        # if not user:
        #     return False

        return message.from_user.id in ADMINS
