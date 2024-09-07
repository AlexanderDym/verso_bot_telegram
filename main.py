import logging
import config
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import subprocess
import os
import time
import asyncio

# Логирование для отладки
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Путь к сохранению аудиофайлов
BASE_AUDIO_PATH = "audio_files/"

# Функция для реверсирования аудио
async def reverse_audio(input_path, output_path):
    command = [
        "ffmpeg",
        "-i", input_path,
        "-af", "areverse",
        "-b:a", "192k",
        "-acodec", "libmp3lame",
        output_path,
    ]
    logger.info(f"Запуск команды реверсирования: {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        logger.info(f"Файл успешно реверсирован: {output_path}")
    else:
        logger.error(f"Ошибка при реверсировании аудио: {stderr.decode('utf-8')}")

# Функция для конвертации аудио в MP3
async def convert_to_mp3(input_path, output_path):
    command = [
        "ffmpeg",
        "-i", input_path,
        "-b:a", "192k",
        "-acodec", "libmp3lame",
        output_path,
    ]
    logger.info(f"Конвертация файла {input_path} в MP3: {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        logger.info(f"Файл успешно конвертирован в MP3: {output_path}")
    else:
        logger.error(f"Ошибка при конвертации аудио: {stderr.decode('utf-8')}")

# Функция для объединения аудиофайлов
async def combine_audio_files(file_list, output_path):
    # Конвертируем все файлы в MP3
    converted_files = []
    for idx, file_path in enumerate(file_list):
        mp3_file = f"temp_{idx}.mp3"
        await convert_to_mp3(file_path, mp3_file)
        converted_files.append(mp3_file)

    # Создаем временный файл с путями к аудио для ffmpeg
    with open("file_list.txt", "w") as f:
        for file_path in converted_files:
            f.write(f"file '{file_path}'\n")

    command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", "file_list.txt",
        "-c", "copy",
        output_path
    ]

    logger.info(f"Запуск команды для объединения файлов: {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        logger.info(f"Файлы успешно объединены в {output_path}")
    else:
        logger.error(f"Ошибка при объединении аудио: {stderr.decode('utf-8')}")

    # Удаляем временные MP3-файлы
    for file_path in converted_files:
        os.remove(file_path)

# Функция для разделения аудио с учётом пауз
async def split_audio_with_silence_detection(input_path, output_dir):
    if not os.path.exists(input_path):
        logger.error(f"Файл {input_path} не найден.")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_template = os.path.join(output_dir, "chunk_%03d.mp3")
    
    # Используем silencedetect для поиска тишины и разрезки
    command = [
        "ffmpeg",
        "-i", input_path,
        "-af", "silencedetect=noise=-35dB:d=1",  # Настройка для поиска тишины (громкость ниже -35dB и паузы от 1 сек)
        "-f", "segment",  # Разделение файла по найденным паузам
        "-acodec", "libmp3lame",  # Кодек для MP3
        output_template,
    ]

    logger.info(f"Запуск команды для разделения аудио: {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        logger.info(f"Файл успешно разделен и сохранен в {output_dir}")
    else:
        logger.error(f"Ошибка при разделении аудио: {stderr.decode('utf-8')}")
        logger.info(f"Вывод команды: {stdout.decode('utf-8')}")

# Функция старта и выбора режима
async def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    logger.info(f"User {user.first_name} started the bot.")

    keyboard = [[InlineKeyboardButton("Дуэль", callback_data="duel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Готовы к дуэли? Выберите режим:", reply_markup=reply_markup)

# Функция завершения игры и предложения новой
async def send_final_message(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton("Начать новую игру", callback_data="new_game")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Угадали? Готовы начать заново?", reply_markup=reply_markup)

# Функция обработки CallbackQuery для новой игры
async def handle_callback_query(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    user = query.from_user
    callback_data = query.data
    logger.info(f"Получен callback_data: {callback_data} от пользователя {user.first_name}")

    if callback_data == "duel":
        # Очищаем данные предыдущей игры
        context.user_data["user_responses"] = []  # Сбрасываем список записей
        context.user_data["reversed_file_path"] = None  # Очищаем путь к реверсированному файлу
        context.user_data["split_files"] = []  # Очищаем список частей
        context.user_data["awaiting_response"] = False  # Сбрасываем состояние ожидания

        await query.edit_message_text("Вы выбрали дуэль! Запишите фрагмент песни или фразу, которую должен будет угадать ваш соперник.")
        context.user_data["mode"] = "duel"

    elif callback_data == "split":
        logger.info("Кнопка 'Поделить' нажата")
        await process_split_audio(update, context)

    elif callback_data == "new_game":
        # Очищаем данные предыдущей игры перед началом новой
        context.user_data["user_responses"] = []  # Сбрасываем список записей
        context.user_data["reversed_file_path"] = None  # Очищаем путь к реверсированному файлу
        context.user_data["split_files"] = []  # Очищаем список частей
        context.user_data["awaiting_response"] = False  # Сбрасываем состояние ожидания

        # Вместо функции start, отправляем новое приветственное сообщение
        keyboard = [[InlineKeyboardButton("Дуэль", callback_data="duel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Привет! Готовы к дуэли? Выберите режим:", reply_markup=reply_markup)

    else:
        logger.warning(f"Неизвестное callback_data: {callback_data}")

# Функция обработки записи аудио Игроком А
async def handle_audio(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user

    # Проверка, находимся ли мы в процессе ожидания ответа на игру
    if context.user_data.get("awaiting_response"):
        current_part = context.user_data["current_part"]
        total_parts = context.user_data["total_parts"]
        logger.info(f"Получен ответ на часть {current_part + 1} из {total_parts}")

        # Сохраняем ответ пользователя
        user_audio_dir = context.user_data["user_audio_dir"]
        user_response_path = os.path.join(user_audio_dir, f"user_response_{current_part + 1}.ogg")
        file = await update.message.voice.get_file()
        await file.download_to_drive(user_response_path)

        logger.info(f"Запись пользователя сохранена: {user_response_path}")

        # Добавляем путь к файлу в список ответов
        if "user_responses" not in context.user_data:
            context.user_data["user_responses"] = []
        context.user_data["user_responses"].append(user_response_path)

        # Переходим к следующей части
        current_part += 1
        if current_part < total_parts:
            context.user_data["current_part"] = current_part
            await send_next_part(update, context)
        else:
            await update.message.reply_text("Отлично! Все части записаны. Объединяю и реверсирую...")

            # Собираем только те части, которые были записаны после каждой части
            combined_audio_path = os.path.join(user_audio_dir, "combined_audio.mp3")
            await combine_audio_files(context.user_data["user_responses"], combined_audio_path)

            # Переворачиваем объединённое аудио
            reversed_combined_audio_path = os.path.join(user_audio_dir, "reversed_combined_audio.mp3")
            await reverse_audio(combined_audio_path, reversed_combined_audio_path)

            # Отправляем пользователю финальный файл
            with open(reversed_combined_audio_path, "rb") as audio:
                await update.message.reply_voice(voice=audio, caption="Вот ваш финальный перевёрнутый файл!")
            
            context.user_data["awaiting_response"] = False
            
            # Вызов функции отправки сообщения для новой игры
            await send_final_message(update, context)
    else:
        if context.user_data.get("mode") == "duel":
            file = await update.message.voice.get_file()
            timestamp = int(time.time() * 1000)  # Уникальный таймстамп с миллисекундами

            # Создаем уникальную папку для каждого пользователя
            user_audio_dir = os.path.join(BASE_AUDIO_PATH, str(user.id), str(timestamp))
            os.makedirs(user_audio_dir, exist_ok=True)

            original_file_path = os.path.join(user_audio_dir, "original.ogg")
            reversed_file_path = os.path.join(user_audio_dir, "reversed.mp3")

            # Сохраняем оригинальное аудио
            await file.download_to_drive(original_file_path)

            logger.info(f"Аудиофайл загружен и сохранен в {original_file_path}")

            try:
                # Переворачиваем аудио
                await reverse_audio(original_file_path, reversed_file_path)
            except Exception as e:
                logger.error(f"Ошибка при реверсировании аудио: {e}")
                await update.message.reply_text("Произошла ошибка при обработке аудио.")
                return

            if not os.path.exists(reversed_file_path):
                logger.error(f"Файл {reversed_file_path} не существует. Проверьте путь.")
                await update.message.reply_text("Произошла ошибка: файл для разделения не найден.")
                return

            # Сохраняем путь к перевернутому файлу для дальнейшего разделения
            context.user_data["reversed_file_path"] = reversed_file_path
            context.user_data["user_audio_dir"] = user_audio_dir

            # Кнопка для разделения аудио
            keyboard = [[InlineKeyboardButton("Поделить", callback_data="split")]]
            markup = InlineKeyboardMarkup(keyboard)

            with open(reversed_file_path, "rb") as audio:
                await update.message.reply_voice(voice=audio, caption="Перевернутая запись. Поделить на части?", reply_markup=markup)

# Функция для обработки разделения аудио
async def process_split_audio(update: Update, context: CallbackContext) -> None:
    query = update.callback_query

    user_audio_dir = context.user_data.get("user_audio_dir")
    reversed_file_path = context.user_data.get("reversed_file_path")

    if not user_audio_dir or not reversed_file_path:
        logger.error("Нет данных о пути к файлам. Проверьте сохранение данных в user_data.")
        await query.message.reply_text(text="Ошибка: данные о файлах отсутствуют.")
        return

    logger.info(f"Путь к аудиофайлу: {reversed_file_path}")
    logger.info(f"Папка для разделения: {user_audio_dir}")

    split_output_dir = os.path.join(user_audio_dir, "split")

    try:
        if not os.path.exists(reversed_file_path):
            logger.error(f"Файл для разделения не найден: {reversed_file_path}")
            await query.message.reply_text(text="Ошибка: файл для разделения не найден.")
            return

        # Разделяем аудио с учётом пауз
        await split_audio_with_silence_detection(reversed_file_path, split_output_dir)

        # Проверяем, были ли созданы части
        files_in_dir = sorted(os.listdir(split_output_dir))
        if not files_in_dir:
            logger.error("Нет файлов после разделения.")
            await query.message.reply_text(text="Ошибка: не удалось разделить аудио на части.")
            return

        logger.info(f"Файлы после разделения: {files_in_dir}")

        # Сохраняем части в контексте
        context.user_data["split_files"] = files_in_dir
        context.user_data["total_parts"] = len(files_in_dir)
        context.user_data["current_part"] = 0
        context.user_data["awaiting_response"] = True

        # Отправка первой части
        await send_next_part(query, context)
    except Exception as e:
        logger.error(f"Ошибка при разделении аудио: {e}")
        await query.message.reply_text(text="Произошла ошибка при разделении аудио.")

# Функция для отправки следующей части
async def send_next_part(update: Update, context: CallbackContext) -> None:
    current_part = context.user_data["current_part"]
    split_files = context.user_data["split_files"]
    user_audio_dir = context.user_data["user_audio_dir"]

    if current_part < len(split_files):
        chunk_file = split_files[current_part]
        chunk_file_path = os.path.join(user_audio_dir, "split", chunk_file)
        logger.info(f"Отправка части {current_part + 1}: {chunk_file_path}")

        with open(chunk_file_path, "rb") as audio:
            await update.message.reply_voice(voice=audio, caption=f"Часть {current_part + 1}. Запишите свою версию!")
    else:
        await update.message.reply_text("Все части отправлены.")
        context.user_data["awaiting_response"] = False

# Основная функция запуска бота
def main():
    if not os.path.exists(BASE_AUDIO_PATH):
        os.makedirs(BASE_AUDIO_PATH)

    application = Application.builder().token(config.tg_bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.VOICE, handle_audio))

    application.run_polling()

if __name__ == "__main__":
    main()
