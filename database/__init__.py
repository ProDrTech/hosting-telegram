from database.db import (
    init_db, add_task, get_active_tasks, get_upcoming_tasks, 
    get_due_tasks, postpone_task, mark_task_completed, 
    reactivate_snoozed_tasks, get_all_upcoming_tasks,
    # Admin panel uchun funksiyalar
    create_users_table, create_config_table, create_post_channels_table,
    add_user, get_user_count, get_completed_tasks_count, get_snoozed_tasks_count,
    get_active_tasks_count, get_tasks_per_user, set_config, get_config,
    add_post_channel, get_post_channels, remove_post_channel
)

async def setup_db():
    """Barcha ma'lumotlar bazasi jadvallarini yaratish"""
    await init_db()
    await create_users_table()
    await create_config_table()
    await create_post_channels_table()

__all__ = [
    'init_db', 'add_task', 'get_active_tasks', 'get_upcoming_tasks',
    'get_due_tasks', 'postpone_task', 'mark_task_completed',
    'reactivate_snoozed_tasks', 'get_all_upcoming_tasks',
    # Admin panel uchun funksiyalar
    'create_users_table', 'create_config_table', 'create_post_channels_table',
    'add_user', 'get_user_count', 'get_completed_tasks_count', 'get_snoozed_tasks_count',
    'get_active_tasks_count', 'get_tasks_per_user', 'set_config', 'get_config',
    'add_post_channel', 'get_post_channels', 'remove_post_channel',
    # Yig'ilgan funksiyalar
    'setup_db'
] 