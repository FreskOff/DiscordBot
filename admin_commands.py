import discord
from discord.ext import commands
from discord.utils import get
from dotenv import load_dotenv
import os
import time
import asyncio
import re
import random
from collections import defaultdict

# Загрузка токена из файла .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Настройка ID ролей
ROLES = {
    'moderator_role': 1292360394626564128,  # ID роли модератора
    'mute_role': 1292360480350015498        # ID роли мута
}

# Инициализация бота
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Хранение истории мутов, варнов и банов
punishment_history = defaultdict(list)

# Логи действий в отдельный канал
async def log_action(ctx, action, member, reason=None):
    log_channel = discord.utils.get(ctx.guild.text_channels, name="admin-logs")
    if not log_channel:
        return
    log_message = f"{ctx.author} выполнил команду {action} на {member.name}"
    if reason:
        log_message += f" с причиной: {reason}"
    await log_channel.send(log_message)

# Предупреждение пользователя через ЛС
async def warn_user(ctx, member, warning_message):
    try:
        await member.send(f"Вам выдано предупреждение: {warning_message}")
    except discord.Forbidden:
        await ctx.send(f"Не удалось отправить предупреждение {member.name}, у него закрыты ЛС.")

# Проверка наличия роли модератора
def has_moderator_role(ctx):
    moderator_role = discord.utils.get(ctx.guild.roles, id=ROLES['moderator_role'])
    return moderator_role in ctx.author.roles

# Функция для преобразования строки времени в секунды
def parse_time(time_str):
    time_units = {'m': 60, 'h': 3600, 'd': 86400}  # минуты, часы, дни
    match = re.match(r"(\d+)([mhd])", time_str)
    
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        return amount * time_units[unit]
    else:
        raise ValueError("Неверный формат времени. Используйте m (минуты), h (часы), или d (дни).")
# НОВОЕ 
# Функция для логирования изменений сообщений
@bot.event
async def on_message_edit(before, after):
    log_channel = discord.utils.get(before.guild.text_channels, name="logs")
    if log_channel is None:
        return
    
    if before.content != after.content:  # Проверяем, изменилось ли сообщение
        embed = discord.Embed(title="Сообщение изменено", color=discord.Color.orange())
        embed.add_field(name="Автор", value=before.author.mention, inline=False)
        embed.add_field(name="До изменения", value=before.content or "Пусто", inline=False)
        embed.add_field(name="После изменения", value=after.content or "Пусто", inline=False)
        embed.add_field(name="Канал", value=before.channel.mention, inline=False)
        await log_channel.send(embed=embed)

# Функция для логирования удалённых сообщений
@bot.event
async def on_message_delete(message):
    log_channel = discord.utils.get(message.guild.text_channels, name="logs")
    if log_channel is None:
        return
    
    embed = discord.Embed(title="Сообщение удалено", color=discord.Color.red())
    embed.add_field(name="Автор", value=message.author.mention, inline=False)
    embed.add_field(name="Содержание", value=message.content or "Пусто", inline=False)
    embed.add_field(name="Канал", value=message.channel.mention, inline=False)
    await log_channel.send(embed=embed)

@bot.command(name='участники')
async def member_count(ctx):
    await ctx.send(f"На сервере {ctx.guild.member_count} участников.")

@bot.command(name='случайный')
async def random_member(ctx):
    random_user = random.choice(ctx.guild.members)
    await ctx.send(f"Случайный участник: {random_user.mention}")


@bot.command(name='мут')
async def mute(ctx, member: discord.Member = None, time: str = None, *, reason=None):
    if not has_moderator_role(ctx):
        await ctx.send("У вас нет прав для выполнения этой команды.")
        return
    
    if member is None or time is None or reason is None:
        await ctx.send("Неправильное использование команды. Пример: !мут @пользователь (время, например 10m) причина")
        return

    try:
        duration_in_seconds = parse_time(time)
    except ValueError as e:
        await ctx.send(str(e))
        return

    mute_role = discord.utils.get(ctx.guild.roles, id=ROLES['mute_role'])
    if mute_role is None:
        await ctx.send("Роль мута не найдена.")
        return
    
    await member.add_roles(mute_role, reason=reason)
    await ctx.send(f"{member.mention} был замьючен на {time} по причине: {reason}")
    
    # Логируем действие
    await log_action(ctx, 'мут', member, reason)
    
    # Записываем в историю
    if member.id not in punishment_history:
        punishment_history[member.id] = []
    punishment_history[member.id].append(f"Мут на {time} по причине: {reason}")
    
    # Снятие мута через заданное время
    await unmute_member_after(ctx, member, duration_in_seconds)

# Функция для автоматического снятия мута
async def unmute_member_after(ctx, member, duration):
    await asyncio.sleep(duration)
    mute_role = discord.utils.get(ctx.guild.roles, id=ROLES['mute_role'])
    if mute_role in member.roles:
        await member.remove_roles(mute_role)
        await ctx.send(f'{member.mention} был размьючен автоматически.')

# Команда !бан с проверкой
@bot.command(name='бан')
async def ban(ctx, member: discord.Member, *, reason=None):
    if not has_moderator_role(ctx):
        await ctx.send("У вас нет прав для выполнения этой команды.")
        return
    
    if not member or not reason:
        await ctx.send("Неправильное использование команды. Пример: !бан @пользователь причина")
        return

    try:
        await ctx.guild.ban(member, reason=reason)
        await ctx.send(f"{member.mention} был забанен по причине: {reason}")
        
        # Логируем действие
        await log_action(ctx, 'бан', member, reason)
        
        # Записываем в историю
        punishment_history[member.id].append(f"Бан по причине: {reason}")
    except discord.Forbidden:
        await ctx.send("Не удалось забанить пользователя. Проверьте права бота.")

# Команда !варн
@bot.command(name='варн')
async def warn(ctx, member: discord.Member, *, reason=None):
    if not has_moderator_role(ctx):
        await ctx.send("У вас нет прав для выполнения этой команды.")
        return
    
    if not member or not reason:
        await ctx.send("Неправильное использование команды. Пример: !варн @пользователь причина")
        return
    
    await warn_user(ctx, member, reason)
    await ctx.send(f"{member.mention} получил предупреждение: {reason}")
    
    # Логируем действие
    await log_action(ctx, 'варн', member, reason)
    
    # Записываем в историю
    punishment_history[member.id].append(f"Варн по причине: {reason}")

# Команда !история для просмотра истории наказаний
@bot.command(name='история')
async def history(ctx, member: discord.Member):
    if not has_moderator_role(ctx):
        await ctx.send("У вас нет прав для выполнения этой команды.")
        return
    
    history = punishment_history.get(member.id, [])
    if not history:
        await ctx.send(f"У {member.mention} нет истории наказаний.")
    else:
        await ctx.send(f"История наказаний {member.mention}:\n" + "\n".join(history))

# Команда !очистка для очистки сообщений
@bot.command(name='очистка')
async def clear(ctx, amount: int):
    if has_moderator_role(ctx):
        deleted = await ctx.channel.purge(limit=amount)
        await ctx.send(f"Очищено {len(deleted)} сообщений.", delete_after=5)
    else:
        await ctx.send("У вас недостаточно прав для выполнения этой команды.")

# Команда !помощь для обычных пользователей
@bot.command(name='помощь')
async def help_command(ctx):
    help_text = """
    **Команды для пользователей:**
    `!помощь` - Вывод всех доступных команд
    `!история @пользователь` - Просмотр истории наказаний пользователя
    `!участники` - Количество участников на сервере
    `!случайный` - Выбор случайного участника на сервере
    """
    await ctx.send(help_text)

# Команда !админпомощь для администраторов
@bot.command(name='админпомощь')
async def admin_help_command(ctx):
    if has_moderator_role(ctx):
        help_text = """
        **Административные команды:**
        `!мут @пользователь (время) причина` - Замьютить пользователя
        `!бан @пользователь причина` - Забанить пользователя
        `!варн @пользователь причина` - Выдать предупреждение
        `!история @пользователь` - Просмотреть историю наказаний пользователя
        `!очистка (количество)` - Очистить сообщения в канале
        `!участники` - Количество участников на сервере
        `!случайный` - Выбор случайного участника на сервере
        """
        await ctx.send(help_text)
    else:
        await ctx.send("У вас нет прав для просмотра админских команд.")

# Новая команда !админы для просмотра списка всех администраторов
@bot.command(name='админы')
async def list_admins(ctx):
    admins = [member.mention for member in ctx.guild.members if ROLES['moderator_role'] in [role.id for role in member.roles]]
    await ctx.send(f"Администраторы сервера: {', '.join(admins)}")

# Запуск бота
bot.run(TOKEN)
