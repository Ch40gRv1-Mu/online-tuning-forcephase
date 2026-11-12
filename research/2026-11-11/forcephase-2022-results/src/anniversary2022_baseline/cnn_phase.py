"""Train a signed CNF graph convolution network to choose D, Fplus or Fminus."""

import argparse
from collections import deque
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time

import numpy as np
import torch
from torch import nn

from .common import sha, write
from .route_phase_2022 import SOLVER_FLAGS, load_formula
from .score_width_budget_recovery import assess, timed_cost
from .structural_clusters import ACTIONS, BASE, DATA, ROOT, load, read_csv, write_csv


SEED = 20261110
MAX_BYTES = 3_000_000
MAX_CLAUSES = 512
MAX_EDGES = 4096
HIDDEN = 16
ROUNDS = 2
EPOCHS = 24
BATCH = 16
PATIENCE = 6
TRAIN_THREADS = 4


def connected_clause_sample(variables, clauses, widths, rng):
    """Grow bounded clause neighborhoods and retain complete admitted clauses."""
    m = len(widths)
    if m <= MAX_CLAUSES and widths.sum() <= MAX_EDGES:
        return np.arange(m), 1 if m else 0, 0
    offsets = np.r_[0, widths.cumsum()]
    order = np.argsort(variables, kind="stable")
    degree = np.bincount(variables)
    pointers = np.r_[0, degree.cumsum()]
    seeds = rng.permutation(m)
    seed_cursor = seed_count = skipped = pops = 0
    queue = deque()
    seen = np.zeros(m, dtype=bool)
    selected = []
    remaining = MAX_EDGES
    while len(selected) < MAX_CLAUSES and pops < MAX_CLAUSES * 32:
        if not queue:
            while seed_cursor < m and seen[seeds[seed_cursor]]:
                seed_cursor += 1
            if seed_cursor == m:
                break
            queue.append(int(seeds[seed_cursor]))
            seed_cursor += 1
            seed_count += 1
        clause = queue.popleft()
        pops += 1
        if seen[clause]:
            continue
        seen[clause] = True
        width = int(widths[clause])
        if width > remaining:
            skipped += 1
            continue
        selected.append(clause)
        remaining -= width
        if width == 0:
            continue
        positions = rng.choice(width, min(width, 8), replace=False)
        adjacent_variables = np.unique(variables[offsets[clause] + positions])
        for variable in adjacent_variables:
            incident = order[pointers[variable]:pointers[variable + 1]]
            edges = rng.choice(incident, min(len(incident), 8), replace=False)
            queue.extend(int(c) for c in clauses[edges] if not seen[c])
    return np.sort(selected), seed_count, skipped


def encode_formula(raw, sampling="uniform"):
    """Bound the network graph while using full-CNF degrees as node attributes."""
    header = None
    body = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(b"c"):
            continue
        if line.startswith(b"p"):
            fields = line.split()
            if header is not None or len(fields) != 4 or fields[:2] != [b"p", b"cnf"]:
                raise ValueError("invalid DIMACS header")
            header = tuple(map(int, fields[2:]))
        else:
            body.append(line)
    if header is None:
        raise ValueError("missing DIMACS header")
    n, m = header
    tokens = np.fromstring(b" ".join(body).decode("ascii"), dtype=np.int64, sep=" ")
    ends = np.flatnonzero(tokens == 0)
    if n < 0 or m < 0 or len(ends) != m or (len(tokens) and tokens[-1] != 0):
        raise ValueError("incomplete DIMACS input")
    literals = tokens[tokens != 0]
    if len(literals) and (np.abs(literals).max() > n):
        raise ValueError("literal exceeds header")
    widths = np.diff(np.r_[-1, ends]) - 1
    clauses = np.repeat(np.arange(m), widths)
    ids, variables = np.unique(np.abs(literals), return_inverse=True)
    positive = literals > 0
    pos_degree = np.bincount(variables, weights=positive, minlength=len(ids))
    neg_degree = np.bincount(variables, weights=~positive, minlength=len(ids))
    clause_pos = np.bincount(clauses, weights=positive, minlength=m)
    degree = pos_degree + neg_degree
    variable_features = np.column_stack((
        np.log1p(pos_degree) / 12, np.log1p(neg_degree) / 12,
        (pos_degree - neg_degree) / np.maximum(degree, 1),
        neg_degree == 0, pos_degree == 0,
    )).astype(np.float32)
    clause_features = np.column_stack((
        np.log1p(widths) / 12, clause_pos / np.maximum(widths, 1),
        widths == 1, widths == 2,
    )).astype(np.float32)
    global_features = np.array([
        np.log1p(n) / 20, np.log1p(m) / 20,
        np.log1p(len(literals)) / 20, len(ids) / max(n, 1),
    ], dtype=np.float32)
    # The seed only fixes sampling. Variable IDs and clause indices are absent
    # from learned features, and signs remain attached to graph edges.
    rng = np.random.default_rng(SEED)
    seed_count = skipped = 0
    if sampling == "connected":
        chosen, seed_count, skipped = connected_clause_sample(variables, clauses, widths, rng)
    else:
        chosen = np.sort(rng.choice(m, min(m, MAX_CLAUSES), replace=False))
    clause_map = np.full(m, -1, dtype=np.int64)
    clause_map[chosen] = np.arange(len(chosen))
    edges = np.flatnonzero(clause_map[clauses] >= 0)
    if len(edges) > MAX_EDGES and sampling == "uniform":
        edges = np.sort(rng.choice(edges, MAX_EDGES, replace=False))
    assert len(edges) <= MAX_EDGES
    kept_variables, local_variables = np.unique(variables[edges], return_inverse=True)
    v = variable_features[kept_variables]
    c = clause_features[chosen]
    # Empty graphs retain a dummy zero node for well-defined pooling.
    if len(v) == 0:
        v = np.zeros((1, 5), dtype=np.float32)
    if len(c) == 0:
        c = np.zeros((1, 4), dtype=np.float32)
    pooled = np.r_[v.mean(0), v.std(0), c.mean(0), c.std(0), global_features].astype(np.float32)
    return {
        "v": v, "c": c, "ev": local_variables.astype(np.int64),
        "ec": clause_map[clauses[edges]],
        "sign": np.where(positive[edges], 1, -1).astype(np.float32),
        "g": global_features, "pooled": pooled,
        "sampled_seed_count": np.array(seed_count),
        "skipped_clause_count": np.array(skipped),
    }


def merge_equivalent_groups(labels, iso):
    parent = {label: label for label in labels}

    def root(label):
        while parent[label] != label:
            parent[label] = parent[parent[label]]
            label = parent[label]
        return label

    seen = {}
    for label, equivalent in zip(labels, iso):
        if equivalent in seen:
            a, b = sorted((root(label), root(seen[equivalent])))
            parent[b] = a
        seen[equivalent] = label
    return np.array([root(label) for label in labels])


def prepare(args):
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, iso, _ = load()
    broad_path = DATA / "scc_width_fixed_20261110/predictions.csv"
    fine_path = DATA / "scc_root_up_20261110/predictions.csv"
    broad_rows = {row["instance_key"]: row for row in read_csv(broad_path)}
    fine_rows = {row["instance_key"]: row for row in read_csv(fine_path)}
    broad = merge_equivalent_groups([broad_rows[k]["coarse_cluster_group"] for k in keys], iso)
    fine = merge_equivalent_groups([fine_rows[k]["shape_block"] for k in keys], iso)
    with sqlite3.connect(f"file:{BASE}?mode=ro", uri=True) as db:
        sizes = {key: int(size) for key, size in db.execute("select hash,bytes from features")
                 if key in set(keys)}
    assert len(sizes) == len(keys) == 4719
    eligible = np.array([sizes[key] <= MAX_BYTES for key in keys])
    assert eligible.sum() == 2843
    panel = {row["instance_key"]: args.panel / "cnf" / (row["case"] + ".cnf")
             for row in read_csv(args.panel / "association_only.csv")}
    args.out.mkdir(parents=True, exist_ok=False)
    graph_dir = args.work / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)

    def collect(key):
        began, thread = time.monotonic(), time.thread_time()
        path = args.cache / (key + ".cnf.gz")
        if not path.is_file():
            path = panel[key]
        raw = load_formula(path)
        if len(raw) > 3_050_000:
            raise ValueError("bounded CNF read exceeded")
        graph = encode_formula(raw, args.sampling)
        feature_cpu = time.thread_time() - thread
        check = subprocess.check_output([str(args.verifier.resolve())], input=raw, timeout=5).split()
        if check[0].decode() != key:
            raise ValueError("CNF identity mismatch")
        np.savez_compressed(graph_dir / (key + ".npz"), **graph)
        return {"instance_key": key, "status": "ok", "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "feature_CPU_s": feature_cpu, "identity_CPU_s": float(check[4]),
                "variables_kept": len(graph["v"]), "clauses_kept": len(graph["c"]),
                "sampled_seed_count": int(graph["sampled_seed_count"]),
                "skipped_clause_count": int(graph["skipped_clause_count"]),
                "edges_kept": len(graph["ev"]), "wall_s": time.monotonic() - began}

    records = {}
    with ThreadPoolExecutor(max_workers=4) as pool, (args.out / "feature_receipts.jsonl").open("w") as stream:
        for record in pool.map(collect, [key for key, use in zip(keys, eligible) if use]):
            records[record["instance_key"]] = record
            stream.write(json.dumps(record) + "\n")
            if len(records) % 400 == 0:
                stream.flush()
                print(f"Encoded {len(records)}/2843 CNFs", flush=True)
    # Assign entire coarse groups to four balanced folds using counts alone.
    fold_sizes = [0] * 4
    assigned = {}
    for group in sorted(set(broad), key=lambda g: (-int((broad == g).sum()), g)):
        fold = int(np.argmin(fold_sizes))
        assigned[group] = fold
        fold_sizes[fold] += int((broad == group).sum())
    rows = []
    for i, key in enumerate(keys):
        digest = hashlib.sha256(("cnf_gcn_v1:" + fine[i]).encode()).digest()
        rows.append({"instance_key": key, "eligible": bool(eligible[i]), "iso_group": iso[i],
                     "coarse_group": broad[i], "fine_group": fine[i],
                     "coarse_fold": assigned[broad[i]], "fine_fold": int.from_bytes(digest[:4], "big") % 5,
                     "inner_validation": int.from_bytes(digest[4:8], "big") % 5 == 0,
                     "feature_CPU_s": records.get(key, {}).get("feature_CPU_s", 0)})
    write_csv(args.out / "splits.csv", rows)
    bounded_oracle = costs[:, 0].copy()
    bounded_oracle[eligible] = costs[eligible].min(axis=1)
    write(args.out / "preparation.json", {
        "parents": len(keys), "encoded": len(records), "fallback_D": int((~eligible).sum()),
        "sampling": args.sampling,
        "coarse_groups_after_equivalence_merge": len(set(broad)), "coarse_fold_sizes": fold_sizes,
        "all_timeout": int((costs.min(axis=1) == 1200).sum()),
        "free_oracle_gain_pct_within_scope": float(100 * (costs[:, 0] - bounded_oracle).sum() / costs[:, 0].sum()),
        "feature_CPU_s": sum(row["feature_CPU_s"] for row in records.values()),
        "identity_CPU_s": sum(row["identity_CPU_s"] for row in records.values()),
        "collector_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - start,
        "source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in
                          (broad_path, fine_path, DATA / "raw_data_20261110/matrix.csv", BASE)},
        "splits_sha256": sha(args.out / "splits.csv"), "new_solver_calls": 0,
    })
    print("CNF encoding and fixed split assignment complete", flush=True)


def collate(graphs):
    fields = {name: [] for name in ("v", "c", "ev", "ec", "sign", "vg", "cg", "g", "pooled")}
    v_offset = c_offset = 0
    for i, graph in enumerate(graphs):
        for name in ("v", "c", "sign", "pooled", "g"):
            fields[name].append(graph[name])
        fields["ev"].append(graph["ev"] + v_offset)
        fields["ec"].append(graph["ec"] + c_offset)
        fields["vg"].append(np.full(len(graph["v"]), i, dtype=np.int64))
        fields["cg"].append(np.full(len(graph["c"]), i, dtype=np.int64))
        v_offset += len(graph["v"])
        c_offset += len(graph["c"])
    return {name: torch.from_numpy(np.stack(values) if name in ("g", "pooled")
                                   else np.concatenate(values)) for name, values in fields.items()}


def mean_pool(values, index, count):
    sums = values.new_zeros((count, values.shape[1])).index_add(0, index, values)
    degree = torch.bincount(index, minlength=count).clamp_min(1).unsqueeze(1)
    return sums / degree


class GraphCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.variable = nn.Linear(5, HIDDEN)
        self.clause = nn.Linear(4, HIDDEN)
        self.to_clause = nn.Sequential(nn.Linear(3 * HIDDEN, HIDDEN), nn.ReLU(), nn.Linear(HIDDEN, HIDDEN))
        self.to_variable = nn.Sequential(nn.Linear(3 * HIDDEN, HIDDEN), nn.ReLU(), nn.Linear(HIDDEN, HIDDEN))
        self.head = nn.Sequential(nn.Linear(2 * HIDDEN + 4, 32), nn.ReLU(), nn.Linear(32, 3))

    def forward(self, batch):
        v, c = self.variable(batch["v"]).relu(), self.clause(batch["c"]).relu()
        ev, ec, sign = batch["ev"], batch["ec"], batch["sign"].unsqueeze(1)
        for _ in range(ROUNDS):
            messages = v[ev]
            incoming = mean_pool(torch.cat((messages, messages * sign), 1), ec, len(c))
            c = (c + self.to_clause(torch.cat((c, incoming), 1))).relu()
            messages = c[ec]
            incoming = mean_pool(torch.cat((messages, messages * sign), 1), ev, len(v))
            v = (v + self.to_variable(torch.cat((v, incoming), 1))).relu()
        count = len(batch["g"])
        pooled = torch.cat((mean_pool(v, batch["vg"], count),
                            mean_pool(c, batch["cg"], count), batch["g"]), 1)
        return self.head(pooled)


class PooledMLP(nn.Module):
    def __init__(self):
        super().__init__()
        target = sum(parameter.numel() for parameter in GraphCNN().parameters())
        width = min(range(16, 257), key=lambda h: abs((22 + 1) * h + (h + 1) * 32 + 33 * 3 - target))
        self.layers = nn.Sequential(nn.Linear(22, width), nn.ReLU(), nn.Linear(width, 32),
                                    nn.ReLU(), nn.Linear(32, 3))

    def forward(self, batch):
        return self.layers(batch["pooled"])


def build_model(kind):
    return GraphCNN() if kind == "gcn" else PooledMLP()


def training_loss(logits, costs, objective):
    excess = torch.as_tensor((costs - costs[:, :1]) / 1200, dtype=torch.float32)
    if objective == "cost_ce":
        weights = excess.max(1, keepdim=True).values - excess
        return -(weights * logits.log_softmax(1)).sum(1).mean()
    return (logits.softmax(1) * excess).sum(1).mean()


@torch.no_grad()
def probabilities(model, graphs, indices):
    result = []
    for start in range(0, len(indices), 32):
        batch = collate([graphs[i] for i in indices[start:start + 32]])
        result.append(model(batch).softmax(1).numpy())
    return np.concatenate(result) if result else np.empty((0, 3))


def fit_model(kind, graphs, costs, train, validation, h, seed, log_path, objective, deadline=float("inf")):
    torch.set_num_threads(TRAIN_THREADS)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    model = build_model(kind)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.003, weight_decay=.0001)
    best_score, best_epoch, best_state = float("inf"), 0, None
    train_ids, val_ids = np.flatnonzero(train), np.flatnonzero(validation)
    if len(train_ids) < 50 or len(val_ids) < 20:
        raise ValueError("insufficient complete training or validation group")
    history = []
    began, cpu = time.monotonic(), time.process_time()
    for epoch in range(1, EPOCHS + 1):
        model.train()
        order = rng.permutation(train_ids)
        losses = []
        for start in range(0, len(order), BATCH):
            if time.monotonic() - began > 480 or time.monotonic() > deadline:
                raise TimeoutError("model fold or whole-stage wall budget exhausted")
            ids = order[start:start + BATCH]
            batch = collate([graphs[i] for i in ids])
            # This loss weights mistakes by their actual archived PAR2 penalty.
            loss = training_loss(model(batch), costs[ids], objective)
            if not torch.isfinite(loss):
                raise ValueError("nonfinite training loss")
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        pred = probabilities(model, graphs, val_ids).argmax(1)
        score = float(timed_cost(costs[val_ids, pred], h[val_ids] + .01, 600).mean())
        if score < best_score - 1e-8:
            best_score, best_epoch, best_state = score, epoch, copy.deepcopy(model.state_dict())
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)),
                        "validation_PAR2": score, "best_epoch": best_epoch})
        write(log_path, {"kind": kind, "train": len(train_ids), "validation": len(val_ids),
                         "history": history, "status": "training"})
        if epoch - best_epoch >= PATIENCE:
            break
    model.load_state_dict(best_state)
    model.eval()
    receipt = {"kind": kind, "objective": objective, "train": len(train_ids), "validation": len(val_ids),
               "epochs_run": len(history), "best_epoch": best_epoch, "validation_PAR2": best_score,
               "parameters": sum(parameter.numel() for parameter in model.parameters()),
               "training_CPU_s": time.process_time() - cpu, "wall_s": time.monotonic() - began,
               "history": history, "status": "complete"}
    write(log_path, receipt)
    return model, receipt


@torch.no_grad()
def measured_predictions(model, graphs, indices):
    torch.set_num_threads(1)
    if len(indices):
        model(collate([graphs[indices[0]]]))
    probabilities_out, overhead = [], []
    for i in indices:
        cpu = time.process_time()
        p = model(collate([graphs[i]])).softmax(1).numpy()[0]
        overhead.append(time.process_time() - cpu)
        probabilities_out.append(p)
    return np.asarray(probabilities_out), np.asarray(overhead)


def train(args):
    start, cpu = time.monotonic(), time.process_time()
    keys, _, costs, _, _, _ = load()
    dataset = args.data or args.out
    sampling = json.loads((dataset / "preparation.json").read_text()).get("sampling", "uniform")
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out / "summary.json").exists():
        raise ValueError("training already has a receipt; preserve it and use a new run identity")
    if dataset.resolve() != args.out.resolve():
        (args.out / "splits.csv").write_bytes((dataset / "splits.csv").read_bytes())
    # Check the graph's essential permutation semantics at the normal entry.
    torch.set_num_threads(1)
    torch.manual_seed(SEED)
    check_model = GraphCNN().eval()
    left = encode_formula(b"p cnf 4 3\n1 -2 0\n2 3 0\n-1 -3 4 0\n", sampling)
    right = encode_formula(b"p cnf 4 3\n2 -4 -3 0\n1 4 0\n-1 3 0\n", sampling)
    with torch.no_grad():
        assert torch.allclose(check_model(collate([left])), check_model(collate([right])), atol=1e-6)
    rows = read_csv(args.out / "splits.csv")
    assert [row["instance_key"] for row in rows] == keys
    eligible = np.array([row["eligible"] == "True" for row in rows])
    h = np.array([float(row["feature_CPU_s"]) for row in rows])
    graphs = {}
    for i in np.flatnonzero(eligible):
        with np.load(args.work / "graphs" / (keys[i] + ".npz")) as archive:
            graphs[i] = {name: archive[name] for name in archive.files}
    modes = {"coarse": (4, "coarse_fold"), "fine": (5, "fine_fold")}
    inner = np.array([row["inner_validation"] == "True" for row in rows])
    coarse = np.array([row["coarse_group"] for row in rows])
    fine = np.array([row["fine_group"] for row in rows])
    iso = np.array([row["iso_group"] for row in rows])
    columns = [{"instance_key": key, "eligible": bool(eligible[i]), "D_PAR2": costs[i, 0],
                "feature_CPU_s": h[i], "coarse_group": coarse[i], "fine_group": fine[i]}
               for i, key in enumerate(keys)]
    summaries, receipts = {}, []
    for mode, (fold_count, field) in modes.items():
        folds = np.array([int(row[field]) for row in rows])
        for kind in ("gcn", "pooled_mlp"):
            name = mode + "_" + kind
            actions = np.zeros(len(keys), dtype=int)
            inference_h = np.zeros(len(keys))
            for fold in range(fold_count):
                tag = f"{name}_{fold}"
                test = folds == fold
                validation = ~test & inner & eligible
                training = ~test & ~inner & eligible
                assert not (set(iso[test]) & set(iso[training | validation]))
                assert not (set(fine[training]) & set(fine[validation]))
                print(f"Training {tag}, train={training.sum()}, val={validation.sum()}, test={test.sum()}", flush=True)
                model, receipt = fit_model(kind, graphs, costs, training, validation, h,
                                           SEED + fold, args.out / (tag + ".json"), args.objective,
                                           start + args.wall_limit)
                receipt.update(mode=mode, fold=fold)
                receipts.append(receipt)
                ids = np.flatnonzero(test & eligible)
                p, inference = measured_predictions(model, graphs, ids)
                actions[ids], inference_h[ids] = p.argmax(1), inference
                for index, probs in zip(ids, p):
                    for action, value in zip(ACTIONS, probs):
                        columns[index][name + "_p_" + action] = float(value)
                torch.save({"kind": kind, "state_dict": model.state_dict(), "format": "cnf_gcn_v1",
                            "seed": SEED + fold, "scope_bytes": MAX_BYTES,
                            "sampling": sampling,
                            "objective": args.objective}, args.out / (tag + ".pt"))
                print(f"Completed {tag}, best epoch={receipt['best_epoch']}, CPU={receipt['training_CPU_s']:.1f}s", flush=True)
            paid = timed_cost(costs[np.arange(len(keys)), actions], h + inference_h, 600)
            blocks = coarse if mode == "coarse" else fine
            result = assess(costs[:, 0], paid, blocks, 600)
            result["actions"] = {action: int((actions == i).sum()) for i, action in enumerate(ACTIONS)}
            result["inference_CPU_s"] = float(inference_h.sum())
            summaries[name] = result
            for i, row in enumerate(columns):
                row[name + "_action"] = ACTIONS[actions[i]]
                row[name + "_PAR2"] = float(paid[i])
                row[name + "_inference_CPU_s"] = float(inference_h[i])
            print(f"SCORED {name}: {json.dumps(result)}", flush=True)
            # Pad unavailable probability columns consistently for CSV output.
            for row in columns:
                for action in ACTIONS:
                    row.setdefault(name + "_p_" + action, "")
            write_csv(args.out / "predictions.csv", columns)
            write(args.out / "summary.json", {"status": "running", "scores": summaries,
                                               "fits": receipts, "new_solver_calls": 0})
    # Export a usable model trained on all admitted development CNFs. Its fit
    # has no separate score; the reported scores above use held-out predictions.
    epochs = max(1, int(np.median([r["best_epoch"] for r in receipts if r["kind"] == "gcn"])))
    torch.set_num_threads(TRAIN_THREADS)
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    final_model = GraphCNN()
    optimizer = torch.optim.AdamW(final_model.parameters(), lr=.003, weight_decay=.0001)
    ids = np.flatnonzero(eligible)
    final_cpu = time.process_time()
    for _ in range(epochs):
        order = rng.permutation(ids)
        for step in range(0, len(order), BATCH):
            if time.monotonic() - start > args.wall_limit:
                raise TimeoutError("whole-stage wall budget exhausted")
            batch_ids = order[step:step + BATCH]
            batch = collate([graphs[i] for i in batch_ids])
            loss = training_loss(final_model(batch), costs[batch_ids], args.objective)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(final_model.parameters(), 5)
            optimizer.step()
    torch.save({"kind": "gcn", "state_dict": final_model.state_dict(), "format": "cnf_gcn_v1",
                "seed": SEED, "scope_bytes": MAX_BYTES, "epochs": epochs,
                "sampling": sampling,
                "objective": args.objective}, args.out / "final_gcn.pt")
    write(args.out / "summary.json", {
        "status": "complete", "parents": len(keys), "encoded": len(graphs), "fallback_D": int((~eligible).sum()),
        "objective": args.objective, "encoding_receipt_sha256": sha(dataset / "preparation.json"),
        "sampling": sampling,
        "scores": summaries, "fits": receipts, "final_model_epochs": epochs,
        "final_model_training_CPU_s": time.process_time() - final_cpu,
        "feature_CPU_s": float(h.sum()), "training_and_analysis_CPU_s": time.process_time() - cpu,
        "training_and_analysis_wall_s": time.monotonic() - start, "torch_version": torch.__version__,
        "device": "cpu", "training_threads": TRAIN_THREADS, "new_solver_calls": 0,
        "small_graph_variable_clause_literal_permutation_check": "passed",
        "independent_test": False, "source_sha256": sha(Path(__file__)),
        "splits_sha256": sha(args.out / "splits.csv"), "final_model_sha256": sha(args.out / "final_gcn.pt"),
    })


def predict(args):
    began = time.process_time()
    torch.set_num_threads(1)
    raw = load_formula(args.cnf)
    if len(raw) > MAX_BYTES:
        result = {"action": "D", "status": "resource_fallback", "probabilities": None}
    else:
        checkpoint = torch.load(args.model, map_location="cpu", weights_only=True)
        if checkpoint["format"] != "cnf_gcn_v1":
            raise ValueError("unsupported network format")
        model = build_model(checkpoint["kind"])
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        with torch.no_grad():
            p = model(collate([encode_formula(raw, checkpoint.get("sampling", "uniform"))])).softmax(1).numpy()[0]
        result = {"action": ACTIONS[int(p.argmax())], "status": "ok",
                  "probabilities": dict(zip(ACTIONS, map(float, p)))}
    result["solver_flags"] = SOLVER_FLAGS[result["action"]]
    result["CPU_s_after_import"] = time.process_time() - began
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "train"):
        sub = commands.add_parser(command)
        sub.add_argument("--out", type=Path, required=True)
        sub.add_argument("--work", type=Path, required=True)
        if command == "prepare":
            sub.add_argument("--sampling", choices=("uniform", "connected"), default="uniform")
            sub.add_argument("--cache", type=Path, required=True)
            sub.add_argument("--panel", type=Path, required=True)
            sub.add_argument("--verifier", type=Path, required=True)
        else:
            sub.add_argument("--data", type=Path)
            sub.add_argument("--objective", choices=("expected", "cost_ce"), default="expected")
            sub.add_argument("--wall-limit", type=float, default=3600)
    sub = commands.add_parser("predict")
    sub.add_argument("cnf", type=Path)
    sub.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    {"prepare": prepare, "train": train, "predict": predict}[args.command](args)


if __name__ == "__main__":
    main()
