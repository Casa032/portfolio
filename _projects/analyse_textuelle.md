---
layout: project
title: "The Escalation of Violence in Haiti Through the Lens of the Media"
date: 2025-10-15
tech: Python, NLP
tools: [Python, NLP]

---

A textual analysis project  that tracks how national media reported the escalation of violence in Haiti over the years.

## Summary

This project is a text analysis of a corpus of Haitian press articles, aiming to understand how violence in Haiti is represented across different media outlets, and what conclusions can be drawn from this about the nature and stakes of the current crisis.

To carry out this work, I built a corpus of articles through manual selection, with violence and crime as the main themes. I chose this method because of the difficulties involved in generating a complete corpus: none of the media outlets considered has an easily accessible online archiving system, and the way their websites are set up doesn't allow for classic web scraping.

The selection covered two articles per month, over a ten-year period (January 2015 to early October 2025), from three Haitian media outlets: *Le Nouvelliste*, *AlterPresse* and *HaïtiLibre*. The theoretical target was 720 articles (2 × 12 × 10 × 3), but the final corpus contains 688 articles, since some months didn't produce enough content matching the chosen themes.

Once the corpus was built, I used Python and several libraries (spaCy, scikit-learn, prince) to identify the most frequent words, the dominant lexical fields, and the variations between media outlets.


## Development

### Context: the media landscape in Haiti

Before the digital era, access to information in Haiti mostly happened orally, through radio broadcasts, rather than through written newspapers. With the rise of social networks and the advance of communication tools, a shift gradually took place toward an online presence.

The climate of insecurity of recent years accelerated this shift: the digital format offers an extra layer of safety to journalists who are often victims of reprisals, in a country where press freedom is fragile and institutional protections are close to non-existent.

The project focuses on three media outlets, each with a distinct editorial profile:

- **Le Nouvelliste** : a historic daily founded in 1898, which used to offer both a digital and a print version (the latter no longer existing since late 2022); moderate and factual tone.
- **AlterPresse** : an online news agency with a social and alternative orientation, active since the 2000s; an engaged outlet with a more critical approach.
- **HaïtiLibre** : a digital outlet focused on fast coverage of current events; short, less elaborate dispatches, but a constant publishing frequency.

### Methodology: building and cleaning the corpus

The corpus is loaded from (.xlsx) an Excel file, then the dates are broken down (day, month, year) to enable time-based analysis:


```python
df = pd.read_excel("Corpus.xlsx")
df = df.dropna(subset=['contenu', 'date'])
df['source'] = df['source'].astype(str)

df['date'] = pd.to_datetime(df['date'], errors='coerce')
df['jour'] = df['date'].dt.day
df['mois'] = df['date'].dt.month
df['annee'] = df['date'].dt.year
df['annee_mois'] = df['date'].dt.to_period('M')
```
   
   
Cleaning the text is a central step in this project. Many place names, armed groups and Haitian public figures are spelled in several different ways from one article to another ("Port-au-Prince", "Port au Prince"…). So I built a normalization dictionary based on regular expressions, to unify these variants before any analysis:

```python
modifications = {
    r'(?i)\bvillage de dieu\b': 'village-de-dieu',
    r'(?i)\bport au prince\b': 'portauprince',
    r'(?i)\b400 Mawozo\b': '400-mawozo',
    r'(?i)\bViv Ansanm\b': 'viv-ansanm',
    r'(?i)\bJimmy Cherizier\b': 'jimmy-cherizier',
    r'(?i)\bJovenel Moïse\b': 'jovenel-moïse',
    # ... (full dictionary of about forty entries)
}

def nettoyer(txt):
    def remplacer(match):
        contenu = match.group(1).strip()
        if len(contenu.split()) > 4:
            return contenu
        else:
            return match.group(0)

    txt = re.sub(r'(?s)«(.*?)»', remplacer, txt)
    txt = txt.lower()
    for expr, remplacement in modifications.items():
        txt = re.sub(expr, remplacement, txt)

    txt = txt.translate(str.maketrans('', '', string.punctuation))
    txt = re.sub(r'\s+', ' ', txt)
    return txt.strip()
```

### Tokenization, stopwords and lemmatization

For tokenization and lemmatization, I used **spaCy** with the French model `fr_core_news_md`. Beyond the classic stopwords, I defined a list of custom stopwords (media names, days of the week, overly generic words like "violence" or "haïtien" that appear in almost every article and therefore add no discriminative information):

```python
nlp = spacy.load("fr_core_news_md")

propre_stopwords = {
    'être', 'avoir', 'faire', 'aller', 'ce', 'il', 'elle',
    'national', 'zone', 'ayiti', 'haiti', 'haitien', 'journal',
    'violence', 'agence', 'alterpresse', 'nouvelliste',
    'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche'
}
propre_stopwords_norm = {unidecode.unidecode(w) for w in propre_stopwords}
```

One point I paid particular attention to: expressions in quotation marks (often quotes or the names of armed groups, like "Kraze Barye" or "5 Segonn") are extracted separately and turned into single tokens, then removed from the text so they aren't analyzed twice. I also defined groupings to merge spelling variants or nicknames referring to the same entity (for example "pnh" and "policier" are grouped under "police", or "jimmycherizier" is grouped with "barbecue", his nickname):

```python
regroupements = {
    'policier': 'police',
    'pnh': 'police',
    'capitale': 'portauprince',
    'metropolitain': 'portauprince',
    'jimmycherizier': 'barbecue',
    'fantom': 'fantom509',
}

def tokenizer(txt):
    doc = nlp(txt)
    tokens = []
    for token in doc:
        lemme_norm = unidecode.unidecode(token.lemma_.lower()).strip()
        if (not token.is_stop and lemme_norm not in propre_stopwords_norm and
            not token.is_punct and len(token.text) > 1):
            lemme_norm = regroupements.get(lemme_norm, lemme_norm)
            tokens.append(lemme_norm)
    return list(set(tokens))

df['tokens'] = df['contenu'].apply(tokenizer)
```

### How violence is represented by each media outlet

Across the whole corpus, words don't carry the same weight: some are repeated much more often than others. We find keywords like "arme" (weapon), "gang", "portauprince" or "bandit". A first conclusion follows from this: violence in Haiti is centered around armed individuals who commit crimes, whether gang members or bandits, and the coverage is mostly centered on the capital, Port-au-Prince.

A diachronic analysis of how these keywords are used lets me put forward the first arguments.


<div class="img-proj">
    <p>Evolution of the term "portauprince" by media outlet</p>
    <img src="{{ '/assets/images/projects/p1-img1.png' | relative_url }}" class='img'>
</div>

We can see substantial media coverage of violent events in Port-au-Prince throughout the period, with strong fluctuations between 2015 and 2024. Although the overall trend is similar across outlets, **AlterPresse** stands out for the particular attention it gives to violent events linked to the capital. There's also a shift in **Le Nouvelliste**'s editorial line: since 2020, it has published far more articles about violent events than **HaïtiLibre**, whereas the trend used to be the opposite.

<div class="img-proj">
    <p>Evolution of the use of the word "gang" by media outlet</p>
    <img src="{{ '/assets/images/projects/p1-img2.png' | relative_url }}" class='img'>
</div>

We also see an upward trend in the use of the word "gang", with **AlterPresse** again standing out for its more critical approach. This outlet uses more explicit words related to violence ("gang", "bandit"), followed by **Le Nouvelliste**, while **HaïtiLibre**, with its shorter dispatches, necessarily uses fewer words. That said, the overall direction is the same for all three: a situation that is progressively worsening.

To make these differences in discourse more objective, I built a TF-IDF score per media outlet to identify each one's most characteristic terms:

```python
vectorizer = TfidfVectorizer(max_features=1000)
X = vectorizer.fit_transform(df['txt_tokenisé'])

tfidf_df = pd.DataFrame(X.toarray(), columns=vectorizer.get_feature_names_out())
tfidf_df['source'] = df['source'].values
moyenne_source = tfidf_df.groupby('source').mean()

for source in moyenne_source.index:
    top_mots = moyenne_source.loc[source].sort_values(ascending=False).head(10)
    print(f"\nTop TF-IDF words for media outlet: {source}")
    print(top_mots)
```

| AlterPresse | score | HaïtiLibre | score | Le Nouvelliste | score |
|---|---|---|---|---|---|
| portauprince | 0.0555 | arme | 0.0375 | bandit | 0.0381 |
| arme | 0.0442 | gang | 0.0362 | savoir | 0.0338 |
| gang | 0.0419 | population | 0.0342 | arme | 0.0334 |
| quartier | 0.0369 | balle | 0.0299 | atil | 0.0330 |
| balle | 0.0346 | portauprince | 0.0278 | population | 0.0311 |

This table confirms the intuition drawn from the charts: **AlterPresse** stays true to its engaged stance, with a vivid, human-centered representation; **HaïtiLibre** takes a more factual approach ("operations", "reminder"); **Le Nouvelliste** stands out with a more sustained narrative style, questioning accountability ("responsible", "authority").

### Evolution of the lexical field over time

To track how the vocabulary evolved, I identified, year by year, the words that newly appeared and persisted over at least two of the following years:

```python
seuil = 2  # the word must persist for at least 2 later years

for i in range(1, len(annees) - 1):
    n_moins_1 = m_annee[annees[i - 1]]
    n_courant = m_annee[annees[i]]
    mots_nouveaux = n_courant - n_moins_1

    mots_persistants = {
        mot for mot in mots_nouveaux
        if sum(mot in m_annee[annees[j]] for j in range(i + 1, len(annees))) >= seuil
    }

    mots_frequents = Counter()
    for j in range(i, len(annees)):
        mots_frequents.update([mot for mot in t_annee[annees[j]] if mot in mots_persistants])

    introduction[annees[i]] = mots_frequents.most_common(15)
```

This tracking highlights fairly clear stages in the crisis: from 2017 onward, terms with a violent connotation appear ("massacre", "blood"); 2018 marks the start of "kidnapping" and the establishment of the first criminal groups ("coalition", "village-de-dieu"); 2020 sees the consolidation of larger coalitions ("G9", "400 Mawozo"); 2021 marks a turning point with the president's assassination and the emergence of a "de facto government"; and from 2022 onward, the vocabulary shifts toward lawless zones, internal migration and calls for a multinational force.

### Thematic analysis of the corpus (clustering)

To go beyond a word-by-word analysis, I grouped the articles into five central themes using K-means applied to the TF-IDF matrix:

```python
vectorizer = TfidfVectorizer(max_features=1000)
X = vectorizer.fit_transform(df['txt_tokenisé'])

kmeans = KMeans(n_clusters=5, random_state=42)
df['Cluster'] = kmeans.fit_predict(X)

terms = vectorizer.get_feature_names_out()
for i in range(5):
    top = X[df['Cluster'] == i].mean(axis=0).A1
    top_indices = top.argsort()[-10:][::-1]
    print(f"Cluster {i}: {[terms[j] for j in top_indices]}")
```

The five resulting clusters correspond to five angles from which the crisis is covered:

- **Cluster 0 - State repressive forces**: police operations, arrests, institutional communication.
- **Cluster 1 - Occasional disruptions**: disruptions to transport and traffic, notably in 2021.
- **Cluster 2 - Popular demands**: demonstrations, State responses, judicial measures.
- **Cluster 3 - Geopolitical dimension**: how the international community (UN, NGOs) views the situation.
- **Cluster 4 - Urban crime**: everyday violence, clashes between gangs, direct impact on the population.


<div class="img-proj">
    <p>Relative evolution (%) of the five clusters by year</p>
    <img src="{{ '/assets/images/projects/p1-img3.png' | relative_url }}" class='img'>
</div>

Two clear trajectories emerge. Clusters 0, 1 and 2 decline sharply over time, each ending up representing less than 10% of the themes covered. Conversely, clusters 3 and 4 together account for nearly 80% of the coverage by the end of the period, reflecting a shift in media discourse toward the international dimension and urban crime - a sign of the State's retreat and of insecurity becoming widespread.

### Correspondence Analysis (CA)

To visualize the relationships between years and clusters on a single plane, I used correspondence analysis (via the `prince` library) applied to the years × clusters cross-tabulation:

```python
table = pd.crosstab(df['annee'], df['Cluster'])

afc = prince.CA(n_components=2, random_state=42)
afc = afc.fit(table)

rows = afc.row_coordinates(table)
cols = afc.column_coordinates(table)

plt.scatter(rows[0], rows[1], color='blue', label='Years')
plt.scatter(cols[0], cols[1], color='red', label='Clusters')
```
<div class="img-proj">
    <p>CA,correspondence between years and clusters</p>
    <img src="{{ '/assets/images/projects/p1-img4.png' | relative_url }}" class='img'>
</div>


Reading the factorial plane brings out two interpretive axes:

- **Axis 1 - Controlled violence vs. territorialized violence**: from 2015 to 2019, the State retains a significant share of its repressive power; from 2020 onward, armed groups expand their influence and take over entire neighborhoods of the capital, which become genuine operational bases.
- **Axis 2 - Political paralysis vs. political order**: the periods 2015-2018 and 2023-2025 correspond to relatively stable power, contrary to 2019-2022, marked by political instability, the assassination of President Jovenel Moïse and Ariel Henry's contested government.

### Evolution of keywords by media outlet and by year

Finally, I built a source × year cross-tabulation to track the frequency of the most frequent words overall, then plotted their compared evolution across several media outlets:

```python
mots = ['arme', 'portauprince', 'gang', 'bandit', 'population']

for mot in mots:
    for source in sources:
        courbe = evolution.loc[source][mot]
        plt.plot(courbe.index, courbe.values, marker='o', label=source)
    plt.title(f"Evolution of the word '{mot}' by media outlet")
    plt.legend(title="Media outlet")
    plt.show()
```


   

## Conclusion

This project allowed me to combine several natural language processing approaches (regex-based cleaning, lemmatization with spaCy, TF-IDF vectorization, K-means clustering and correspondence analysis) to reconstruct, through the lens of three Haitian media outlets, ten years of evolving discourse on violence in Haiti.

Beyond the differences in tone between **Le Nouvelliste**, **AlterPresse** and **HaïtiLibre**, the results converge toward the same conclusion: violence has progressively become embedded in the country's daily reality, with a clear turning point from 2020-2021 onward, a visible retreat of the State apparatus, and a growing prominence of urban crime and the international dimension in media coverage of the crisis.