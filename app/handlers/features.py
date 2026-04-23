"""
Yangi funksiyalar:
  - AI Recommendation + For You feed
  - Anime DNA Profile
  - Daily Missions / Gamification
  - Clips (Shorts)
  - Anime Assistant (Claude API)
  - Dynamic Premium
  - A/B Testing
"""
import asyncio
import json
import aiohttp
import os
from app.database import Database

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database import Database

router = Router()

DNA_EMOJIS = {
    'Action':  '⚔️', 'Romance': '💕', 'Dark': '🌑',
    'Comedy':  '😂', 'Fantasy': '🔮', 'Sci-Fi': '🤖',
}

PREMIUM_TIERS = {
    'Simple':    {'label': '🆓 Oddiy',      'color': '⬜', 'perks': []},
    'Premium +': {'label': '💎 Premium +',  'color': '🟦', 'perks': [
        'VIP anime', 'Early access', 'Reklamasiz', 'Tezkor yuklash', 'Badge'
    ]},
}

db = Database()


ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


class AssistantState(StatesGroup):
    chatting = State()

class ClipUploadState(StatesGroup):
    anime_id = State()
    file     = State()
    caption  = State()


    # ══════════════════════════════════════════════════════════════════════
    # FOR YOU FEED (TikTok style)
    # ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "for_you")
async def for_you_start(call: CallbackQuery, state: FSMContext):
        await state.update_data(feed_offset=0)
        await _send_feed_item(call, db, 0)
        await call.answer()

@router.callback_query(F.data.startswith("feed_next_"))
async def feed_next(call: CallbackQuery, state: FSMContext):
        offset = int(call.data.split("_")[-1])
        await _send_feed_item(call, db, offset)
        await call.answer()

@router.callback_query(F.data.startswith("feed_watch_"))
async def feed_watch(call: CallbackQuery):
        anime_id = int(call.data.split("_")[-1])
        bot_me = await call.bot.get_me()
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text="▶️ To'liq ko'rish",
            url=f"https://t.me/{bot_me.username}?start={anime_id}"
        ))
        await call.message.answer("Tomosha qilish:", reply_markup=kb.as_markup())
        db.log_ab_event(call.from_user.id, 'feed_watch_click')
        await call.answer()

    # ══════════════════════════════════════════════════════════════════════
    # ANIME DNA PROFILE
    # ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "my_dna")
async def show_dna(call: CallbackQuery):
        user_id = call.from_user.id
        dna = db.get_anime_dna(user_id)
        user = db.get_user(user_id)

        if not dna:
            await call.message.answer(
                "🧬 <b>Anime DNA Profile</b>\n\n"
                "Hali yetarli ma'lumot yo'q!\n"
                "Kamida 3-5 ta anime ko'ring, keyin profilingiz tayyor bo'ladi.",
                parse_mode='HTML'
            )
            await call.answer(); return

        sorted_dna = sorted(dna.items(), key=lambda x: x[1], reverse=True)
        dominant = sorted_dna[0][0]

        text = f"🧬 <b>{user.get('first_name', 'Siz')}ning Anime DNA Profili</b>\n\n"
        for category, percent in sorted_dna:
            emoji = DNA_EMOJIS.get(category, '🎭')
            bar = _progress_bar(percent)
            text += f"{emoji} <b>{category}</b>\n{bar} {percent}%\n\n"

        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"🏆 Dominant janr: <b>{dominant} {DNA_EMOJIS.get(dominant,'')}</b>\n\n"
        text += f"📤 Do'stlaringizga ulashing!"

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text="📤 DNA Share qilish",
            switch_inline_query=f"Mening Anime DNA Profilim: {dominant} {DNA_EMOJIS.get(dominant,'')} {dna.get(dominant,0)}% | Botni sinab ko'r!"
        ))
        kb.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="back_main"))

        await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode='HTML')
        db.log_ab_event(user_id, 'dna_viewed')
        await call.answer()

    # ══════════════════════════════════════════════════════════════════════
    # DAILY MISSIONS
    # ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "daily_missions")
async def show_missions(call: CallbackQuery):
        user_id = call.from_user.id
        missions = db.get_daily_missions(user_id)
        user = db.get_user(user_id)
        streak = user.get('streak', 0) or 0
        coins  = user.get('coins', 0) or 0

        streak_bonus = db.get_streak_bonus(streak)

        text = f"🎮 <b>Kunlik Missiyalar</b>\n\n"
        text += f"🔥 Streak: <b>{streak} kun</b>"
        if streak_bonus:
            text += f" (+{streak_bonus} coin bonus)"
        text += f"\n💰 Coinlar: <b>{coins}</b>\n\n"

        for m in missions:
            icon = m['icon']
            prog = m.get('progress', 0)
            target = m['target']
            completed = m.get('completed', 0)
            reward = m['reward']

            if completed:
                status = "✅"
            else:
                status = f"{prog}/{target}"

            text += f"{icon} {m['text']}\n"
            text += f"   {status} → +{reward} 🪙\n\n"

        completed_count = sum(1 for m in missions if m.get('completed'))
        total = len(missions)
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"📊 Bugun: {completed_count}/{total} missiya bajarildi"

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🏆 Liderlar jadvali", callback_data="leaderboard"))
        kb.row(InlineKeyboardButton(text="🔙 Ortga",            callback_data="back_main"))

        await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode='HTML')
        await call.answer()

@router.callback_query(F.data == "leaderboard")
async def show_leaderboard(call: CallbackQuery):
        leaders = db.get_leaderboard(10)
        user_id = call.from_user.id

        text = "🏆 <b>Top 10 — Coin liderlar</b>\n\n"
        medals = ["🥇","🥈","🥉"] + ["🏅"]*7
        for i, u in enumerate(leaders):
            name = u.get('first_name') or f"User {u['user_id']}"
            you = " ← Siz" if u['user_id'] == user_id else ""
            text += f"{medals[i]} {name} — <b>{u['coins']} 🪙</b>{you}\n"

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="daily_missions"))
        await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode='HTML')
        await call.answer()

    # ══════════════════════════════════════════════════════════════════════
    # CLIPS / SHORTS
    # ══════════════════════════════════════════════════════════════════════
@router.callback_query(F.data == "watch_clips")
async def watch_clips(call: CallbackQuery):
        clips = db.get_random_clips(5)
        if not clips:
            await call.message.answer("📭 Hozircha shorts yo'q!")
            await call.answer(); return

        await call.message.answer(
            f"🎬 <b>Anime Shorts</b>\n\n"
            f"Qisqa highlight videolar — anime dunyosini bir daqiqada his qiling! 🔥",
            parse_mode='HTML'
        )

        for i, clip in enumerate(clips):
            db.increment_clip_views(clip['id'])
            bot_me = await call.bot.get_me()
            kb = InlineKeyboardBuilder()
            kb.row(
                InlineKeyboardButton(
                    text="▶️ To'liq anime",
                    url=f"https://t.me/{bot_me.username}?start={clip['anime_id']}"
                ),
                InlineKeyboardButton(
                    text=f"⭐ Baho ber",
                    callback_data=f"rate_anime_{clip['anime_id']}"
                )
            )
            caption = (
                f"🎬 <b>{clip['name']}</b>\n"
                f"🎭 {clip['genre']}\n"
                f"{'📝 '+clip['caption'] if clip['caption'] else ''}"
            )
            await call.message.answer_video(
                video=clip['file_id'],
                caption=caption,
                reply_markup=kb.as_markup(),
                parse_mode='HTML'
            )
            await asyncio.sleep(0.3)

        await call.answer()

@router.callback_query(F.data.startswith("clips_anime_"))
async def clips_for_anime(call: CallbackQuery):
        anime_id = int(call.data.split("_")[-1])
        anime = db.search_anime_by_id(anime_id)
        clips = db.get_clips(anime_id)
        if not clips:
            await call.answer("Bu anime uchun shorts yo'q!", show_alert=True)
            return
        bot_me = await call.bot.get_me()
        for clip in clips:
            db.increment_clip_views(clip['id'])
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(
                text="▶️ To'liq ko'rish",
                url=f"https://t.me/{bot_me.username}?start={anime_id}"
            ))
            await call.message.answer_video(
                video=clip['file_id'],
                caption=f"✂️ <b>{anime['name']}</b> — Highlight\n{clip.get('caption','')}",
                reply_markup=kb.as_markup(),
                parse_mode='HTML'
            )
            await asyncio.sleep(0.2)
        await call.answer()

    # Admin: clip qo'shish

@router.callback_query(F.data == "add_clip")
async def add_clip_start(call: CallbackQuery, state: FSMContext):
        if call.from_user.id != ADMIN_ID:
            await call.answer("❌ Ruxsat yo'q!"); return
        await state.set_state(ClipUploadState.anime_id)
        await call.message.answer("📎 Clip uchun Anime ID ni kiriting:")
        await call.answer()

@router.message(ClipUploadState.anime_id)
async def clip_anime_id(message: Message, state: FSMContext):
        try:
            anime_id = int(message.text)
            anime = db.search_anime_by_id(anime_id)
            if not anime:
                await message.answer("❌ Anime topilmadi!"); return
            await state.update_data(clip_anime_id=anime_id)
            await state.set_state(ClipUploadState.file)
            await message.answer(f"✅ {anime['name']}\nEndi 10-30 sekundlik clip videoni yuboring:")
        except ValueError:
            await message.answer("❌ Faqat raqam!")

@router.message(ClipUploadState.file, F.video)
async def clip_file(message: Message, state: FSMContext):
        await state.update_data(clip_file_id=message.video.file_id)
        await state.set_state(ClipUploadState.caption)
        await message.answer("📝 Clip uchun qisqa tavsif yozing (yoki /skip):")

@router.message(ClipUploadState.caption)
async def clip_caption(message: Message, state: FSMContext):
        caption = '' if message.text == '/skip' else message.text
        data = await state.get_data()
        db.add_clip(data['clip_anime_id'], data['clip_file_id'], caption)
        await state.clear()
        await message.answer("✅ Clip muvaffaqiyatli qo'shildi! 🎬")

    # ══════════════════════════════════════════════════════════════════════
    # ANIME ASSISTANT (Claude API)
    # ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "anime_assistant")
async def assistant_start(call: CallbackQuery, state: FSMContext):
        await state.set_state(AssistantState.chatting)
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🗑 Suhbatni tozala", callback_data="clear_ai_chat"))
        kb.row(InlineKeyboardButton(text="❌ Chiqish",         callback_data="exit_assistant"))
        await call.message.answer(
            "🤖 <b>Anime Assistant</b>\n\n"
            "Men anime haqida har qanday savolga javob bera olaman!\n\n"
            "💬 Misol:\n"
            "• <i>Naruto nechta qism?</i>\n"
            "• <i>Attack on Titan haqida tushuntir</i>\n"
            "• <i>Mening sevimli janrlarim uchun anime tavsiya qil</i>\n\n"
            "Savolingizni yozing 👇",
            reply_markup=kb.as_markup(),
            parse_mode='HTML'
        )
        db.log_ab_event(call.from_user.id, 'assistant_opened')
        await call.answer()

@router.message(AssistantState.chatting)
async def handle_assistant_message(message: Message, state: FSMContext):
        user_id = message.from_user.id
        user_text = message.text

        api_key = db.get_setting('anthropic_api_key')

        thinking_msg = await message.answer("🤔 O'ylamoqda...")

        if not api_key:
            # API key yo'q bo'lsa — built-in javob
            answer = _builtin_anime_answer(user_text, db, user_id)
        else:
            # Claude API bilan
            history = db.get_ai_history(user_id, limit=8)
            db.add_ai_message(user_id, 'user', user_text)
            answer = await _ask_claude(api_key, history, user_text, db, user_id)
            db.add_ai_message(user_id, 'assistant', answer)

        await thinking_msg.delete()

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🗑 Suhbatni tozala", callback_data="clear_ai_chat"))
        kb.row(InlineKeyboardButton(text="❌ Chiqish",         callback_data="exit_assistant"))

        await message.answer(
            f"🤖 <b>Anime Assistant:</b>\n\n{answer}",
            reply_markup=kb.as_markup(),
            parse_mode='HTML'
        )
        db.update_mission(user_id, 'search_anime')
        db.log_ab_event(user_id, 'assistant_message_sent')

@router.callback_query(F.data == "clear_ai_chat")
async def clear_ai_chat(call: CallbackQuery):
        db.clear_ai_history(call.from_user.id)
        await call.answer("✅ Suhbat tozalandi!")
        await call.message.answer("🗑 Suhbat tarixi o'chirildi. Yangi savol bering:")

@router.callback_query(F.data == "exit_assistant")
async def exit_assistant(call: CallbackQuery, state: FSMContext):
        await state.clear()
        from app.keyboards import main_menu_keyboard
        lang = db.get_user(call.from_user.id).get('language','uz')
        await call.message.answer("✅ Assistantdan chiqdingiz.", reply_markup=main_menu_keyboard(lang))
        await call.answer()

    # ══════════════════════════════════════════════════════════════════════
    # DYNAMIC PREMIUM
    # ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "premium_info")
async def premium_info(call: CallbackQuery):
        user = db.get_user(call.from_user.id)
        status = user.get('status', 'Simple')
        price  = db.get_setting('premium_price') or '5000'

        early_anime = db.get_early_access_anime()
        early_text = ""
        if early_anime:
            early_text = "\n\n🔒 <b>Early Access animelari (faqat Premium):</b>\n"
            for a in early_anime[:3]:
                early_text += f"  • {a['name']}\n"

        if status == 'Simple':
            text = (
                f"💎 <b>Premium + — Hamma imtiyozlar</b>\n\n"
                f"✅ VIP anime to'liq kirish\n"
                f"⚡ Early Access — yangi animeni birinchi ko'ring\n"
                f"🚫 Majburiy obunasiz foydalanish\n"
                f"📥 Video ulashish har doim ochiq\n"
                f"🏅 Premium badge profilda\n"
                f"🔔 Yangi anime qo'shilganda bildirishnoma\n"
                f"🤖 AI Assistant cheklovsiz\n"
                f"{early_text}\n\n"
                f"💳 Narx: <b>{price} UZS / 30 kun</b>"
            )
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text=f"💳 Sotib olish — {price} UZS", callback_data="buy_premium"))
            kb.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="back_main"))
        else:
            text = (
                f"💎 <b>Siz Premium + foydalanuvchisiz!</b>\n\n"
                f"📅 Muddat: <b>{user.get('vip_time','?')}</b>\n\n"
                f"✅ Barcha imtiyozlar faol\n"
                f"🏅 Badge: <b>Premium +</b>\n"
                f"{early_text}"
            )
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="🔄 Uzaytirish", callback_data="buy_premium"))
            kb.row(InlineKeyboardButton(text="🔙 Ortga",     callback_data="back_main"))

        await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode='HTML')
        db.log_ab_event(call.from_user.id, 'premium_page_viewed')
        await call.answer()

    # ══════════════════════════════════════════════════════════════════════
    # A/B TESTING STATS (admin)
    # ══════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "ab_test_stats")
async def ab_test_stats(call: CallbackQuery):
        if call.from_user.id != ADMIN_ID:
            await call.answer("❌"); return

        stats = db.get_ab_stats()
        text = "🧪 <b>A/B Test Natijalari</b>\n\n"

        for group, data in stats.items():
            text += f"<b>Guruh {group}</b> — {data['total_users']} foydalanuvchi\n"
            events = data.get('events', {})
            if events:
                for event, cnt in sorted(events.items(), key=lambda x: -x[1])[:5]:
                    text += f"  • {event}: {cnt}\n"
            else:
                text += "  • Hozircha event yo'q\n"

            # Konversiya hisoblash
            total = data['total_users']
            if total > 0:
                premium_events = events.get('premium_page_viewed', 0)
                conv = round(premium_events / total * 100, 1)
                text += f"  📈 Premium konversiya: {conv}%\n"
            text += "\n"

        text += "💡 A — eski dizayn | B — yangi dizayn"

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="back_admin"))
        await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode='HTML')
        await call.answer()


# ── Private helpers ────────────────────────────────────────────────────────────
async def _send_feed_item(call: CallbackQuery, db: Database, offset: int):
    user_id = call.from_user.id
    items = db.get_for_you_feed(user_id, offset=offset, limit=1)

    if not items:
        await call.message.answer("📭 Hozircha tavsiya yo'q! Ko'proq anime ko'ring.")
        return

    anime = items[0]
    match = anime.get('match_percent')
    match_text = f"\n🎯 <b>Sizga {match}% mos!</b>" if match else ""

    bot_me = await call.bot.get_me()
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="▶️ Ko'rish",       callback_data=f"feed_watch_{anime['id']}"),
        InlineKeyboardButton(text="⏭ Keyingisi",      callback_data=f"feed_next_{offset+1}")
    )
    kb.row(
        InlineKeyboardButton(text="🔔 Kuzatuvga qo'sh", callback_data=f"watchlist_toggle_{anime['id']}"),
        InlineKeyboardButton(text="⭐ Baho ber",         callback_data=f"rate_anime_{anime['id']}")
    )
    if anime.get('is_vip'):
        kb.row(InlineKeyboardButton(text="💎 VIP anime — Premium kerak", callback_data="premium_info"))

    caption = (
        f"🎬 <b>{anime['name']}</b>{match_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎭 {anime['genre']}\n"
        f"🎬 {anime['episode']} qism\n"
        f"⭐ {anime['rating']}/10 | 👁 {anime.get('views',0)}\n"
        f"📝 {anime['description'][:120]}..."
        if len(anime['description'] or '') > 120 else
        f"📝 {anime['description']}"
    )

    try:
        await call.message.answer_photo(
            photo=anime['image'],
            caption=caption,
            reply_markup=kb.as_markup(),
            parse_mode='HTML'
        )
    except Exception:
        await call.message.answer(
            caption, reply_markup=kb.as_markup(), parse_mode='HTML'
        )

    db.log_ab_event(user_id, 'feed_item_shown')


def _progress_bar(percent: int, length=12) -> str:
    filled = int(length * percent / 100)
    return '█' * filled + '░' * (length - filled)


def _builtin_anime_answer(text: str, db: Database, user_id: int) -> str:
    """API key yo'q bo'lganda built-in javoblar"""
    t = text.lower()

    if any(w in t for w in ['tavsiya', 'recommend', 'qaysi', 'nima ko\'ray']):
        recs = db.get_smart_recommendations(user_id, limit=3)
        if recs:
            ans = "🎯 <b>Siz uchun tavsiyalar:</b>\n\n"
            for a in recs:
                ans += f"• <b>{a['name']}</b> — {a['match_percent']}% mos\n  {a['genre']} | ⭐{a['rating']}\n\n"
            return ans
        return "Hali yetarli ma'lumot yo'q. Ko'proq anime ko'ring!"

    if any(w in t for w in ['top', 'eng yaxshi', 'best', 'popular']):
        top = db.get_top_anime(5)
        ans = "🏆 <b>Top 5 anime:</b>\n\n"
        for i, a in enumerate(top, 1):
            ans += f"{i}. <b>{a['name']}</b> — ⭐{a['rating']}/10\n"
        return ans

    if any(w in t for w in ['yangi', 'new', 'oxirgi', 'last']):
        new = db.get_new_releases(5)
        ans = "🆕 <b>Yangi animeler:</b>\n\n"
        for a in new:
            ans += f"• <b>{a['name']}</b> — {a['genre']}\n"
        return ans

    if any(w in t for w in ['action', 'romance', 'comedy', 'fantasy', 'dark', 'sci-fi']):
        for genre in ['action','romance','comedy','fantasy','dark','sci-fi']:
            if genre in t:
                results = db.search_anime_by_genre(genre)
                if results:
                    ans = f"🎭 <b>{genre.title()} janridagi animeler:</b>\n\n"
                    for a in results[:5]:
                        ans += f"• <b>{a['name']}</b> — ⭐{a['rating']}\n"
                    return ans

    # Generic javob
    return (
        "🤖 Men anime bot assistantiman!\n\n"
        "Quyidagilarni so'rashingiz mumkin:\n"
        "• <i>Tavsiya qil / Qaysi anime ko'ray?</i>\n"
        "• <i>Top anime / Eng yaxshi anime</i>\n"
        "• <i>Yangi anime</i>\n"
        "• <i>Action / Romance / Comedy anime</i>\n\n"
        "💡 To'liq AI javoblar uchun admin API key sozlashi kerak."
    )


async def _ask_claude(api_key: str, history: list, user_text: str,
                      db: Database, user_id: int) -> str:
    """Anthropic Claude API bilan suhbat"""
    system_prompt = (
        "Sen anime bo'yicha mutaxassis assistantsan. "
        "Foydalanuvchiga anime haqida savollarga qisqa, aniq va foydali javob ber. "
        "O'zbek tilida javob ber. Emoji ishlatish mumkin. "
        "Agar anime bazasidan ma'lumot kerak bo'lsa, umumiy bilimingdan foydalanish mumkin."
    )

    messages = []
    for h in history[-6:]:
        messages.append({"role": h['role'], "content": h['content']})
    messages.append({"role": "user", "content": user_text})

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 512,
                    "system": system_prompt,
                    "messages": messages
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['content'][0]['text']
                else:
                    return _builtin_anime_answer(user_text, db, user_id)
    except Exception:
        return _builtin_anime_answer(user_text, db, user_id)