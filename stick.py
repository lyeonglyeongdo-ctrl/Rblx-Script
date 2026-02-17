import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os

TOKEN = "MTQ3MjUwMzAwMTA2MjE4MzAwOA.GQBzLY.KpyBvDAxDH2rX6TuFwpdWWfFpEolKrMyH0lAkI"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "sticky_data.json")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================== 데이터 ==================

sticky_messages = {}   # {guild_id: {channel_id: message_id}}
sticky_contents = {}   # {guild_id: {channel_id: content}}
sticky_versions = {}   # {channel_id: version}

log_channels = {}      # {guild_id: channel_id}
log_enabled = {}       # {guild_id: True/False}


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
    save_data()


@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    guild_id = message.guild.id
    channel_id = message.channel.id

    if guild_id in sticky_messages and \
       channel_id in sticky_messages[guild_id]:

        current_version = sticky_versions.get(channel_id, 0) + 1
        sticky_versions[channel_id] = current_version

        bot.loop.create_task(
            delayed_sticky(guild_id, message.channel, current_version)
        )

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


# ================== 시작 ==================

@bot.event
async def on_ready():
    load_data()

    await bot.tree.sync()  # 🌍 글로벌 동기화

    print(f"✅ 글로벌 동기화 완료: {bot.user}")




bot.run(TOKEN)
