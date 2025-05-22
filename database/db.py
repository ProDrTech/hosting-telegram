import aiosqlite
import datetime
import logging
from typing import Dict, List, Any, Optional

DATABASE_NAME = "tasks.db"

# Loggerga sozlash
logger = logging.getLogger(__name__)

async def init_db():
    """Ma'lumotlar bazasini yaratish va jadvallarni sozlash"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Avval tasks jadvalining mavjudligini tekshirish
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        table_exists = await cursor.fetchone()
        
        if not table_exists:
            # Yangi jadval yaratish task_datetime bilan
            await db.execute("""
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_name TEXT NOT NULL,
                task_time TEXT NOT NULL,
                task_datetime TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_completed BOOLEAN DEFAULT FALSE,
                status TEXT DEFAULT 'active'
            )
            """)
            await db.commit()
        else:
            # Mavjud jadvalga task_datetime qo'shish
            try:
                await db.execute("ALTER TABLE tasks ADD COLUMN task_datetime TEXT")
                # Mavjud tasklar uchun task_datetime ni to'ldirish
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                await db.execute(f"UPDATE tasks SET task_datetime = task_time || ' {today}'")
                await db.commit()
                logger.info("Jadvalga task_datetime ustuni qo'shildi va mavjud ma'lumotlar yangilandi")
            except aiosqlite.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info("task_datetime ustuni allaqachon mavjud")
                else:
                    logger.error(f"Jadval o'zgartirishda xatolik: {e}")

async def add_task(user_id: int, task_name: str, task_date: str, task_time: str) -> None:
    """
    Yangi task qo'shish
    
    Args:
        user_id: Foydalanuvchi ID
        task_name: Task nomi
        task_date: Task sanasi (YYYY-MM-DD formatda)
        task_time: Task vaqti (HH:MM formatda)
    """
    # Sana va vaqtni birlashtirish
    task_datetime = f"{task_date} {task_time}"
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            "INSERT INTO tasks (user_id, task_name, task_time, task_datetime, status) VALUES (?, ?, ?, ?, 'active')",
            (user_id, task_name, task_time, task_datetime)
        )
        await db.commit()
        logger.info(f"Yangi task qo'shildi: {task_name}, {task_datetime}")

async def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    """Task ID bo'yicha tasklarni olish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_active_tasks(user_id: int) -> List[Dict[str, Any]]:
    """Foydalanuvchining barcha aktiv tasklarini olish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND status = 'active' ORDER BY task_datetime",
            (user_id,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

async def get_upcoming_tasks(user_id: int) -> List[Dict[str, Any]]:
    """Foydalanuvchining kelayotgan (vaqti hali kelmagan) tasklarini olish"""
    current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM tasks 
            WHERE user_id = ? AND status = 'active' AND task_datetime > ? 
            ORDER BY task_datetime
            """,
            (user_id, current_datetime)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

async def get_all_upcoming_tasks(user_id: int) -> List[Dict[str, Any]]:
    """Foydalanuvchining kelayotgan barcha tasklarini olish (active va snoozed)"""
    current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM tasks 
            WHERE user_id = ? AND (status = 'active' OR status = 'snoozed') AND task_datetime > ? 
            ORDER BY task_datetime
            """,
            (user_id, current_datetime)
        ) as cursor:
            tasks = await cursor.fetchall()
            result = [dict(row) for row in tasks]
            logger.info(f"User {user_id} uchun {len(result)} ta upcoming task topildi")
            return result

async def get_due_tasks() -> List[Dict[str, Any]]:
    """Vaqti kelgan tasklarni olish"""
    # Hozirgi vaqt
    now = datetime.datetime.now()
    current_datetime = now.strftime("%Y-%m-%d %H:%M")
    
    # Bir daqiqa oldingi vaqt
    one_minute_ago = now - datetime.timedelta(minutes=1)
    one_minute_ago_str = one_minute_ago.strftime("%Y-%m-%d %H:%M")
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM tasks 
            WHERE status = 'active' 
            AND task_datetime >= ? 
            AND task_datetime <= ?
            """,
            (one_minute_ago_str, current_datetime)
        ) as cursor:
            tasks = await cursor.fetchall()
            result = [dict(row) for row in tasks]
            
            # Agar vaqti kelgan tasklar topilsa log yozish
            if result:
                task_ids = [t['id'] for t in result]
                logger.info(f"Vaqti kelgan tasklar topildi, IDs: {task_ids}")
            
            return result

async def postpone_task(task_id: int, minutes: int = 5) -> None:
    """Taskni ma'lum vaqtga kechiktirish"""
    # Avval task mavjudligini tekshirish
    task = await get_task_by_id(task_id)
    if not task:
        logger.warning(f"Task ID {task_id} topilmadi, kechiktirishni o'tkazib yuborildi")
        return
    
    logger.info(f"Task ID {task_id} {minutes} daqiqaga kechiktirilmoqda. Oldingi status: {task['status']}")
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        try:
            # Task datetimeni olish va yangi vaqtni hisoblash
            task_datetime_str = task['task_datetime'] if 'task_datetime' in task else None
            task_time_str = task['task_time'] if 'task_time' in task else None
            
            if task_datetime_str:
                # task_datetime mavjud bo'lsa, undan foydalanish
                task_dt = datetime.datetime.strptime(task_datetime_str, "%Y-%m-%d %H:%M")
                new_dt = task_dt + datetime.timedelta(minutes=minutes)
                new_datetime_str = new_dt.strftime("%Y-%m-%d %H:%M")
                new_time_str = new_dt.strftime("%H:%M")
            elif task_time_str:
                # Faqat task_time mavjud bo'lsa
                current_date = datetime.datetime.now().strftime("%Y-%m-%d")
                task_datetime_str = f"{current_date} {task_time_str}"
                task_dt = datetime.datetime.strptime(task_datetime_str, "%Y-%m-%d %H:%M")
                new_dt = task_dt + datetime.timedelta(minutes=minutes)
                new_datetime_str = new_dt.strftime("%Y-%m-%d %H:%M")
                new_time_str = new_dt.strftime("%H:%M")
            else:
                # Ikkovi ham yo'q bo'lsa
                logger.error(f"Task ID {task_id} vaqtni olishda xatolik - task_datetime va task_time yo'q")
                return
            
            # Task vaqti va statusini yangilash
            await db.execute(
                "UPDATE tasks SET task_time = ?, task_datetime = ?, status = 'snoozed', is_completed = FALSE WHERE id = ?",
                (new_time_str, new_datetime_str, task_id)
            )
            await db.commit()
            
            logger.info(f"Task ID {task_id} muvaffaqiyatli kechiktirildi. Yangi vaqt: {new_datetime_str}")
        except Exception as e:
            logger.error(f"Task ID {task_id} kechiktirishda xatolik: {e}")

async def mark_task_completed(task_id: int) -> None:
    """Taskni bajarilgan deb belgilash"""
    # Avval task mavjudligini tekshirish
    task = await get_task_by_id(task_id)
    if not task:
        logger.warning(f"Task ID {task_id} topilmadi, bajarilgan deb belgilashni o'tkazib yuborildi")
        return
    
    logger.info(f"Task ID {task_id} bajarilgan deb belgilanmoqda. Oldingi status: {task['status']}")
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            "UPDATE tasks SET status = 'completed', is_completed = TRUE WHERE id = ?",
            (task_id,)
        )
        await db.commit()
        logger.info(f"Task ID {task_id} muvaffaqiyatli bajarilgan deb belgilandi")

async def reactivate_snoozed_tasks() -> None:
    """Kechiktirilgan tasklarni faollashtirish, agar ular vaqti kelgan bo'lsa"""
    current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Kechiktirilgan tasklarni olish
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, task_datetime FROM tasks WHERE status = 'snoozed'"
        ) as cursor:
            tasks = await cursor.fetchall()
            # sqlite3.Row ni dict ga konvert qilish
            tasks = [dict(row) for row in tasks]
        
        if tasks:
            task_ids = [t['id'] for t in tasks]
            logger.debug(f"Kechiktirilgan tasklar tekshirilmoqda: {task_ids}")
            
        for task in tasks:
            task_id = task['id']
            # get() o'rniga to'g'ridan-to'g'ri indeks bilan olish
            task_datetime = task.get('task_datetime')
            
            if not task_datetime:
                logger.warning(f"Task ID {task_id} uchun task_datetime mavjud emas")
                continue
            
            try:
                # Task vaqtini datetime obyektiga aylantirish
                task_dt = datetime.datetime.strptime(task_datetime, "%Y-%m-%d %H:%M")
                current_dt = datetime.datetime.now()
                
                # Vaqtni tekshirish - agar taskning vaqti kelgan bo'lsa yoki o'tib ketgan bo'lsa
                if current_dt >= task_dt:
                    logger.info(f"Task ID {task_id} vaqti keldi, 'active' holatiga o'tkazilmoqda")
                    await db.execute(
                        "UPDATE tasks SET status = 'active' WHERE id = ?",
                        (task_id,)
                    )
                    await db.commit()
            except Exception as e:
                # Vaqtni konvert qilishda xatolik
                logger.error(f"Task ID {task_id} vaqtini konvert qilishda xatolik: {e}")
                pass

async def delete_completed_tasks() -> int:
    """
    Bajarilgan (completed) tasklarni ma'lumotlar bazasidan o'chiradi
    
    Returns:
        int: O'chirilgan tasklar soni
    """
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute(
            "DELETE FROM tasks WHERE status = 'completed'"
        )
        deleted_count = cursor.rowcount
        await db.commit()
        
        if deleted_count > 0:
            logger.info(f"{deleted_count} ta bajarilgan task o'chirildi")
        
        return deleted_count

async def clean_old_completed_tasks(days: int = 3) -> int:
    """
    Ma'lum kundan oldin bajarilgan tasklarni o'chiradi
    
    Args:
        days: Necha kundan oldingi bajarilgan tasklarni o'chirish (default: 3)
        
    Returns:
        int: O'chirilgan tasklar soni
    """
    # Xozirgi vaqtdan N kun oldingi sanani hisoblash
    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute(
            """
            DELETE FROM tasks 
            WHERE status = 'completed' 
            AND substr(task_datetime, 1, 10) <= ?
            """,
            (cutoff_date,)
        )
        deleted_count = cursor.rowcount
        await db.commit()
        
        if deleted_count > 0:
            logger.info(f"{deleted_count} ta eski bajarilgan task ({days} kundan oldingi) o'chirildi")
        
        return deleted_count

# --- Admin panel uchun funksiyalar ---

async def create_users_table():
    """Foydalanuvchilar jadvalini yaratish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Avval users jadvalining mavjudligini tekshirish
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = await cursor.fetchone()
        
        if not table_exists:
            # Yangi jadval yaratish
            await db.execute("""
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
            """)
            await db.commit()
            logger.info("Users jadvali yaratildi")

async def create_config_table():
    """Konfiguratsiya jadvalini yaratish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Avval config jadvalining mavjudligini tekshirish
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
        table_exists = await cursor.fetchone()
        
        if not table_exists:
            # Yangi jadval yaratish
            await db.execute("""
            CREATE TABLE config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            await db.commit()
            logger.info("Config jadvali yaratildi")

async def create_post_channels_table():
    """Post kanallar jadvalini yaratish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Avval jadvalning mavjudligini tekshirish
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='post_channels'")
        table_exists = await cursor.fetchone()
        
        if not table_exists:
            # Yangi jadval yaratish
            await db.execute("""
            CREATE TABLE post_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE,
                channel_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            await db.commit()
            logger.info("Post kanallar jadvali yaratildi")

async def add_user(user_id: int, full_name: str, username: str = None) -> bool:
    """
    Yangi foydalanuvchi qo'shish yoki mavjud foydalanuvchini yangilash
    
    Args:
        user_id: Foydalanuvchi ID
        full_name: Foydalanuvchi to'liq ismi
        username: Foydalanuvchi @username (optional)
    
    Returns:
        bool: True agar yangi foydalanuvchi qo'shilgan bo'lsa, False agar foydalanuvchi yangilangan bo'lsa
    """
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Foydalanuvchi mavjudligini tekshirish
        user_exists = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        user_exists = await user_exists.fetchone()
        
        if user_exists:
            # Mavjud foydalanuvchini yangilash
            await db.execute(
                "UPDATE users SET full_name = ?, username = ?, is_active = TRUE WHERE user_id = ?",
                (full_name, username, user_id)
            )
            await db.commit()
            logger.info(f"Mavjud foydalanuvchi {user_id} ma'lumotlari yangilandi")
            return False
        else:
            # Yangi foydalanuvchi qo'shish
            await db.execute(
                "INSERT INTO users (user_id, full_name, username) VALUES (?, ?, ?)",
                (user_id, full_name, username)
            )
            await db.commit()
            logger.info(f"Yangi foydalanuvchi qo'shildi: {user_id} ({full_name})")
            return True

async def get_user_count() -> int:
    """Foydalanuvchilar sonini olish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        count = await cursor.fetchone()
        return count[0] if count else 0

async def get_completed_tasks_count() -> int:
    """Bajarilgan tasklar sonini olish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'")
        count = await cursor.fetchone()
        return count[0] if count else 0

async def get_snoozed_tasks_count() -> int:
    """Kechiktirilgan tasklar sonini olish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'snoozed'")
        count = await cursor.fetchone()
        return count[0] if count else 0

async def get_active_tasks_count() -> int:
    """Aktiv tasklar sonini olish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'active'")
        count = await cursor.fetchone()
        return count[0] if count else 0

async def get_tasks_per_user() -> float:
    """Har bir foydalanuvchiga o'rtacha task sonini hisoblash"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Barcha tasklar soni
        cursor = await db.execute("SELECT COUNT(*) FROM tasks")
        task_count = await cursor.fetchone()
        task_count = task_count[0] if task_count else 0
        
        # Foydalanuvchilar soni
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        user_count = await cursor.fetchone()
        user_count = user_count[0] if user_count else 0
        
        # O'rtacha hisoblash
        if user_count > 0:
            return round(task_count / user_count, 2)
        else:
            return 0.0

async def set_config(key: str, value: str) -> None:
    """Konfiguratsiya qiymatini o'rnatish yoki yangilash"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Mavjudligini tekshirish
        cursor = await db.execute("SELECT 1 FROM config WHERE key = ?", (key,))
        exists = await cursor.fetchone()
        
        if exists:
            # Yangilash
            await db.execute(
                "UPDATE config SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
                (value, key)
            )
        else:
            # Yangi qo'shish
            await db.execute(
                "INSERT INTO config (key, value) VALUES (?, ?)",
                (key, value)
            )
        
        await db.commit()
        logger.info(f"Konfiguratsiya yangilandi: {key} = {value}")

async def get_config(key: str) -> Optional[str]:
    """Konfiguratsiya qiymatini olish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT value FROM config WHERE key = ?", (key,))
        result = await cursor.fetchone()
        return result[0] if result else None

async def add_post_channel(channel_id: str, channel_name: str = None) -> bool:
    """
    Yangi post kanali qo'shish
    
    Args:
        channel_id: Kanal ID yoki username
        channel_name: Kanal nomi (optional)
    
    Returns:
        bool: True agar muvaffaqiyatli qo'shilgan bo'lsa
    """
    async with aiosqlite.connect(DATABASE_NAME) as db:
        try:
            # Kanal mavjud emasligini tekshirish
            cursor = await db.execute("SELECT 1 FROM post_channels WHERE channel_id = ?", (channel_id,))
            exists = await cursor.fetchone()
            
            if exists:
                # Yangilash
                await db.execute(
                    "UPDATE post_channels SET channel_name = ? WHERE channel_id = ?",
                    (channel_name, channel_id)
                )
                await db.commit()
                logger.info(f"Post kanali yangilandi: {channel_id}")
                return True
            else:
                # Yangi qo'shish
                await db.execute(
                    "INSERT INTO post_channels (channel_id, channel_name) VALUES (?, ?)",
                    (channel_id, channel_name)
                )
                await db.commit()
                logger.info(f"Yangi post kanali qo'shildi: {channel_id}")
                return True
        except Exception as e:
            logger.error(f"Post kanali qo'shishda xatolik: {e}")
            return False

async def get_post_channels() -> List[Dict[str, Any]]:
    """Barcha post kanallarini olish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM post_channels ORDER BY added_at DESC")
        channels = await cursor.fetchall()
        return [dict(row) for row in channels]

async def remove_post_channel(channel_id: str) -> bool:
    """Post kanalini o'chirish"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        try:
            cursor = await db.execute("DELETE FROM post_channels WHERE channel_id = ?", (channel_id,))
            deleted = cursor.rowcount > 0
            await db.commit()
            
            if deleted:
                logger.info(f"Post kanali o'chirildi: {channel_id}")
            
            return deleted
        except Exception as e:
            logger.error(f"Post kanalini o'chirishda xatolik: {e}")
            return False 