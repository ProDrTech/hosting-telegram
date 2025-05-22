import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from database import get_config
from handlers.admin import check_user_subscription, is_admin

logger = logging.getLogger(__name__)

class SubscriptionMiddleware(BaseMiddleware):
    """Foydalanuvchining har bir harakatida majburiy kanalga obuna bo'lganligini tekshiruvchi middleware"""
    
    # Qayta tekshirilgan callbacklarni saqlash uchun container
    _processed_callbacks = set()
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Bot obyektini olish
        bot = data.get("bot")
        
        # Admin tekshirish
        user_id = None
        
        # User ID olish va message/callback turini aniqlash
        if isinstance(event, Message):
            user_id = event.from_user.id
            # Admin ekan?
            if is_admin(user_id):
                # Adminlar obunasiz o'tkazib yuboriladi
                return await handler(event, data)
                
            # /start buyrugʻi uchun alohida handler mavjud 
            # (u yerda o'z ichida obuna tekshirish bor)
            if event.text and event.text == "/start":
                return await handler(event, data)
                
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            # Admin ekan?
            if is_admin(user_id):
                # Adminlar obunasiz o'tkazib yuboriladi
                return await handler(event, data)
                
            # Bu subscription callback emasmi?
            # CallbackQuery.data atributiga to'g'ri murojaat qilish
            try:
                callback_data = event.data
                if callback_data == "check_subscription":
                    # check_subscription callback uchun maxsus ishlov qo'shilgan, 
                    # shuning uchun to'g'ridan-to'g'ri handler ga o'tkaziladi
                    return await handler(event, data)
            except AttributeError:
                # data atributi yo'q bo'lsa, davom etamiz
                pass
        
        # Foydalanuvchi ID si yoki bot mavjud emasmi tekshirish
        if not user_id or not bot:
            # Handler ni o'tkazib yuborish va boshqa tekshirmaslik
            return await handler(event, data)
        
        # Kanal ID sini olish
        channel_id = await get_config("REQUIRED_CHANNEL_ID")
        
        # Kanal mavjud emasmi?
        if not channel_id:
            return await handler(event, data)
        
        # Obunani tekshirish
        try:
            subscribed = await check_user_subscription(bot, user_id)
            if subscribed:
                # Agar obuna bo'lsa handler ga o'tkazish
                return await handler(event, data)
        except Exception as e:
            logger.error(f"Obuna tekshirishda xatolik: {e}")
            # Xatolik bo'lsa ham davom etamiz (foydalanuvchidan obuna talab qilamiz)
            
        # Obuna bo'lmagan bo'lsa
        try:
            # Kanal nomini olish
            channel_name = channel_id
            try:
                chat = await bot.get_chat(channel_id)
                channel_name = chat.title or channel_id
            except Exception as e:
                logger.error(f"Kanal ma'lumotlarini olishda xatolik: {e}")
            
            # Kanalga havola yaratish
            channel_link = channel_id
            if not channel_link.startswith(('https://', 'http://')):
                if channel_link.startswith('@'):
                    channel_link = f"https://t.me/{channel_link[1:]}"
                else:
                    channel_link = f"https://t.me/{channel_link}"
            
            # Obuna tekshirish tugmasini yaratish
            check_sub_button = InlineKeyboardBuilder()
            check_sub_button.row(InlineKeyboardButton(
                text=f"📢 {channel_name}ga obuna bo'lish", 
                url=channel_link
            ))
            check_sub_button.row(InlineKeyboardButton(
                text="✅ Obuna bo'ldim", 
                callback_data="check_subscription"
            ))
            
            # Foydalanuvchiga xabar yuborish
            if isinstance(event, Message):
                await event.answer(
                    "Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:",
                    reply_markup=check_sub_button.as_markup()
                )
            elif isinstance(event, CallbackQuery):
                # Callback ID ni tekshirish
                callback_id = str(event.id)
                
                # Bu callback ni ilgari ko'rdikmi?
                if callback_id in self._processed_callbacks:
                    # Allaqachon ko'rilgan callback, bir narsani qilmaymiz
                    await event.answer("Obuna tekshirilmoqda...")
                    return
                
                # Callbackni saqlashga qo'shish
                self._processed_callbacks.add(callback_id)
                
                # 300 tadan ortiq bo'lsa, eski callbacklarni o'chiramiz
                if len(self._processed_callbacks) > 300:
                    self._processed_callbacks.clear()
                
                # Foydalanuvchiga alert sifatida xabar ko'rsatish
                await event.answer("Siz hali kanalga obuna bo'lmagansiz", show_alert=True)
                
                # Xabarni yangilash o'rniga, yangi xabar yuboramiz
                if event.message:
                    try:
                        # Yangi xabar yuborish
                        await event.message.answer(
                            "Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:",
                            reply_markup=check_sub_button.as_markup()
                        )
                        
                        # Eski xabarni o'chirishga harakat qilamiz
                        try:
                            await event.message.delete()
                        except Exception as e:
                            logger.error(f"Eski xabarni o'chirishda xatolik: {e}")
                            
                    except Exception as e:
                        logger.error(f"Callback bilan ishlashda xatolik: {e}")
        except Exception as e:
            logger.error(f"Obuna xabarini yuborishda xatolik: {e}")
            # Har qanday xatolikda ham olib tashlash
            
        # Qayta ishlashni to'xtatish
        return 