import asyncio
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database import Database
from app.keyboards import (
    admin_panel_keyboard, anime_settings_keyboard, back_admin_button,
    channel_settings_keyboard, main_settings_keyboard,
    mandatory_channels_keyboard, send_message_keyboard,
    edit_anime_fields_keyboard, scheduled_posts_keyboard
)

router = Router()

class AddAnimeStates(StatesGroup):
    name=State(); episode=State(); country=State(); language=State()
    description=State(); genre=State(); image=State(); is_vip=State(); early_access=State()

class AddEpisodeStates(StatesGroup):
    anime_id=State(); file=State()

class EditAnimeStates(StatesGroup):
    select=State(); field=State(); value=State()

class DeleteAnimeState(StatesGroup):
    anime_id=State()

class AddChannelStates(StatesGroup):
    channel_id=State(); channel_link=State()

class AnimeChannelSetup(StatesGroup): value=State()
class StartTextSetup(StatesGroup):    value=State()
class HelpTextSetup(StatesGroup):     value=State()
class AdsTextSetup(StatesGroup):      value=State()
class PremiumPriceSetup(StatesGroup): value=State()
class ReferralBonusSetup(StatesGroup):value=State()
class ApiKeySetup(StatesGroup):       value=State()
class BroadcastStates(StatesGroup):   message=State()
class ForwardStates(StatesGroup):     message=State()
class UserMessageStates(StatesGroup): user_id=State(); message=State()
class SchedulePostStates(StatesGroup):anime_id=State(); datetime_str=State()


def register_admin_handlers(router: Router, db: Database, admin_id: int):

    def is_admin(uid): return uid == admin_id

    @router.message(Command("admin"))
    @router.message(Command("panel"))
    async def admin_panel(message: Message):
        if not is_admin(message.from_user.id):
            await message.answer("❌ Siz admin emassiz!"); return
        await message.answer("👨‍💼 Admin panel:", reply_markup=admin_panel_keyboard())

    @router.callback_query(F.data == "back_admin")
    async def back_admin(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await call.message.edit_text("👨‍💼 Admin panel:", reply_markup=admin_panel_keyboard())
        await call.answer()

    @router.callback_query(F.data == "anime_settings")
    async def anime_settings(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await call.message.edit_text("🎥 Anime sozlamlari:", reply_markup=anime_settings_keyboard())
        await call.answer()

    # ── Statistika ─────────────────────────────────────────────────────────────
    @router.callback_query(F.data == "stats")
    async def stats(call: CallbackQuery):
        s = db.get_stats()
        top = db.get_most_viewed_anime(3)
        top_text = "\n".join([f"  {i+1}. {a['name']} — {a['views']} ko'rish"
                               for i, a in enumerate(top)])
        ab = db.get_ab_stats()
        ab_text = f"\n🧪 A/B: A={ab['A']['total_users']} | B={ab['B']['total_users']}"
        await call.message.edit_text(
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Jami: <b>{s['total_users']}</b> | Bugun: <b>{s['today_users']}</b>\n"
            f"💎 Premium: <b>{s['premium_users']}</b>\n"
            f"🎥 Anime: <b>{s['total_anime']}</b> | Epizod: <b>{s['total_episodes']}</b>\n"
            f"👁 Ko'rishlar: <b>{s['total_views']}</b>\n"
            f"🎬 Clips: <b>{s['total_clips']}</b>\n\n"
            f"🏆 Eng ko'p ko'rilgan:\n{top_text}"
            f"{ab_text}",
            reply_markup=back_admin_button(), parse_mode='HTML')
        await call.answer()

    # ── Clips admin ────────────────────────────────────────────────────────────
    @router.callback_query(F.data == "clips_admin")
    async def clips_admin(call: CallbackQuery):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="➕ Clip qo'shish",    callback_data="add_clip"))
        kb.row(InlineKeyboardButton(text="🔙 Ortga",            callback_data="back_admin"))
        await call.message.edit_text("🎬 Clips boshqaruvi:", reply_markup=kb.as_markup())
        await call.answer()

    # ── API sozlamalar ─────────────────────────────────────────────────────────
    @router.callback_query(F.data == "api_settings")
    async def api_settings(call: CallbackQuery, state: FSMContext):
        if not is_admin(call.from_user.id): await call.answer("❌"); return
        current = db.get_setting('anthropic_api_key') or ''
        masked = current[:8] + "..." if len(current) > 8 else "Kiritilmagan"
        await state.set_state(ApiKeySetup.value)
        await call.message.edit_text(
            f"🔑 <b>Anthropic API Key</b>\n\n"
            f"Hozirgi: <code>{masked}</code>\n\n"
            f"Yangi API key kiriting (yoki /skip):\n\n"
            f"💡 API key olmish: <a href='https://console.anthropic.com'>console.anthropic.com</a>",
            reply_markup=back_admin_button(), parse_mode='HTML')
        await call.answer()

    @router.message(ApiKeySetup.value)
    async def handle_api_key(message: Message, state: FSMContext):
        if not is_admin(message.from_user.id): return
        if message.text != '/skip':
            db.update_setting('anthropic_api_key', message.text.strip())
            await message.answer("✅ API key saqlandi!", reply_markup=back_admin_button())
        else:
            await message.answer("⏭ O'tkazib yuborildi.", reply_markup=back_admin_button())
        await state.clear()

    # ══════════════════════════════════════════════════════════════════════════
    # ANIME QO'SHISH
    # ══════════════════════════════════════════════════════════════════════════
    @router.callback_query(F.data == "add_anime")
    async def add_anime_start(call: CallbackQuery, state: FSMContext):
        await state.clear(); await state.set_state(AddAnimeStates.name)
        await call.message.edit_text("🎥 Anime nomini kiriting:", reply_markup=back_admin_button())
        await call.answer()

    @router.message(AddAnimeStates.name)
    async def add_anime_name(message: Message, state: FSMContext):
        await state.update_data(name=message.text); await state.set_state(AddAnimeStates.episode)
        await message.answer("💀 Qismlar soni:", reply_markup=back_admin_button())

    @router.message(AddAnimeStates.episode)
    async def add_anime_episode(message: Message, state: FSMContext):
        try:
            await state.update_data(episode=int(message.text)); await state.set_state(AddAnimeStates.country)
            await message.answer("🌍 Davlat:", reply_markup=back_admin_button())
        except ValueError:
            await message.answer("❌ Faqat son!", reply_markup=back_admin_button())

    @router.message(AddAnimeStates.country)
    async def add_anime_country(message: Message, state: FSMContext):
        await state.update_data(country=message.text); await state.set_state(AddAnimeStates.language)
        await message.answer("🔦 Til:", reply_markup=back_admin_button())

    @router.message(AddAnimeStates.language)
    async def add_anime_language(message: Message, state: FSMContext):
        await state.update_data(language=message.text); await state.set_state(AddAnimeStates.description)
        await message.answer("📜 Tavsif:", reply_markup=back_admin_button())

    @router.message(AddAnimeStates.description)
    async def add_anime_description(message: Message, state: FSMContext):
        await state.update_data(description=message.text); await state.set_state(AddAnimeStates.genre)
        await message.answer("🎭 Janr:", reply_markup=back_admin_button())

    @router.message(AddAnimeStates.genre)
    async def add_anime_genre(message: Message, state: FSMContext):
        await state.update_data(genre=message.text); await state.set_state(AddAnimeStates.image)
        await message.answer("🖼 Rasmni yuboring:", reply_markup=back_admin_button())

    @router.message(AddAnimeStates.image, F.photo)
    async def add_anime_image(message: Message, state: FSMContext):
        await state.update_data(image=message.photo[-1].file_id)
        await state.set_state(AddAnimeStates.is_vip)
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="💎 Ha (VIP only)",   callback_data="anime_vip_yes"),
            InlineKeyboardButton(text="🆓 Yo'q (Hammaga)", callback_data="anime_vip_no")
        )
        await message.answer("💎 Bu anime VIP only bo'ladimi?", reply_markup=kb.as_markup())

    @router.callback_query(AddAnimeStates.is_vip, F.data.in_({"anime_vip_yes","anime_vip_no"}))
    async def add_anime_vip(call: CallbackQuery, state: FSMContext):
        await state.update_data(is_vip=1 if call.data=="anime_vip_yes" else 0)
        await state.set_state(AddAnimeStates.early_access)
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="⚡ Ha (Early Access)", callback_data="anime_ea_yes"),
            InlineKeyboardButton(text="🆓 Yo'q",             callback_data="anime_ea_no")
        )
        await call.message.edit_text("⚡ Early Access (faqat premium birinchi ko'radi)?",
                                      reply_markup=kb.as_markup()); await call.answer()

    @router.callback_query(AddAnimeStates.early_access, F.data.in_({"anime_ea_yes","anime_ea_no"}))
    async def add_anime_early(call: CallbackQuery, state: FSMContext):
        ea = 1 if call.data == "anime_ea_yes" else 0
        data = await state.get_data()
        try:
            anime_id = db.add_anime(
                data['name'], data['episode'], data['country'], data['language'],
                data['image'], data['description'], data['genre'], data['is_vip'], ea)
            await state.clear()
            tags = (" 💎 VIP" if data['is_vip'] else "") + (" ⚡ Early" if ea else "")
            await call.message.edit_text(
                f"✅ Anime{tags} qo'shildi!\n🆔 Kod: <code>{anime_id}</code>",
                parse_mode='HTML', reply_markup=back_admin_button())

            # Watchlist subscribers'ga xabar (agar shu janrda kuzatuvchilar bo'lsa)
        except Exception as e:
            await call.message.edit_text(f"❌ Xatolik: {e}", reply_markup=back_admin_button())
        await call.answer()

    @router.message(AddAnimeStates.image)
    async def add_anime_image_wrong(message: Message):
        await message.answer("❌ Faqat rasm yuboring!", reply_markup=back_admin_button())

    # ══════════════════════════════════════════════════════════════════════════
    # QISM QO'SHISH
    # ══════════════════════════════════════════════════════════════════════════
    @router.callback_query(F.data == "add_episode")
    async def add_episode_start(call: CallbackQuery, state: FSMContext):
        await state.clear(); await state.set_state(AddEpisodeStates.anime_id)
        await call.message.edit_text("🔢 Anime ID:", reply_markup=back_admin_button()); await call.answer()

    @router.message(AddEpisodeStates.anime_id)
    async def add_episode_id(message: Message, state: FSMContext):
        try:
            anime_id = int(message.text)
            anime = db.search_anime_by_id(anime_id)
            if anime:
                await state.update_data(anime_id=anime_id, anime_name=anime['name'])
                await state.set_state(AddEpisodeStates.file)
                await message.answer(f"🎥 {anime['name']} uchun videoni yuboring:", reply_markup=back_admin_button())
            else: await message.answer("❌ Topilmadi!", reply_markup=back_admin_button())
        except ValueError:
            await message.answer("❌ Faqat raqam!", reply_markup=back_admin_button())

    @router.message(AddEpisodeStates.file, F.video)
    async def add_episode_file(message: Message, state: FSMContext):
        data = await state.get_data(); anime_id = data['anime_id']
        try:
            episodes = db.get_anime_episodes(anime_id)
            ep_number = len(episodes) + 1
            db.add_episode(anime_id, ep_number, message.video.file_id)
            await message.answer(
                f"✅ {data['anime_name']} — {ep_number}-qism yuklandi!\n"
                "Keyingi videoni yuboring yoki 🔙 Ortga bosing",
                reply_markup=back_admin_button())
            asyncio.create_task(
                _notify_subscribers(message.bot, db, anime_id, ep_number, data['anime_name']))
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}", reply_markup=back_admin_button())

    @router.message(AddEpisodeStates.file)
    async def add_episode_wrong(message: Message):
        await message.answer("❌ Faqat video!", reply_markup=back_admin_button())

    # ══════════════════════════════════════════════════════════════════════════
    # ANIME TAHRIRLASH
    # ══════════════════════════════════════════════════════════════════════════
    @router.callback_query(F.data == "edit_anime")
    async def edit_anime_start(call: CallbackQuery, state: FSMContext):
        await state.clear(); await state.set_state(EditAnimeStates.select)
        await call.message.edit_text("✏️ Tahrirlamoqchi bo'lgan anime ID:", reply_markup=back_admin_button())
        await call.answer()

    @router.message(EditAnimeStates.select)
    async def edit_anime_select(message: Message, state: FSMContext):
        try:
            anime_id = int(message.text)
            anime = db.search_anime_by_id(anime_id)
            if anime:
                await state.update_data(edit_anime_id=anime_id)
                await state.set_state(EditAnimeStates.field)
                await message.answer(
                    f"✏️ <b>{anime['name']}</b> — qaysi maydon?",
                    reply_markup=edit_anime_fields_keyboard(), parse_mode='HTML')
            else: await message.answer("❌ Topilmadi!", reply_markup=back_admin_button())
        except ValueError:
            await message.answer("❌ Faqat raqam!", reply_markup=back_admin_button())

    @router.callback_query(EditAnimeStates.field, F.data.startswith("edit_field_"))
    async def edit_anime_field(call: CallbackQuery, state: FSMContext):
        field = call.data.replace("edit_field_","")
        await state.update_data(edit_field=field)
        await state.set_state(EditAnimeStates.value)
        names = {'name':'nomi','episode':'epizodlar soni','country':'davlati','language':'tili',
                 'description':'tavsifi','genre':'janri','image':'rasmi',
                 'is_vip':'VIP holati (0/1)','early_access':'Early Access (0/1)'}
        await call.message.edit_text(f"✏️ Yangi {names.get(field,field)}ni kiriting:",
                                      reply_markup=back_admin_button()); await call.answer()

    @router.message(EditAnimeStates.value, F.photo)
    async def edit_value_photo(message: Message, state: FSMContext):
        data = await state.get_data()
        if data.get('edit_field') == 'image':
            db.update_anime(data['edit_anime_id'], 'image', message.photo[-1].file_id)
            await state.clear()
            await message.answer("✅ Rasm yangilandi!", reply_markup=back_admin_button())
        else:
            await message.answer("❌ Matn kiriting!", reply_markup=back_admin_button())

    @router.message(EditAnimeStates.value, F.text)
    async def edit_value_text(message: Message, state: FSMContext):
        data = await state.get_data(); field = data['edit_field']; value = message.text
        try:
            if field in ('episode','is_vip','early_access'): value = int(value)
            db.update_anime(data['edit_anime_id'], field, value)
            await state.clear()
            await message.answer(f"✅ {field} yangilandi!", reply_markup=back_admin_button())
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}", reply_markup=back_admin_button())

    # ── List / Delete ──────────────────────────────────────────────────────────
    @router.callback_query(F.data == "list_anime")
    async def list_anime(call: CallbackQuery):
        anime_list = db.get_all_anime()
        if not anime_list:
            await call.message.edit_text("📭 Anime yo'q!", reply_markup=back_admin_button()); await call.answer(); return
        text = "📋 <b>Anime ro'yxati:</b>\n\n"
        for a in anime_list:
            tags = ("💎" if a.get('is_vip') else "") + ("⚡" if a.get('early_access') else "")
            text += f"🆔 {a['id']} — {a['name']} {tags} | {a['episode']}ep | ⭐{a['rating']} | 👁{a['views']}\n"
        if len(text) > 4000: text = text[:4000] + "\n..."
        await call.message.edit_text(text, reply_markup=back_admin_button(), parse_mode='HTML'); await call.answer()

    @router.callback_query(F.data == "delete_anime")
    async def delete_anime_start(call: CallbackQuery, state: FSMContext):
        await state.set_state(DeleteAnimeState.anime_id)
        await call.message.edit_text("🗑 O'chirmoqchi bo'lgan anime ID:", reply_markup=back_admin_button()); await call.answer()

    @router.message(DeleteAnimeState.anime_id)
    async def handle_delete_anime(message: Message, state: FSMContext):
        try:
            anime_id = int(message.text); anime = db.search_anime_by_id(anime_id)
            if anime:
                db.delete_anime(anime_id); await state.clear()
                await message.answer(f"✅ {anime['name']} o'chirildi!", reply_markup=back_admin_button())
            else: await message.answer("❌ Topilmadi!", reply_markup=back_admin_button())
        except ValueError:
            await message.answer("❌ Faqat raqam!", reply_markup=back_admin_button())

    # ══════════════════════════════════════════════════════════════════════════
    # POST TAYYORLASH
    # ══════════════════════════════════════════════════════════════════════════
    @router.callback_query(F.data == "create_post")
    async def create_post(call: CallbackQuery, state: FSMContext):
        await state.set_state(SchedulePostStates.anime_id)
        await call.message.edit_text("📺 Anime ID:", reply_markup=back_admin_button()); await call.answer()

    @router.message(SchedulePostStates.anime_id)
    async def schedule_post_id(message: Message, state: FSMContext):
        try:
            anime_id = int(message.text); anime = db.search_anime_by_id(anime_id)
            if not anime:
                await message.answer("❌ Topilmadi!", reply_markup=back_admin_button()); return
            await state.update_data(post_anime_id=anime_id)
            caption = _post_caption(anime)
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="🚀 Hozir yuborish",  callback_data=f"send_post_now_{anime_id}"))
            kb.row(InlineKeyboardButton(text="📅 Rejalashtirish",  callback_data=f"schedule_post_{anime_id}"))
            kb.row(InlineKeyboardButton(text="🔙 Ortga",           callback_data="back_admin"))
            await message.answer_photo(photo=anime['image'], caption=caption,
                                        parse_mode='Markdown', reply_markup=kb.as_markup())
            await state.clear()
        except ValueError:
            await message.answer("❌ Faqat raqam!", reply_markup=back_admin_button())

    @router.callback_query(F.data.startswith("send_post_now_"))
    async def send_post_now(call: CallbackQuery):
        await _send_to_channel(call, db, int(call.data.split("_")[-1]))

    @router.callback_query(F.data.startswith("schedule_post_"))
    async def schedule_post_cb(call: CallbackQuery, state: FSMContext):
        await state.update_data(post_anime_id=int(call.data.split("_")[-1]))
        await state.set_state(SchedulePostStates.datetime_str)
        await call.message.answer(
            "📅 Qachon yuborilsin?\n\nFormat: <code>2025-12-31 18:00</code>",
            reply_markup=back_admin_button(), parse_mode='HTML'); await call.answer()

    @router.message(SchedulePostStates.datetime_str)
    async def handle_schedule_dt(message: Message, state: FSMContext):
        try:
            dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
            data = await state.get_data()
            db.add_scheduled_post(data['post_anime_id'], db.get_setting('anime_channel'),
                                   dt.strftime("%Y-%m-%d %H:%M"))
            await state.clear()
            await message.answer(f"✅ Post rejalashtirildi!\n📅 <b>{dt.strftime('%Y-%m-%d %H:%M')}</b>",
                                  reply_markup=back_admin_button(), parse_mode='HTML')
        except ValueError:
            await message.answer("❌ Format xato! Misol: <code>2025-12-31 18:00</code>",
                                  reply_markup=back_admin_button(), parse_mode='HTML')

    @router.callback_query(F.data == "scheduled_posts")
    async def scheduled_posts(call: CallbackQuery):
        await call.message.edit_text("📅 Rejalashtirish:", reply_markup=scheduled_posts_keyboard()); await call.answer()

    @router.callback_query(F.data == "list_scheduled")
    async def list_scheduled(call: CallbackQuery):
        posts = db.get_all_scheduled_posts()
        if not posts:
            await call.message.edit_text("📭 Rejalashtirilgan post yo'q!", reply_markup=back_admin_button()); await call.answer(); return
        kb = InlineKeyboardBuilder()
        for p in posts:
            kb.row(InlineKeyboardButton(text=f"🗓 {p['scheduled_at']} — {p['name']}",
                                         callback_data=f"del_scheduled_{p['id']}"))
        kb.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="back_admin"))
        await call.message.edit_text("📋 Rejalashtirilgan (o'chirish uchun bosing):", reply_markup=kb.as_markup()); await call.answer()

    @router.callback_query(F.data.startswith("del_scheduled_"))
    async def del_scheduled(call: CallbackQuery):
        db.delete_scheduled_post(int(call.data.split("_")[-1]))
        await call.answer("✅ O'chirildi!")
        posts = db.get_all_scheduled_posts()
        if not posts:
            await call.message.edit_text("📭 Rejalashtirilgan post yo'q!", reply_markup=back_admin_button()); return
        kb = InlineKeyboardBuilder()
        for p in posts:
            kb.row(InlineKeyboardButton(text=f"🗓 {p['scheduled_at']} — {p['name']}",
                                         callback_data=f"del_scheduled_{p['id']}"))
        kb.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="back_admin"))
        await call.message.edit_reply_markup(reply_markup=kb.as_markup())

    @router.callback_query(F.data.startswith("send_post_"))
    async def send_post_legacy(call: CallbackQuery):
        if "now" in call.data or "schedule" in call.data: return
        await _send_to_channel(call, db, int(call.data.split('_')[-1]))

    # ══════════════════════════════════════════════════════════════════════════
    # KANALLAR
    # ══════════════════════════════════════════════════════════════════════════
    @router.callback_query(F.data == "channel_settings")
    async def channel_settings(call: CallbackQuery):
        await call.message.edit_text("📣 Kanallar:", reply_markup=channel_settings_keyboard()); await call.answer()

    @router.callback_query(F.data == "mandatory_subscriptions")
    async def mandatory_subscriptions(call: CallbackQuery):
        await call.message.edit_text("🔐 Majburiy obuna:", reply_markup=mandatory_channels_keyboard()); await call.answer()

    @router.callback_query(F.data == "add_channel")
    async def add_channel_start(call: CallbackQuery, state: FSMContext):
        await state.set_state(AddChannelStates.channel_id)
        await call.message.edit_text("Kanal ID (-100 qo'ymasdan):", reply_markup=back_admin_button()); await call.answer()

    @router.message(AddChannelStates.channel_id)
    async def add_channel_id(message: Message, state: FSMContext):
        await state.update_data(channel_id=message.text); await state.set_state(AddChannelStates.channel_link)
        await message.answer("Kanal havolasi (https://t.me bilan):", reply_markup=back_admin_button())

    @router.message(AddChannelStates.channel_link)
    async def add_channel_link(message: Message, state: FSMContext):
        data = await state.get_data()
        try:
            db.add_channel(data['channel_id'], message.text, 'request')
            await message.answer("✅ Kanal qo'shildi!", reply_markup=back_admin_button())
        except Exception as e:
            await message.answer(f"❌ Xatolik: {e}", reply_markup=back_admin_button())
        await state.clear()

    @router.callback_query(F.data == "list_channels")
    async def list_channels(call: CallbackQuery):
        channels = db.get_channels('request')
        if not channels:
            await call.message.edit_text("📭 Kanal yo'q!", reply_markup=back_admin_button()); await call.answer(); return
        text = "📃 Kanallar:\n\n" + "\n".join([f"{i+1}. <a href='{ch['channel_link']}'>Kanal</a>" for i,ch in enumerate(channels)])
        await call.message.edit_text(text, parse_mode='HTML', reply_markup=back_admin_button()); await call.answer()

    @router.callback_query(F.data == "delete_channel")
    async def delete_channel_menu(call: CallbackQuery):
        channels = db.get_channels('request')
        if not channels:
            await call.message.edit_text("📭 Kanal yo'q!", reply_markup=back_admin_button()); await call.answer(); return
        kb = InlineKeyboardBuilder()
        for i,ch in enumerate(channels):
            kb.row(InlineKeyboardButton(text=f"{i+1}. {ch['channel_link']}",
                                         callback_data=f"delete_channel_{ch['channel_id']}"))
        kb.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="back_admin"))
        await call.message.edit_text("🗑 O'chirish:", reply_markup=kb.as_markup()); await call.answer()

    @router.callback_query(F.data.startswith("delete_channel_"))
    async def delete_channel_confirm(call: CallbackQuery):
        db.delete_channel(call.data.replace("delete_channel_",""))
        await call.message.edit_text("✅ Kanal o'chirildi!", reply_markup=back_admin_button()); await call.answer()

    # ══════════════════════════════════════════════════════════════════════════
    # ASOSIY SOZLAMALAR
    # ══════════════════════════════════════════════════════════════════════════
    @router.callback_query(F.data == "main_settings")
    async def main_settings(call: CallbackQuery):
        await call.message.edit_text("⚙️ Asosiy sozlamalar:", reply_markup=main_settings_keyboard(db)); await call.answer()

    @router.callback_query(F.data == "toggle_share")
    async def toggle_share(call: CallbackQuery):
        s = db.get_setting('share'); new_s = 'true' if s=='false' else 'false'
        db.update_setting('share', new_s)
        await call.message.edit_text(f"✅ Uzatish {'yoqildi' if new_s=='true' else 'ochirildi'}!",
                                      reply_markup=main_settings_keyboard(db)); await call.answer()

    @router.callback_query(F.data == "bot_situation_setup")
    async def bot_situation_setup(call: CallbackQuery):
        sit = db.get_setting('situation')
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text="O'chirish ❌" if sit=='On' else "Yoqish ✅",
            callback_data="toggle_bot_situation"))
        kb.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="back_admin"))
        await call.message.edit_text(
            f"🤖 Bot holati: {'Yoqilgan ✅' if sit=='On' else 'Ochirilgan ❌'}",
            reply_markup=kb.as_markup()); await call.answer()

    @router.callback_query(F.data == "toggle_bot_situation")
    async def toggle_bot_situation(call: CallbackQuery):
        sit = db.get_setting('situation'); new_sit = 'Off' if sit=='On' else 'On'
        db.update_setting('situation', new_sit)
        await call.message.edit_text(
            f"✅ Bot {'ochirildi' if new_sit=='Off' else 'yoqildi'}!",
            reply_markup=back_admin_button()); await call.answer()

    for setup_key, cb_data, state_class, label in [
        ('anime_channel', 'anime_channel_setup', AnimeChannelSetup, 'Anime kanal'),
        ('start_text',    'start_text_setup',    StartTextSetup,    'Start matni'),
        ('help_text',     'help_text_setup',      HelpTextSetup,     'Yordam matni'),
        ('ads_text',      'ads_text_setup',        AdsTextSetup,      'Reklama matni'),
        ('premium_price', 'premium_price_setup',  PremiumPriceSetup, 'Premium narx (UZS)'),
        ('referral_bonus','referral_bonus_setup',  ReferralBonusSetup,'Referral bonus (UZS)'),
    ]:
        def make_handlers(key, cb, sc, lbl):
            @router.callback_query(F.data == cb)
            async def _setup(call: CallbackQuery, state: FSMContext, sc=sc, _key=key, _lbl=lbl):
                await state.set_state(sc.value)
                await call.message.edit_text(
                    f"📝 Hozirgi {_lbl}:\n{db.get_setting(_key)}\n\nYangisini kiriting:",
                    reply_markup=back_admin_button()); await call.answer()

            @router.message(sc.value)
            async def _handle(message: Message, state: FSMContext, _key=key, _lbl=lbl):
                db.update_setting(_key, message.text)
                await state.clear()
                await message.answer(f"✅ {_lbl} yangilandi!", reply_markup=back_admin_button())

        make_handlers(setup_key, cb_data, state_class, label)

    # ══════════════════════════════════════════════════════════════════════════
    # XABAR YUBORISH
    # ══════════════════════════════════════════════════════════════════════════
    @router.callback_query(F.data == "send_message")
    async def send_message_menu(call: CallbackQuery):
        await call.message.edit_text("✉️ Xabar yuborish:", reply_markup=send_message_keyboard()); await call.answer()

    @router.callback_query(F.data == "broadcast_message")
    async def broadcast_start(call: CallbackQuery, state: FSMContext):
        await state.set_state(BroadcastStates.message)
        await call.message.edit_text("Hamma userlarga xabar:", reply_markup=back_admin_button()); await call.answer()

    @router.message(BroadcastStates.message)
    async def handle_broadcast(message: Message, state: FSMContext):
        await state.clear()
        users = db.get_all_users(); total = len(users); sent = 0
        status_msg = await message.answer(f"Yuborish boshlandi: 0/{total}")
        for uid in users:
            try:
                await message.bot.send_message(uid, message.text, parse_mode='HTML')
                sent += 1
                if sent % 10 == 0: await status_msg.edit_text(f"Yuborildi: {sent}/{total}")
                await asyncio.sleep(0.05)
            except: continue
        await status_msg.edit_text(f"✅ Yakunlandi: {sent}/{total}")

    @router.callback_query(F.data == "forward_message")
    async def forward_start(call: CallbackQuery, state: FSMContext):
        await state.set_state(ForwardStates.message)
        await call.message.edit_text("Forward xabarni yuboring:", reply_markup=back_admin_button()); await call.answer()

    @router.message(ForwardStates.message)
    async def handle_forward(message: Message, state: FSMContext):
        await state.clear()
        users = db.get_all_users(); total = len(users); sent = 0
        status_msg = await message.answer(f"Forward boshlandi: 0/{total}")
        for uid in users:
            try:
                await message.bot.forward_message(uid, message.chat.id, message.message_id)
                sent += 1
                if sent % 10 == 0: await status_msg.edit_text(f"Yuborildi: {sent}/{total}")
                await asyncio.sleep(0.05)
            except: continue
        await status_msg.edit_text(f"✅ Yakunlandi: {sent}/{total}")

    @router.callback_query(F.data == "user_message")
    async def user_msg_start(call: CallbackQuery, state: FSMContext):
        await state.set_state(UserMessageStates.user_id)
        await call.message.edit_text("Foydalanuvchi ID:", reply_markup=back_admin_button()); await call.answer()

    @router.message(UserMessageStates.user_id)
    async def handle_user_id(message: Message, state: FSMContext):
        try:
            await state.update_data(target_user_id=int(message.text))
            await state.set_state(UserMessageStates.message)
            await message.answer("Xabarni kiriting:", reply_markup=back_admin_button())
        except ValueError:
            await message.answer("❌ Faqat raqam!", reply_markup=back_admin_button())

    @router.message(UserMessageStates.message)
    async def handle_send_to_user(message: Message, state: FSMContext):
        data = await state.get_data(); await state.clear()
        try:
            await message.bot.send_message(data['target_user_id'], message.text, parse_mode='HTML')
            await message.answer("✅ Yuborildi!")
        except Exception as e:
            await message.answer(f"❌ Xato: {e}")


# ── Helpers ────────────────────────────────────────────────────────────────────
def _post_caption(anime: dict) -> str:
    tags = ("💎" if anime.get('is_vip') else "") + ("⚡" if anime.get('early_access') else "")
    return (
        f"📺 *{anime['name']}* {tags}\n"
        f"┏━━━━━━━━━━━━━━━┓\n"
        f"┃ 🎞 *Qismlar:* {anime['episode']}\n"
        f"┃ 🌍 *Davlat:* {anime.get('country','')}\n"
        f"┃ 🗣 *Til:* {anime.get('language','')}\n"
        f"┃ 🔖 *Janr:* {anime['genre']}\n"
        f"┃ ⭐ *Reyting:* {anime['rating']}\n"
        f"┗━━━━━━━━━━━━━━━┛\n"
        f"📌 *Tavsif:* {anime['description']}"
    )


async def _send_to_channel(call: CallbackQuery, db: Database, anime_id: int):
    anime = db.search_anime_by_id(anime_id)
    if not anime: await call.answer("Anime topilmadi!", show_alert=True); return
    channel = db.get_setting('anime_channel')
    bot_me = await call.bot.get_me()
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔷 Tomosha qilish 🔷",
                                 url=f"https://t.me/{bot_me.username}?start={anime_id}"))
    try:
        await call.bot.send_photo(channel, anime['image'],
                                   caption=_post_caption(anime), parse_mode='Markdown',
                                   reply_markup=kb.as_markup())
        await call.message.edit_text("✅ Post kanalga yuborildi!", reply_markup=back_admin_button())
    except Exception as e:
        await call.message.edit_text(f"❌ Xatolik: {e}", reply_markup=back_admin_button())
    await call.answer()


async def _notify_subscribers(bot, db: Database, anime_id: int, ep_number: int, anime_name: str):
    subscribers = db.get_watchlist_subscribers(anime_id)
    bot_me = await bot.get_me()
    for uid in subscribers:
        try:
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="▶️ Ko'rish",
                                         url=f"https://t.me/{bot_me.username}?start={anime_id}"))
            await bot.send_message(uid,
                f"🔔 <b>{anime_name}</b> — yangi qism!\n📀 <b>{ep_number}-qism</b> qo'shildi!",
                reply_markup=kb.as_markup(), parse_mode='HTML')
            await asyncio.sleep(0.05)
        except: continue