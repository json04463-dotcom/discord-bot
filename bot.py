import os
from datetime import datetime

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
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


async def write_auth_log(
    guild: discord.Guild,
    user: discord.Member,
    character_name: str,
    server_name: str,
    class_name: str,
) -> None:
    if not LOG_CHANNEL_ID:
        return

    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel is None:
        return

    embed = discord.Embed(
        title="인증 로그",
        color=discord.Color.green(),
        timestamp=datetime.now(),
    )
    embed.add_field(name="유저", value=f"{user} (`{user.id}`)", inline=False)
    embed.add_field(name="캐릭터", value=character_name, inline=True)
    embed.add_field(name="서버", value=server_name, inline=True)
    embed.add_field(name="직업", value=class_name, inline=True)

    try:
        await log_channel.send(embed=embed)
    except discord.Forbidden:
        pass


async def grant_roles_and_update_nick(
    interaction: discord.Interaction,
    character_name: str,
    server_name: str,
    class_name: str,
) -> None:
    guild = interaction.guild
    user = interaction.user

    if guild is None or not isinstance(user, discord.Member):
        await interaction.followup.send("❌ 서버 안에서만 사용할 수 있습니다.", ephemeral=True)
        return

    auth_role = discord.utils.get(guild.roles, name="인증됨")
    if auth_role is None:
        auth_role = await guild.create_role(name="인증됨")

    server_role = discord.utils.get(guild.roles, name=server_name)
    if server_role is None:
        server_role = await guild.create_role(name=server_name)

    class_role = discord.utils.get(guild.roles, name=class_name)
    if class_role is None:
        class_role = await guild.create_role(name=class_name)

    try:
        await user.add_roles(auth_role, server_role, class_role, reason="로스트아크 수동 인증")
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ 역할 지급 실패: 봇 권한 또는 역할 위치를 확인해주세요.",
            ephemeral=True,
        )
        return

    nick_changed = True
    try:
        await user.edit(nick=character_name, reason="로스트아크 수동 인증 닉네임 변경")
    except discord.Forbidden:
        nick_changed = False

    await write_auth_log(guild, user, character_name, server_name, class_name)

    message = (
        f"✅ 인증 완료!\n"
        f"캐릭터: {character_name}\n"
        f"서버: {server_name}\n"
        f"직업: {class_name}\n"
        f"닉네임 변경: {'성공' if nick_changed else '실패'}"
    )
    await interaction.followup.send(message, ephemeral=True)


class ClassSelect(discord.ui.Select):
    def __init__(self, character_name: str, server_name: str):
        self.character_name = character_name
        self.server_name = server_name

        options = [discord.SelectOption(label=name) for name in classes[:25]]
        super().__init__(
            placeholder="직업을 선택해주세요",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_class = self.values[0]
        await interaction.response.defer(ephemeral=True)
        await grant_roles_and_update_nick(
            interaction,
            self.character_name,
            self.server_name,
            selected_class,
        )


class ExtraClassSelect(discord.ui.Select):
    def __init__(self, character_name: str, server_name: str):
        self.character_name = character_name
        self.server_name = server_name

        extra_classes = classes[25:]
        options = [discord.SelectOption(label=name) for name in extra_classes]
        super().__init__(
            placeholder="나머지 직업 선택",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_class = self.values[0]
        await interaction.response.defer(ephemeral=True)
        await grant_roles_and_update_nick(
            interaction,
            self.character_name,
            self.server_name,
            selected_class,
        )


class ClassSelectView(discord.ui.View):
    def __init__(self, character_name: str, server_name: str):
        super().__init__(timeout=300)
        self.add_item(ClassSelect(character_name, server_name))
        if len(classes) > 25:
            self.add_item(ExtraClassSelect(character_name, server_name))


class ServerSelect(discord.ui.Select):
    def __init__(self, character_name: str):
        self.character_name = character_name

        options = [discord.SelectOption(label=name) for name in servers]
        super().__init__(
            placeholder="서버를 선택해주세요",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected_server = self.values[0]
        await interaction.response.send_message(
            "직업을 선택해주세요.",
            view=ClassSelectView(self.character_name, selected_server),
            ephemeral=True,
        )


class ServerSelectView(discord.ui.View):
    def __init__(self, character_name: str):
        super().__init__(timeout=300)
        self.add_item(ServerSelect(character_name))


class CharacterNameModal(discord.ui.Modal, title="캐릭터 이름 입력"):
    character_name = discord.ui.TextInput(
        label="캐릭터 이름",
        placeholder="예: 만개초",
        min_length=1,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = str(self.character_name.value).strip()
        if not name:
            await interaction.response.send_message(
                "❌ 캐릭터 이름을 입력해주세요.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "서버를 선택해주세요.",
            view=ServerSelectView(name),
            ephemeral=True,
        )


class AuthStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="인증하기", style=discord.ButtonStyle.green)
    async def start_auth(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(CharacterNameModal())


@bot.event
async def on_ready():
    print(f"로그인됨: {bot.user}")


@bot.command()
async def 인증(ctx: commands.Context):
    await ctx.send("아래 버튼을 눌러 인증을 진행하세요.", view=AuthStartView())


bot.run(TOKEN)
