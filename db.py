# === Импорт библиотек ===
import aiosqlite # Для асинхронной работы с базой данных SQLite
import datetime # Для работы с датами и временем
import uuid # Для генерации уникальных кодов заявок

# === Настройка базы данных ===
DB_NAME = "tickets.db" # Имя файла базы данных SQLite

# ID супер-администратора (замените на свой Telegram ID)
# Этот пользователь будет иметь полный доступ ко всем функциям бота.
SUPERADMIN_ID = 7963375756 # <--- ЗАМЕНИТЕ ЭТО НА ВАШ РЕАЛЬНЫЙ TELEGRAM ID

# === Функции для работы с базой данных ===
async def generate_tickets_excel(*args, **kwargs):
    pass

async def init_db():
    """Инициализирует базу данных: создает таблицы, если они не существуют."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица для хранения заявок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                code TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                username TEXT,
                user_id INTEGER NOT NULL,
                priority TEXT DEFAULT 'Низкий',
                category TEXT DEFAULT 'Общий вопрос',
                assigned_to_id INTEGER,
                rating INTEGER,
                feedback_text TEXT,
                last_admin_reply_at TEXT
            )
        """)
        # Таблица для хранения сообщений в рамках заявок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_code TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL, -- 'user', 'admin', 'moderator'
                message_text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (ticket_code) REFERENCES tickets (code)
            )
        """)
        # Таблица для хранения ролей пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL, -- 'user', 'moderator', 'admin', 'superadmin'
                username TEXT -- Добавлено поле username
            )
        """)
        # Таблица для хранения вложений к заявкам
        await db.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_code TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_name TEXT,
                file_type TEXT, -- 'photo', 'document'
                FOREIGN KEY (ticket_code) REFERENCES tickets (code)
            )
        """)
        # Таблица для хранения шаблонов ответов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS response_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                text TEXT NOT NULL
            )
        """)
        await db.commit()

        # Убедимся, что супер-админ всегда имеет роль 'superadmin'
        # и его username актуален, если бот запущен.
        # Это должно быть сделано после создания таблицы.
        # При первом запуске, если SUPERADMIN_ID еще не в user_roles, он будет добавлен.
        # Если он уже есть, его роль будет обновлена до 'superadmin'.
        # Username будет обновлен при первом запуске бота через cmd_start
        await set_user_role(SUPERADMIN_ID, 'superadmin') 

async def is_admin_or_moderator(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором или модератором."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT role FROM user_roles WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row and row[0] in ('admin', 'moderator', 'superadmin'): # superadmin тоже имеет доступ к админским функциям
            return True
        return False

async def is_superadmin(user_id: int) -> bool:
    """Проверяет, является ли пользователь супер-админом."""
    return user_id == SUPERADMIN_ID

async def create_ticket(user_id: int, text: str, priority: str, category: str) -> tuple:
    """Создает новую заявку в базе данных."""
    code = f"R-{str(uuid.uuid4())[:8].upper()}" # Генерируем уникальный код заявки
    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "open" # Новая заявка всегда открыта
    
    async with aiosqlite.connect(DB_NAME) as db:
        # Получаем username пользователя, если он есть в user_roles
        cursor = await db.execute("SELECT username FROM user_roles WHERE user_id = ?", (user_id,))
        user_data = await cursor.fetchone()
        username = user_data[0] if user_data else None # Если пользователя нет в user_roles, username будет None

        await db.execute(
            "INSERT INTO tickets (code, text, created_at, status, username, user_id, priority, category) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (code, text, created_at, status, username, user_id, priority, category)
        )
        await db.commit()
        # Добавляем первое сообщение в историю переписки
        await add_message(code, user_id, 'user', text)
        return code, created_at, status

async def get_ticket_by_code(code: str) -> tuple | None:
    """Возвращает информацию о заявке по ее коду."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT code, text, created_at, status, username, user_id, priority, category, assigned_to_id, rating, feedback_text, last_admin_reply_at FROM tickets WHERE code = ?",
            (code,)
        )
        return await cursor.fetchone()

async def close_ticket(code: str):
    """Закрывает заявку по ее коду."""
    closed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        # Добавлено условие, чтобы закрывать только открытые заявки
        await db.execute(
            "UPDATE tickets SET status = ?, closed_at = ? WHERE code = ? AND status = 'open'", 
            ("closed", closed_at, code)
        )
        await db.commit()

async def get_tickets_by_user_id(user_id: int) -> list[tuple]:
    """Возвращает все заявки, созданные определенным пользователем."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT code, text, created_at, status, username, user_id, priority, category, assigned_to_id, rating, feedback_text, last_admin_reply_at FROM tickets WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        return await cursor.fetchall()

async def get_tickets_by_date_range(start_date: str = None, end_date: str = None, status: str = None, 
                                     priority: str = None, category: str = None, assigned_to_id: int = None) -> list[tuple]:
    """
    Возвращает заявки по диапазону дат создания, статусу, приоритету, категории или назначенному ID.
    Даты должны быть в формате 'YYYY-MM-DD'.
    """
    query = "SELECT code, text, created_at, status, username, user_id, priority, category, assigned_to_id, rating, feedback_text, last_admin_reply_at FROM tickets WHERE 1=1"
    params = []

    if start_date:
        query += " AND created_at >= ?"
        params.append(start_date + " 00:00:00")
    if end_date:
        query += " AND created_at <= ?"
        params.append(end_date + " 23:59:59")
    if status:
        query += " AND status = ?"
        params.append(status)
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    if category:
        query += " AND category = ?"
        params.append(category)
    if assigned_to_id is not None:
        if assigned_to_id == 0: # Для неназначенных (assigned_to_id IS NULL)
            query += " AND assigned_to_id IS NULL"
        else: # Для назначенных конкретному ID
            query += " AND assigned_to_id = ?"
            params.append(assigned_to_id)
            
    query += " ORDER BY created_at DESC"

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(query, tuple(params))
        return await cursor.fetchall()

async def get_user_role(user_id: int) -> str | None:
    """Возвращает роль пользователя."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT role FROM user_roles WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else None

async def set_user_role(user_id: int, role: str, username: str = None):
    """Устанавливает или обновляет роль пользователя."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Проверяем, существует ли пользователь
        cursor = await db.execute("SELECT user_id FROM user_roles WHERE user_id = ?", (user_id,))
        existing_user = await cursor.fetchone()

        if existing_user:
            # Обновляем роль и username. COALESCE сохранит существующий username, если новый не предоставлен.
            await db.execute(
                "UPDATE user_roles SET role = ?, username = COALESCE(?, username) WHERE user_id = ?",
                (role, username, user_id)
            )
        else:
            # Вставляем нового пользователя с ролью и username
            await db.execute(
                "INSERT INTO user_roles (user_id, role, username) VALUES (?, ?, ?)",
                (user_id, role, username)
            )
        await db.commit()

async def get_all_users_with_roles() -> list[tuple]:
    """Возвращает список всех пользователей с их ролями."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, username, role FROM user_roles")
        return await cursor.fetchall()

async def add_message(ticket_code: str, user_id: int, role: str, message_text: str):
    """Добавляет сообщение в историю переписки заявки."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO messages (ticket_code, user_id, role, message_text, timestamp) VALUES (?, ?, ?, ?, ?)",
            (ticket_code, user_id, role, message_text, timestamp)
        )
        # Если сообщение от админа/модератора, обновляем last_admin_reply_at в таблице tickets
        if role in ('admin', 'moderator', 'superadmin'):
            await db.execute(
                "UPDATE tickets SET last_admin_reply_at = ? WHERE code = ?",
                (timestamp, ticket_code)
            )
        await db.commit()

async def get_messages_by_ticket(ticket_code: str) -> list[tuple]:
    """Возвращает все сообщения для определенной заявки."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT role, message_text, timestamp FROM messages WHERE ticket_code = ? ORDER BY timestamp ASC",
            (ticket_code,)
        )
        return await cursor.fetchall()

async def get_recent_users_with_tickets(limit: int = 10) -> list[tuple]:
    """Возвращает список последних пользователей, создававших заявки."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT DISTINCT T1.user_id, T2.username FROM tickets AS T1 LEFT JOIN user_roles AS T2 ON T1.user_id = T2.user_id ORDER BY T1.created_at DESC LIMIT ?",
            (limit,)
        )
        return await cursor.fetchall()

async def get_user_by_username(username: str) -> tuple | None:
    """Возвращает информацию о пользователе по его username."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, username, role FROM user_roles WHERE username = ?", (username,))
        return await cursor.fetchone()

async def update_user_username(user_id: int, username: str):
    """
    Обновляет username пользователя в базе данных, не затрагивая его роль.
    Если пользователь не существует в user_roles, добавляет его с ролью 'user'.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        # Проверяем, существует ли пользователь в таблице user_roles
        cursor = await db.execute("SELECT user_id FROM user_roles WHERE user_id = ?", (user_id,))
        user_exists = await cursor.fetchone()

        if user_exists:
            # Если пользователь существует, просто обновляем его username
            await db.execute(
                "UPDATE user_roles SET username = ? WHERE user_id = ?",
                (username, user_id)
            )
        else:
            # Если пользователь не существует, добавляем его с ролью 'user' и username
            await db.execute(
                "INSERT INTO user_roles (user_id, role, username) VALUES (?, 'user', ?)",
                (user_id, username)
            )
        
        # Также обновляем username в таблице tickets, чтобы он был актуальным
        await db.execute(
            "UPDATE tickets SET username = ? WHERE user_id = ?",
            (username, user_id)
        )
        await db.commit()


async def add_attachment(ticket_code: str, file_id: str, file_name: str, file_type: str):
    """Добавляет вложение к заявке."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO attachments (ticket_code, file_id, file_name, file_type) VALUES (?, ?, ?, ?)",
            (ticket_code, file_id, file_name, file_type)
        )
        await db.commit()

async def get_attachments_by_ticket(ticket_code: str) -> list[tuple]:
    """Возвращает все вложения для определенной заявки."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT file_id, file_name, file_type FROM attachments WHERE ticket_code = ?",
            (ticket_code,)
        )
        return await cursor.fetchall()

async def add_response_template(name: str, text: str) -> bool:
    """Добавляет новый шаблон ответа. Возвращает True при успехе, False если шаблон с таким именем уже существует."""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO response_templates (name, text) VALUES (?, ?)",
                (name, text)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError: # Обработка UNIQUE ограничения
            return False

async def get_response_templates() -> list[tuple]:
    """Возвращает все сохраненные шаблоны ответов."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, name, text FROM response_templates ORDER BY name ASC")
        return await cursor.fetchall()

async def delete_response_template(template_id: int):
    """Удаляет шаблон ответа по его ID."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM response_templates WHERE id = ?", (template_id,))
        await db.commit()

async def assign_ticket(ticket_code: str, assigned_to_id: int):
    """Назначает заявку конкретному администратору/модератору."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE tickets SET assigned_to_id = ? WHERE code = ?",
            (assigned_to_id, ticket_code)
        )
        await db.commit()

async def unassign_ticket(ticket_code: str):
    """Снимает назначение с заявки."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE tickets SET assigned_to_id = NULL WHERE code = ?",
            (ticket_code,)
        )
        await db.commit()

async def get_all_admins_and_moderators() -> list[tuple]:
    """Возвращает список всех администраторов и модераторов."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT user_id, username, role FROM user_roles WHERE role IN ('admin', 'moderator', 'superadmin')"
        )
        return await cursor.fetchall()

async def add_ticket_feedback(ticket_code: str, rating: int, feedback_text: str = None):
    """Добавляет оценку и текстовый отзыв к закрытой заявке."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE tickets SET rating = ?, feedback_text = ? WHERE code = ?",
            (rating, feedback_text, ticket_code)
        )
        await db.commit()

async def get_stale_tickets(hours: int = 24) -> list[tuple]:
    """
    Возвращает список "зависших" заявок (открытых, без назначенного или без ответа админа
    более указанного количества часов).
    """
    threshold_time = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT 
                T.code, T.text, T.created_at, T.status, T.username, T.user_id, 
                T.priority, T.category, T.assigned_to_id, T.last_admin_reply_at
            FROM tickets AS T
            WHERE 
                T.status = 'open' AND (
                    T.assigned_to_id IS NULL OR 
                    T.last_admin_reply_at IS NULL OR 
                    T.last_admin_reply_at < ?
                )
            ORDER BY T.created_at ASC
        """, (threshold_time,))
        return await cursor.fetchall()

async def get_all_registered_users() -> list[tuple]:
    """Возвращает список всех зарегистрированных пользователей (ID и username)."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, username FROM user_roles ORDER BY username ASC")
        return await cursor.fetchall()

async def update_ticket_details(ticket_code: str, new_text: str = None, new_priority: str = None, new_category: str = None) -> bool:
    """
    Обновляет детали заявки (текст, приоритет, категорию) по ее коду.
    Возвращает True при успехе, False в противном случае.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.cursor()
        updates = []
        params = []
        if new_text is not None:
            updates.append("text = ?")
            params.append(new_text)
        if new_priority is not None:
            updates.append("priority = ?")
            params.append(new_priority)
        if new_category is not None:
            updates.append("category = ?")
            params.append(new_category)
        
        if updates:
            query = f"UPDATE tickets SET {', '.join(updates)} WHERE code = ?"
            params.append(ticket_code)
            await cursor.execute(query, tuple(params))
            await db.commit()
            return True
        return False

