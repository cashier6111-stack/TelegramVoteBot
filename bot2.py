import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

admin_data = {}
votes = {}
voted_users = {}

vote_counter = 1000


def vote_keyboard(vote_id):
    vote_data = votes[vote_id]
    team1 = vote_data["team1"]
    team2 = vote_data["team2"]
    closed = vote_data.get("closed", False)

    if closed:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"🔒 {team1} ({vote_data['team1_votes']})",
                    callback_data=f"closed:{vote_id}"
                ),
                InlineKeyboardButton(
                    f"🔒 {team2} ({vote_data['team2_votes']})",
                    callback_data=f"closed:{vote_id}"
                )
            ]
        ])

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"{team1} ({vote_data['team1_votes']})",
                callback_data=f"vote:{vote_id}:team1"
            ),
            InlineKeyboardButton(
                f"{team2} ({vote_data['team2_votes']})",
                callback_data=f"vote:{vote_id}:team2"
            )
        ]
    ])


def user_name(user):
    if user.username:
        return f"@{user.username}"
    return user.full_name


async def newvote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_data[user_id] = {"step": "photo"}
    await update.message.reply_text("📷 Please send match image.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in admin_data or admin_data[user_id].get("step") != "photo":
        return

    admin_data[user_id]["photo"] = update.message.photo[-1].file_id
    admin_data[user_id]["step"] = "text"

    await update.message.reply_text(
        "📝 Please send match text.\n\n"
        "Example:\n"
        "⚽ FIFA World Cup 2026\n\n"
        "MEXICO VS SOUTH AFRICA\n\n"
        "Who will win?"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global vote_counter

    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in admin_data:
        return

    step = admin_data[user_id].get("step")

    if step == "text":
        admin_data[user_id]["caption"] = text
        admin_data[user_id]["step"] = "teams"

        await update.message.reply_text(
            "🏆 Send team names like this:\n\nMexico|South Africa"
        )

    elif step == "teams":
        if "|" not in text:
            await update.message.reply_text(
                "Wrong format. Please use:\n\nMexico|South Africa"
            )
            return

        team1, team2 = text.split("|", 1)
        team1 = team1.strip()
        team2 = team2.strip()

        vote_counter += 1
        vote_id = str(vote_counter)

        data = admin_data[user_id]

        votes[vote_id] = {
            "team1": team1,
            "team2": team2,
            "team1_votes": 0,
            "team2_votes": 0,
            "team1_users": [],
            "team2_users": [],
            "closed": False,
            "channel_message_id": None,
            "caption": data["caption"],
        }

        voted_users[vote_id] = set()

        sent = await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=data["photo"],
            caption=data["caption"],
            reply_markup=vote_keyboard(vote_id)
        )

        votes[vote_id]["channel_message_id"] = sent.message_id

        await update.message.reply_text(
            f"✅ Vote post published.\n\n"
            f"Vote ID: {vote_id}\n\n"
            f"/results {vote_id}\n"
            f"/closevote {vote_id}"
        )

        del admin_data[user_id]


async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if query.data.startswith("closed:"):
        await query.answer("Voting is closed.", show_alert=True)
        return

    _, vote_id, choice = query.data.split(":")

    if vote_id not in votes:
        await query.answer("Vote expired.", show_alert=True)
        return

    if votes[vote_id].get("closed"):
        await query.answer("Voting is closed.", show_alert=True)
        return

    if user_id in voted_users[vote_id]:
        await query.answer("You already voted!", show_alert=True)
        return

    name = user_name(query.from_user)

    if choice == "team1":
        votes[vote_id]["team1_votes"] += 1
        votes[vote_id]["team1_users"].append(name)

    elif choice == "team2":
        votes[vote_id]["team2_votes"] += 1
        votes[vote_id]["team2_users"].append(name)

    voted_users[vote_id].add(user_id)

    await query.answer("Vote saved!")

    await query.edit_message_reply_markup(
        reply_markup=vote_keyboard(vote_id)
    )


async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not votes:
        await update.message.reply_text("No vote found.")
        return

    if len(context.args) == 0:
        msg = "📋 Vote List\n\n"

        for vote_id, data in votes.items():
            status = "🔒 Closed" if data.get("closed") else "🟢 Open"

            msg += (
                f"Vote ID: {vote_id}\n"
                f"{data['team1']} vs {data['team2']}\n"
                f"{status}\n\n"
            )

        await update.message.reply_text(msg)
        return

    vote_id = context.args[0]

    if vote_id not in votes:
        await update.message.reply_text("Vote ID not found.")
        return

    data = votes[vote_id]

    team1_list = "\n".join(data["team1_users"]) if data["team1_users"] else "No votes yet"
    team2_list = "\n".join(data["team2_users"]) if data["team2_users"] else "No votes yet"

    msg = f"""
📊 Vote Results

Vote ID: {vote_id}

{data['team1']} ({data['team1_votes']})

{team1_list}

{data['team2']} ({data['team2_votes']})

{team2_list}
"""

    await update.message.reply_text(msg)


async def closevote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text(
            "/closevote 1001"
        )
        return

    vote_id = context.args[0]

    if vote_id not in votes:
        await update.message.reply_text("Vote ID not found.")
        return

    data = votes[vote_id]

    data["closed"] = True

    await context.bot.edit_message_reply_markup(
        chat_id=CHANNEL_ID,
        message_id=data["channel_message_id"],
        reply_markup=vote_keyboard(vote_id)
    )

    await update.message.reply_text(
        f"🔒 Vote Closed\nVote ID: {vote_id}"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_data.pop(user_id, None)
    await update.message.reply_text("Cancelled.")


app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .build()
)

app.add_handler(CommandHandler("newvote", newvote))
app.add_handler(CommandHandler("results", results))
app.add_handler(CommandHandler("closevote", closevote))
app.add_handler(CommandHandler("cancel", cancel))

app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

app.add_handler(CallbackQueryHandler(vote))

print("Bot Started...")
app.run_polling()