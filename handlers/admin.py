import logging
from typing import Union, List, Dict, Any
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (
    add_user, set_config, get_config, add_post_channel, 
    get_post_channels, remove_post_channel, get_user_count, 
    get_completed_tasks_count, get_snoozed_tasks_count, get_active_tasks_count,
    get_tasks_per_user
)

# Router yaratish
router = Router()
logger = logging.getLogger(__name__)

# Global o'zgaruvchilar
ADMIN_IDS: List[int] = []  # Bu main.py dan to'ldiriladi

# Admin FSM holatlari
class AdminFSM(StatesGroup):
    main_menu = State()
    # Majburiy obuna
    waiting_channel_id = State()
    # Post kanal
    waiting_post_channel = State()


# Adminligini tekshirish uchun funksiya
def is_admin(user_id: int) -> bool:
    """Foydalanuvchi admin ekanligini tekshirish"""
    return user_id in ADMIN_IDS


# Admin panel klaviaturasi
def get_admin_keyboard():
    """Admin panel uchun inline tugmalar"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📌 Majburiy obuna sozlash", callback_data="admin:force_subscribe")
    keyboard.button(text="📤 Add Post Channel", callback_data="admin:add_post_channel")
    keyboard.button(text="📊 Statistikani ko'rish", callback_data="admin:statistics")
    keyboard.button(text="🔙 Orqaga / Exit", callback_data="admin:exit")
    keyboard.adjust(1)  # 1 qatorda 1 ta tugma
    return keyboard.as_markup()


# Admin komandasi handler
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Admin panel komandasi"""
    user_id = message.from_user.id
    
    # Admin emasmi?
    if not is_admin(user_id):
        await message.answer("Sizda bu funksiyadan foydalanish huquqi yo'q")
        return
    
    await state.set_state(AdminFSM.main_menu)
    await message.answer(
        "🔧 Admin panel\n\nKerakli bo'limni tanlang:",
        reply_markup=get_admin_keyboard()
    )


# Callback querylar uchun handler
@router.callback_query(F.data.startswith("admin:"))
async def admin_callback_handler(callback: CallbackQuery, state: FSMContext):
    """Admin panelida tugmaga bosish handlerlar"""
    user_id = callback.from_user.id
    
    # Admin emasmi?
    if not is_admin(user_id):
        await callback.answer("Sizda bu funksiyadan foydalanish huquqi yo'q", show_alert=True)
        return
    
    # Tugma bosishni olish
    try:
        data = callback.data.split(":")
        action = data[1] if len(data) > 1 else ""
    except (AttributeError, IndexError, ValueError) as e:
        logger.error(f"CallbackQuery data ni olishda xatolik: {e}")
        await callback.answer("Xatolik yuz berdi", show_alert=True)
        return
    
    # Orqaga tugmasi uchun
    if action == "exit":
        await callback.message.edit_text("Admin panel yopildi.")
        await state.clear()
        return
    
    # Bosh menyu
    if action == "main_menu":
        await state.set_state(AdminFSM.main_menu)
        await callback.message.edit_text(
            "🔧 Admin panel\n\nKerakli bo'limni tanlang:",
            reply_markup=get_admin_keyboard()
        )
        return
    
    # Majburiy obuna sozlash
    if action == "force_subscribe":
        channel_id = await get_config("REQUIRED_CHANNEL_ID")
        current = f"\n\nJoriy kanal: {channel_id}" if channel_id else ""
        
        await state.set_state(AdminFSM.waiting_channel_id)
        await callback.message.edit_text(
            f"📌 Majburiy obuna\n\nMajburiy obuna uchun kanal ID yoki usernameni yuboring. "
            f"Misol: @channel yoki -1001234567890{current}",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Orqaga", callback_data="admin:main_menu"
            ).as_markup()
        )
        return
    
    # Post kanal qo'shish
    if action == "add_post_channel":
        # Mavjud kanallarni ko'rsatish
        channels = await get_post_channels()
        channels_text = ""
        if channels:
            channels_text = "\n\nMavjud kanallar:\n"
            for ch in channels:
                channels_text += f"- {ch['channel_name'] or ch['channel_id']} ({ch['channel_id']})\n"
        
        await state.set_state(AdminFSM.waiting_post_channel)
        await callback.message.edit_text(
            f"📤 Post kanal qo'shish\n\nYangi tasklar yuborilishi uchun kanal ID yoki usernameni yuboring."
            f"Misol: @channel yoki -1001234567890{channels_text}",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Orqaga", callback_data="admin:main_menu"
            ).as_markup()
        )
        return
    
    # Statistika
    if action == "statistics":
        # Statistikani olish
        user_count = await get_user_count()
        completed_tasks = await get_completed_tasks_count()
        snoozed_tasks = await get_snoozed_tasks_count()
        active_tasks = await get_active_tasks_count()
        tasks_per_user = await get_tasks_per_user()
        
        stats_text = (
            "📊 Statistika\n\n"
            f"👥 Foydalanuvchilar soni: {user_count}\n"
            f"✅ Bajarilgan tasklar soni: {completed_tasks}\n"
            f"⏰ Kechiktirilgan tasklar soni: {snoozed_tasks}\n"
            f"📆 Aktiv tasklar soni: {active_tasks}\n"
            f"📈 O'rtacha task/user: {tasks_per_user:.2f}"
        )
        
        await callback.message.edit_text(
            stats_text,
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Orqaga", callback_data="admin:main_menu"
            ).as_markup()
        )
        return
    
    await callback.answer()


# Majburiy obuna uchun kanal id qabul qilish
@router.message(AdminFSM.waiting_channel_id)
async def process_channel_id(message: Message, state: FSMContext):
    """Majburiy obuna uchun kanal ID yoki username qabul qilish"""
    user_id = message.from_user.id
    
    # Admin emasmi?
    if not is_admin(user_id):
        return
    
    channel_id = message.text.strip()
    
    # Konfiguratsiyaga saqlash
    await set_config("REQUIRED_CHANNEL_ID", channel_id)
    
    await message.answer(
        f"✅ Majburiy obuna kanali sozlandi: {channel_id}",
        reply_markup=InlineKeyboardBuilder().button(
            text="🔙 Bosh menyu", callback_data="admin:main_menu"
        ).as_markup()
    )


# Post kanal qo'shish
@router.message(AdminFSM.waiting_post_channel)
async def process_post_channel(message: Message, state: FSMContext):
    """Post kanal ID yoki username qabul qilish"""
    user_id = message.from_user.id
    
    # Admin emasmi?
    if not is_admin(user_id):
        return
    
    channel_id = message.text.strip()
    
    # Kanalga qo'shish
    success = await add_post_channel(channel_id)
    
    if success:
        await message.answer(
            f"✅ Post kanal qo'shildi: {channel_id}",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Bosh menyu", callback_data="admin:main_menu"
            ).as_markup()
        )
    else:
        await message.answer(
            f"❌ Post kanalni qo'shishda xatolik: {channel_id}",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 Bosh menyu", callback_data="admin:main_menu"
            ).as_markup()
        )


# Yangi foydalanuvchilar uchun adminga xabar yuborish
# Bu funksiya boshqa joylarda chaqiriladi
async def notify_admins_new_user(bot: Bot, user_id: int, username: str, full_name: str):
    """Adminlarga yangi foydalanuvchi haqida xabar yuborish"""
    if not ADMIN_IDS:
        logger.warning("Adminlar ro'yxati bo'sh, xabar yuborilmadi")
        return
    
    user_mention = f"@{username}" if username else f"{user_id}"
    message = f"🆕 Yangi foydalanuvchi qo'shildi: {full_name} ({user_mention}) – {user_id}"
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, message)
        except Exception as e:
            logger.error(f"Adminga {admin_id} xabar yuborishda xatolik: {e}")


# Obuna tekshirish funksiyasi 
async def check_user_subscription(bot: Bot, user_id: int) -> bool:
    """Foydalanuvchi majburiy kanalga obuna bo'lganmi tekshirish"""
    # Majburiy kanal ID olish
    channel_id = await get_config("REQUIRED_CHANNEL_ID")
    
    if not channel_id:
        # Majburiy obuna o'rnatilmagan
        return True
    
    try:
        # Kanalga a'zolikni tekshirish
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        # Obuna statusini tekshirish
        status = member.status
        return status in ['creator', 'administrator', 'member']
    except Exception as e:
        logger.error(f"Obuna tekshirishda xatolik: {e}")
        # Xatolik yuzaga kelganda, foydalanuvchiga ruxsat berish
        return True


# Task yuborilganda kanallarga post yuborish
async def post_new_task(bot: Bot, user_id: int, task_name: str, task_datetime: str, username: str = None, full_name: str = None):
    """Yangi task yaratilganda post kanallarga yuborish"""
    # Kanallar ro'yxati
    channels = await get_post_channels()
    if not channels:
        return
    
    # Foydalanuvchi haqida ma'lumot
    user_info = ""
    if username:
        user_info = f"@{username}"
    elif full_name:
        user_info = full_name
    else:
        user_info = f"ID: {user_id}"
    
    message_text = (
        f"🆕 Yangi task: {task_name}\n"
        f"📅 {task_datetime}\n"
        f"👤 Foydalanuvchi: {user_info}"
    )
    
    for channel in channels:
        try:
            await bot.send_message(channel['channel_id'], message_text)
        except Exception as e:
            logger.error(f"Kanallarga {channel['channel_id']} xabar yuborishda xatolik: {e}") 