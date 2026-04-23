import asyncio
import logging
from os import getenv
from typing import Callable, Dict, Any, Awaitable

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Ma'lumotlar bazasi va handlerlar
from app.database import Database
from app.handlers.user import router as user_router, register_user_handlers
from app.handlers.admin import router as admin_router, register_admin_handlers
from app.handlers.features import router as features_router

# .env faylini yuklash
load_dotenv()
BOT_TOKEN = getenv("BOT_TOKEN")
ADMIN_ID = int(getenv("ADMIN_ID"))

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- MIDDLEWARE ---
class DbMiddleware(BaseMiddleware):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Ma'lumotlar bazasini barcha handlerlarga argument sifatida o'zatadi
        data["db"] = self.db
        return await handler(event, data)

# --- SCHEDULER ---
async def scheduler(bot: Bot, db: Database):
    """Rejalashtirilgan postlarni tekshirish va yuborish"""
    while True:
        try:
            for post in db.get_pending_posts():
                kb = InlineKeyboardBuilder()
                bot_me = await bot.get_me()
                kb.row(InlineKeyboardButton(
                    text="🔷 Tomosha qilish 🔷",
                    url=f"https://t.me/{bot_me.username}?start={post['anime_id']}"
                ))
                caption = (
                    f"📺 *{post['name']}*\n"
                    f"┏━━━━━━━━━━━━━━━┓\n"
                    f"┃ 🎞 *Qismlar:* {post['episode']}\n"
                    f"┃ 🌍 *Davlat:* {post.get('country','')}\n"
                    f"┃ 🗣 *Til:* {post.get('language','')}\n"
                    f"┃ 🔖 *Janr:* {post['genre']}\n"
                    f"┃ ⭐ *Reyting:* {post['rating']}\n"
                    f"┗━━━━━━━━━━━━━━━┛\n"
                    f"📌 *Tavsif:* {post['description']}"
                )
                try:
                    await bot.send_photo(
                        chat_id=post['channel'], 
                        photo=post['image'],
                        caption=caption, 
                        parse_mode='Markdown',
                        reply_markup=kb.as_markup()
                    )
                    db.mark_post_sent(post['id'])
                    logger.info(f"Scheduled post sent: {post['name']}")
                except Exception as e:
                    logger.error(f"Post yuborishda xato: {e}")
        except Exception as e:
            logger.error(f"Scheduler xato: {e}")

        await asyncio.sleep(60)

# --- MAIN ---
async def main():
    # 1. Obyektlarni main ichida yaratamiz (RuntimeError oldini olish uchun)
    db = Database()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # 2. Middleware ulash (Routerlardan oldin bo'lishi shart)
    dp.update.middleware(DbMiddleware(db))

    # 3. Eski uslubdagi handlerlarni ro'yxatdan o'tkazish (agar kerak bo'lsa)
    register_user_handlers(user_router, db, ADMIN_ID)
    register_admin_handlers(admin_router, db, ADMIN_ID)
    # register_feature_handlers(features_router) shart emas, chunki router mustaqil

    # 4. Routerlarni Dispatcherga ulash (Faqat bir marta!)
    dp.include_router(admin_router)
    dp.include_router(features_router)
    dp.include_router(user_router)

    logger.info("✅ Bot v3 ishga tushdi!")
    
    # Eskidan qolib ketgan xabarlarni o'chirib yuborish
    await bot.delete_webhook(drop_pending_updates=True)

    # Bot va Shcedulerni parallel ishga tushirish
    await asyncio.gather(
        dp.start_polling(bot),
        scheduler(bot, db)
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi!")