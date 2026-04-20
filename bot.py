import os
import threading
import time
from datetime import datetime
from urllib.parse import quote

import discord
import requests
from flask import Flask
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
LOSTARK_API_KEY = os.getenv("LOSTARK_API_KEY")
LOG_CHANNEL_ID_RAW = os.getenv("LOG_CHANNEL_ID", "")
PORT = int(os.getenv("PORT", "10000"))

if not TOKEN:
    raise ValueError("TOKEN 환경변수가 설정되지 않았습니다.")

if not LOSTARK_API_KEY:
    raise ValueError("LOSTARK_API_KEY 환경변수가 설정되지 않았습니다.")

try:
    LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_RAW) if LOG_CHANNEL_ID_RAW else None
except ValueError:
    LOG_CHANNEL_ID = None

UNVERIFIED_ROLE_NAME = "미인증"
VERIFIED_ROLE_NAME = "인증됨"

# ---------------------------
# Render Web Service용 Flask
# ---------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running", 200

def run_web():
    app.run(host="0.0.0.0", port=PORT)

def keep_alive():
    thread = threading.Thread(target=run_web)
    thread.daemon = True
    thread.start()

# ---------------------------
# Discord 설정
# ---------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

BASE_URL = "https://developer-lostark.game.onstove.com"
API_HEADERS = {
    "accept": "application/json",
    "authorization": f"Bearer {LOSTARK_API_KEY}",
}

SERVER_NAMES = [
    "루페온",
    "아브렐슈드",
    "카단",
    "카제로스",
    "실리안",
    "아만",
    "카마인",
    "니나브",
]

CLASS_NAMES = [
    "버서커",
    "디스트로이어",
    "워로드",
    "홀리나이트",
    "슬레이어",
    "배틀마스터",
    "인파이터",
    "기공사",
    "창술사",
    "스트라이커",
    "브레이커",
    "데빌헌터",
    "블래스터",
    "호크아이",
    "스카우터",
    "건슬링어",
    "바드",
    "서머너",
    "아르카나",
    "소서리스",
    "데모닉",
    "블레이드",
    "리퍼",
    "소울이터",
    "도화가",
    "기상술사",
    "환수사",
]

# 같은 유저 연속 클릭 방지
active_auth_users: set[int] = set()

# ---------------------------
# 로그 함수
# ---------------------------
async def write_log(
    guild: discord.Guild,
    user: discord.Member,
    char_name: str,
    server: str,
    job: str,
    removed_roles: list[str],
) -> None:
    if not LOG_CHANNEL_ID:
        return

    channel = guild.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(
        title="인증 로그",
        color=discord.Color.green(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="유저", value=f"{user} ({user.id})", inline=False)
    embed.add_field(name="태그", value=user.mention, inline=False)
    embed.add_field(name="캐릭터", value=char_name, inline=True)
    embed.add_field(name="서버", value=server, inline=True)
    embed.add_field(name="직업", value=job, inline=True)

    if removed_roles:
        embed.add_field(
            name="재인증으로 제거된 역할",
            value=", ".join(removed_roles),
            inline=False,
        )

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass

# ---------------------------
# 역할 찾기/생성
# ---------------------------
async def get_or_create_role(guild: discord.Guild, role_name: str) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name=role_name)
    if role:
        return role

    try:
        return await guild.create_role(name=role_name)
    except discord.Forbidden:
        return None

# ---------------------------
# 로아 API 조회
# ---------------------------
def get_lostark_profile(character_name: str) -> tuple[str | None, str | None, str | None]:
    encoded_name = quote(character_name.strip())
    found_char_name = None
    server_name = None
    class_name = None

    try:
        res = requests.get(
            f"{BASE_URL}/characters/{encoded_name}/siblings",
            headers=API_HEADERS,
            timeout=10,
        )

        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and data:
                target = None

                for c in data:
                    api_name = str(c.get("CharacterName", "")).strip().lower()
                    if api_name == character_name.strip().lower():
                        target = c
                        break

                if target is None:
                    target = data[0]

                found_char_name = target.get("CharacterName")
                server_name = target.get("ServerName")
                class_name = target.get("ClassName")
    except Exception:
        pass

    try:
        res = requests.get(
            f"{BASE_URL}/armories/characters/{encoded_name}/profiles",
            headers=API_HEADERS,
            timeout=10,
        )

        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                server_name = data.get("ServerName") or server_name
                class_name = data.get("CharacterClassName") or class_name
    except Exception:
        pass

    if not found_char_name:
        found_char_name = character_name

    if not server_name or not class_name:
        return None, None, None

    return found_char_name, server_name, class_name

# ---------------------------
# 인증 처리
# ---------------------------
async def process_auth(
    interaction: discord.Interaction,
    char_name: str,
    server: str,
    job: str,
) -> None:
    guild = interaction.guild
    user = interaction.user

    if guild is None or not isinstance(user, discord.Member):
        await interaction.followup.send("❌ 서버 안에서만 사용할 수 있습니다.", ephemeral=True)
        return

    auth_role = await get_or_create_role(guild, VERIFIED_ROLE_NAME)
    unverified_role = await get_or_create_role(guild, UNVERIFIED_ROLE_NAME)
    server_role = await get_or_create_role(guild, server)
    job_role = await get_or_create_role(guild, job)

    if not auth_role or not unverified_role or not server_role or not job_role:
        await interaction.followup.send(
            "❌ 역할 생성 또는 조회에 실패했습니다. 봇 권한을 확인해주세요.",
            ephemeral=True,
        )
        return

    removed_role_names: list[str] = []
    roles_to_remove: list[discord.Role] = []

    # 기존 서버/직업 역할 중 다른 것만 제거
    for role in user.roles:
        if role.name in SERVER_NAMES and role.name != server:
            roles_to_remove.append(role)
            removed_role_names.append(role.name)

        if role.name in CLASS_NAMES and role.name != job:
            roles_to_remove.append(role)
            removed_role_names.append(role.name)

    # 인증되면 미인증 제거
    if unverified_role in user.roles:
        roles_to_remove.append(unverified_role)
        removed_role_names.append(unverified_role.name)

    # 중복 제거
    unique_remove_roles = []
    seen_remove_ids = set()
    for role in roles_to_remove:
        if role.id not in seen_remove_ids:
            unique_remove_roles.append(role)
            seen_remove_ids.add(role.id)

    try:
        if unique_remove_roles:
            await user.remove_roles(*unique_remove_roles, reason="인증/재인증으로 역할 갱신")
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ 기존 역할 제거 실패 (봇 권한 / 역할 위치 확인)",
            ephemeral=True,
        )
        return

    # 이미 가진 역할은 다시 추가하지 않음
    roles_to_add = []
    current_role_ids = {role.id for role in user.roles}

    for role in (auth_role, server_role, job_role):
        if role.id not in current_role_ids:
            roles_to_add.append(role)

    try:
        if roles_to_add:
            await user.add_roles(*roles_to_add, reason="로아 자동 인증")
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ 역할 지급 실패 (봇 권한 / 역할 위치 확인)",
            ephemeral=True,
        )
        return

    # 닉네임이 다를 때만 변경
    nick_ok = True
    try:
        if user.nick != char_name:
            await user.edit(nick=char_name, reason="로아 자동 인증 닉네임 변경")
    except discord.Forbidden:
        nick_ok = False

    await write_log(guild, user, char_name, server, job, removed_role_names)

    removed_text = ", ".join(removed_role_names) if removed_role_names else "없음"

    await interaction.followup.send(
        f"✅ 인증 완료!\n"
        f"캐릭터: {char_name}\n"
        f"서버: {server}\n"
        f"직업: {job}\n"
        f"닉네임 변경: {'성공' if nick_ok else '실패'}\n"
        f"제거된 이전 역할: {removed_text}",
        ephemeral=True,
    )

# ---------------------------
# 신규 입장 시 미인증 역할 부여
# ---------------------------
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    unverified_role = await get_or_create_role(guild, UNVERIFIED_ROLE_NAME)

    if not unverified_role:
        return

    if unverified_role in member.roles:
        return

    try:
        await member.add_roles(unverified_role, reason="신규 입장자 미인증 역할 부여")
    except discord.Forbidden:
        pass

# ---------------------------
# 모달
# ---------------------------
class NameModal(discord.ui.Modal, title="캐릭터 이름 입력"):
    name = discord.ui.TextInput(label="캐릭터 이름", placeholder="예: 만개초")

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        if user_id in active_auth_users:
            await interaction.response.send_message(
                "⚠️ 이미 인증 처리 중입니다. 잠시 후 다시 시도해주세요.",
                ephemeral=True,
            )
            return

        input_name = str(self.name.value).strip()

        if not input_name:
            await interaction.response.send_message(
                "❌ 캐릭터 이름을 입력해주세요.",
                ephemeral=True,
            )
            return

        active_auth_users.add(user_id)

        try:
            await interaction.response.defer(thinking=True, ephemeral=True)

            char_name, server_name, class_name = get_lostark_profile(input_name)

            if not server_name or not class_name:
                await interaction.followup.send(
                    "❌ 서버 또는 직업 정보를 가져올 수 없어 인증에 실패했습니다.",
                    ephemeral=True,
                )
                return

            await process_auth(interaction, char_name, server_name, class_name)

        finally:
            active_auth_users.discard(user_id)

# ---------------------------
# Persistent View
# ---------------------------
class AuthView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="인증하기",
        style=discord.ButtonStyle.green,
        custom_id="auth_button"
    )
    async def button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in active_auth_users:
            await interaction.response.send_message(
                "⚠️ 이미 인증 처리 중입니다. 잠시 후 다시 시도해주세요.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(NameModal())

# ---------------------------
# 명령어 / 이벤트
# ---------------------------
@bot.command()
@commands.cooldown(1, 15, commands.BucketType.user)
async def 인증(ctx: commands.Context):
    await ctx.send("버튼을 눌러 인증하세요.", view=AuthView())

@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def 테스트(ctx: commands.Context):
    await ctx.send("✅ 테스트 성공 (명령어 작동 중)")

@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ 잠시 후 다시 시도해주세요. ({error.retry_after:.1f}초)")
        return

    print(f"명령어 오류: {error}")

@bot.event
async def on_ready():
    bot.add_view(AuthView())
    print(f"로그인됨: {bot.user}")

# ---------------------------
# 실행
# ---------------------------
keep_alive()
bot.run(TOKEN)
