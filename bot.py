import os
import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import aiohttp
from datetime import datetime
from typing import Dict, List, Any
import io
import asyncpg
import asyncio

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

# Rôle par défaut (si aucun configuré)
DEFAULT_ADMIN_ROLE_ID = None  # Aucun rôle par défaut

# ============================================
# BASE DE DONNÉES POSTGRESQL
# ============================================
class Database:
    def __init__(self):
        self.pool = None
        self.connected = False
    
    async def init(self):
        try:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                print("❌ DATABASE_URL non définie !")
                return False
            
            print("🔄 Connexion à PostgreSQL...")
            
            self.pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=5,
                timeout=60
            )
            
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
                
                # Table des utilisateurs
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        credits INTEGER DEFAULT 10,
                        total_searches INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Table de l'historique
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS history (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT REFERENCES users(user_id),
                        query TEXT,
                        results INTEGER,
                        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Table des bannissements
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bans (
                        user_id TEXT PRIMARY KEY
                    )
                """)
                
                # Table de configuration (pour stocker le rôle admin)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS config (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                
                # Ajouter la config par défaut si elle n'existe pas
                await conn.execute("""
                    INSERT INTO config (key, value) 
                    VALUES ('admin_role_id', '') 
                    ON CONFLICT (key) DO NOTHING
                """)
            
            self.connected = True
            print("✅ Base de données PostgreSQL connectée")
            return True
            
        except Exception as e:
            print(f"❌ Erreur PostgreSQL: {e}")
            self.connected = False
            return False
    
    async def ensure_connected(self):
        if not self.connected or self.pool is None:
            return await self.init()
        return True
    
    # ========== GESTION UTILISATEURS ==========
    async def get_user(self, user_id: str):
        if not await self.ensure_connected():
            return {"credits": 0, "total_searches": 0, "created_at": None}
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow(
                    "SELECT * FROM users WHERE user_id = $1", user_id
                )
                if not result:
                    await conn.execute(
                        "INSERT INTO users (user_id, credits) VALUES ($1, 10)", user_id
                    )
                    return {"credits": 10, "total_searches": 0, "created_at": datetime.now()}
                return dict(result)
        except Exception as e:
            print(f"❌ Erreur get_user: {e}")
            return {"credits": 0, "total_searches": 0, "created_at": None}
    
    async def add_credits(self, user_id: str, amount: int):
        if not await self.ensure_connected():
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
                    amount, user_id
                )
        except Exception as e:
            print(f"❌ Erreur add_credits: {e}")
    
    async def remove_credits(self, user_id: str, amount: int):
        if not await self.ensure_connected():
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET credits = GREATEST(credits - $1, 0) WHERE user_id = $2",
                    amount, user_id
                )
        except Exception as e:
            print(f"❌ Erreur remove_credits: {e}")
    
    async def add_search_history(self, user_id: str, query: str, results: int):
        if not await self.ensure_connected():
            return
        try:
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
        except Exception as e:
            print(f"❌ Erreur add_search_history: {e}")
    
    async def get_history(self, user_id: str, limit: int = 10):
        if not await self.ensure_connected():
            return []
        try:
            async with self.pool.acquire() as conn:
                results = await conn.fetch(
                    "SELECT query, results, date FROM history WHERE user_id = $1 ORDER BY date DESC LIMIT $2",
                    user_id, limit
                )
                return [dict(r) for r in results]
        except Exception as e:
            print(f"❌ Erreur get_history: {e}")
            return []
    
    async def get_credits(self, user_id: str) -> int:
        user = await self.get_user(user_id)
        return user.get("credits", 0)
    
    async def get_total_searches(self, user_id: str) -> int:
        user = await self.get_user(user_id)
        return user.get("total_searches", 0)
    
    # ========== GESTION BANS ==========
    async def ban_user(self, user_id: str):
        if not await self.ensure_connected():
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO bans (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                    user_id
                )
        except Exception as e:
            print(f"❌ Erreur ban_user: {e}")
    
    async def unban_user(self, user_id: str):
        if not await self.ensure_connected():
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM bans WHERE user_id = $1", user_id
                )
        except Exception as e:
            print(f"❌ Erreur unban_user: {e}")
    
    async def is_banned(self, user_id: str) -> bool:
        if not await self.ensure_connected():
            return False
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow(
                    "SELECT user_id FROM bans WHERE user_id = $1", user_id
                )
                return result is not None
        except Exception as e:
            print(f"❌ Erreur is_banned: {e}")
            return False
    
    # ========== GESTION CONFIG ==========
    async def get_admin_role(self) -> int:
        """Récupère l'ID du rôle admin depuis la base"""
        if not await self.ensure_connected():
            return None
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow(
                    "SELECT value FROM config WHERE key = 'admin_role_id'"
                )
                if result and result["value"]:
                    return int(result["value"])
                return None
        except Exception as e:
            print(f"❌ Erreur get_admin_role: {e}")
            return None
    
    async def set_admin_role(self, role_id: int):
        """Définit l'ID du rôle admin dans la base"""
        if not await self.ensure_connected():
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE config SET value = $1 WHERE key = 'admin_role_id'",
                    str(role_id)
                )
        except Exception as e:
            print(f"❌ Erreur set_admin_role: {e}")

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
# FONCTIONS ADMIN
# ============================================
async def get_admin_role_id() -> int:
    """Récupère l'ID du rôle admin depuis la DB"""
    return await db.get_admin_role()

async def is_admin(interaction: discord.Interaction) -> bool:
    """Vérifie si l'utilisateur a le rôle admin configuré"""
    if not interaction.guild:
        return False
    
    admin_role_id = await get_admin_role_id()
    if not admin_role_id:
        # Aucun rôle configuré → personne n'est admin
        return False
    
    role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
    if not role:
        return False
    
    return role in interaction.user.roles

async def check_admin(interaction: discord.Interaction) -> bool:
    """Vérifie le rôle et envoie un message d'erreur si non autorisé"""
    if not await is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    return True

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
        # Vérifier rôle admin
        if not await is_admin(interaction):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous n'avez pas la permission d'effectuer une recherche.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Vérifier bannissement
        if await db.is_banned(str(interaction.user.id)):
            embed = discord.Embed(title="⛔ Accès refusé", description="Vous avez été banni.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Créer l'utilisateur s'il n'existe pas
        await db.get_user(str(interaction.user.id))
        
        # Vérifier crédits
        credits = await db.get_credits(str(interaction.user.id))
        if credits <= 0:
            embed = discord.Embed(title="❌ Crédits insuffisants", description="Contactez un administrateur pour en obtenir.", color=discord.Color.red())
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
                    embed = discord.Embed(title="❌ Aucun résultat", description="Aucune personne trouvée avec ces critères.", color=discord.Color.orange())
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
        # Vérifier rôle admin
        if not await is_admin(interaction):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous n'avez pas la permission d'effectuer un lookup.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if await db.is_banned(str(interaction.user.id)):
            embed = discord.Embed(title="⛔ Accès refusé", description="Vous avez été banni.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Créer l'utilisateur s'il n'existe pas
        await db.get_user(str(interaction.user.id))
        
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
                    embed = discord.Embed(title="❌ Aucun résultat", description="Aucun enregistrement trouvé.", color=discord.Color.orange())
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
            
            if person.get("prenom"):
                fields.append(f"👤 **Prénom**: {person['prenom']}")
            if person.get("nom_famille"):
                fields.append(f"📛 **Nom**: {person['nom_famille']}")
            if person.get("email"):
                fields.append(f"📧 **Email**: {person['email']}")
            if person.get("telephone"):
                fields.append(f"📱 **Téléphone**: {person['telephone']}")
            if person.get("ville"):
                fields.append(f"🏙️ **Ville**: {person['ville']}")
            if person.get("date_naissance"):
                fields.append(f"🎂 **Naissance**: {person['date_naissance']}")
            if person.get("adresse"):
                fields.append(f"📍 **Adresse**: {person['adresse']}")
            if person.get("code_postal"):
                fields.append(f"📮 **Code postal**: {person['code_postal']}")
            if person.get("_confidence"):
                fields.append(f"🔒 **Confiance**: {person['_confidence']}%")
            if person.get("_sources"):
                sources = ", ".join(person["_sources"][:5])
                if len(person["_sources"]) > 5:
                    sources += f" et {len(person['_sources'])-5} autre(s)"
                fields.append(f"📚 **Sources**: {sources}")
            
            embed.description = "\n".join(fields) if fields else "Aucune information détaillée"
            embed.add_field(name="👤 Personne", value=f"**#{self.page + 1}/{len(self.results)}**", inline=False)
        else:
            embed.description = "Aucun résultat"
        
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
        if not await is_admin(interaction):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous n'avez pas la permission d'utiliser le panel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.send_modal(SearchModal())
    
    @discord.ui.button(label="📧 Lookup Email", style=discord.ButtonStyle.success)
    async def lookup_email_button(self, interaction: discord.Interaction, button: Button):
        if not await is_admin(interaction):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous n'avez pas la permission d'utiliser le panel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.send_modal(LookupModal("email"))
    
    @discord.ui.button(label="📱 Lookup Phone", style=discord.ButtonStyle.success)
    async def lookup_phone_button(self, interaction: discord.Interaction, button: Button):
        if not await is_admin(interaction):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous n'avez pas la permission d'utiliser le panel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.send_modal(LookupModal("phone"))
    
    @discord.ui.button(label="🏦 Lookup IBAN", style=discord.ButtonStyle.success)
    async def lookup_iban_button(self, interaction: discord.Interaction, button: Button):
        if not await is_admin(interaction):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous n'avez pas la permission d'utiliser le panel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.send_modal(LookupModal("iban"))
    
    @discord.ui.button(label="📊 Mon compte", style=discord.ButtonStyle.secondary)
    async def account_button(self, interaction: discord.Interaction, button: Button):
        if not await is_admin(interaction):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous n'avez pas la permission d'utiliser le panel.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            await db.get_user(str(interaction.user.id))
            
            user_data = await db.get_user(str(interaction.user.id))
            history = await db.get_history(str(interaction.user.id), 5)
            
            embed = discord.Embed(title="📊 Mon compte", color=discord.Color.purple(), timestamp=datetime.now())
            embed.add_field(name="💰 Crédits", value=f"**{user_data.get('credits', 0)}**", inline=True)
            embed.add_field(name="🔍 Recherches", value=f"**{user_data.get('total_searches', 0)}**", inline=True)
            embed.add_field(name="🚫 Banni", value="✅ Oui" if await db.is_banned(str(interaction.user.id)) else "❌ Non", inline=True)
            
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
            else:
                embed.add_field(name="📜 Dernières recherches", value="Aucune recherche effectuée", inline=False)
            
            embed.set_footer(text="Created by Index")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(title="❌ Erreur", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# CRÉATION DU BOT
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

bot = Bot()

# ============================================
# COMMANDES
# ============================================
@bot.tree.command(name="panel", description="📊 Ouvrir le panel de recherche")
async def panel(interaction: discord.Interaction):
    if not await is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.get_user(str(interaction.user.id))
    
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

@bot.tree.command(name="config", description="⚙️ Configurer le rôle admin (utilisable 1 fois)")
async def config(interaction: discord.Interaction, role: discord.Role):
    """Définit le rôle qui pourra utiliser toutes les commandes (utilisable 1 fois)"""
    
    # Vérifier si un rôle est déjà configuré
    existing_role_id = await db.get_admin_role()
    if existing_role_id:
        existing_role = discord.utils.get(interaction.guild.roles, id=existing_role_id)
        embed = discord.Embed(
            title="❌ Configuration déjà effectuée",
            description=f"Un rôle admin est déjà configuré : {existing_role.mention if existing_role else 'ID: ' + str(existing_role_id)}\n\nContacte un administrateur pour modifier la configuration.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Définir le nouveau rôle
    await db.set_admin_role(role.id)
    
    embed = discord.Embed(
        title="✅ Configuration terminée",
        description=f"Le rôle **{role.name}** peut maintenant utiliser toutes les commandes du bot.",
        color=discord.Color.green()
    )
    embed.add_field(
        name="📋 Rôle configuré",
        value=f"ID: `{role.id}`\nMention: {role.mention}",
        inline=False
    )
    embed.set_footer(text="Cette configuration ne peut être modifiée qu'en base de données.")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="addcredits", description="💰 Ajouter des crédits")
async def add_credits(interaction: discord.Interaction, utilisateur: discord.Member, montant: int):
    if not await is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if montant <= 0:
        embed = discord.Embed(title="❌ Erreur", description="Le montant doit être supérieur à 0.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.get_user(str(utilisateur.id))
    await db.add_credits(str(utilisateur.id), montant)
    
    embed = discord.Embed(title="✅ Crédits ajoutés", description=f"{montant} crédit(s) ajouté(s) à {utilisateur.mention}", color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="removecredits", description="💰 Enlever des crédits")
async def remove_credits(interaction: discord.Interaction, utilisateur: discord.Member, montant: int):
    if not await is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if montant <= 0:
        embed = discord.Embed(title="❌ Erreur", description="Le montant doit être supérieur à 0.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.get_user(str(utilisateur.id))
    await db.remove_credits(str(utilisateur.id), montant)
    
    embed = discord.Embed(title="✅ Crédits retirés", description=f"{montant} crédit(s) retiré(s) à {utilisateur.mention}", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="look", description="🔍 Voir les statistiques d'un utilisateur")
async def look(interaction: discord.Interaction, utilisateur: discord.Member):
    if not await is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.get_user(str(utilisateur.id))
    
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
    else:
        embed.add_field(name="📜 10 dernières recherches", value="Aucune recherche effectuée", inline=False)
    
    embed.set_footer(text="Created by Index")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ban", description="⛔ Bannir un utilisateur")
async def ban_user(interaction: discord.Interaction, utilisateur: discord.Member):
    if not await is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if utilisateur.id == interaction.user.id:
        embed = discord.Embed(title="❌ Erreur", description="Vous ne pouvez pas vous bannir vous-même.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.ban_user(str(utilisateur.id))
    embed = discord.Embed(title="⛔ Utilisateur banni", description=f"{utilisateur.mention} a été banni.", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unban", description="✅ Débannir un utilisateur")
async def unban_user(interaction: discord.Interaction, utilisateur: discord.Member):
    if not await is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await db.unban_user(str(utilisateur.id))
    embed = discord.Embed(title="✅ Utilisateur débanni", description=f"{utilisateur.mention} peut maintenant effectuer des recherches.", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="checkrole", description="🔍 Vérifier le rôle admin configuré")
async def checkrole(interaction: discord.Interaction):
    admin_role_id = await db.get_admin_role()
    
    embed = discord.Embed(
        title="🔍 Configuration du rôle admin",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    if admin_role_id:
        role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
        if role:
            has_role = role in interaction.user.roles
            embed.add_field(
                name="✅ Rôle configuré",
                value=f"**Nom:** {role.name}\n**ID:** `{role.id}`\n**Mention:** {role.mention}\n\n**Vous avez ce rôle:** {'✅ Oui' if has_role else '❌ Non'}",
                inline=False
            )
        else:
            embed.add_field(
                name="⚠️ Rôle introuvable",
                value=f"Le rôle avec l'ID `{admin_role_id}` n'existe plus dans ce serveur.\n\n💡 Utilise `/config` pour en définir un nouveau.",
                inline=False
            )
    else:
        embed.add_field(
            name="❌ Aucun rôle configuré",
            value="Aucun rôle admin n'a été configuré.\n\n💡 Utilise `/config` pour définir le rôle qui pourra utiliser les commandes.",
            inline=False
        )
    
    # Lister les rôles du serveur
    roles_list = ""
    for r in interaction.guild.roles:
        if r.name != "@everyone":
            roles_list += f"<@&{r.id}> → `{r.id}`\n"
    
    if roles_list:
        embed.add_field(name="📋 Rôles du serveur", value=roles_list[:1000], inline=False)
    
    embed.set_footer(text="Created by Index")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================
# ÉVÉNEMENTS
# ============================================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")
    print(f"✅ Invité dans {len(bot.guilds)} serveurs")
    
    # Initialiser la base de données
    success = await db.init()
    if not success:
        print("❌ Échec de connexion à PostgreSQL - vérifie DATABASE_URL")
    else:
        print("✅ Base de données prête")
        admin_role = await db.get_admin_role()
        if admin_role:
            print(f"✅ Rôle admin configuré: {admin_role}")
        else:
            print("ℹ️ Aucun rôle admin configuré - Utilise /config pour en définir un")
    
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