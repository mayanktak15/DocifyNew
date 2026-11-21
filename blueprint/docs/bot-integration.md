# 🤖 Bot Integration Guide

> How to build and deploy Telegram, WhatsApp, and Discord bots that integrate with the Docify v2 chatbot pipeline.

---

## 1. Architecture Overview

All bots share the same chatbot pipeline — the same RAG engine, same FAISS index, same LLM provider chain. Each bot is a thin adapter that:
1. Receives messages from its platform
2. Authenticates the user (via linked account + JWT)
3. Routes the query through `ChatbotService.get_response()`
4. Formats the response for the platform
5. Sends it back

```
Telegram ──┐
WhatsApp ──┼──→ ChatbotService → HybridRetriever → LLM Chain → Response
Discord  ──┘
```

---

## 2. Telegram Bot

### 2.1 Setup

1. **Create bot** via [@BotFather](https://t.me/BotFather) on Telegram
2. Get the bot token
3. Set environment variable: `TELEGRAM_BOT_TOKEN=your_token_here`

### 2.2 Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + setup instructions |
| `/help` | List available commands |
| `/link <email> <token>` | Link Telegram account to Docify |
| `/ask <question>` | Ask the AI chatbot |
| `/consult <symptoms>` | Create a new consultation |
| `/status` | Check latest consultation status |
| `/history` | View recent chat history |

### 2.3 Implementation

```python
# bots/telegram_bot.py
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from chatbot import get_response
from bots.bot_auth import BotAuthService

RATE_LIMIT = {}  # {user_id: [timestamps]}

async def cmd_start(update, context):
    await update.message.reply_text(
        "👋 Welcome to Docify Online!\n\n"
        "I'm your medical assistant bot. Here's what I can do:\n"
        "• /ask <question> — Ask a health question\n"
        "• /consult <symptoms> — Submit a consultation\n"
        "• /status — Check consultation status\n"
        "• /link <email> <token> — Link your Docify account\n\n"
        "🔒 Link your account to access all features!"
    )

async def cmd_ask(update, context):
    if not _check_rate_limit(update.effective_user.id):
        await update.message.reply_text("⏳ Rate limit reached. Try again in a minute.")
        return
    
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Usage: /ask <your question>\nExample: /ask What is Docify?")
        return
    
    response = get_response(query)
    await update.message.reply_text(response or "Sorry, I couldn't generate a response.")

async def cmd_consult(update, context):
    auth = BotAuthService()
    user = auth.get_user('telegram', update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "❌ Account not linked!\n"
            "Use /link <email> <token> to connect your Docify account."
        )
        return
    
    symptoms = ' '.join(context.args)
    if not symptoms:
        await update.message.reply_text("Usage: /consult <your symptoms>")
        return
    
    # Create consultation via service
    consultation = create_consultation(user.id, symptoms)
    await update.message.reply_text(
        f"✅ Consultation #{consultation.id} created!\n"
        f"📋 Status: {consultation.status}\n"
        f"🩺 A doctor will review your symptoms soon."
    )

def main():
    token = os.environ['TELEGRAM_BOT_TOKEN']
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('help', cmd_start))
    app.add_handler(CommandHandler('ask', cmd_ask))
    app.add_handler(CommandHandler('consult', cmd_consult))
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('link', cmd_link))
    
    # Fallback: treat plain messages as /ask
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == '__main__':
    main()
```

### 2.4 Requirements
```
python-telegram-bot>=21.0
```

---

## 3. WhatsApp Bot (Twilio)

### 3.1 Setup

1. Create a [Twilio account](https://www.twilio.com/)
2. Enable WhatsApp sandbox or get a production number
3. Set webhook URL to `https://yourdomain.com/webhook/whatsapp`
4. Set environment variables:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxx
   TWILIO_AUTH_TOKEN=xxxxx
   TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
   ```

### 3.2 Webhook Handler

```python
# bots/whatsapp_bot.py
from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

whatsapp_bp = Blueprint('whatsapp', __name__)

@whatsapp_bp.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    # Validate Twilio signature
    validator = RequestValidator(os.environ['TWILIO_AUTH_TOKEN'])
    if not validator.validate(
        request.url, request.form, request.headers.get('X-Twilio-Signature', '')
    ):
        abort(403)
    
    incoming_msg = request.form.get('Body', '').strip()
    from_number = request.form.get('From', '')
    
    # Get chatbot response
    response = get_response(incoming_msg)
    
    # Build Twilio response
    resp = MessagingResponse()
    resp.message(response or "I couldn't process your message. Please try again.")
    
    return str(resp)
```

### 3.3 Requirements
```
twilio>=9.0
```

---

## 4. Discord Bot

### 4.1 Setup

1. Create application at [Discord Developer Portal](https://discord.com/developers)
2. Create a Bot user and get the token
3. Enable necessary Gateway Intents (Message Content)
4. Generate invite URL with `bot` + `applications.commands` scopes
5. Set environment variable: `DISCORD_BOT_TOKEN=your_token_here`

### 4.2 Implementation

```python
# bots/discord_bot.py
import discord
from discord import app_commands
from chatbot import get_response

class DocifyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    
    async def setup_hook(self):
        await self.tree.sync()
    
    async def on_ready(self):
        print(f'Discord bot logged in as {self.user}')

client = DocifyBot()

@client.tree.command(name="ask", description="Ask the Docify medical chatbot")
@app_commands.describe(question="Your health or platform question")
async def slash_ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    
    response = get_response(question)
    
    embed = discord.Embed(
        title="🩺 Docify Assistant",
        description=response or "No answer available.",
        color=discord.Color.green()
    )
    embed.set_footer(text="Docify Online • AI Medical Assistant")
    
    await interaction.followup.send(embed=embed)

@client.tree.command(name="consult", description="Submit a consultation")
@app_commands.describe(symptoms="Describe your symptoms")
async def slash_consult(interaction: discord.Interaction, symptoms: str):
    auth = BotAuthService()
    user = auth.get_user('discord', interaction.user.id)
    
    if not user:
        await interaction.response.send_message(
            "❌ Link your Docify account first!\n"
            "Use `/link <email> <token>` to connect.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer()
    consultation = create_consultation(user.id, symptoms)
    
    embed = discord.Embed(
        title="✅ Consultation Created",
        color=discord.Color.blue()
    )
    embed.add_field(name="ID", value=f"#{consultation.id}", inline=True)
    embed.add_field(name="Status", value=consultation.status, inline=True)
    embed.add_field(name="Symptoms", value=symptoms, inline=False)
    
    await interaction.followup.send(embed=embed)

client.run(os.environ['DISCORD_BOT_TOKEN'])
```

### 4.3 Requirements
```
discord.py>=2.4
```

---

## 5. User Linking Flow

```
1. User registers on Docify web → gets account
2. User generates a linking token from profile page
3. User sends /link <email> <token> in Telegram/Discord
4. Bot verifies JWT token matches the email
5. Bot stores platform_id → user_id mapping
6. User can now use /consult, /status (requires auth)
```

### Token Generation (Web Side)
```python
@dashboard_bp.route('/generate_bot_token', methods=['POST'])
@login_required_page
def generate_bot_token():
    user = get_current_user()
    token = user.generate_jwt(expires_in=600)  # 10 min expiry
    return jsonify({"token": token, "expires_in": 600})
```

---

## 6. Rate Limiting for Bots

| Platform | Limit | Storage |
|----------|-------|---------|
| Telegram | 10 messages/minute per user | Redis `ratelimit:telegram:{user_id}` |
| WhatsApp | 10 messages/minute per number | Redis `ratelimit:whatsapp:{phone}` |
| Discord | 10 commands/minute per user | Redis `ratelimit:discord:{user_id}` |

---

## 7. Docker Compose Integration

```yaml
# Add to docker-compose.yml

  telegram-bot:
    build: .
    command: python -m bots.telegram_bot
    depends_on:
      web: { condition: service_healthy }
      redis: { condition: service_healthy }
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      REDIS_URL: redis://redis:6379/0
      DATABASE_URL: postgresql://docify:${DB_PASSWORD}@db:5432/docify
    restart: unless-stopped

  discord-bot:
    build: .
    command: python -m bots.discord_bot
    depends_on:
      web: { condition: service_healthy }
      redis: { condition: service_healthy }
    environment:
      DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN}
      REDIS_URL: redis://redis:6379/0
      DATABASE_URL: postgresql://docify:${DB_PASSWORD}@db:5432/docify
    restart: unless-stopped
```

> **Note**: WhatsApp doesn't need a separate service — it's handled by the Flask webhook endpoint in the web service.
