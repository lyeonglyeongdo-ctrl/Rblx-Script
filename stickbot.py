import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "sticky_data.json")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================== 데이터 ==================
sticky_data = {}


log_channels = {}      # {guild_id: channel_id}
log_enabled = {}       # {guild_id: True/False}

# 고정임베드 클래스
class EmbedStickyModal(discord.ui.Modal, title="임베드 고정 설정"):

    title_input = discord.ui.TextInput(
        label="임베드 제목",
        placeholder="제목을 입력하세요",
        max_length=100
    )

    description_input = discord.ui.TextInput(
        label="임베드 설명",
        placeholder="설명을 입력하세요",
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.title_input.value,
            description=self.description_input.value,
            color=0xffd700  # 노란색
        )

        message = await interaction.channel.send(embed=embed)

        # 고정 데이터 저장
        guild_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id)

        if guild_id not in sticky_data:
            sticky_data[guild_id] = {}

        sticky_data[guild_id][channel_id] = {
            "type": "embed",
            "title": self.title_input.value,
            "description": self.description_input.value,
            "message_id": message.id
        }

        save_data()

        await interaction.response.send_message("✅ 임베드가 고정되었습니다.", ephemeral=True)
# ================== 저장 / 로드 ==================

def save_data():
    data = {
        "messages": sticky_messages,
        "contents": sticky_contents,
        "logs": log_channels,
        "log_enabled": log_enabled
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_data():
    global sticky_messages, sticky_contents, log_channels, log_enabled

    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    sticky_messages = {
        int(gid): {int(cid): mid for cid, mid in channels.items()}
        for gid, channels in data.get("messages", {}).items()
    }

    sticky_contents = {
        int(gid): {int(cid): content for cid, content in channels.items()}
        for gid, channels in data.get("contents", {}).items()
    }

    log_channels = {
        int(gid): int(cid)
        for gid, cid in data.get("logs", {}).items()
    }

    log_enabled = {
        int(gid): value
        for gid, value in data.get("log_enabled", {}).items()
    }

# 멘션 감지 class
class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

@discord.ui.button(label="📌 사용하기", style=discord.ButtonStyle.primary)
async def invite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    await interaction.response.send_message(
        "# [고정봇 추가](https://discord.com/oauth2/authorize?client_id=1472503001062183008)",
    ephemeral=True
        )
# 접근
class ServerListModal(discord.ui.Modal, title="서버 목록 확인"):
    password = discord.ui.TextInput(
        label="접근 코드 입력",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):

        await interaction.response.defer(ephemeral=True)

        if self.password.value != "choimobile":
            await interaction.followup.send(
                "❌ 접근 코드가 올바르지 않습니다.",
                ephemeral=True
            )
            return

        result_text = ""
        guilds = bot.guilds

        for guild in guilds:

            invite_link = "초대 생성 실패"

            # 🔥 초대 생성 시도
            for channel in guild.text_channels:
                try:
                    invite = await channel.create_invite(
                        max_age=300,  # 5분
                        max_uses=1,
                        unique=True
                    )
                    invite_link = invite.url
                    break
                except:
                    continue

            result_text += (
                f"**{guild.name}**\n"
                f"ID: {guild.id}\n"
                f"멤버: {guild.member_count}명\n"
                f"초대: {invite_link}\n\n"
            )

        # embed 길이 제한 대비
        if len(result_text) > 4000:
            result_text = result_text[:4000]

        embed = discord.Embed(
            title="📌 고정봇 사용 서버",
            description=result_text,
            color=0x2b2d31
        )

        embed.set_footer(text=f"총 {len(guilds)}개 서버")

        await interaction.followup.send(embed=embed, ephemeral=True)
# ================== 고정 모달 ==================

class StickyModal(discord.ui.Modal, title="고정 메시지 설정"):
    message = discord.ui.TextInput(
        label="고정할 메시지",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id

        sticky_messages.setdefault(guild_id, {})
        sticky_contents.setdefault(guild_id, {})

        # 기존 고정 삭제
        if channel_id in sticky_messages[guild_id]:
            try:
                old = await interaction.channel.fetch_message(
                    sticky_messages[guild_id][channel_id]
                )
                await old.delete()
            except:
                pass

        sent = await interaction.channel.send(self.message.value)

        sticky_messages[guild_id][channel_id] = sent.id
        sticky_contents[guild_id][channel_id] = self.message.value
        sticky_versions[channel_id] = 0

        save_data()

        await interaction.response.send_message("✅ 고정 완료!", ephemeral=True)


# ================== 슬래시 명령어 ==================

@bot.tree.command(name="고정")
@app_commands.checks.has_permissions(administrator=True)
async def sticky(interaction: discord.Interaction):
    await interaction.response.send_modal(StickyModal())
async def pin_message(interaction: discord.Interaction, message: str):
    # 관리자가 아니면 사용 못하게
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return

    # 고정할 메시지 처리
    try:
        # 메시지 고정
        pinned_message = await interaction.channel.send(message)  # 고정할 메시지 전송

        # 고정된 메시지 기록 (콘솔에 출력)
        print(f"{interaction.user}가 '/고정' 명령어를 사용했습니다.")
        print(f"메시지 내용: {message}")

        # 기록할 로그 채널 ID로 로그 전송 (로그 채널 ID 지정 필요)
        log_channel = interaction.guild.get_channel(1473916982226059285)  # 로그 채널 ID 넣기
        if log_channel:
            embed = discord.Embed(
                title="📌 고정봇 사용 기록",
                description=f"**사용자**: {interaction.user}\n**고정 메시지**: {message}",
                color=0x2b2d31
            )
            await log_channel.send(embed=embed)

        # 사용자에게 고정 완료 메시지
        await interaction.response.send_message("메시지가 고정되었습니다.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 에러가 발생했습니다: {str(e)}", ephemeral=True)

@bot.tree.command(name="임베드고정", description="임베드 형태로 고정 메시지를 설정합니다")
async def embed_pin(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 관리자만 사용 가능합니다.", ephemeral=True)
        return

    await interaction.response.send_modal(EmbedStickyModal())
@bot.tree.command(name="고정해제")
@app_commands.checks.has_permissions(administrator=True)
async def unsticky(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    channel_id = interaction.channel.id

    if guild_id not in sticky_messages or \
       channel_id not in sticky_messages[guild_id]:
        await interaction.response.send_message("❌ 고정 없음", ephemeral=True)
        return

    try:
        old = await interaction.channel.fetch_message(
            sticky_messages[guild_id][channel_id]
        )
        await old.delete()
    except:
        pass

    sticky_messages[guild_id].pop(channel_id, None)
    sticky_contents[guild_id].pop(channel_id, None)
    sticky_versions.pop(channel_id, None)

    save_data()

    await interaction.response.send_message("🗑️ 고정 해제 완료!", ephemeral=True)


@bot.tree.command(name="로그채널설정")
@app_commands.checks.has_permissions(administrator=True)
async def set_log(interaction: discord.Interaction, 채널: discord.TextChannel):

    guild_id = interaction.guild.id
    log_channels[guild_id] = 채널.id
    log_enabled[guild_id] = True

    save_data()

    await interaction.response.send_message(
        f"✅ 로그 채널 설정 완료: {채널.mention}",
        ephemeral=True
    )


@bot.tree.command(name="로그끄기")
@app_commands.checks.has_permissions(administrator=True)
async def disable_log(interaction: discord.Interaction):

    guild_id = interaction.guild.id

    if guild_id not in log_enabled:
        await interaction.response.send_message(
            "❌ 로그가 설정되지 않았습니다.",
            ephemeral=True
        )
        return

    log_enabled[guild_id] = False
    save_data()

    await interaction.response.send_message(
        "🛑 메시지 로그 비활성화 완료",
        ephemeral=True
    )


# ================== 2초 재고정 + 도배 방지 ==================

async def delayed_sticky(guild_id, channel, version):
    await asyncio.sleep(2)

    if sticky_versions.get(channel.id) != version:
        return

    if guild_id not in sticky_contents:
        return

    if channel.id not in sticky_contents[guild_id]:
        return

    try:
        old = await channel.fetch_message(
            sticky_messages[guild_id][channel.id]
        )
        await old.delete()
    except:
        pass

    sent = await channel.send(sticky_contents[guild_id][channel.id])
    sticky_messages[guild_id][channel.id] = sent.id
# on_message
@bot.event
async def on_message(message):

    # 봇 메시지 무시
    if message.author.bot:
        return

    # DM 무시
    if not message.guild:
        return

    guild_id = message.guild.id
    channel_id = message.channel.id

    # 🔥 봇 멘션 감지
    if bot.user in message.mentions:
        embed = discord.Embed(
            title="📌 고정봇",
            description="선택 메시지를 자동으로 재전송해주는 국산 봇입니다.",
            color=0xffd400
        )

        await message.channel.send(embed=embed, view=InviteView())
        return

    # =========================
    # 🔹 기존 delayed_sticky 시스템
    # =========================
    if guild_id in sticky_messages and \
       channel_id in sticky_messages[guild_id]:

        current_version = sticky_versions.get(channel_id, 0) + 1
        sticky_versions[channel_id] = current_version

        bot.loop.create_task(
            delayed_sticky(guild_id, message.channel, current_version)
        )

    # =========================
    # 🔹 새 embed / text 고정 시스템
    # =========================
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)

    if guild_id_str in sticky_data and \
       channel_id_str in sticky_data[guild_id_str]:

        data = sticky_data[guild_id_str][channel_id_str]

        if data["type"] == "embed":
            embed = discord.Embed(
                title=data["title"],
                description=data["description"],
                color=0xffd700
            )
            await message.channel.send(embed=embed)
        elif data["type"] == "text":
            await message.channel.send(data["content"])

    # 🔥 이거 꼭 마지막에
    await bot.process_commands(message)
# ================== 삭제 로그 ==================

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return

    guild_id = message.guild.id

    if guild_id not in log_enabled or not log_enabled[guild_id]:
        return

    if guild_id not in log_channels:
        return

    log_channel = bot.get_channel(log_channels[guild_id])
    if not log_channel:
        return

    embed = discord.Embed(title="🗑 삭제된 메시지", color=0xff4444)
    embed.add_field(name="작성자", value=message.author.mention, inline=False)
    embed.add_field(name="채널", value=message.channel.mention, inline=False)
    embed.add_field(
        name="내용",
        value=message.content if message.content else "첨부파일 또는 임베드",
        inline=False
    )
    embed.set_footer(text=f"User ID: {message.author.id}")

    await log_channel.send(embed=embed)


# ================== 수정 로그 ==================

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild:
        return

    if before.content == after.content:
        return

    guild_id = before.guild.id

    if guild_id not in log_enabled or not log_enabled[guild_id]:
        return

    if guild_id not in log_channels:
        return

    log_channel = bot.get_channel(log_channels[guild_id])
    if not log_channel:
        return

    embed = discord.Embed(title="✏️ 수정된 메시지", color=0xffaa00)
    embed.add_field(name="작성자", value=before.author.mention, inline=False)
    embed.add_field(name="채널", value=before.channel.mention, inline=False)
    embed.add_field(
        name="📝 수정 전",
        value=before.content if before.content else "내용 없음",
        inline=False
    )
    embed.add_field(
        name="📝 수정 후",
        value=after.content if after.content else "내용 없음",
        inline=False
    )
    embed.set_footer(text=f"User ID: {before.author.id}")

    await log_channel.send(embed=embed)

# /서버목록
@bot.tree.command(name="서버목록", description="고정봇 사용 서버 목록 확인")
async def server_list(interaction: discord.Interaction):
    await interaction.response.send_modal(ServerListModal())
# ================== 시작 ==================

@bot.event
async def on_ready():
    load_data()

    await bot.tree.sync()  # 🌍 글로벌 동기화

    print(f"✅ 글로벌 동기화 완료: {bot.user}")




bot.run(TOKEN)
