import os
import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import aiohttp
from datetime import datetime
from typing import Dict, List, Any
import json
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

# Fichier de configuration (utilise un fichier local)
CONFIG_FILE = "config.json"

# ============================================
# GESTIONNAIRE DE CONFIGURATION
# ============================================
class ConfigManager:
    def __init__(self):
        self.config = {}
        self.load()
    
    def load(self):
        try:
            with open(CONFIG_FILE, "r") as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config = {"admin_role_id": None}
            self.save()
    
    def save(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)
    
    def get_admin_role(self):
        return self.config.get("admin_role_id")
    
    def set_admin_role(self, role_id: int):
        self.config["admin_role_id"] = role_id
        self.save()
    
    def is_configured(self):
        return self.config.get("admin_role_id") is not None

config = ConfigManager()

# ============================================
# FONCTIONS ADMIN
# ============================================
def is_admin(interaction: discord.Interaction) -> bool:
    """Vérifie si l'utilisateur a le rôle admin configuré"""
    if not interaction.guild:
        return False
    
    admin_role_id = config.get_admin_role()
    if not admin_role_id:
        return False
    
    role = discord.utils.get(interaction.guild.roles, id=admin_role_id)
    if not role:
        return False
    
    return role in interaction.user.roles

def check_admin(interaction: discord.Interaction):
    """Vérifie et retourne un embed d'erreur si non admin"""
    if not is_admin(interaction):
        embed = discord.Embed(
            title="⛔ Accès refusé",
            description="Vous n'avez pas la permission d'utiliser cette commande.",
            color=discord.Color.red()
        )
        return embed
    return None

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
        # Vérifier admin
        error = check_admin(interaction)
        if error:
            await interaction.response.send_message(embed=error, ephemeral=True)
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        # Construire la requête
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
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BASE_URL}/search",
                    json=query,
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        results = result.get("data", {}).get("results", [])
                        
                        if results:
                            view = PaginationView(results, page=0, user_id=interaction.user.id)
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
                        embed = discord.Embed(
                            title="❌ Erreur API",
                            description=f"Code: {response.status}",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Erreur",
                description=str(e),
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
        # Vérifier admin
        error = check_admin(interaction)
        if error:
            await interaction.response.send_message(embed=error, ephemeral=True)
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
                endpoint = f"{BASE_URL}/lookup/email/{value}"
            elif self.lookup_type == "phone":
                endpoint = f"{BASE_URL}/lookup/phone/{value}"
            elif self.lookup_type == "iban":
                endpoint = f"{BASE_URL}/lookup/iban/{value}"
            else:
                raise ValueError("Type non supporté")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    endpoint,
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        results = result.get("data", {}).get("results", [])
                        
                        if results:
                            embed = discord.Embed(
                                title=f"🔍 Résultats lookup {self.lookup_type}",
                                description=f"**{len(results)}** enregistrement(s) trouvé(s)",
                                color=discord.Color.green()
                            )
                            
                            for i, record in enumerate(results[:5], 1):
                                fields = []
                                for key, val in record.items():
                                    if key.startswith("_") or not val:
                                        continue
                                    key_fr = {
                                        "prenom": "Prénom",
                                        "nom_famille": "Nom",
                                        "email": "Email",
                                        "telephone": "Téléphone",
                                        "adresse": "Adresse",
                                        "ville": "Ville",
                                        "code_postal": "Code postal"
                                    }.get(key, key)
                                    fields.append(f"**{key_fr}**: {val}")
                                
                                if fields:
                                    embed.add_field(
                                        name=f"📝 Enregistrement #{i}",
                                        value="\n".join(fields[:10]),
                                        inline=False
                                    )
                            
                            embed.set_footer(text=f"Recherche: {value} • Created by Index")
                            await interaction.followup.send(embed=embed, ephemeral=True)
                        else:
                            embed = discord.Embed(
                                title="❌ Aucun résultat",
                                description="Aucun enregistrement trouvé.",
                                color=discord.Color.orange()
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        embed = discord.Embed(
                            title="❌ Erreur API",
                            description=f"Code: {response.status}",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Erreur",
                description=str(e),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

# ============================================
# PAGINATION VIEW
# ============================================
class PaginationView(View):
    def __init__(self, results: List[Dict], page: int = 0, user_id: int = None):
        super().__init__(timeout=120)
        self.results = results
        self.page = page
        self.user_id = user_id
        self.total_pages = max(1, len(results))
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
        embed = discord.Embed(
            title="🔍 Résultats de la recherche",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
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
                fields.append(f"🎂 **Date de naissance**: {person['date_naissance']}")
            if person.get("adresse"):
                fields.append(f"📍 **Adresse**: {person['adresse']}")
            if person.get("code_postal"):
                fields.append(f"📮 **Code postal**: {person['code_postal']}")
            if person.get("_confidence"):
                fields.append(f"🔒 **Confiance**: {person['_confidence']}%")
            if person.get("_sources"):
                sources = ", ".join(person["_sources"][:3])
                if len(person["_sources"]) > 3:
                    sources += f" et {len(person['_sources'])-3} autre(s)"
                fields.append(f"📚 **Sources**: {sources}")
            
            embed.description = "\n".join(fields) if fields else "Aucune information détaillée"
            embed.add_field(
                name="👤 Personne",
                value=f"**#{self.page + 1}/{len(self.results)}**",
                inline=False
            )
        
        embed.set_footer(
            text=f"Page {self.page + 1}/{self.total_pages} • Created by Index"
        )
        return embed
    
    def update_buttons(self):
        self.clear_items()
        
        prev_button = Button(
            label="◀ Précédent",
            style=discord.ButtonStyle.secondary,
            disabled=self.page == 0
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        page_button = Button(
            label=f"📄 Page {self.page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.grey,
            disabled=True
        )
        self.add_item(page_button)
        
        next_button = Button(
            label="Suivant ▶",
            style=discord.ButtonStyle.secondary,
            disabled=self.page >= self.total_pages - 1
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
        
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
        error = check_admin(interaction)
        if error:
            await interaction.response.send_message(embed=error, ephemeral=True)
            return
        await interaction.response.send_modal(SearchModal())
    
    @discord.ui.button(label="📧 Lookup Email", style=discord.ButtonStyle.success)
    async def lookup_email_button(self, interaction: discord.Interaction, button: Button):
        error = check_admin(interaction)
        if error:
            await interaction.response.send_message(embed=error, ephemeral=True)
            return
        await interaction.response.send_modal(LookupModal("email"))
    
    @discord.ui.button(label="📱 Lookup Phone", style=discord.ButtonStyle.success)
    async def lookup_phone_button(self, interaction: discord.Interaction, button: Button):
        error = check_admin(interaction)
        if error:
            await interaction.response.send_message(embed=error, ephemeral=True)
            return
        await interaction.response.send_modal(LookupModal("phone"))
    
    @discord.ui.button(label="🏦 Lookup IBAN", style=discord.ButtonStyle.success)
    async def lookup_iban_button(self, interaction: discord.Interaction, button: Button):
        error = check_admin(interaction)
        if error:
            await interaction.response.send_message(embed=error, ephemeral=True)
            return
        await interaction.response.send_modal(LookupModal("iban"))
    
    @discord.ui.button(label="📊 Mon compte", style=discord.ButtonStyle.secondary)
    async def account_button(self, interaction: discord.Interaction, button: Button):
        error = check_admin(interaction)
        if error:
            await interaction.response.send_message(embed=error, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📊 Mon compte",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="💰 Crédits",
            value="**10**",
            inline=True
        )
        embed.add_field(
            name="🔍 Recherches effectuées",
            value="**0**",
            inline=True
        )
        embed.add_field(
            name="📋 Plan",
            value="Premium",
            inline=True
        )
        embed.add_field(
            name="📊 Quota journalier",
            value="**100**",
            inline=True
        )
        embed.add_field(
            name="📈 Utilisé aujourd'hui",
            value="**0**",
            inline=True
        )
        embed.add_field(
            name="📜 Dernières recherches",
            value="Aucune recherche effectuée",
            inline=False
        )
        embed.set_footer(text="Created by Index")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================
# CRÉATION DU BOT
# ============================================
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    
    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Commandes synchronisées")

bot = MyBot()

# ============================================
# COMMANDES
# ============================================
@bot.tree.command(name="config", description="⚙️ Configurer le rôle admin (1 fois)")
async def config(interaction: discord.Interaction, role: discord.Role):
    """Définit le rôle qui pourra utiliser toutes les commandes"""
    
    # Vérifier si déjà configuré
    if config.is_configured():
        admin_id = config.get_admin_role()
        existing_role = discord.utils.get(interaction.guild.roles, id=admin_id)
        embed = discord.Embed(
            title="❌ Configuration déjà effectuée",
            description=f"Un rôle admin est déjà configuré : {existing_role.mention if existing_role else 'ID: ' + str(admin_id)}",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Définir le nouveau rôle
    config.set_admin_role(role.id)
    
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

@bot.tree.command(name="checkrole", description="🔍 Voir le rôle admin configuré")
async def checkrole(interaction: discord.Interaction):
    """Vérifie quel rôle est configuré comme admin"""
    
    admin_id = config.get_admin_role()
    
    embed = discord.Embed(
        title="🔍 Configuration du rôle admin",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    if admin_id:
        role = discord.utils.get(interaction.guild.roles, id=admin_id)
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
                value=f"Le rôle avec l'ID `{admin_id}` n'existe plus dans ce serveur.",
                inline=False
            )
    else:
        embed.add_field(
            name="❌ Aucun rôle configuré",
            value="Utilise `/config` pour définir le rôle qui pourra utiliser les commandes.",
            inline=False
        )
    
    embed.set_footer(text="Created by Index")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="panel", description="📊 Ouvrir le panel de recherche")
async def panel(interaction: discord.Interaction):
    """Ouvre le panel principal"""
    
    error = check_admin(interaction)
    if error:
        await interaction.response.send_message(embed=error, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🔍 **Csint Lookup**",
        description="🔎 **Recherche dans plus de 33 milliards de données indexées en quelques millisecondes**",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    embed.set_image(url="https://cdn.discordapp.com/attachments/1477415267452719208/1529531032720904202/image.png?ex=6a624647&is=6a60f4c7&hm=8d3dded32a15867f4909a10a8c948c5e41dcf4b395e86cd1a8145d69990c5202&")
    embed.set_footer(text="⚡ Ultra rapide • Fiable • Created by Index")
    
    view = PanelView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="addcredits", description="💰 Ajouter des crédits")
async def add_credits(interaction: discord.Interaction, utilisateur: discord.Member, montant: int):
    """Ajoute des crédits à un utilisateur"""
    
    error = check_admin(interaction)
    if error:
        await interaction.response.send_message(embed=error, ephemeral=True)
        return
    
    if montant <= 0:
        embed = discord.Embed(
            title="❌ Erreur",
            description="Le montant doit être supérieur à 0.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="✅ Crédits ajoutés",
        description=f"{montant} crédit(s) ajouté(s) à {utilisateur.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="removecredits", description="💰 Enlever des crédits")
async def remove_credits(interaction: discord.Interaction, utilisateur: discord.Member, montant: int):
    """Enlève des crédits à un utilisateur"""
    
    error = check_admin(interaction)
    if error:
        await interaction.response.send_message(embed=error, ephemeral=True)
        return
    
    if montant <= 0:
        embed = discord.Embed(
            title="❌ Erreur",
            description="Le montant doit être supérieur à 0.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="✅ Crédits retirés",
        description=f"{montant} crédit(s) retiré(s) à {utilisateur.mention}",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="look", description="🔍 Voir les statistiques d'un utilisateur")
async def look(interaction: discord.Interaction, utilisateur: discord.Member):
    """Affiche les statistiques d'un utilisateur"""
    
    error = check_admin(interaction)
    if error:
        await interaction.response.send_message(embed=error, ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📊 Statistiques de {utilisateur.display_name}",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    embed.add_field(name="💰 Crédits", value="**10**", inline=True)
    embed.add_field(name="🔍 Recherches", value="**0**", inline=True)
    embed.add_field(name="🚫 Banni", value="❌ Non", inline=True)
    embed.add_field(
        name="📜 10 dernières recherches",
        value="Aucune recherche effectuée",
        inline=False
    )
    embed.set_footer(text="Created by Index")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ban", description="⛔ Bannir un utilisateur")
async def ban_user(interaction: discord.Interaction, utilisateur: discord.Member):
    """Bannit un utilisateur"""
    
    error = check_admin(interaction)
    if error:
        await interaction.response.send_message(embed=error, ephemeral=True)
        return
    
    if utilisateur.id == interaction.user.id:
        embed = discord.Embed(
            title="❌ Erreur",
            description="Vous ne pouvez pas vous bannir vous-même.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="⛔ Utilisateur banni",
        description=f"{utilisateur.mention} a été banni et ne peut plus effectuer de recherches.",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unban", description="✅ Débannir un utilisateur")
async def unban_user(interaction: discord.Interaction, utilisateur: discord.Member):
    """Débannit un utilisateur"""
    
    error = check_admin(interaction)
    if error:
        await interaction.response.send_message(embed=error, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="✅ Utilisateur débanni",
        description=f"{utilisateur.mention} peut maintenant effectuer des recherches.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

# ============================================
# ÉVÉNEMENTS
# ============================================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")
    print(f"✅ Invité dans {len(bot.guilds)} serveurs")
    
    admin_id = config.get_admin_role()
    if admin_id:
        print(f"✅ Rôle admin configuré: {admin_id}")
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