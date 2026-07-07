#!/usr/bin/env python3
"""Stage 4 v2 review for task 129: facebookresearch/flow_matching."""

import json
import sqlite3
from datetime import datetime, timezone

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"

# Opportunities to keep with refined evidence
KEEP = {
    3169: {
        "source_type": "bug",
        "title": "GeodesicProbPath.sample() fails for data with ndim > 1 (regression in 1.0.10)",
        "description": "After upgrading from 1.0.9 to 1.0.10, calling GeodesicProbPath.sample() on high-dimensional inputs (batch, *data_dims) raises RuntimeError in einsum because t shape handling assumes 1D trailing dimensions.",
        "impl_hint": "Inspect GeodesicProbPath.sample() and t broadcasting; generalize einsum/unsqueeze logic to support arbitrary trailing data dimensions while preserving backward compatibility for 1D cases. Add a regression test with shape (batch, D1, D2).",
        "value_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 1,
            "issue_count": 9,
            "has_workaround": False,
            "prod_signal_quote": "RuntimeError: einsum(): the number of subscripts in the equation (1) does not match the number of dimensions (2) for operand 0 and no ellipsis was given",
            "has_prod_signal": True,
            "gap_desc": "Regression bug: GeodesicProbPath.sample() does not support data with ndim > 1 after v1.0.10"
        },
        "difficulty_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "Moderate: requires careful broadcasting/einsum fix in Riemannian path sampling and a regression test; no canonical reference needed.",
            "target_approach_file": "flow_matching/path/geodesic.py or flow_matching/path/riemannian.py"
        },
        "urgency_evidence": {
            "cve_id": None,
            "has_prod_signal": True,
            "has_workaround": False
        },
        "maintainer_evidence": {
            "similar_prs": [],
            "maintainer_responses": [],
            "welcome_labels": []
        }
    },
    3167: {
        "source_type": "feature",
        "title": "Implement Mean Flows for one-step sampling",
        "description": "User request to add Mean Flows (arXiv:2505.13447) as an optional solver/path method for one-step sampling, which could improve inference speed for the PyTorch community.",
        "impl_hint": "Add a MeanFlowPath or MeanFlowSolver class implementing the mean-flow training objective and deterministic one-step sampler; include an example and unit tests.",
        "value_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 1,
            "issue_count": 5,
            "has_workaround": False,
            "prod_signal_quote": "Adding Mean Flows as an available option would be a nice win for the PyTorch community.",
            "has_prod_signal": False,
            "gap_desc": "Missing feature: Mean Flows one-step sampler is not implemented"
        },
        "difficulty_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "High: requires implementing a new training objective and sampler from a recent paper, plus example/docs.",
            "target_approach_file": "flow_matching/solver/ or flow_matching/path/"
        },
        "urgency_evidence": {
            "cve_id": None,
            "has_prod_signal": False,
            "has_workaround": False
        },
        "maintainer_evidence": {
            "similar_prs": [],
            "maintainer_responses": [],
            "welcome_labels": []
        }
    },
    3171: {
        "source_type": "feature",
        "title": "Support cartesian product manifolds",
        "description": "Request to add top-level manifold types representing cartesian products (e.g. sphere x sphere, sphere x tori x euclidean), similar to the prior facebookresearch/riemannian-fm repo.",
        "impl_hint": "Introduce a ProductManifold wrapper that composes existing manifolds and delegates expmap/logmap/geodesic operations component-wise; add tests for mixed topology products.",
        "value_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": ["https://github.com/facebookresearch/riemannian-fm"],
            "issue_reactions": 0,
            "issue_count": 11,
            "has_workaround": False,
            "prod_signal_quote": "The original Riemannian flow matching repo had nice support for product spaces",
            "has_prod_signal": True,
            "gap_desc": "Missing feature: no support for cartesian product manifolds, unlike peer repo facebookresearch/riemannian-fm"
        },
        "difficulty_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "Moderate-High: requires designing a clean product-manifold abstraction compatible with the existing manifold interface and testing across mixed geometries.",
            "target_approach_file": "flow_matching/utils/manifolds.py or new flow_matching/utils/product_manifold.py"
        },
        "urgency_evidence": {
            "cve_id": None,
            "has_prod_signal": True,
            "has_workaround": False
        },
        "maintainer_evidence": {
            "similar_prs": [],
            "maintainer_responses": [],
            "welcome_labels": []
        }
    },
    3173: {
        "source_type": "bug",
        "title": "Image example save_model calls non-existent save_checkpoint",
        "description": "In examples/image/logic/load_and_save.py, save_model() calls model.save_checkpoint when no image example model defines that method; the method only exists on TrainState in examples/text/logic/state.py.",
        "impl_hint": "Fix save_model to use save_on_master when loss_scaler is absent, or import/use a shared TrainState/checkpoint helper; add a smoke test for image example checkpointing.",
        "value_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 0,
            "issue_count": 6,
            "has_workaround": False,
            "prod_signal_quote": "the save_model function uses model.save_checkpoint but I don't think any of the model in the image example has a save_checkpoint method",
            "has_prod_signal": True,
            "gap_desc": "Bug: image training example cannot save checkpoints because save_checkpoint is not implemented on image models"
        },
        "difficulty_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "Low: straightforward example wiring fix; reuse existing save_on_master or shared TrainState logic.",
            "target_approach_file": "examples/image/logic/load_and_save.py"
        },
        "urgency_evidence": {
            "cve_id": None,
            "has_prod_signal": True,
            "has_workaround": False
        },
        "maintainer_evidence": {
            "similar_prs": [],
            "maintainer_responses": [],
            "welcome_labels": []
        }
    },
    3170: {
        "source_type": "feature",
        "title": "Add reflow algorithm to examples",
        "description": "User request to add the reflow algorithm from 'Improving the Training of Rectified Flows' to the examples.",
        "impl_hint": "Implement reflow training loop as a new example script or an option in existing rectified-flow example; include distillation/sampling changes and a README note.",
        "value_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 0,
            "issue_count": 7,
            "has_workaround": False,
            "prod_signal_quote": "This algorithm comes from 'Improving the Training of Rectified Flows'",
            "has_prod_signal": False,
            "gap_desc": "Missing example: reflow algorithm is not included in the examples"
        },
        "difficulty_evidence": {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "Moderate: requires implementing reflow training logic and matching it to library APIs.",
            "target_approach_file": "examples/"
        },
        "urgency_evidence": {
            "cve_id": None,
            "has_prod_signal": False,
            "has_workaround": False
        },
        "maintainer_evidence": {
            "similar_prs": [],
            "maintainer_responses": [],
            "welcome_labels": []
        }
    }
}

# IDs to discard
DISCARD = [3168, 3172, 3174, 3175, 3176]


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    for opp_id, data in KEEP.items():
        cur.execute(
            """
            UPDATE opportunities
            SET status='open',
                source_type=?,
                title=?,
                description=?,
                impl_hint=?,
                value_evidence=?,
                difficulty_evidence=?,
                urgency_evidence=?,
                maintainer_evidence=?,
                value=NULL,
                difficulty=NULL,
                urgency=NULL,
                maintainer_signal=NULL,
                updated_at=?
            WHERE id=?
            """,
            (
                data["source_type"],
                data["title"],
                data["description"],
                data["impl_hint"],
                json.dumps(data["value_evidence"], ensure_ascii=False),
                json.dumps(data["difficulty_evidence"], ensure_ascii=False),
                json.dumps(data["urgency_evidence"], ensure_ascii=False),
                json.dumps(data["maintainer_evidence"], ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
                opp_id,
            ),
        )
        print(f"Updated opportunity {opp_id} -> open ({data['source_type']})")

    for opp_id in DISCARD:
        cur.execute("DELETE FROM opportunities WHERE id=?", (opp_id,))
        print(f"Deleted opportunity {opp_id}")

    # Mark task done
    finished_at = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "UPDATE tasks SET status='done', finished_at=? WHERE id=129",
        (finished_at,),
    )
    print("Marked task 129 as done")

    # Mark project active
    cur.execute(
        "UPDATE projects SET status='active' WHERE id=(SELECT project_id FROM tasks WHERE id=129) AND status='analyzing'"
    )
    print("Marked project active if it was analyzing")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
