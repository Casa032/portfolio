---
layout: project
title: Commerce Analytics Dashboard
tech: R
tools: [R]
---

An interactive web application built with R and Shiny to explore
international trade flows. 


## Summary

Since the last Uruguay Round conferences, which led to the creation of the World Trade Organization in 1995, and the worldwide application of the GATT, world trade has experienced a boom compared to the protectionist era during which various countries were trying to protect their industries at all costs. Today this commercial order is being called into question with the return to power of the American president Donald Trump. Known for using trade tariffs as a commercial and political weapon, it remains to be seen how the United States, on the initiative of their president, will affect the established order.

The objective of this work is first to appreciate commercial exchanges in the world in order to highlight the dynamics that exist between the different countries, in particular with the United States at least before the changes provoked by the current policies.


**Data sources:** [OECD](https://data-explorer.oecd.org/), [WTO](https://ttd.wto.org/en), [USITC](https://dataweb.usitc.gov/).


## I. Preparing the data

### 1. The four bases

The work rests on four Excel bases, each answering a specific question of the analysis:

| Base | Content | Source |
| :---- | :---- | :---- |
| `echange.xlsx` | Exports, imports and net trade by country, product and year (2016–2024) | WTO |
| `entreprise_usa.xlsx` | Imports of American companies by partner country and sector (2017–2022) | OECD |
| `import_china.xlsx` | US imports from China broken down by product family (2017–2022) | OECD |
| `tarif.xlsx` | Customs duty rates applied by the US to Chinese products (2017–2024) | USITC |

The main base is long-format: one row per country, product, year and flow type, the flow type being *Exportations*, *Importations* or *Échange net*. That structure is what allows the same base to feed the world map, the regional charts and the balance-of-trade ranking without ever being reshaped.

### 2. Harmonising country names

The main technical difficulty of the project is not statistical but nominal. The WTO does not name countries the way the `rnaturalearth` geographic base does, and a country whose name does not match is silently dropped from the map. It simply appears in grey, which is far more dangerous than an error message.

The cleaning therefore starts by removing the aggregates that would double-count the volumes (`World` in particular), then recodes every divergent label:

```r
echange <- echange %>% 
  filter(!Country %in% c('Tokelau','Gibraltar','World','Bonaire, Sint Eustatius and Saba')) %>%
  mutate(Country = recode(Country,
    "Venezuela, Bolivarian Republic of" = "Venezuela",
    "Türkiye"                           = "Turkey",
    "Korea, Republic of"                = "Republic of Korea",
    "United States of America"          = "United States",
    "Chinese Taipei"                    = "Taiwan",
    "Hong Kong, China"                  = "Hong Kong",
    "Cabo Verde"                        = "Republic of Cabo Verde",
    "Slovak Republic"                   = "Slovakia",
    ...
  ))

world <- ne_countries(scale = "medium", returnclass = "sf")

echange_pays <- echange %>%
  filter(Country %in% world$name_long)
```

The `filter` on `world$name_long` is deliberate: it separates genuine countries from everything else. That separation is then reused as a feature rather than as a constraint, since the rows that do **not** match a country are precisely the economic blocs (WTO, G20, G7, APEC) that are analysed later on.

### 3. Computing the share in world trade

A country's share in international trade measures its weight in the whole of the exchanges:


```r
part_echange_clean <- echange_pays %>%
  filter(Produit == "Total des marchandises") %>%
  group_by(Year, Country) %>%
  summarise(Echanges = sum(Value, na.rm = TRUE), .groups = "drop") %>%
  group_by(Year) %>%
  mutate(part_echange_total = (Echanges / sum(Echanges, na.rm = TRUE)) * 100) %>%
  ungroup()
```


## II. The actors of international trade

### 1. A world map of trade shares

The map is built with `sf` and `ggplot2`, then passed through `ggplotly()` so that hovering a country reveals its share. The base world layer is drawn first in grey, and the data layer on top of it, so that countries with no data remain visible instead of leaving a hole in the map:

```r
p <- ggplot() +
  geom_sf(data = world, fill = "grey90", color = "grey70", size = 0.2) + 
  geom_sf(
    data = filter(world_data, Year == 2024, Produit == "Total des marchandises"),
    aes(fill = part_echange_total, text = tooltip),
    color = "black", size = 0.3
  ) +
  scale_fill_gradientn(
    colours = c("#e5f5e0", "#a1d99b", "#31a354", "#006d2c"),
    breaks = c(1, 5, 10),
    labels = percent_format(accuracy = 0.2, scale = 1)
  ) +
  labs(
    title = "Part des pays\n dans les échanges mondiaux de marchandises",
    subtitle = "Exportations + importations – Données 2024",
    fill = "Part (%)",
    caption = "Source: OMC"
  ) +
  theme_minimal(base_size = 12)

ggplotly(p, tooltip = "text")
```

The `text` aesthetic is not understood by `ggplot2` itself,  it is carried through to `plotly`, which is what makes the custom tooltip possible. This is the pattern reused for every interactive figure of the report.

<div class="img-proj">
    <p>World map of each country's share in global merchandise trade, 2024</p>
    <img src="{{ '/assets/images/projects/p3-img1.png' | relative_url }}" class='img'>
</div>


Three countries stand out from the others: China, the United States and Germany hold a significant importance compared to the rest of the world, with respective shares of 14.6%, 8.4% and 6.8%. The first is the factory of the world, the second an economic superpower, while the last is known to be the exporting power of Europe. The total volume of goods exchanged by any one of these three countries is so high that it exceeds the whole African continent.

To understand this divergence, we have to go back to its causes, that is to analyse the volume of exports and of imports separately.

### 2. Exports and imports by region

The same code is run twice, once filtered on *Exportations* and once on *Importations*. Each bar is a continent, stacked by country, the fill being reordered by value so that the dominant exporter of each region reads immediately:

```r
filtrer <- world_data %>%
  filter(
    continent %in% c("Africa", "Asia", "North America", "South America", "Europe", "Oceania"),
    Year == 2024,
    Type == "Exportations",
    Produit == "Total des marchandises"
  ) %>%
  group_by(continent) %>%
  mutate(
    Part = Value / sum(Value, na.rm = TRUE),
    tooltip = paste0("Pays : ", name_long,
                     "<br>Valeur : ", comma(Value),
                     "<br>Part de la région : ", percent(Part, accuracy = 0.1))
  )

p <- ggplot(filtrer, aes(x = factor(continent), y = Value,
                         fill = fct_reorder(name_long, Value, .desc = FALSE),
                         text = tooltip)) +
  geom_col(colour = 'lightgreen', size = 0.3) +
  scale_fill_viridis_d(option = "mako") +
  scale_y_continuous(labels = comma) +
  theme_classic() +
  guides(fill = "none")
```

<div class="img-proj">
    <p>Exports by region, stacked by country, 2024</p>
    <img src="{{ '/assets/images/projects/p3-img2.png' | relative_url }}" class='img'>
</div>


It is not surprising to find these three countries as the largest exporters of their respective regions. While the position of China and of the United States is uncontested, Germany is rivalled in Europe by other powers, such as the Netherlands for instance.

<div class="img-proj">
    <p>Imports by region, stacked by country, 2024</p>
    <img src="{{ '/assets/images/projects/p3-img3.png' | relative_url }}" class='img'>
</div>


On the import side the leadership has not changed, although notable differences deserve to be highlighted. Among the three main countries presented so far, Germany and China have an import share smaller than their export share, which allows them to generate a trade surplus. The situation is the opposite for the United States: with a gap of more than 8 percentage points, the United States visibly import more than they export, which places them in a trade deficit. This situation is shared by numerous European and Asian countries, as the comparison between these two last charts shows.

In a deficit situation, a country is obliged to borrow (from the countries in surplus) in order to finance its investments. If this deficit accumulates over several periods, it may affect its capacity to absorb its debt.

### 3. Trade by economic bloc

This is where the rows rejected by the country filter become useful. Instead of being discarded, they are isolated with `is.na(part_echange_total)`, which by construction selects everything that is not a country, and the continents are excluded in turn so that only the economic groupings remain:

```r
zone <- echange %>%
  filter(is.na(part_echange_total), !Country %in% world$continent)

volume_par_zone <- zone %>%
  filter(Produit == "Total des marchandises") %>%
  group_by(Country, Year) %>%
  summarise(Volume_Echange = sum(Value, na.rm = TRUE), .groups = "drop")

top5_zones <- volume_par_zone %>%
  group_by(Country) %>%
  summarise(Total = sum(Volume_Echange, na.rm = TRUE)) %>%
  arrange(desc(Total)) %>%
  slice_head(n = 5) %>%
  pull(Country)
```

The five largest blocs are then displayed as a small-multiple with `facet_wrap`, on a fixed scale so that the volumes stay comparable from one panel to the next.

<div class="img-proj">
    <p>Trade volume of the five largest economic blocs, 2016–2024</p>
    <img src="{{ '/assets/images/projects/p3-img4.png' | relative_url }}" class='img'>
</div>


Gathering 164 countries, the WTO is an organisation one of whose main objectives is to favour trade by seeking to limit import barriers. It is therefore not surprising to observe that, whatever the year, the total trade volume of WTO members represents the largest volume of goods exchanged on the planet.

It is also important to underline that, although WTO members adhere to the same principles, bilateral agreements nonetheless exist outside the charter of the organisation. Moreover, every country in the world participates to some extent in international trade, which has led to the creation of multiple alliances aiming to protect themselves or to promote an agenda favourable to the members of a group. We thus find the G20, gathering the 19 largest world economies and the European Union, or the G7 with the most developed economies. Another group, in strong growth thanks to the economic advances of the Asian countries, is APEC, which favours cooperation and growth in a less formal framework than the WTO or the European Union.

This important volume of exchanges between the countries of the world reminds us how much we no longer live in autarky. Holding a comparative advantage makes it possible to extract gains from international trade.


## III. The American deficit and the Chinese partner

### 1. Net trade

The net trade type is already present in the base, so isolating the ten largest deficits is a matter of keeping the negative values and taking the smallest ones:

```r
top10 <- world_data %>%
  filter(Type == "Échange net", Value < 0, Year == 2024) %>%
  group_by(name_long) %>%
  summarise(Balance = sum(Value, na.rm = TRUE)) %>%
  slice_min(order_by = Balance, n = 10) %>%
  arrange(Balance)
```

Note the use of `slice_min` rather than a sort followed by a `head`: on a negative variable it is the correct verb, and it makes the intention explicit in the code.

<div class="img-proj">
    <p>Top 10 countries with a negative trade balance, 2024</p>
    <img src="{{ '/assets/images/projects/p3-img5.png' | relative_url }}" class='img'>
</div>


We can here observe the magnitude of the trade deficit of certain countries for the year 2024. The United States display a commercial loss of more than 1,000 billion dollars, far ahead of the United Kingdom with a declared deficit of 303 billion or of India with nearly 259 billion. The deficit of the leading economic power is four times higher than the second largest deficit. An enormous figure, which can have major consequences on its currency, for example. The constant demand for foreign currencies to support purchases can lead to a loss of value of the money. This figure also implies a certain dependence on the outside, which makes the country vulnerable in case of external shocks, such as a price increase among trade partners.

### 2. Bilateral relations of the United States

To understand the magnitude of the deficit of the world superpower, it is necessary to look into its so-called trade partners. The OECD base is expressed in thousands, so it is rescaled at load time before anything else is computed:

```r
usa <- read_excel("base/entreprise_usa.xlsx")
usa$Value <- usa$Value * 1000

top10_imports <- usa %>%
  filter(Year == 2022, Sector == "Toutes les activités", Type == "Importation") %>%
  arrange(desc(Value)) %>%
  slice(1:10)
```

<div class="img-proj">
    <p>Top 10 countries exporting to the United States, 2022</p>
    <img src="{{ '/assets/images/projects/p3-img6.png' | relative_url }}" class='img'>
</div>


We observe that the main exporters to the United States are in the same region, with the exception of China. Based on the most recent data concerning the imports of American companies, we notice that they maintain a privileged commercial relationship with Chinese companies, from which they import more than 497 billion dollars.

The trade deficit and this growing dependence on China are among the reasons that explain the first trade war under the first mandate of the Trump administration.

### 3. Breakdown of Chinese imports

For this figure, `ggplot2` is set aside in favour of a native `plot_ly` treemap. The reason is structural: a treemap has no Cartesian axes, so building it through `ggplotly()` would mean fighting the conversion. The `parents` argument is filled with empty strings, which declares a flat hierarchy of one single level:

```r
bilateral_2022 <- bilateral %>%
  filter(Year == 2022) %>%
  mutate(
    Part = Value / sum(Value, na.rm = TRUE),
    Label = paste0(
      Produits, "<br>",
      "Importation : ", label_number(scale = 1e-9, suffix = " Mds")(Value), "<br>",
      "Part : ", percent(Part, accuracy = 1)
    )
  )

plot_ly(
  data = bilateral_2022,
  type = "treemap",
  labels = ~Produits,
  values = ~Value,
  parents = rep("", nrow(bilateral_2022)),
  hovertext = ~Label,
  hoverinfo = "text",
  textinfo = "label+percent entry",
  marker = list(colorscale = "Greens")
)
```

<div class="img-proj">
    <p>Treemap of US imports from China by product family, 2022</p>
    <img src="{{ '/assets/images/projects/p3-img7.png' | relative_url }}" class='img'>
</div>

When we focus on the breakdown by family of the products imported from China, important information can be detected. Electrical and non-electrical machinery, together with manufactured products, represent around 60% of the imports coming from China in 2022. This testifies to a strong need for industrial products manufactured by the various companies on the other side of the Pacific. We may even suppose a domination of Chinese companies in the industrial sector and a fall in the competitiveness of the United States.

### 4. Customs duties

The tariff base covers six product families between 2017 and 2024. A `facet_wrap` with a free y-scale is used rather than a single set of superimposed lines, because the products do not start from the same level and a shared scale would flatten the smaller movements:

```r
ggplot(tarifs, aes(x = annee, y = tarif, color = produit)) +
  geom_line(size = 1.2) +
  geom_point(size = 2) +
  scale_y_continuous(labels = function(x) paste0(x, " %")) +
  scale_x_continuous(breaks = unique(tarifs$annee)) +
  labs(title = "Évolution des tarifs américains sur les produits chinois",
       y = "Taux de droit de douane (%)", caption = "Source: USITC") +
  theme_minimal(base_size = 13) +
  guides(color = 'none') +
  facet_wrap(~ produit, scales = "free_y")
```

<div class="img-proj">
    <p>Evolution of US tariffs on Chinese products by family, 2017–2024</p>
    <img src="{{ '/assets/images/projects/p3-img8.png' | relative_url }}" class='img'>
</div>

In sum, we have seen that the United States are in trade deficit, and that one of the countries taking the lion's share of this deficit is China. In response to this growing dependence, and because of the competition existing between these two great powers, the American government imposed tariffs to try to mitigate the situation, putting forward the protection of their markets against a set of unfair policies from Chinese competitors, judged disrespectful of environmental standards.

Since 2018, a set of measures has been put in place to that end. The figure above shows the increase of tariffs on Chinese products, with a rise going up to 25% on all the product families whose import volume was the highest, such as industrial, chemical and electrical products.

---

## IV. The Shiny dashboard

The report answers the questions we asked. The dashboard lets the reader ask their own. Every static filter of the report — the year fixed at 2024, the product fixed to total merchandise, the sector fixed to all activities — becomes an input.

### 1. Structure

The application is built with `shinydashboard` and organised in three pages that follow the same progression as the report: a general dashboard on world trade, a page on American imports, and a page confronting the United States and China.

```r
ui <- dashboardPage(
  dashboardHeader(title = "Commerce mondial"),
  dashboardSidebar(
    sidebarMenu(
      menuItem("Dashboard", tabName = "tabDashboard"),
      menuItem("Importations des USA", tabName = "Page2"),
      menuItem("USA vs Chine", tabName = "Page3")
    )
  ),
  dashboardBody(tabItems( ... ))
)
```

### 2. A single reactive feeding three outputs

The first page holds a map, a searchable table and a regional chart. Rather than filtering three times, the filtering is factored into one `reactive()` that the three outputs consume. A change of year therefore recomputes the subset once and refreshes the three visualisations consistently:

```r
data_reactive <- reactive({
  req(input$indic, input$type, input$year)
  echange %>%
    filter(Year == input$year,
           Produit == input$indic,
           Type == input$type,
           Country %in% world$name_long) %>%
    mutate(part = Value / sum(Value, na.rm = TRUE))
})
```

The `req()` call guards against the initial render, when the inputs are not yet initialised and the reactive would otherwise fail on an empty selection.

The table is rendered with `DT`, with search highlighting enabled so that a reader looking for one specific country finds it immediately:

```r
output$valeurs_pays <- renderDataTable({
  data_reactive() %>%
    arrange(desc(Value)) %>%
    select(Pays = Country, `Valeur (M$)` = Value, `Part (%)` = part) %>%
    mutate(`Part (%)` = percent(`Part (%)`, accuracy = 0.1))
}, options = list(pageLength = 10, lengthChange = TRUE,
                  autoWidth = TRUE, searchHighlight = TRUE))
```

### 3. Optional filters

On the second page, the country and sector selectors are multiple and empty by default. An empty selection has to mean "everything", not "nothing", so the filters are applied conditionally instead of being chained into the pipeline:

```r
rea <- usa %>%
  filter(Year == input$usa_year,
         Type == "Importation",
         Sector != "Toutes les activités")

if (!is.null(input$usa_country)) {
  rea <- rea %>% filter(Country %in% input$usa_country)
}

if (!is.null(input$usa_sector)) {
  rea <- rea %>% filter(Sector %in% input$usa_sector)
}
```

The `Sector != "Toutes les activités"` exclusion also matters: that modality is an aggregate of the other two, and keeping it would double the height of every stacked bar.

<div class="img-proj">
    <p>Shiny dashboard, world trade page</p>
    <img src="{{ '/assets/images/projects/p3-img9.png' | relative_url }}" class='img'>
</div>

<div class="img-proj">
    <p>Shiny dashboard, US vs China page</p>
    <img src="{{ '/assets/images/projects/p3-img10.png' | relative_url }}" class='img'>
</div>


### 4. Styling

The report uses a custom `theme.css` layered over the `readthedown` template, with a green palette matching the choropleth scales, so that the document reads as one coherent piece rather than as a series of figures pasted into a template:

```css
body {
  background-color: #f2f2f2;  
  --rd-color: #2e7d32;       
  --rd-color-light: #a5d6a7;  
  --rd-link-color: #2e7d32;   
  font-family: "Roboto", sans-serif;
}

h1, h2, h3 {
  background-color: #e0f2f1; 
  border-left: 5px solid #2e7d32; 
  padding: 10px 15px;
  border-radius: 4px;
}
```

---

## Conclusion

We have shown in this work that the Asian giant and the American giant maintain a complex commercial relationship. Moreover, following the rapid development of China, which allowed it to rise to a prime position on the world chessboard, the political divergences between these two great powers are at their peak.

Several voices have condemned China for practices they consider unfair (dumping, that is selling below cost or below the market price, and subsidies ) and for its aggressive development outside environmental standards. It is therefore not surprising that, under the pressure of numerous American lobbyists and in a concern to strengthen the power of the United States, president Trump, during his first mandate, considerably increased customs duties on the product families most appreciated by Americans. In 2018, the Trump administration imposed 25% tariffs on nearly 250 billion dollars of Chinese products, notably in strategic sectors such as electronics, industrial and chemical products, with the objective of rebalancing bilateral trade.

China, in retaliation, also increased its customs duties, while seeking to develop better commercial relations with other Asian countries as well as with Europe. This had a considerable impact on the exports of the United States. However, any good economist will say that exports generate imports: the less you export, the less you import. But where the shoe pinches is for the American consumer, who saw the prices of certain products (those coming from China ) increase significantly, especially in the sectors where demand is less sensitive to price. On the other hand, in the sectors where demand is more elastic, producers had to sacrifice their margins.

Back in the White House, president Donald Trump has promised to raise tariffs, this time up to **45%**. Questions are already being raised about the effectiveness of such measures, given the contested results of the first trade war. It is clear that the world, after decades of openness, seems to be closing in on itself. We may then ask: faced with the various challenges of everyday life, will the poorest people not find themselves in even greater difficulty in this new economic order?




<a href=" {{ '/assets/projects/commerce_int.html' | relative_url }} " class="btn-pages" target="_blank">
    View the dashboard
</a>