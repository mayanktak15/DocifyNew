"""Run with DISCORD_BOT_TOKEN set: python -m bots.discord_bot."""
import os
import asyncio
import discord
from discord import app_commands
from chatbot import respond
from bots.rate_limit import bot_limiter

NOTICE = 'Docify is a prototype. Do not share personal health details here. For emergencies, contact local emergency services.'


class DocifyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


client = DocifyClient()


@client.tree.command(name='ask', description='Ask a question about the Docify prototype')
async def ask(interaction: discord.Interaction, question: str):
    result = await asyncio.to_thread(bot_limiter.check, 'discord', str(interaction.user.id))
    if result != 'allowed':
        await interaction.response.send_message('Too many requests or service temporarily unavailable. Please try again later.', ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    answer = await asyncio.to_thread(respond, question[:1000])
    embed = discord.Embed(title='Docify', description=answer['reply'], color=0x1B6654)
    embed.set_footer(text=NOTICE)
    await interaction.followup.send(embed=embed, ephemeral=True)


@client.tree.command(description='List common platform questions')
async def faq(interaction: discord.Interaction):
    from chatbot.service import documents
    if await asyncio.to_thread(bot_limiter.check, 'discord', str(interaction.user.id)) != 'allowed':
        await interaction.response.send_message('Please try again later.', ephemeral=True)
        return
    questions = [doc['question'] for doc in documents()[:8]]
    await interaction.response.send_message('Use /ask with a question.\n' + '\n'.join(questions), ephemeral=True)


async def account(interaction, command, argument=''):
    if interaction.guild_id is not None:
        await interaction.response.send_message('Use this command in a direct message.', ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    from bots.accounts import dispatch
    result = await asyncio.to_thread(bot_limiter.check, 'discord', str(interaction.user.id))
    reply = 'Please try again later.'
    if result == 'allowed':
        reply = await asyncio.to_thread(dispatch, 'discord', str(interaction.user.id), command, argument)
    await interaction.followup.send(reply, ephemeral=True)


@client.tree.command()
async def link(interaction: discord.Interaction, code: str):
    await account(interaction, 'link', code)


@client.tree.command()
async def consult(interaction: discord.Interaction, description: str):
    await account(interaction, 'consult', description)


@client.tree.command()
async def status(interaction: discord.Interaction):
    await account(interaction, 'status')


@client.tree.command()
async def unlink(interaction: discord.Interaction):
    await account(interaction, 'unlink')


def main():
    token = os.environ.get('DISCORD_BOT_TOKEN')
    if not token:
        raise RuntimeError('Set DISCORD_BOT_TOKEN')
    client.run(token)


if __name__ == '__main__':
    main()
