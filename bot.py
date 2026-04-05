import os
import requests
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from urllib.parse import quote
from keep_alive import keep_alive

LOG_CHANNEL_ID = 1485629887673929949

LOSTARK_API_TOKEN = os.environ["LOSTARK_API_TOKEN"]
LOSTARK_API_BASE = "https://developer-lostark.game.onstove.com"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

servers = [
    "루페온", "아브렐슈드", "카단", "카제로스",
    "실리안", "아만", "카마인", "니나브"
]

classes = [
    "버서커", "디스트로이어", "워로드", "홀리나이트",
    "배틀마스터", "인파이터", "기공사", "창술사", "스트라이커",
    "데빌헌터", "블래스터", "호크아이", "스카우터",
    "바드", "서머너", "아르카나", "소서리스",
    "데모닉", "블레이드", "리퍼", "소울이터",
    "도화가", "기상술사"
]


@bot.event
async def on_ready():
    print(f"로그인됨: {bot.user}")
    bot.add_view(인증버튼())

    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 동기화 완료: {len(synced)}개")
    except Exception as e:
        print(f"슬래시 명령어 동기화 실패: {e}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"명령어 오류: {error}")


def 캐릭터프로필조회(char_name: str):
    encoded_name = quote(char_name)
    url = f"{LOSTARK_API_BASE}/armories/characters/{encoded_name}/profiles"
    headers = {
        "accept": "application/json",
        "authorization": f"bearer {LOSTARK_API_TOKEN}"
    }

    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code == 200:
        data = response.json()
        return {
            "success": True,
            "character_name": data.get("CharacterName"),
            "server_name": data.get("ServerName"),
            "class_name": data.get("CharacterClassName")
        }

    if response.status_code == 404:
        return {
            "success": False,
            "message": "캐릭터를 찾을 수 없습니다."
        }

    if response.status_code == 401:
        return {
            "success": False,
            "message": "로스트아크 API 인증키가 올바르지 않습니다."
        }

    if response.status_code == 429:
        return {
            "success": False,
            "message": "API 요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
        }

    return {
        "success": False,
        "message": f"API 오류가 발생했습니다. 상태코드: {response.status_code}"
    }


async def 인증로그(guild: discord.Guild, user: discord.Member, char_name: str, server_name: str, class_name: str):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel is None:
        return

    embed = discord.Embed(
        title="📌 로스트아크 인증 로그",
        color=0x2ECC71,
        timestamp=datetime.now()
    )
    embed.add_field(name="유저", value=user.mention, inline=False)
    embed.add_field(name="캐릭터", value=char_name, inline=True)
    embed.add_field(name="서버", value=server_name, inline=True)
    embed.add_field(name="직업", value=class_name, inline=True)
    embed.set_footer(text=f"User ID: {user.id}")

    await log_channel.send(embed=embed)


async def 역할지급(interaction: discord.Interaction, char_name: str, server_name: str, class_name: str):
    guild = interaction.guild
    user = interaction.user

    if guild is None or not isinstance(user, discord.Member):
        await interaction.followup.send("❌ 서버에서만 사용할 수 있습니다.", ephemeral=True)
        return

    if server_name not in servers:
        await interaction.followup.send(f"❌ 지원하지 않는 서버입니다: {server_name}", ephemeral=True)
        return

    if class_name not in classes:
        await interaction.followup.send(f"❌ 지원하지 않는 직업입니다: {class_name}", ephemeral=True)
        return

    인증역할 = discord.utils.get(guild.roles, name="인증됨")
    if 인증역할 is None:
        인증역할 = await guild.create_role(name="인증됨")

    서버역할 = discord.utils.get(guild.roles, name=server_name)
    if 서버역할 is None:
        서버역할 = await guild.create_role(name=server_name)

    직업역할 = discord.utils.get(guild.roles, name=class_name)
    if 직업역할 is None:
        직업역할 = await guild.create_role(name=class_name)

    current_server_roles = [role for role in user.roles if role.name in servers]
    current_class_roles = [role for role in user.roles if role.name in classes]

    roles_to_remove = []

    for role in current_server_roles:
        if role.name != server_name:
            roles_to_remove.append(role)

    for role in current_class_roles:
        if role.name != class_name:
            roles_to_remove.append(role)

    if roles_to_remove:
        try:
            await user.remove_roles(*roles_to_remove, reason="로스트아크 재인증 역할 정리")
        except discord.Forbidden:
            await interaction.followup.send("❌ 기존 역할 제거 권한이 없습니다. 봇 역할 위치를 확인해주세요.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send("❌ 기존 역할 제거 중 오류가 발생했습니다.", ephemeral=True)
            return

    roles_to_add = []

    if 인증역할 not in user.roles:
        roles_to_add.append(인증역할)

    if 서버역할 not in user.roles:
        roles_to_add.append(서버역할)

    if 직업역할 not in user.roles:
        roles_to_add.append(직업역할)

    if roles_to_add:
        try:
            await user.add_roles(*roles_to_add, reason="로스트아크 자동 인증 완료")
        except discord.Forbidden:
            await interaction.followup.send("❌ 역할 지급 권한이 없습니다. 봇 역할 위치를 확인해주세요.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.followup.send("❌ 역할 지급 중 오류가 발생했습니다.", ephemeral=True)
            return

    닉네임변경실패 = False
    try:
        await user.edit(nick=char_name, reason="로스트아크 자동 인증 닉네임 변경")
    except discord.Forbidden:
        닉네임변경실패 = True
    except discord.HTTPException:
        닉네임변경실패 = True

    await 인증로그(guild, user, char_name, server_name, class_name)

    msg = (
        f"✅ 자동 인증 완료!\n"
        f"캐릭터: {char_name}\n"
        f"서버: {server_name}\n"
        f"직업: {class_name}"
    )

    if 닉네임변경실패:
        msg += "\n⚠️ 닉네임 변경 권한이 없어 닉네임은 바꾸지 못했습니다."

    await interaction.followup.send(msg, ephemeral=True)


class 캐릭터입력(discord.ui.Modal, title="캐릭터 이름 입력"):
    캐릭터명 = discord.ui.TextInput(
        label="캐릭터 이름",
        placeholder="예: 모코콩떡",
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        char_name = str(self.캐릭터명.value).strip()
        if not char_name:
            await interaction.followup.send("❌ 캐릭터 이름을 입력해주세요.", ephemeral=True)
            return

        try:
            result = 캐릭터프로필조회(char_name)
        except requests.RequestException:
            await interaction.followup.send("❌ 로스트아크 API 요청에 실패했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
            return

        if not result["success"]:
            await interaction.followup.send(f"❌ 자동 인증 실패: {result['message']}", ephemeral=True)
            return

        server_name = result["server_name"]
        class_name = result["class_name"]
        real_char_name = result["character_name"] or char_name

        if not server_name or not class_name:
            await interaction.followup.send("❌ 서버 또는 직업 정보를 가져오지 못했습니다.", ephemeral=True)
            return

        await 역할지급(interaction, real_char_name, server_name, class_name)


class 인증버튼(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="인증하기",
        style=discord.ButtonStyle.green,
        custom_id="auth_button"
    )
    async def 인증(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(캐릭터입력())


@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("pong")


@bot.command(name="인증")
@commands.has_permissions(administrator=True)
async def auth_command(ctx):
    await ctx.send("버튼을 눌러 자동 인증하세요.", view=인증버튼())


@auth_command.error
async def auth_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ 관리자만 사용할 수 있는 명령어입니다.")


@bot.tree.command(name="핑", description="봇 응답 확인")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong")


@bot.tree.command(name="인증", description="로스트아크 자동 인증 버튼을 띄웁니다")
@app_commands.checks.has_permissions(administrator=True)
async def slash_auth(interaction: discord.Interaction):
    await interaction.response.send_message(
        "버튼을 눌러 자동 인증하세요.",
        view=인증버튼()
    )


@slash_auth.error
async def slash_auth_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ 관리자만 사용할 수 있는 명령어입니다.",
            ephemeral=True
        )


keep_alive()

DISCORD_TOKEN = os.environ["TOKEN"]
bot.run(DISCORD_TOKEN)
