import logging
from typing import Dict, Any

from aiogram import Router, Bot, types
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from utils import scheduler

# Router yaratish
router = Router()

# Notification uchun inline klaviatura
def get_notification_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """
    Task notification uchun inline klaviatura yaratadi.
    
    Args:
        task_id: Task ID
        
    Returns:
        InlineKeyboardMarkup: "+5 min" va "✅ Bajardim" tugmali klaviatura
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="+5 min", callback_data=f"postpone_{task_id}"),
                InlineKeyboardButton(text="✅ Bajardim", callback_data=f"complete_{task_id}")
            ]
        ]
    )
    return keyboard

# Task eslatmasi uchun xabar yuborish
async def send_task_notification(bot: Bot, user_id: int, task_id: int, task_name: str) -> None:
    """
    Task vaqti kelganda avvalgi eslatma xabarini yuboradi.
    
    Args:
        bot: Bot obyekti
        user_id: Foydalanuvchi ID
        task_id: Task ID
        task_name: Task nomi
    """
    try:
        # Task hozir 'active' statusda - u hali bajarilmagan yoki kechiktirilmagan
        logging.info(f"Task {task_id} ({task_name}) vaqti keldi, eslatma yuborilmoqda")
        
        await bot.send_message(
            chat_id=user_id,
            text=f"⏰ Eslatma: {task_name} taskni bajarish vaqti keldi!",
            parse_mode=None,  # Markdown formatini o'chirib qo'yamiz
            reply_markup=get_notification_keyboard(task_id)
        )
        
        # Eslatma loopini boshlatish - task id ni ham task_name ga qo'shamiz
        # MUHIM: Task statusini o'zgartirmaymiz - loop to'xtatilsa ham activ bo'lib qoladi
        loop_task_name = f"{task_id}_{task_name}"
        scheduler.start_task_reminder_loop(user_id, task_id, loop_task_name, send_reminder_message)
    except Exception as e:
        logging.error(f"Notification yuborishda xatolik: {e}")

# Reminder xabarini yuborish
async def send_reminder_message(user_id: int, task_name: str) -> None:
    """
    Takroriy eslatma xabarini yuboradi.
    
    Args:
        user_id: Foydalanuvchi ID
        task_name: Task nomi
    """
    try:
        bot = router.bot
        # Task ID olish uchun
        task_id = 0
        original_task_name = task_name
        
        # Agar task_name formatida task_id_user_id ko'rinishida bo'lsa, task_id ni ajratib olish
        if "_" in task_name and task_name.split("_")[0].isdigit():
            try:
                task_id = int(task_name.split("_")[0])
                # Foydalanuvchi uchun task nomini tozalash - task_id ni olib tashlash
                parts = task_name.split("_")
                if len(parts) > 1:
                    original_task_name = "_".join(parts[1:])
            except (ValueError, IndexError) as e:
                logging.warning(f"Task ID ajratishda xatolik: {e}")
        
        # Markdown formatini o'chirib yuborish
        logging.info(f"Eslatma yuborilmoqda: {original_task_name}, taskID: {task_id}")
        
        await bot.send_message(
            chat_id=user_id,
            text=f"⏰ {original_task_name} – Hali ham bajarmadingiz. Iltimos, bajaring.",
            parse_mode=None,  # Markdown formatini o'chirib qo'yamiz
            reply_markup=get_notification_keyboard(task_id)
        )
    except Exception as e:
        logging.error(f"Reminder xabarini yuborishda xatolik: {e}, task_name: {task_name}")

# Postpone callback handler
@router.callback_query(lambda c: c.data.startswith("postpone_"))
async def process_postpone(callback_query: types.CallbackQuery) -> None:
    """
    "+5 min" tugmasini bosganda taskni kechiktiradi.
    
    Args:
        callback_query: Callback query obyekti
    """
    # Faqat task egasiga tugma bosilishini tekshirish
    user_id = callback_query.from_user.id
    task_id = int(callback_query.data.split("_")[1])
    
    # Avval eslatma loopini to'xtatish
    if scheduler.stop_reminder_loop(user_id, task_id):
        logging.info(f"Task ID {task_id} uchun eslatma loopi to'xtatildi")
    else:
        logging.warning(f"Task ID {task_id} uchun eslatma loopi topilmadi")
    
    # Task vaqtini 5 minutga kechiktirish
    await db.postpone_task(task_id, 5)
    
    await callback_query.answer("Task 5 minutga kechiktirildi!")
    await callback_query.message.edit_text(
        f"{callback_query.message.text}\n\n✅ +5 daqiqaga kechiktirildi."
    )

# Complete callback handler
@router.callback_query(lambda c: c.data.startswith("complete_"))
async def process_complete(callback_query: types.CallbackQuery) -> None:
    """
    "✅ Bajardim" tugmasini bosganda taskni bajarilgan deb belgilaydi.
    
    Args:
        callback_query: Callback query obyekti
    """
    # Faqat task egasiga tugma bosilishini tekshirish
    user_id = callback_query.from_user.id
    task_id = int(callback_query.data.split("_")[1])
    
    # Avval eslatma loopini to'xtatish
    if scheduler.stop_reminder_loop(user_id, task_id):
        logging.info(f"Task ID {task_id} uchun eslatma loopi to'xtatildi")
    else:
        logging.warning(f"Task ID {task_id} uchun eslatma loopi topilmadi")
    
    # Taskni bajarilgan deb belgilash
    await db.mark_task_completed(task_id)
    
    await callback_query.answer("Task bajarilgan deb belgilandi!")
    await callback_query.message.edit_text(
        f"{callback_query.message.text}\n\n✅ Bajarilgan deb belgilandi!"
    ) 