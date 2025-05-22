import asyncio
import logging
from typing import Dict, Any, Callable, Coroutine, Optional
from datetime import datetime

from aiogram import Bot
from database import db
import aiosqlite

# Faol eslatma looplarini saqlash uchun dictionary
# Key: {task_id}_{user_id}, Value: task loop
active_notification_loops: Dict[str, asyncio.Task] = {}

# Loggerni sozlash
logger = logging.getLogger(__name__)

async def check_due_tasks(bot: Bot, notification_callback: Callable[[Bot, int, int, str], Coroutine[Any, Any, None]]) -> None:
    """
    Har daqiqada vaqti kelgan tasklarni tekshiradi va eslatma yuboradi.
    
    Args:
        bot: Bot obyekti xabar yuborish uchun
        notification_callback: Task vaqti kelganda chaqiriladigan funksiya
    """
    # Tasklar tozalagichni hisoblash uchun counter
    clean_counter = 0
    
    while True:
        try:
            # Kechiktirilgan tasklarni faollashtirish, agar ular vaqti kelgan bo'lsa
            await db.reactivate_snoozed_tasks()
            
            # Vaqti kelgan tasklarni olish
            tasks = await db.get_due_tasks()
            logger.info(f"Vaqti kelgan {len(tasks)} ta task tekshirilmoqda")
            
            for task in tasks:
                # Taskni egasiga eslatma yuborish
                user_id = task["user_id"]
                task_id = task["id"]
                task_name = task["task_name"]
                
                # Task hali aktiv ekanligini tekshirish
                task_current = await db.get_task_by_id(task_id)
                if not task_current or task_current["status"] != "active":
                    logger.warning(f"Task ID {task_id} aktiv emas, eslatma o'tkazib yuborildi")
                    continue
                
                # Callback funksiyasini chaqirish
                await notification_callback(bot, user_id, task_id, task_name)

            # Har 3 soatda (360 takrorlashdan so'ng, 30 sekund oralig'ida) bajarilgan tasklarni tozalash
            clean_counter += 1
            if clean_counter >= 360:  # 30 sekund * 360 = 10800 sekund = 3 soat
                logger.info("Bajarilgan tasklarni tozalash boshlanmoqda...")
                deleted_count = await db.clean_old_completed_tasks(days=3)
                clean_counter = 0
                
        except Exception as e:
            logger.error(f"Tasklarni tekshirishda xatolik: {e}")
        
        # Har 30 sekundda takrorlash
        await asyncio.sleep(30)

# Task eslatma loopini boshqarish
def start_task_reminder_loop(user_id: int, task_id: int, task_name: str, 
                           reminder_callback: Callable[[int, str], Coroutine[Any, Any, None]]) -> asyncio.Task:
    """
    Eslatma xabarlarini yuborish uchun loop yaratadi.
    
    Args:
        user_id: Foydalanuvchi ID
        task_id: Task ID
        task_name: Task nomi
        reminder_callback: Har bir eslatma uchun chaqiriladigan funksiya
        
    Returns:
        asyncio.Task: Yaratilgan task
    """
    # Avvalgi eslatma loopi bo'lsa, to'xtatish
    loop_key = f"{task_id}_{user_id}"
    
    # Avvalgi loopni to'xtatish
    stop_reminder_loop(user_id, task_id)
    
    # Debug xabarni chiqarish
    logger.info(f"Yangi eslatma loopi yaratyapti: {loop_key}")
    
    # Yangi loop yaratish
    try:
        loop = asyncio.create_task(_task_reminder_loop(user_id, task_id, task_name, reminder_callback))
        active_notification_loops[loop_key] = loop
        return loop
    except Exception as e:
        logger.error(f"Loop yaratishda xatolik: {e}")
        return None

async def _task_reminder_loop(user_id: int, task_id: int, task_name: str, 
                            reminder_callback: Callable[[int, str], Coroutine[Any, Any, None]]) -> None:
    """
    Task eslatma loopini ichki funksiyasi. Har 30 sekundda eslatma yuboradi.
    
    Args:
        user_id: Foydalanuvchi ID
        task_id: Task ID
        task_name: Task nomi
        reminder_callback: Har bir eslatma uchun chaqiriladigan funksiya
    """
    reminder_count = 0
    max_reminders = 10  # 5 minut = 10 ta 30 sekundlik eslatma
    loop_key = f"{task_id}_{user_id}"
    
    logger.info(f"Reminder loop boshlanmoqda: {loop_key}")
    
    try:
        while reminder_count < max_reminders:
            # 30 sekund kutish
            await asyncio.sleep(30)
            
            # Agar loop bekor qilingan bo'lsa, chiqib ketish
            if loop_key not in active_notification_loops:
                logger.info(f"Loop to'xtatilgan: {loop_key}")
                break
            
            # Task statusini tekshirish - agar status 'snoozed' bo'lsa, eslatmani yubormaslik
            task_current = await db.get_task_by_id(task_id)
            
            # Agar task o'chirilgan bo'lsa
            if not task_current:
                logger.warning(f"Task ID {task_id} topilmadi, eslatma loopi to'xtatilmoqda")
                stop_reminder_loop(user_id, task_id)
                break
                
            # Agar task statusini o'zgargan bo'lsa
            if task_current["status"] != "active":
                logger.info(f"Task {task_id} statusi '{task_current['status']}', eslatma loopi to'xtatilmoqda")
                stop_reminder_loop(user_id, task_id)
                break
                
            # Eslatma funksiyasini chaqirish
            logger.info(f"Eslatma yuborilmoqda: {loop_key}, count: {reminder_count}")
            await reminder_callback(user_id, task_name)
            
            reminder_count += 1
    except asyncio.CancelledError:
        logger.info(f"Loop bekor qilindi: {loop_key}")
    except Exception as e:
        logger.error(f"Reminder loop xatolik: {e}")
    finally:
        # Loop tugaganda, agar hali aktiv bo'lsa, o'chirish
        if loop_key in active_notification_loops:
            logger.info(f"Loop tugatilmoqda: {loop_key}")
            del active_notification_loops[loop_key]

def stop_reminder_loop(user_id: int, task_id: int) -> bool:
    """
    Eslatma loopini to'xtatadi.
    
    Args:
        user_id: Foydalanuvchi ID
        task_id: Task ID
        
    Returns:
        bool: Loop to'xtatilgan bo'lsa True, aks holda False
    """
    loop_key = f"{task_id}_{user_id}"
    if loop_key in active_notification_loops:
        # Loopni bekor qilish
        try:
            logger.info(f"Loop to'xtatilmoqda: {loop_key}")
            loop = active_notification_loops[loop_key]
            loop.cancel()
            del active_notification_loops[loop_key]
            return True
        except Exception as e:
            logger.error(f"Loop to'xtatishda xatolik: {e}")
    else:
        logger.info(f"Loop topilmadi: {loop_key}")
    return False 