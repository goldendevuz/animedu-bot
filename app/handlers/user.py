import asyncio
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton,
    InlineQuery, InlineQueryResultPhoto
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database import Database
from app.keyboards import (
    main_menu_keyboard, search_keyboard, back_button,
    premium_keyboard, profile_keyboard, payment_confirmation_keyboard,
    ask_question_keyboard, language_keyboard, genre_select_keyboard,
    anime_detail_keyboard, rating_keyboard, review_ask_keyboard,
    episode_keyboard, inline_watch_keyboard, TEXTS
)

router = Router()
TEXTS_LIST = list(TEXTS.values())

class SearchStates(StatesGroup):
    search_name  = State()
    search_code  = State()
    search_genre = State()

class PaymentStates(StatesGroup):
    amount = State()
    photo  = State()

class ContactAdminState(StatesGroup):
    message = State()

class ReplyUserState(StatesGroup):
    message = State()

class RatingState(StatesGroup):
    review = State()

class GenreOnboarding(StatesGroup):
    selecting = State()


def register_user_handlers(router: Router, db: Database, admin_id: int):

    async def _check_sub(user_id, bot):
        channels = db.get_channels('request')
        if not channels: return True
        kb = InlineKeyboardBuilder()
        not_sub = False
        for i, ch in enumerate(channels):
            try:
                cid = ch['channel_id']
                if not cid.startswith('-100'): cid = f"-100{cid}"
                m = await bot.get_chat_member(chat_id=int(cid), user_id=user_id)
                ok = m.status in ('creator','administrator','member')
            except: ok = False
            title = ch['channel_link'].split('/')[-1] if ch['channel_link'] else f"Kanal {i+1}"
            kb.row(InlineKeyboardButton(
                text=f"{'✅' if ok else '❌'} {title}",
                url=ch['channel_link'] if ch['channel_link'] else None,
                callback_data=None if ch['channel_link'] else "no_link"
            ))
            if not ok: not_sub = True
        kb.row(InlineKeyboardButton(text="🔄 Tekshirish", callback_data="check_subscription"))
        if not_sub:
            await bot.send_message(
                user_id,
                "⚠️ <b>Botdan foydalanish uchun kanallarga obuna bo'ling!</b>",
                reply_markup=kb.as_markup(), parse_mode='HTML')
            return False
        return True

    def _lang(uid): 
        u = db.get_user(uid)
        return u.get('language','uz') if u else 'uz'

    def _is_off(uid): 
        return db.get_setting('situation') == 'Off' and uid != admin_id

    # ── /start ─────────────────────────────────────────────────────────────────
    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        await state.clear()
        user = message.from_user
        is_new = db.is_new_user(user.id)

        ref_by = None
        args = message.text.split()
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                ref_by = int(args[1].split("_")[1])
                if ref_by == user.id: ref_by = None
            except: pass

        db.add_user(user.id, user.username, user.first_name, user.last_name, ref_by)
        db.update_last_seen(user.id)

        # Streak bonus
        u = db.get_user(user.id)
        streak = u.get('streak', 0) or 0
        streak_bonus = db.get_streak_bonus(streak)

        # Login mission
        completed, reward = db.update_mission(user.id, 'daily_login')
        bonus_msgs = []
        if completed:
            bonus_msgs.append(f"📅 Kunlik kirish: +{reward} 🪙")
        if streak_bonus and streak > 1:
            db.add_coins(user.id, streak_bonus, f"Streak bonus {streak} kun")
            bonus_msgs.append(f"🔥 {streak} kunlik streak: +{streak_bonus} 🪙")

        # Referral bonus
        if is_new and ref_by:
            bonus = int(db.get_setting('referral_bonus') or 100)
            db.update_user_balance(ref_by, bonus)
            db.add_coins(ref_by, 10, "Referral coin")
            try:
                await message.bot.send_message(
                    ref_by,
                    f"🎉 <b>{user.first_name}</b> botga qo'shildi!\n💰 +{bonus} UZS bonus!",
                    parse_mode='HTML')
            except: pass

        if db.get_setting('situation') == 'Off' and user.id != admin_id:
            await message.answer("⚠️ <b>Bot vaqtincha ishlamayapti!</b>", parse_mode='HTML')
            return

        if not await _check_sub(user.id, message.bot): return

        # Yangi user — til tanlash
        if is_new:
            await message.answer(
                "🌐 <b>Tilni tanlang / Выберите язык / Choose language:</b>",
                reply_markup=language_keyboard(), parse_mode='HTML')
            return

        # Anime ID orqali kelgan
        if len(args) > 1 and not args[1].startswith("ref_"):
            try:
                await _send_anime_episodes(message, db, int(args[1]))
                return
            except ValueError: pass

        # Bonus xabari
        if bonus_msgs:
            await message.answer("🎁 " + " | ".join(bonus_msgs))

        lang = _lang(user.id)

        # Janr preferenslari yo'q bo'lsa
        if is_new and not db.has_genre_preferences(user.id):
            await state.set_state(GenreOnboarding.selecting)
            await state.update_data(selected_genres=[])
            await message.answer(
                "🎭 <b>Qaysi janrlarni yaxshi ko'rasiz?</b>",
                reply_markup=genre_select_keyboard([]), parse_mode='HTML')
            return

        db.log_ab_event(user.id, 'start_opened')
        start_text = db.get_setting('start_text') or '❄️ Xush kelibsiz!'

        # A/B test: A guruh oddiy start, B guruh "For You" taklifi bilan
        ab = db.get_ab_group(user.id)
        if ab == 'B':
            start_text += "\n\n✨ <b>Siz uchun tavsiyalar tayyor!</b> «Siz uchun» tugmasini bosing!"

        await message.answer(start_text, reply_markup=main_menu_keyboard(lang), parse_mode='HTML')

    # ── Til tanlash ────────────────────────────────────────────────────────────
    @router.callback_query(F.data.startswith("lang_"))
    async def set_lang(call: CallbackQuery, state: FSMContext):
        lang = call.data.split("_")[1]
        db.set_user_language(call.from_user.id, lang)
        await call.answer("✅")
        if not db.has_genre_preferences(call.from_user.id):
            await state.set_state(GenreOnboarding.selecting)
            await state.update_data(selected_genres=[])
            await call.message.edit_text(
                "🎭 <b>Qaysi janrlarni yaxshi ko'rasiz?</b>",
                reply_markup=genre_select_keyboard([]), parse_mode='HTML')
        else:
            await call.message.edit_text(
                db.get_setting('start_text') or '❄️ Xush kelibsiz!',
                reply_markup=main_menu_keyboard(lang), parse_mode='HTML')

    @router.callback_query(F.data == "change_language")
    async def change_lang(call: CallbackQuery):
        await call.message.edit_text("🌐 <b>Tilni tanlang:</b>", reply_markup=language_keyboard(), parse_mode='HTML')
        await call.answer()

    # ── Genre onboarding ───────────────────────────────────────────────────────
    @router.callback_query(GenreOnboarding.selecting, F.data.startswith("genre_toggle_"))
    async def genre_toggle(call: CallbackQuery, state: FSMContext):
        genre = call.data.replace("genre_toggle_","")
        data = await state.get_data()
        sel = data.get('selected_genres', [])
        if genre in sel: sel.remove(genre)
        else: sel.append(genre)
        await state.update_data(selected_genres=sel)
        await call.message.edit_reply_markup(reply_markup=genre_select_keyboard(sel))
        await call.answer()

    @router.callback_query(GenreOnboarding.selecting, F.data == "genre_done")
    async def genre_done(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        sel = data.get('selected_genres', [])
        if sel: db.save_user_genres(call.from_user.id, sel)
        await state.clear()
        lang = _lang(call.from_user.id)
        await call.message.edit_text("✅ Janrlar saqlandi! 🎉", parse_mode='HTML')
        await call.message.answer(
            db.get_setting('start_text') or '❄️ Xush kelibsiz!',
            reply_markup=main_menu_keyboard(lang), parse_mode='HTML')
        await call.answer()

    # ── Menu handlerlari ───────────────────────────────────────────────────────
    all_texts = {t[k] for t in TEXTS_LIST for k in t}

    @router.message(F.text.in_({t['search'] for t in TEXTS_LIST}))
    async def menu_search(message: Message):
        if _is_off(message.from_user.id): return
        if not await _check_sub(message.from_user.id, message.bot): return
        db.update_mission(message.from_user.id, 'search_anime')
        await message.answer("🔎 Animeni qanday izlaymiz?", reply_markup=search_keyboard())

    @router.message(F.text.in_({t['for_you'] for t in TEXTS_LIST if 'for_you' in t}))
    async def menu_for_you(message: Message):
        if _is_off(message.from_user.id): return
        if not await _check_sub(message.from_user.id, message.bot): return
        db.log_ab_event(message.from_user.id, 'for_you_opened')
        from app.handlers.features import _send_feed_item

        class FakeCall:
            def __init__(self, msg): self.message = msg; self.from_user = msg.from_user; self.bot = msg.bot
            async def answer(self): pass

        fake = FakeCall(message)
        await message.answer("✨ <b>Siz uchun tavsiyalar:</b>", parse_mode='HTML')
        await _send_feed_item(fake, db, 0)

    @router.message(F.text.in_({t['shorts'] for t in TEXTS_LIST if 'shorts' in t}))
    async def menu_shorts(message: Message):
        if _is_off(message.from_user.id): return
        if not await _check_sub(message.from_user.id, message.bot): return
        clips = db.get_random_clips(5)
        if not clips:
            await message.answer("📭 Hozircha shorts yo'q!"); return
        await message.answer("🎬 <b>Anime Shorts</b> — eng qiziqarli momentlar!", parse_mode='HTML')
        bot_me = await message.bot.get_me()
        for clip in clips:
            db.increment_clip_views(clip['id'])
            kb = InlineKeyboardBuilder()
            kb.row(
                InlineKeyboardButton(text="▶️ To'liq anime", url=f"https://t.me/{bot_me.username}?start={clip['anime_id']}"),
                InlineKeyboardButton(text="⭐ Baho ber",     callback_data=f"rate_anime_{clip['anime_id']}")
            )
            await message.answer_video(
                video=clip['file_id'],
                caption=f"🎬 <b>{clip['name']}</b>\n🎭 {clip['genre']}\n{clip.get('caption','')}",
                reply_markup=kb.as_markup(), parse_mode='HTML')
            await asyncio.sleep(0.3)

    @router.message(F.text.in_({t['top'] for t in TEXTS_LIST}))
    async def menu_top(message: Message):
        if _is_off(message.from_user.id): return
        if not await _check_sub(message.from_user.id, message.bot): return
        top = db.get_top_anime(10)
        if not top:
            await message.answer("Hozircha top anime yo'q!"); return
        text = "🏆 <b>Top 10 Anime:</b>\n\n"
        for i, a in enumerate(top, 1):
            vip = " 💎" if a.get('is_vip') else ""
            text += f"{i}. <b>{a['name']}</b>{vip} — ⭐{a['rating']} | 👁{a['views']}\n"
        kb = InlineKeyboardBuilder()
        for a in top:
            kb.row(InlineKeyboardButton(text=f"📺 {a['name']}", callback_data=f"anime_{a['id']}"))
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode='HTML')

    @router.message(F.text.in_({t['missions'] for t in TEXTS_LIST if 'missions' in t}))
    async def menu_missions(message: Message):
        if _is_off(message.from_user.id): return
        class FakeCall:
            def __init__(self, msg): self.message = msg; self.from_user = msg.from_user; self.bot = msg.bot
            async def answer(self): pass
        # Direct call
        missions = db.get_daily_missions(message.from_user.id)
        user = db.get_user(message.from_user.id)
        streak = user.get('streak',0) or 0
        coins  = user.get('coins',0) or 0
        streak_bonus = db.get_streak_bonus(streak)
        text = f"🎮 <b>Kunlik Missiyalar</b>\n\n"
        text += f"🔥 Streak: <b>{streak} kun</b>"
        if streak_bonus: text += f" (+{streak_bonus} coin bonus)"
        text += f"\n💰 Coinlar: <b>{coins}</b>\n\n"
        for m in missions:
            prog = m.get('progress',0); target = m['target']
            comp = m.get('completed',0)
            status = "✅" if comp else f"{prog}/{target}"
            text += f"{m['icon']} {m['text']}\n   {status} → +{m['reward']} 🪙\n\n"
        done = sum(1 for m in missions if m.get('completed'))
        text += f"📊 Bugun: {done}/{len(missions)} missiya"
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🏆 Liderlar jadvali", callback_data="leaderboard"))
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode='HTML')

    @router.message(F.text.in_({t['dna'] for t in TEXTS_LIST}))
    async def menu_dna(message: Message):
        if _is_off(message.from_user.id): return
        class FakeCall:
            def __init__(self, msg): self.message = msg; self.from_user = msg.from_user; self.bot = msg.bot
            async def answer(self): pass
        from app.handlers.features import show_dna
        await show_dna(FakeCall(message))

    @router.message(F.text.in_({t['watchlist'] for t in TEXTS_LIST}))
    async def menu_watchlist(message: Message):
        if _is_off(message.from_user.id): return
        wl = db.get_user_watchlist(message.from_user.id)
        if not wl:
            await message.answer("📭 Kuzatuv ro'yxatingiz bo'sh!\nAnime sahifasida 🔔 tugmani bosing."); return
        kb = InlineKeyboardBuilder()
        for item in wl:
            kb.row(InlineKeyboardButton(
                text=f"📺 {item['name']} ({item['episode']} qism)",
                callback_data=f"anime_{item['anime_id']}"))
        await message.answer("📌 <b>Kuzatuv ro'yxatingiz:</b>", reply_markup=kb.as_markup(), parse_mode='HTML')

    @router.message(F.text.in_({t['history'] for t in TEXTS_LIST}))
    async def menu_history(message: Message):
        if _is_off(message.from_user.id): return
        history = db.get_user_history(message.from_user.id)
        if not history:
            await message.answer("📭 Ko'rish tarixi bo'sh!"); return
        kb = InlineKeyboardBuilder()
        for item in history:
            kb.row(InlineKeyboardButton(
                text=f"📺 {item['name']} — {item['episode_number']}/{item['episode']} qism",
                callback_data=f"resume_{item['anime_id']}_{item['episode_number']}"))
        await message.answer("🕓 <b>Ko'rish tarixi:</b>", reply_markup=kb.as_markup(), parse_mode='HTML')

    @router.message(F.text.in_({t['assistant'] for t in TEXTS_LIST}))
    async def menu_assistant(message: Message, state: FSMContext):
        if _is_off(message.from_user.id): return
        from aiogram.fsm.state import State
        from app.handlers.features import AssistantState
        await state.set_state(AssistantState.chatting)
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🗑 Suhbatni tozala", callback_data="clear_ai_chat"))
        kb.row(InlineKeyboardButton(text="❌ Chiqish",         callback_data="exit_assistant"))
        await message.answer(
            "🤖 <b>Anime Assistant</b>\n\n"
            "Anime haqida har qanday savol bering!\n\n"
            "• <i>Tavsiya qil</i>\n• <i>Top anime</i>\n• <i>Naruto haqida</i>",
            reply_markup=kb.as_markup(), parse_mode='HTML')
        db.log_ab_event(message.from_user.id, 'assistant_opened')

    @router.message(F.text.in_({t['premium'] for t in TEXTS_LIST}))
    async def menu_premium(message: Message):
        if _is_off(message.from_user.id): return
        db.log_ab_event(message.from_user.id, 'premium_page_viewed')
        user = db.get_user(message.from_user.id)
        if user['status'] == 'Simple':
            await message.answer(
                "💎 <b>Premium + imtiyozlari:</b>\n\n"
                "✅ VIP anime to'liq kirish\n"
                "⚡ Early Access — yangi animeni birinchi ko'ring\n"
                "🚫 Majburiy obunasiz\n"
                "🏅 Premium badge\n"
                "🤖 AI Assistant cheklovsiz",
                reply_markup=premium_keyboard(), parse_mode='HTML')
        else:
            await message.answer(f"💎 Siz <b>Premium +</b> da!\n📅 Muddat: {user['vip_time']}", parse_mode='HTML')

    @router.message(F.text.in_({t['profile'] for t in TEXTS_LIST}))
    async def menu_profile(message: Message):
        if _is_off(message.from_user.id): return
        user = db.get_user(message.from_user.id)
        ref_count = db.get_referral_count(message.from_user.id)
        bot_me = await message.bot.get_me()
        status_badge = "🏅 Premium +" if user['status'] == 'Premium +' else "🆓 Oddiy"
        await message.answer(
            f"🧑‍💻 <b>Shaxsiy hisobingiz</b>\n\n"
            f"💰 Balans: <b>{user['balance']} UZS</b>\n"
            f"🪙 Coinlar: <b>{user.get('coins',0)}</b>\n"
            f"🔥 Streak: <b>{user.get('streak',0)} kun</b>\n"
            f"🆔 ID: <code>{user['user_id']}</code>\n"
            f"💎 Status: <b>{status_badge}</b>\n"
            f"👥 Taklif qilinganlar: <b>{ref_count}</b>\n\n"
            f"🔗 Referral link:\n<code>https://t.me/{bot_me.username}?start=ref_{user['user_id']}</code>",
            reply_markup=profile_keyboard(), parse_mode='HTML')

    @router.message(F.text.in_({t['contact'] for t in TEXTS_LIST}))
    async def menu_contact(message: Message, state: FSMContext):
        if _is_off(message.from_user.id): return
        await state.set_state(ContactAdminState.message)
        await message.answer("Adminga yubormoqchi bo'lgan xabaringizni kiriting:", reply_markup=back_button())

    # ── Resume ─────────────────────────────────────────────────────────────────
    @router.callback_query(F.data.startswith("resume_"))
    async def resume_watching(call: CallbackQuery):
        parts = call.data.split("_")
        await _send_episode(call.message, db, int(parts[1]), int(parts[2]), call.from_user.id)
        await call.answer()

    # ── Contact admin FSM ──────────────────────────────────────────────────────
    @router.message(ContactAdminState.message)
    async def handle_admin_message(message: Message, state: FSMContext):
        user_id = message.from_user.id
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"reply_{user_id}"))
        await message.bot.send_message(
            admin_id,
            f"📩 Yangi xabar:\n👤 ID: {user_id}\n💬 {message.text}",
            reply_markup=kb.as_markup())
        await state.clear()
        await message.answer("✅ Xabaringiz adminga yuborildi!", reply_markup=ask_question_keyboard())

    @router.callback_query(F.data == "ask_question")
    async def ask_question(call: CallbackQuery, state: FSMContext):
        await state.set_state(ContactAdminState.message)
        await call.message.answer("Adminga yubormoqchi bo'lgan xabaringizni kiriting:")
        await call.answer()

    @router.callback_query(F.data.startswith("reply_"))
    async def reply_to_user(call: CallbackQuery, state: FSMContext):
        target_id = int(call.data.split("_")[1])
        await state.update_data(reply_user_id=target_id)
        await state.set_state(ReplyUserState.message)
        await call.message.answer("✍️ Foydalanuvchiga javob yozing:")
        await call.answer()

    @router.message(ReplyUserState.message)
    async def handle_reply(message: Message, state: FSMContext):
        data = await state.get_data(); await state.clear()
        try:
            await message.bot.send_message(data['reply_user_id'],
                f"📩 Admin javobi:\n\n{message.text}", reply_markup=ask_question_keyboard())
            await message.answer("✅ Javob yuborildi!")
        except Exception as e:
            await message.answer(f"❌ Xato: {e}")

    # ── Search ─────────────────────────────────────────────────────────────────
    @router.callback_query(F.data == "search_name")
    async def search_name_cb(call: CallbackQuery, state: FSMContext):
        await state.set_state(SearchStates.search_name)
        await call.message.edit_text(
            "🔎 Anime nomini kiriting:\n\n📝 Namuna: <code>Naruto Shippuden</code>",
            reply_markup=back_button(), parse_mode='HTML'); await call.answer()

    @router.message(SearchStates.search_name)
    async def handle_search_name(message: Message, state: FSMContext):
        await state.clear()
        db.update_mission(message.from_user.id, 'search_anime')
        await _send_anime_list(message, db, db.search_anime_by_name(message.text))

    @router.callback_query(F.data == "search_code")
    async def search_code_cb(call: CallbackQuery, state: FSMContext):
        await state.set_state(SearchStates.search_code)
        await call.message.edit_text(
            "🔎 Anime kodini kiriting:\n\n📝 Namuna: <code>99</code>",
            reply_markup=back_button(), parse_mode='HTML'); await call.answer()

    @router.message(SearchStates.search_code)
    async def handle_search_code(message: Message, state: FSMContext):
        await state.clear()
        try:
            anime = db.search_anime_by_id(int(message.text))
            if anime: await _send_anime_card(message, db, anime, message.from_user.id)
            else: await message.answer("❌ Anime topilmadi!", reply_markup=back_button())
        except ValueError:
            await message.answer("⚠️ Faqat raqam kiriting!", reply_markup=back_button())

    @router.callback_query(F.data == "search_genre")
    async def search_genre_cb(call: CallbackQuery, state: FSMContext):
        await state.set_state(SearchStates.search_genre)
        await call.message.edit_text(
            "🔎 Janrni kiriting:\n\n📌 Masalan: Action, Comedy, Drama...",
            reply_markup=back_button()); await call.answer()

    @router.message(SearchStates.search_genre)
    async def handle_search_genre(message: Message, state: FSMContext):
        await state.clear()
        await _send_anime_list(message, db, db.search_anime_by_genre(message.text))

    # ── Anime detail ───────────────────────────────────────────────────────────
    @router.callback_query(F.data.startswith("anime_"))
    async def show_anime(call: CallbackQuery):
        try:
            anime_id = int(call.data.split('_')[1])
            anime = db.search_anime_by_id(anime_id)
            if anime: await _send_anime_card(call.message, db, anime, call.from_user.id)
        except (ValueError, IndexError):
            await call.answer("Xatolik!", show_alert=True)
        await call.answer()

    # ── Watchlist ──────────────────────────────────────────────────────────────
    @router.callback_query(F.data.startswith("watchlist_toggle_"))
    async def watchlist_toggle(call: CallbackQuery):
        anime_id = int(call.data.split("_")[-1])
        uid = call.from_user.id
        if db.is_in_watchlist(uid, anime_id):
            db.remove_from_watchlist(uid, anime_id)
            await call.answer("🔕 Kuzatuvdan olib tashlandi")
        else:
            db.add_to_watchlist(uid, anime_id)
            db.update_mission(uid, 'add_watchlist')
            await call.answer("🔔 Kuzatuvga qo'shildi!")
        anime = db.search_anime_by_id(anime_id)
        if anime:
            bot_me = await call.bot.get_me()
            clips = db.get_clips(anime_id)
            try:
                await call.message.edit_reply_markup(
                    reply_markup=anime_detail_keyboard(
                        bot_me.username, anime_id,
                        db.is_in_watchlist(uid, anime_id),
                        bool(anime.get('is_vip')),
                        bool(clips)
                    ))
            except: pass

    # ── Rating ─────────────────────────────────────────────────────────────────
    @router.callback_query(F.data.startswith("rate_anime_"))
    async def rate_anime(call: CallbackQuery):
        anime_id = int(call.data.split("_")[-1])
        existing = db.get_user_rating(anime_id, call.from_user.id)
        text = (f"⭐ Hozirgi bahoyingiz: {existing['rating']}/10\n\n" if existing else "") + "Yangi baho bering:"
        await call.message.answer(text, reply_markup=rating_keyboard(anime_id))
        await call.answer()

    @router.callback_query(F.data.startswith("give_rating_"))
    async def give_rating(call: CallbackQuery, state: FSMContext):
        parts = call.data.split("_")
        anime_id, rating = int(parts[2]), int(parts[3])
        await state.update_data(rating_anime_id=anime_id, rating_value=rating)
        await state.set_state(RatingState.review)
        await call.message.edit_text(
            f"✅ Baho: {rating}/10 ⭐\n\nSharh yozmoqchimisiz?",
            reply_markup=review_ask_keyboard(anime_id))
        await call.answer()

    @router.callback_query(F.data.startswith("write_review_"))
    async def write_review_cb(call: CallbackQuery):
        await call.message.edit_text("✍️ Sharhingizni yozing:"); await call.answer()

    @router.message(RatingState.review)
    async def handle_review(message: Message, state: FSMContext):
        data = await state.get_data()
        db.add_rating(data['rating_anime_id'], message.from_user.id, data['rating_value'], message.text)
        completed, reward = db.update_mission(message.from_user.id, 'give_rating')
        await state.clear()
        anime = db.search_anime_by_id(data['rating_anime_id'])
        msg = f"✅ Baho va sharh saqlandi! ⭐{anime['rating']}/10"
        if completed: msg += f"\n🎉 Mission: +{reward} 🪙"
        await message.answer(msg)

    @router.callback_query(F.data.startswith("reviews_"))
    async def show_reviews(call: CallbackQuery):
        anime_id = int(call.data.split("_")[-1])
        reviews = db.get_anime_reviews(anime_id)
        anime = db.search_anime_by_id(anime_id)
        if not reviews:
            await call.answer("Hali sharh yo'q!", show_alert=True); return
        text = f"💬 <b>{anime['name']} — Sharhlar:</b>\n\n"
        for r in reviews:
            text += f"👤 <b>{r['first_name']}</b> — ⭐{r['rating']}/10\n<i>{r['review']}</i>\n\n"
        await call.message.answer(text, parse_mode='HTML')
        await call.answer()

    # ── Episode nav ────────────────────────────────────────────────────────────
    @router.callback_query(F.data.startswith("ep_"))
    async def episode_nav(call: CallbackQuery):
        parts = call.data.split("_")
        await _send_episode(call.message, db, int(parts[1]), int(parts[2]), call.from_user.id)
        await call.answer()

    # ── Inline query ───────────────────────────────────────────────────────────
    @router.inline_query()
    async def inline_search(query: InlineQuery):
        q = query.query.strip()
        results_list = db.search_anime_by_name(q)[:10] if q else db.get_top_anime(10)
        bot_me = await query.bot.get_me()
        results = []
        for anime in results_list:
            results.append(InlineQueryResultPhoto(
                id=str(anime['id']),
                photo_url=anime['image'], thumbnail_url=anime['image'],
                title=anime['name'],
                description=f"⭐{anime['rating']} | {anime['genre']} | {anime['episode']} qism",
                caption=_anime_caption(anime), parse_mode='HTML',
                reply_markup=inline_watch_keyboard(bot_me.username, anime['id'])
            ))
        await query.answer(results, cache_time=10)

    # ── Premium / Payment ──────────────────────────────────────────────────────
    @router.callback_query(F.data == "buy_premium")
    async def buy_premium(call: CallbackQuery):
        user = db.get_user(call.from_user.id)
        price = int(db.get_setting('premium_price') or 5000)
        if user['balance'] >= price:
            vip_time = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
            db.update_user_balance(call.from_user.id, -price)
            db.set_user_vip(call.from_user.id, vip_time)
            db.add_coins(call.from_user.id, 50, "Premium bonus coins")
            db.log_ab_event(call.from_user.id, 'premium_purchased')
            await call.message.edit_text(
                f"✅ <b>Premium + faollashtirildi!</b> 🏆\n\n"
                f"📅 Muddat: <b>{vip_time}</b>\n"
                f"🎁 Bonus: <b>+50 🪙</b> coin", parse_mode='HTML')
        else:
            await call.message.edit_text(
                f"⚠️ Balansingizda yetarlicha mablag' yo'q!\n\n"
                f"Kerak: <b>{price} UZS</b> | Sizda: <b>{user['balance']} UZS</b>\n\n"
                f"➕ Pul kiritish uchun profilingizga o'ting.", parse_mode='HTML')
        await call.answer()

    @router.callback_query(F.data == "add_money")
    async def add_money(call: CallbackQuery):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="✅ To'lov qildim", callback_data="payment_done"),
               InlineKeyboardButton(text="🔙 Ortga",         callback_data="back_main"))
        await call.message.edit_text(
            "💳 <b>Pul kiritish</b>\n\n"
            "📌 Quyidagi kartaga pul tashlang va chekni yuboring.\n\n"
            "💳 Karta: <code>12345678</code>\n👤 Otajonov O.",
            reply_markup=kb.as_markup(), parse_mode='HTML'); await call.answer()

    @router.callback_query(F.data == "referral_link")
    async def referral_link(call: CallbackQuery):
        bot_me = await call.bot.get_me()
        uid = call.from_user.id
        ref_count = db.get_referral_count(uid)
        bonus = db.get_setting('referral_bonus') or '100'
        await call.message.answer(
            f"🔗 <b>Referral linkiniz:</b>\n"
            f"<code>https://t.me/{bot_me.username}?start=ref_{uid}</code>\n\n"
            f"👥 Taklif qilinganlar: <b>{ref_count}</b>\n"
            f"💰 Har bir taklif: <b>{bonus} UZS</b>",
            parse_mode='HTML'); await call.answer()

    @router.callback_query(F.data == "payment_done")
    async def payment_done(call: CallbackQuery, state: FSMContext):
        await state.set_state(PaymentStates.amount)
        await call.message.edit_text("💰 Qancha to'lov qildingiz?", reply_markup=back_button()); await call.answer()

    @router.message(PaymentStates.amount)
    async def payment_amount(message: Message, state: FSMContext):
        try:
            await state.update_data(payment_amount=int(message.text))
            await state.set_state(PaymentStates.photo)
            await message.answer("📸 To'lov chekini yuboring:", reply_markup=back_button())
        except ValueError:
            await message.answer("⚠️ Faqat raqam!", reply_markup=back_button())

    @router.message(PaymentStates.photo, F.photo)
    async def payment_photo(message: Message, state: FSMContext):
        data = await state.get_data()
        amount = data['payment_amount']
        photo = message.photo[-1].file_id
        uid = message.from_user.id
        payment_id = db.add_payment(uid, amount, photo)
        await state.clear()
        await message.answer("✅ To'lov arizasi adminga yuborildi!")
        await message.bot.send_photo(
            admin_id, photo,
            caption=f"👤 User: {uid}\n💰 Summa: {amount} UZS\n✅ Tasdiqlaysizmi?",
            reply_markup=payment_confirmation_keyboard(payment_id))

    @router.message(PaymentStates.photo)
    async def payment_photo_wrong(message: Message):
        await message.answer("⚠️ Faqat rasm yuboring!", reply_markup=back_button())

    @router.callback_query(F.data.startswith("confirm_payment_"))
    async def confirm_payment(call: CallbackQuery):
        payment_id = int(call.data.split('_')[-1])
        conn = db.get_connection(); cur = conn.cursor()
        try:
            cur.execute('SELECT user_id,amount FROM payments WHERE id=?',(payment_id,))
            p = cur.fetchone()
            if p:
                uid, amount = p
                cur.execute('UPDATE payments SET status=? WHERE id=?',('confirmed',payment_id))
                cur.execute('UPDATE users SET balance=balance+? WHERE user_id=?',(amount,uid))
                conn.commit()
                await call.bot.send_message(uid, f"✅ To'lovingiz tasdiqlandi! Balans +{amount} UZS")
                await call.answer("✅ Tasdiqlandi!")
        except Exception as e:
            await call.answer(f"Xato: {e}", show_alert=True)
        finally:
            conn.close()

    @router.callback_query(F.data.startswith("cancel_payment_"))
    async def cancel_payment(call: CallbackQuery):
        db.update_payment_status(int(call.data.split('_')[-1]), 'cancelled')
        await call.answer("❌ Bekor qilindi")

    # ── Subscription check ─────────────────────────────────────────────────────
    @router.callback_query(F.data == "check_subscription")
    async def check_sub_cb(call: CallbackQuery):
        if await _check_sub(call.from_user.id, call.bot):
            lang = _lang(call.from_user.id)
            await call.message.edit_text(
                db.get_setting('start_text') or '❄️ Xush kelibsiz!',
                reply_markup=main_menu_keyboard(lang), parse_mode='HTML')
        await call.answer()

    # ── Back main ──────────────────────────────────────────────────────────────
    @router.callback_query(F.data == "back_main")
    async def back_main(call: CallbackQuery, state: FSMContext):
        await state.clear()
        lang = _lang(call.from_user.id)
        await call.message.edit_text(
            db.get_setting('start_text') or '❄️ Xush kelibsiz!',
            reply_markup=main_menu_keyboard(lang), parse_mode='HTML')
        await call.answer()


# ── Helpers ────────────────────────────────────────────────────────────────────
def _anime_caption(anime: dict) -> str:
    vip = " 💎" if anime.get('is_vip') else ""
    early = " ⚡" if anime.get('early_access') else ""
    return (
        f"📺 <b>{anime['name']}</b>{vip}{early}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎭 <b>Janr:</b> {anime['genre']}\n"
        f"🎬 <b>Epizodlar:</b> {anime['episode']}\n"
        f"🌍 <b>Davlat:</b> {anime.get('country','')}\n"
        f"⭐ <b>Reyting:</b> {anime['rating']}/10\n"
        f"👁 <b>Ko'rishlar:</b> {anime.get('views',0)}\n"
        f"📝 <b>Tavsif:</b> <i>{anime.get('description','')}</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>ID:</b> {anime['id']}"
    )


async def _send_anime_card(message: Message, db: Database, anime: dict, user_id: int = None):
    bot_me = await message.bot.get_me()
    in_wl = db.is_in_watchlist(user_id, anime['id']) if user_id else False
    clips = db.get_clips(anime['id']) if user_id else []
    kb = anime_detail_keyboard(
        bot_me.username, anime['id'], in_wl,
        bool(anime.get('is_vip')), bool(clips)
    )
    try:
        await message.answer_photo(photo=anime['image'], caption=_anime_caption(anime),
                                    reply_markup=kb, parse_mode='HTML')
    except Exception:
        await message.answer(_anime_caption(anime), reply_markup=kb, parse_mode='HTML')


async def _send_anime_list(message: Message, db: Database, results: list):
    if results:
        for anime in results:
            await _send_anime_card(message, db, anime, message.from_user.id)
    else:
        await message.answer("❌ Anime topilmadi!\n🔍 Boshqa nom yoki janr bilan urinib ko'ring.",
                              reply_markup=back_button())


async def _send_anime_episodes(message: Message, db: Database, anime_id: int):
    anime = db.search_anime_by_id(anime_id)
    if not anime:
        await message.answer("Bu anime topilmadi!"); return

    user = db.get_user(message.from_user.id)
    # VIP tekshirish
    if anime.get('is_vip') and user and user['status'] == 'Simple':
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="💎 Premium olish", callback_data="premium_info"))
        await message.answer(
            "💎 Bu anime faqat <b>Premium +</b> foydalanuvchilar uchun!",
            reply_markup=kb.as_markup(), parse_mode='HTML'); return

    # Early access tekshirish
    if anime.get('early_access') and user and user['status'] == 'Simple':
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="⚡ Early Access olish", callback_data="premium_info"))
        await message.answer(
            "⚡ Bu anime <b>Early Access</b> — faqat Premium foydalanuvchilar uchun!\n"
            "Hammaga uchun tez orada ochiladi.",
            reply_markup=kb.as_markup(), parse_mode='HTML'); return

    episodes = db.get_anime_episodes(anime_id)
    if not episodes:
        await message.answer("Bu animeda qismlar topilmadi!"); return

    db.increment_views(anime_id)
    progress = db.get_progress(message.from_user.id, anime_id)
    start_ep = progress['episode_number'] if progress else 1
    ep = next((e for e in episodes if e['episode_number'] == start_ep), episodes[0])

    if progress and progress['episode_number'] > 1:
        await message.answer(
            f"▶️ Davom etish: <b>{start_ep}-qismdan</b>",
            parse_mode='HTML')

    await _send_episode(message, db, anime_id, ep['episode_number'], message.from_user.id)


async def _send_episode(message: Message, db: Database, anime_id: int,
                         ep_number: int, user_id: int):
    anime = db.search_anime_by_id(anime_id)
    episodes = db.get_anime_episodes(anime_id)
    ep = next((e for e in episodes if e['episode_number'] == ep_number), None)
    if not ep:
        await message.answer("Bu qism topilmadi!"); return

    protect = db.get_setting('share') == 'true'
    caption = (
        f"🍿 <b>{anime['name']}</b>\n"
        f"✨───────────────✨\n"
        f"🎥 <b>Qism:</b> {ep['episode_number']} / {anime['episode']}\n"
        f"📜 <b>Til:</b> {anime['language']}"
    )
    kb = episode_keyboard(anime_id, ep['episode_number'], len(episodes))
    await message.answer_video(
        video=ep['file_id'], caption=caption, parse_mode='HTML',
        protect_content=protect, reply_markup=kb)
    db.save_progress(user_id, anime_id, ep_number)

    # Mission: episode ko'rish
    completed, reward = db.update_mission(user_id, 'watch_episode')
    if completed:
        await message.answer(f"🎉 Mission bajarildi: +{reward} 🪙")