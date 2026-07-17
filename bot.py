import os
import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import aiohttp
from datetime import datetime
from typing import Dict, List, Any
import io
import asyncpg
import json

# ============================================
# CONFIGURATION
# ============================================
API_KEY = os.getenv("BRIXHUB_API_KEY")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = "https://api.brixhub.is/api/v1"
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}
ADMIN_ROLE_ID = 1527750818986590248

# ============================================
# BASE DE DONNÉES POSTGRESQL
# ============================================
class Database:
    def __init__(self):
        self.pool = None
    
    async def init(self):
        try:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                print("❌ DATABASE_URL non définie !")
                return False
            
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=10
            )
            
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        credits INTEGER DEFAULT 10,
                        total_searches INTEGER DEFAULT 0
                    )
                """)
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS history (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT REFERENCES users(user_id),
                        query TEXT,
                        results INTEGER,
                        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bans (
                        user_id TEXT PRIMARY KEY
                    )
                """)
                
            print("✅ Base de données PostgreSQL connectée")
            return True
            
        except Exception as e:
            print(f"❌ Erreur PostgreSQL: {e}")
            return False
    
    async def get_user(self, user_id: str):
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            if not result:
                await conn.execute(
                    "INSERT INTO users (user_id, credits) VALUES ($1, 10)", user_id
                )
                return {"credits": 10, "total_searches": 0}
            return dict(result)
    
    async def add_credits(self, user_id: str, amount: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
                amount, user_id
            )
    
    async def remove_credits(self, user_id: str, amount: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET credits = GREATEST(credits - $1, 0) WHERE user_id = $2",
                amount, user_id
            )
    
    async def add_search_history(self, user_id: str, query: str, results: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO history (user_id, query, results) VALUES ($1, $2, $3)",
                user_id, query, results
            )
            await conn.execute(
                "UPDATE users SET total_searches = total_searches + 1 WHERE user_id = $1",
                user_id
            )
            await conn.execute("""
                DELETE FROM history 
                WHERE id IN (
                    SELECT id FROM history 
                    WHERE user_id = $1 
                    ORDER BY date DESC 
                    OFFSET 10
                )
            """, user_id)
    
    async def get_history(self, user_id: str, limit: int = 10):
        async with self.pool.acquire() as conn:
            results = await conn.fetch(
                "SELECT query, results, date FROM history WHERE user_id = $1 ORDER BY date DESC LIMIT $2",
                user_id, limit
            )
            return [dict(r) for r in results]
    
    async def get_credits(self, user_id: str) -> int:
        user = await self.get_user(user_id)
        return user.get("credits", 0)
    
    async def get_total_searches(self, user_id: str) -> int:
        user = await self.get_user(user_id)
        return user.get("total_searches", 0)
    
    async def ban_user(self, user_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO bans (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
    
    async def unban_user(self, user_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM bans WHERE user_id = $1", user_id
            )
    
    async def is_banned(self, user_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT user_id FROM bans WHERE user_id = $1", user_id
            )
            return result is not None

db = Database()

# ============================================
# API HANDLER
# ============================================
class LookupAPI:
    @staticmethod
    async def search(data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BASE_URL}/search",
                    json=data,
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"status": response.status, "error": await response.text()}
        except Exception as e:
            return {"status": 500, "error": str(e)}
    
    @staticmethod
    async def lookup_email(email: str) -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BASE_URL}/lookup/email/{email}",
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"status": response.status, "error": await response.text()}
        except Exception as e:
            return {"status": 500, "error": str(e)}
    
    @staticmethod
    async def lookup_phone(phone: str) -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BASE_URL}/lookup/phone/{phone}",
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"status": response.status, "error": await response.text()}
        except Exception as e:
            return {"status": 500, "error": str(e)}
    
    @staticmethod
    async def lookup_iban(iban: str) -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BASE_URL}/lookup/iban/{iban}",
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"status": response.status, "error": await response.text()}
        except Exception as e:
            return {"status": 500, "error": str(e)}
    
    @staticmethod
    async def get_me() -> Dict[str, Any]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BASE_URL}/me",
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"status": response.status, "error": await response.text()}
        except Exception as e:
            return {"status": 500, "error": str(e)}

# ============================================
# MODAL DE RECHERCHE
# ============================================
class SearchModal(Modal):
    def __init__(self):
        super().__init__(title="🔍 Recherche")
        
        self.prenom = TextInput(label="Prénom", placeholder="Jean", required=False, max_length=50)
        self.add_item(self.prenom)
        
        self.nom = TextInput(label="Nom de famille", placeholder="Dupont", required=False, max_length=50)
        self.add_item(self.nom)
        
        self.email = TextInput(label="Email", placeholder="jean.dupont@email.com", required=False, max_length=100)
        self.add_item(self.email)
        
        self.telephone = TextInput(label="Téléphone", placeholder="0612345678", required=False, max_length=20)
        self.add_item(self.telephone)
        
        self.ville = TextInput(label="Ville", placeholder="Paris", required=False, max_length=50)
        self.add_item(self.ville)
    
    async def on_submit(self, interaction: discord.Interaction):
        if await db.is_banned(str(interaction.user.id)):
            embed = discord.Embed(title="⛔ Accès refusé", description="Vous avez été banni.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        credits = await db.get_credits(str(interaction.user.id))
        if credits <= 0:
            embed = discord.Embed(title="❌ Crédits insuffisants", description="Contactez un administrateur.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        query = {}
        if self.prenom.value: query["prenom"] = self.prenom.value
        if self.nom.value: query["nom_famille"] = self.nom.value
        if self.email.value: query["email"] = self.email.value
        if self.telephone.value: query["telephone"] = self.telephone.value
        if self.ville.value: query["ville"] = self.ville.value
        
        if not query:
            embed = discord.Embed(title="❌ Erreur", description="Veuillez remplir au moins un champ !", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        query["flexible"] = True
        query["per_page"] = 10
        
        try:
            result = await LookupAPI.search(query)
            
            if result.get("status") == 200:
                results = result.get("data", {}).get("results", [])
                
                if results:
                    await db.remove_credits(str(interaction.user.id), 1)
                    query_str = ", ".join([f"{k}={v}" for k, v in query.items() if k not in ["flexible", "per_page"]])
                    await db.add_search_history(str(interaction.user.id), query_str, len(results))
                    
                    view = PaginationView(results, page=0, query=query, user_id=interaction.user.id)
                    embed = view.create_embed()
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    embed = discord.Embed(title="❌ Aucun résultat", description="Aucune personne trouvée.", color=discord.Color.orange())
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(title="❌ Erreur API", description=f"Erreur: {result.get('status', 500)}", color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except Exception as e:
            embed = discord.Embed(title="❌ Erreur", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# LOOKUP MODAL
# ============================================
class LookupModal(Modal):
    def __init__(self, lookup_type: str):
        super().__init__(title=f"🔍 Lookup {lookup_type.capitalize()}")
        self.lookup_type = lookup_type
        
        placeholder = {"email": "jean.dupont@gmail.com", "phone": "0612345678", "iban": "FR7630006000011234567890189"}.get(lookup_type, "")
        label = {"email": "Adresse email", "phone": "Numéro de téléphone", "iban": "IBAN"}.get(lookup_type, lookup_type)
        
        self.value_input = TextInput(label=label, placeholder=placeholder, required=True, max_length=100)
        self.add_item(self.value_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        if await db.is_banned(str(interaction.user.id)):
            embed = discord.Embed(title="⛔ Accès refusé", description="Vous avez été banni.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        credits = await db.get_credits(str(interaction.user.id))
        if credits <= 0:
            embed = discord.Embed(title="❌ Crédits insuffisants", description="Contactez un administrateur.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            value = self.value_input.value.strip()
            
            if self.lookup_type == "email":
                result = await LookupAPI.lookup_email(value)
            elif self.lookup_type == "phone":
                result = await LookupAPI.lookup_phone(value)
            elif self.lookup_type == "iban":
                result = await LookupAPI.lookup_iban(value)
            else:
                raise ValueError("Type non supporté")
            
            if result.get("status") == 200:
                results = result.get("data", {}).get("results", [])
                
                if results:
                    await db.remove_credits(str(interaction.user.id), 1)
                    await db.add_search_history(str(interaction.user.id), f"{self.lookup_type}={value}", len(results))
                    
                    embed = discord.Embed(title=f"🔍 Résultats lookup {self.lookup_type}", description=f"**{len(results)}** résultat(s)", color=discord.Color.green())
                    
                    for i, record in enumerate(results[:5], 1):
                        fields = [f"**{k}**: {v}" for k, v in record.items() if not k.startswith("_") and v]
                        if fields:
                            embed.add_field(name=f"📝 #{i}", value="\n".join(fields[:10]), inline=False)
                    
                    embed.set_footer(text=f"Recherche: {value} • Created by Index")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    embed = discord.Embed(title="❌ Aucun résultat", description=f"Aucun enregistrement trouvé.", color=discord.Color.orange())
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(title="❌ Erreur API", description=f"Erreur: {result.get('status', 500)}", color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except Exception as e:
            embed = discord.Embed(title="❌ Erreur", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# PAGINATION VIEW
# ============================================
class PaginationView(View):
    def __init__(self, results: List[Dict], page: int = 0, query: Dict = None, user_id: int = None):
        super().__init__(timeout=300)
        self.results = results
        self.page = page
        self.query = query or {}
        self.user_id = user_id
        self.total_pages = max(1, len(results))
        self.update_buttons()
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id and interaction.user.id != self.user_id:
            embed = discord.Embed(title="⛔ Accès refusé", description="Ces résultats sont privés.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True
    
    def create_embed(self):
        embed = discord.Embed(title="🔍 Résultats", color=discord.Color.blue(), timestamp=datetime.now())
        
        if self.page < len(self.results):
            person = self.results[self.page]
            fields = []
            
            for key, value in person.items():
                if key.startswith("_"): continue
                if value:
                    key_fr = {"prenom": "Prénom", "nom_famille": "Nom", "email": "Email", "telephone": "Téléphone", "ville": "Ville"}.get(key, key)
                    fields.append(f"**{key_fr}**: {value}")
            
            embed.description = "\n".join(fields) if fields else "Aucune information"
            embed.add_field(name="👤 Personne", value=f"**#{self.page + 1}/{len(self.results)}**", inline=False)
        
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} • Created by Index")
        return embed
    
    def update_buttons(self):
        self.clear_items()
        
        prev_button = Button(label="◀", style=discord.ButtonStyle.primary, disabled=self.page == 0)
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        page_button = Button(label=f"{self.page + 1}/{self.total_pages}", style=discord.ButtonStyle.grey, disabled=True)
        self.add_item(page_button)
        
        next_button = Button(label="▶", style=discord.ButtonStyle.primary, disabled=self.page >= self.total_pages - 1)
        next_button.callback = self.next_page
        self.add_item(next_button)
        
        close_button = Button(label="❌", style=discord.ButtonStyle.danger)
        close_button.callback = self.close_panel
        self.add_item(close_button)
    
    async def update_embed(self, interaction: discord.Interaction):
        embed = self.create_embed()
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def previous_page(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            await self.update_embed(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_embed(interaction)
    
    async def close_panel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="✅ Panel fermé", embed=None, view=None)

# ============================================
# PANEL VIEW
# ============================================
class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🔍 Recherche", style=discord.ButtonStyle.primary)
    async def search_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(SearchModal())
    
    @discord.ui.button(label="📧 Lookup Email", style=discord.ButtonStyle.success)
    async def lookup_email_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(LookupModal("email"))
    
    @discord.ui.button(label="📱 Lookup Phone", style=discord.ButtonStyle.success)
    async def lookup_phone_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(LookupModal("phone"))
    
    @discord.ui.button(label="🏦 Lookup IBAN", style=discord.ButtonStyle.success)
    async def lookup_iban_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(LookupModal("iban"))
    
    @discord.ui.button(label="📊 Mon compte", style=discord.ButtonStyle.secondary)
    async def account_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            user_data = await db.get_user(str(interaction.user.id))
            history = await db.get_history(str(interaction.user.id), 5)
            
            embed = discord.Embed(title="📊 Mon compte", color=discord.Color.purple(), timestamp=datetime.now())
            embed.add_field(name="💰 Crédits", value=f"**{user_data.get('credits', 0)}**", inline=True)
            embed.add_field(name="🔍 Recherches", value=f"**{user_data.get('total_searches', 0)}**", inline=True)
            
            me = await LookupAPI.get_me()
            if me.get("status") == 200:
                data = me.get("data", {})
                embed.add_field(name="📋 Plan", value=data.get("plan", "Inconnu"), inline=True)
                embed.add_field(name="📊 Quota", value=data.get("daily_quota", 0), inline=True)
                embed.add_field(name="📈 Utilisé", value=data.get("daily_used", 0), inline=True)
            
            if history:
                history_text = ""
                for i, entry in enumerate(history[:5], 1):
                    date = entry["date"].strftime("%d/%m %H:%M") if isinstance(entry["date"], datetime) else entry["date"][:16]
                    history_text += f"`{i}. {entry['query']}` → {entry['results']} résultats\n"
                embed.add_field(name="📜 Dernières recherches", value=history_text, inline=False)
            
            embed.set_footer(text="Created by Index")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(title="❌ Erreur", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# FONCTIONS ADMIN
# ============================================
def is_admin(interaction: discord.Interaction) -> bool:
    role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
    return role and role in interaction.user.roles

# ============================================
# CRÉATION DU BOT (ICI !)
# ============================================
class Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    
    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Commandes synchronisées")

bot = Bot()  # <-- BOT CRÉÉ ICI

# ============================================
# COMMANDES (APRÈS LA CRÉATION DE bot)
# ============================================
@bot.tree.command(name="panel", description="📊 Ouvrir le panel de recherche")
async def panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔍 **Csint Lookup**",
        description="🔎 **Recherche dans plus de 33 milliards de données indexées en quelques millisecondes**",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    embed.set_image(url="https://cdn.discordapp.com/attachments/1477415267452719208/1508616783903461417/logo.PNG")
    embed.set_footer(text="⚡ Ultra rapide • Fiable • Created by Index")
    
    view = PanelView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="addcredits", description="Ajouter des crédits (Admin)")
async def add_credits(interaction: discord.Interaction, utilisateur: discord.Member, montant: int):
    if not is_admin(interaction):
        embed = discord.Embed(title="⛔ Accès refusé", description="Admin seulement.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.add_credits(str(utilisateur.id), montant)
    embed = discord.Embed(title="✅ Crédits ajoutés", description=f"{montant} crédit(s) ajouté(s) à {utilisateur.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="removecredits", description="Enlever des crédits (Admin)")
async def remove_credits(interaction: discord.Interaction, utilisateur: discord.Member, montant: int):
    if not is_admin(interaction):
        embed = discord.Embed(title="⛔ Accès refusé", description="Admin seulement.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.remove_credits(str(utilisateur.id), montant)
    embed = discord.Embed(title="✅ Crédits retirés", description=f"{montant} crédit(s) retiré(s) à {utilisateur.mention}", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="look", description="Voir les statistiques d'un utilisateur")
async def look(interaction: discord.Interaction, utilisateur: discord.Member):
    if utilisateur.id != interaction.user.id and not is_admin(interaction):
        embed = discord.Embed(title="⛔ Accès refusé", description="Vous ne pouvez voir que vos propres stats.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    user_data = await db.get_user(str(utilisateur.id))
    history = await db.get_history(str(utilisateur.id), 10)
    
    embed = discord.Embed(title=f"📊 Stats de {utilisateur.display_name}", color=discord.Color.blue(), timestamp=datetime.now())
    embed.add_field(name="💰 Crédits", value=f"**{user_data.get('credits', 0)}**", inline=True)
    embed.add_field(name="🔍 Recherches", value=f"**{user_data.get('total_searches', 0)}**", inline=True)
    embed.add_field(name="🚫 Banni", value="✅ Oui" if await db.is_banned(str(utilisateur.id)) else "❌ Non", inline=True)
    
    if history:
        history_text = ""
        for i, entry in enumerate(history[:10], 1):
            date = entry["date"].strftime("%d/%m %H:%M") if isinstance(entry["date"], datetime) else entry["date"][:16]
            history_text += f"`{i}. {entry['query']}` → {entry['results']} résultats ({date})\n"
        embed.add_field(name="📜 10 dernières recherches", value=history_text, inline=False)
    
    embed.set_footer(text="Created by Index")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ban", description="Bannir un utilisateur (Admin)")
async def ban_user(interaction: discord.Interaction, utilisateur: discord.Member):
    if not is_admin(interaction):
        embed = discord.Embed(title="⛔ Accès refusé", description="Admin seulement.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.ban_user(str(utilisateur.id))
    embed = discord.Embed(title="⛔ Utilisateur banni", description=f"{utilisateur.mention} a été banni.", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unban", description="Débannir un utilisateur (Admin)")
async def unban_user(interaction: discord.Interaction, utilisateur: discord.Member):
    if not is_admin(interaction):
        embed = discord.Embed(title="⛔ Accès refusé", description="Admin seulement.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.unban_user(str(utilisateur.id))
    embed = discord.Embed(title="✅ Utilisateur débanni", description=f"{utilisateur.mention} peut maintenant effectuer des recherches.", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

# ============================================
# ÉVÉNEMENTS
# ============================================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")
    print(f"✅ Invité dans {len(bot.guilds)} serveurs")
    print(f"✅ Admin Role ID: {ADMIN_ROLE_ID}")
    
    success = await db.init()
    if not success:
        print("❌ Échec de connexion à la base de données")
    
    print("✅ Created by Index")

# ============================================
# LANCEMENT
# ============================================
if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ ERREUR: DISCORD_TOKEN non défini !")
    elif not API_KEY:
        print("❌ ERREUR: BRIXHUB_API_KEY non défini !")
    else:
        try:
            bot.run(BOT_TOKEN)
        except discord.LoginFailure:
            print("❌ ERREUR: Token Discord invalide !")
        except Exception as e:
            print(f"❌ ERREUR: {e}")