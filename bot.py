import os
import discord
from discord.ext import commands
from datetime import datetime
from keep_alive import keep_alive

LOG_CHANNEL_ID = 1485629887673929949

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
    try:
        synced = await bot.tree.sync()
        print(f"슬래시 명령어 동기화 완료: {len(synced)}개")
    except Exception as e:
        print(f"슬래시 명령어 동기화 실패: {e}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"명령어 오류: {error}")


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

    인증역할 = discord.utils.get(guild.roles, name="인증됨")
    if 인증역할 is None:
        인증역할 = await guild.create_role(name="인증됨")

    서버역할 = discord.utils.get(guild.roles, name=server_name)
    if 서버역할 is None:
        서버역할 = await guild.create_role(name=server_name)

    직업역할 = discord.utils.get(guild.roles, name=class_name)
    if 직업역할 is None:
        직업역할 = await guild.create_role(name=class_name)

    try:
        await user.add_roles(인증역할, 서버역할, 직업역할, reason="로스트아크 인증 완료")
    except discord.Forbidden:
        await interaction.followup.send("❌ 역할 지급 권한이 없습니다. 봇 역할 위치를 확인해주세요.", ephemeral=True)
        return
    except discord.HTTPException:
        await interaction.followup.send("❌ 역할 지급 중 오류가 발생했습니다.", ephemeral=True)
        return

    닉네임변경실패 = False
    try:
        await user.edit(nick=char_name, reason="로스트아크 인증 닉네임 변경")
    except discord.Forbidden:
        닉네임변경실패 = True
    except discord.HTTPException:
        닉네임변경실패 = True

    await 인증로그(guild, user, char_name, server_name, class_name)

    msg = (
        f"✅ 인증 완료!\n"
        f"캐릭터: {char_name}\n"
        f"서버: {server_name}\n"
        f"직업: {class_name}"
    )

    if 닉네임변경실패:
        msg += "\n⚠️ 닉네임 변경 권한이 없어서 닉네임은 바꾸지 못했습니다."

    await interaction.followup.send(msg, ephemeral=True)


class 캐릭터입력(discord.ui.Modal, title="캐릭터 이름 입력"):
    캐릭터명 = discord.ui.TextInput(
        label="캐릭터 이름",
        placeholder="예: 모코콩떡",
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "서버를 선택해주세요.",
            view=서버선택(self.캐릭터명.value),
            ephemeral=True
        )


class 인증버튼(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="인증하기", style=discord.ButtonStyle.green)
    async def 인증(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(캐릭터입력())


class 서버선택(discord.ui.View):
    def __init__(self, char_name: str):
        super().__init__(timeout=180)
        self.char_name = char_name

        select = discord.ui.Select(
            placeholder="서버 선택",
            options=[discord.SelectOption(label=s) for s in servers]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        select_item = self.children[0]
        if not isinstance(select_item, discord.ui.Select):
            return

        server = select_item.values[0]
        await interaction.response.send_message(
            "직업을 선택해주세요.",
            view=직업선택(self.char_name, server),
            ephemeral=True
        )


class 직업선택(discord.ui.View):
    def __init__(self, char_name: str, server: str):
        super().__init__(timeout=180)
        self.char_name = char_name
        self.server = server

        select = discord.ui.Select(
            placeholder="직업 선택",
            options=[discord.SelectOption(label=c) for c in classes]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        select_item = self.children[0]
        if not isinstance(select_item, discord.ui.Select):
            return

        job = select_item.values[0]
        await interaction.response.defer(ephemeral=True)
        await 역할지급(interaction, self.char_name, self.server, job)


@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("pong")


@bot.command(name="인증")
async def 인증(ctx):
    await ctx.send("버튼을 눌러 인증하세요.", view=인증버튼())


@bot.tree.command(name="핑", description="봇 응답 확인")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong")


@bot.tree.command(name="인증", description="로스트아크 인증 버튼을 띄웁니다")
async def slash_auth(interaction: discord.Interaction):
    await interaction.response.send_message(
        "버튼을 눌러 인증하세요.",
        view=인증버튼()
    )


keep_alive()

TOKEN = os.environ["TOKEN"]
bot.run(TOKEN)
