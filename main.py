import asyncio
import logging
import os
import sys
from typing import Dict, Any, List

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from database import (
    init_db, create_users_table, create_config_table, 
    create_post_channels_table, setup_db
)
from handlers import task, notification, admin
from handlers.middleware import SubscriptionMiddleware
from utils import scheduler
from handlers.notification import send_task_notification

# .env faylini yuklash
load_dotenv()

# Bot tokeni
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logging.error("BOT_TOKEN topilmadi. .env fayliga qo'shing!")
    sys.exit(1)

# Adminlar ro'yxati (bular ID raqamlar bo'lishi kerak)
ADMIN_IDS = []
admin_ids_str = os.getenv("ADMIN_IDS", "")
if admin_ids_str:
    try:
        ADMIN_IDS = [int(admin_id.strip()) for admin_id in admin_ids_str.split(",")]
        logging.info(f"Adminlar ro'yxati yuklandi: {ADMIN_IDS}")
    except ValueError:
        logging.error("ADMIN_IDS noto'g'ri formatda. Vergul bilan ajratilgan raqamlar bo'lishi kerak.")
else:
    logging.warning("ADMIN_IDS topilmadi. Admin funksiyalarini ishlatish uchun .env fayliga qo'shing!")

# Log konfiguratsiyasi
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Asosiy funksiya
async def main() -> None:
    """
    Botni ishga tushirish, handlerlarni ro'yxatdan o'tkazish
    va ma'lumotlar bazasini yaratish.
    """
    # Bot yaratish
    bot = Bot(token=TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Bot obyektini routerlarga saqlash
    notification.router.bot = bot
    admin.router.bot = bot
    task.router.bot = bot
    
    # Admin ruxsatlarini admin moduliga yuborish
    admin.ADMIN_IDS = ADMIN_IDS
    
    # Majburiy obuna middleware qo'shish
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    
    # Handlerlarni ro'yxatdan o'tkazish
    dp.include_router(task.router)
    dp.include_router(notification.router)
    dp.include_router(admin.router)
    
    # Ma'lumotlar bazasini ishga tushirish
    logger.info("Ma'lumotlar bazasini ishga tushirish...")
    await setup_db()
    
    # 30 sekundda tasklarni tekshirish uchun background task yaratish
    logger.info("Task tekshiruvchini ishga tushirish...")
    asyncio.create_task(scheduler.check_due_tasks(bot, send_task_notification))
    
    # Bot ishga tushirish
    logger.info("Bot ishga tushirilmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.info("Bot ishga tushirilmoqda...")
    asyncio.run(main()) 