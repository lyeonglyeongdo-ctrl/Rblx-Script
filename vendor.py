import discord
from discord.ext import commands, tasks
from discord import app_commands
from pushbullet import Pushbullet
import sqlite3
import re

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PUSHBULLET_TOKEN = os.getenv("PUSHBULLET_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

pb = Pushbullet(PUSHBULLET_TOKEN)

conn = sqlite3.connect("vending.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS pending (
    user_id TEXT,
    name TEXT,
    amount INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS balance (
    user_id TEXT PRIMARY KEY,
    money INTEGER
)
""")

conn.commit()

processed = set()

# ------------------ 충전 모달 ------------------

class ChargeModal(discord.ui.Modal, title="충전 신청"):
    name = discord.ui.TextInput(label="입금자명")
    amount = discord.ui.TextInput(label="금액")

    async def on_submit(self, interaction: discord.Interaction):
        cur.execute(
            "INSERT INTO pending VALUES (?, ?, ?)",
            (str(interaction.user.id), self.name.value, int(self.amount.value))
        )
        conn.commit()

        await interaction.response.send_message(
            "입금 확인 시 자동 충전됩니다.",
            ephemeral=True
        )

@bot.tree.command(name="충전")
async def charge(interaction: discord.Interaction):
    await interaction.response.send_modal(ChargeModal())

# ------------------ 잔액 확인 ------------------

@bot.tree.command(name="잔액")
async def balance(interaction: discord.Interaction):
    cur.execute("SELECT money FROM balance WHERE user_id=?", (str(interaction.user.id),))
    result = cur.fetchone()

    money = result[0] if result else 0

    await interaction.response.send_message(
        f"현재 잔액: {money}원",
        ephemeral=True
    )

# ------------------ Pushbullet 자동 감지 ------------------

@tasks.loop(seconds=10)
async def check_pushbullet():
    pushes = pb.get_pushes(limit=5)

    for push in pushes:
        pid = push["iden"]
        body = push.get("body", "")

        if pid in processed:
            continue

        name_match = re.search(r"(.+?)님이", body)
        amount_match = re.search(r"(\d+)원", body)

        if name_match and amount_match:
            name = name_match.group(1)
            amount = int(amount_match.group(1))

            cur.execute(
                "SELECT user_id FROM pending WHERE name=? AND amount=?",
                (name, amount)
            )
            result = cur.fetchone()

            if result:
                user_id = result[0]

                cur.execute(
                    "INSERT INTO balance(user_id, money) VALUES(?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET money = money + ?",
                    (user_id, amount, amount)
                )

                cur.execute(
                    "DELETE FROM pending WHERE user_id=?",
                    (user_id,)
                )

                conn.commit()

                user = await bot.fetch_user(int(user_id))
                await user.send(f"✅ {amount}원 충전 완료!")

        processed.add(pid)

@bot.event
async def on_ready():
    print("봇 준비 완료")
    check_pushbullet.start()

bot.run(BOT_TOKEN)
