"""Self-contained HTML renderer for the final report model."""

from base64 import b64encode
from html import escape
import mimetypes
from pathlib import Path
from typing import Any, Mapping

from .model import ImageResolver
from .settings import ReportProfileSettings, ReportStyleSettings


def _text(value: Any) -> str:
    return escape(str(value)) if value not in (None, "") else "—"


def _image(path: Path | None, alt: str) -> str:
    if path is None:
        return f'<div class="image placeholder">{escape(alt)} unavailable</div>'
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = b64encode(path.read_bytes()).decode("ascii")
    return f'<div class="image"><img alt="{escape(alt)}" src="data:{mime};base64,{encoded}"></div>'


def _score_bar(label: str, value: Any) -> str:
    score = float(value) if isinstance(value, (int, float)) else 0.0
    shown = f"{score:.2f}" if isinstance(value, (int, float)) else "n/a"
    return (f'<div class="score-row"><span>{escape(label.title())}</span>'
            f'<div class="bar"><i style="width:{score * 100:.1f}%"></i></div><b>{shown}</b></div>')


def _cards(items: list[Mapping[str, Any]], kind: str) -> str:
    cards = []
    for item in items:
        identifier = item.get("finding_id") or item.get("recommendation_id")
        body = item.get("statement") if kind == "finding" else item.get("action")
        meta = []
        for key in (("severity", "confidence") if kind == "finding" else ("priority", "origin")):
            if item.get(key):
                meta.append(f'<span class="tag">{escape(key)}: {_text(item[key])}</span>')
        sources = " · ".join(_text(ref) for ref in item.get("source_refs", []))
        cards.append(f'''<article class="card {kind}">
          <h3>{_text(identifier)} · {_text(item.get("title"))}</h3><p>{_text(body)}</p>
          <div>{''.join(meta)}</div><small>{sources}</small></article>''')
    return "".join(cards)


def render_html(report: Mapping[str, Any], profile_name: str, profile: ReportProfileSettings,
                style: ReportStyleSettings, images: ImageResolver) -> str:
    overview = report["assembly_overview"]
    aggregate = report["scorecard"].get("aggregate", {})
    total = aggregate.get("mean_total_ffa")
    summary = "".join(f"<li>{_text(item.get('statement'))}</li>" for item in report["executive_summary"])
    findings = report["key_findings"][:profile.max_findings]
    recommendations = report["recommendations"][:profile.max_recommendations]
    subprocess = "".join(_score_bar(name, aggregate.get(f"mean_{name}_score"))
                         for name in ("separation", "handling", "positioning", "joining"))
    steps = ""
    if profile.include_steps:
        blocks = []
        for step in report["steps"]:
            rows = "".join(_score_bar(name, step["subprocesses"][name].get("score"))
                           for name in ("separation", "handling", "positioning", "joining"))
            narratives = "".join(
                f'<div><h4>{escape(name.title())}</h4><p><b>Potential:</b> {_text(step["subprocesses"][name].get("automation_potential"))}</p>'
                f'<p><b>Risk:</b> {_text(step["subprocesses"][name].get("risks"))}</p></div>'
                for name in ("separation", "handling", "positioning", "joining"))
            image = images.step(step["step_id"], step.get("image_refs"))
            blocks.append(f'''<section class="page"><h2>Step {step['step_id']} · {_text(step.get('step_description'))}</h2>
              <p>{_text(step.get('joining_process'))} · FFA {_text(step.get('total_ffa'))}</p>
              <div class="two">{_image(image, 'Step image')}<div>{rows}</div></div>
              <div class="grid">{narratives}</div></section>''')
        steps = "".join(blocks)
    parts = ""
    if profile.include_parts:
        blocks = []
        for part in report["parts"]:
            image = images.part(str(part["part_id"]))
            facts = (("Name", part.get("name")), ("Quantity", part.get("quantity")),
                     ("Size", part.get("size")), ("Volume", part.get("volume")),
                     ("Summary", part.get("intrinsic_summary")),
                     ("Geometry", part.get("geometric_characteristics")))
            fact_html = "".join(f"<dt>{escape(name)}</dt><dd>{_text(value)}</dd>" for name, value in facts)
            links = ", ".join(part.get("finding_ids", []) + part.get("recommendation_ids", [])) or "None"
            blocks.append(f'''<section class="page"><h2>{_text(part['part_id'])} · {_text(part.get('name'))}</h2>
              <div class="two">{_image(image, 'Part image')}<dl>{fact_html}<dt>Linked decisions</dt><dd>{escape(links)}</dd></dl></div></section>''')
        parts = "".join(blocks)
    unknowns = "".join(f"<li>{_text(item.get('statement'))}</li>" for item in report["assumptions_and_unknowns"])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_text(overview.get('assembly_name_guess') or overview.get('assembly_name'))}</title>
<style>
:root{{--primary:{style.primary};--accent:{style.accent};--risk:{style.risk};--muted:{style.muted};--bg:{style.background}}}
*{{box-sizing:border-box}} body{{margin:0;color:#172126;font-family:{style.font_family},sans-serif;background:var(--bg);line-height:1.45}}
main{{max-width:1180px;margin:auto;background:white}} .page{{padding:34px 42px;border-bottom:8px solid var(--bg);break-after:page}}
h1,h2,h3,h4{{color:var(--primary);margin-top:0}} .eyebrow{{color:var(--muted);text-transform:uppercase;letter-spacing:.12em}}
.hero{{display:grid;grid-template-columns:1.1fr .9fr;gap:28px}} .two{{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .image{{height:270px;display:flex;align-items:center;justify-content:center;border:1px solid #d7dfdc;background:#fff}}
.image img{{max-width:100%;max-height:100%;object-fit:contain}} .placeholder{{color:var(--muted)}}
.big-score{{font-size:54px;font-weight:700;color:var(--accent)}} .score-row{{display:grid;grid-template-columns:110px 1fr 42px;gap:10px;align-items:center;margin:9px 0}}
.bar{{height:9px;background:#dce4e1;border-radius:8px;overflow:hidden}} .bar i{{display:block;height:100%;background:var(--accent)}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .card{{padding:16px;border:1px solid #d7dfdc;border-left:5px solid var(--primary);border-radius:4px}}
.card.finding{{border-left-color:var(--risk)}} .tag{{display:inline-block;margin:0 7px 7px 0;padding:3px 7px;background:var(--bg);font-size:12px}}
small{{display:block;color:var(--muted);overflow-wrap:anywhere}} dl{{display:grid;grid-template-columns:130px 1fr;gap:7px 14px}} dt{{font-weight:700;color:var(--primary)}} dd{{margin:0}}
@media(max-width:760px){{.hero,.two,.grid,.cards{{grid-template-columns:1fr}}}} @media print{{body{{background:white}}main{{max-width:none}}}}
</style></head><body><main>
<section class="page"><div class="eyebrow">Fitness for Automation · {escape(profile_name)} report</div>
<h1>{_text(overview.get('assembly_name_guess') or overview.get('assembly_name'))}</h1>
<div class="hero"><div><div class="big-score">{_text(f'{total:.2f}' if isinstance(total,(int,float)) else None)}</div><p>Overall FFA score</p>{subprocess}</div>
{_image(images.assembly(), 'Assembly image')}</div><h2>Executive assessment</h2><ul>{summary}</ul></section>
<section class="page"><h2>Key findings</h2><div class="cards">{_cards(findings,'finding')}</div></section>
<section class="page"><h2>Recommendations</h2><div class="cards">{_cards(recommendations,'recommendation')}</div></section>
{steps}{parts}<section class="page"><h2>Assumptions and unknowns</h2><ul>{unknowns or '<li>None recorded</li>'}</ul></section>
</main></body></html>'''
