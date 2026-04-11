import os
from datetime import datetime
from urllib.parse import quote

import discord
import requests
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
LOSTARK_API_KEY = os.getenv("LOSTARK_API_KEY")
LOG_CHANNEL_ID_RAW = os.getenv("LOG_CHANNEL_ID", "")

if not TOKEN:
    raise ValueError("TOKEN 환경변수가 설정되지 않았습니다.")

try:
    LOG_CHANNEL_ID = int(LOG_CHANNEL_ID_RAW) if LOG_CHANNEL_ID_RAW else None
except ValueError:
    LOG_CHANNEL_ID = None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

servers = [
    "루페온",
    "아브렐슈드",
    "카단",
    "카제로스",
    "실리안",
    "아만",
    "카마인",
    "니나브",
]

classes = [
    "버서커", "디스트로이어", "워로드", "홀리나이트", "슬레이어",
    "배틀마스터", "인파이터", "기공사", "창술사", "스트라이커", "브레이커",
    "데빌헌터", "블래스터", "호크아이", "스카우터", "건슬링어",
    "바드", "서머너", "아르카나", "소서리스",
    "데모닉", "블레이드", "리퍼", "소울이터",
    "도화가", "기상술사", "환수사",
]

BASE_URL = "https://developer-lostark.game.onstove.com"
API_HEADERS = {
    "accept": "application/json",
    "authorization": f"Bearer {LOSTARK_API_KEY}" if LOSTARK_API_KEY else "",
}


async def write_log(
    guild: discord.Guild,
    user: discord.Member,
    char_name: str,
    server: str,
    job: str,
    mode: str,
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
    embed.add_field(name="캐릭터", value=char_name, inline=True)
    embed.add_field(name="서버", value=server, inline=True)
    embed.add_field(name="직업", value=job, inline=True)
    embed.add_field(name="인증방식", value=mode, inline=False)

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


def get_lostark_profile(character_name: str) -> tuple[str | None, str | None]:
    """
    로아 API로 서버/직업 조회
    성공하면 (server_name, class_name)
    실패하면 (None, None)
    """
    if not LOSTARK_API_KEY:
        return None, None

    encoded_name = quote(character_name.strip())
    server_name = None
    class_name = None

    # 1) siblings 조회
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
                    server_name = target.get("ServerName")
                    class_name = target.get("ClassName")
    except Exception:
        pass

    # 2) profiles 조회로 직업 보완
    if not class_name:
        try:
            profile_url = f"{BASE_URL}/armories/characters/{encoded_name}/profiles"
            res = requests.get(profile_url, headers=API_HEADERS, timeout=10)

            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    class_name = data.get("CharacterClassName") or class_name
                    server_name = data.get("ServerName") or server_name
        except Exception:
            pass

    return server_name, class_name


async def process_auth(
    interaction: discord.Interaction,
    char_name: str,
    server: str,
    job: str,
    mode: str,
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

    try:
        await user.add_roles(auth_role, server_role, job_role)
    except discord.Forbidden:
        await interaction.followup.send("❌ 역할 지급 실패 (봇 권한 / 역할 위치 확인)", ephemeral=True)
        return

    nick_ok = True
    try:
        await user.edit(nick=char_name)
    except discord.Forbidden:
        nick_ok = False

    await write_log(guild, user, char_name, server, job, mode)

    await interaction.followup.send(
        f"✅ 인증 완료!\n"
        f"캐릭터: {char_name}\n"
        f"서버: {server}\n"
        f"직업: {job}\n"
        f"닉네임 변경: {'성공' if nick_ok else '실패'}\n"
        f"인증방식: {mode}",
        ephemeral=True,
    )


class JobSelect(discord.ui.Select):
    def __init__(self, char_name: str, server: str):
        self.char_name = char_name
        self.server = server

        options = [discord.SelectOption(label=c) for c in classes[:25]]
        super().__init__(placeholder="직업 선택", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await process_auth(
            interaction,
            self.char_name,
            self.server,
            self.values[0],
            mode="수동 선택",
        )


class ExtraJobSelect(discord.ui.Select):
    def __init__(self, char_name: str, server: str):
        self.char_name = char_name
        self.server = server

        extra = classes[25:]
        options = [discord.SelectOption(label=c) for c in extra]
        super().__init__(placeholder="나머지 직업 선택", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await process_auth(
            interaction,
            self.char_name,
            self.server,
            self.values[0],
            mode="수동 선택",
        )


class JobView(discord.ui.View):
    def __init__(self, char_name: str, server: str):
        super().__init__(timeout=300)
        self.add_item(JobSelect(char_name, server))
        if len(classes) > 25:
            self.add_item(ExtraJobSelect(char_name, server))


class ServerSelect(discord.ui.Select):
    def __init__(self, char_name: str):
        self.char_name = char_name

        options = [discord.SelectOption(label=s) for s in servers]
        super().__init__(placeholder="서버 선택", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "직업을 선택해주세요",
            view=JobView(self.char_name, self.values[0]),
            ephemeral=True,
        )


class ServerView(discord.ui.View):
    def __init__(self, char_name: str):
        super().__init__(timeout=300)
        self.add_item(ServerSelect(char_name))


class NameModal(discord.ui.Modal, title="캐릭터 이름 입력"):
    name = discord.ui.TextInput(label="캐릭터 이름", placeholder="예: 만개초")

    async def on_submit(self, interaction: discord.Interaction):
        char_name = str(self.name.value).strip()

        if not char_name:
            await interaction.response.send_message("❌ 캐릭터 이름을 입력해주세요.", ephemeral=True)
            return

        # 로아 API 자동 조회
        server_name, class_name = get_lostark_profile(char_name)

        # 자동 인증 성공
        if server_name and class_name:
            await interaction.response.defer(ephemeral=True)
            await process_auth(
                interaction,
                char_name,
                server_name,
                class_name,
                mode="로아 API 자동 조회",
            )
            return

        # 자동 실패 → 수동 선택
        await interaction.response.send_message(
            "⚠️ 로아 API 자동 조회에 실패했습니다.\n서버를 직접 선택해주세요.",
            view=ServerView(char_name),
            ephemeral=True,
        )


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


bot.run(TOKEN)
