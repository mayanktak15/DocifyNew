"""Run with TELEGRAM_BOT_TOKEN set: python -m bots.telegram_bot."""
import os
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from chatbot.service import documents
from chatbot import respond
from bots.rate_limit import bot_limiter
from bots.accounts import dispatch

NOTICE = 'Docify is a prototype. Do not send personal health details here. For emergencies, contact local emergency services.'


async def start(update, context):
    if not await permitted(update):
        return
    keyboard = [[InlineKeyboardButton(doc['question'], callback_data=f'faq:{i}')]
                for i, doc in enumerate(documents()[:5])]
    await update.effective_message.reply_text(
        NOTICE + '\n/ask QUESTION answers platform questions. In private chat, use /link CODE, /consult DESCRIPTION, /status or /unlink.',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def quick_reply(update, context):
    callback = update.callback_query
    await callback.answer()
    if not await permitted(update):
        return
    index = int(callback.data.split(':')[1])
    if index < len(documents()):
        await update.effective_message.reply_text(documents()[index]['answer'])


async def permitted(update):
    user = update.effective_user
    result = await asyncio.to_thread(bot_limiter.check, 'telegram', str(user.id) if user else '')
    if result != 'allowed':
        await update.effective_message.reply_text('Too many requests or service temporarily unavailable. Please try again later.')
        return False
    return True


async def ask(update, context):
    if not await permitted(update):
        return
    question = ' '.join(context.args).strip()
    if not question:
        await update.effective_message.reply_text('Use /ask followed by a platform question. ' + NOTICE)
        return
    await update.effective_message.reply_text(respond(question[:1000])['reply'] + '\n\n' + NOTICE)


async def account(update, context):
    if not await permitted(update):
        return
    if update.effective_chat.type != 'private':
        await update.effective_message.reply_text('Use account commands in a private chat.')
        return
    command = update.effective_message.text.split()[0][1:].split('@')[0]
    reply = await asyncio.to_thread(dispatch, 'telegram', str(update.effective_user.id), command, ' '.join(context.args))
    await update.effective_message.reply_text(reply)


def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise RuntimeError('Set TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(['start', 'help'], start))
    app.add_handler(CommandHandler('ask', ask))
    app.add_handler(CommandHandler(['link', 'consult', 'status', 'unlink'], account))
    app.add_handler(CallbackQueryHandler(quick_reply, pattern=r'^faq:[0-9]{1,2}$'))
    app.run_polling()


if __name__ == '__main__':
    main()
