import json
import os
import logging
import asyncio
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== КОНФИГ ==========
TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ========== СЛОВАРИ ПЕРЕВОДОВ ==========
TEXTS = {
    "ru": {
        "welcome": "🎁 Добро пожаловать в магазин подарочных наборов!\n\nВыберите категорию:",
        "choose_cat": "Выберите категорию:",
        "choose_subcat": "Категория: {cat}\nВыберите подкатегорию:",
        "cat_girl": "🎁 Для девушки",
        "cat_boy": "🎁 Для парня",
        "back": "⬅️ Назад",
        "home": "🏠 В начало",
        "boy_dad": "Для папы", "boy_friend": "Для друга", "boy_love": "Для любимого", "boy_brother": "Для брата",
        "girl_mom": "Для мамы", "girl_friend": "Для подруги", "girl_love": "Для любимой", "girl_sister": "Для сестры",
        "choose_size": "Выбрано: {cat} → {sub}\n\nВыберите размер бокса:",
        "size_S": "📦 Бокс S — 30 BYN",
        "size_L": "📦 Бокс L — 75 BYN",
        "size_XL": "📦 Бокс XL — 150 BYN",
        "size_chosen": "Размер: {size} — {price} BYN\n\nХотите добавить предпочтения или исключить что-то из подарка?",
        "prefs_add": "✅ Добавить предпочтения",
        "prefs_exclude": "🚫 Исключить из подарка",
        "prefs_skip": "⏭ Пропустить",
        "write_prefs": "Напишите, что добавить в подарок.\n\n⚠️ Обратите внимание: бюджет на дополнительные предпочтения не должен превышать 50% от стоимости коробки. Товары 18+ выдаются только по паспорту:",
        "write_exclude": "Напишите, что исключить из подарка:",
        "prefs_saved": "Предпочтения сохранены.",
        "exclude_saved": "Исключения сохранены.",
        "write_address": "🏠 Пожалуйста, напишите ваш адрес доставки (город, улица, дом, квартира):",
        "address_saved": "Адрес сохранён.",
        "have_promo": "У вас есть промокод?",
        "promo_enter": "🎟 Ввести промокод",
        "promo_skip": "⏭ Без промокода",
        "write_promo": "Введите промокод:",
        "promo_not_found": "❌ Промокод не найден.\n\nПопробуйте другой.",
        "promo_applied": "✅ Промокод применён: скидка {discount}%.",
        "order_success": "✅ Заказ #{id} оформлен!\n\n💰 Итого: {price} BYN (скидка {discount}%)\n\nМы свяжемся с вами.",
        "order_error": "❌ Ошибка при оформлении заказа.",
        "status_update": "📬 Статус вашего заказа #{id} обновлён: {status}",
        "lang_select": "🇷🇺 Выберите язык / 🇬🇧 Choose language:",
        "start_btn": "🏠 В начало",
    },
    "en": {
        "welcome": "🎁 Welcome to the gift shop!\n\nChoose a category:",
        "choose_cat": "Choose a category:",
        "choose_subcat": "Category: {cat}\nChoose a subcategory:",
        "cat_girl": "🎁 For Her",
        "cat_boy": "🎁 For Him",
        "back": "⬅️ Back",
        "home": "🏠 Main Menu",
        "boy_dad": "For Dad", "boy_friend": "For Friend", "boy_love": "For Beloved", "boy_brother": "For Brother",
        "girl_mom": "For Mom", "girl_friend": "For Girlfriend", "girl_love": "For Beloved", "girl_sister": "For Sister",
        "choose_size": "Selected: {cat} → {sub}\n\nChoose box size:",
        "size_S": "📦 Box S — 30 BYN",
        "size_L": "📦 Box L — 75 BYN",
        "size_XL": "📦 Box XL — 150 BYN",
        "size_chosen": "Size: {size} — {price} BYN\n\nWould you like to add preferences or exclude anything?",
        "prefs_add": "✅ Add preferences",
        "prefs_exclude": "🚫 Exclude from gift",
        "prefs_skip": "⏭ Skip",
        "write_prefs": "Write what to add to the gift.\n\n⚠️ Please note: the budget for additional preferences should not exceed 50% of the box price. 18+ items are issued only upon passport presentation:",
        "write_exclude": "Write what to exclude:",
        "prefs_saved": "Preferences saved.",
        "exclude_saved": "Exclusions saved.",
        "write_address": "🏠 Please write your delivery address (city, street, building, apartment):",
        "address_saved": "Address saved.",
        "have_promo": "Do you have a promo code?",
        "promo_enter": "🎟 Enter promo code",
        "promo_skip": "⏭ Skip promo",
        "write_promo": "Enter promo code:",
        "promo_not_found": "❌ Promo code not found.\n\nTry another one.",
        "promo_applied": "✅ Promo applied: {discount}% discount.",
        "order_success": "✅ Order #{id} placed!\n\n💰 Total: {price} BYN (discount {discount}%)\n\nWe will contact you.",
        "order_error": "❌ Error placing order.",
        "status_update": "📬 Your order #{id} status has been updated: {status}",
        "lang_select": "🇷🇺 Выберите язык / 🇬🇧 Choose language:",
        "start_btn": "🏠 Main Menu",
    }
}

STATUS_TRANSLATIONS = {
    "new": {"ru": "Новый", "en": "New"},
    "confirmed": {"ru": "Подтверждён", "en": "Confirmed"},
    "shipped": {"ru": "В пути", "en": "Shipped"},
    "completed": {"ru": "Выполнен", "en": "Completed"},
    "cancelled": {"ru": "Отменён", "en": "Cancelled"}
}

# ========== БАЗА ДАННЫХ (POSTGRESQL) ==========

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=15)

def init_db():
    if not DATABASE_URL: return
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS promos (
                code VARCHAR(50) PRIMARY KEY, discount INT NOT NULL, 
                expires_at TIMESTAMP NOT NULL, active BOOLEAN DEFAULT TRUE
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, username VARCHAR(255),
                category_name VARCHAR(100), subcategory_name VARCHAR(100), size VARCHAR(10),
                price INT, discount INT DEFAULT 0, final_price INT, preferences TEXT,
                exclude TEXT, address TEXT, promo VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'new'
            );
        """)
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS address TEXT;")
        
        # Создаем таблицу пользователей и принудительно добавляем колонку lang
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, lang VARCHAR(2) DEFAULT 'ru'
            );
        """)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lang VARCHAR(2) DEFAULT 'ru';")
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

def get_user_lang(uid):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT lang FROM users WHERE user_id = %s", (uid,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            return row[0]
        return "ru"
    except Exception as e:
        logger.error(f"Ошибка получения языка: {e}")
        return "ru"

def set_user_lang(uid, lang):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (user_id, lang) VALUES (%s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET lang = EXCLUDED.lang", 
            (uid, lang)
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Пользователь {uid} сменил язык на {lang}")
    except Exception as e:
        logger.error(f"Ошибка смены языка: {e}")

def get_users():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        users = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return users
    except Exception:
        return []

def save_promo(code, discount, expires_at):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO promos (code, discount, expires_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (code) DO UPDATE SET discount=EXCLUDED.discount, expires_at=EXCLUDED.expires_at, active=TRUE",
            (code.upper(), discount, expires_at)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception:
        return False

def get_promo(code):
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM promos WHERE code = %s AND active = TRUE", (code.upper(),))
        promo = cur.fetchone()
        cur.close()
        conn.close()
        return promo
    except Exception:
        return None

def save_order(order_data):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (user_id, username, category_name, subcategory_name, size, price, discount, final_price, preferences, exclude, address, promo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (
            order_data["user_id"], order_data["username"], order_data["category_name"],
            order_data["subcategory_name"], order_data["size"], order_data["price"],
            order_data["discount"], order_data["final_price"], order_data["preferences"],
            order_data["exclude"], order_data["address"], order_data["promo"]
        ))
        order_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return str(order_id)
    except Exception as e:
        logger.error(f"Ошибка сохранения заказа: {e}")
        return None

def get_order(order_id):
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM orders WHERE id = %s", (int(order_id),))
        order = cur.fetchone()
        cur.close()
        conn.close()
        return order
    except Exception:
        return None

def get_active_orders():
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, username, final_price, status FROM orders WHERE status NOT IN ('completed', 'cancelled') ORDER BY id DESC LIMIT 20")
        orders = cur.fetchall()
        cur.close()
        conn.close()
        return orders
    except Exception:
        return []

def update_order_status(order_id, new_status):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, int(order_id)))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception:
        return False

# ========== КЛАВИАТУРЫ ==========

def get_t(uid):
    lang = get_user_lang(uid)
    return TEXTS.get(lang, TEXTS["ru"]), lang

def home_btn(text):
    return [InlineKeyboardButton(text["home"], callback_data="back_main")]

def main_menu(text):
    keyboard = [
        [InlineKeyboardButton(text["cat_girl"], callback_data="cat_girl")],
        [InlineKeyboardButton(text["cat_boy"], callback_data="cat_boy")],
        [InlineKeyboardButton("🇷🇺 RU / 🇬🇧 EN", callback_data="change_lang")]
    ]
    return InlineKeyboardMarkup(keyboard)

def subcat_menu(text, category):
    if category == "girl":
        subs = [(text["girl_mom"], "sub_girl_mom"), (text["girl_friend"], "sub_girl_friend"), (text["girl_love"], "sub_girl_love"), (text["girl_sister"], "sub_girl_sister")]
    else:
        subs = [(text["boy_dad"], "sub_boy_dad"), (text["boy_friend"], "sub_boy_friend"), (text["boy_love"], "sub_boy_love"), (text["boy_brother"], "sub_boy_brother")]
    keyboard = [[InlineKeyboardButton(name, callback_data=cb)] for name, cb in subs]
    keyboard.append(home_btn(text))
    return InlineKeyboardMarkup(keyboard)

def size_menu(text, category, subcategory):
    keyboard = [
        [InlineKeyboardButton(text["size_S"], callback_data=f"size_S_{category}_{subcategory}")],
        [InlineKeyboardButton(text["size_L"], callback_data=f"size_L_{category}_{subcategory}")],
        [InlineKeyboardButton(text["size_XL"], callback_data=f"size_XL_{category}_{subcategory}")],
        home_btn(text)
    ]
    return InlineKeyboardMarkup(keyboard)

def prefs_menu(text):
    keyboard = [
        [InlineKeyboardButton(text["prefs_add"], callback_data="prefs_add")],
        [InlineKeyboardButton(text["prefs_exclude"], callback_data="prefs_exclude")],
        [InlineKeyboardButton(text["prefs_skip"], callback_data="prefs_skip")],
        home_btn(text)
    ]
    return InlineKeyboardMarkup(keyboard)

def promo_menu(text):
    keyboard = [
        [InlineKeyboardButton(text["promo_enter"], callback_data="promo_enter")],
        [InlineKeyboardButton(text["promo_skip"], callback_data="promo_skip")],
        home_btn(text)
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Добавить промокод", callback_data="admin_promo")],
        [InlineKeyboardButton("📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📋 Заказы", callback_data="admin_orders")],
    ]
    return InlineKeyboardMarkup(keyboard)

def active_orders_menu(orders):
    keyboard = []
    for o in orders:
        uname = o['username'] or "—"
        status_ru = STATUS_TRANSLATIONS.get(o['status'], {}).get("ru", o['status'])
        btn_text = f"#{o['id']} | {uname} | {o['final_price']} BYN | {status_ru}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"adm_order_{o['id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад в админку", callback_data="admin_back")])
    return InlineKeyboardMarkup(keyboard)

def order_status_menu(order_id):
    keyboard = [
        [InlineKeyboardButton("✅ Подтверждён", callback_data=f"status_{order_id}_confirmed")],
        [InlineKeyboardButton("🚚 Отправлен", callback_data=f"status_{order_id}_shipped")],
        [InlineKeyboardButton("✔️ Выполнен", callback_data=f"status_{order_id}_completed")],
        [InlineKeyboardButton("❌ Отменён", callback_data=f"status_{order_id}_cancelled")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data="admin_orders")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== ХЕЛПЕРЫ ==========

def get_category_name(key, lang="ru"):
    mapping = {
        "girl": "cat_girl", "boy": "cat_boy",
        "mom": "girl_mom", "friend": "girl_friend", "love": "girl_love", "sister": "girl_sister",
        "dad": "boy_dad", "brother": "boy_brother"
    }
    if lang == "en" and key == "friend": return "For Friend"
    if lang == "en" and key == "love": return "For Beloved"
    
    text_key = mapping.get(key)
    if not text_key: return key
    return TEXTS.get(lang, TEXTS["ru"]).get(text_key, key)

def format_order_admin(order):
    status_ru = STATUS_TRANSLATIONS.get(order.get('status', 'new'), {}).get("ru", order.get('status'))
    date_str = order.get("created_at").strftime('%Y-%m-%d %H:%M') if order.get("created_at") else datetime.now().strftime('%Y-%m-%d %H:%M')
    
    cat_ru = get_category_name(order['category_name'], "ru")
    sub_ru = get_category_name(order['subcategory_name'], "ru")

    return (
        f"🆔 Заказ #{order['id']}\n"
        f"📂 {cat_ru} → {sub_ru}\n"
        f"📦 {order['size']} — {order['price']} BYN\n"
        f"🏷 Промокод: {order.get('promo', '—')} (скидка {order.get('discount', 0)}%)\n"
        f"💰 Итого: {order['final_price']} BYN\n"
        f"🏠 Адрес: {order.get('address', '—')}\n"
        f"✅ Предпочтения: {order.get('preferences', '—')}\n"
        f"🚫 Исключить: {order.get('exclude', '—')}\n"
        f"👤 Покупатель: @{order.get('username', '—')} (ID: {order['user_id']})\n"
        f"📅 {date_str}\n"
        f"📌 Статус: {status_ru}"
    )

def check_promo(promo_code):
    code = promo_code.strip().upper()
    promo = get_promo(code)
    if not promo: return None, "not_found"
    if promo["expires_at"] and datetime.now() > promo["expires_at"]: return None, "expired"
    return promo["discount"], None

# ========== ХЕНДЛЕРЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT lang FROM users WHERE user_id = %s", (uid,))
        exists = cur.fetchone()
        cur.close()
        conn.close()
    except:
        exists = True

    if not exists:
        keyboard = [[InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")], [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]]
        await update.message.reply_text("🇷🇺 Выберите язык / 🇬🇧 Choose language:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    text, _ = get_t(uid)
    await update.message.reply_text(text["welcome"], reply_markup=main_menu(text))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_cb = query.data
    uid = query.from_user.id
    text, lang = get_t(uid)

    if data_cb == "change_lang":
        keyboard = [[InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")], [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]]
        await query.edit_message_text(text["lang_select"], reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data_cb.startswith("lang_"):
        new_lang = data_cb.split("_")[1]
        set_user_lang(uid, new_lang)
        text, _ = get_t(uid)
        await query.edit_message_text(text["welcome"], reply_markup=main_menu(text))
        return

    if data_cb == "back_main":
        await query.edit_message_text(text["choose_cat"], reply_markup=main_menu(text))
        return

    if data_cb.startswith("cat_"):
        cat = data_cb.split("_", 1)[1]
        cat_name = text["cat_girl"] if cat == "girl" else text["cat_boy"]
        context.user_data["category"] = cat
        await query.edit_message_text(text["choose_subcat"].format(cat=cat_name), reply_markup=subcat_menu(text, cat))
        return

    if data_cb.startswith("sub_"):
        parts = data_cb.split("_", 2)
        cat = parts[1]
        sub_key = parts[2]
        
        sub_name = get_category_name(sub_key, lang)
        context.user_data["subcategory"] = sub_key
        await query.edit_message_text(text["choose_size"].format(cat=text["cat_girl"] if cat=="girl" else text["cat_boy"], sub=sub_name), reply_markup=size_menu(text, cat, sub_key))
        return

    if data_cb.startswith("size_"):
        parts = data_cb.split("_")
        size = parts[1]
        prices = {"S": 30, "L": 75, "XL": 150}
        context.user_data["size"] = size
        context.user_data["price"] = prices[size]
        context.user_data["discount"] = 0
        context.user_data["applied_promo"] = None
        await query.edit_message_text(text["size_chosen"].format(size=size, price=prices[size]), reply_markup=prefs_menu(text))
        return

    if data_cb == "prefs_add":
        context.user_data["awaiting"] = "prefs_add"
        await query.edit_message_text(text["write_prefs"])
        return

    if data_cb == "prefs_exclude":
        context.user_data["awaiting"] = "prefs_exclude"
        await query.edit_message_text(text["write_exclude"])
        return

    if data_cb == "prefs_skip":
        context.user_data["awaiting"] = "address" 
        await query.edit_message_text(text["write_address"])
        return

    if data_cb == "promo_enter":
        context.user_data["awaiting"] = "promo_enter"
        await query.edit_message_text(text["write_promo"])
        return

    if data_cb == "promo_skip":
        context.user_data["discount"] = 0
        context.user_data["applied_promo"] = None
        await finalize_order(query, context)
        return

    if data_cb == "admin_back":
        await query.edit_message_text("👑 Админ-меню:", reply_markup=admin_menu())
        return

    if data_cb == "admin_promo":
        context.user_data["awaiting"] = "admin_promo"
        await query.edit_message_text("Введите промокод в формате:\n`КОД ПРОЦЕНТ ЧАСОВ`\n\nПример: `SALE10 10 48`", parse_mode="Markdown")
        return

    if data_cb == "admin_broadcast":
        context.user_data["awaiting"] = "admin_broadcast"
        await query.edit_message_text("Введите текст рассылки:")
        return

    if data_cb == "admin_orders":
        orders = get_active_orders()
        if not orders:
            await query.edit_message_text("Активных заказов нет.", reply_markup=admin_menu())
            return
        await query.edit_message_text("📋 Выберите заказ для смены статуса:\n(Выполненные и отменённые скрыты)", reply_markup=active_orders_menu(orders))
        return

    if data_cb.startswith("adm_order_"):
        order_id = data_cb.split("_")[2]
        order = get_order(order_id)
        if order:
            await query.edit_message_text(f"Заказ #{order_id}\n\n{format_order_admin(order)}", reply_markup=order_status_menu(order_id))
        else:
            await query.edit_message_text(f"❌ Заказ {order_id} не найден.")
        return

    if data_cb.startswith("status_"):
        parts = data_cb.split("_", 2)
        order_id = str(parts[1])
        new_status = parts[2]
        
        order = get_order(order_id)
        if order:
            if update_order_status(order_id, new_status):
                status_ru = STATUS_TRANSLATIONS.get(new_status, {}).get("ru", new_status)
                if new_status in ["completed", "cancelled"]:
                    await query.edit_message_text(f"✅ Заказ #{order_id} закрыт со статусом: {status_ru}", reply_markup=admin_menu())
                else:
                    orders = get_active_orders()
                    if orders:
                        await query.edit_message_text("📋 Выберите заказ для смены статуса:", reply_markup=active_orders_menu(orders))
                    else:
                        await query.edit_message_text("Активных заказов нет.", reply_markup=admin_menu())

                user_lang = get_user_lang(order["user_id"])
                status_client = STATUS_TRANSLATIONS.get(new_status, {}).get(user_lang, new_status)
                try:
                    await context.bot.send_message(
                        chat_id=order["user_id"], 
                        text=TEXTS[user_lang]["status_update"].format(id=order_id, status=status_client)
                    )
                except Exception:
                    pass
            else:
                await query.edit_message_text("Ошибка при обновлении статуса.")
        else:
            await query.edit_message_text(f"❌ Заказ {order_id} не найден.")
        return

async def finalize_order(query, context):
    uid = query.from_user.id
    text, _ = get_t(uid)

    order_data = {
        "user_id": uid,
        "username": query.from_user.username or "—",
        "category_name": context.user_data.get("category", "—"),
        "subcategory_name": context.user_data.get("subcategory", "—"),
        "size": context.user_data.get("size", "—"),
        "price": context.user_data.get("price", 0),
        "discount": context.user_data.get("discount", 0),
        "final_price": int(context.user_data.get("price", 0) * (100 - context.user_data.get("discount", 0)) / 100),
        "preferences": context.user_data.get("prefs_add", "—"),
        "exclude": context.user_data.get("prefs_exclude", "—"),
        "address": context.user_data.get("address", "—"),
        "promo": context.user_data.get("applied_promo") or "—",
    }
    
    order_id = save_order(order_data)
    
    if order_id:
        await query.edit_message_text(
            text["order_success"].format(id=order_id, price=order_data['final_price'], discount=order_data['discount']),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text["start_btn"], callback_data="back_main")]])
        )
        order_data["id"] = order_id 
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🆕 Новый заказ!\n\n{format_order_admin(order_data)}",
                reply_markup=order_status_menu(order_id),
            )
        except Exception as e:
            logger.error(f"ОШИБКА отправки админу: {e}")
    else:
        await query.edit_message_text(text["order_error"])

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    awaiting = context.user_data.get("awaiting")
    t, _ = get_t(uid)

    if awaiting == "prefs_add":
        context.user_data["prefs_add"] = text
        context.user_data["awaiting"] = "address" 
        await update.message.reply_text(t["prefs_saved"])
        await update.message.reply_text(t["write_address"])
        return

    if awaiting == "prefs_exclude":
        context.user_data["prefs_exclude"] = text
        context.user_data["awaiting"] = "address" 
        await update.message.reply_text(t["exclude_saved"])
        await update.message.reply_text(t["write_address"])
        return

    if awaiting == "address":
        context.user_data["address"] = text
        context.user_data["awaiting"] = None
        await update.message.reply_text(t["address_saved"])
        await update.message.reply_text(t["have_promo"], reply_markup=promo_menu(t))
        return

    if awaiting == "promo_enter":
        discount, error = check_promo(text)
        context.user_data["awaiting"] = None
        if error:
            await update.message.reply_text(t["promo_not_found"])
            await update.message.reply_text(t["have_promo"], reply_markup=promo_menu(t))
            return
        context.user_data["discount"] = discount
        context.user_data["applied_promo"] = text.upper()
        await update.message.reply_text(t["promo_applied"].format(discount=discount))

        class FakeQuery:
            from_user = update.effective_user
            async def edit_message_text(self, *a, **kw):
                await update.message.reply_text(*a, **kw)
        await finalize_order(FakeQuery(), context)
        return

    if uid != ADMIN_ID:
        await update.message.reply_text("Пожалуйста, используйте кнопки в меню. Нажмите /start")
        return

    if awaiting == "admin_promo":
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("Формат: `КОД ПРОЦЕНТ ЧАСОВ`")
            return
        code = parts[0].strip().upper()
        discount = int(parts[1])
        hours = int(parts[2])
        expires_at = datetime.now() + timedelta(hours=hours)
        if save_promo(code, discount, expires_at):
            context.user_data["awaiting"] = None
            await update.message.reply_text(f"✅ Промокод {code} сохранен (скидка {discount}%).")
        else:
            await update.message.reply_text("Ошибка сохранения.")
        return

    if awaiting == "admin_broadcast":
        users = get_users()
        sent = 0
        for u in users:
            try:
                await context.bot.send_message(chat_id=u, text=f"📢 {text}")
                sent += 1
            except Exception: pass
        context.user_data["awaiting"] = None
        await update.message.reply_text(f"Рассылка отправлена {sent} пользователям.")
        return

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("👑 Админ-меню:", reply_markup=admin_menu())

# ========== ЗАПУСК ==========

async def on_startup(app: Application):
    init_db()
    await app.bot.delete_webhook(drop_pending_updates=False)

def main():
    if not all([TOKEN, ADMIN_ID, DATABASE_URL, WEBHOOK_URL]): return
    try: asyncio.get_event_loop()
    except RuntimeError: asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_webhook(
        listen="0.0.0.0", port=PORT, url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}", drop_pending_updates=False,
    )

if __name__ == "__main__":
    main()