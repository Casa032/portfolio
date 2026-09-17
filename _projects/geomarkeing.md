---
layout: project
title: "Geomarketing with QGIS: Picking a Catchment Area for a New Hardware Store"
date: 2025-09-24
tech: Argis, Qgis
tools: [Argis, Qgis]

---

*A study for a potential hardware store near Saint-Omer: building 10/20/30 km catchment rings, joining socio-demographic data at the commune level, and mapping 47 competitors to assess the site's potential and its risks.*

## Summary

For this project, we carried out a geomarketing study for a new **Bricomagic** hardware store (store #25 - fake by the way), located at 41 rue de Calais, in Saint-Martin-lez-Tatinghem, on the outskirts of Saint-Omer. The goal was to evaluate the commercial potential of the site and its catchment area, and to issue concrete recommendations on how the store should position itself.

The whole study was carried out in **QGIS**. We geolocated the site, drew iso-distance rings around it at 10, 20 and 30 km using the Multi-Ring Buffer tool, and joined socio-demographic data (population, households, housing types) from the Hauts-de-France region to the communes falling within each ring. In parallel, we built a competitor layer from open data, geocoded and filtered it, and mapped it against the same catchment area. The result is a set of thematic maps and a synthesis table that we used to size the market and shape our final recommendations.

## Development

### The site and its surroundings

Bricomagic store #25 sits in Saint-Martin-lez-Tatinghem, on the north-western outskirts of Saint-Omer, right on the border with the Nord department. The site is directly served by the D928 and sits close to the Rocade de Saint-Omer, the D943 and the A26 motorway which means it benefits from Saint-Omer's urban catchment while also being able to draw customers from across the Pas-de-Calais/Nord border. Locally, it's next to the attractive Zone d'Activités du Fond Squin, has direct visibility from the D928, and offers easy car access with a sufficiently large parking area.

<div class="img-proj">
    <p>Site location and access roads (D928, Rocade de Saint-Omer</p>
    <img src="{{ '/assets/images/projects/p5-img1.png' | relative_url }}" class='img'>
</div>


### Methodology: building the catchment area in QGIS

The whole study was built in QGIS. We started by geolocating the site, then drew three iso-distance rings around it : 10, 20 and 30 km using the **Multi-Ring Buffer** tool, shading them from darkest (closest to the store) to lightest (furthest away).

The trickier part was assigning the right commune to the right ring when a commune straddles two rings. To handle that, we:

1. Built a layer of commune **centroids**.
2. Intersected the centroids layer with the communes layer, then with the multi-ring buffer layer.
3. Used the resulting intersection to get every commune of the catchment area, each one correctly assigned to a single ring based on where its centroid falls.

From that intersection layer, we ran a join with socio-demographic data for the Hauts-de-France region (population, households, housing categories, etc.), which let us aggregate the indicators we needed at the ring level.

For the thematic maps (households, percentage of owners, average consumption), we applied color scales based on the underlying indicator: **quartiles** for the households variable, and **equal intervals** for the percentage of owners and the average consumption.

<div class="img-proj">
    <p>Map - 10/20/30 km multi-ring buffer around the store</p>
    <img src="{{ '/assets/images/projects/p5-img2.png' | relative_url }}" class='img'>
</div>


### Defining the catchment area

The catchment area stretches from the Belgian border to the Opal Coast, straddling the Pas-de-Calais and Nord departments, and breaks down into three zones:

- **Primary zone [0–10 km]** : the Saint-Omer urban area, the most dynamic zone and the core of the store's commercial potential.
- **Secondary zone [10–20 km]** :  a more rural population, with a large residential base that may be willing to travel for equipment.
- **Tertiary zone [20–30 km]** :  an area strongly polarized by Lillers, Hazebrouck, Calais and Dunkirk, where the store's pull is more limited against competing hubs.

### Synthesis table

Aggregating the socio-demographic data by ring gave us the following picture:

| Zone | Households | Population | Owners (%) | Renters (%) | Market (€/year) | Avg. spend (€/household/year) | Avg. spend (€/person/year) |
|---|---|---|---|---|---|---|---|
| [0–10 km] | 35,171 | 84,123 | 76.11% | 23.89% | 65,860,736.60 | 2,047.37 | 806.22 |
| [11–20 km] | 36,598 | 93,426 | 81.79% | 18.21% | 74,560,927.97 | 2,072.90 | 795.17 |
| [21–30 km] | 102,565 | 258,956 | 79.37% | 20.63% | 199,362,884.11 | 2,033.81 | 781.43 |
| **Total zone** | **174,334** | **436,505** | **79.76%** | **20.24%** | **339,784,548.68** | **2,048.35** | **789.03** |

Altogether, the catchment area represents close to **440 million euros** of annual market potential across roughly 174,000 households. A sizeable opportunity, even before accounting for competition.

### Thematic analysis

Looking at **households**, the north-western part of the catchment area is densely populated, meaning a higher rate of potential customers there, while the south-eastern part is sparser and more rural; fewer customers, but potentially higher basket sizes per household.

<div class="img-proj">
    <p>Thematic map - households by commune, catchment area</p>
    <img src="{{ '/assets/images/projects/p5-img3.png' | relative_url }}" class='img'>
</div>


On **home ownership**, close to 80% of the catchment area's population are homeowners, which points toward demand for large-scale work (renovations, extensions, kitchens, etc.). Saint-Omer itself has the lowest concentration of renters in the zone, suggesting more frequent but smaller-scale projects there. Taken together, this points toward centering the offer on large-scale renovation work, without neglecting the proximity customer segment, which is made up mostly of renters.

<div class="img-proj">
    <p>Thematic map - percentage of homeowners by commune</p>
    <img src="{{ '/assets/images/projects/p5-img4.png' | relative_url }}" class='img'>
</div>


On **consumption**, most of the catchment area shows high spending, above €2,000 per household per year, consistent with sizeable renovation projects. Saint-Omer itself has the lowest consumption level of the primary zone, between €1,500 and €1,750 a proximity customer base with a more limited budget.

<div class="img-proj">
    <p>Thematic map - average consumption per household by commune</p>
    <img src="{{ '/assets/images/projects/p5-img5.png' | relative_url }}" class='img'>
</div>


### Competitor analysis

The competitor layer  was built from an open dataset available on data.gouv.fr, listing stores across France. After extracting and cleaning the data, selecting the relevant retail chains, and checking coordinates via Google Maps, we imported the competitor points into QGIS and produced a structured file with their IDs, addresses, coordinates and retail chains. From that layer, we could filter by chain name and apply the matching logo to each franchise on the map.

On the Saint-Omer agglomeration alone, **13 competitors** are present: **5 national chains** (Gamm Vert, Point P, Screwfix, Bricoman and Chausson Matériaux) and **8 independent stores** (an already fairly competitive local market.)

<div class="img-proj">
    <p>Competitors in the Saint-Omer agglomeration</p>
    <img src="{{ '/assets/images/projects/p5-img6.png' | relative_url }}" class='img'>
</div>


Across the full 30 km catchment area, that count rises to **47 competitors**: **29 belonging to 10 national chains** (Gamm Vert, Point P, Screwfix, Bricoman, Chausson Matériaux, Leroy Merlin, Mr Bricolage, Weldom and BigMat) and **18 independent stores** confirming that this is an ultra-competitive zone where differentiation is essential.

<div class="img-proj">
    <p>All competitors across the 30 km catchment area</p>
    <img src="{{ '/assets/images/projects/p5-img7.png' | relative_url }}" class='img'>
</div>


### Conclusion (from the study)

Weighing the advantages against the drawbacks, the site benefits from strong **accessibility and visibility** (served by the D928, close to the Rocade de Saint-Omer) and sits on a catchment area with real **commercial potential**. Close to €440 million a year across 174,334 households, with close to 80% of the population being homeowners, which favors larger-scale projects.

On the other hand, the site operates in an **ultra-competitive environment** (13 competitors in the agglomeration, 47 across the full catchment area), and it partly **excludes a segment of Saint-Omer's renters**. A proximity customer base due to limited public transport options.

### Recommendations

Building on these findings, we formulated four recommendations for the store:

- **Target large-scale renovation work**, which concerns the homeowner segment specifically.
- **Don't neglect the proximity customer base**: keep an offer geared toward smaller, more frequent projects, aimed mainly at local renters.
- **Differentiate through complementary services** : delivery, tool rental, take-back of unused materials, cutting services, expert advice.
- **Build a professional offer**: a dedicated counter for tradespeople, with faster service, specific pricing, and extended opening hours.

## Conclusion

This project let us apply the classic geomarketing toolkit: multi-ring buffers, centroid-based spatial joins, choropleth thematic mapping, and open-data competitor mapping to a real siting question. The centroid/intersection technique in particular was the key methodological choice: without it, communes straddling two rings would have been miscounted or double-counted, which would have distorted every aggregate figure downstream. Combining the demographic side (market size, ownership, spending) with the competitive side (13 competitors locally, 47 across the whole zone) gave a much more balanced view of the site than either analysis would have on its own, and translated directly into recommendations that go beyond "the market is big enough" to actually addressing how the store should differentiate itself in a crowded market.