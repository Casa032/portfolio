---
layout: project
title: "Data Mining: Banking Product Associations for Cross-Selling"
date: 2025-11-30
tech: Sas
tools: [Sas]
---

*Data mining project where we make recommendations based on cross-selling strategies.*

## Summary

For this project, we study the associations between the banking products and services held by the customers. The bank had a database describing, for each of its 72,531 customers, which of 26 binary products/services they held (payment methods, accounts, savings, credit, insurance, protection plans, etc.), and the goal was to understand how these products combine with each other in order to identify cross-selling opportunities.

We worked in SAS throughout: importing and describing the data, handling missing values, excluding non-informative variables, regrouping the 26 individual products into 7 broader product families, and then mining association rules. First at the family level, then at the more granular product level based on the classic support / confidence / lift indicators. We closed the project with concrete, business-facing recommendations for the bank's marketing team.


## Development

### Exploring and describing the data

The dataset contains 72,531 customers and 26 variables, all binary (holds the product or not): bank cards, current account, overdraft, service packages, various types of credit (consumer, home, renovation), insurance (auto, home, health, personal-accident guarantee, legal protection), savings and life insurance products, and investment products (stocks, bonds, mutual funds).

None of the product variables had missing values. The `SEXE` (gender) variable, on the other hand, had 1,283 missing values (about 1.8% of the base). Since gender is not needed to build association rules and using it in a recommendation engine could introduce an ethical/regulatory bias by differentiating commercial offers by gender we excluded it from the association-rule analysis, but kept it for a separate descriptive analysis of product appetite by gender later in the report. Because every variable is strictly binary, there was no risk of out-of-range or otherwise inconsistent values, and our checks confirmed none were present.

We also excluded three additional variables from the analysis: `DAV` (current account, held by 99.04% of customers too common to be discriminant), `SEVDOM` (home assistance / remote monitoring, held by only 1.62%  too rare to yield actionable rules), and the combined variable `ASSPREVDECDEP`, which simply duplicates the union of two other variables we already keep separately.

### Grouping products into families

To make the analysis more readable and business-relevant, we grouped the 26 individual products into 7 families using simple conditional flags in a SAS data step:

```sas
data ds.data;
    set ds.data;
    if cart=1 or cjeu=1 or cpai=1 or carte=1 then cb=1; else cb=0;
    if credconso=1 or credhab=1 or credrenov=1 then credit=1; else credit=0;
    if assprevdec=1 or assdep=1 or sante=1 or gav=1 then assurance_personne=1; else assurance_personne=0;
    if auto=1 or pj=1 or assmh=1 then assurance_dommage=1; else assurance_dommage=0;
    if packserv=1 or decauth=1 then services=1; else services=0;
    if eparlog=1 or assvieeuro=1 or csl=1 or eparbanc=1 then epargne=1; else epargne=0;
    if action=1 or obligation=1 or sicavfcp=1 then placement=1; else placement=0;
run;
```

This gave us seven families: **Payment methods** (bank card, youth card, payment card), **Credit** (consumer, home, renovation), **Personal insurance** (death protection, dependency protection, health, GAV), **Damage insurance** (auto, home, legal protection), **Banking services** (service package, authorized overdraft), **Savings / life insurance** (home savings, life insurance, savings account, bank savings), and **Financial investments** (stocks, bonds, mutual funds).

<div class="img-proj">
    <p>Equipment rate of customers by product family</p>
    <img src="{{ '/assets/images/projects/p4-img1.png' | relative_url }}" class='img'>
</div>


Looking at how equipped customers are per family, **Damage insurance** (94.1%), **Savings** (87.8%), **Payment methods** (85.0%) and **Banking services** (83.6%) are the most widely held - they form the backbone of the banking relationship. **Credit** sits in the middle (60.9%), typically tied to a specific personal or real-estate project, while **Personal insurance** (31.1%) and **Financial investments** (28.2%) are the least diffused families, and therefore the ones with the most room to grow.

### Methodology: support, confidence and lift

To measure how meaningful an association between two products is, we relied on the three classic association-rule indicators:

- **Support** : how frequently the pair appears across the whole customer base; a higher support means the association concerns a larger share of customers.
- **Confidence** : the probability that a customer holds product B given that they already hold product A; it reflects the strength and business usefulness of a recommendation.
- **Lift** : checks that the association isn't just due to chance, by comparing observed co-occurrence to what independence would predict. A lift above 1 signals genuine complementarity between two products.

We computed these directly in SAS rather than through a dedicated association-rule mining procedure, building the support/confidence/lift matrices "by hand" from aggregated counts:

```sas
%macro tableau2(x);
proc sql;
create table &x as select
    sum(cb) as cb, sum(services) as services, sum(placement) as placement,
    sum(credit) as credit, sum(assurance_personne) as assurance_personne,
    sum(assurance_dommage) as assurance_dommage, sum(epargne) as epargne
from ds.data
where &x=1;
quit;
%mend tableau2;

%tableau2(cb); %tableau2(services); %tableau2(placement);
%tableau2(credit); %tableau2(assurance_personne);
%tableau2(assurance_dommage); %tableau2(epargne);
```

For each family `&x`, this macro sums up how many of its holders also hold each of the other six families. Support is then simply that count divided by the total customer count, confidence divides the pairwise support by the "row" family's own support, and lift divides the confidence by the "column" family's own overall support:

```sas
data ds.support2;
    set etape2;
    array n[7]  cb credit services epargne placement assurance_personne assurance_dommage;
    array s[7]  scb scredit sservices separgne splacement sassurance_personne sassurance_dommage;
    do i=1 to dim(n);
        s[i] = n[i]/&NCLIENT;   /* support as a proportion */
    end;
run;

data ds.lift2;
    set ds.confiance2;
    lcb    = ccb   / &p_cb;
    lcredit = ccredit / &p_credit;
    /* ... one division per family, confidence over the target's own support ... */
run;
```

We then transposed these wide tables into a long "item_i / item_j / support / confidence / lift" format with a small `do`-loop over arrays, so we could read the results as a proper 2D matrix with `proc tabulate`, and rank all pairs by lift with `proc sort` + `proc print`. We repeated the exact same logic at the individual-product level afterwards, this time looping over 15 products instead of 7 families.

### Choosing the thresholds

For the family-level analysis, we deliberately used fairly loose thresholds, since we wanted to surface only the big, structuring trends: a minimum **support of 10%** (so the association concerns a meaningful share of the customer base), a minimum **confidence of 60%** (so that holding one family gives better-than-half odds of holding the other), and a **lift above 1.05**  a low bar, but appropriate at this aggregated, high-volume level, where even a small over-representation can reveal a real purchasing pattern.

At the product level, we relaxed these thresholds to surface more actionable, fine-grained opportunities: a minimum **support of 1%**, a minimum **confidence of 30%**, and a **lift above 1.2**, to make sure the association reflects a genuine affinity rather than statistical coincidence.

### Family-level associations

Working through the pairs of families that cleared our thresholds, a few clear patterns emerged. **Savings customers are a strong entry point into investment products**: almost all customers who already hold an investment product also hold a savings product (95% confidence), even though the reverse is much weaker (only 3 in 10 savers also invest) suggesting savers can be gradually steered toward low-risk investment products.

**Banking-services customers are a solid base for credit offers**: about 90% of credit holders also have a banking-service product, and the relationship, while more moderate in the other direction (65%), is still a useful entry point. Similarly, **banking services act as a gateway to personal insurance** (27% joint holding) and payment-method holders are a good target for personal insurance as well.

**Payment methods and credit** are held together by half the customer base, with 64% of card holders also holding a credit product — a real, if modest, cross-selling opportunity. **Payment methods and banking services** show a stronger pattern: 75% of customers hold both, and nearly 9 in 10 holders of either product also hold the other (lift of 1.05), supporting a combined "services + card" offer.

Finally, **personal insurance and investment products**, although just below our stricter thresholds, showed a lift of 1.27 ( holding one increases the odds of holding the other by 27% ) making it a strong candidate for a bundled offer aimed at customers who value both protection and investment.

### Product-level associations

Relaxing the thresholds to look product by product revealed the **GAV contract (Personal Accident Guarantee)** as a real hub within the insurance family. It has a strong relationship with dependency/disability protection (lift of 4.38 thus holding the protection plan more than quadruples the odds of holding GAV) and a solid relationship with health insurance (2,176 joint holders), suggesting a combined "protection + health" package.

GAV also bridges into damage insurance: it's linked to auto insurance (lift of 1.39) and, even more strongly, to legal-assistance contracts (5,077 joint holders, 70% confidence from the GAV side), supporting a bundled "personal + legal + auto" security package. Protection-plan holders (whether dependency or death protection) also showed a meaningful link to legal assistance, with dependency-protection holders 50% more likely to also hold legal assistance.

On the savings side, **bank savings strongly predicts life insurance** (lift of 2.4) and, even more so, home savings (68% confidence, +84% odds). Pointing to customers who progressively move from simple savings toward home-ownership projects and then toward life insurance. **Life insurance and home savings** turned out to be genuinely bidirectional, with nearly 7,978 customers holding both, reflecting a coherent long-term wealth-management logic.

Across insurance and savings, **GAV also connects to home savings** (36% higher odds) and, more surprisingly, only weakly to life insurance (38% confidence) likely because the two products serve overlapping needs and customers tend to pick one rather than both, which is itself an opportunity to sell them on their complementary strengths rather than their overlap.

At the family × product level, we found that **GAV and dependency protection holders are 60% more likely to hold an investment product** (twice as likely for GAV holders specifically), and that **home savings and life insurance holders are strongly linked to investment products** (11,604 joint holders for home savings + investment, 7,978 for life insurance + investment)  a natural basis for a progressive wealth-building offer.

### Gender-based appetite

Gender information was missing for 1,283 customers, and overall, most products skew male (roughly 60/40). Two products stand out with a particularly strong skew:

| Product | Men (%) | Women (%) |
|---|---|---|
| Bank cards | 71.23 | 28.77 |
| Home credit | 75.68 | 24.32 |

This suggests these two products could be specifically promoted toward the male customer segment where they're already over-represented — while being mindful, as noted earlier, that gender was deliberately excluded from the core association-rule engine for ethical reasons.

### Recommendations

Based on all of the above, we translated our findings into a small playbook for the bank's marketing team:

- **Protection-plan holders** (death or dependency protection) → offer a GAV as a natural extension of their existing coverage, then, depending on their financial profile, steer them toward investment products.
- **Existing GAV holders** → add legal protection (the strongest association after protection plans); if they own a vehicle, propose auto insurance; if they're renters or young professionals, promote home savings; if they have available savings, propose life insurance and then investment products; if they already hold a protection plan, complete their coverage with health insurance.
- **Savings holders** (home or bank savings) → propose life insurance, then investment products, then highlight GAV as a complementary personal-protection layer.
- **Gender-based targeting** → promote bank cards and home credit more heavily toward male customers, where uptake is already concentrated.

### Associations to avoid

Not every pair of products behaves as complements — some behave as substitutes, where holding one actually lowers the odds of holding the other, making them poor candidates for joint offers:

- **Death protection <=> Savings** : customers oriented toward death protection are generally not in a savings mindset, and vice versa.
- **Banking services / Credit <=> Investments / Structured savings** : customers focused on day-to-day banking or currently repaying credit tend to be focused on managing current expenses, not investing.
- **Health insurance <=> Damage insurance / Savings** : these products correspond to different life moments and priorities, with little observed overlap.

## Conclusion

Working through this project taught us to move between two levels of granularity: a macro view at the family level, which surfaces the big structuring relationships (savings as a gateway to investment, banking services as a gateway to credit and personal insurance), and a micro view at the individual-product level, which pinpoints exactly which products carry the strongest, most actionable value. GAV in particular emerged as a real hub within the insurance family.

The core takeaway is that commercial potential doesn't come from concentrating on a single flagship product, but from combining several complementary ones. Building the support/confidence/lift pipeline by hand in SAS (rather than relying on a packaged association-rule procedure) also forced us to be precise about what each indicator actually measures and why the choice of thresholds changes what "interesting" means at each level of analysis. Combining the macro and micro views gives Up Bank a clear, actionable roadmap for its cross-selling campaigns.