import os
import threading
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

# Flask 서버
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

# Discord 설정
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
    "루페온", "아브렐슈드", "카단", "카제로스",
    "실리안", "아만", "카마인", "니나브"
]

CLASS_NAMES = [
    "버서커", "디스트로이어", "워로드", "홀리나이트", "슬레이어",
    "배틀마스터", "인파이터", "기공사", "창술사", "스트라이커", "브레이커",
    "데빌헌터", "블래스터", "호크아이", "스카우터", "건슬링어",
    "바드", "서머너", "아르카나", "소서리스",
    "데모닉", "블레이드", "리퍼", "소울이터",
    "도화가", "기상술사", "환수사"
]

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
    embed.add_field(name="인증방식", value="로아 API 자동 조회", inline=False)

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

def get_lostark_profile(character_name: str) -> tuple[str | None, str | None, str | None]:
    encoded_name = quote(character_name.strip())
    found_char_name = None
    server_name = None
    class_name = None

    try:
        siblings_url = f"{BASE_URL}/characters/{encoded_name}/siblings"
        res = requests.get(siblings_url, headers=API_HEADERS, timeout=10)

        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                target = None

                for c in data:
                    api_name = str(c.get("CharacterName", "")).strip().lower()
                    if api_name == character_name.strip().lower():
                        target = c
                        break

                if target is None and len(data) > 0:
                    target = data[0]

                if target:
                    found_char_name = target.get("CharacterName")
                    server_name = target.get("ServerName")
                    class_name = target.get("ClassName")
    except Exception:
        pass

    try:
        profile_url = f"{BASE_URL}/armories/characters/{encoded_name}/profiles"
        res = requests.get(profile_url, headers=API_HEADERS, timeout=10)

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

    auth_role = discord.utils.get(guild.roles, name="인증됨")
    if not auth_role:
        auth_role = await guild.create_role(name="인증됨")

    server_role = discord.utils.get(guild.roles, name=server)
    if not server_role:
        server_role = await guild.create_role(name=server)

    job_role = discord.utils.get(guild.roles, name=job)
    if not job_role:
        job_role = await guild.create_role(name=job)

    # 재인증 시 기존 서버/직업 역할 제거
    removed_role_names = []
    roles_to_remove = []

    for role in user.roles:
        if role.name in SERVER_NAMES and role.name != server:
            roles_to_remove.append(role)
            removed_role_names.append(role.name)

        if role.name in CLASS_NAMES and role.name != job:
            roles_to_remove.append(role)
            removed_role_names.append(role.name)

    try:
        if roles_to_remove:
            await user.remove_roles(*roles_to_remove, reason="재인증으로 서버/직업 역할 갱신")
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ 기존 역할 제거 실패 (봇 권한 / 역할 위치 확인)",
            ephemeral=True,
        )
        return

    try:
        await user.add_roles(auth_role, server_role, job_role, reason="로아 자동 인증")
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ 역할 지급 실패 (봇 권한 / 역할 위치 확인)",
            ephemeral=True,
        )
        return

    nick_ok = True
    try:
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

class NameModal(discord.ui.Modal, title="캐릭터 이름 입력"):
    name = discord.ui.TextInput(label="캐릭터 이름", placeholder="예: 만개초")

    async def on_submit(self, interaction: discord.Interaction):
        input_name = str(self.name.value).strip()

        if not input_name:
            await interaction.response.send_message(
                "❌ 캐릭터 이름을 입력해주세요.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        char_name, server_name, class_name = get_lostark_profile(input_name)

        if not server_name or not class_name:
            await interaction.followup.send(
                "❌ 서버 또는 직업 정보를 가져올 수 없어 인증에 실패했습니다.",
                ephemeral=True,
            )
            return

        await process_auth(interaction, char_name, server_name, class_name)

class AuthView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="인증하기", style=discord.ButtonStyle.green)
    async def button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NameModal())

@bot.event
async def on_ready():
    print(f"로그인됨: {bot.user}")

@bot.command()
async def 인증(ctx):
    await ctx.send("버튼을 눌러 인증하세요", view=AuthView())

keep_alive()
bot.run(TOKEN)
