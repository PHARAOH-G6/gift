import json
import os
import logging
import requests
import asyncio
from datetime import datetime, timedelta

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

# Upstash Redis (REST)
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

# Локальный кэш на случай сбоев Redis
LOCAL_PROMOS = {}

# ========== UPSTASH REDIS (REST API) ==========

def redis_set(key, value):
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        return False
    try:
        payload = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        r = requests.post(
            f"{UPSTASH_URL}/set/{key}",
            headers={
                "Authorization": f"Bearer {UPSTASH_TOKEN}",
                "Content-Type": "application/json",
            },
            data=payload,
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.error(f"redis_set error: {e}")
        return False


def redis_get(key):
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        return None
    try:
        r = requests.get(
            f"{UPSTASH_URL}/get/{key}",
            headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
            timeout=10,
        )
        data = r.json()
        result = data.get("result")
        if result is None:
            return None
        return json.loads(result) if result.startswith("{") else result
    except Exception as e:
        logger.error(f"redis_get error: {e}")
        return None


# ========== ЛОГИКА ДАННЫХ ==========

def save_promo(code, data):
    LOCAL_PROMOS[code] = data  # Сохраняем локально
    redis_set(f"promo:{code}", data)  # И в Redis


def get_promo(code):
    # Сначала ищем локально, потом в Redis
    if code in LOCAL_PROMOS:
        return LOCAL_PROMOS[code]
    return redis_get(f"promo:{code}")


def get_next_order_id():
    val = redis_get("order_counter")
    if not val:
        redis_set("order_counter", 1)
        return "1"
    new_val = int(val) + 1
    redis_set("order_counter", new_val)
    return str(new_val)


def save_order(order_id, order_data):
    redis_set(f"order:{order_id}", order_data)


def get_order(order_id):
    return redis_get(f"order:{order_id}")


def add_user(uid):
    users = redis_get("users") or []
    if not isinstance(users, list):
        users = []
    if uid not in users:
        users.append(uid)
        redis_set("users", users)


# ========== КЛАВИАТУРЫ ==========

def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎁 Для девушки", callback_data="cat_girl")],
        [InlineKeyboardButton("🎁 Для парня", callback_data="cat_boy")],
    ]
    return InlineKeyboardMarkup(keyboard)


def subcat_menu(category):
    if category == "girl":
        subs = [
            ("Для мамы", "sub_girl_mom"),
            ("Для подруги", "sub_girl_friend"),
            ("Для любимой", "sub_girl_love"),
            ("Для сестры", "sub_girl_sister"),
        ]
    else:
        subs = [
            ("Для папы", "sub_boy_dad"),
            ("Для друга", "sub_boy_friend"),
            ("Для любимого", "sub_boy_love"),
            ("Для брата", "sub_boy_brother"),
        ]
    keyboard = [[InlineKeyboardButton(name, callback_data=cb)] for name, cb in subs]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(keyboard)


def size_menu(category, subcategory):
    keyboard = [
        [InlineKeyboardButton("📦 Бокс S — 30 BYN", callback_data=f"size_S_{category}_{subcategory}")],
        [InlineKeyboardButton("📦 Бокс L — 75 BYN", callback_data=f"size_L_{category}_{subcategory}")],
        [InlineKeyboardButton("📦 Бокс XL — 150 BYN", callback_data=f"size_XL_{category}_{subcategory}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"cat_{category}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def prefs_menu():
    keyboard = [
        [InlineKeyboardButton("✅ Добавить предпочтения", callback_data="prefs_add")],
        [InlineKeyboardButton("🚫 Исключить из подарка", callback_data="prefs_exclude")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="prefs_skip")],
    ]
    return InlineKeyboardMarkup(keyboard)


def promo_menu():
    keyboard = [
        [InlineKeyboardButton("🎟 Ввести промокод", callback_data="promo_enter")],
        [InlineKeyboardButton("⏭ Без промокода", callback_data="promo_skip")],
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Добавить промокод", callback_data="admin_promo")],
        [InlineKeyboardButton("📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📋 Заказы", callback_data="admin_orders")],
    ]
    return InlineKeyboardMarkup(keyboard)


def order_status_menu(order_id):
    keyboard = [
        [InlineKeyboardButton("✅ Подтверждён", callback_data=f"status_{order_id}_confirmed")],
        [InlineKeyboardButton("🚚 Отправлен", callback_data=f"status_{order_id}_shipped")],
        [InlineKeyboardButton("✔️ Выполнен", callback_data=f"status_{order_id}_completed")],
        [InlineKeyboardButton("❌ Отменён", callback_data=f"status_{order_id}_cancelled")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ========== ХЕЛПЕРЫ ==========

def format_order(order):
    prefs = order.get("preferences", "—")
    exclude = order.get("exclude", "—")
    promo = order.get("promo", "—")
    discount = order.get("discount", 0)
    lines = [
        f"🆔 Заказ #{order['id']}",
        f"📂 {order['category_name']} → {order['subcategory_name']}",
        f"📦 {order['size']} — {order['price']} BYN",
        f"🏷 Промокод: {promo} (скидка {discount}%)",
        f"💰 Итого: {order['final_price']} BYN",
        f"✅ Предпочтения: {prefs}",
        f"🚫 Исключить: {exclude}",
        f"👤 Покупатель: @{order.get('username', '—')} (ID: {order['user_id']})",
        f"📅 {order['created_at']}",
        f"📌 Статус: {order.get('status', 'новый')}",
    ]
    return "\n".join(lines)


def check_promo(promo_code):
    code = promo_code.strip().upper()
    promo = get_promo(code)
    if not promo:
        logger.warning(f"Промокод {code} не найден.")
        return None, "Промокод не найден."
        
    expires_at = promo.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at)
            if datetime.now() > exp:
                return None, f"Промокод истёк {exp.strftime('%Y-%m-%d %H:%M')}."
        except Exception:
            pass
    return promo["discount"], None


# ========== ХЕНДЛЕРЫ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id)
    text = "🎁 Добро пожаловать в магазин подарочных наборов!\n\nВыберите категорию:"
    await update.message.reply_text(text, reply_markup=main_menu())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_cb = query.data

    if data_cb == "back_main":
        await query.edit_message_text("Выберите категорию:", reply_markup=main_menu())
        return

    if data_cb.startswith("cat_"):
        cat = data_cb.split("_", 1)[1]
        cat_name = "Для девушки" if cat == "girl" else "Для парня"
        context.user_data["category"] = cat
        context.user_data["category_name"] = cat_name
        await query.edit_message_text(f"Категория: {cat_name}\nВыберите подкатегорию:", reply_markup=subcat_menu(cat))
        return

    if data_cb.startswith("sub_"):
        parts = data_cb.split("_", 2)
        cat = parts[1]
        sub_key = parts[2]
        sub_names = {
            "mom": "Для мамы", "friend": "Для подруги", "love": "Для любимой", "sister": "Для сестры",
            "dad": "Для папы", "brother": "Для брата"
        }
        if cat == "boy" and sub_key == "friend": sub_name = "Для друга"
        elif cat == "boy" and sub_key == "love": sub_name = "Для любимого"
        else: sub_name = sub_names.get(sub_key, sub_key)

        context.user_data["subcategory"] = sub_key
        context.user_data["subcategory_name"] = sub_name
        await query.edit_message_text(f"Выбрано: {context.user_data['category_name']} → {sub_name}\n\nВыберите размер бокса:", reply_markup=size_menu(cat, sub_key))
        return

    if data_cb.startswith("size_"):
        parts = data_cb.split("_")
        size = parts[1]
        prices = {"S": 30, "L": 75, "XL": 150}
        context.user_data["size"] = size
        context.user_data["price"] = prices[size]
        context.user_data["discount"] = 0
        context.user_data["applied_promo"] = None
        await query.edit_message_text(f"Размер: {size} — {prices[size]} BYN\n\nХотите добавить предпочтения или исключить что-то из подарка?", reply_markup=prefs_menu())
        return

    if data_cb == "prefs_add":
        context.user_data["awaiting"] = "prefs_add"
        await query.edit_message_text("Напишите, что добавить в подарок:")
        return

    if data_cb == "prefs_exclude":
        context.user_data["awaiting"] = "prefs_exclude"
        await query.edit_message_text("Напишите, что исключить из подарка:")
        return

    if data_cb == "prefs_skip":
        await query.edit_message_text("У вас есть промокод?", reply_markup=promo_menu())
        return

    if data_cb == "promo_enter":
        context.user_data["awaiting"] = "promo_enter"
        await query.edit_message_text("Введите промокод:")
        return

    if data_cb == "promo_skip":
        context.user_data["discount"] = 0
        context.user_data["applied_promo"] = None
        await finalize_order(query, context)
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
        await query.edit_message_text("Введите ID заказа для смены статуса:")
        context.user_data["awaiting"] = "admin_status_id"
        return

    if data_cb.startswith("status_"):
        parts = data_cb.split("_", 2)
        order_id = str(parts[1])
        new_status = parts[2]
        
        order = get_order(order_id)
        if order:
            order["status"] = new_status
            save_order(order_id, order)
            await query.edit_message_text(f"Статус заказа #{order_id} изменён на: {new_status}")
            try:
                await context.bot.send_message(chat_id=order["user_id"], text=f"📬 Статус вашего заказа #{order_id} обновлён: {new_status}")
            except Exception as e:
                logger.warning(f"Не удалось оповестить: {e}")
        else:
            await query.edit_message_text(f"❌ Заказ {order_id} не найден.")
        return


async def finalize_order(query, context):
    order_id = get_next_order_id()
    base_price = context.user_data.get("price", 0)
    discount = context.user_data.get("discount", 0)
    final_price = int(base_price * (100 - discount) / 100)

    order = {
        "id": order_id,
        "user_id": query.from_user.id,
        "username": query.from_user.username or "—",
        "category_name": context.user_data.get("category_name", "—"),
        "subcategory_name": context.user_data.get("subcategory_name", "—"),
        "size": context.user_data.get("size", "—"),
        "price": base_price,
        "discount": discount,
        "final_price": final_price,
        "preferences": context.user_data.get("prefs_add", "—"),
        "exclude": context.user_data.get("prefs_exclude", "—"),
        "promo": context.user_data.get("applied_promo") or "—",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "новый",
    }
    
    save_order(order_id, order)

    await query.edit_message_text(f"✅ Заказ #{order_id} оформлен!\n\n💰 Итого: {final_price} BYN (скидка {discount}%)")

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 Новый заказ!\n\n{format_order(order)}",
            reply_markup=order_status_menu(order_id),
        )
    except Exception as e:
        logger.error(f"Не удалось отправить админу: {e}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    awaiting = context.user_data.get("awaiting")

    if awaiting == "prefs_add":
        context.user_data["prefs_add"] = text
        context.user_data["awaiting"] = None
        await update.message.reply_text("Предпочтения сохранены.")
        await update.message.reply_text("У вас есть промокод?", reply_markup=promo_menu())
        return

    if awaiting == "prefs_exclude":
        context.user_data["prefs_exclude"] = text
        context.user_data["awaiting"] = None
        await update.message.reply_text("Исключения сохранены.")
        await update.message.reply_text("У вас есть промокод?", reply_markup=promo_menu())
        return

    if awaiting == "promo_enter":
        discount, error = check_promo(text)
        context.user_data["awaiting"] = None
        if error:
            await update.message.reply_text(f"❌ {error}\n\nПопробуйте другой.")
            await update.message.reply_text("У вас есть промокод?", reply_markup=promo_menu())
            return
        context.user_data["discount"] = discount
        context.user_data["applied_promo"] = text.upper()
        await update.message.reply_text(f"✅ Промокод применён: скидка {discount}%.")

        class FakeQuery:
            from_user = update.effective_user
            async def edit_message_text(self, *a, **kw):
                await update.message.reply_text(*a, **kw)
        await finalize_order(FakeQuery(), context)
        return

    if uid != ADMIN_ID:
        await update.message.reply_text("Используйте /start для оформления заказа.")
        return

    if awaiting == "admin_promo":
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("Формат: `КОД ПРОЦЕНТ ЧАСОВ`")
            return
        code = parts[0].strip().upper()
        discount = int(parts[1])
        hours = int(parts[2])
        expires_at = (datetime.now() + timedelta(hours=hours)).isoformat()
        
        promo_data = {"discount": discount, "expires_at": expires_at, "active": True}
        save_promo(code, promo_data)
        
        context.user_data["awaiting"] = None
        await update.message.reply_text(f"✅ Промокод {code} сохранен (скидка {discount}%).")
        return

    if awaiting == "admin_broadcast":
        users = redis_get("users") or []
        sent = 0
        for u in users:
            try:
                await context.bot.send_message(chat_id=u, text=f"📢 {text}")
                sent += 1
            except Exception:
                pass
        context.user_data["awaiting"] = None
        await update.message.reply_text(f"Рассылка отправлена {sent} пользователям.")
        return

    if awaiting == "admin_status_id":
        oid = text.strip()
        order = get_order(oid)
        if order:
            await update.message.reply_text(f"Заказ #{oid}. Выберите новый статус:", reply_markup=order_status_menu(oid))
            context.user_data["awaiting"] = None
        else:
            await update.message.reply_text(f"Заказ {oid} не найден.")
        return


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("👑 Админ-меню:", reply_markup=admin_menu())


# ========== ЗАПУСК ==========

def main():
    if not all([TOKEN, ADMIN_ID, UPSTASH_URL, UPSTASH_TOKEN, WEBHOOK_URL]):
        logger.error("Не все переменные окружения заданы.")
        return

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
        drop_pending_updates=False,
    )

if __name__ == "__main__":
    main()