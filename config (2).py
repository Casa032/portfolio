SOURCES =[
    # Source rss
{#CNIL
    "id"       :   "cnil",
    "nom"      :   "CNIL",
    "url_rss"  :   'https://cnil.fr/fr/rss.xml',
    "url_api"  :    None ,
    "portee"   :   "nationale",
    "pays"     :   "FR" ,
    "fiabilite" :  "officielle" 
},
{ #GDPRHUB   
    "id"       :   "gdprhub",
    "nom"      :   "GDPRHUB",
    "url_rss"  :   'https://gdprhub.eu/index.php?title=Special:NewPages&feed=atom&hideredirs=1&limit=10&render=1',
    "url_api"  :    None ,
    "portee"   :   "européenne",
    "pays"     :   "EU" ,
    "fiabilite" :  "blog" 
},
{#EDPB
    "id"       :   "edpb",
    "nom"      :   "EDPB",
    "url_rss"  :   'https://www.edpb.europa.eu/feed/news_en',
    "url_api"  :    None ,
    "portee"   :   "européenne",
    "pays"     :   "EU" ,
    "fiabilite" :  "officielle" 
},
{#CJUE
    "id"       :   "cjue",
    "nom"      :   "CJUE",
    "url_rss"  :   "http://curia.europa.eu/site/rss.jsp?lang=fr&secondLang=en",
    "url_api"  :    None ,
    "portee"   :   "européenne",
    "pays"     :   "EU" ,
    "fiabilite" :  "officielle" 
},
    {#Mathias Avocat
    "id"       :   "mathias avocat",
    "nom"      :   "CABINET MATHIAS",
    "url_rss"  :   "https://www.avocats-mathias.com/feed",
    "url_api"  :    None ,
    "portee"   :   "nationale",
    "pays"     :   "FR" ,
    "fiabilite" :  "newsletter" 
},
        {#Bensoussan
    "id"       :   "Bensoussan",
    "nom"      :   "CABINET BENSOUSSAN",
    "url_rss"  :   "https://www.lexing.law/feed/",
    "url_api"  :    None ,
    "portee"   :   "nationale",
    "pays"     :   "FR" ,
    "fiabilite" :  "newsletter" 
},


    # Sources api
{ #Eur-lex
    "id"       :   "lex",
    "nom"      :   "Eur-lex",
    "url_rss"  :    None,
    "url_api"  :   "https://lex-api.com/api/v1/documents/recent",
    "portee"   :   "européenne",
    "pays"     :   "EU" ,
    "fiabilite" :  "journal" 
},
    { #Légifrance
    "id"       :   "legifrance",
    "nom"      :   "LEGIFRANCE",
    "url_rss"  :    None,
    "url_api"  :   'https://oauth.piste.gouv.fr/api/oauth/token',
    "portee"   :   "nationale",
    "pays"     :   "france" ,
    "fiabilite" :  "officielle" 
}

]

MOTS_CLES=[
    "données personnelles",
    "protection des données",
    "RGPD",
    "CNIL",
    "cybersécurité",
    "vie privée",
    "traitement des données",
    "données à caractère personnel",
    "sécurité informatique",
    "intelligence artificielle",

]


PISTE_CLIENT_ID = "de991a0a-0c19-41de-8e01-1a18954ba644"
PISTE_CLIENT_SECRET = "fadc9b45-ce2a-46a8-98c2-75b227cda696"





MAPPING_API= {
    "lex": { "auteur": "author", "date": "dateOfDocument", "langue": "language", "titre": "title", "resume": "resume", "url": "url", "celex": "celexNumber"}

}

API_HEADERS={
    "lex" :{"x-api-key": "lex_live_947240f324c08dcef4e1d0987cc77a9fe91775a9e0cbcdd0d6c990f7034d2e93","Content-Type" : "application/json"}
}


# ---------------- Traduction (API compatible OpenAI) ----------------
# >>> À COMPLÉTER avec ton fournisseur Qwen :
TRAD_API_URL   = "https://ton-endpoint/v1/chat/completions"   # <-- URL de l'API
TRAD_API_KEY   = "sk-..."                                      # <-- ta clé
TRAD_MODELE    = "qwen-coder"                                  # <-- nom exact du modèle
TRAD_ACTIVE    = True                                          # mettre False pour désactiver

# On ne traduit QUE les sources dont la langue n'est pas le français.
# (les id correspondent à ceux de SOURCES)
SOURCES_A_TRADUIRE = {"edpb", "gdprhub", "cjue", "lex"}


# ---------------- Règles de scoring de pertinence DPO ----------------
# Chaque terme rapporte des points s'il apparaît dans titre+resume.
# Les termes sont cherchés en minuscules, accents inclus.
# Pondération : 3 = très spécifique DPO, 2 = spécifique, 1 = générique.
TERMES_SCORE = {
    # Très spécifiques (3 pts)
    "rgpd": 3, "gdpr": 3, "cnil": 3, "edpb": 3, "cepd": 3,
    "données personnelles": 3, "données à caractère personnel": 3,
    "données à caractère personnelles": 3,
    "violation de données": 3, "data breach": 3,
    "délégué à la protection des données": 3, "dpo": 3,
    # Spécifiques (2 pts)
    "protection des données": 2, "vie privée": 2, "privacy": 2,
    "transfert de données": 2, "consentement": 2,
    "analyse d'impact": 2, "aipd": 2, "dpia": 2,
    "sous-traitant": 2, "responsable de traitement": 2,
    "sanction": 2, "amende": 2,
    # Génériques (1 pt) — utiles mais ambigus
    "cybersécurité": 1, "sécurité informatique": 1, "fuite": 1,
    "intelligence artificielle": 1, "traitement": 1, "cookies": 1,
}

# Termes qui RETIRENT des points (bruit fréquent dans une veille).
TERMES_MALUS = {
    "offre d'emploi": -5, "recrutement": -3, "webinaire": -2,
    "newsletter": -2, "communiqué de presse": -1,
}

# Seuil indicatif : en-dessous, l'article est considéré peu pertinent.
# (on ne rejette rien, c'est juste une borne pour filtrer à l'affichage)
SEUIL_PERTINENCE = 3


# ---------------- Scoring sémantique par LLM (API compatible OpenAI) ----------------
# >>> À COMPLÉTER avec ton fournisseur :
LLM_API_URL  = "https://ton-endpoint/v1/chat/completions"   # <-- URL de l'API
LLM_API_KEY  = "sk-..."                                      # <-- ta clé
LLM_MODELE   = "gpt-4o-mini"                                 # <-- nom du modèle
LLM_ACTIVE   = True                                          # False pour désactiver

# Description du périmètre DPO, injectée dans le prompt.
# Ajuste-la pour cadrer ce que le LLM doit considérer comme pertinent.
LLM_PERIMETRE_DPO = (
    "La protection des données personnelles et la vie privée : RGPD, CNIL, EDPB/CEPD, "
    "violations de données, transferts internationaux de données, sanctions et amendes "
    "relatives aux données personnelles, consentement, sous-traitance, analyses d'impact "
    "(AIPD/DPIA), cybersécurité touchant aux données personnelles, et décisions de justice "
    "en matière de protection des données. NE concerne PAS : actualités économiques générales, "
    "offres d'emploi, événements/webinaires, sujets juridiques sans lien avec les données "
    "personnelles."
)

# Seuil sur le score LLM (0-10) au-dessus duquel un article est jugé pertinent.
# Repère : >=7 pertinent, 4-6 à vérifier, <=3 écarté.
LLM_SEUIL = 7



