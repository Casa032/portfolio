---
layout: project
title: "Predicting Road Accident Severity in France (BAAC 2019–2024)"
date: 2026-01-01
tech : Machine learning, Scikit-learn, Git, Numpy, Pandas
tools: [Machine learning, Scikit-learn, Git, Numpy, Pandas]

---

A full MLOps project built on the French national road accident database (BAAC, 2019–2024). The goal is to train a binary severity classifier tracked with MLflow. The final model detects close to 7 severe accidents out of 10 as soon as the accident is reported.





## Summary

The project addresses a major public health issue: road safety. We work on the French National File of Injury Road Accidents (BAAC), the statistical reference for road accidents in France, which is fed by the reports written by the police forces intervening on the accident site. Our scope covers the 2019–2024 period, which allows us to integrate the recent evolutions of mobility (the rise of electric scooters, for instance) while taking into account the traffic variations linked to past health crises.

The central objective is to design a robust machine learning model able to predict, in real time, the severity of an accident as soon as it is reported. The model classifies each accident according to a criticality score (Light vs Severe/Fatal). Downstream, this score is meant to optimise resource allocation: identifying instantly whether heavy means (SMUR, helicopter) are required, adjusting the staff dispatched on site and on a longer horizon, identifying recurring severity factors in order to suggest infrastructure improvements to public authorities.

The final deliverable is made of two notebooks (exploration and modelling on one side, MLflow tracking on the other), a reproducible join script, and a written report.

---

**Data source:** [Annual databases of injury road accidents - data.gouv.fr](https://www.data.gouv.fr/datasets/bases-de-donnees-annuelles-des-accidents-corporels-de-la-circulation-routiere-annees-de-2005-a-2024)   

**Repository link:** [GitHub repository for the project](https://github.com/Casa032/ml_project.git)

---

## I. Building the dataset

### 1. Merging the four source tables

The BAAC data is split into four complementary tables that have to be merged to obtain a complete view of each event:

| Table | Content |
| :---- | :---- |
| Caractéristiques | Temporal circumstances, weather conditions, intersection type, luminosity |
| Lieux | Road network (motorway, departmental road), lane number, traffic regime |
| Véhicules | Vehicle category, initial point of impact, manoeuvre performed |
| Usagers | Victim profile (age, sex), safety equipment (seat belt, helmet), health severity |

The merge is handled by a dedicated script rather than inside a notebook. The reason is reproducibility: the raw files change format slightly from one year to another (column naming, non-breaking spaces, keys exported as floats), so the cleaning has to be centralised and re-runnable.

The script loads each table for every year between 2019 and 2024, harmonises the columns across years, then normalises the join keys:

```python
def normaliser(data: pd.DataFrame) -> pd.DataFrame:
    # column cleaning
    data.columns = (
        data.columns.str.strip()
                  .str.lower()
                  .str.replace(" ", "_")
                  .str.replace("-", "_")
                  .str.replace("é", "e")
    )

    # text columns cleaning
    for col in data.select_dtypes(include='object').columns:
        data[col] = data[col].str.replace('\xa0', '', regex=False).str.strip()

    # num_acc normalisation
    if "num_acc" in data.columns:
        data["num_acc"] = (
            data["num_acc"]
            .astype(str)
            .str.strip()
            .str.replace(".0", "", regex=False)
        )
    ...
```

The merge itself follows the natural granularity of the data. We start from the finest level (one row = one road user), attach the vehicle the user was in, then the accident context:

```python
# USAGERS <- VEHICULES (num_acc + id_vehicule)
data1 = usagers.merge(vehicules, on=["num_acc", "id_vehicule", "annee"],
                      how="left", suffixes=("_usag", "_veh"))

# + CARACTERISTIQUES (num_acc)
data2 = data1.merge(caracteristiques, on=["num_acc", "annee"], how="left")

# + LIEUX (num_acc)
master = data2.merge(lieux, on=["num_acc", "annee"], how="left")
```

The resulting master table covering 2019–2024 contains **820,413 observations and 58 variables**.

### 2. Missing values

The analysis revealed important disparities in the filling rate of the variables. Some of them are massively empty, such as `lartpc` (width of the central reservation), `occutc` (number of public transport occupants) and `v2` (alphanumeric road index). Variables with more than 90% missing values were dropped or transformed  `lartpc`, for example, was converted into a binary indicator of the presence of a central reservation rather than being discarded entirely:

```python
if "lartpc" in df.columns:
    df["presence_bande_cyclable"] = df["lartpc"].notna().astype(int)
    df = df.drop(columns=["lartpc"])

cols_to_drop_df = [c for c in ["v2", "voie"] if c in df.columns]
if len(cols_to_drop_df) > 0:
    df = df.drop(columns=cols_to_drop_df)
```

The free-text variable `adr` was also removed, being too heterogeneous for a standard model.

### 3. Outliers and anomalies

The Interquartile Range (IQR) method was applied to every numerical variable in order to flag aberrant values. Two cases required a business decision.

Regarding speed, 25,764 records at 0 km/h and 225 records above 130 km/h (going up to 901) were identified. These values were imputed by the median of the plausible range (50 km/h):

```python
vma_valid = df.loc[(df["vma"] > 0) & (df["vma"] <= 130), "vma"]
vma_median = vma_valid.median()

df.loc[df["vma"] <= 0, "vma"] = vma_median      # includes -1
df.loc[df["vma"] > 130, "vma"] = vma_median
```

Regarding age, 201 extreme cases (> 110 years) were detected through `an_nais`. In the BAAC coding scheme, `-1` is used as a "not filled in" code across many categorical variables, which cannot be left as is before encoding. We replaced it by the mode computed on valid values only, so that the imputation never propagates the missing code itself.


### 4. Geographic check

Before moving to feature engineering, we plotted the accidents on a map to verify the coordinates were usable. Latitude and longitude are stored as strings with comma decimal separators, so they need to be converted first, then filtered on metropolitan France:

```python
df["lat"] = df["lat"].astype(str).str.replace(",", ".", regex=False)
df["long"] = df["long"].astype(str).str.replace(",", ".", regex=False)
df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
df["long"] = pd.to_numeric(df["long"], errors="coerce")
df = df.dropna(subset=["lat", "long"])

df = df[(df["lat"] >= 41) & (df["lat"] <= 51)]
df = df[(df["long"] >= -5) & (df["long"] <= 10)]

geometry = [Point(xy) for xy in zip(df["long"], df["lat"])]
gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326").to_crs(epsg=3857)

fig, ax = plt.subplots(figsize=(10, 12))
gdf.plot(ax=ax, column="grav", cmap="Reds", markersize=5, alpha=0.6, legend=True)
ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
```

GeoPandas is used to build the geometry, Shapely to create the points, and contextily to add the OpenStreetMap basemap. The reprojection to EPSG:3857 (Web Mercator) is mandatory here, otherwise the tiles and the points do not align.

## II. Analysis and feature engineering

### 1. Descriptive analysis and profiling

Our target variable is distributed as follows (after removal of the unreported values):

|-------|:-----:|--------:|
| Unharmed| 42.45% (348,299 users)|
| Slightly injured| 39.90% (327,378 users)|
| Hospitalised injured| 15.04% (123,399 users)|
| Killed| 2.55% (20,880 users)|

The population involved in accidents is mostly male (551,793 men against 256,335 women), with a median age of 38 years. Accidents mainly occur in urban areas, the most frequent maximum authorised speed (VMA) being 50 km/h (397,431 cases), although the average stands at 58.4 km/h.


### 2. Defining the target at accident level

The raw `grav` variable describes the injury severity **of a road user**, not of the accident. Since the business objective is to trigger emergency resources for an event, the target has to be redefined at accident level.

According to the official ONISR documentation, `grav = 1` is unharmed, `2` killed, `3` hospitalised injured and `4` slightly injured. We therefore define an accident as severe if at least one user is killed or hospitalised:

```python
df["is_grave_usager"] = df["grav"].isin([2, 3]).astype(int)

target_acc = (
    df.groupby("num_acc")["is_grave_usager"]
    .max()
    .reset_index()
    .rename(columns={"is_grave_usager": "grav_acc"})
)
```

|-------|--------|
| Class 0 (Light)| unharmed (1) and slightly injured (4)
| Class 1 (Severe)| killed (2) and hospitalised injured (3)  around 35.8% of the accidents in the base

Before freezing this rule, we tested several competing definitions and compared the resulting proportion of severe accidents, in order to make sure that a coding error would not mechanically label 95% of the base as severe.

### 3. Aggregating users and vehicles

The dataset has to be brought from user level to accident level (one row = one accident). Here we deliberately did **not** keep fine-grained statistics such as the average or median age of the victims, because that kind of information is not realistically available at the moment of the emergency call. Instead we built simple indicators that a witness or a first responder can state immediately:

```python
df["is_pieton"] = (df["catu"] == CATU_PIETON).astype(int)
df["is_enfant"] = (df["age"] < 14).astype(int)
df["is_senior"] = (df["age"] >= 65).astype(int)

df_agg1 = df.groupby("num_acc").agg(
    nb_usager=("id_usager", "count"),
    nb_hommes=("is_homme", "sum"),
    nb_femmes=("is_femme", "sum"),
    presence_pieton=("is_pieton", "max"),
    presence_enfant=("is_enfant", "max"),
    presence_senior=("is_senior", "max"),
).reset_index()
```

Reporting the presence of a single fragile person is often enough to tip the accident into the "Severe" category, which is exactly what these `presence_*` flags are designed to capture.

The same logic is applied to vehicles. The `catv` codes were grouped into 7 business families following the official BAAC mapping, then aggregated with a `max` so that the feature reads as "at least one vehicle of this family was involved":

```python
MAP_CATV_TO_FAM = {
    "velo": set([1, 80]),                    # bicycles
    "2rm": set([30, 31, 32, 33, 34]),        # powered two-wheelers
    "3rm_quad": set([35, 36, 41, 42, 43]),   # three-wheelers / quads
    "vl_vu": set([7, 10]),                   # cars and light utility vehicles
    "pl": set([13, 14, 15, 16, 17]),         # heavy goods vehicles
    "tc": set([37, 38, 40]),                 # public transport
    "edp": set([50, 60]),                    # personal mobility devices
}
```

For the `lieux` table, which can contain several rows per accident, the aggregation keeps the most frequent modality (mode) for `vma`, `nbv`, `catr`, `circ` and `surf`, and the maximum for the binary presence indicators.

### 4. Temporal features and final table

Hour and day of week were transformed into sine/cosine functions in order to model the real periodicity of traffic flows (night/day, week/weekend). A linear encoding would wrongly place 23h and 0h at opposite ends of the scale:

```python
df2["heure_sin"] = np.sin(2 * np.pi * df2["heure"] / 24)
df2["heure_cos"] = np.cos(2 * np.pi * df2["heure"] / 24)
df2.drop(columns="heure", inplace=True)

df2["jour_sin"] = np.sin(2 * np.pi * df2["jour_semaine"] / 7)
df2["jour_cos"] = np.cos(2 * np.pi * df2["jour_semaine"] / 7)
df2.drop(columns="jour_semaine", inplace=True)
```

The five blocks are then merged into the final modelling table:

```python
df2 = (
    df_feat
    .merge(df_agg1, on="num_acc", how="left")   # users
    .merge(df_agg2, on="num_acc", how="left")   # vehicles
    .merge(df_agg3, on="num_acc", how="left")   # places
    .merge(target_acc, on="num_acc", how="left")  # target
)
```

The missing values appearing after the joins were treated according to the nature of the variables. The binary presence variables (`presence_*`) and the count variables (`nb_*`) were imputed to 0, this choice reflecting the absence of a user, a vehicle type or a characteristic when the information is not reported in the source tables. Continuous numerical variables (such as the year or the maximum authorised speed) were imputed by the median, a statistic robust to extreme values, so as not to bias the distribution. Finally, categorical variables were imputed by their most frequent modality, which preserves consistency with the overall structure of the data without introducing artificial categories.

Technical identifiers (`num_acc`, `id_vehicule`, `id_usager`) were removed, being useless for the model.

## III. Predictive modelling and results

### 1. Preprocessing pipeline

Every transformation is encapsulated in a `Pipeline` combined with a `ColumnTransformer`. This guarantees that the exact same operations are applied at training time and at prediction time, which limits the risk of information leakage and makes the whole process reproducible.

One point deserves attention: several BAAC variables are stored as integers but are in fact **codes**, not quantities. They have to be forced to categorical before encoding, otherwise the model would interpret "departmental road = 3" as being three times "motorway = 1":

```python
code_cols = ["lum", "atm", "agg", "int", "col", "catr", "circ", "surf", "nbv", "dep", "saison"]
for c in code_cols:
    if c in X.columns:
        X[c] = X[c].astype("category")

numeric_transformer = Pipeline(steps=[
    ("imputer", SimpleImputer(strategy="median")),
    ("scaler", StandardScaler())
])

categorical_transformer = Pipeline(steps=[
    ("imputer", SimpleImputer(strategy="most_frequent")),
    ("encoder", OneHotEncoder(handle_unknown="ignore"))
])

preprocessor = ColumnTransformer(
    transformers=[
        ("num", numeric_transformer, num_vars),
        ("cat", categorical_transformer, cat_vars)
    ],
    remainder="drop"
)
```

The `handle_unknown="ignore"` option matters here, since a modality present in 2024 but absent from the training years would otherwise break the prediction.

After preprocessing, the feature space grows to roughly **205 columns**: one categorical variable can become 5, 10 or 20 columns depending on the number of modalities present in the training sample.

### 2. Temporal train/test split

The data was split into two sets according to a chronological criterion. Accidents that occurred between 2019 and 2023 were used as the training set, while the 2024 data was kept as the test set:

```python
df_train = df2[df2["annee"] < 2024].copy()
df_test  = df2[df2["annee"] == 2024].copy()
```

This chronological split allows the model to be evaluated on data that is genuinely in the future with respect to what it learned from, which is a more realistic assessment of its generalisation capacity. It also avoids any temporal information leakage and reflects the real conditions of use of the model. The distribution of the target was checked on both sides to make sure the proportions of severe and non-severe accidents remain comparable, a necessary condition for a reliable evaluation in a moderately imbalanced setting.

Given the volume of the dataset, a controlled sub-sample of the training set is used to speed up the hyperparameter search, while preserving the target distribution:

```python
N_SAMPLE = 30000
X_train_small = X_train.sample(n=N_SAMPLE, random_state=42)
y_train_small = y_train.loc[X_train_small.index]
```

### 3. Model comparison

Three approaches were tested through automated preprocessing pipelines, with a `GridSearchCV` scored on **recall** rather than accuracy : the business metric is stated explicitly in the search itself:

```python
grids = {
    "Logistic Regression": GridSearchCV(pipe_logreg, param_logreg, cv=3,
                                        scoring="recall", n_jobs=-1, verbose=1),
    "Random Forest": GridSearchCV(pipe_rf, param_rf, cv=3,
                                  scoring="recall", n_jobs=-1, verbose=1),
    "Gradient Boosting": GridSearchCV(pipe_gb, param_gb, cv=3,
                                      scoring="recall", n_jobs=-1, verbose=1)
}

for name, grid in grids.items():
    grid.fit(X_train_small, y_train_small)
    results[name] = grid
```

Results on the 2024 test set:

| Model | ROC-AUC | Precision (Severe) | Recall (Severe) |
| :---- | :---- | :---- | :---- |
| Logistic Regression | 0.789 | 0.64 | 0.57 |
| Random Forest | 0.776 | 0.72 | 0.35 |
| Gradient Boosting | 0.792 | 0.69 | 0.45 |



In this project, Recall is the most critical metric because it measures the ability of the model to correctly identify every accident that is genuinely severe. A low recall would mean the model classifies as "Light" accidents that are in reality "Severe". For emergency services, this translates into an insufficient dispatch of means while lives are at stake.

Logistic Regression was favoured over Gradient Boosting because it offers a better balance of performance on the target class, showing an initial recall of 0.57 against 0.35 for the Random Forest, despite a very close ROC-AUC of 0.789. This choice is also justified by the interpretability of the model, which makes it possible to explain the predictions to public decision-makers by isolating the impact of critical factors such as the maximum authorised speed or the vulnerability linked to age. By avoiding the opacity of complex models, the coefficients make the causes of severity easier to understand.

On the operational side, Logistic Regression is a light and fast model, ideal for real-time integration as soon as an injury accident is reported by the police forces. It also strengthens the confidence of business users, such as SAMU regulators, by making the criticality criteria explicit, unlike models acting as black boxes.

### 4. Decision threshold adjustment

Since false negatives are the most critical errors in this use case, we did not keep the default 0.5 threshold and instead studied the trade-off between recall and false alarms:

```python
best_est = results["Logistic Regression"].best_estimator_
proba = best_est.predict_proba(X_test)[:, 1]

for t in [0.5, 0.4, 0.3, 0.2]:
    y_pred_t = (proba >= t).astype(int)
    r = recall_score(y_test, y_pred_t)
    cm = confusion_matrix(y_test, y_pred_t)
    print(f"Seuil={t:.1f} | Recall grave={r:.3f} | Matrice={cm.tolist()}")

seuil_final = 0.4
y_pred_final = (proba >= seuil_final).astype(int)
```

By lowering the decision threshold to 0.4, we accept slightly more false alarms in order to guarantee that **68.3% of the severe cases are immediately detected**. It is preferable to dispatch heavy means as a precaution rather than to underestimate a vital emergency. In our case, the model identifies nearly 7 severe accidents out of 10 as soon as the accident is reported, allowing an anticipated triggering of heavy means (SMUR, helicopter).


### 5. Influential severity factors

The analysis of variable importance identifies the maximum authorised speed as the primary lever of road mortality, because speed turns what could have been a light accident into a dramatic event. This danger is intrinsically linked to the structure of the road network, where departmental and national roads prove more prone to accidents than motorways or urban lanes. In parallel, the user profile plays a determining role in the criticality score, since the presence of seniors or of powered two-wheeler drivers drastically increases the probability of severe injury or death due to their physical vulnerability. Finally, the mechanical configuration of the impact confirms that frontal collisions remain the most lethal for occupants, largely surpassing rear impacts in severity.


### 6. Coefficient interpretation

To make the results of the model interpretable, we convert the coefficients into Odds Ratios (OR) using the exponential function. An OR above 1 indicates that the modality increases the odds of severity relative to the reference, while an OR below 1 indicates a protective effect:

```python
coef_logreg_or = coef_logreg.copy()
coef_logreg_or["odds_ratio"] = np.exp(coef_logreg_or["coefficient"])
```

The model reveals major geographic disparities. Department 70 shows a coefficient of 1.83, i.e. an OR of 6.23: all other characteristics being equal, an accident occurring in this department has 6.2 times more chances of being severe than in the reference department. Conversely, department 92 (beta = -2.08, OR = 0.13) reduces these odds by 87%. These gaps often reflect differences in network typology and local traffic speed.

The "outside the public network" context (`catr_5`) shows an OR of 2.20, meaning an accident there is 2.2 times more likely to be severe than in a classic urban area. At the opposite end, motorways (`catr_1`) show an OR of 0.57, reducing the odds of severity by 43%, probably thanks to the separation of traffic flows and the absence of lateral obstacles.

The presence of mud on the road (`surf_6`) multiplies the odds of severity by 2.38. More surprisingly, snowy roads (`surf_5`, OR = 0.44) or roads with grease (`surf_8`, OR = 0.52) are associated with a drop of nearly 50% in the probability of severity. This result suggests an adaptation of user behaviour, who reduce their speed when facing a visible danger.

Finally, the type of collision also influences severity. Rear collisions (`col_2`) and chain collisions (`col_4`) reduce the odds of severity by 44% and 51% respectively compared to frontal collisions, confirming that the latter absorb a far more lethal kinetic energy.

## IV. MLOps: experiment tracking with MLflow

The second notebook industrialises the evaluation step. The point is not to re-train the model, but to make every run traceable, comparable and reusable.

### 1. Standardised local tracking

```python
import mlflow

mlflow.set_tracking_uri("file:../mlruns")
mlflow.set_experiment("BAAC")
```

The tracking URI is forced to a local `mlruns` folder inside the project, so the experiment history lives with the repository rather than in a user-level default directory.

### 2. A complete, traceable run

The whole evaluation is wrapped in a single `mlflow.start_run(...)` block, which logs parameters, metrics, artefacts and the model itself:

```python
with mlflow.start_run(run_name="RF_BAAC_Final"):
    y_pred = grid_rf.predict(X_test)
    y_proba = grid_rf.predict_proba(X_test)[:, 1]

    # --- params + metrics ---
    mlflow.log_params(grid_rf.best_params_)
    mlflow.log_metric("recall_2024", recall_score(y_test, y_pred))
    mlflow.log_metric("precision_2024", precision_score(y_test, y_pred))
    mlflow.log_metric("f1_2024", f1_score(y_test, y_pred))
    mlflow.log_metric("roc_auc_2024", roc_auc_score(y_test, y_proba))

    mlflow.log_param("n_features_input", X_train.shape[1])
    mlflow.log_param("n_train_total", len(X_train))
    mlflow.log_param("n_train_sample", len(X_train_small))
    mlflow.log_param("n_test_2024", len(X_test))
```

Logging the dataset sizes alongside the hyperparameters is deliberate: without `n_train_sample` and `n_test_2024`, two runs with identical hyperparameters but different sampling would be indistinguishable in the MLflow UI.

### 3. Artefacts

The classification report is exported as a `.txt` and the confusion matrix as a `.png`, both written to a temporary directory and then attached to the run:

```python
with tempfile.TemporaryDirectory() as tmp:
    report_path = f"{tmp}/classification_report_2024.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(classification_report(y_test, y_pred))
    mlflow.log_artifact(report_path, artifact_path="reports")

    plt.figure(figsize=(5, 4))
    sns.heatmap(confusion_matrix(y_test, y_pred), annot=True, fmt="d", cmap="Blues")
    plt.title("Matrice de confusion - Test 2024")
    fig_path = f"{tmp}/confusion_matrix_2024.png"
    plt.tight_layout()
    plt.savefig(fig_path, dpi=150)
    plt.close()
    mlflow.log_artifact(fig_path, artifact_path="figures")
```

### 4. Logging the full model

What is saved is not only the classifier but the **complete pipeline** (preprocessing + classifier), together with an inferred signature and an input example. This is what makes the artefact directly reusable: reloading it is enough to score raw data, with no risk of forgetting a transformation step.

```python
best_model = grid_rf.best_estimator_
signature = infer_signature(X_train_small, best_model.predict(X_train_small))

mlflow.sklearn.log_model(
    sk_model=best_model,
    artifact_path="model",
    signature=signature,
    input_example=X_train_small.head(5)
)
```

Metrics logged for the tracked Random Forest run on the 2024 test set:

| Metric | Value |
| :---- | :---- |
| Recall 2024 | 0.471 |
| Precision 2024 | 0.669 |
| F1 2024 | 0.553 |
| ROC-AUC 2024 | 0.781 |


## Conclusion

This project demonstrates the effectiveness of data science in answering very real problems. By binarising severity to isolate accidents involving people killed or hospitalised for more than 24 hours, we provide a criticality score directly useful to emergency services.

The choice of Logistic Regression, with a decision threshold adjusted to 0.4, yields a recall of 68.3%. In a road safety context, recall is the priority metric: it is better to generate a few false alarms — dispatching means for an accident that turns out to be light — than to miss a severe one. This model identifies nearly 7 severe accidents out of 10 from the very first call, making it possible to trigger heavy means (SMUR, helicopter) immediately.

The interpretation of the coefficients underlines that the maximum authorised speed (VMA) and the road typology (departmental roads vs motorways) are the fundamental levers for action. The results suggest that public policies should favour infrastructure separating traffic flows in order to limit frontal impacts, and maintain heightened vigilance on secondary networks where accident severity is higher.

### Limits

* **False negatives vs false alarms:** the improvement in recall comes at the price of a larger volume of false positives, which has to be compatible with a fast triage in an emergency context.
* **Geographic variables:** the departments improve performance but may reduce robustness if the distribution shifts (new year, new areas). They capture context rather than a directly actionable factor.
* The model helps to prioritise, but does not replace field expertise.

