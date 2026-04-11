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

# 🔥 Flask 서버 (Render용)
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

# 🔥 Discord 설정
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
    "버서커","디스트로이어","워로드","홀리나이트","슬레이어",
    "배틀마스터","인파이터","기공사","창술사","스트라이커","브레이커",
    "데빌헌터","블래스터","호크아이","스카우터","건슬링어",
    "바드","서머너","아르카나","소서리스",
    "데모닉","블레이드","리퍼","소울이터",
    "도화가","기상술사","환수사"
]

# 🔥 로그 함수 (인증방식 제거됨)
async def write_log(guild, user, char_name, server, job, removed_roles):
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
    except:
        pass

# 🔥 로아 API
def get_lostark_profile(character_name):
    encoded_name = quote(character_name.strip())
    found_char_name = None
    server_name = None
    class_name = None

    try:
        res = requests.get(
            f"{BASE_URL}/characters/{encoded_name}/siblings",
            headers=API_HEADERS,
            timeout=10
        )

        if res.status_code == 200:
            data = res.json()
            if data:
                target = data[0]
                found_char_name = target.get("CharacterName")
                server_name = target.get("ServerName")
                class_name = target.get("ClassName")
    except:
        pass

    try:
        res = requests.get(
            f"{BASE_URL}/armories/characters/{encoded_name}/profiles",
            headers=API_HEADERS,
            timeout=10
        )

        if res.status_code == 200:
            data = res.json()
            server_name = data.get("ServerName") or server_name
            class_name = data.get("CharacterClassName") or class_name
    except:
        pass

    if not found_char_name:
        found_char_name = character_name

    if not server_name or not class_name:
        return None, None, None

    return found_char_name, server_name, class_name

# 🔥 인증 처리
async def process_auth(interaction, char_name, server, job):
    guild = interaction.guild
    user = interaction.user

    auth_role = discord.utils.get(guild.roles, name="인증됨") or await guild.create_role(name="인증됨")
    server_role = discord.utils.get(guild.roles, name=server) or await guild.create_role(name=server)
    job_role = discord.utils.get(guild.roles, name=job) or await guild.create_role(name=job)

    # 기존 역할 제거
    removed = []
    remove_list = []

    for role in user.roles:
        if role.name in SERVER_NAMES and role.name != server:
            remove_list.append(role)
            removed.append(role.name)
        if role.name in CLASS_NAMES and role.name != job:
            remove_list.append(role)
            removed.append(role.name)

    if remove_list:
        await user.remove_roles(*remove_list)

    await user.add_roles(auth_role, server_role, job_role)

    try:
        await user.edit(nick=char_name)
    except:
        pass

    await write_log(guild, user, char_name, server, job, removed)

    await interaction.followup.send(
        f"✅ 인증 완료!\n서버: {server}\n직업: {job}",
        ephemeral=True
    )

# 🔥 UI
class NameModal(discord.ui.Modal, title="캐릭터 이름 입력"):
    name = discord.ui.TextInput(label="캐릭터 이름")

    async def on_submit(self, interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        char, server, job = get_lostark_profile(self.name.value)

        if not server or not job:
            await interaction.followup.send("❌ 인증 실패 (캐릭터 확인)", ephemeral=True)
            return

        await process_auth(interaction, char, server, job)

class AuthView(discord.ui.View):
    @discord.ui.button(label="인증하기", style=discord.ButtonStyle.green)
    async def button(self, interaction, button):
        await interaction.response.send_modal(NameModal())

@bot.command()
async def 인증(ctx):
    await ctx.send("버튼을 눌러 인증하세요", view=AuthView())

@bot.event
async def on_ready():
    print(f"로그인됨: {bot.user}")

keep_alive()
bot.run(TOKEN)
