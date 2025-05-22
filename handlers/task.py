from datetime import datetime
import aiosqlite
import logging
from aiogram.exceptions import TelegramBadRequest

from aiogram import Router, types, F, Bot
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, any_state
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from database import db, add_user
from handlers.admin import check_user_subscription, notify_admins_new_user, post_new_task

# Router yaratish
router = Router()

# Holat mashinalari
class TaskStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()
    waiting_for_time = State()

# Klaviaturalarni yaratish
def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Asosiy klaviatura tugmalarini yaratadi.
    
    Returns:
        ReplyKeyboardMarkup: Asosiy klaviatura
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Yangi Task yaratish")],
            [KeyboardButton(text="⏳ Bajarilmagan Tasklar")],
            [KeyboardButton(text="✅ Bajarilgan Tasklar")]
        ],
        resize_keyboard=True
    )
    return keyboard

# /start komandasi uchun handler
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    """
    /start komandasini qayta ishlaydi.
    
    Args:
        message: Xabar obyekti
        state: FSM holati
    """
    # Foydalanuvchi ma'lumotlarini olish
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username
    
    # Foydalanuvchini bazaga qo'shish
    is_new_user = await add_user(user_id, full_name, username)
    
    # Yangi foydalanuvchi bo'lsa, adminlarga xabar yuborish
    if is_new_user and hasattr(router, 'bot'):
        await notify_admins_new_user(router.bot, user_id, username, full_name)
    
    # Majburiy obunani tekshirish
    subscribed = True
    if hasattr(router, 'bot'):
        subscribed = await check_user_subscription(router.bot, user_id)
    
    if not subscribed:
        # Majburiy kanal uchun tugma yaratish
        channel_id = await db.get_config("REQUIRED_CHANNEL_ID")
        
        # Kanal nomini olish
        channel_name = channel_id
        try:
            chat = await router.bot.get_chat(channel_id)
            channel_name = chat.title or channel_id
        except:
            pass
        
        # Kanalga havola yaratish
        channel_link = channel_id
        if not channel_link.startswith(('https://', 'http://')):
            if channel_link.startswith('@'):
                channel_link = f"https://t.me/{channel_link[1:]}"
            else:
                channel_link = f"https://t.me/{channel_link}"
        
        # Obuna tekshirish tugmasini yaratish
        check_sub_button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📢 {channel_name}ga obuna bo'lish", url=channel_link)],
            [InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_subscription")]
        ])
        
        await message.answer(
            "Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:",
            reply_markup=check_sub_button
        )
        return
    
    # Agar obuna bo'lsa yoki majburiy obuna o'rnatilmagan bo'lsa
    await message.answer(
        f"Assalomu alaykum, {message.from_user.first_name}! Men Tasklar bo'yicha eslatuvchi botman.",
        reply_markup=get_main_keyboard()
    )

# Menyu tugmalarini bosish uchun umumiy handler - FSM holatidan qat'iy nazar birinchi tekshiriladi
@router.message(F.text.in_(["➕ Yangi Task yaratish", "⏳ Bajarilmagan Tasklar", "✅ Bajarilgan Tasklar"]), any_state)
async def handle_menu_buttons_in_any_state(message: types.Message, state: FSMContext) -> None:
    """
    Menyu tugmalari bosilganda, FSM holatidan qat'iy nazar bu handler ishga tushadi.
    
    Args:
        message: Xabar obyekti
        state: FSM holati
    """
    # Joriy holat
    current_state = await state.get_state()
    
    # Agar foydalanuvchi biror holatda bo'lsa (task yaratish jarayonida), holatni tozalash
    if current_state is not None:
        await state.clear()
        await message.answer("Task yaratish bekor qilindi.", reply_markup=get_main_keyboard())
    
    # Tugma turiga qarab mos funksiyani chaqirish
    if message.text == "➕ Yangi Task yaratish":
        await create_new_task(message, state)
    elif message.text == "⏳ Bajarilmagan Tasklar":
        await show_active_tasks(message)
    elif message.text == "✅ Bajarilgan Tasklar":
        await show_completed_tasks(message)

# 'Yangi Task yaratish' tugmasi uchun handler - endi bu faqat dastlabki holatda ishlaydi
@router.message(lambda message: message.text == "➕ Yangi Task yaratish")
async def create_new_task(message: types.Message, state: FSMContext) -> None:
    """
    Yangi task yaratishni boshlaydi.
    
    Args:
        message: Xabar obyekti
        state: FSM holati
    """
    # Avval joriy holatni tozalash
    await state.clear()
    
    # Task yaratish holatini belgilash
    await state.set_state(TaskStates.waiting_for_name)
    await message.answer("Task nomini yozing:")

# Task nomini olish
@router.message(TaskStates.waiting_for_name)
async def process_task_name(message: types.Message, state: FSMContext) -> None:
    """
    Task nomini saqlaydi.
    
    Args:
        message: Xabar obyekti
        state: FSM holati
    """
    await state.update_data(task_name=message.text)
    await state.set_state(TaskStates.waiting_for_date)
    await message.answer(
        "Task bajariladigan sanani kiriting (KK.OO.YY formatda):\n"
        "Masalan: 15.05.25"
    )

# Task sanasini olish va tekshirish
@router.message(TaskStates.waiting_for_date)
async def process_task_date(message: types.Message, state: FSMContext) -> None:
    """
    Task sanasini tekshiradi va saqlaydi.
    
    Args:
        message: Xabar obyekti
        state: FSM holati
    """
    task_date = message.text.strip()
    
    # Sana formatini tekshirish
    try:
        # KK.OO.YY formatidagi sanani tekshirish
        if len(task_date.split('.')) != 3:
            raise ValueError("Noto'g'ri format")
        
        day, month, short_year = task_date.split('.')
        
        # Raqamlarga o'tkazish
        day = int(day)
        month = int(month)
        short_year = int(short_year)
        
        # Yilni to'liq formatga o'tkazish (20XX)
        full_year = 2000 + short_year if short_year < 100 else short_year
        
        # Sanani tekshirish uchun datetime obyektiga o'tkazish
        task_date_obj = datetime(full_year, month, day)
        
        # Bazaga saqlash uchun YYYY-MM-DD formatiga o'tkazish
        formatted_date = f"{full_year:04d}-{month:02d}-{day:02d}"
        
        # Joriy sanadan ilgari bo'lsa, xato qaytarish
        current_date = datetime.now().date()
        if task_date_obj.date() < current_date:
            await message.answer(
                "❌ Kiritilgan sana o'tib ketgan. Iltimos, hozirgi yoki kelajak sanani kiriting "
                "(KK.OO.YY formatda):"
            )
            return
        
    except (ValueError, IndexError, TypeError):
        await message.answer(
            "❌ Noto'g'ri format! Iltimos, sanani KK.OO.YY formatida kiriting.\n"
            "Masalan: 15.05.25"
        )
        return
    
    # Sana ma'lumotlarini saqlash - YYYY-MM-DD formatida
    await state.update_data(task_date=formatted_date)
    
    # Vaqtni so'rash
    await state.set_state(TaskStates.waiting_for_time)
    await message.answer(
        "Task bajariladigan vaqtni kiriting (HH:MM formatda):\n"
        "Masalan: 18:30"
    )

# Task vaqtini olish va saqlash
@router.message(TaskStates.waiting_for_time)
async def process_task_time(message: types.Message, state: FSMContext) -> None:
    """
    Task vaqtini tekshiradi va taskni saqlaydi.
    
    Args:
        message: Xabar obyekti
        state: FSM holati
    """
    task_time = message.text.strip()
    
    # Vaqt formatini tekshirish
    try:
        task_time_obj = datetime.strptime(task_time, "%H:%M")
    except ValueError:
        await message.answer(
            "❌ Noto'g'ri format! Iltimos, vaqtni HH:MM formatida kiriting.\n"
            "Masalan: 18:30"
        )
        return
    
    # Ma'lumotlarni o'qish
    data = await state.get_data()
    task_name = data["task_name"]
    task_date = data["task_date"]  # YYYY-MM-DD formatida
    user_id = message.from_user.id
    
    # Sana va vaqtni birlashtirish va tekshirish
    try:
        task_datetime = datetime.strptime(f"{task_date} {task_time}", "%Y-%m-%d %H:%M")
        
        # O'tib ketgan vaqt emasligini tekshirish
        now = datetime.now()
        if task_datetime < now:
            await message.answer(
                "❌ Siz kiritgan sana va vaqt allaqachon o'tib ketgan. "
                "Iltimos, kelajakdagi vaqtni kiriting:"
            )
            return
    except ValueError:
        await message.answer("Sana va vaqtni kombinatsiya qilishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")
        return
    
    # Taskni databasega qo'shish
    await db.add_task(user_id, task_name, task_date, task_time)
    
    # Task yaratilgani haqida kanallarga yuborish
    if hasattr(router, 'bot'):
        # Foydalanuvchi ma'lumotlarini olish
        username = message.from_user.username
        full_name = message.from_user.full_name
        
        await post_new_task(
            router.bot, 
            user_id, 
            task_name, 
            f"{task_date} {task_time}", 
            username, 
            full_name
        )
    
    # Holatni tozalash
    await state.clear()
    
    # Foydalanuvchiga ko'rsatish uchun qulayroq format (KK.OO.YY)
    day, month, year = task_date.split('-')
    user_friendly_date = f"{day}.{month}.{year[2:]}"
    
    await message.answer(
        f"✅ Task muvaffaqiyatli saqlandi!\n\n"
        f"📝 Task: {task_name}\n"
        f"📅 Sana: {user_friendly_date}\n"
        f"⏰ Vaqt: {task_time}\n\n"
        f"<b>Bajarilishi:</b> {user_friendly_date} {task_time}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard()
    )

# 'Bajarilmagan Tasklar' tugmasi uchun handler
async def show_active_tasks(message: types.Message) -> None:
    """
    Bajarilmagan tasklarni ko'rsatadi.
    
    Args:
        message: Xabar obyekti
    """
    user_id = message.from_user.id
    tasks = await db.get_all_upcoming_tasks(user_id)
    
    if not tasks:
        await message.answer("Sizda hozircha bajarilmagan tasklar yo'q.", reply_markup=get_main_keyboard())
        return
    
    response = "⏳ <b>Bajarilmagan tasklaringiz:</b>\n\n"
    current_date = datetime.now().date()
    
    for task in tasks:
        status_icon = "🔄" if task["status"] == "snoozed" else "⏳"
        task_name = task['task_name']
        
        # task_datetime ni ajratish va formatlash
        task_datetime_str = task.get('task_datetime')
        task_time = task.get('task_time', '')
        
        try:
            if task_datetime_str:
                # task_datetime mavjud bo'lsa, undan foydalanish
                task_dt = datetime.strptime(task_datetime_str, "%Y-%m-%d %H:%M")
                task_date = task_dt.date()
                
                # Bugungi, ertangi yoki kelajakdagi sana ekanligini aniqlash
                if task_date == current_date:
                    date_str = "Bugun"
                elif task_date == current_date + datetime.timedelta(days=1):
                    date_str = "Ertaga"
                else:
                    date_str = task_dt.strftime("%d.%m.%Y")
                
                # Chiroyli formatda vaqtni chiqarish
                time_str = task_dt.strftime("%H:%M")
                
                response += f"{status_icon} <b>{task_name}</b>\n"
                response += f"📅 {date_str}, 🕒 {time_str}\n\n"
            else:
                # task_datetime mavjud bo'lmasa, faqat task_time ni ko'rsatish
                response += f"{status_icon} <b>{task_name}</b>\n"
                response += f"🕒 {task_time}\n\n"
        except Exception as e:
            # Xatolik yuz bersa, oddiy formatda ko'rsatish
            response += f"{status_icon} <b>{task_name}</b>\n"
            response += f"⏰ {task_time}\n\n"
    
    await message.answer(response, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())

# 'Bajarilgan Tasklar' tugmasi uchun handler
async def show_completed_tasks(message: types.Message) -> None:
    """
    Bajarilgan tasklarni ko'rsatadi va o'chirish imkoniyatini beradi.
    
    Args:
        message: Xabar obyekti
    """
    user_id = message.from_user.id
    
    async with aiosqlite.connect(db.DATABASE_NAME) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status = 'completed' ORDER BY task_datetime DESC",
            (user_id,)
        ) as cursor:
            tasks = await cursor.fetchall()
            completed_tasks = [dict(row) for row in tasks]
    
    if not completed_tasks:
        await message.answer("Sizda bajarilgan tasklar yo'q.", reply_markup=get_main_keyboard())
        return
    
    # O'chirish tugmasini yaratish
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Bajarilgan tasklarni o'chirish", callback_data="delete_completed")]
    ])
    
    response = "✅ <b>Bajarilgan tasklaringiz:</b>\n\n"
    
    for task in completed_tasks:
        task_name = task['task_name']
        task_datetime_str = task.get('task_datetime')
        
        try:
            if task_datetime_str:
                task_dt = datetime.strptime(task_datetime_str, "%Y-%m-%d %H:%M")
                formatted_date = task_dt.strftime("%d.%m.%Y %H:%M")
                response += f"✓ <b>{task_name}</b>\n"
                response += f"📅 {formatted_date}\n\n"
            else:
                response += f"✓ <b>{task_name}</b>\n\n"
        except Exception as e:
            response += f"✓ <b>{task_name}</b>\n\n"
    
    await message.answer(
        response, 
        parse_mode=ParseMode.HTML, 
        reply_markup=keyboard
    )

# O'chirish tugmasi bosilganda
@router.callback_query(lambda c: c.data == "delete_completed")
async def delete_completed_tasks_callback(callback_query: types.CallbackQuery) -> None:
    """
    Bajarilgan tasklarni o'chirish uchun callback.
    
    Args:
        callback_query: Callback query
    """
    # Bajarilgan tasklarni o'chirish
    deleted_count = await db.delete_completed_tasks()
    
    # Foydalanuvchiga natija haqida xabar berish
    if deleted_count > 0:
        await callback_query.answer(f"{deleted_count} ta bajarilgan task o'chirildi")
        await callback_query.message.edit_text(
            "✅ Bajarilgan tasklar muvaffaqiyatli o'chirildi!",
            reply_markup=None
        )
    else:
        await callback_query.answer("O'chiriladigan task topilmadi")
        await callback_query.message.edit_text(
            "O'chiriladigan task topilmadi.",
            reply_markup=None
        )

# Obuna tekshirish
@router.callback_query(lambda c: c.data == "check_subscription")
async def check_subscription_callback(callback_query: types.CallbackQuery) -> None:
    """
    Foydalanuvchi obunasini tekshirish uchun callback
    
    Args:
        callback_query: Callback query
    """
    user_id = callback_query.from_user.id
    
    try:
        # Obunani tekshirish
        if hasattr(router, 'bot'):
            subscribed = await check_user_subscription(router.bot, user_id)
        else:
            subscribed = True  # Tekshirish imkoni bo'lmasa
        
        if subscribed:
            # Foydalanuvchiga qisqa javob beramiz
            await callback_query.answer("✅ Obuna tasdiqlandi!", show_alert=True)
            
            try:
                # Yangi xabar yuboramiz, edit_text qilmasdan
                await callback_query.message.answer(
                    f"Assalomu alaykum, {callback_query.from_user.first_name}! Men Tasklar bo'yicha eslatuvchi botman.",
                    reply_markup=get_main_keyboard()
                )
                
                # Original xabarni o'chirishga harakat qilamiz
                try:
                    await callback_query.message.delete()
                except Exception as e:
                    logging.error(f"Eski xabarni o'chirishda xatolik: {e}")
                
            except Exception as e:
                logging.error(f"Obuna tasdiqlagandan keyin xabar yuborishda xatolik: {e}")
                
            return
        
        # Obuna bo'lmaganda
        await callback_query.answer("Siz hali kanalga obuna bo'lmagansiz", show_alert=True)
        
        # Kanal ma'lumotlarini olish
        channel_id = await db.get_config("REQUIRED_CHANNEL_ID")
        
        # Kanal bo'sh ekan
        if not channel_id:
            # Majburiy obuna o'rnatilmagan
            await callback_query.message.answer(
                f"Assalomu alaykum, {callback_query.from_user.first_name}! Men Tasklar bo'yicha eslatuvchi botman.",
                reply_markup=get_main_keyboard()
            )
            return
            
        # Kanal nomini olish
        channel_name = channel_id
        try:
            chat = await router.bot.get_chat(channel_id)
            channel_name = chat.title or channel_id
        except Exception:
            pass
        
        # Kanalga havola yaratish
        channel_link = channel_id
        if not channel_link.startswith(('https://', 'http://')):
            if channel_link.startswith('@'):
                channel_link = f"https://t.me/{channel_link[1:]}"
            else:
                channel_link = f"https://t.me/{channel_link}"
        
        # Obuna tekshirish tugmasini yaratish
        check_sub_button = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=f"📢 {channel_name}ga obuna bo'lish", url=channel_link)],
            [types.InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_subscription")]
        ])
        
        # Obuna bo'lmaganda yangi xabar yuboramiz o'rniga
        try:
            # Xabarni yangilamay, yangi xabar yuboramiz
            await callback_query.message.answer(
                "Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:",
                reply_markup=check_sub_button
            )
            
            # Eski xabarni o'chirishga harakat qilamiz
            try:
                await callback_query.message.delete()
            except Exception as e:
                logging.error(f"Eski xabarni o'chirishda xatolik: {e}")
                
        except Exception as e:
            logging.error(f"Obuna tekshirish callbackida xatolik: {e}")
            # Agar xatolik bo'lsa, foydalanuvchiga ma'lum qilamiz
            await callback_query.answer("Obuna tekshirishda xatolik yuz berdi. Iltimos, /start buyrug'ini bosing.", show_alert=True)
    except Exception as e:
        logging.error(f"Check subscription callback da umumiy xatolik: {e}")
        # Xatolik bo'lsa, foydalanuvchiga ma'lum qilamiz
        await callback_query.answer("Obuna tekshirishda xatolik yuz berdi. Iltimos, /start buyrug'ini bosing.", show_alert=True) 