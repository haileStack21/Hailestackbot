
from datetime import datetime, timedelta, timezone
from telegram.ext import MessageHandler, filters
import os
from dotenv import load_dotenv
from psycopg import IntegrityError

from database import (
    init_db,
    save_student,
    get_pending_students,
    get_student,
    set_student_status,
)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {
    int(item.strip())
    for item in os.getenv("ADMIN_IDS", "").split(",")
    if item.strip().isdigit()
}

NAME, STREAM, DEPARTMENT, PAYMENT = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("📝 Register", callback_data="register")
    ]]

    await update.message.reply_text(
        "Welcome to Hailestack Academy!\n\n"
        "Learn • Build • Earn\n"
        "Annual tuition: 500 ETB\n\n"
        "Press Register to begin.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    await query.message.reply_text("Step 1/4: Enter your full name.")
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    if len(name) < 2 or len(name) > 100:
        await update.message.reply_text("Please enter a valid full name.")
        return NAME

    context.user_data["name"] = name

    keyboard = [
        [InlineKeyboardButton(
            "Social Media & Content Creation",
            callback_data="social"
        )],
        [InlineKeyboardButton(
            "Software Development",
            callback_data="software"
        )],
    ]

    await update.message.reply_text(
        "Step 2/4: Choose your learning stream.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return STREAM


async def get_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    streams = {
        "social": "Social Media & Content Creation",
        "software": "Software Development",
    }
    context.user_data["stream"] = streams[query.data]

    await query.message.reply_text(
        "Step 3/4: Enter your university department."
    )
    return DEPARTMENT


async def get_department(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    department = update.message.text.strip()

    if len(department) < 2 or len(department) > 100:
        await update.message.reply_text(
            "Please enter a valid department."
        )
        return DEPARTMENT

    context.user_data["department"] = department

    await update.message.reply_text(
        "Step 4/4: Payment instructions\n\n"
        "Annual tuition: 500 ETB\n\n"
        "Bank: Commercial Bank of Ethiopia (CBE)\n"
        "Account holder: Hailemariam Solomon Tadesse\n"
        "Account number: [your configured account number]\n\n"
        "After making the payment, enter your transaction reference.\n"
        "Your registration remains pending until an administrator "
        "verifies the payment. Do not submit a reference for a "
        "payment you have not made."
    )
    return PAYMENT


async def get_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reference = update.message.text.strip()

    if len(reference) < 3 or len(reference) > 120:
        await update.message.reply_text(
            "Please enter a valid transaction reference."
        )
        return PAYMENT

    user = update.effective_user

    try:
        student_id = save_student(
            telegram_id=user.id,
            telegram_username=user.username,
            full_name=context.user_data["name"],
            stream=context.user_data["stream"],
            department=context.user_data["department"],
            payment_reference=reference,
        )
    except IntegrityError:
        await update.message.reply_text(
            "This payment reference has already been submitted. "
            "Please contact the administrator if you need help."
        )
        return PAYMENT
    except Exception:
        await update.message.reply_text(
            "We could not save your registration. "
            "Please contact the administrator."
        )
        return PAYMENT

    await update.message.reply_text(
        "Registration saved successfully!\n\n"
        f"Registration ID: {student_id}\n"
        f"Name: {context.user_data['name']}\n"
        f"Stream: {context.user_data['stream']}\n"
        f"Department: {context.user_data['department']}\n\n"
        "Payment status: PENDING\n"
        "An administrator must verify your payment before approval."
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Registration cancelled. "
        "Send /start whenever you want to register again."
    )
    return ConversationHandler.END


async def admin_only(update: Update) -> bool:
    user = update.effective_user

    if user is None or user.id not in ADMIN_IDS:
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ You are not authorized to use this admin command."
            )
        return False

    return True
async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Academy chat ID: {update.effective_chat.id}"
    )

async def pending_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not await admin_only(update):
        return

    try:
        students = get_pending_students()
    except Exception:
        await update.effective_message.reply_text(
            "Database error while loading pending registrations."
        )
        return

    if not students:
        await update.effective_message.reply_text(
            "✅ There are no pending registrations."
        )
        return

    lines = ["📋 PENDING REGISTRATIONS (up to 20)\n"]

    for student in students:
        username = (
            f"@{student['telegram_username']}"
            if student["telegram_username"]
            else "Not set"
        )
        lines.append(
            f"ID: {student['id']}\n"
            f"Name: {student['full_name']}\n"
            f"Stream: {student['stream']}\n"
            f"Department: {student['department']}\n"
            f"Username: {username}\n"
            f"Payment reference: {student['payment_reference']}\n"
            f"Registered: {student['registered_at']}\n"
            f"Approve: /approve {student['id']}\n"
            f"Reject: /reject {student['id']}\n"
            "-------------------------"
        )

    # Keep messages within Telegram's message length limit.
    message = ""
    for line in lines:
        if len(message) + len(line) + 1 > 3500:
            await update.effective_message.reply_text(message)
            message = ""
        message += line + "\n"

    if message:
        await update.effective_message.reply_text(message)


async def send_academy_invite(bot, student):
    chat_id = os.getenv("ACADEMY_CHAT_ID")

    if not chat_id:
        raise ValueError(
            "ACADEMY_CHAT_ID is missing from the .env file"
        )

    chat_id = int(chat_id)

    invite = await bot.create_chat_invite_link(
        chat_id=chat_id,
        name=f"Student {student['id']}",
        member_limit=1,
    )

    await bot.send_message(
        chat_id=student["telegram_id"],
        text=(
            "🎓 Congratulations! Your Hailestack Academy "
            "registration has been approved!\n\n"
            "Join the Academy using your personal invitation:\n"
            f"{invite.invite_link}\n\n"
            "This invitation allows one successful join."
        ),
    )

async def decide_registration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    decision: str,
):
    if not await admin_only(update):
        return

    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(
            f"Usage: /{decision} <registration_id>"
        )
        return

    student_id = int(context.args[0])

    try:
        updated = set_student_status(student_id, decision)

        if updated is None:
            existing = get_student(student_id)

            if existing is None:
                message = f"Student {student_id} was not found."
            else:
                message = (
                    f"Registration {student_id} has already been "
                    f"processed.\nCurrent status: "
                    f"{existing['payment_status'].upper()}"
                )

            await update.effective_message.reply_text(message)
            return

        student = get_student(student_id)

        if student is None:
            await update.effective_message.reply_text(
                f"Registration {student_id} was updated, "
                "but the student record could not be retrieved."
            )
            return

    except Exception as exc:
        print(f"Decision error for student {student_id}: {exc}")
        await update.effective_message.reply_text(
            "Database error. Check the terminal for details."
        )
        return

    if decision == "approved":
        try:
            await send_academy_invite(context.bot, student)
            await update.effective_message.reply_text(
                f"Student {student_id} approved. "
                "Academy invitation sent."
            )
        except Exception as exc:
            print(
                f"Invitation error for student {student_id}: {exc}"
            )
            await update.effective_message.reply_text(
                f"Student {student_id} is approved, but the "
                "invitation could not be sent. Check the bot "
                "permissions and Academy chat ID."
            )
    else:
        try:
            await context.bot.send_message(
                chat_id=student["telegram_id"],
                text=(
                    "Your Hailestack Academy registration "
                    "has been rejected. If you believe this "
                    "is a mistake, please contact the administrator."
                ),
            )
            await update.effective_message.reply_text(
                f"Student {student_id} rejected and notified."
            )
        except Exception as exc:
            print(
                f"Rejection notification error for "
                f"student {student_id}: {exc}"
            )
            await update.effective_message.reply_text(
                f"Student {student_id} rejected in the database, "
                "but the student could not be notified."
            )
            


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Chat ID: {update.effective_chat.id}"
    )
    
async def show_channel_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.channel_post:
        print(
            "ACADEMY CHANNEL ID:",
            update.channel_post.chat.id
        )

async def approve_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await decide_registration(update, context, "approved")


async def reject_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await decide_registration(update, context, "rejected")




def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing from .env")

    if not ADMIN_IDS:
        raise RuntimeError(
            "ADMIN_IDS is missing or invalid in .env. "
            "Add your numeric Telegram user ID."
        )

    init_db()
    app = Application.builder().token(TOKEN).build()

    registration = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(begin, pattern="^register$")
        ],
        states={
            NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    get_name,
                )
            ],
            STREAM: [
                CallbackQueryHandler(
                    get_stream,
                    pattern="^(social|software)$",
                )
            ],
            DEPARTMENT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    get_department,
                )
            ],
            PAYMENT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    get_payment,
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
    )

    # Temporary channel ID diagnostic handler
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            show_channel_id,
        )
    )

    # User commands and registration
    app.add_handler(CommandHandler("start", start))
    app.add_handler(registration)

    # Admin and diagnostic commands
    app.add_handler(CommandHandler("chatid", chatid))
    app.add_handler(CommandHandler("pending", pending_command))
    app.add_handler(CommandHandler("approve", approve_command))
    app.add_handler(CommandHandler("reject", reject_command))

    print("Hailestack Academy bot is running!")
    app.run_polling()


if __name__ == "__main__":
    main()

