# DinoTasks - Telegram Task Eslatuvchi Bot

Bu bot foydalanuvchilarga task yaratish va ularni vaqtida eslatish imkonini beruvchi Telegram bot.

## Imkoniyatlari

- Yangi task yaratish
- Task vaqti kelganda eslatma olish
- Eslatmani +5 daqiqaga kechiktirish
- Aktiv tasklarni ko'rish
- Admin panel bilan boshqarish
- Majburiy obuna kanali o'rnatish
- Yangi tasklarni kanalga e'lon qilish
- Statistikani ko'rish

## O'rnatish

1. Repositoriyani klonlash:

```bash
git clone https://github.com/username/dinotasks.git
cd dinotasks
```

2. Kerakli kutubxonalarni o'rnatish:

```bash
pip install -r requirements.txt
```

3. `.env` faylini yaratish va sozlash:

```
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=12345678,87654321
```

Bot tokeni olish uchun [@BotFather](https://t.me/BotFather) ga murojaat qiling.
`ADMIN_IDS` parametriga admin foydalanuvchilar ID raqamlarini vergul bilan ajratilgan holda kiriting.

## Ishga tushirish

```bash
python main.py
```

## Admin panel

Admin panel quyidagi imkoniyatlarni taqdim etadi:

- **Majburiy obuna sozlash**: Foydalanuvchilar botdan foydalanishi uchun majburiy kanalga obuna bo'lishi kerak
- **Add Post Channel**: Yangi task yaratilganda xabarlar yuborilishi kerak bo'lgan kanallar ro'yxatiga qo'shish
- **Statistikani ko'rish**: Foydalanuvchilar soni, tasklar soni va boshqa statistikalarni ko'rish

Admin panelni ochish uchun `/admin` komandasini yuboring (faqat `.env` faylida ko'rsatilgan adminlar uchun mavjud).

## Texnologiyalar

- Python 3.8+
- aiogram 3.1.1 (Telegram Bot API uchun)
- SQLite (Ma'lumotlar bazasi)
- aiosqlite (Asynchronous SQLite) 