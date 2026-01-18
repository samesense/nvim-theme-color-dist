#!/usr/local/bin/python
import json
import math
from pathlib import Path

import click
import numpy as np
import pandas as pd
from PIL import Image
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text
from skimage.color import lab2rgb, rgb2lab

# ------------------------------------------------------------
# Role ordering & display order
# ------------------------------------------------------------

ROLE_ORDER = [
    "background",
    "surface",
    "overlay",
    "text",
    "accent_red",
    "accent_warm",
    "accent_cool",
    "accent_bridge",
]


def add_ranks(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["L_rank"] = df.groupby("role")["L"].rank(pct=True, method="average")
    df["chroma_rank"] = df.groupby("role")["chroma"].rank(pct=True, method="average")

    # New: ranks for foreground usability vs background anchor
    # (higher = more separated, typically more readable as fg)
    if "deltaE_bg" in df.columns:
        df["deltaE_bg_rank"] = df.groupby("role")["deltaE_bg"].rank(
            pct=True, method="average"
        )
    else:
        df["deltaE_bg_rank"] = np.nan

    if "abs_deltaL_bg" in df.columns:
        df["abs_deltaL_bg_rank"] = df.groupby("role")["abs_deltaL_bg"].rank(
            pct=True, method="average"
        )
    else:
        df["abs_deltaL_bg_rank"] = np.nan

    return df


# ------------------------------------------------------------
# Color helpers
# ------------------------------------------------------------


def rgb_to_hex(rgb):
    r, g, b = map(int, rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def lab_to_chroma(a, b):
    return math.sqrt(a * a + b * b)


def lab_to_hue(a, b):
    return math.degrees(math.atan2(b, a)) % 360.0


def circular_distance(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def deltaE76(lab1: np.ndarray, lab2: np.ndarray) -> float:
    d = lab1 - lab2
    return float(np.sqrt(np.dot(d, d)))


# ------------------------------------------------------------
# Lab/LCh helpers
# ------------------------------------------------------------


def lab_to_lch(L, a, b):
    C = math.sqrt(a * a + b * b)
    h = math.degrees(math.atan2(b, a)) % 360.0 if C > 1e-9 else 0.0
    return float(L), float(C), float(h)


def lch_to_lab(L, C, h):
    hr = math.radians(h)
    a = C * math.cos(hr)
    b = C * math.sin(hr)
    return float(L), float(a), float(b)


def lab_to_rgb_tuple(L, a, b):
    lab = np.array([[[L, a, b]]], dtype=float)
    rgb = lab2rgb(lab)[0, 0, :]
    rgb = np.clip(rgb, 0.0, 1.0)
    r, g, bb = (rgb * 255.0 + 0.5).astype(int)
    return int(r), int(g), int(bb)


# ------------------------------------------------------------
# Dark-hue estimation
# ------------------------------------------------------------


def circular_mean_deg_weighted(deg: np.ndarray, w: np.ndarray) -> float:
    rad = np.deg2rad(deg)
    s = np.sum(np.sin(rad) * w)
    c = np.sum(np.cos(rad) * w)
    if abs(s) < 1e-9 and abs(c) < 1e-9:
        return 0.0
    return float(np.rad2deg(np.arctan2(s, c)) % 360.0)


def dominant_dark_hue(df: pd.DataFrame) -> tuple[float | None, float]:
    dark = df[(df["L"] <= df["L"].quantile(0.4)) & (df["chroma"] >= 5.0)].copy()
    if dark.empty:
        return None, 0.0

    bins = np.linspace(0, 360, 25)
    weights = dark["frequency"].to_numpy() * (dark["chroma"].to_numpy() + 1.0)
    hist, edges = np.histogram(dark["hue"].to_numpy(), bins=bins, weights=weights)
    if hist.sum() <= 0:
        return None, 0.0

    idx = int(hist.argmax())
    center = (edges[idx] + edges[idx + 1]) / 2.0
    confidence = float(hist[idx] / hist.sum())
    return float(center), confidence


def dominant_hue_band(
    df: pd.DataFrame,
    *,
    mask: pd.Series,
    bins: int = 24,
    weight_chroma: bool = True,
) -> tuple[float | None, float]:
    sub = df[mask].copy()
    if sub.empty:
        return None, 0.0

    weights = sub["frequency"].to_numpy()
    if weight_chroma:
        weights = weights * (sub["chroma"].to_numpy() + 1.0)

    edges = np.linspace(0, 360, bins + 1)
    hist, edges = np.histogram(sub["hue"].to_numpy(), bins=edges, weights=weights)
    if hist.sum() <= 0:
        return None, 0.0

    idx = int(hist.argmax())
    center = (edges[idx] + edges[idx + 1]) / 2.0
    confidence = float(hist[idx] / hist.sum())
    return float(center), confidence


def kmeans_dark_cluster_hue(
    df: pd.DataFrame, *, k: int = 3, iters: int = 12
) -> tuple[float | None, float]:
    dark = df[(df["L"] <= df["L"].quantile(0.4)) & (df["chroma"] >= 5.0)].copy()
    if len(dark) < k:
        return None, 0.0

    L = dark["L"].to_numpy()
    C = dark["chroma"].to_numpy()
    h = np.deg2rad(dark["hue"].to_numpy())
    x = np.stack([L, C, np.cos(h), np.sin(h)], axis=1)
    w = dark["frequency"].to_numpy()
    w = w / w.sum()

    # Initialize centers by weighted sampling
    idx = np.random.choice(len(x), size=k, replace=False, p=w)
    centers = x[idx].copy()

    for _ in range(iters):
        dists = np.sum((x[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels = np.argmin(dists, axis=1)
        for j in range(k):
            mask = labels == j
            if not np.any(mask):
                continue
            wj = w[mask]
            centers[j] = np.sum(x[mask] * wj[:, None], axis=0) / wj.sum()

    # Pick cluster with strongest "useful dark hue" signal
    best_hue = None
    best_score = 0.0
    for j in range(k):
        mask = labels == j
        if not np.any(mask):
            continue
        wj = w[mask]
        weight = float(wj.sum())
        mean_c = float(np.average(C[mask], weights=wj))
        score = weight * mean_c
        if score > best_score:
            best_score = score
            cx, sy = centers[j][2], centers[j][3]
            hue = float(np.rad2deg(np.arctan2(sy, cx)) % 360.0)
            best_hue = hue

    return best_hue, float(best_score)

# ------------------------------------------------------------
# Image sampling
# ------------------------------------------------------------


def load_image_colors(path: Path, max_pixels: int | None):
    img = Image.open(path).convert("RGB")
    rgb = np.asarray(img).reshape(-1, 3)

    if max_pixels and len(rgb) > max_pixels:
        idx = np.random.choice(len(rgb), max_pixels, replace=False)
        rgb = rgb[idx]

    return rgb


# ------------------------------------------------------------
# Palette inference
# ------------------------------------------------------------


def infer_palette(photo_stats, palette_profiles):
    # Hard polarity gate
    if photo_stats["L_median"] > 50:
        candidates = ["latte"]
    else:
        candidates = [p for p in palette_profiles if p != "latte"]

    best = None
    best_score = float("inf")

    for palette in candidates:
        prof = palette_profiles[palette]

        score = (
            abs(photo_stats["L_median"] - prof["L_median"])
            + 0.5 * abs(photo_stats["L_range"] - prof["L_range"])
            + 0.5 * abs(photo_stats["chroma_median"] - prof["chroma_median"])
            + 0.2 * abs(photo_stats["hue_entropy"] - prof["hue_entropy"])
        )

        if score < best_score:
            best_score = score
            best = palette

    return best


def palette_fit_score(df: pd.DataFrame, constraints_all: dict) -> dict[str, float]:
    scores = {}
    palettes = constraints_all["constraints"]["chroma"].keys()
    for palette in palettes:
        constraints = {
            "chroma": constraints_all["constraints"]["chroma"][palette],
            "hue": constraints_all["constraints"]["hue"][palette],
            "deltaL": constraints_all["constraints"]["deltaL"][palette],
            "lightness": constraints_all["constraints"].get("lightness", {}).get(
                palette, {}
            ),
        }

        role_counts = {r: 0 for r in ROLE_ORDER}
        role_L = {r: [] for r in ROLE_ORDER}
        for _, r in df.iterrows():
            roles = eligible_roles(r, constraints)
            for role in roles:
                role_counts[role] += 1
                role_L[role].append(float(r.L))

        weights = {
            "background": 3.0,
            "surface": 3.0,
            "overlay": 3.0,
            "text": 3.0,
            "accent_red": 1.0,
            "accent_warm": 1.0,
            "accent_cool": 1.0,
            "accent_bridge": 1.0,
        }
        coverage = sum(
            weights[r] * math.log1p(role_counts[r]) for r in ROLE_ORDER
        )

        missing_structural = any(
            role_counts[r] == 0 for r in ["background", "surface", "overlay", "text"]
        )
        if missing_structural:
            coverage -= 25.0

        polarity = constraints_all.get("polarity", {}).get(palette, "dark")
        is_dark = polarity != "light"
        min_bt = constraints["deltaL"]["background→text"]["q25"]
        delta_possible = None
        if is_dark:
            if role_L["background"] and role_L["text"]:
                delta_possible = max(role_L["text"]) - min(role_L["background"])
        else:
            if role_L["background"] and role_L["text"]:
                delta_possible = max(role_L["background"]) - min(role_L["text"])

        if delta_possible is None or delta_possible < min_bt:
            coverage -= 15.0

        scores[palette] = float(coverage)

    return scores


# ------------------------------------------------------------
# Role eligibility + scoring
# ------------------------------------------------------------


def eligible_roles(row, constraints):
    roles = []

    chroma = row.chroma
    hue = row.hue
    L = row.L

    # Core UI roles (lightness-driven via chroma constraints only)
    for role in ["background", "surface", "overlay", "text"]:
        if role not in constraints["chroma"]:
            continue
        c = constraints["chroma"][role]
        Lc = constraints.get("lightness", {}).get(role)
        if Lc is None:
            if c["q25"] <= chroma <= c["q75"]:
                roles.append(role)
        else:
            if c["q25"] <= chroma <= c["q75"] and Lc["q25"] <= L <= Lc["q75"]:
                roles.append(role)

    # Accent roles (chroma + hue)
    for role in ["accent_red", "accent_warm", "accent_cool", "accent_bridge"]:
        if role not in constraints["hue"]:
            continue

        c = constraints["chroma"][role]
        h = constraints["hue"][role]
        Lc = constraints.get("lightness", {}).get(role)

        if chroma < c["q25"]:
            continue
        if Lc is not None and not (Lc["q10"] <= L <= Lc["q90"]):
            continue

        if circular_distance(hue, h["center"]) <= h["width"] / 2:
            roles.append(role)

    return roles


def score_color(row, role, constraints):
    score = row.frequency * 5.0

    if role in constraints["chroma"]:
        c = constraints["chroma"][role]
        score -= abs(row.chroma - ((c["q25"] + c["q75"]) / 2))

    if role in constraints.get("lightness", {}):
        Lc = constraints["lightness"][role]
        score -= abs(row.L - Lc["median"]) * 0.5

    if role in constraints["hue"]:
        h = constraints["hue"][role]
        score -= circular_distance(row.hue, h["center"]) * 0.1

    return score


def pick_anchor(pool: pd.DataFrame, role: str) -> pd.Series | None:
    sub = pool[pool.role == role].sort_values("score", ascending=False)
    if sub.empty:
        return None
    return sub.iloc[0]


# ------------------------------------------------------------
# Rich display
# ------------------------------------------------------------


def render_role_pool(df):
    console = Console()
    table = Table(show_header=True, header_style="bold")

    table.add_column("Role", style="cyan", no_wrap=True)
    table.add_column("Colors")

    for role in ROLE_ORDER:
        sub = df[df.role == role].sort_values("score", ascending=False)
        if sub.empty:
            continue

        strip = Text()
        for _, r in sub.iterrows():
            w = min(30, max(1, int(r.frequency * 300)))
            strip.append(" " * w, style=Style(bgcolor=rgb_to_hex((r.R, r.G, r.B))))

        table.add_row(f"{role} ({len(sub)})", strip)

    console.print(table)


# ------------------------------------------------------------
# Rich table export
# ------------------------------------------------------------


def _build_pool_table(pool: pd.DataFrame, *, max_per_role: int) -> Table:
    table = Table(title="extracted_colors")
    table.add_column("Role", style="cyan", no_wrap=True)
    table.add_column("Hex", no_wrap=True)
    table.add_column(" ")
    table.add_column("L*", justify="right")
    table.add_column("C*", justify="right")
    table.add_column("Hue", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Freq", justify="right")
    table.add_column("Src", justify="center")
    table.add_column("dE_rank", justify="right")
    table.add_column("|dL|_rank", justify="right")

    def fmt_rank(x):
        if x is None:
            return ""
        try:
            if np.isnan(x):
                return ""
        except Exception:
            pass
        return f"{float(x):.2f}"

    for role in ROLE_ORDER:
        sub = pool[pool.role == role].copy()
        if sub.empty:
            continue
        sub = sub.sort_values(["score", "frequency"], ascending=[False, False]).head(
            max_per_role
        )
        first = True
        for _, r in sub.iterrows():
            h = rgb_to_hex((r.R, r.G, r.B))
            table.add_row(
                role if first else "",
                h,
                Text("   ", style=Style(bgcolor=h)),
                f"{float(r.L):.1f}",
                f"{float(r.chroma):.1f}",
                f"{float(r.hue):.0f}°",
                f"{float(r.score):.2f}",
                f"{float(r.frequency):.3f}",
                "nudge" if bool(r.get("derived", False)) else "orig",
                fmt_rank(r.get("deltaE_bg_rank")),
                fmt_rank(r.get("abs_deltaL_bg_rank")),
            )
            first = False

    return table


def save_pool_table_image(pool: pd.DataFrame, out_path: Path, *, max_per_role: int):
    table = _build_pool_table(pool, max_per_role=max_per_role)
    console = Console(record=True, width=110, force_terminal=True)
    console.print(table)
    svg_content = console.export_svg(title="extracted_colors")

    suffix = out_path.suffix.lower()
    if suffix == ".svg":
        out_path.write_text(svg_content)
    elif suffix == ".png":
        try:
            import cairosvg
        except ImportError:
            raise click.ClickException(
                "PNG export requires cairosvg: pip install cairosvg"
            )
        cairosvg.svg2png(bytestring=svg_content.encode(), write_to=str(out_path))
    else:
        raise click.ClickException(
            f"Unsupported image format: {suffix} (use .svg or .png)"
        )


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------


@click.command()
@click.argument("image_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--constraints-json",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option(
    "--palette",
    type=click.Choice(
        ["auto", "latte", "frappe", "macchiato", "mocha"], case_sensitive=False
    ),
    default="auto",
    show_default=True,
)
@click.option("--max-pixels", default=100_000, show_default=True)
@click.option("--quant", default=8, show_default=True)
@click.option(
    "--out-csv",
    default="color_pool.csv",
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--out-image",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Save extracted color pool table as image (.svg or .png).",
)
@click.option(
    "--max-per-role",
    default=12,
    show_default=True,
    type=int,
    help="Max rows per role in output table image.",
)
@click.option(
    "--cool-min-deltae",
    default=25.0,
    show_default=True,
    type=float,
    help="Minimum Lab deltaE from background for accent_cool (foreground safety).",
)
@click.option(
    "--cool-min-abs-deltal",
    default=12.0,
    show_default=True,
    type=float,
    help="Minimum absolute deltaL from background for accent_cool (foreground safety).",
)
@click.option(
    "--cool-soft-min-deltal",
    default=18.0,
    show_default=True,
    type=float,
    help="Soft penalty threshold: accent_cool below bg_L + this gets penalized.",
)
@click.option(
    "--min-role-candidates",
    default=10,
    show_default=True,
    type=int,
    help="Minimum candidate colors per role (nudges added if needed).",
)
@click.option(
    "--nudge-samples",
    default=300,
    show_default=True,
    type=int,
    help="Number of source colors to sample when nudging missing roles.",
)
def extract_color_pool(
    image_path,
    constraints_json,
    palette,
    max_pixels,
    quant,
    out_csv,
    out_image,
    max_per_role,
    cool_min_deltae,
    cool_min_abs_deltal,
    cool_soft_min_deltal,
    min_role_candidates,
    nudge_samples,
):
    """
    Build a role-aware color pool from a photo using learned palette constraints.
    """

    constraints_all = json.loads(constraints_json.read_text())
    palette_profiles = constraints_all["profiles"]

    # --------------------------------------------------------
    # Sample image
    # --------------------------------------------------------

    rgb = load_image_colors(image_path, max_pixels)
    rgb = (rgb // quant) * quant
    rgb = rgb.astype(np.uint8)

    uniq, counts = np.unique(rgb, axis=0, return_counts=True)
    freq = counts / counts.sum()

    lab = rgb2lab(uniq[np.newaxis, :, :] / 255.0)[0]

    df = pd.DataFrame(
        {
            "R": uniq[:, 0],
            "G": uniq[:, 1],
            "B": uniq[:, 2],
            "L": lab[:, 0],
            "a": lab[:, 1],
            "b": lab[:, 2],
            "frequency": freq,
        }
    )

    df["chroma"] = np.sqrt(df.a**2 + df.b**2)
    df["hue"] = np.degrees(np.arctan2(df.b, df.a)) % 360.0

    # --------------------------------------------------------
    # Photo stats → palette choice
    # --------------------------------------------------------

    photo_stats = {
        "L_median": df.L.median(),
        "L_range": df.L.quantile(0.9) - df.L.quantile(0.1),
        "chroma_median": df.chroma.median(),
        "hue_entropy": np.histogram(df.hue, bins=12, density=True)[0].var(),
    }

    fit_scores = None
    if palette == "auto":
        fit_scores = palette_fit_score(df, constraints_all)
        palette = max(fit_scores, key=fit_scores.get)

    console = Console()
    if fit_scores is None:
        console.print(f"\n🎨 Selected palette constraints: [bold]{palette}[/bold]\n")
    else:
        top = sorted(fit_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        fit_msg = ", ".join([f"{p}:{s:.1f}" for p, s in top])
        console.print(
            f"\n🎨 Selected palette constraints: [bold]{palette}[/bold] ({fit_msg})\n"
        )

    constraints = {
        "chroma": constraints_all["constraints"]["chroma"][palette],
        "hue": constraints_all["constraints"]["hue"][palette],
        "deltaL": constraints_all["constraints"]["deltaL"][palette],
        "lightness": constraints_all["constraints"].get("lightness", {}).get(
            palette, {}
        ),
    }

    # --------------------------------------------------------
    # Dark hue estimates (for background variety)
    # --------------------------------------------------------

    dark_hue, dark_hue_conf = dominant_dark_hue(df)
    dark_cluster_hue, dark_cluster_score = kmeans_dark_cluster_hue(df)

    # Background-ish hue from muted midtones (captures cool fields)
    L_q30 = df["L"].quantile(0.30)
    L_q85 = df["L"].quantile(0.85)
    C_q60 = df["chroma"].quantile(0.60)
    bg_mask = (df["L"] >= L_q30) & (df["L"] <= L_q85) & (df["chroma"] <= C_q60)
    bg_hue, bg_hue_conf = dominant_hue_band(df, mask=bg_mask, weight_chroma=False)

    # Warm accent hue from high-chroma warm range
    C_q75 = df["chroma"].quantile(0.75)
    warm_mask = (
        (df["hue"] >= 20) & (df["hue"] <= 110) & (df["chroma"] >= max(20.0, C_q75))
    )
    warm_hue, warm_hue_conf = dominant_hue_band(df, mask=warm_mask, weight_chroma=True)

    # --------------------------------------------------------
    # Initial role eligibility + scoring
    # --------------------------------------------------------

    rows = []
    for _, r in df.iterrows():
        roles = eligible_roles(r, constraints)
        for role in roles:
            rows.append(
                {
                    **r.to_dict(),
                    "role": role,
                    "score": score_color(r, role, constraints),
                }
            )

    pool = pd.DataFrame(rows)
    if pool.empty:
        pool = pd.DataFrame(columns=df.columns.tolist() + ["role", "score"])
    else:
        pool["derived"] = False

    # --------------------------------------------------------
    # Nudge missing roles to ensure candidate coverage
    # --------------------------------------------------------

    def nudge_into_role(row, role, *, relax: bool):
        L0, a0, b0 = float(row.L), float(row.a), float(row.b)
        L, C, h = lab_to_lch(L0, a0, b0)

        if role in constraints.get("lightness", {}):
            l = constraints["lightness"][role]
            q25 = float(l["q25"])
            q75 = float(l["q75"])
            if relax:
                relax_delta = float(l.get("relax_delta", (l["q90"] - l["q10"]) / 2))
                q25 = max(0.0, q25 - relax_delta)
                q75 = min(100.0, q75 + relax_delta)
            if L < q25:
                L = q25
            elif L > q75:
                L = q75

        if role in constraints["chroma"]:
            c = constraints["chroma"][role]
            q25 = float(c["q25"])
            q75 = float(c["q75"])
            if relax:
                relax_delta = float(c.get("relax_delta", (c["q90"] - c["q10"]) / 2))
                q25 = max(0.0, q25 - relax_delta)
                q75 = q75 + relax_delta
            if C < q25:
                C = q25
            elif C > q75:
                C = q75

        if role in constraints["hue"]:
            hinfo = constraints["hue"][role]
            center = float(hinfo["center"])
            half = float(hinfo["width"]) / 2.0
            mult = float(hinfo.get("relax_mult", 1.3)) if relax else 1.0
            half *= mult
            if circular_distance(h, center) > half:
                h = center

        L2, a2, b2 = lch_to_lab(L, C, h)
        r, g, b = lab_to_rgb_tuple(L2, a2, b2)
        return {
            "R": r,
            "G": g,
            "B": b,
            "L": L2,
            "a": a2,
            "b": b2,
            "chroma": math.sqrt(a2 * a2 + b2 * b2),
            "hue": math.degrees(math.atan2(b2, a2)) % 360.0,
            "frequency": float(row.frequency),
            "role": role,
            "derived": True,
        }

    roles = [
        "background",
        "surface",
        "overlay",
        "text",
        "accent_red",
        "accent_warm",
        "accent_cool",
        "accent_bridge",
    ]

    # broader sample: weighted random + high frequency head
    sample_n = min(nudge_samples, len(df))
    if sample_n > 0:
        prob = df["frequency"].to_numpy()
        prob = prob / prob.sum()
        rand_idx = np.random.choice(len(df), size=sample_n, replace=False, p=prob)
        head_n = min(200, len(df))
        head_idx = df["frequency"].nlargest(head_n).index.to_numpy()
        src = pd.concat(
            [df.loc[rand_idx], df.loc[head_idx]], ignore_index=True
        ).drop_duplicates()
    else:
        src = df.copy()

    nudged_rows = []
    for role in roles:
        have = int((pool["role"] == role).sum()) if not pool.empty else 0
        need = max(0, min_role_candidates - have)
        if need == 0:
            continue
        for _, r in src.sample(frac=1.0).iterrows():
            cand = nudge_into_role(r, role, relax=True)
            score_row = type("Row", (), cand)()
            cand["score"] = score_color(score_row, role, constraints)
            nudged_rows.append(cand)
            need -= 1
            if need == 0:
                break

    if nudged_rows:
        pool = pd.concat([pool, pd.DataFrame(nudged_rows)], ignore_index=True)
    if "derived" not in pool.columns:
        pool["derived"] = False

    # --------------------------------------------------------
    # Background anchor + fg-safety metrics
    # --------------------------------------------------------

    bg = pick_anchor(pool, "background")
    if bg is None:
        raise click.ClickException("No background matched constraints")

    bg_lab = np.array([bg.L, bg.a, bg.b], dtype=float)
    bg_L = float(bg.L)

    # Compute separation from background for all rows
    pool["deltaE_bg"] = pool.apply(
        lambda r: deltaE76(np.array([r.L, r.a, r.b], dtype=float), bg_lab),
        axis=1,
    )
    pool["deltaL_bg"] = pool["L"] - bg_L
    pool["abs_deltaL_bg"] = pool["deltaL_bg"].abs()

    # --------------------------------------------------------
    # Improve accent_cool pool for later syntax usage
    #   - hard gate: deltaE + abs(deltaL)
    #   - rescore: reward separation, penalize too-dark cools
    # --------------------------------------------------------

    cool_mask = pool["role"] == "accent_cool"
    if cool_mask.any():
        cool = pool[cool_mask].copy()

        # Hard gates (foreground safety)
        cool = cool[
            (cool["deltaE_bg"] >= cool_min_deltae)
            & (cool["abs_deltaL_bg"] >= cool_min_abs_deltal)
        ]

        if not cool.empty:
            # Rescore: boost separation; keep it bounded
            # (Additive to original score so we still prefer frequent + on-hue candidates.)
            cool["score"] = (
                cool["score"]
                + np.minimum(cool["deltaE_bg"], 60.0) * 0.5
                + np.minimum(cool["abs_deltaL_bg"], 40.0) * 0.6
            )

            # Soft penalty: discourage cool accents that are too close to bg in lightness on the dark side
            # This specifically prevents "almost-base teal" foregrounds.
            too_dark = cool["L"] < (bg_L + cool_soft_min_deltal)
            cool.loc[too_dark, "score"] -= (
                bg_L + cool_soft_min_deltal - cool.loc[too_dark, "L"]
            ) * 2.0

            # Replace old accent_cool rows with improved set
            pool = pd.concat([pool[~cool_mask], cool], ignore_index=True)
        else:
            # If we eliminated all cool accents, drop them (caller can tune thresholds)
            pool = pool[~cool_mask].copy()

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    render_role_pool(pool)

    # --------------------------------------------------------
    # Add metadata + ranks
    # --------------------------------------------------------

    pool = pool.reset_index(drop=True)
    pool["hex"] = pool.apply(lambda r: rgb_to_hex((r.R, r.G, r.B)), axis=1)
    pool["palette"] = palette
    pool["photo_dark_hue"] = dark_hue
    pool["photo_dark_hue_conf"] = dark_hue_conf
    pool["photo_dark_cluster_hue"] = dark_cluster_hue
    pool["photo_dark_cluster_score"] = dark_cluster_score
    pool["photo_bg_hue"] = bg_hue
    pool["photo_bg_hue_conf"] = bg_hue_conf
    pool["photo_warm_hue"] = warm_hue
    pool["photo_warm_hue_conf"] = warm_hue_conf

    pool = add_ranks(pool)

    # Deduplicate by visible color within role, prefer originals over nudged.
    pool = pool.sort_values(
        ["role", "derived", "score", "frequency"],
        ascending=[True, True, False, False],
    )
    pool = pool.drop_duplicates(subset=["role", "hex"], keep="first").reset_index(
        drop=True
    )
    pool["color_id"] = pool.index

    # Column order (authoritative)
    cols = [
        "color_id",
        "palette",
        "role",
        "derived",
        "hex",
        "R",
        "G",
        "B",
        "L",
        "a",
        "b",
        "chroma",
        "hue",
        "frequency",
        "score",
        "L_rank",
        "chroma_rank",
        "deltaE_bg",
        "deltaL_bg",
        "abs_deltaL_bg",
        "deltaE_bg_rank",
        "abs_deltaL_bg_rank",
    ]

    pool[cols].to_csv(out_csv, index=False)

    if out_image is not None:
        save_pool_table_image(pool, out_image, max_per_role=max_per_role)


if __name__ == "__main__":
    extract_color_pool()
