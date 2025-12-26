import asyncio
import json
from pathlib import Path
import os
import random
import asyncio

from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def health():
    return {"status": "ok"}
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# -------------------------------------
# LOAD TOKEN (deferred - don't fail at import time)
# -------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# -------------------------------------
# PATHS
# -------------------------------------
BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = BASE_DIR / "questions.json"

# -------------------------------------
# DATA STRUCTURES
# -------------------------------------
router = Router()
QUESTIONS = []
ORDERED_QUESTIONS = []
QUESTION_INDEX = {}   # "1" -> question object
USER_PROGRESS = {}    # user_id -> {"difficulty":, "index":}
SEEN_USERS = set()    # user_ids that already received intro

USER_STATS = {}       # user_id -> stats dict

TOPIC_INDEX = {}      # topic_name -> [qnum strings]
TOPIC_NAME_MAP = {}   # lowercased topic -> canonical topic


# -------------------------------------
# HELPERS: STATS
# -------------------------------------
def get_user_stats(user_id: int):
    if user_id not in USER_STATS:
        USER_STATS[user_id] = {
            "total": 0,
            "correct": 0,
            "by_diff": {},      # diff -> {"total":, "correct":}
            "wrong_qnums": set()
        }
    return USER_STATS[user_id]


def update_stats(user_id: int, question: dict, qnum: str, is_correct: bool):
    stats = get_user_stats(user_id)

    stats["total"] += 1
    if is_correct:
        stats["correct"] += 1

    diff = question.get("difficulty", "unknown")
    by_diff = stats["by_diff"].setdefault(diff, {"total": 0, "correct": 0})
    by_diff["total"] += 1
    if is_correct:
        by_diff["correct"] += 1

    # wrong questions set
    if is_correct:
        stats["wrong_qnums"].discard(qnum)
    else:
        stats["wrong_qnums"].add(qnum)


# -------------------------------------
# LOAD QUESTIONS & TOPICS
# -------------------------------------
def load_questions():
    global QUESTIONS, ORDERED_QUESTIONS, QUESTION_INDEX, TOPIC_INDEX, TOPIC_NAME_MAP

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        QUESTIONS = json.load(f)

    ORDERED_QUESTIONS = QUESTIONS[:]
    QUESTION_INDEX = {str(i + 1): q for i, q in enumerate(ORDERED_QUESTIONS)}

    # Build topics index
    TOPIC_INDEX = {}
    for qnum, q in QUESTION_INDEX.items():
        topic = q.get("topic")
        if topic:
            topic_str = str(topic)
            TOPIC_INDEX.setdefault(topic_str, []).append(qnum)

    # lowercased name map
    TOPIC_NAME_MAP = {topic.lower(): topic for topic in TOPIC_INDEX.keys()}


def get_questions_by_difficulty(difficulty: str):
    return [q for q in QUESTIONS if q.get("difficulty") == difficulty]


# -------------------------------------
# SEND ANY QUESTION (universal)
# -------------------------------------
async def send_question_universal(bot, user_id, q, qnum, nav_mode="manual"):
    question_text = q.get("question_kg") or q.get("text") or "Суроо жок"

    options_block = "\n".join(
        f"{letter}) {text}" for letter, text in q["options"].items()
    )

    header = f"Суроо {qnum} / {len(ORDERED_QUESTIONS)}"

    msg = (
        f"{header}\n"
        f"────────────────────────\n"
        f"{question_text}\n\n"
        f"Жооп варианттары:\n{options_block}"
    )

    kb = InlineKeyboardBuilder()

    # Answer buttons
    for letter in q["options"].keys():
        kb.button(
            text=letter,
            callback_data=f"answer|{q['id']}|{letter}|{nav_mode}|{qnum}"
        )

    # Navigation buttons (global prev/next)
    kb.button(text="⬅️ Previous", callback_data=f"nav_prev|{qnum}")
    kb.button(text="➡️ Next", callback_data=f"nav_next|{qnum}")

    # First row: answers (A–D), second row: Prev/Next
    kb.adjust(4, 2)

    # With image
    image_path = q.get("image")
    if image_path:
        img_file = BASE_DIR / image_path
        if img_file.exists():
            await bot.send_photo(
                chat_id=user_id,
                photo=FSInputFile(img_file),
                caption=msg,
                reply_markup=kb.as_markup(),
            )
            return

    # Without image
    await bot.send_message(
        user_id,
        msg,
        reply_markup=kb.as_markup()
    )


# -------------------------------------
# SEND SEQUENTIAL QUESTION (by difficulty)
# -------------------------------------
async def send_sequential(bot, user_id, difficulty):
    questions = get_questions_by_difficulty(difficulty)
    if not questions:
        await bot.send_message(user_id, "Бул деңгээлде суроолор жок.")
        return

    progress = USER_PROGRESS.get(user_id)
    if not progress or progress["difficulty"] != difficulty:
        progress = {"difficulty": difficulty, "index": 0}
        USER_PROGRESS[user_id] = progress

    idx = progress["index"]

    if idx >= len(questions):
        await bot.send_message(user_id, "Бул деңгээлдеги бардык суроолорду бүттүң.")
        return

    q = questions[idx]

    # Find global qnum
    qnum = None
    for num, obj in QUESTION_INDEX.items():
        if obj["id"] == q["id"]:
            qnum = num
            break

    await send_question_universal(bot, user_id, q, qnum, nav_mode="sequential")


# -------------------------------------
# INTRO MESSAGE
# -------------------------------------
async def send_intro(message: Message):
    kb = InlineKeyboardBuilder()
    # Difficulty buttons
    kb.button(text="Жеңил", callback_data="level|easy")
    kb.button(text="Орточо", callback_data="level|medium")
    kb.button(text="Кыйын", callback_data="level|hard")
    # Extra onboarding (only random + help, NO topics button)
    kb.button(text="🎲 Random суроо", callback_data="intro_random")
    kb.button(text="ℹ️ Командалар", callback_data="intro_help")
    kb.adjust(1)

    intro_text = (
        "Салам! 👋 Бул бот SAT Math суроолорун кыргызча берёт: A/B/C/D варианттары, сүрөттөр, түшүндүрмө, Previous/Next навигациясы.\n\n"
        "Командалар:\n"
        "• /random — рандом суроо\n"
        "• /goto 25 — номер боюнча өтүү\n"
        "• /stats — статистика\n"
        "• /review_wrong — ката суроолор\n"
        "• /topics — темалар\n\n"
        "🇬🇧 English: SAT Math practice in Kyrgyz: images, explanations, navigation."
    )

    await message.answer(intro_text, reply_markup=kb.as_markup())


# -------------------------------------
# START COMMAND
# -------------------------------------
@router.message(CommandStart())
async def start_handler(message: Message):
    SEEN_USERS.add(message.from_user.id)
    await send_intro(message)


# -------------------------------------
# LEVEL SELECTOR
# -------------------------------------
@router.callback_query(F.data.startswith("level|"))
async def level_handler(callback: CallbackQuery, bot: Bot):
    _, difficulty = callback.data.split("|")

    USER_PROGRESS[callback.from_user.id] = {"difficulty": difficulty, "index": 0}

    await callback.message.answer(f"Тандалды: {difficulty}\nМына биринчи суроо:")
    await send_sequential(bot, callback.from_user.id, difficulty)
    await callback.answer()


# -------------------------------------
# INTRO EXTRA BUTTONS
# -------------------------------------
@router.callback_query(F.data == "intro_random")
async def intro_random(callback: CallbackQuery, bot: Bot):
    qnum = str(random.randint(1, len(ORDERED_QUESTIONS)))
    q = QUESTION_INDEX[qnum]
    await send_question_universal(bot, callback.from_user.id, q, qnum, nav_mode="manual")
    await callback.answer()


@router.callback_query(F.data == "intro_help")
async def intro_help(callback: CallbackQuery):
    text = (
        "Негизги командалар:\n"
        "• /start — баштапкы меню\n"
        "• /random — рандом суроо\n"
        "• /goto 25 — 25-суроого өтүү\n"
        "• /stats — сенин статистикаң\n"
        "• /review_wrong — мурун ката кеткен суроолор\n"
        "• /topics — бардык темалар\n"
        "• /topic Algebra — белгилүү тема боюнча суроо"
    )
    await callback.message.answer(text)
    await callback.answer()


# -------------------------------------
# /goto N
# -------------------------------------
@router.message(F.text.startswith("/goto"))
async def goto_handler(message: Message):
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Туура формат: /goto 59")
        return

    qnum = parts[1]

    if qnum not in QUESTION_INDEX:
        await message.answer("Бул номердеги суроо жок.")
        return

    q = QUESTION_INDEX[qnum]
    await send_question_universal(
        message.bot, message.from_user.id, q, qnum, nav_mode="manual"
    )


# -------------------------------------
# /random
# -------------------------------------
@router.message(F.text == "/random")
async def random_handler(message: Message):
    qnum = str(random.randint(1, len(ORDERED_QUESTIONS)))
    q = QUESTION_INDEX[qnum]
    await send_question_universal(
        message.bot, message.from_user.id, q, qnum, nav_mode="manual"
    )


# -------------------------------------
# /stats
# -------------------------------------
@router.message(F.text == "/stats")
async def stats_handler(message: Message):
    user_id = message.from_user.id
    stats = USER_STATS.get(user_id)

    if not stats or stats["total"] == 0:
        await message.answer("Азырынча статистика жок. Адегенде суроолорду чеч.")
        return

    total = stats["total"]
    correct = stats["correct"]
    acc = (correct / total) * 100 if total > 0 else 0.0

    lines = [
        "📊 Сенин статистикаң:",
        f"Бардык суроолор: {total}",
        f"Туура жооптор: {correct} ({acc:.1f}%)",
        ""
    ]

    if stats["by_diff"]:
        lines.append("Деңгээл боюнча:")
        for diff, d in stats["by_diff"].items():
            t = d["total"]
            c = d["correct"]
            a = (c / t) * 100 if t > 0 else 0.0
            lines.append(f"• {diff}: {c}/{t} ({a:.1f}%)")
    else:
        lines.append("Деңгээл боюнча маалымат жок.")

    wrong_count = len(stats["wrong_qnums"])
    lines.append(f"\nКайталай турган суроолор (wrong): {wrong_count}")
    if wrong_count > 0:
        sample = list(stats["wrong_qnums"])[:10]
        lines.append("Мисалы: " + ", ".join(sample))

    await message.answer("\n".join(lines))


# -------------------------------------
# /review_wrong
# -------------------------------------
@router.message(F.text == "/review_wrong")
async def review_wrong_handler(message: Message):
    user_id = message.from_user.id
    stats = USER_STATS.get(user_id)

    if not stats or not stats["wrong_qnums"]:
        await message.answer("Азырынча ката суроолор жок же баарын оңдогонсүң. 👌")
        return

    qnum = random.choice(list(stats["wrong_qnums"]))
    q = QUESTION_INDEX[qnum]
    await send_question_universal(
        message.bot, user_id, q, qnum, nav_mode="review"
    )


# -------------------------------------
# /topics
# -------------------------------------
@router.message(F.text == "/topics")
async def topics_handler(message: Message):
    if not TOPIC_INDEX:
        await message.answer("Азырынча темалар белгиленген эмес.")
        return

    lines = ["Бар болгон темалар:"]
    for topic, lst in sorted(TOPIC_INDEX.items()):
        lines.append(f"• {topic} ({len(lst)} суроо)")
    lines.append(
        "\nБелгилүү темадан суроо алуу үчүн:\n"
        "/topic <аталыш>\n"
        "Мисалы: /topic Algebra"
    )

    await message.answer("\n".join(lines))


# -------------------------------------
# /topic <name>
# -------------------------------------
@router.message(F.text.startswith("/topic"))
async def topic_handler(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Туура формат: /topic Algebra")
        return

    query = parts[1].strip().lower()
    topic_canonical = None

    if query in TOPIC_NAME_MAP:
        topic_canonical = TOPIC_NAME_MAP[query]
    else:
        for low, canon in TOPIC_NAME_MAP.items():
            if low.startswith(query):
                topic_canonical = canon
                break

    if not topic_canonical:
        await message.answer("Мындай тема табылган жок. /topics командасын кара.")
        return

    qnums = TOPIC_INDEX[topic_canonical]
    qnum = random.choice(qnums)
    q = QUESTION_INDEX[qnum]
    await send_question_universal(
        message.bot, message.from_user.id, q, qnum, nav_mode="manual"
    )


# -------------------------------------
# NAVIGATION BUTTONS (Prev/Next)
# -------------------------------------
@router.callback_query(F.data.startswith("nav_prev|"))
async def nav_prev(callback: CallbackQuery, bot: Bot):
    _, qnum = callback.data.split("|")
    cur = int(qnum)
    prev_num = str(cur - 1)
    if prev_num not in QUESTION_INDEX:
        await callback.message.answer("Бул биринчи суроо.")
        await callback.answer()
        return

    q = QUESTION_INDEX[prev_num]
    await send_question_universal(bot, callback.from_user.id, q, prev_num, nav_mode="manual")
    await callback.answer()


@router.callback_query(F.data.startswith("nav_next|"))
async def nav_next(callback: CallbackQuery, bot: Bot):
    _, qnum = callback.data.split("|")
    cur = int(qnum)
    next_num = str(cur + 1)
    if next_num not in QUESTION_INDEX:
        await callback.message.answer("Бул акыркы суроо.")
        await callback.answer()
        return

    q = QUESTION_INDEX[next_num]
    await send_question_universal(bot, callback.from_user.id, q, next_num, nav_mode="manual")
    await callback.answer()


# -------------------------------------
# ANSWER HANDLER (always with explanation)
# -------------------------------------
@router.callback_query(F.data.startswith("answer|"))
async def answer_handler(callback: CallbackQuery, bot: Bot):
    _, qid, choice, nav_mode, qnum = callback.data.split("|")

    q = QUESTION_INDEX[qnum]
    correct = q.get("answer") or q.get("correct")
    explanation = q.get("explanation_kg") or q.get("explanation") or ""

    is_correct = (choice == correct)
    user_id = callback.from_user.id

    # Update stats
    update_stats(user_id, q, qnum, is_correct)

    if is_correct:
        result = "✅ Туура!"
    else:
        result = (
            f"❌ Туура эмес.\n"
            f"Туура жооп: {correct}) {q['options'][correct]}"
        )

    text = f"{result}\n\nТүшүндүрмө:\n{explanation}"

    await callback.message.answer(text)

    # SEQUENTIAL navigation -> go to next question in this difficulty
    if nav_mode == "sequential":
        progress = USER_PROGRESS.get(user_id)
        if progress:
            progress["index"] += 1
            USER_PROGRESS[user_id] = progress
            await send_sequential(bot, user_id, progress["difficulty"])

    await callback.answer()


# -------------------------------------
# FALLBACK HANDLER
# -------------------------------------
@router.message()
async def fallback_handler(message: Message):
    text = message.text or ""

    # Commands handled by other handlers
    if text.startswith("/"):
        return

    user_id = message.from_user.id

    if user_id not in SEEN_USERS:
        SEEN_USERS.add(user_id)
        await send_intro(message)
    else:
        await message.answer(
            "Команда түшүнүксүз.\n"
            "Колдонсоң болот:\n"
            "• /start — баштапкы меню\n"
            "• /random — рандом суроо\n"
            "• /goto 15 — 15-суроого өтүү\n"
            "• /stats — сенин статистикаң\n"
            "• /review_wrong — ката суроолор"
        )


# -------------------------------------
# MAIN
# -------------------------------------
async def main():
    if not BOT_TOKEN:
        print("WARNING: BOT_TOKEN not found. Bot will not start.")
        return
    
    load_questions()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("BOT IS RUNNING...")
    await dp.start_polling(bot)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(main())