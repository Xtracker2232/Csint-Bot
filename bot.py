import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import aiohttp
from datetime import datetime
from typing import Dict, List, Any
import asyncio
import io

# ============================================
# CONFIGURATION - À MODIFIER AVEC VOS INFOS
# ============================================
API_KEY = os.getenv("BRIXHUB_API_KEY")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = "https://api.brixhub.is/api/v1"
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# ============================================
# API HANDLER
# ============================================
class LookupAPI:
    """Gestionnaire de l'API"""
    
    @staticmethod
    async def search(data: Dict[str, Any]) -> Dict[str, Any]:
        """Effectue une recherche multi-critères"""
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
        """Recherche par email"""
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
        """Recherche par téléphone"""
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
        """Recherche par IBAN"""
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
        """Informations du compte"""
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
# MODALS
# ============================================
class SearchModal(Modal):
    """Modal de recherche simple"""
    
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
        """Soumission de la recherche"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        # Construction de la requête
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
        
        # Vérifier qu'au moins un champ est rempli
        if not query:
            embed = discord.Embed(
                title="❌ Erreur",
                description="Veuillez remplir au moins un champ !",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Ajouter les options
        query["flexible"] = True
        query["per_page"] = 10
        
        try:
            # Effectuer la recherche
            result = await LookupAPI.search(query)
            
            if result.get("status") == 200:
                results = result.get("data", {}).get("results", [])
                total = result.get("meta", {}).get("total", 0)
                
                if results:
                    view = PaginationView(results, page=0, query=query, user_id=interaction.user.id)
                    embed = view.create_embed()
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    embed = discord.Embed(
                        title="❌ Aucun résultat",
                        description="Aucune personne trouvée avec ces critères.\n"
                                    "💡 Astuce : Essayez avec moins de critères ou utilisez le lookup par email/téléphone.",
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

class LookupModal(Modal):
    """Modal pour les lookups"""
    
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
        """Soumission du lookup"""
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
    """Vue avec boutons de pagination et téléchargement"""
    
    def __init__(self, results: List[Dict], page: int = 0, query: Dict = None, user_id: int = None):
        super().__init__(timeout=300)
        self.results = results
        self.page = page
        self.query = query or {}
        self.user_id = user_id
        self.results_per_page = 1  # 1 résultat par page pour un affichage détaillé
        self.total_pages = max(1, (len(results) + self.results_per_page - 1) // self.results_per_page)
        self.update_buttons()
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Vérifie que seul l'utilisateur qui a fait la recherche peut interagir"""
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
        """Crée l'embed pour la page actuelle"""
        start_idx = self.page * self.results_per_page
        end_idx = min(start_idx + self.results_per_page, len(self.results))
        
        embed = discord.Embed(
            title="🔍 Résultats de la recherche",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Info sur la page
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
        
        # Résultat de la page
        if start_idx < len(self.results):
            person = self.results[start_idx]
            fields = []
            
            # Informations personnelles
            if person.get("prenom"):
                fields.append(f"👤 **Prénom**: {person['prenom']}")
            if person.get("nom_famille"):
                fields.append(f"📛 **Nom**: {person['nom_famille']}")
            if person.get("nom_naissance"):
                fields.append(f"📝 **Nom de naissance**: {person['nom_naissance']}")
            if person.get("nom_affichage"):
                fields.append(f"🖊️ **Nom d'affichage**: {person['nom_affichage']}")
            if person.get("nom_utilisateur"):
                fields.append(f"🔑 **Nom d'utilisateur**: {person['nom_utilisateur']}")
            
            # Contact
            if person.get("email"):
                fields.append(f"📧 **Email**: {person['email']}")
            if person.get("telephone"):
                fields.append(f"📱 **Téléphone**: {person['telephone']}")
            if person.get("mobile"):
                fields.append(f"📱 **Mobile**: {person['mobile']}")
            
            # Adresse
            if person.get("adresse"):
                fields.append(f"📍 **Adresse**: {person['adresse']}")
            if person.get("complement_adresse"):
                fields.append(f"🏢 **Complément**: {person['complement_adresse']}")
            if person.get("ville"):
                fields.append(f"🏙️ **Ville**: {person['ville']}")
            if person.get("code_postal"):
                fields.append(f"📮 **Code postal**: {person['code_postal']}")
            if person.get("pays"):
                fields.append(f"🌍 **Pays**: {person['pays']}")
            if person.get("region"):
                fields.append(f"🗺️ **Région**: {person['region']}")
            if person.get("departement"):
                fields.append(f"📌 **Département**: {person['departement']}")
            
            # Naissance
            if person.get("date_naissance"):
                fields.append(f"🎂 **Date de naissance**: {person['date_naissance']}")
            if person.get("annee_naissance"):
                fields.append(f"📅 **Année de naissance**: {person['annee_naissance']}")
            if person.get("ville_naissance"):
                fields.append(f"🏠 **Ville de naissance**: {person['ville_naissance']}")
            if person.get("lieu_naissance"):
                fields.append(f"📍 **Lieu de naissance**: {person['lieu_naissance']}")
            
            # Identifiants
            if person.get("discord_id"):
                fields.append(f"🆔 **Discord ID**: {person['discord_id']}")
            if person.get("steam_id"):
                fields.append(f"🎮 **Steam ID**: {person['steam_id']}")
            if person.get("fivem_license"):
                fields.append(f"🎯 **FiveM License**: {person['fivem_license']}")
            if person.get("fivem_license2"):
                fields.append(f"🎯 **FiveM License 2**: {person['fivem_license2']}")
            if person.get("xbox_live_id"):
                fields.append(f"🎮 **Xbox Live ID**: {person['xbox_live_id']}")
            if person.get("live_id"):
                fields.append(f"🎮 **Live ID**: {person['live_id']}")
            
            # Bancaire
            if person.get("iban"):
                fields.append(f"🏦 **IBAN**: {person['iban']}")
            if person.get("bic"):
                fields.append(f"🏦 **BIC**: {person['bic']}")
            
            # Professionnel
            if person.get("societe"):
                fields.append(f"🏢 **Société**: {person['societe']}")
            if person.get("profession"):
                fields.append(f"💼 **Profession**: {person['profession']}")
            if person.get("fonction"):
                fields.append(f"📋 **Fonction**: {person['fonction']}")
            
            # Entreprise
            if person.get("siret"):
                fields.append(f"📋 **SIRET**: {person['siret']}")
            if person.get("siren"):
                fields.append(f"📋 **SIREN**: {person['siren']}")
            
            # Informations de confiance
            if person.get("_confidence"):
                fields.append(f"🔒 **Confiance**: {person['_confidence']}%")
            if person.get("_sources"):
                sources = ", ".join(person["_sources"][:5])
                if len(person["_sources"]) > 5:
                    sources += f" et {len(person['_sources'])-5} autre(s)"
                fields.append(f"📚 **Sources**: {sources}")
            
            embed.description = "\n".join(fields) if fields else "Aucune information détaillée"
            
            # Numéro de la personne
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
        """Met à jour l'état des boutons"""
        self.clear_items()
        
        # Bouton Gauche (Précédent)
        prev_button = Button(
            label="◀ Gauche",
            style=discord.ButtonStyle.primary,
            disabled=self.page == 0
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # Indicateur de page
        page_button = Button(
            label=f"📄 {self.page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.grey,
            disabled=True
        )
        self.add_item(page_button)
        
        # Bouton Droite (Suivant)
        next_button = Button(
            label="Droite ▶",
            style=discord.ButtonStyle.primary,
            disabled=self.page >= self.total_pages - 1
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
        
        # Bouton Télécharger
        download_button = Button(
            label="📥 Télécharger .txt",
            style=discord.ButtonStyle.success,
            custom_id="download"
        )
        download_button.callback = self.download_page
        self.add_item(download_button)
        
        # Bouton Fermer
        close_button = Button(
            label="❌ Fermer",
            style=discord.ButtonStyle.danger
        )
        close_button.callback = self.close_panel
        self.add_item(close_button)
    
    async def update_embed(self, interaction: discord.Interaction):
        """Met à jour l'embed avec la nouvelle page"""
        embed = self.create_embed()
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def previous_page(self, interaction: discord.Interaction):
        """Page précédente"""
        if self.page > 0:
            self.page -= 1
            await self.update_embed(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        """Page suivante"""
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_embed(interaction)
    
    async def download_page(self, interaction: discord.Interaction):
        """Télécharge la page actuelle en .txt"""
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
        
        # Créer le contenu du fichier
        content = "=" * 60 + "\n"
        content += f"🔍 RÉSULTAT DE RECHERCHE\n"
        content += f"📊 Page {self.page + 1}/{self.total_pages}\n"
        content += f"👤 Personne #{start_idx + 1}/{len(self.results)}\n"
        content += f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        content += "=" * 60 + "\n\n"
        
        # Ajouter toutes les informations
        for key, value in person.items():
            if key.startswith("_"):
                continue
            if value:
                key_fr = {
                    "prenom": "Prénom",
                    "nom_famille": "Nom",
                    "nom_naissance": "Nom de naissance",
                    "nom_affichage": "Nom d'affichage",
                    "nom_utilisateur": "Nom d'utilisateur",
                    "email": "Email",
                    "telephone": "Téléphone",
                    "mobile": "Mobile",
                    "adresse": "Adresse",
                    "complement_adresse": "Complément d'adresse",
                    "ville": "Ville",
                    "code_postal": "Code postal",
                    "pays": "Pays",
                    "region": "Région",
                    "departement": "Département",
                    "date_naissance": "Date de naissance",
                    "annee_naissance": "Année de naissance",
                    "ville_naissance": "Ville de naissance",
                    "lieu_naissance": "Lieu de naissance",
                    "discord_id": "Discord ID",
                    "steam_id": "Steam ID",
                    "fivem_license": "FiveM License",
                    "fivem_license2": "FiveM License 2",
                    "xbox_live_id": "Xbox Live ID",
                    "live_id": "Live ID",
                    "iban": "IBAN",
                    "bic": "BIC",
                    "societe": "Société",
                    "profession": "Profession",
                    "fonction": "Fonction",
                    "siret": "SIRET",
                    "siren": "SIREN",
                    "vin_plaque": "VIN/Plaque",
                    "immatriculation": "Immatriculation",
                    "numero_serie": "Numéro de série",
                    "marque": "Marque",
                    "modele": "Modèle",
                    "genre": "Genre",
                    "civilite": "Civilité",
                    "adresse_ip": "Adresse IP"
                }.get(key, key)
                content += f"{key_fr}: {value}\n"
        
        # Ajouter les sources
        if person.get("_sources"):
            content += "\n" + "-" * 40 + "\n"
            content += "📚 Sources:\n"
            for source in person["_sources"]:
                content += f"  • {source}\n"
        
        if person.get("_confidence"):
            content += f"\n🔒 Confiance: {person['_confidence']}%\n"
        
        content += "\n" + "=" * 60 + "\n"
        content += "Created by Index"
        
        # Créer le fichier
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
        """Ferme le panel"""
        await interaction.response.edit_message(
            content="✅ Panel fermé",
            embed=None,
            view=None
        )

# ============================================
# PANEL VIEW
# ============================================
class PanelView(View):
    """Vue principale du panel"""
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🔍 Recherche", style=discord.ButtonStyle.primary, custom_id="search")
    async def search_button(self, interaction: discord.Interaction, button: Button):
        """Bouton de recherche"""
        await interaction.response.send_modal(SearchModal())
    
    @discord.ui.button(label="📧 Lookup Email", style=discord.ButtonStyle.success, custom_id="lookup_email")
    async def lookup_email_button(self, interaction: discord.Interaction, button: Button):
        """Bouton lookup email"""
        await interaction.response.send_modal(LookupModal("email"))
    
    @discord.ui.button(label="📱 Lookup Phone", style=discord.ButtonStyle.success, custom_id="lookup_phone")
    async def lookup_phone_button(self, interaction: discord.Interaction, button: Button):
        """Bouton lookup phone"""
        await interaction.response.send_modal(LookupModal("phone"))
    
    @discord.ui.button(label="🏦 Lookup IBAN", style=discord.ButtonStyle.success, custom_id="lookup_iban")
    async def lookup_iban_button(self, interaction: discord.Interaction, button: Button):
        """Bouton lookup iban"""
        await interaction.response.send_modal(LookupModal("iban"))
    
    @discord.ui.button(label="📊 Mon compte", style=discord.ButtonStyle.secondary, custom_id="account")
    async def account_button(self, interaction: discord.Interaction, button: Button):
        """Bouton compte"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        try:
            me = await LookupAPI.get_me()
            
            if me.get("status") == 200:
                data = me.get("data", {})
                embed = discord.Embed(
                    title="📊 Informations du compte",
                    color=discord.Color.purple(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(
                    name="📋 Plan",
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
                embed.add_field(
                    name="📊 Total requêtes",
                    value=data.get("total_requests", 0),
                    inline=True
                )
                embed.add_field(
                    name="📄 Pagination",
                    value="✅ Activée" if data.get("pagination_enabled") else "❌ Désactivée",
                    inline=True
                )
                
                embed.set_footer(text="Created by Index")
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ Erreur",
                    description="Impossible de récupérer les informations du compte",
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
# BOT
# ============================================
class Bot(discord.Client):
    """Bot Discord"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
    
    async def setup_hook(self):
        """Configuration du bot"""
        await self.tree.sync()
        print("✅ Commandes synchronisées")

bot = Bot()

@bot.event
async def on_ready():
    """Événement quand le bot est prêt"""
    print(f"✅ Bot connecté en tant que {bot.user}")
    print(f"✅ Invité dans {len(bot.guilds)} serveurs")
    print(f"✅ Tapez /panel pour ouvrir le panel")
    print(f"✅ Created by Index")

@bot.tree.command(
    name="panel",
    description="📊 Ouvrir le panel de recherche"
)
async def panel(interaction: discord.Interaction):
    """Commande pour ouvrir le panel"""
    
    embed = discord.Embed(
        title="🔍 **Csint Lookup**",
        description="🔎 **Recherche dans plus de 33 milliards de données indexées en quelques millisecondes**",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.set_image(url="https://cdn.discordapp.com/attachments/1524748144238137354/1527393637401628685/5333CBCB-BB49-4786-8256-C8AC04CA29C3-1.png?ex=6a5a7fac&is=6a592e2c&hm=6c7dccc9c433c1e4abac8ad7b7e8d58460c1b09fabfe95078bbdbf386e0d9f54&")
    
    embed.set_footer(text="⚡ Ultra rapide • Fiable • Created by Index")
    
    view = PanelView()
    await interaction.response.send_message(embed=embed, view=view)

# ============================================
# LANCEMENT DU BOT
# ============================================
if __name__ == "__main__":
    if BOT_TOKEN == "VOTRE_TOKEN_DISCORD":
        print("❌ ERREUR: Veuillez configurer votre token Discord dans BOT_TOKEN")
        print("❌ Ne partagez jamais votre token !")
    else:
        try:
            bot.run(BOT_TOKEN)
        except discord.LoginFailure:
            print("❌ ERREUR: Token Discord invalide !")
        except Exception as e:
            print(f"❌ ERREUR: {e}")