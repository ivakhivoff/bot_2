import asyncio
from datetime import datetime, timedelta
from itertools import cycle
import json
import logging
import os
from pathlib import Path
import pathlib
import threading
from logging.handlers import TimedRotatingFileHandler
import time
import traceback

from aiogram import Bot, Dispatcher, executor, types
from aiogram import types
import aiogram
from config import ADMINS, API_HASH, API_ID, BOT_TOKEN
from filters import Admin
from aiogram.dispatcher import FSMContext
import csv


from telethon import TelegramClient
from telethon.events import NewMessage
from aiogram.types import (
    InputFile,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ContentType,
)
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
# from models.settings import Setting
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger
from aiogram.utils.exceptions import BotBlocked

def create_timed_rotating_log(filename):
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("MyLogger")
    logger.setLevel(logging.INFO)

    handler = TimedRotatingFileHandler(
        f"logs/{filename}",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8"
    )

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger

global main_client
main_client: TelegramClient = None
if os.path.exists("accounts/main.session"):
    main_client = TelegramClient(
            f"accounts/main.session",
            api_id=API_ID,
            api_hash=API_HASH
        )

logger = create_timed_rotating_log("logs.log")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] {%(filename)s:%(funcName)s:%(lineno)d} %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')
}
scheduler = AsyncIOScheduler(jobstores=jobstores)
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)
dp.filters_factory.bind(Admin)

@dp.message_handler(commands=["id"])
async def get_id(message: types.Message):
    await message.answer(message.from_user.id)
    
@dp.message_handler(commands=["start"], is_admin=True)
async def get_id(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=1).add(
        # InlineKeyboardButton("Розсылки", callback_data="mailings"),
        InlineKeyboardButton("Добавить розсылку", callback_data="add_mailings"),
        InlineKeyboardButton("Аккаунты", callback_data="accounts"),
    )
    await message.answer("Меню", reply_markup=kb)

class MailingStates(StatesGroup):
    msg = State()
    chats = State()
    mailtype = State()
    by_time = State()
    by_msg = State()

@dp.callback_query_handler(text="add_mailings")
async def proccess_upd(call: CallbackQuery, state: FSMContext):
    await call.message.answer("!!! Прежде чем начинать рассылку убедитесь что есть рабочий аккаунт main.session")
    await MailingStates.msg.set()
    await call.answer()
    await state.update_data(texts=[])
    await call.message.answer("Отправьте сообщение, которые будут использоваться для рассылки (только текст)", reply_markup=get_cancel_kb())

@dp.message_handler(state=MailingStates.msg)
async def proccess_upd(message: Message, state: FSMContext):
    async with state.proxy() as data:
        data["texts"].append(message.text)
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Продолжить", callback_data="continue_mailing")
    )
    await message.answer("Отправьте ещё сообщение или нажмите продолжить", reply_markup=kb)

@dp.callback_query_handler(text="continue_mailing", state=MailingStates.msg)
async def proccess_upd(call: CallbackQuery, state: FSMContext):
    await MailingStates.chats.set()
    await call.answer()
    await call.message.answer("Отправьте список чатов в одном сообщении, где каждая новая строка это @username чат или ссылка на чат в формате https://t.me/+aaaaa")
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, GetHistoryRequest, CheckChatInviteRequest
from telethon.tl.types import ChatInviteAlready
from telethon.errors.rpcerrorlist import FloodWaitError
@dp.message_handler(state=MailingStates.chats)
async def proccess_upd(message: Message, state: FSMContext):
    global main_client
    chats = message.text.split("\n")
    await message.answer("Заходим в чаты...")
    await state.update_data(chats=[])
    for chat in chats:
        if chat.startswith("@"):
            chat = chat.lstrip("@")
            for s in os.listdir("accounts"):
                await asyncio.sleep(0.1)
                if s.endswith(".session") and not s == "main.session":
                    client = TelegramClient("accounts/" + s, api_hash=API_HASH, api_id=API_ID)
                    await client.connect()
                    if not await client.is_user_authorized():
                        await message.answer(f"Аккаунт не авторизирован: {s}")
                        continue
                    try:
                        res = await client(JoinChannelRequest(await client.get_input_entity(chat)))
                        chat_id = res.chats[0].id
                    except FloodWaitError as e:
                        await message.answer(f"Аккаунт {s} находится в бане на {e.seconds} секунд и не может зайти в чат")
                    except Exception:
                        logger.info(f"channel {chat}, account {s}")
                        logger.error(traceback.format_exc())
                    await client.disconnect()
            if main_client:
                try:
                    res = await main_client(JoinChannelRequest(await main_client.get_input_entity(chat)))
                    chat_id = res.chats[0].id
                except Exception:
                    logger.info(f"channel {chat}, account {s}")
                    logger.error(traceback.format_exc())
        elif chat.startswith("https://t.me/+"):
            await asyncio.sleep(0.1)
            chat = chat.lstrip("https://t.me/+")
            for s in os.listdir("accounts"):
                if s.endswith(".session") and not s == "main.session":
                    client = TelegramClient("accounts/" + s, api_hash=API_HASH, api_id=API_ID)
                    await client.connect()
                    if not await client.is_user_authorized():
                        await message.answer(f"Аккаунт не авторизирован: {s}")
                        continue
                    try:
                        r = await client(CheckChatInviteRequest(hash=chat))
                        if type(r) is ChatInviteAlready:
                            chat_id = r.chat.id
                        else:
                            try:
                                res = await client(ImportChatInviteRequest(hash=chat))
                            except FloodWaitError as e:
                                await message.answer(f"Аккаунт {s} находится в бане на {e.seconds} секунд и не может зайти в чат")
                            chat_id = res.chats[0].id
                    except Exception:
                        logger.info(f"channel {chat}, account {s}")
                        logger.error(traceback.format_exc())
                    await client.disconnect()
            if main_client:
                try:
                    r = await main_client(CheckChatInviteRequest(hash=chat))
                    if type(r) is ChatInviteAlready:
                        chat_id = r.chat.id
                    else:
                        res = await main_client(ImportChatInviteRequest(hash=chat))
                        chat_id = res.chats[0].id
                except FloodWaitError:
                    await message.answer(f"Флуд еррор на мейн аккаунте")
                except Exception:
                    logger.info(f"channel {chat}, account {s}")
                    logger.error(traceback.format_exc())
        else:
            await message.answer(f"Неправильный формат, пропуск: {chat}")
            continue
        async with state.proxy() as data:
            try:
                print(chat_id)
                data["chats"].append(chat_id)
            except:
                logger.error(traceback.format_exc())
    await MailingStates.mailtype.set()
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("По времени", callback_data="by_time"),
        InlineKeyboardButton("По сообщениям", callback_data="by_msg"),
    )
    await message.answer("Аккаунты успешно добавлены в чаты. Выберите тип рассылки", reply_markup=kb)

@dp.callback_query_handler(text="by_time", state=MailingStates.mailtype)
async def process_upd(call: CallbackQuery):
    await call.answer()
    await MailingStates.by_time.set()
    await call.message.answer("Напишите интервал в формате гг:мм:сс, через сколько отправлять следующее сообщение")

@dp.callback_query_handler(text="by_msg", state=MailingStates.mailtype)
async def process_upd(call: CallbackQuery):
    await call.answer()
    await MailingStates.by_msg.set()
    await call.message.answer("Напишите через сколько сообщений отправлять рассылку")

from models.settings import Setting

from aiogram.utils.callback_data import CallbackData

cancel_mail_cb = CallbackData('cancel_mail_cb', "mail_id")

@dp.callback_query_handler(cancel_mail_cb.filter())
async def _make_mail(call: CallbackQuery, state: FSMContext, callback_data: dict):
    await call.answer()
    mail_id = callback_data["mail_id"]
    try:
        scheduler.remove_job(f"mailing_{mail_id}")
    except:
        logger.exception("error delete mailing")
        # await call.message.answer("Виникла помилка")
    else:
        await call.message.answer("Успішно!")
    Setting.delete_by_id(mail_id)

@dp.message_handler(state=MailingStates.by_time)
async def proccess_upd(message: Message, state: FSMContext):
    try:
        time = datetime.strptime(message.text, "%H:%M:%S")        
    except:
        await message.answer("Неправильный формат")
        return
    await state.update_data(time=time)
    async with state.proxy() as data:
        s = Setting.create(chats=";".join(map(lambda a: str(a),data["chats"])), texts="|||".join(data["texts"]), by_time=time)
        scheduler.add_job(make_mail, args=(data["chats"], s.id), id=f"mailing_{s.id}", trigger="interval", hours=time.hour, minutes=time.minute, seconds=time.second)
        await message.answer(f"Розсилка з ID {s.id}", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("Скасувати", callback_data=cancel_mail_cb.new(str(s.id)))))
    await state.finish()

def get_next_acc():
    i = 0
    while True:
        files = os.listdir("accounts")
        try:
            f = files[i]
        except IndexError:
            i = 0
            continue
        if not f.endswith(".session"):
            i+=1
            continue
        if f == "main.session":
            i+=1
            continue
        i+=1
        yield f



accs_gen = get_next_acc()

async def make_mail(chat_ids, mail_id):
    for chat_id in chat_ids:
        acc = next(accs_gen)
        client = TelegramClient("accounts/"+acc, api_hash=API_HASH, api_id=API_ID)
        await client.connect()
        if not await client.is_user_authorized():
            for adm in ADMINS:
                try:
                    await bot.send_message(adm, f"Аккаунт разлогинен: {acc}")
                except:
                    pass
            return
        s = Setting.get(id=mail_id)
        texts = s.texts.split("|||")
        s.counter += 1
        s.save()
        try:
            await client.send_message(chat_id, texts[s.counter % len(texts)])
        except:
            logger.info(f"channel {chat_id}, account {acc}")
            logger.exception(exc_info=True)
            continue
        finally:
            await client.disconnect()


@dp.message_handler(state=MailingStates.by_msg)
async def proccess_upd(message: Message, state: FSMContext):
    if not message.text.isdecimal():
        await message.answer("Это не число!")
        return
    num = int(message.text)
    if not num > 0:
        await message.answer("Число должно быть больше 0!")
        return
    await state.update_data(msg_num=num)
    async with state.proxy() as data:
        s = Setting.create(chats=";".join(map(lambda a: str(a),data["chats"])), texts="|||".join(data["texts"]), by_msg=num)
        # scheduler.add_job(make_mail, args=(data["chats"], s.id), id=f"mailing_{s.id}", trigger="interval", hours=time.hour, minutes=time.minute, seconds=time.second)
        await message.answer(f"Розсилка з ID {s.id}", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("Скасувати", callback_data=cancel_mail_cb.new(str(s.id)))))
    await state.finish()
    # async with state.proxy() as data:
    #     Setting.create(chats=";".join(data["chats"]), texts="|||".join(data["texts"]), by_time=)
    # await state.finish()


class DeleteAcc(StatesGroup):
    name = State()


class AddAcc(StatesGroup):
    file = State()

@dp.callback_query_handler(text="accounts")
async def proccess_upd(call: CallbackQuery):
    await call.answer()
    files = os.listdir("accounts")
    text = "Пусто"
    if files:
        text = ", ".join(filter(lambda f: f.endswith(".session"),files))
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("Добавить аккаунт", callback_data="add_account"),
        InlineKeyboardButton("Удалить аккаунт", callback_data="delete_account")
    )
    await call.message.answer(f"Аккаунты: {text}", reply_markup=kb)

def get_cancel_kb():
    return InlineKeyboardMarkup(row_width=1).add(InlineKeyboardButton("Отмена", callback_data="cancel"))

@dp.callback_query_handler(text="delete_account")
async def proccess_upd(call: CallbackQuery):
    await call.answer()
    await DeleteAcc.name.set()
    await call.message.answer("Введите имя аккаунта", reply_markup=get_cancel_kb())

@dp.callback_query_handler(text="add_account")
async def proccess_upd(call: CallbackQuery):
    await call.answer()
    await AddAcc.file.set()
    await call.message.answer("Отправьте session файл аккаунта", reply_markup=get_cancel_kb())

work_dir = pathlib.Path().resolve()

def process_handlers(acc):
    @acc.on(NewMessage())
    async def my_event_handler(event):
        chat = await event.get_chat()
        print(event.chat_id)
        print(chat.id)

@dp.message_handler(content_types=["document"],state=AddAcc.file)
async def proccess_upd(message: Message, state: FSMContext):
    global main_client
    await state.finish()
    await message.document.download(destination=work_dir/"accounts"/message.document.file_name)
    if message.document.file_name == "main.session":
        main_client = TelegramClient(
            f"accounts/main.session",
            api_id=API_ID,
            api_hash=API_HASH
        )
        await main_client.connect()
        if not await main_client.is_user_authorized():
            await message.answer("Main session не авторизирован. Удалите и добавьте авторизированный аккаунт")
            return
        process_handlers(main_client)
        
    await message.answer("Успешно")

@dp.callback_query_handler(text="cancel", state="*", is_admin=True)
async def proxys_get(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.finish()
    await call.message.answer("Отменено")

@dp.message_handler(state=DeleteAcc.name)
async def proccess_upd(message: Message, state: FSMContext):
    global main_client
    await state.finish()
    if message.text == "main.session":
        await main_client.disconnect()
        main_client = None
    os.remove("accounts/" + message.text)
    await message.answer("Успешно")



async def on_startup():
    if main_client:
        await main_client.connect()
        if not await main_client.is_user_authorized():
            for admin in ADMINS:
                try:
                    await bot.send_message(admin, "Main session не авторизирован. Удалите и добавьте авторизированный аккаунт")
                except:
                    pass
            return
        process_handlers(main_client)
        asyncio.create_task(main_client.run_until_disconnected())

async def main():
    # await main2()
    scheduler.start()
    await on_startup()
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(main())