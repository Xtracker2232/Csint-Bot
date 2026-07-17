import os
import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import aiohttp
from datetime import datetime
from typing import Dict, List, Any
import asyncio
import json
import io

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

# ID du rôle Admin
ADMIN_ROLE_ID = 1527750818986590248

# Fichier de base de données (stockage des crédits, historique, bans)
DB_FILE = "data.json"

# ============================================
# GESTIONNAIRE DE BASE DE DONNÉES
# ============================================
class Database:
    def __init__(self):
        self.data = {}
        self.load()
    
    def load(self):
        try:
            with open(DB_FILE, "r") as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {"users": {}, "bans": []}
            self.save()
    
    def save(self):
        with open(DB_FILE, "w") as f:
            json.dump(self.data, f, indent=2)
    
    def get_user(self, user_id: str):
        if user_id not in self.data["users"]:
            self.data["users"][user_id] = {
                "credits": 0,
                "total_searches": 0,
                "history": []
            }
            self.save()
        return self.data["users"][user_id]
    
    def add_credits(self, user_id: str, amount: int):
        user = self.get_user(user_id)
        user["credits"] += amount
        self.save()
    
    def remove_credits(self, user_id: str, amount: int):
        user = self.get_user(user_id)
        user["credits"] = max(0, user["credits"] - amount)
        self.save()
    
    def add_search_history(self, user_id: str, query: str, results: int):
        user = self.get_user(user_id)
        user["total_searches"] += 1
        user["history"].insert(0, {
            "query": query,
            "results": results,
            "date": datetime.now().isoformat()
        })
        # Garder seulement les 10 dernières recherches
        user["history"] = user["history"][:10]
        self.save()
    
    def ban_user(self, user_id: str):
        if user_id not in self.data["bans"]:
            self.data["bans"].append(user_id)
            self.save()
    
    def unban_user(self, user_id: str):
        if user_id in self.data["bans"]:
            self.data["bans"].remove(user_id)
            self.save()
    
    def is_banned(self, user_id: str) -> bool:
        return user_id in self.data["bans"]

db = Database()

# ============================================
# API HANDLER
# ============================================
class LookupAPI:
    """Gestionnaire de l'API"""
    
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
        
        self.prenom = TextInput(
            label="Prénom",
            placeholder="Jean",
            required=False,
            max_length=50
        )
        self.add_item(self.prenom)
        
        self.nom = TextInput(
            label="Nom de famille",
            placeholder="Dupont",
            required=False,
            max_length=50
        )
        self.add_item(self.nom)
        
        self.email = TextInput(
            label="Email",
            placeholder="jean.dupont@email.com",
            required=False,
            max_length=100
        )
        self.add_item(self.email)
        
        self.telephone = TextInput(
            label="Téléphone",
            placeholder="0612345678",
            required=False,
            max_length=20
        )
        self.add_item(self.telephone)
        
        self.ville = TextInput(
            label="Ville",
            placeholder="Paris",
            required=False,
            max_length=50
        )
        self.add_item(self.ville)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Vérifier si l'utilisateur est banni
        if db.is_banned(str(interaction.user.id)):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous avez été banni et ne pouvez plus effectuer de recherches.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Vérifier les crédits
        user_data = db.get_user(str(interaction.user.id))
        if user_data["credits"] <= 0:
            embed = discord.Embed(
                title="❌ Crédits insuffisants",
                description="Vous n'avez plus de crédits. Contactez un administrateur.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        query = {}
        if self.prenom.value:
            query["prenom"] = self.prenom.value
        if self.nom.value:
            query["nom_famille"] = self.nom.value
        if self.email.value:
            query["email"] = self.email.value
        if self.telephone.value:
            query["telephone"] = self.telephone.value
        if self.ville.value:
            query["ville"] = self.ville.value
        
        if not query:
            embed = discord.Embed(
                title="❌ Erreur",
                description="Veuillez remplir au moins un champ !",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        query["flexible"] = True
        query["per_page"] = 10
        
        try:
            result = await LookupAPI.search(query)
            
            if result.get("status") == 200:
                results = result.get("data", {}).get("results", [])
                total = result.get("meta", {}).get("total", 0)
                
                if results:
                    # Déduire 1 crédit
                    db.remove_credits(str(interaction.user.id), 1)
                    # Ajouter à l'historique
                    query_str = ", ".join([f"{k}={v}" for k, v in query.items() if k not in ["flexible", "per_page"]])
                    db.add_search_history(str(interaction.user.id), query_str, len(results))
                    
                    view = PaginationView(results, page=0, query=query, user_id=interaction.user.id)
                    embed = view.create_embed()
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    embed = discord.Embed(
                        title="❌ Aucun résultat",
                        description="Aucune personne trouvée avec ces critères.",
                        color=discord.Color.orange()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                error_msg = result.get("error", "Erreur inconnue")
                embed = discord.Embed(
                    title="❌ Erreur API",
                    description=f"Code: {result.get('status', 500)}\n{error_msg}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except Exception as e:
            embed = discord.Embed(
                title="❌ Erreur",
                description=f"Une erreur est survenue : {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# LOOKUP MODAL
# ============================================
class LookupModal(Modal):
    def __init__(self, lookup_type: str):
        super().__init__(title=f"🔍 Lookup {lookup_type.capitalize()}")
        self.lookup_type = lookup_type
        
        placeholder = {
            "email": "jean.dupont@gmail.com",
            "phone": "0612345678",
            "iban": "FR7630006000011234567890189"
        }.get(lookup_type, "")
        
        label = {
            "email": "Adresse email",
            "phone": "Numéro de téléphone",
            "iban": "IBAN"
        }.get(lookup_type, lookup_type)
        
        self.value_input = TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            max_length=100
        )
        self.add_item(self.value_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Vérifier si l'utilisateur est banni
        if db.is_banned(str(interaction.user.id)):
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Vous avez été banni et ne pouvez plus effectuer de recherches.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Vérifier les crédits
        user_data = db.get_user(str(interaction.user.id))
        if user_data["credits"] <= 0:
            embed = discord.Embed(
                title="❌ Crédits insuffisants",
                description="Vous n'avez plus de crédits. Contactez un administrateur.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            value = self.value_input.value.strip()
            
            if not value:
                embed = discord.Embed(
                    title="❌ Erreur",
                    description="Veuillez entrer une valeur valide.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            if self.lookup_type == "email":
                result = await LookupAPI.lookup_email(value)
            elif self.lookup_type == "phone":
                result = await LookupAPI.lookup_phone(value)
            elif self.lookup_type == "iban":
                result = await LookupAPI.lookup_iban(value)
            else:
                raise ValueError("Type de lookup non supporté")
            
            if result.get("status") == 200:
                results = result.get("data", {}).get("results", [])
                
                if results:
                    # Déduire 1 crédit
                    db.remove_credits(str(interaction.user.id), 1)
                    db.add_search_history(str(interaction.user.id), f"{self.lookup_type}={value}", len(results))
                    
                    embed = discord.Embed(
                        title=f"🔍 Résultats du lookup {self.lookup_type}",
                        description=f"**{len(results)}** enregistrement(s) trouvé(s)",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    
                    for i, record in enumerate(results[:10], 1):
                        fields = []
                        for key, val in record.items():
                            if key.startswith("_") or not val:
                                continue
                            key_fr = {
                                "prenom": "Prénom",
                                "nom_famille": "Nom",
                                "email": "Email",
                                "telephone": "Téléphone",
                                "mobile": "Mobile",
                                "adresse": "Adresse",
                                "ville": "Ville",
                                "code_postal": "Code postal",
                                "date_naissance": "Date de naissance",
                                "nom_naissance": "Nom de naissance",
                                "societe": "Société",
                                "profession": "Profession"
                            }.get(key, key)
                            fields.append(f"**{key_fr}**: {val}")
                        
                        if record.get("_source_db"):
                            fields.append(f"**Source**: {record['_source_db']}")
                        
                        if fields:
                            embed.add_field(
                                name=f"📝 Enregistrement #{i}",
                                value="\n".join(fields[:15]),
                                inline=False
                            )
                    
                    embed.set_footer(text=f"Recherche: {value} • Created by Index")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    embed = discord.Embed(
                        title="❌ Aucun résultat",
                        description=f"Aucun enregistrement trouvé pour `{value}`",
                        color=discord.Color.orange()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                error_msg = result.get("error", "Erreur inconnue")
                embed = discord.Embed(
                    title="❌ Erreur API",
                    description=f"Code: {result.get('status', 500)}\n{error_msg}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except Exception as e:
            embed = discord.Embed(
                title="❌ Erreur",
                description=f"Une erreur est survenue : {str(e)}",
                color=discord.Color.red()
            )
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
        self.results_per_page = 1
        self.total_pages = max(1, (len(results) + self.results_per_page - 1) // self.results_per_page)
        self.update_buttons()
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id and interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="⛔ Accès refusé",
                description="Ces résultats sont visibles uniquement par la personne qui a effectué la recherche.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True
    
    def create_embed(self):
        start_idx = self.page * self.results_per_page
        end_idx = min(start_idx + self.results_per_page, len(self.results))
        
        embed = discord.Embed(
            title="🔍 Résultats de la recherche",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📊 Page",
            value=f"**{self.page + 1}/{self.total_pages}**",
            inline=True
        )
        embed.add_field(
            name="📋 Total résultats",
            value=f"**{len(self.results)}**",
            inline=True
        )
        
        if start_idx < len(self.results):
            person = self.results[start_idx]
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
            
            embed.add_field(
                name="👤 Personne",
                value=f"**#{start_idx + 1}** sur {len(self.results)}",
                inline=False
            )
        else:
            embed.description = "Aucun résultat à afficher"
        
        embed.set_footer(
            text=f"Page {self.page + 1}/{self.total_pages} • "
                 f"Résultat {start_idx + 1}/{len(self.results)} • Created by Index"
        )
        
        return embed
    
    def update_buttons(self):
        self.clear_items()
        
        prev_button = Button(
            label="◀ Gauche",
            style=discord.ButtonStyle.primary,
            disabled=self.page == 0
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        page_button = Button(
            label=f"📄 {self.page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.grey,
            disabled=True
        )
        self.add_item(page_button)
        
        next_button = Button(
            label="Droite ▶",
            style=discord.ButtonStyle.primary,
            disabled=self.page >= self.total_pages - 1
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
        
        download_button = Button(
            label="📥 Télécharger .txt",
            style=discord.ButtonStyle.success
        )
        download_button.callback = self.download_page
        self.add_item(download_button)
        
        close_button = Button(
            label="❌ Fermer",
            style=discord.ButtonStyle.danger
        )
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
    
    async def download_page(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        start_idx = self.page * self.results_per_page
        end_idx = min(start_idx + self.results_per_page, len(self.results))
        
        if start_idx >= len(self.results):
            embed = discord.Embed(
                title="❌ Erreur",
                description="Aucun résultat à télécharger.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        person = self.results[start_idx]
        
        content = "=" * 60 + "\n"
        content += f"🔍 RÉSULTAT DE RECHERCHE\n"
        content += f"📊 Page {self.page + 1}/{self.total_pages}\n"
        content += f"👤 Personne #{start_idx + 1}/{len(self.results)}\n"
        content += f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        content += "=" * 60 + "\n\n"
        
        for key, value in person.items():
            if key.startswith("_"):
                continue
            if value:
                key_fr = {
                    "prenom": "Prénom",
                    "nom_famille": "Nom",
                    "email": "Email",
                    "telephone": "Téléphone",
                    "mobile": "Mobile",
                    "adresse": "Adresse",
                    "ville": "Ville",
                    "code_postal": "Code postal",
                    "date_naissance": "Date de naissance"
                }.get(key, key)
                content += f"{key_fr}: {value}\n"
        
        if person.get("_sources"):
            content += "\n" + "-" * 40 + "\n"
            content += "📚 Sources:\n"
            for source in person["_sources"]:
                content += f"  • {source}\n"
        
        if person.get("_confidence"):
            content += f"\n🔒 Confiance: {person['_confidence']}%\n"
        
        content += "\n" + "=" * 60 + "\n"
        content += "Created by Index"
        
        file = discord.File(
            io.BytesIO(content.encode('utf-8')),
            filename=f"recherche_page_{self.page + 1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        await interaction.followup.send(
            content=f"📥 Téléchargement de la page {self.page + 1}/{self.total_pages}",
            file=file,
            ephemeral=True
        )
    
    async def close_panel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="✅ Panel fermé",
            embed=None,
            view=None
        )

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
            user_data = db.get_user(str(interaction.user.id))
            
            embed = discord.Embed(
                title="📊 Mon compte",
                color=discord.Color.purple(),
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="💰 Crédits disponibles",
                value=f"**{user_data['credits']}**",
                inline=True
            )
            embed.add_field(
                name="🔍 Recherches effectuées",
                value=f"**{user_data['total_searches']}**",
                inline=True
            )
            
            # API BrixHub
            me = await LookupAPI.get_me()
            if me.get("status") == 200:
                data = me.get("data", {})
                embed.add_field(
                    name="📋 Plan BrixHub",
                    value=data.get("plan", "Inconnu"),
                    inline=True
                )
                embed.add_field(
                    name="📊 Quota journalier",
                    value=data.get("daily_quota", 0),
                    inline=True
                )
                embed.add_field(
                    name="📈 Utilisé aujourd'hui",
                    value=data.get("daily_used", 0),
                    inline=True
                )
                embed.add_field(
                    name="✅ Restant",
                    value=data.get("daily_remaining", 0),
                    inline=True
                )
            
            # Historique
            if user_data["history"]:
                history_text = ""
                for i, entry in enumerate(user_data["history"][:5], 1):
                    date = datetime.fromisoformat(entry["date"]).strftime("%d/%m %H:%M")
                    history_text += f"`{i}. {entry['query']}` → {entry['results']} résultats ({date})\n"
                embed.add_field(
                    name="📜 Dernières recherches",
                    value=history_text if history_text else "Aucune recherche",
                    inline=False
                )
            else:
                embed.add_field(
                    name="📜 Dernières recherches",
                    value="Aucune recherche effectuée",
                    inline=False
                )
            
            embed.set_footer(text="Created by Index")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Erreur",
                description=f"Une erreur est survenue : {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# COMMANDES ADMIN
# ============================================
def is_admin(interaction: discord.Interaction) -> bool:
    """Vérifie si l'utilisateur a le rôle admin"""
    role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
    if not role:
        return False
    return role in interaction.user.roles

@bot.tree.command(
    name="addcredits",
    description="Ajouter des crédits à un utilisateur (Admin seulement)"
)
async def add_credits(interaction: discord.Interaction, utilisateur: discord.Member, montant: int):
    if not is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if montant <= 0:
        embed = discord.Embed(
            title="❌ Erreur",
            description="Le montant doit être supérieur à 0.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    db.add_credits(str(utilisateur.id), montant)
    
    embed = discord.Embed(
        title="✅ Crédits ajoutés",
        description=f"{montant} crédit(s) ajouté(s) à {utilisateur.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(
    name="removecredits",
    description="Enlever des crédits à un utilisateur (Admin seulement)"
)
async def remove_credits(interaction: discord.Interaction, utilisateur: discord.Member, montant: int):
    if not is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if montant <= 0:
        embed = discord.Embed(
            title="❌ Erreur",
            description="Le montant doit être supérieur à 0.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    db.remove_credits(str(utilisateur.id), montant)
    
    embed = discord.Embed(
        title="✅ Crédits retirés",
        description=f"{montant} crédit(s) retiré(s) à {utilisateur.mention}",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(
    name="look",
    description="Voir les statistiques d'un utilisateur"
)
async def look(interaction: discord.Interaction, utilisateur: discord.Member):
    # Vérifier si l'utilisateur a le droit de voir les stats des autres
    if utilisateur.id != interaction.user.id and not is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous ne pouvez voir que vos propres statistiques.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    user_data = db.get_user(str(utilisateur.id))
    
    embed = discord.Embed(
        title=f"📊 Statistiques de {utilisateur.display_name}",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="💰 Crédits",
        value=f"**{user_data['credits']}**",
        inline=True
    )
    embed.add_field(
        name="🔍 Recherches totales",
        value=f"**{user_data['total_searches']}**",
        inline=True
    )
    embed.add_field(
        name="🚫 Banni",
        value="✅ Oui" if db.is_banned(str(utilisateur.id)) else "❌ Non",
        inline=True
    )
    
    # Historique des 10 dernières recherches
    if user_data["history"]:
        history_text = ""
        for i, entry in enumerate(user_data["history"][:10], 1):
            date = datetime.fromisoformat(entry["date"]).strftime("%d/%m/%Y %H:%M")
            history_text += f"`{i}. {entry['query']}` → {entry['results']} résultats ({date})\n"
        embed.add_field(
            name="📜 10 dernières recherches",
            value=history_text if history_text else "Aucune recherche",
            inline=False
        )
    else:
        embed.add_field(
            name="📜 10 dernières recherches",
            value="Aucune recherche effectuée",
            inline=False
        )
    
    embed.set_footer(text="Created by Index")
    
    # Si c'est l'utilisateur qui se regarde, message privé
    if utilisateur.id == interaction.user.id:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed)

@bot.tree.command(
    name="ban",
    description="Bannir un utilisateur (Admin seulement)"
)
async def ban_user(interaction: discord.Interaction, utilisateur: discord.Member):
    if not is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if utilisateur.id == interaction.user.id:
        embed = discord.Embed(
            title="❌ Erreur",
            description="Vous ne pouvez pas vous bannir vous-même.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    db.ban_user(str(utilisateur.id))
    
    embed = discord.Embed(
        title="⛔ Utilisateur banni",
        description=f"{utilisateur.mention} a été banni et ne peut plus effectuer de recherches.",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(
    name="unban",
    description="Débannir un utilisateur (Admin seulement)"
)
async def unban_user(interaction: discord.Interaction, utilisateur: discord.Member):
    if not is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    db.unban_user(str(utilisateur.id))
    
    embed = discord.Embed(
        title="✅ Utilisateur débanni",
        description=f"{utilisateur.mention} peut maintenant effectuer des recherches.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

# ============================================
# BOT PRINCIPAL
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

@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")
    print(f"✅ Invité dans {len(bot.guilds)} serveurs")
    print(f"✅ Tapez /panel pour ouvrir le panel")
    print(f"✅ Admin Role ID: {ADMIN_ROLE_ID}")
    print(f"✅ Created by Index")

@bot.tree.command(
    name="panel",
    description="📊 Ouvrir le panel de recherche"
)
async def panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔍 **Csint Lookup**",
        description="🔎 **Recherche dans plus de 33 milliards de données indexées en quelques millisecondes**",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.set_image(url="https://cdn.discordapp.com/attachments/1477415267452719208/1508616783903461417/logo.PNG?ex=6a5a159e&is=6a58c41e&hm=9b8b1439fbb9e7e2b045ca054dd52c32b8544a6f985740a5e33f636d4ca08210")
    embed.set_footer(text="⚡ Ultra rapide • Fiable • Created by Index")
    
    view = PanelView()
    await interaction.response.send_message(embed=embed, view=view)

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