#!/usr/bin/env python3
"""Stage 4 v2 batch judgment: yzhao062/pyod (task 1177).

Note: canonical_url is empty for pyod — there is no Java canonical; pyod is a
pure-Python outlier detection library. Per judgment principle 2, opportunity
value must not rely on a non-existent canonical reference.
"""
import sqlite3, json

DB = 'data/pipeline.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

def delete_opp(opp_id, why):
    cur.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
    print(f"DELETE {opp_id}: {why}")

def promote(opp_id, **kw):
    cur.execute("""
        UPDATE opportunities SET
            status='open',
            source_type=?, title=?, description=?, impl_hint=?,
            value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
            value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
        WHERE id=?
    """, (kw['source_type'], kw['title'], kw['description'], kw['impl_hint'],
          json.dumps(kw['value_evidence']), json.dumps(kw['difficulty_evidence']),
          json.dumps(kw['urgency_evidence']), json.dumps(kw['maintainer_evidence']),
          opp_id))
    print(f"PROMOTE {opp_id} -> open ({kw['source_type']}): {kw['title']}")

# Pure usage questions, no contribution surface
delete_opp(5584, "question/discussion, no actionable contribution surface (maintainer: 'Will put on my todo list' but no concrete change requested)")
delete_opp(7760, "maintainer explicitly says no PyOD model gives per-feature scores; push-back, no contribution surface")
delete_opp(7763, "mislabeled 'security' but is a usage clarification about contamination=0; maintainer explains as convenience, not a vulnerability")
delete_opp(7768, "pure usage question about Anogan input shape, no contribution surface")
delete_opp(7769, "maintainer resolves as expected randomness behavior (not a bug), only doc nit at most")

# 5585 — issue:75, add HDBSCAN to PyOD
promote(5585,
    source_type='issue',
    title='[Feat] Add HDBSCAN as another anomaly detection method to PyOD',
    description="Add HDBSCAN (https://github.com/scikit-learn-contrib/hdbscan) as another density-based anomaly detection method in PyOD. Maintainer is open to wrapping it under PyOD's estimator interface; concern was only about external dependency weight, which the user has addressed.",
    impl_hint="Implement a new model class `pyod.models.hdbscan.HDBSCAN` that subclasses `pyod.models.base.BaseDetector`. Internally wrap `hdbscan.HDBSCAN(min_cluster_size=...).fit(X)` and convert cluster membership / outlier scores into PyOD's `decision_scores_` and `labels_` format.",
    value_evidence={
        "canonical_impl_url": "https://github.com/scikit-learn-contrib/hdbscan",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 2,
        "issue_count": 20,
        "has_workaround": False,
        "prod_signal_quote": "could you add HDBscan (https://github.com/scikit-learn-contrib/hdbscan) as another anomaly detection method to PyOD?",
        "has_prod_signal": True,
        "gap_desc": "PyOD lacks HDBSCAN; density-based clustering-based outlier detection is a popular family not covered by existing PyOD algorithms"
    },
    difficulty_evidence={
        "canonical_impl_url": "https://github.com/scikit-learn-contrib/hdbscan",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires wrapping an external library while matching PyOD's BaseDetector contract (decision_scores_, labels_, fit, decision_function); needs tests + example notebook",
        "target_approach_file": "pyod/models/hdbscan.py"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [
            {"number": 692, "title": "Fix DataFrame feature name warnings in sklearn wrapper models (#540)", "merged": True, "url": "https://github.com/yzhao062/pyod/pull/692", "age_days": 97, "maintainer_comment": ""}
        ],
        "maintainer_responses": [
            {"body_quote": "@rjdoubleu Thanks for the interest. I think HDBSCAN has its own library...but I am a little concerned about relying on too many external libs. So feel free to explore and I am open to any sensible ide[a]"},
            {"body_quote": "This makes sense to me. Will be happy if you could adapt/import the framework to be covered under the same umbrella. You are correct--the dependency here should not be an issue :)"}
        ],
        "welcome_labels": ["help wanted"]
    })

# 5592 — issue:314, autoencoder StandardScaler/sigmoid inconsistency
promote(5592,
    source_type='issue',
    title='[Feat] Autoencoder: configurable output activation to match input scaling',
    description="PyOD's autoencoder uses sigmoid (output in [0,1]) by default, but StandardScaler (the common input scaler) produces values outside [0,1]. This mismatch degrades reconstruction. Maintainer agrees: 'Maybe we should change the sigmoid to relu or leakyrelu' and invites a PR.",
    impl_hint="In `pyod/models/auto_encoder.py`, expose an `output_activation` parameter (default `sigmoid` for backward-compat) and document the trade-off in the docstring. Add a small parameter-validation example showing MinMaxScaler+sigmoid vs StandardScaler+relu.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 24,
        "has_workaround": True,
        "prod_signal_quote": "according to the standard autoencoder settings the output layer has the sigmoid activation function whose values are within 0 and 1, but the input data are scaled with StandardScaler whose values can be higher than 1 and smaller than 0. Why do we have this inconsistency?",
        "has_prod_signal": True,
        "gap_desc": "PyOD autoencoder hard-codes sigmoid output while users commonly feed StandardScaler-normalized inputs (range outside [0,1]); mismatch hurts reconstruction"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: trivial parameter plumbing, but must validate it doesn't regress existing benchmarks and update docstring + example notebook",
        "target_approach_file": "pyod/models/auto_encoder.py"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": True},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "autoencoder is more like a type of neural architecture with many design choices. It is not necessary to follow the exact setting. That being said, feel free to modify the file to use MinMaxScalaer or ..."},
            {"body_quote": "I think your concern makes sense. Maybe we should change the sigmoid to relu or leakyrelu. The reason to not use minmax scalaer for input is it is sensitive to outliers in the data. You could initi[ate the PR]"}
        ],
        "welcome_labels": []
    })

# 7764 — issue:88, save/load pyod model
promote(7764,
    source_type='issue',
    title='[Feat] Add first-class save/load API for PyOD models',
    description="PyOD lacks a documented, first-class way to save and reload trained models. Auto-encoder users specifically report being unable to pickle them (Keras Lambda layer issues). Maintainer confirms: 'Agreed that a model save functionality should be added. Marked as a todo task.'",
    impl_hint="Add `save_model(model, path)` and `load_model(path)` helpers in `pyod/utils.py` that handle both classic sklearn-style estimators (joblib) and Keras-backed models (auto_encoder, VAE) by replacing the Lambda layer with a custom serializable layer first.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 19,
        "has_workaround": True,
        "prod_signal_quote": "I've just trained a auto-encoder model, and I wonder how can I save the model so that I don't need to train it again next time I want it.",
        "has_prod_signal": True,
        "gap_desc": "No first-class save/load API in PyOD; users resort to pickle/joblib and hit Keras Lambda layer serialization errors"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires handling both sklearn-style estimators (trivial) and Keras-backed models (need to replace Lambda layer with a custom serializable subclass); cross-version Keras compatibility",
        "target_approach_file": "pyod/utils.py"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": True},
    maintainer_evidence={
        "similar_prs": [
            {"number": 704, "title": "Fix DeepSVDD not training due to disabled backward pass", "merged": True, "url": "https://github.com/yzhao062/pyod/pull/704", "age_days": 37, "maintainer_comment": ""},
            {"number": 674, "title": "fix(lunar): stop sharing scaler state across instances (closes #502)", "merged": True, "url": "https://github.com/yzhao062/pyod/pull/674", "age_days": 112, "maintainer_comment": ""},
            {"number": 61, "title": "SOD implementation", "merged": True, "url": "https://github.com/yzhao062/pyod/pull/61", "age_days": 2728, "maintainer_comment": ""}
        ],
        "maintainer_responses": [
            {"body_quote": "Agreed that a model save functionality should be added. Marked as a todo task. I am not sure whether pickle will work or not (hopefully yes), and I will also do some tests."},
            {"body_quote": "@epicsol-inc sorry for the late response. AE in pyod is written with keras, and saving the model can be tricky. To my understanding, keras models may not be pickable"}
        ],
        "welcome_labels": []
    })

# 7765 — compat:345, FileNotFoundError for bps_prediction.joblib
promote(7765,
    source_type='compatibility',
    title='[Bug] SUOD pickled model fails to load across machines due to absolute path',
    description="A SUOD-trained model pickled with `joblib.dump` on machine A fails to load on machine B with `FileNotFoundError` because `bps_prediction.joblib` is opened from the absolute path baked into the original machine. Maintainer acknowledges the gap: 'we have not considered the use case of saving SUOD.'",
    impl_hint="In `pyod/models/suod.py` (the SUOD internals), store `bps_prediction.joblib` as a sibling filename relative to the pickle path, not an absolute path. Or load it via `pkg_resources`/importlib.resources so the file resolves next to the installed package.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 30,
        "has_workaround": False,
        "prod_signal_quote": "I trained a model on one computer and then pickled it using `joblib.dump`. On another computer, I opened the model using `joblib.load` and got a `FileNotFoundError` because `bps_prediction.joblib` is trying to be opened from the path to the joblib file on the original computer.",
        "has_prod_signal": True,
        "gap_desc": "SUOD pickles bake an absolute path to bps_prediction.joblib, breaking cross-machine model portability"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires locating where SUOD serializes the bps_prediction.joblib path and switching to a package-relative or pickle-relative resolution; needs backward-compat with existing pickles",
        "target_approach_file": "pyod/models/suod.py"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "noted. we have not considered the use case of saving SUOD. This may be a bit involved since bps_prediction.joblib should be part of the suod package. Would you mind sharing a minimal example with a sy[nthetic dataset]"}
        ],
        "welcome_labels": []
    })

# 7767 — issue:328, save VAE model (Lambda layer)
promote(7767,
    source_type='issue',
    title='[Feat] Make VAE model serializable (replace fragile Lambda layer)',
    description="PyOD's VAE uses a Keras `Lambda` layer for the sampling step which cannot be serialized. Users cannot save the trained VAE to disk. Maintainer confirms: 'lambda layer is very fragile. we will have to replace that with a custom layer.'",
    impl_hint="In `pyod/models/vae.py`, define a custom `Sampling` layer subclassing `keras.layers.Layer` that exposes `get_config()` for serialization, replacing the `Lambda(self.sampling, ...)` call.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 18,
        "has_workaround": False,
        "prod_signal_quote": "I have a problem when I want to save the VAE model after the training. This is because this Lambda layer cannot be saved into file. Could you give me any advice to save it?",
        "has_prod_signal": True,
        "gap_desc": "VAE model uses Keras Lambda layer which is not serializable; trained VAE models cannot be saved to disk"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires writing a custom Keras Layer subclass with proper get_config/serialization; cross-Keras-version compatibility checks needed",
        "target_approach_file": "pyod/models/vae.py"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "I just searched around and realize lambda layer is very fragile. we will have to replace that with a custom layer."},
            {"body_quote": "for self-reference: https://github.com/keras-team/keras/issues/6442"}
        ],
        "welcome_labels": []
    })

conn.commit()
conn.close()
print("yzhao062/pyod batch complete")