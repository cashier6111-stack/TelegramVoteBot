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

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing")

if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID is missing")

admin_data = {}
votes = {}
voted_users = {}

vote_counter = 1000


def vote_keyboard(vote_id):
    vote_data = votes[vote_id]
    closed = vote_data.get("closed", False)

    keyboard = []

    for i, match in enumerate(vote_data["matches"]):
        team1 = match["team1"]
        team2 = match["team2"]

        if closed:
            keyboard.append([
                InlineKeyboardButton(
                    f"🔒 {team1} ({match['team1_votes']})",
                    callback_data=f"closed:{vote_id}"
                ),
                InlineKeyboardButton(
                    f"🔒 {team2} ({match['team2_votes']})",
                    callback_data=f"closed:{vote_id}"
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"{team1} ({match['team1_votes']})",
                    callback_data=f"vote:{vote_id}:{i}:team1"
                ),
                InlineKeyboardButton(
                    f"{team2} ({match['team2_votes']})",
                    callback_data=f"vote:{vote_id}:{i}:team2"
                )
            ])

    return InlineKeyboardMarkup(keyboard)


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
            "🏆 Send matches like this:\n\n"
            "Mexico|South Africa\n"
            "USA|Paraguay\n"
            "Brazil|Japan\n"
            "Spain|Germany"
        )

    elif step == "teams":
        lines = text.strip().splitlines()
        matches = []

        for line in lines:
            line = line.strip()

            if not line:
                continue

            if "|" not in line:
                await update.message.reply_text(
                    "Wrong format.\n\n"
                    "Please use one match per line:\n\n"
                    "Mexico|South Africa\n"
                    "USA|Paraguay"
                )
                return

            team1, team2 = line.split("|", 1)
            team1 = team1.strip()
            team2 = team2.strip()

            if not team1 or not team2:
                await update.message.reply_text(
                    "Team name cannot be empty.\n\n"
                    "Example:\nMexico|South Africa"
                )
                return

            matches.append({
                "team1": team1,
                "team2": team2,
                "team1_votes": 0,
                "team2_votes": 0,
                "team1_users": [],
                "team2_users": [],
                "voted_users": set()
            })

        if not matches:
            await update.message.reply_text("No match found.")
            return

        vote_counter += 1
        vote_id = str(vote_counter)

        data = admin_data[user_id]

        votes[vote_id] = {
            "matches": matches,
            "closed": False,
            "channel_message_id": None,
            "caption": data["caption"],
        }

        sent = await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=data["photo"],
            caption=data["caption"],
            reply_markup=vote_keyboard(vote_id)
        )

        votes[vote_id]["channel_message_id"] = sent.message_id

        await update.message.reply_text(
            f"✅ Vote post published to channel.\n\n"
            f"Vote ID: {vote_id}\n\n"
            f"Use:\n"
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

    parts = query.data.split(":")

    if len(parts) != 4:
        await query.answer("Invalid vote.", show_alert=True)
        return

    _, vote_id, match_index, choice = parts
    match_index = int(match_index)

    if vote_id not in votes:
        await query.answer("Vote expired.", show_alert=True)
        return

    vote_data = votes[vote_id]

    if vote_data.get("closed"):
        await query.answer("Voting is closed.", show_alert=True)
        return

    if match_index < 0 or match_index >= len(vote_data["matches"]):
        await query.answer("Match not found.", show_alert=True)
        return

    match = vote_data["matches"][match_index]

    if user_id in match["voted_users"]:
        await query.answer(
            "You already bet on this match!",
            show_alert=True
        )
        return

    name = user_name(query.from_user)

    if choice == "team1":
        match["team1_votes"] += 1
        match["team1_users"].append(name)
        selected_team = match["team1"]

    elif choice == "team2":
        match["team2_votes"] += 1
        match["team2_users"].append(name)
        selected_team = match["team2"]

    else:
        await query.answer("Invalid choice.", show_alert=True)
        return

    match["voted_users"].add(user_id)

    await query.answer(f"Bet saved: {selected_team}", show_alert=True)

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
            msg += f"Vote ID: {vote_id}\nStatus: {status}\n"

            for i, match in enumerate(data["matches"], start=1):
                msg += f"{i}. {match['team1']} vs {match['team2']}\n"

            msg += f"\n/results {vote_id}\n/closevote {vote_id}\n\n"

        await update.message.reply_text(msg)
        return

    vote_id = context.args[0]

    if vote_id not in votes:
        await update.message.reply_text("Vote ID not found.")
        return

    data = votes[vote_id]
    status = "🔒 Closed" if data.get("closed") else "🟢 Open"

    msg = f"📊 Vote Results\n\nVote ID: {vote_id}\nStatus: {status}\n\n"

    for i, match in enumerate(data["matches"], start=1):
        team1_list = "\n".join(match["team1_users"]) if match["team1_users"] else "No votes yet"
        team2_list = "\n".join(match["team2_users"]) if match["team2_users"] else "No votes yet"

        msg += (
            f"Match {i}\n"
            f"{match['team1']} vs {match['team2']}\n\n"
            f"{match['team1']} ({match['team1_votes']})\n"
            f"{team1_list}\n\n"
            f"{match['team2']} ({match['team2_votes']})\n"
            f"{team2_list}\n\n"
            f"--------------------\n\n"
        )

    await update.message.reply_text(msg)


async def closevote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text(
            "Please send Vote ID.\n\nExample:\n/closevote 1001"
        )
        return

    vote_id = context.args[0]

    if vote_id not in votes:
        await update.message.reply_text("Vote ID not found.")
        return

    data = votes[vote_id]

    if data.get("closed"):
        await update.message.reply_text("This vote is already closed.")
        return

    data["closed"] = True

    await context.bot.edit_message_reply_markup(
        chat_id=CHANNEL_ID,
        message_id=data["channel_message_id"],
        reply_markup=vote_keyboard(vote_id)
    )

    await update.message.reply_text(
        f"🔒 Voting closed.\n\nVote ID: {vote_id}"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_data.pop(user_id, None)
    await update.message.reply_text("Cancelled.")


app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .connect_timeout(30)
    .read_timeout(30)
    .write_timeout(30)
    .pool_timeout(30)
    .build()
)

app.add_handler(CommandHandler("newvote", newvote))
app.add_handler(CommandHandler("results", results))
app.add_handler(CommandHandler("closevote", closevote))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(CallbackQueryHandler(vote))

if __name__ == "__main__":
    app.run_polling()