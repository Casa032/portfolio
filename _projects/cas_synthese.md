---
layout: project
title: "Business analysis"
date: 2025-12-20
tech: Semarchy , SQL , Power BI
tools: [Semarchy, SQL, Power BI]

---

End-to-end analysis of a business operations, from data transformation to visualization.

## Summary

For this project,we worked on the full chain of a BI pipeline, from raw CSV files all the way to a finished Power BI report. We started from a set of source files describing an e-commerce business (a product catalog, clients, orders placed online or in physical stores, browsing sessions, and city population reference data). Designed a target star schema for it, and then built the pipeline to get the data from the CSV files into that model: raw data is first loaded into an Oracle database, then transformed and integrated through the **Semarchy xDI** ETL, and finally consumed in **Power BI** for reporting.


<div class="img-proj">
    <p>Pipeline diagram</p>
    <img src="{{ '/assets/images/projects/p2-img1.png' | relative_url }}" class='img'>
</div>


Alongside the modeling and the ETL work, we also built a dedicated test suite (unit tests and integration tests) to check the quality of the data before and after loading, and we designed a nine-page Power BI report backed by a set of custom DAX measures. This post focuses in particular on the Semarchy xDI setup and on the Power BI / DAX side of the project.

## Development

### Pipeline overview

The overall architecture is fairly simple to describe in three steps: raw data arrives as CSV files, gets loaded into an **Oracle** database that acts as the data manager, and is then transformed by the **Semarchy xDI** ETL (Extract, Transform, Load) before being exposed to **Power BI**, our visualization tool, for the final dashboards.

### Source data and target model

The source files (documented in our data dictionary, the DDI) describe seven raw tables: a product catalog (`ID_PRODUCT`, `PRODUCT_NAME`, `PRICE`, `CATEGORY`), a clients table (`ID_CLIENT`, `AGE`, `INSCRIPTION_DATE`, `CITY`, `COUNTRY`), an orders table split by channel (online vs. physical), a sessions table (browsing behavior: duration, page visits, basket additions, payment, traffic source), and three country-specific population reference tables (France, UK, Spain).

From there, we designed a target star schema (documented in the MCDF and in a second data dictionary, the DICO_MCD, which renames and standardizes every column for the target model). The model has four fact tables : **Commande** (a general orders table), **Commande en ligne**, **Commande physique**, and **Sessions** ; and three dimension tables which are **Catalogue produit**, **Client**, and **Population**. `Commande` centralizes both order channels and links out to the client and product dimensions, while `Sessions` records browsing behavior and optionally references an order when a session converts into a purchase.

<div class="img-proj">
    <p>Star diagram</p>
    <img src="{{ '/assets/images/projects/p2-img2.png' | relative_url }}" class='img'>
</div>



### Loading and transforming the data with Semarchy xDI

Once Semarchy xDI Designer is installed and pointed at the right workspace, the key step is configuring a **metadata**. Semarchy's term for a connection to a data source, Oracle in our case. Two things matter here: making sure the Oracle JDBC driver (`ojdbc11.jar`) is registered under the metadata's module, and filling in the connection details correctly:

```
Driver: oracle.jdbc.OracleDriver
URL:    jdbc:oracle:thin:@<host>:dddd/<service_name>
User:   username
Password: password
```


Semarchy xDI organizes its work around three concepts, which we found useful to keep straight while building the project:

- **Mappings** : he link between two tables, used together with integration templates to define how data flows from a source to a target.
- **Metadata** : the connection definitions used to pull data from a source (here, Oracle).
- **Processes** : a way to orchestrate and group the execution of several mappings, and to parameterize them.


### Data quality: unit and integration tests

To make sure the mappings actually behaved as intended, we built a dedicated test file rather than describing tests in prose. It's organized around two kinds of checks, applied to every table in the model (product catalog, clients, population, orders, online orders, physical orders, sessions), each time on a sample of 10 distinct rows:

- **Unit tests**, which check data quality before and after loading into Semarchy - making sure business rules are correctly applied and that the parameters we configured behave as expected.
- **Integration tests**, which check volume and consistency - verifying that the exact expected number of rows made it through, and that each individual record is correct.

Concretely, for each table we worked through three stages: 
1. **extraction** (the raw `INSERT` statements representing the source data), 
2. **collect** (the same data as staged before transformation), 
3. **distribution** (the data as it lands in the target table, e.g. `CQ_TAB_CAT_PRO`) comparing the three side by side. For example, on the product catalog, this approach caught a duplicate row (`P_705094`, "Boucles Infini") that had been inserted twice at the source, which we could then flag and track through the pipeline rather than have it silently distort the target counts.

### The Power BI report and DAX measures

On the reporting side, we built the data model directly in Power BI on top of the Oracle target tables, then wrote a full set of DAX measures to drive nine report pages: **Home**, **Dashboard**, **Dashboard_Produit**, **Dashboard_Pays**, **Dashboard_évolution**, **client**, **site web**, **site web précognisation**, and **Commande**. Combining KPI cards, line and area charts, a clustered column chart, a funnel, a map, and a decomposition tree, depending on the page's focus.

Since the source tables didn't include a proper date table, the first thing we built was a calculated **calendar table**, derived dynamically from the earliest and latest dates found across the `Commande` and `Sessions` tables:

```python
Calendrier =
VAR MinDateCommande = MIN ( Commande[Date de commande] )
VAR MinDateSession  = MIN ( Sessions[Date de création de session] )
VAR MaxDateCommande = MAX ( Commande[Date de commande] )
VAR MaxDateSession  = MAX ( Sessions[Date de création de session] )

VAR MinDate = MIN ( MinDateCommande, MinDateSession )
VAR MaxDate = MAX ( MaxDateCommande, MaxDateSession )

RETURN
ADDCOLUMNS (
    CALENDAR ( MinDate, MaxDate ),
    "Année", YEAR ( [Date] ),
    "NumMois", MONTH ( [Date] ),
    "Mois", FORMAT ( [Date], "[$-fr-FR]mmmm" ),
    "Trimestre", "T" & FORMAT ( [Date], "Q" ),
    "Semestre", "S" & ROUNDUP ( MONTH ( [Date] ) / 6, 0 ),
    "Jour", DAY ( [Date] ),
    "NomDuJour", FORMAT ( [Date], "[$-fr-FR]dddd" )
)
```

That calendar table then powers every time-based analysis in the report. Filtering by year, quarter, or month, and enabling time-intelligence measures. Revenue itself is a straightforward sum, with a "total fixed" variant that ignores any filter context, useful for percentage-of-total calculations:

```python
CA = SUM( Commande[Montant total de la ligne de commande] )

Nombre client Total Fixe =
CALCULATE(
    [Nombre de client],
    REMOVEFILTERS()
)
```

On top of that, we used `TOPN` to build a family of "best of" measures ( best month, best country, best product, best traffic source ) all following the same pattern of ranking a dimension by a chosen metric and keeping the top row:

```python
Meilleur mois =
TOPN(
    1,
    ALL(Calendrier[Mois]),
    [CA],
    DESC
)

Meilleur pays =
TOPN(
    1,
    ALL(Population[Pays]),
    [CA],
    DESC
)

Meilleur reseau =
TOPN(
    1,
    ALL(Sessions[Nom du réseaux]),
    [Nombre de sessions],
    DESC
)
```

For year-over-year comparisons, we relied on Power BI's built-in time-intelligence functions rather than reimplementing the date shifting by hand:

```python
CA_Année_Dernière =
CALCULATE(
    [CA],
    DATEADD(Calendrier[Date], -1, YEAR)
)
```

Finally, for the "site web" pages, we needed to isolate sessions that never converted into a client. A simple `CALCULATE` combined with `ISBLANK` on the client key did the job:

```python
Nombre_sessions_non_client =
CALCULATE(
    COUNT(Sessions[Numéro de la session]),
    ISBLANK(Sessions[Numéro du client])
)
```


<div class="img-proj">
    <p>Power BI report</p>
    <img src="{{ '/assets/images/projects/p2-img3.png' | relative_url }}" class='img'>
    <img src="{{ '/assets/images/projects/p2-img4.png' | relative_url }}" class='img'>
    <img src="{{ '/assets/images/projects/p2-img5.png' | relative_url }}" class='img'>
</div>

Across the nine pages, this small library of measures gets reused and recombined: the same `TOPN` pattern surfaces the best product, best country or best traffic source depending on the page; the same time-intelligence logic drives both the year-over-year revenue comparison and the evolution charts; and the percentage-style measures (share of revenue, share of orders, online vs. physical split) all divide a filtered measure by its "total fixed" counterpart.

## Conclusion

This project let us work through a full, realistic BI chain rather than a single isolated tool: modeling a source-to-target mapping, actually operating an ETL (Semarchy xDI) to move and transform data into Oracle, writing tests to validate that the transformation did what it was supposed to, and then building a genuinely useful Power BI report on top of it, backed by a coherent, reusable set of DAX measures.

The Semarchy xDI part taught us to think in terms of metadata, mappings and processes as separate, composable building blocks, and made clear how much groundwork (driver compatibility, connection parameters, refreshing metadata correctly) sits underneath what looks like a simple "run the process" click. On the Power BI side, building the calendar table and the `TOPN`/time-intelligence measures ourselves  rather than relying only on built-in visuals gave us a much better sense of how a handful of well-designed DAX measures can support an entire multi-page report.