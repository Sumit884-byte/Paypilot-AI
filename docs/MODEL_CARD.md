# Model card — payscore-lgbm-baseline (0.1.0-synthetic-seed42)

**Intended use:** integration/demo of an AI credit-scoring component. **Not** for real lending decisions.

* **Model:** LightGBM binary classifier (`payscore_lgbm.txt`), 21 features (`models/model_metadata.json`), early stopping on validation AUC (best iteration 178). Missing values passed natively as NaN.
* **Training data:** 30,000 rows from `payscore.synthetic` (seed 42, ~8% default rate). Labels are produced by an invented risk formula plus noise, so the model largely re-learns that formula. Dataset SHA-256 is recorded in the metadata.
* **Split:** stratified 70/15/15 train/valid/test, `random_state=42`, done before any fitting; target never enters the features (tested).
* **Metrics (synthetic test split, n=4500):** ROC-AUC 0.855, PR-AUC 0.381, KS 0.580, log-loss 0.203, Brier 0.058.
  Logistic-regression baseline on the same split: ROC-AUC 0.839. Train AUC 0.930 vs valid 0.845 shows some overfitting.
  **The 0.855 test AUC (and every number here) comes from synthetic data. These are pipeline checks only: they are not evidence of real-world credit-risk accuracy and not Home Credit or PayPal results.**
* **Score mapping:** PD -> 300-850 via standard odds scaling (see README); bands at 720 / 650 / 560.
* **Fallback:** if no artifact is present, a deterministic formula is served and labelled `development_fallback`.
* **Known gaps:** no calibration on real outcomes; no fairness or subgroup analysis (age and employment type are model inputs and need review before any real use); no explanations/reason codes; no drift monitoring; PayPal-to-schema mapping unverified; the Home Credit loader maps only 6 of the 16 model inputs (plus the ID; `business_age_months` is an employment-length proxy), leaves the other 10 empty, uses unconverted currency, and has only been tested on a mock CSV.
* **Reproducibility (checked):** retraining with defaults (seed 42, `num_threads=1`) to a temporary directory gave a model file byte-identical to the committed one in repeated runs and under two library sets (lightgbm 4.7.0; scikit-learn 1.8.0/1.9.1, pandas 3.0.2/3.1.0, numpy 2.4.4/2.5.4), on Linux x86_64 / Python 3.12.3. The metadata JSON differs only in `trained_at_utc`. Not tested on other OS/Python/LightGBM versions.
