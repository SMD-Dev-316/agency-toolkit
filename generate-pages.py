#!/usr/bin/env python3
# ============================================================
# Rank & Rent Page Generation Script ‚Äî Option C
# Generates: city overview pages + individual service/city pages
# Usage: python3 generate-pages.py --config configs/fence-tier1-cities.json
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --dry-run
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --update
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --only-overviews
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --only-service-pages
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --static-pages
# ============================================================

import os
import sys
import json
import re
import uuid
import time
import random
import shutil
import argparse
import subprocess
from dotenv import load_dotenv
import anthropic

# ============================================================
# SETUP
# ============================================================
load_dotenv('/var/www/agency-toolkit/.env')
client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

GREEN  = '\033[0;32m'
YELLOW = '\033[1;33m'
RED    = '\033[0;31m'
BLUE   = '\033[0;34m'
NC     = '\033[0m'

def log(msg):     print(f"{GREEN}[‚úì]{NC} {msg}")
def warn(msg):    print(f"{YELLOW}[!]{NC} {msg}")
def err(msg):     print(f"{RED}[‚úó]{NC} {msg}"); sys.exit(1)
def section(msg): print(f"\n{BLUE}--- {msg} ---{NC}")

# ============================================================
# WP-CLI HELPER
# ============================================================
def wp(command, wp_path):
    full_cmd = f"wp {command} --path={wp_path} --allow-root"
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"WP-CLI error: {result.stderr.strip()}")
    return result.stdout.strip()

# ============================================================
# BLOCK ID UTILITIES
# ============================================================
def gen_id():
    return uuid.uuid4().hex[:8]

def gen_faq_id():
    ts = int(time.time() * 1000)
    suffix = uuid.uuid4().hex[:4]
    time.sleep(0.002)
    return f"faq-question-{ts}-{suffix}"

# Escape a string for JSON attribute embedding (backslash-escape quotes, no raw dashes in attrs)
def esc(text):
    return text.replace('"', '\\"').replace("'", "\\'")

# Escape content for WP-CLI single-quoted shell argument
def shell_esc(text):
    return text.replace("'", "'\\''")

# ============================================================
# KADENCE BLOCK BUILDERS ‚Äî Spectra ‚Üí Kadence migration
# ============================================================
# Every shape below was verified live against a real Kadence-enabled WP
# install (rar01.web-samples.com, 2026-09-27) by building the actual block in
# the real editor and reading back the real saved post_content via wp-cli ‚Äî
# not from block.json's attribute list alone, which hid real gotchas:
#   - kadence/infobox and kadence/advancedheading content is literal HTML
#     (the title/text lives in the saved <h*>/<p> tags), NOT a JSON attribute,
#     despite block.json listing "title"/"contentText"/"content" as attributes.
#   - kadence/testimonial is the opposite: content/name/occupation/rating
#     ARE real JSON attributes (omitted from output when they equal the
#     block's built-in default, e.g. rating defaults to 5).
#   - kadence/rowlayout always needs an explicit nested kadence/column child
#     ‚Äî it is not a single self-contained container the way uagb/container was.
#   - kadence/singlebtn can be a self-closing block (just attributes, no
#     inner HTML) ‚Äî Kadence's own JS/CSS renders the real <a> markup.
#   - borderStyle side arrays are ordered [color, style, width], confirmed
#     from class-kadence-blocks-css.php's own index mapping (0=color,1=style,
#     2=width) ‚Äî NOT the more common [width, style, color] convention. The
#     separate top-level "radius"/"borderRadius" split matters too: the plain
#     "radius" key some blocks expose is vestigial and renders no CSS at all;
#     the real field is "borderRadius"/"borderRadiusUnit".
#   - kadence/testimonials (plural, the wrapper) has no way to fully hide its
#     avatar area ‚Äî its Media Type control only offers Image/Icon, no None
#     (unlike infobox, which does support mediaType:"none").
#
# See project_prescale_roadmap.md / the pre-kadence-migration plan for the
# full verification log. Fields not yet needed by any converted call site are
# deliberately left out rather than guessed.

def kadence_row(inner_html, flex_basis_percent=None):
    """Single-column kadence/rowlayout + kadence/column wrapping inner_html.

    Kadence has no flexible N-item flex-wrap container equivalent to the old
    uagb/container(layout:flex) ‚Äî callers that need a multi-item wrapping
    grid still supply their own outer wrapper for now (not yet converted).
    flex_basis_percent (optional) adds a plain flex-sizing wrapper div so
    this still behaves as a flex child of an old uagb flex-parent container
    during the migration, when both block families are on the same page.
    """
    row_id = gen_id()
    col_id = gen_id()
    open_tag, close_tag = "", ""
    if flex_basis_percent:
        open_tag = f'<div style="flex:0 0 {flex_basis_percent}%;max-width:{flex_basis_percent}%;">'
        close_tag = "</div>"
    return (
        f"{open_tag}"
        f'<!-- wp:kadence/rowlayout {{"uniqueID":"{row_id}","columns":1,"colLayout":"equal","kbVersion":2}} -->\n'
        f'<!-- wp:kadence/column {{"borderWidth":["","","",""],"uniqueID":"{col_id}","kbVersion":2}} -->\n'
        f'<div class="wp-block-kadence-column kadence-column{col_id}"><div class="kt-inside-inner-col">'
        f"{inner_html}"
        f"</div></div>\n"
        f"<!-- /wp:kadence/column -->\n"
        f"<!-- /wp:kadence/rowlayout -->"
        f"{close_tag}"
    )


def kadence_heading(text, level=2, color=None, transform=None, letter_spacing=None):
    """kadence/advancedheading. Content is the literal <hN> tag ‚Äî level is
    expressed by which tag is written, not a JSON "level" attribute (verified:
    a real h2 in the editor produced no "level" key in the saved output)."""
    head_id = gen_id()
    attrs = {"uniqueID": head_id}
    if color:
        attrs["color"] = color
    if transform:
        attrs["textTransform"] = transform
    if letter_spacing is not None:
        attrs["letterSpacing"] = letter_spacing
    attrs_json = json.dumps(attrs, ensure_ascii=False, separators=(",", ":"))
    return (
        f"<!-- wp:kadence/advancedheading {attrs_json} -->\n"
        f'<h{level} class="kt-adv-heading{head_id} wp-block-kadence-advancedheading" '
        f'data-kb-block="kb-adv-heading{head_id}">{text}</h{level}>\n'
        f"<!-- /wp:kadence/advancedheading -->"
    )


def kadence_button(text, link, icon=None, icon_side="right", color=None, background=None,
                    color_hover=None, background_hover=None, border_color="#333",
                    border_radius=None, padding=None):
    """kadence/advancedbtn > kadence/singlebtn, self-closing (Kadence's own
    JS/CSS renders the real <a> markup from attributes alone ‚Äî verified live).

    borderStyle side arrays are [color, style, width] (verified from
    class-kadence-blocks-css.php's get_border_value index mapping), and
    radius is the separate "borderRadius"/"borderRadiusUnit" pair, not the
    vestigial "radius" key (same class of mistake already caught once this
    session for Astra's social icons)."""
    outer_id = gen_id()
    btn_id = gen_id()
    attrs = {"uniqueID": btn_id, "text": text, "link": link}
    if icon:
        attrs["icon"] = icon
        attrs["iconSide"] = icon_side
    if color:
        attrs["color"] = color
    if background:
        attrs["background"] = background
    if color_hover:
        attrs["colorHover"] = color_hover
    if background_hover:
        attrs["backgroundHover"] = background_hover
    if border_color:
        side = [border_color, "solid", "1"]
        attrs["borderStyle"] = [{"top": side, "right": side, "bottom": side, "left": side, "unit": "px"}]
    if border_radius is not None:
        attrs["borderRadius"] = [str(border_radius)] * 4
        attrs["borderRadiusUnit"] = "px"
    if padding:
        attrs["padding"] = [str(p) for p in padding]
        attrs["paddingUnit"] = "px"
    attrs_json = json.dumps(attrs, ensure_ascii=False, separators=(",", ":"))
    return (
        f'<!-- wp:kadence/advancedbtn {{"uniqueID":"{outer_id}"}} -->\n'
        f'<div class="wp-block-kadence-advancedbtn kb-buttons-wrap kb-btns{outer_id}">'
        f"<!-- wp:kadence/singlebtn {attrs_json} /--></div>\n"
        f"<!-- /wp:kadence/advancedbtn -->"
    )


def kadence_info_box(title, desc, halign="left"):
    """kadence/infobox with no media (mediaType:"none" ‚Äî verified live that
    this fully omits the media container div, not just empty-styles it).
    Title/description are literal HTML (h2/p tags), not JSON attributes,
    despite block.json listing "title"/"contentText" as attributes ‚Äî this
    version of Kadence sources them from the saved HTML instead."""
    box_id = gen_id()
    attrs = {"uniqueID": box_id, "hAlign": halign, "mediaType": "none", "kbVersion": 2}
    attrs_json = json.dumps(attrs, ensure_ascii=False, separators=(",", ":"))
    return (
        f"<!-- wp:kadence/infobox {attrs_json} -->\n"
        f'<div class="wp-block-kadence-infobox kt-info-box{box_id}">'
        f'<span class="kt-blocks-info-box-link-wrap info-box-link kt-blocks-info-box-media-align-top kt-info-halign-{halign}">'
        f'<div class="kt-infobox-textcontent">'
        f'<h2 class="kt-blocks-info-box-title">{title}</h2>'
        f'<p class="kt-blocks-info-box-text">{desc}</p>'
        f"</div></span></div>\n"
        f"<!-- /wp:kadence/infobox -->"
    )


def kadence_testimonial(quote, name=None, occupation=None, rating=None):
    """kadence/testimonials (plural wrapper, carries the shared rating-icon
    style) > kadence/testimonial (singular, self-closing). Replaces the old
    star-rating + 2x info-box combo (always used together as one card) with
    one native block. Unlike info-box/heading, content/name/occupation/rating
    ARE real JSON attributes here (verified live) ‚Äî each is only included
    when it differs from the block's built-in default (name/occupation
    default to placeholder text, rating defaults to 5), so pass None/omit
    for anything that should stay at the default.

    Known limitation (verified live, not yet worked around): the Testimonials
    media type control only offers Image or Icon ‚Äî there is no way to fully
    hide the avatar area the way kadence_info_box can hide its icon.
    """
    wrap_id = gen_id()
    inner_id = gen_id()
    wrap_attrs = {
        "uniqueID": wrap_id,
        "ratingStyles": [{"color": "#ffd700", "size": 16, "margin": ["", "", "", ""],
                           "iconSpacing": "", "icon": "fas_star", "stroke": 2}],
        "kbVersion": 2,
    }
    inner_attrs = {"uniqueID": inner_id, "content": quote}
    if name:
        inner_attrs["name"] = name
    if occupation:
        inner_attrs["occupation"] = occupation
    if rating is not None:
        inner_attrs["rating"] = rating
    wrap_json = json.dumps(wrap_attrs, ensure_ascii=False, separators=(",", ":"))
    inner_json = json.dumps(inner_attrs, ensure_ascii=False, separators=(",", ":"))
    return (
        f"<!-- wp:kadence/testimonials {wrap_json} -->\n"
        f"<!-- wp:kadence/testimonial {inner_json} /-->\n"
        f"<!-- /wp:kadence/testimonials -->"
    )


# ============================================================
# BLOCK BUILDERS ‚Äî Spectra / Gutenberg markup
# ============================================================


# ── Content cache ─────────────────────────────────────────────────────────────

def _cache_path(config_path):
    name = os.path.basename(config_path).replace(".json", "-content-cache.json")
    return os.path.join("/var/www/agency-toolkit/cache", name)

def _migrate_cache_entry(entry):
    """Convert an old-format cache entry ({"content": {...incl. faqs...},
    "meta": {...}}) into the new per-element schema ({"body", "faqs",
    "meta_title", "meta_description", "focus_keyword"}). Without this,
    every already-generated page would look like "nothing cached" under
    the new schema and trigger a mass fresh regeneration on first run —
    exactly the accidental-overwrite this whole system exists to prevent.
    Already-migrated entries pass through unchanged."""
    if "body" in entry or "faqs" in entry:
        return entry  # already new format
    if "content" not in entry:
        return entry  # unrecognized shape, leave as-is rather than guess
    content = dict(entry["content"])
    faqs = {"faq_h2": content.pop("faq_h2", ""), "faqs": content.pop("faqs", [])} if "faqs" in content else None
    meta = entry.get("meta", {})
    migrated = {"body": content}
    if faqs is not None:
        migrated["faqs"] = faqs
    if "seo_title" in meta:
        migrated["meta_title"] = meta["seo_title"]
    if "meta_description" in meta:
        migrated["meta_description"] = meta["meta_description"]
    if "focus_keyword" in meta:
        migrated["focus_keyword"] = meta["focus_keyword"]
    return migrated


def _load_cache(config_path):
    path = _cache_path(config_path)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {title: _migrate_cache_entry(entry) for title, entry in raw.items()}
    return {}

def _save_cache(cache, config_path):
    path = _cache_path(config_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _save_pre_override_snapshot(config_path, title, element, old_value):
    """Save a timestamped snapshot of an element's OLD value right before an
    unlock flag overwrites it — a fast local undo button for "the override
    was used and produced something worse". Not a durable/offsite backup
    (see the Docs-per-site roadmap item for that); this only protects
    against a single bad override on this server. No-op if there was
    nothing cached yet to protect (first-time generation, not an override)."""
    if old_value is None:
        return
    backup_dir = os.path.join("/var/www/agency-toolkit/cache", "content-backups")
    os.makedirs(backup_dir, exist_ok=True)
    site_name  = os.path.basename(config_path).replace(".json", "")
    safe_title = re.sub(r'[^a-zA-Z0-9_-]+', '-', title).strip('-')
    ts         = time.strftime("%Y%m%dT%H%M%S")
    path = os.path.join(backup_dir, f"{site_name}-{safe_title}-{element}-{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(old_value, f, indent=2)
    log(f"Pre-override snapshot saved: {path}")


# ============================================================
# IMAGE POOL
# ============================================================

POOL_ROOT    = "/var/www/rar-image-pool"
_IMAGE_EXTS  = (".jpg", ".jpeg", ".png", ".webp")


def _list_pool_candidates(pool_dir):
    """Real image files in a pool folder, ignoring NAMING_CONVENTION.txt
    and anything else that isn't an image."""
    if not os.path.isdir(pool_dir):
        return []
    return sorted(f for f in os.listdir(pool_dir) if f.lower().endswith(_IMAGE_EXTS))


def _image_selections_path(config_path):
    name = os.path.basename(config_path).replace(".json", "-image-selections.json")
    return os.path.join("/var/www/agency-toolkit/cache", name)


def _load_image_selections(config_path):
    path = _image_selections_path(config_path)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_image_selections(selections, config_path):
    path = _image_selections_path(config_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(selections, f, indent=2)


def _ensure_service_images_convention(config, config_path):
    """Guarantee config['service_images'][slug] points at the same fixed
    filenames the pool sync (and the homepage's own hardcoded convention)
    both use — rect-{slug}.jpg and wide-{slug}-1/2/3.jpg. This is
    deterministic and unrelated to which pool candidate is currently
    selected; it exists only to stop the homepage and the individual/
    services pages from silently drifting onto different filenames for
    the same service (see project_content_protection_system.md)."""
    services       = config.get("services", [])
    service_images = config.setdefault("service_images", {})
    changed = False
    for svc in services:
        slug   = str(svc).lower().replace(" ", "-").replace(",", "")
        entry  = service_images.setdefault(slug, {})
        rect_expected = f"rect-{slug}.jpg"
        wide_expected = [f"wide-{slug}-{n}.jpg" for n in (1, 2, 3)]
        if entry.get("rect") != rect_expected:
            entry["rect"] = rect_expected
            changed = True
        if entry.get("wide") != wide_expected:
            entry["wide"] = wide_expected
            changed = True
    if changed and config_path:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        log("service_images convention enforced in config (rect/wide filenames)")
    return changed


def sync_pool_images(config, wp_path, config_path, unlock_images=False):
    """Pick and place images from the central per-niche pool for this
    site. Locked by default per purpose (site-wide: hero, home-summary,
    home-about, home-parallax; per-service: rect, wide-1, wide-2, wide-3)
    — a purpose that's already been picked is left untouched unless
    unlock_images forces a fresh pick, with the old selection snapshotted
    first. A missing or empty pool folder is skipped with a warning
    rather than breaking page generation — the pool is additive, not a
    hard dependency, since it may not be populated for every niche yet."""
    niche_slug    = config.get("primary_service_name", "Drain Cleaning").lower().replace(" ", "-")
    pool_niche_dir = os.path.join(POOL_ROOT, niche_slug)
    rar_dest_dir   = os.path.join(wp_path, "wp-content", "uploads", "rar")
    os.makedirs(rar_dest_dir, exist_ok=True)

    selections = _load_image_selections(config_path) if config_path else {}

    def _sync_one(purpose_key, pool_dir, dest_filename):
        if purpose_key in selections and not unlock_images:
            return  # locked, already picked — leave it alone
        candidates = _list_pool_candidates(pool_dir)
        if not candidates:
            warn(f"No pool images for {purpose_key} ({pool_dir}) — leaving existing image in place")
            return
        if purpose_key in selections:
            _save_pre_override_snapshot(config_path, purpose_key, "image_selection", selections[purpose_key])
        chosen = random.choice(candidates)
        shutil.copyfile(os.path.join(pool_dir, chosen), os.path.join(rar_dest_dir, dest_filename))
        selections[purpose_key] = chosen
        log(f"Image pool: {purpose_key} -> {chosen}")

    # Destination filenames are hardcoded per the exact convention build_homepage()
    # already expects — not derived by string-concatenating the purpose name
    # (that produced "home-home-summary-..." for "home-summary", a real bug
    # caught in testing before this shipped).
    site_wide_dest = {
        "hero":          f"home-hero-{niche_slug}-01.jpg",
        "home-summary":  f"home-summary-{niche_slug}-01.jpg",
        "home-about":    f"home-about-{niche_slug}-01.jpg",
        "home-parallax": f"home-parallax-{niche_slug}-01.jpg",
    }
    for purpose, dest_filename in site_wide_dest.items():
        _sync_one(purpose, os.path.join(pool_niche_dir, purpose), dest_filename)

    for svc in config.get("services", []):
        slug = str(svc).lower().replace(" ", "-").replace(",", "")
        _sync_one(f"rect:{slug}", os.path.join(pool_niche_dir, "services", slug, "rect"), f"rect-{slug}.jpg")
        for n in (1, 2, 3):
            _sync_one(f"wide-{n}:{slug}", os.path.join(pool_niche_dir, "services", slug, f"wide-{n}"), f"wide-{slug}-{n}.jpg")

    if config_path:
        _save_image_selections(selections, config_path)
    _ensure_service_images_convention(config, config_path)


def build_faq_block(faqs):
    """Build Rank Math FAQ block with FAQPage schema support."""
    questions = []
    html_items = []
    for faq in faqs:
        faq_id = gen_faq_id()
        questions.append({
            "id": faq_id,
            "title": faq["question"],
            "content": faq["answer"],
            "visible": True
        })
        html_items.append(
            f'<div class="rank-math-faq-item">'
            f'<h3 class="rank-math-question">{faq["question"]}</h3>'
            f'<div class="rank-math-answer">{faq["answer"]}</div>'
            f'</div>'
        )

    q_json = json.dumps(questions, ensure_ascii=False)
    html = ''.join(html_items)
    return (
        f'<!-- wp:rank-math/faq-block {{"questions":{q_json}}} -->\n'
        f'<div class="wp-block-rank-math-faq-block">{html}</div>\n'
        f'<!-- /wp:rank-math/faq-block -->'
    )


def build_banner(h1_text, subtitle, banner_cta_ref, banner_image_url=""):
    """Full-width banner with H1 info-box and reusable CTA button pattern."""
    outer_id  = gen_id()
    inner_id  = gen_id()
    ibox_id   = gen_id()

    if banner_image_url:
        bg_attrs = (
            f'"backgroundType":"image",'
            f'"backgroundImageDesktop":{{"url":"{banner_image_url}"}},'
            f'"backgroundImageColor":"var(\\u002d\\u002dast-global-color-0)",'
            f'"overlayType":"color","overlayOpacity":0.86,'
        )
    else:
        bg_attrs = (
            f'"backgroundType":"color",'
            f'"backgroundColor":"var(\\u002d\\u002dast-global-color-2)",'
        )

    return (
        f'<!-- wp:uagb/container {{"block_id":"{outer_id}","directionDesktop":"row",'
        f'"justifyContentDesktop":"flex-start",{bg_attrs}'
        f'"topPaddingDesktop":40,"bottomPaddingDesktop":40,'
        f'"leftPaddingDesktop":20,"rightPaddingDesktop":20,'
        f'"topPaddingTablet":50,"bottomPaddingTablet":50,'
        f'"leftPaddingTablet":50,"rightPaddingTablet":50,'
        f'"topPaddingMobile":50,"bottomPaddingMobile":50,'
        f'"leftPaddingMobile":30,"rightPaddingMobile":30,'
        f'"paddingLink":false,"variationSelected":true,'
        f'"isBlockRootParent":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{outer_id} alignfull uagb-is-root-container">'
        f'<div class="uagb-container-inner-blocks-wrap">'
        f'<!-- wp:uagb/container {{"block_id":"{inner_id}","widthDesktop":70,"widthSetByUser":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{inner_id}">'
        f'<!-- wp:uagb/info-box {{"classMigrate":true,"block_id":"{ibox_id}",'
        f'"headingAlign":"left","headingColor":"#ffffff","subHeadingColor":"#ffffff",'
        f'"headingTag":"h1","headSpace":20,"subHeadSpace":44,'
        f'"showIcon":false}} -->\n'
        f'<div class="uagb-block-{ibox_id} uagb-infobox__content-wrap uagb-infobox-icon-above-title uagb-infobox-image-valign-top">'
        f'<div class="uagb-ifb-content">'
        f'<div class="uagb-ifb-title-wrap"><h1 class="uagb-ifb-title">{h1_text}</h1></div>'
        f'<p class="uagb-ifb-desc">{subtitle}</p>'
        f'</div></div>\n'
        f'<!-- /wp:uagb/info-box -->\n'
        f'<!-- wp:block {{"ref":{banner_cta_ref}}} /-->'
        f'</div>\n<!-- /wp:uagb/container -->'
        f'</div></div>\n<!-- /wp:uagb/container -->'
    )


def build_uagb_separator(sep_id):
    """Spectra separator block (uagb/separator, not core wp:separator)."""
    return (
        f'<!-- wp:uagb/separator {{"block_id":"{sep_id}","separatorAlign":"left",'
        f'"separatorBorderHeight":1,'
        f'"separatorColor":"var(\\u002d\\u002dast-global-color-0)",'
        f'"blockTopMargin":15,"blockRightMargin":0,"blockLeftMargin":0,"blockBottomMargin":30}} -->\n'
        f'<div class="wp-block-uagb-separator uagb-block-{sep_id}">'
        f'<div class="uagb-separator-spacing-wrapper">'
        f'<div class="wp-block-uagb-separator__inner" style="--my-background-image:"></div>'
        f'</div></div>\n'
        f'<!-- /wp:uagb/separator -->'
    )


def build_content_section(h2, paragraph, cta_title, cta_desc, img_url, free_quote_url, alt_text="", is_last=False):
    """H2 + wide image + paragraph + CTA + separator (one content block)."""
    sec_id  = gen_id()
    head_id = gen_id()
    img_id  = gen_id()
    cta_id  = gen_id()
    sep_id  = gen_id()

    cta_arrow_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        '<path d="M504.3 273.6l-112.1 104c-6.992 6.484-17.18 8.218-25.94 4.406'
        'c-8.758-3.812-14.42-12.45-14.42-21.1L351.9 288H32C14.33 288 .0002 273.7'
        ' .0002 255.1S14.33 224 32 224h319.9l0-72c0-9.547 5.66-18.19 14.42-22'
        'c8.754-3.809 18.95-2.075 25.94 4.41l112.1 104C514.6 247.9 514.6 264.1 504.3 273.6z">'
        '</path></svg>'
    )

    sep = '' if is_last else '\n' + build_uagb_separator(sep_id)

    return (
        f'<!-- wp:uagb/container {{"block_id":"{sec_id}","rowGapDesktop":20}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{sec_id}">'
        f'<!-- wp:uagb/advanced-heading {{"block_id":"{head_id}","classMigrate":true,'
        f'"headingDescToggle":false}} -->\n'
        f'<div class="wp-block-uagb-advanced-heading uagb-block-{head_id}">'
        f'<h2 class="uagb-heading-text">{h2}</h2></div>\n'
        f'<!-- /wp:uagb/advanced-heading -->\n'
        f'<!-- wp:uagb/image {{"block_id":"{img_id}","url":"{img_url}",'
        f'"urlTablet":"{img_url}","urlMobile":"{img_url}",'
        f'"linkDestination":"none","naturalWidth":1024,"naturalHeight":478,'
        f'"sizeSlug":"large","sizeSlugTablet":"large","sizeSlugMobile":"large"}} -->\n'
        f'<div class="wp-block-uagb-image uagb-block-{img_id} '
        f'wp-block-uagb-image--layout-default wp-block-uagb-image--effect-static '
        f'wp-block-uagb-image--align-none">'
        f'<figure class="wp-block-uagb-image__figure">'
        f'<img src="{img_url}" alt="{alt_text}" width="1024" height="478" loading="lazy" role="img"/>'
        f'</figure></div>\n'
        f'<!-- /wp:uagb/image -->\n'
        f'<!-- wp:paragraph -->\n<p>{paragraph}</p>\n<!-- /wp:paragraph -->\n'
        f'<!-- wp:uagb/call-to-action {{"classMigrate":true,"titleColor":"","block_id":"{cta_id}",'
        f'"stack":"desktop","btnBorderTopWidth":1,"btnBorderLeftWidth":1,'
        f'"btnBorderRightWidth":1,"btnBorderBottomWidth":1,'
        f'"btnBorderTopLeftRadius":0,"btnBorderTopRightRadius":0,'
        f'"btnBorderBottomLeftRadius":0,"btnBorderBottomRightRadius":0,'
        f'"btnBorderStyle":"solid","btnBorderColor":"#333","ctaLink":"{free_quote_url}"}} -->\n'
        f'<div class="wp-block-uagb-call-to-action uagb-block-{cta_id} wp-block-button">'
        f'<div class="uagb-cta__wrap">'
        f'<h3 class="uagb-cta__title">{cta_title}</h3>'
        f'<p class="uagb-cta__desc">{cta_desc}</p>'
        f'</div>'
        f'<div class="uagb-cta__buttons">'
        f'<a href="{free_quote_url}" class="uagb-cta__button-link-wrapper wp-block-button__link" '
        f'target="_self" rel="noopener noreferrer">Get a Free Quote{cta_arrow_svg}</a>'
        f'</div></div>\n'
        f'<!-- /wp:uagb/call-to-action -->'
        f'{sep}</div>\n<!-- /wp:uagb/container -->'
    )


def build_service_area_section(area_h2, area_paragraph, faq_h2, faq_block):
    """Service area paragraph + FAQ heading + Rank Math FAQ block."""
    sec_id   = gen_id()
    area_hid = gen_id()
    faq_hid  = gen_id()
    sep_id   = gen_id()

    return (
        f'<!-- wp:uagb/container {{"block_id":"{sec_id}","rowGapDesktop":20}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{sec_id}">'
        f'<!-- wp:uagb/advanced-heading {{"block_id":"{area_hid}","classMigrate":true,'
        f'"headingDescToggle":false}} -->\n'
        f'<div class="wp-block-uagb-advanced-heading uagb-block-{area_hid}">'
        f'<h2 class="uagb-heading-text">{area_h2}</h2></div>\n'
        f'<!-- /wp:uagb/advanced-heading -->\n'
        f'<!-- wp:paragraph -->\n<p>{area_paragraph}</p>\n<!-- /wp:paragraph -->\n'
        f'<!-- wp:uagb/advanced-heading {{"block_id":"{faq_hid}","classMigrate":true,'
        f'"headingDescToggle":false}} -->\n'
        f'<div class="wp-block-uagb-advanced-heading uagb-block-{faq_hid}">'
        f'<h2 class="uagb-heading-text">{faq_h2}</h2></div>\n'
        f'<!-- /wp:uagb/advanced-heading -->\n'
        f'{faq_block}\n'
        f'{build_uagb_separator(sep_id)}'
        f'</div>\n<!-- /wp:uagb/container -->'
    )


def build_sidebar(sidebar_ref):
    """30% sidebar ‚Äî outer wrapper sets width, inner container handles sticky."""
    outer_id = gen_id()
    inner_id = gen_id()

    return (
        f'<!-- wp:uagb/container {{"block_id":"{outer_id}","widthDesktop":30,'
        f'"widthTablet":100,"alignItemsTablet":"center","alignItemsMobile":"center",'
        f'"justifyContentDesktop":"flex-start",'
        f'"topPaddingDesktop":0,"bottomPaddingDesktop":0,'
        f'"leftPaddingDesktop":0,"rightPaddingDesktop":0,'
        f'"topPaddingTablet":0,"bottomPaddingTablet":0,'
        f'"leftPaddingTablet":0,"rightPaddingTablet":0,'
        f'"topPaddingMobile":0,"bottomPaddingMobile":0,'
        f'"leftPaddingMobile":0,"rightPaddingMobile":0,'
        f'"paddingLink":false,"variationSelected":true,'
        f'"rowGapDesktop":24,"rowGapTablet":24,"rowGapMobile":24,'
        f'"columnGapDesktop":0,"columnGapTablet":0,"columnGapMobile":0,'
        f'"widthSetByUser":true,"childrenWidthDesktop":"equal"}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{outer_id}">'
        f'<!-- wp:uagb/container {{"block_id":"{inner_id}",'
        f'"UAGPosition":"sticky","UAGStickyRestricted":true,"UAGStickyOffset":40}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{inner_id}">'
        f'<!-- wp:block {{"ref":{sidebar_ref}}} /-->'
        f'</div>\n<!-- /wp:uagb/container -->'
        f'</div>\n<!-- /wp:uagb/container -->'
    )


def build_service_card_uagb(service_name, description, service_url, img_url, alt_text=""):
    """Single service card for city overview grid ‚Äî original Spectra/uagb
    version, kept during the Kadence migration for comparison/rollback.
    See build_service_card_kadence for the converted version; build_service_card
    below picks between them."""
    card_id   = gen_id()
    img_id    = gen_id()
    ibox_id   = gen_id()
    btns_id   = gen_id()
    btn_id    = gen_id()

    chevron_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 512" aria-hidden="true" focussable="false">'
        '<path d="M96 480c-8.188 0-16.38-3.125-22.62-9.375c-12.5-12.5-12.5-32.75 0-45.25L242.8 256L73.38 86.63'
        'c-12.5-12.5-12.5-32.75 0-45.25s32.75-12.5 45.25 0l192 192c12.5 12.5 12.5 32.75 0 45.25l-192 192'
        'C112.4 476.9 104.2 480 96 480z"></path></svg>'
    )

    return (
        f'<!-- wp:uagb/container {{"block_id":"{card_id}","widthDesktop":33,"widthTablet":31,'
        f'"alignItemsDesktop":"flex-start","justifyContentDesktop":"flex-start",'
        f'"backgroundType":"color","backgroundColor":"var(\\u002d\\u002dast-global-color-5)",'
        f'"boxShadowColor":"rgba(0,0,0,0.1)","boxShadowVOffset":4,"boxShadowBlur":8,"boxShadowSpread":6,'
        f'"topPaddingDesktop":20,"bottomPaddingDesktop":20,"leftPaddingDesktop":20,"rightPaddingDesktop":20,'
        f'"topPaddingTablet":16,"bottomPaddingTablet":16,"leftPaddingTablet":16,"rightPaddingTablet":16,'
        f'"topPaddingMobile":16,"bottomPaddingMobile":16,"leftPaddingMobile":16,"rightPaddingMobile":16,'
        f'"variationSelected":true,'
        f'"rowGapDesktop":24,"rowGapTablet":24,"rowGapMobile":20,"columnGapDesktop":0,'
        f'"widthSetByUser":true,'
        f'"containerBorderTopLeftRadius":6,"containerBorderTopRightRadius":6,'
        f'"containerBorderBottomLeftRadius":6,"containerBorderBottomRightRadius":6,'
        f'"layout":"flex","isGridCssInParent":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-layout-flex uagb-block-{card_id}">'
        f'<!-- wp:uagb/image {{"block_id":"{img_id}",'
        f'"url":"{img_url}","urlTablet":"{img_url}","urlMobile":"{img_url}",'
        f'"align":"left","linkDestination":"none","title":"{esc(service_name)}",'
        f'"width":402,"widthTablet":650,"widthMobile":600,'
        f'"height":260,"heightTablet":300,"heightMobile":200,'
        f'"naturalWidth":1024,"naturalHeight":683,'
        f'"sizeSlug":"custom","sizeSlugTablet":"custom","sizeSlugMobile":"custom",'
        f'"imageTopMargin":0,"imageRightMargin":0,"imageLeftMargin":0,"imageBottomMargin":0,'
        f'"imageMarginLink":false,'
        f'"objectFit":"cover","objectFitTablet":"cover","objectFitMobile":"cover",'
        f'"customHeightSetDesktop":true,"customHeightSetTablet":true,"customHeightSetMobile":true,'
        f'"imageBorderTopWidth":0,"imageBorderLeftWidth":0,"imageBorderRightWidth":0,"imageBorderBottomWidth":0,'
        f'"imageBorderTopLeftRadius":6,"imageBorderTopRightRadius":6,'
        f'"imageBorderBottomLeftRadius":6,"imageBorderBottomRightRadius":6,'
        f'"imageBorderLink":false,"className":"alignleft"}} -->\n'
        f'<div class="wp-block-uagb-image alignleft uagb-block-{img_id} '
        f'wp-block-uagb-image--layout-default wp-block-uagb-image--effect-static wp-block-uagb-image--align-left">'
        f'<figure class="wp-block-uagb-image__figure">'
        f'<img src="{img_url}" alt="{alt_text}" width="402" height="260" '
        f'loading="lazy" role="img"/></figure></div>\n'
        f'<!-- /wp:uagb/image -->\n'
        f'<!-- wp:uagb/info-box {{"classMigrate":true,"block_id":"{ibox_id}",'
        f'"headingAlign":"left","headingColor":"var(\\u002d\\u002dast-global-color-2)",'
        f'"subHeadingColor":"var(\\u002d\\u002dast-global-color-3)",'
        f'"headSpace":16,"subHeadSpace":4,"imageWidth":120,"showIcon":false,'
        f'"headTopMargin":0,"headRightMargin":0,"headLeftMargin":0,'
        f'"headMarginTopTablet":0,"headMarginRightTablet":0,"headTabletSpace":16,"headMarginLeftTablet":0,'
        f'"headMarginTopMobile":0,"headMarginRightMobile":0,"headMobileSpace":12,"headMarginLeftMobile":0,'
        f'"blockTopPaddingTablet":0,"blockRightPaddingTablet":0,"blockLeftPaddingTablet":0,"blockBottomPaddingTablet":0,'
        f'"subHeadTopMargin":0,"subHeadRightMargin":0,"subHeadLeftMargin":0,'
        f'"subHeadMarginTopTablet":0,"subHeadMarginRightTablet":0,"subHeadTabletSpace":0,"subHeadMarginLeftTablet":0,'
        f'"subHeadMarginTopMobile":0,"subHeadMarginRightMobile":0,"subHeadMobileSpace":0,"subHeadMarginLeftMobile":0,'
        f'"btnBorderTopWidth":1,"btnBorderLeftWidth":1,"btnBorderRightWidth":1,"btnBorderBottomWidth":1,'
        f'"btnBorderTopLeftRadius":0,"btnBorderTopRightRadius":0,'
        f'"btnBorderBottomLeftRadius":0,"btnBorderBottomRightRadius":0,'
        f'"btnBorderStyle":"solid","btnBorderColor":"#333"}} -->\n'
        f'<div class="uagb-block-{ibox_id} uagb-infobox__content-wrap uagb-infobox-icon-above-title uagb-infobox-image-valign-top">'
        f'<div class="uagb-ifb-content">'
        f'<div class="uagb-ifb-title-wrap"><h3 class="uagb-ifb-title">{service_name}</h3></div>'
        f'<p class="uagb-ifb-desc">{description}</p>'
        f'</div></div>\n'
        f'<!-- /wp:uagb/info-box -->\n'
        f'<!-- wp:uagb/buttons {{"block_id":"{btns_id}","classMigrate":true,'
        f'"childMigrate":true,"align":"left","alignTablet":"left","alignMobile":"left","gap":0}} -->\n'
        f'<div class="wp-block-uagb-buttons uagb-buttons__outer-wrap uagb-btn__default-btn '
        f'uagb-btn-tablet__default-btn uagb-btn-mobile__default-btn uagb-block-{btns_id}">'
        f'<div class="uagb-buttons__wrap uagb-buttons-layout-wrap ">'
        f'<!-- wp:uagb/buttons-child {{"block_id":"{btn_id}","label":"Learn More",'
        f'"link":"{service_url}",'
        f'"topPadding":7,"rightPadding":10,"bottomPadding":7,"leftPadding":13,"paddingLink":false,'
        f'"color":"#ffffff","hColor":"var(\\u002d\\u002dast-global-color-1)",'
        f'"hBackground":"var(\\u002d\\u002dast-global-color-7)",'
        f'"icon":"chevron-right",'
        f'"topMargin":0,"rightMargin":0,"bottomMargin":0,"leftMargin":0,'
        f'"iconColor":"var(\\u002d\\u002dast-global-color-5)",'
        f'"iconHColor":"var(\\u002d\\u002dast-global-color-1)",'
        f'"btnBorderTopWidth":1,"btnBorderLeftWidth":1,"btnBorderRightWidth":1,"btnBorderBottomWidth":1,'
        f'"btnBorderTopLeftRadius":30,"btnBorderTopRightRadius":30,'
        f'"btnBorderBottomLeftRadius":30,"btnBorderBottomRightRadius":30,'
        f'"btnBorderStyle":"solid","btnBorderColor":"#333","btnBorderHColor":"#333","showIcon":true}} -->\n'
        f'<div class="wp-block-uagb-buttons-child uagb-buttons__outer-wrap '
        f'uagb-block-{btn_id} wp-block-button">'
        f'<div class="uagb-button__wrapper">'
        f'<a class="uagb-buttons-repeater wp-block-button__link" aria-label="" href="{service_url}" '
        f'rel="follow noopener" target="_self" role="button">'
        f'<div class="uagb-button__link">Learn More</div>'
        f'<span class="uagb-button__icon uagb-button__icon-position-after">{chevron_svg}</span>'
        f'</a></div></div>\n'
        f'<!-- /wp:uagb/buttons-child -->'
        f'</div></div>\n<!-- /wp:uagb/buttons -->'
        f'</div>\n<!-- /wp:uagb/container -->'
    )


def build_service_card_kadence(service_name, description, service_url, img_url, alt_text=""):
    """Single service card for city overview grid ‚Äî Kadence version.

    The image stays a plain <img> (not wrapped in a kadence/image block
    comment) deliberately: kadence/image's real saved markup hasn't been
    verified live yet the way info-box/heading/buttons/testimonial have, and
    WordPress renders raw HTML outside any block comment fine (classic/
    freeform content), so this avoids guessing at an unverified block shape.

    The 33%-wide flex-child sizing is preserved via kadence_row's
    flex_basis_percent, since the grid parent this drops into
    (build_city_overview_page / build_homepage's card loop) is still the old
    uagb/container(layout:flex) ‚Äî not yet converted in this pass.
    """
    img_html = (
        f'<img src="{img_url}" alt="{alt_text}" title="{esc(service_name)}" '
        f'width="402" height="260" loading="lazy" role="img" '
        f'style="width:100%;height:260px;object-fit:cover;border-radius:6px;"/>'
    )
    info_box_html = kadence_info_box(service_name, description, halign="left")
    button_html = kadence_button(
        "Learn More", service_url,
        icon="fas_chevron-right", icon_side="right",
        color="#ffffff", background="var(--ast-global-color-5)",
        color_hover="var(--ast-global-color-1)", background_hover="var(--ast-global-color-7)",
        border_radius=30, padding=(7, 13, 7, 10),
    )
    card_inner = img_html + info_box_html + button_html
    return kadence_row(card_inner, flex_basis_percent=33)


def build_service_card(service_name, description, service_url, img_url, alt_text="", use_kadence=False):
    """Single service card for city overview grid. use_kadence picks between
    the original Spectra/uagb markup and the converted Kadence markup ‚Äî see
    the two implementations above."""
    if use_kadence:
        return build_service_card_kadence(service_name, description, service_url, img_url, alt_text)
    return build_service_card_uagb(service_name, description, service_url, img_url, alt_text)


def build_individual_service_page(c, config, service="", city="", state=""):
    """
    Assemble the full block markup for an individual service/city page.
    c = merged body + faqs dicts (from generate_individual_body_content()
    and generate_individual_faqs(), or their cached equivalents)
    """
    free_quote    = config.get("free_quote_url", "/free-quote/")
    phone         = config.get("phone", "000-000-0000")
    sidebar_ref      = config.get("sidebar_block_ref", 1824)
    banner_cta_ref   = config.get("banner_cta_ref", 2419)

    svc_slug   = service.lower().replace(" ", "-").replace(",", "")
    img_base   = config.get("rar_image_base", "")
    svc_imgs   = config.get("service_images", {}).get(svc_slug, {})
    wide       = svc_imgs.get("wide", ["", "", ""])
    img_url_1  = img_base + wide[0] if len(wide) > 0 else ""
    img_url_2  = img_base + wide[1] if len(wide) > 1 else ""
    img_url_3  = img_base + wide[2] if len(wide) > 2 else ""
    alt_text   = f"{service} in {city}, {state}" if city else ""

    faq_block = build_faq_block(c["faqs"])

    banner = build_banner(c["banner_h1"], c["banner_subtitle"], banner_cta_ref)

    s1 = build_content_section(
        c["section1_h2"], c["section1_paragraph"],
        c["section1_cta_title"], c["section1_cta_desc"],
        img_url_1, free_quote, alt_text
    )
    s2 = build_content_section(
        c["section2_h2"], c["section2_paragraph"],
        c["section2_cta_title"], c["section2_cta_desc"],
        img_url_2, free_quote, alt_text
    )
    s3 = build_content_section(
        c["section3_h2"], c["section3_paragraph"],
        c["section3_cta_title"], c["section3_cta_desc"],
        img_url_3, free_quote, alt_text
    )
    s4 = build_service_area_section(
        c["service_area_h2"], c["service_area_paragraph"],
        c["faq_h2"], faq_block
    )

    left_col_id = gen_id()
    left_col = (
        f'<!-- wp:uagb/container {{"block_id":"{left_col_id}","widthDesktop":65,'
        f'"widthTablet":100,"alignItemsTablet":"center","alignItemsMobile":"center",'
        f'"justifyContentDesktop":"flex-start",'
        f'"topPaddingDesktop":0,"bottomPaddingDesktop":0,'
        f'"leftPaddingDesktop":0,"rightPaddingDesktop":0,'
        f'"topPaddingTablet":0,"bottomPaddingTablet":0,'
        f'"leftPaddingTablet":0,"rightPaddingTablet":0,'
        f'"topPaddingMobile":0,"bottomPaddingMobile":0,'
        f'"leftPaddingMobile":0,"rightPaddingMobile":0,'
        f'"paddingLink":false,"variationSelected":true,'
        f'"rowGapDesktop":24,"rowGapTablet":24,"rowGapMobile":24,'
        f'"columnGapDesktop":0,"widthSetByUser":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{left_col_id}">\n'
        f'{s1}\n{s2}\n{s3}\n{s4}\n'
        f'</div>\n<!-- /wp:uagb/container -->'
    )

    sidebar  = build_sidebar(sidebar_ref)
    outer_id = gen_id()
    content_area = (
        f'<!-- wp:uagb/container {{"block_id":"{outer_id}","directionDesktop":"row",'
        f'"directionTablet":"column","alignItemsDesktop":"stretch",'
        f'"alignItemsTablet":"stretch","alignItemsMobile":"stretch",'
        f'"justifyContentDesktop":"flex-start",'
        f'"backgroundType":"color",'
        f'"backgroundColor":"var(\\u002d\\u002dast-global-color-5)",'
        f'"topPaddingDesktop":112,"bottomPaddingDesktop":112,'
        f'"leftPaddingDesktop":40,"rightPaddingDesktop":40,'
        f'"topPaddingTablet":80,"bottomPaddingTablet":80,'
        f'"leftPaddingTablet":32,"rightPaddingTablet":32,'
        f'"topPaddingMobile":64,"bottomPaddingMobile":64,'
        f'"leftPaddingMobile":24,"rightPaddingMobile":24,'
        f'"paddingLink":false,"variationSelected":true,'
        f'"rowGapDesktop":0,"rowGapTablet":0,"rowGapMobile":40,'
        f'"columnGapDesktop":72,"columnGapTablet":40,"columnGapMobile":0,'
        f'"isBlockRootParent":true,"equalHeight":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{outer_id} alignfull uagb-is-root-container">'
        f'<div class="uagb-container-inner-blocks-wrap">\n'
        f'{left_col}\n{sidebar}\n'
        f'</div></div>\n<!-- /wp:uagb/container -->'
    )

    return banner + "\n\n" + content_area


def build_city_overview_page(c, services, config):
    """
    Assemble the full block markup for a city overview page.
    c = content dict from generate_city_overview_content()
    """
    free_quote  = config.get("free_quote_url", "/free-quote/")
    sidebar_ref    = config.get("sidebar_block_ref", 1824)
    banner_cta_ref = config.get("banner_cta_ref", 2419)
    img_base       = config.get("rar_image_base", "")
    service_images = config.get("service_images", {})

    banner = build_banner(c["banner_h1"], c["banner_subtitle"], banner_cta_ref)

    # Build service cards
    cards = []
    primary_city  = c.get("_city", "")
    primary_state = c.get("_state", "")
    for i, svc in enumerate(services):
        svc_slug   = svc.lower().replace(" ", "-").replace(",", "")
        city_slug  = f"{primary_city.lower().replace(' ', '-')}-{primary_state.lower()}"
        svc_url    = f"/{svc_slug}-in-{city_slug}/"
        desc       = c["service_cards"][i]["description"] if i < len(c["service_cards"]) else ""
        rect_file  = service_images.get(svc_slug, {}).get("rect", "")
        img_url    = img_base + rect_file if rect_file else ""
        alt_text   = f"{svc} in {primary_city}, {primary_state}"
        cards.append(build_service_card(svc, desc, svc_url, img_url, alt_text,
                                         use_kadence=config.get("use_kadence", False)))

    grid_inner_id = gen_id()
    grid_outer_id = gen_id()

    cards_markup = "\n".join(cards)
    grid = (
        f'<!-- wp:uagb/container {{"block_id":"{grid_outer_id}","directionDesktop":"row",'
        f'"directionTablet":"column","alignItemsDesktop":"stretch",'
        f'"alignItemsTablet":"stretch","alignItemsMobile":"stretch",'
        f'"justifyContentDesktop":"flex-start",'
        f'"backgroundType":"color",'
        f'"backgroundColor":"var(\\u002d\\u002dast-global-color-5)",'
        f'"topPaddingDesktop":112,"bottomPaddingDesktop":112,'
        f'"leftPaddingDesktop":40,"rightPaddingDesktop":40,'
        f'"topPaddingTablet":80,"bottomPaddingTablet":80,'
        f'"leftPaddingTablet":32,"rightPaddingTablet":32,'
        f'"topPaddingMobile":64,"bottomPaddingMobile":64,'
        f'"leftPaddingMobile":24,"rightPaddingMobile":24,'
        f'"paddingLink":false,"variationSelected":true,'
        f'"rowGapDesktop":0,"rowGapTablet":80,"rowGapMobile":40,'
        f'"columnGapDesktop":72,"columnGapTablet":40,"columnGapMobile":0,'
        f'"isBlockRootParent":true,'
        f'"linkHoverColor":"var(\\u002d\\u002dast-global-color-7)","equalHeight":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{grid_outer_id} alignfull uagb-is-root-container">'
        f'<div class="uagb-container-inner-blocks-wrap">\n'
        f'<!-- wp:uagb/container {{"block_id":"{grid_inner_id}","widthTablet":100,"directionDesktop":"row",'
        f'"alignItemsDesktop":"flex-start","alignItemsTablet":"stretch","alignItemsMobile":"stretch",'
        f'"justifyContentDesktop":"flex-start","variationSelected":true,'
        f'"rowGapDesktop":40,"rowGapMobile":30,'
        f'"columnGapDesktop":24,"columnGapTablet":20,'
        f'"widthSetByUser":true,"childrenWidthDesktop":"equal",'
        f'"layout":"grid",'
        f'"gridColumnDesktop":[{{"default":"custom","min":{{"unit":"px","value":10}},"max":{{"unit":"fr","value":1}},"custom":{{"unit":"fr","value":1}}}},{{"default":"custom","min":{{"unit":"px","value":10}},"max":{{"unit":"fr","value":1}},"custom":{{"unit":"fr","value":1}}}}]}} -->\n'
        f'<div class="wp-block-uagb-container uagb-layout-grid uagb-block-{grid_inner_id}">\n'
        f'{cards_markup}\n'
        f'</div>\n<!-- /wp:uagb/container -->\n'
        f'{build_sidebar(sidebar_ref)}\n'
        f'</div></div>\n<!-- /wp:uagb/container -->'
    )

    return banner + "\n\n" + grid


# ============================================================
# CONTENT GENERATION ‚Äî Claude API
# ============================================================

CONTENT_RULES = """
Writing rules:
- Location format: always write as "[city], [state]" (with comma) and "in [city], [state]"
- Focus keyword must appear in the first 100 words, written naturally
- Mention the county by name at least once
- No specific numbers, percentages, or brand name claims
- No em dashes (‚Äî). Use commas or periods instead
- No overused AI phrases: crucial, vital, essential, paramount, leverage, delve,
  comprehensive, tailored, seamlessly, robust, furthermore, moreover, additionally,
  "it's worth noting", "in conclusion", "look no further"
- Use simple, direct language a local contractor would actually use
- Vary sentence length ‚Äî mix short punchy sentences with longer ones
- Do NOT include H1 tags. The banner renders the H1.
- All H2 content starts with H2, not H1
"""


def generate_individual_body_content(service, city, state, county, nearby, niche, brand):
    """Call Claude to generate the body text (everything except FAQs) for an
    individual service/city page. Split from FAQ generation (see
    generate_individual_faqs) so the two can be independently locked/unlocked
    without wastefully regenerating one to refresh the other."""

    nearby_list = ", ".join(nearby)
    focus_kw    = f"{service} {city} {state}"

    prompt = f"""You are writing SEO content for a local contractor lead-generation website.

Context:
- Niche: {niche}
- Service: {service}
- City: {city}, {state}
- County: {county}
- Nearby towns: {nearby_list}
- Brand: {brand}
- Focus keyword: "{focus_kw}"

{CONTENT_RULES}

Return a single JSON object with EXACTLY these fields. No markdown, no code blocks, raw JSON only.

{{
  "banner_h1": "Primary H1 for this page. Format: '[Service] in [City], [State]'. Max 60 chars.",
  "banner_subtitle": "1-sentence subtitle under the H1. Descriptive, local, direct. Max 120 chars.",
  "section1_h2": "H2 for 'What is this service and why does it matter in this city'. Be specific. Max 70 chars.",
  "section1_paragraph": "3-4 sentences. Define the service and local relevance. Include focus keyword naturally in first sentence. Mention county.",
  "section1_cta_title": "Short CTA heading. 5-8 words. Action-oriented. Example: 'Ready for a New Fence in {city}?'",
  "section1_cta_desc": "1 sentence supporting the CTA. 15-25 words.",
  "section2_h2": "H2 for 'Our [service] process in [city]'. Be specific. Max 70 chars.",
  "section2_paragraph": "3-4 sentences describing how the work is done. Step-like but flowing prose, not a bullet list.",
  "section2_cta_title": "Short CTA heading about getting started. 5-8 words.",
  "section2_cta_desc": "1 sentence. 15-25 words.",
  "section3_h2": "H2 for 'Why choose us for [service] in [city]'. Be specific. Max 70 chars.",
  "section3_paragraph": "3-4 sentences on what sets this company apart locally. Mention nearby towns.",
  "section3_cta_title": "Short CTA heading. 5-8 words. Urgency or value angle.",
  "section3_cta_desc": "1 sentence. 15-25 words.",
  "service_area_h2": "H2 for service area. Example: '[Service] Service Area in {county}'. Max 70 chars.",
  "service_area_paragraph": "2-3 sentences. Name the primary city, county, and at least 3 nearby towns from the list. Natural, not a list dump."
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1600,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw)


def generate_individual_faqs(service, city, state, county, niche, brand):
    """Call Claude to generate just the FAQ section for an individual
    service/city page — split out from the body content so FAQs can be
    refreshed (e.g. to add a client-supplied detail) without touching, or
    wastefully regenerating, the rest of the page."""

    prompt = f"""You are writing SEO content for a local contractor lead-generation website.

Context:
- Niche: {niche}
- Service: {service}
- City: {city}, {state}
- County: {county}
- Brand: {brand}

{CONTENT_RULES}

Return a single JSON object with EXACTLY these fields. No markdown, no code blocks, raw JSON only.

{{
  "faq_h2": "H2 for FAQ section. Example: 'Frequently Asked Questions About {service} in {city}, {state}'. Max 80 chars.",
  "faqs": [
    {{"question": "Specific local question about {service} in {city}", "answer": "Direct answer. 2-4 sentences."}},
    {{"question": "Question about cost or timeline for {service}", "answer": "Direct answer. 2-4 sentences. No specific dollar amounts."}},
    {{"question": "Question about a common concern or decision point for {service}", "answer": "Direct answer. 2-4 sentences."}},
    {{"question": "Question about service area or who qualifies", "answer": "Direct answer. Mention {city} and {county}. 2-3 sentences."}}
  ]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw)


def generate_city_overview_content(city, state, services, niche, brand):
    """Call Claude to generate all text for a city overview page."""

    svc_list = ", ".join(services)

    prompt = f"""You are writing SEO content for a local contractor lead-generation website.

Context:
- Niche: {niche}
- City: {city}, {state}
- Services offered: {svc_list}
- Brand: {brand}

{CONTENT_RULES}

Return a single JSON object with EXACTLY these fields. No markdown, no code blocks, raw JSON only.

{{
  "banner_h1": "Primary H1 for city overview page. Format: '[Niche] in [City], [State]'. Max 60 chars.",
  "banner_subtitle": "1-sentence subtitle. Positions this as the local expert for all services. Max 120 chars.",
  "service_cards": [
    {{"service": "{services[0] if services else 'Service'}", "description": "2-3 sentences about this specific service in {city}. Local, direct, no fluff."}}
  ]
}}

IMPORTANT: The service_cards array must have exactly {len(services)} items, one for each of these services in order: {svc_list}.
Each description should be 2-3 sentences, specific to {city}, {state}.
"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw)


def generate_seo_meta(focus_keyword, city, state, brand):
    """Generate Rank Math SEO title, meta description, and focus keyword."""
    prompt = f"""Generate SEO meta data for a local service page.

Focus keyword: {focus_keyword}
City: {city}, {state}
Brand: {brand}

Return raw JSON only, no markdown:
{{
  "seo_title": "Max 60 chars. Include keyword + brand. No clickbait.",
  "meta_description": "150-160 chars exactly. Include keyword. Specific and compelling.",
  "focus_keyword": "The primary keyword phrase"
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw)


# ============================================================
# WP-CLI PAGE OPERATIONS
# ============================================================

def get_existing_page_id(title, wp_path):
    """Return existing page ID by title, or None."""
    slug = title.lower().replace(" ", "-").replace(",", "").replace("(", "").replace(")", "")
    try:
        result = wp(
            f"post list --post_type=page --post_status=any "
            f"--name=\"{slug}\" --fields=ID --format=ids",
            wp_path
        )
        if result.strip():
            return result.strip().split()[0]
    except Exception:
        pass
    try:
        result = wp(
            "post list --post_type=page --post_status=any "
            "--fields=ID,post_title --format=json",
            wp_path
        )
        for page in json.loads(result):
            if page["post_title"] == title:
                return str(page["ID"])
    except Exception:
        pass
    return None


def upsert_page(title, content, wp_path, existing_id=None):
    """Create or update a WordPress page. Returns post ID."""
    content_esc = shell_esc(content)
    title_esc   = shell_esc(title)

    if existing_id:
        wp(
            f"post update {existing_id} "
            f"--post_content='{content_esc}' "
            f"--post_status=publish",
            wp_path
        )
        return existing_id
    else:
        return wp(
            f"post create "
            f"--post_title='{title_esc}' "
            f"--post_status=publish "
            f"--post_type=page "
            f"--post_content='{content_esc}' "
            f"--porcelain",
            wp_path
        )


def set_rank_math_meta(post_id, meta, wp_path):
    """Set Rank Math SEO meta fields via WP-CLI post meta."""
    wp(f"post meta update {post_id} rank_math_title \"{meta['seo_title']}\"", wp_path)
    wp(f"post meta update {post_id} rank_math_description \"{meta['meta_description']}\"", wp_path)
    wp(f"post meta update {post_id} rank_math_focus_keyword \"{meta['focus_keyword']}\"", wp_path)


# ============================================================
# PAGE GENERATORS
# ============================================================

def generate_individual_service_page(service, city, state, config, city_data, update=False, dry_run=False,
                                      unlock_body=False, unlock_faqs=False,
                                      unlock_meta_title=False, unlock_meta_description=False,
                                      cache=None, config_path=None):
    """Locked-by-default: body, FAQs, meta title, and meta description are
    each independently protected. A page's already-cached value for an
    element is reused untouched unless that element's unlock flag is passed
    — there is no fresh API call, and nothing changes, unless explicitly
    unlocked. First-time generation (nothing cached yet) always generates,
    regardless of unlock flags — the lock protects existing content, it
    doesn't block creating a page that doesn't exist yet."""
    wp_path = config["wp_path"]
    niche   = config["niche"]
    brand   = config["brand_name"]
    county  = city_data.get("county", "")
    nearby  = city_data.get("nearby", [])

    title       = f"{service} in {city}, {state}"
    focus_kw    = f"{service} {city} {state}"
    existing_id = get_existing_page_id(title, wp_path)

    if dry_run:
        action = "update" if existing_id else "create"
        print(f"  [dry-run] Would {action}: {title}")
        return {"title": title, "action": f"dry-run-{action}"}

    if existing_id and not update:
        warn(f"Skipping (exists, ID {existing_id}): {title}  [use --update to refresh]")
        return {"title": title, "action": "skipped", "post_id": existing_id}

    log(f"{'Updating' if existing_id else 'Creating'}: {title}")

    cached = (cache.get(title) if cache is not None else None) or {}

    # Body
    if unlock_body or "body" not in cached:
        if "body" in cached:
            _save_pre_override_snapshot(config_path, title, "body", cached["body"])
        body = generate_individual_body_content(service, city, state, county, nearby, niche, brand)
    else:
        body = cached["body"]

    # FAQs — independently locked; refreshing one never touches the other
    if unlock_faqs or "faqs" not in cached:
        if "faqs" in cached:
            _save_pre_override_snapshot(config_path, title, "faqs", cached["faqs"])
        faqs = generate_individual_faqs(service, city, state, county, niche, brand)
    else:
        faqs = cached["faqs"]

    # Meta title / description — independently locked from each other and
    # from body/FAQs. One API call covers both fields (cheap either way),
    # but only the unlocked field's fresh value is actually kept.
    need_meta_title = unlock_meta_title or "meta_title" not in cached
    need_meta_desc  = unlock_meta_description or "meta_description" not in cached
    if need_meta_title or need_meta_desc:
        fresh_meta = generate_seo_meta(focus_kw, city, state, brand)
        if need_meta_title:
            if "meta_title" in cached:
                _save_pre_override_snapshot(config_path, title, "meta_title", cached["meta_title"])
            meta_title = fresh_meta["seo_title"]
        else:
            meta_title = cached["meta_title"]
        if need_meta_desc:
            if "meta_description" in cached:
                _save_pre_override_snapshot(config_path, title, "meta_description", cached["meta_description"])
            meta_description = fresh_meta["meta_description"]
        else:
            meta_description = cached["meta_description"]
        focus_keyword = fresh_meta["focus_keyword"]
    else:
        meta_title        = cached["meta_title"]
        meta_description  = cached["meta_description"]
        focus_keyword      = cached.get("focus_keyword", focus_kw)

    if cache is not None and config_path:
        cache[title] = {
            "body": body, "faqs": faqs,
            "meta_title": meta_title, "meta_description": meta_description,
            "focus_keyword": focus_keyword,
        }
        _save_cache(cache, config_path)

    content_data = {**body, **faqs}
    meta         = {"seo_title": meta_title, "meta_description": meta_description, "focus_keyword": focus_keyword}
    page_markup  = build_individual_service_page(content_data, config, service, city, state)

    post_id = upsert_page(title, page_markup, wp_path, existing_id)
    set_rank_math_meta(post_id, meta, wp_path)

    log(f"{'Updated' if existing_id else 'Created'} ID {post_id} ‚Äî kw: {meta['focus_keyword']}")
    return {"title": title, "post_id": post_id, "action": "updated" if existing_id else "created", **meta}


def generate_city_overview_page(city, state, config, city_data, update=False, dry_run=False,
                                 unlock_body=False, unlock_meta_title=False, unlock_meta_description=False,
                                 cache=None, config_path=None):
    """Locked-by-default, same principle as generate_individual_service_page
    (no FAQs on overview pages, so no separate FAQ lock needed here)."""
    wp_path  = config["wp_path"]
    niche    = config["niche"]
    brand    = config["brand_name"]
    services = config["services"]

    niche_short = niche.replace(" Services", "").replace(" Service", "")
    title       = f"{niche_short} Services in {city}, {state}"
    focus_kw    = f"{niche_short.lower()} services {city} {state}"
    existing_id = get_existing_page_id(title, wp_path)

    if dry_run:
        action = "update" if existing_id else "create"
        print(f"  [dry-run] Would {action} (overview): {title}")
        return {"title": title, "action": f"dry-run-{action}"}

    if existing_id and not update:
        warn(f"Skipping (exists, ID {existing_id}): {title}  [use --update to refresh]")
        return {"title": title, "action": "skipped", "post_id": existing_id}

    log(f"{'Updating' if existing_id else 'Creating'} (overview): {title}")

    cached = (cache.get(title) if cache is not None else None) or {}

    if unlock_body or "body" not in cached:
        if "body" in cached:
            _save_pre_override_snapshot(config_path, title, "body", cached["body"])
        body = generate_city_overview_content(city, state, services, niche, brand)
        body["_city"]  = city
        body["_state"] = state
    else:
        body = cached["body"]

    need_meta_title = unlock_meta_title or "meta_title" not in cached
    need_meta_desc  = unlock_meta_description or "meta_description" not in cached
    if need_meta_title or need_meta_desc:
        fresh_meta = generate_seo_meta(focus_kw, city, state, brand)
        if need_meta_title:
            if "meta_title" in cached:
                _save_pre_override_snapshot(config_path, title, "meta_title", cached["meta_title"])
            meta_title = fresh_meta["seo_title"]
        else:
            meta_title = cached["meta_title"]
        if need_meta_desc:
            if "meta_description" in cached:
                _save_pre_override_snapshot(config_path, title, "meta_description", cached["meta_description"])
            meta_description = fresh_meta["meta_description"]
        else:
            meta_description = cached["meta_description"]
        focus_keyword = fresh_meta["focus_keyword"]
    else:
        meta_title        = cached["meta_title"]
        meta_description  = cached["meta_description"]
        focus_keyword      = cached.get("focus_keyword", focus_kw)

    if cache is not None and config_path:
        cache[title] = {
            "body": body,
            "meta_title": meta_title, "meta_description": meta_description,
            "focus_keyword": focus_keyword,
        }
        _save_cache(cache, config_path)

    meta         = {"seo_title": meta_title, "meta_description": meta_description, "focus_keyword": focus_keyword}
    page_markup  = build_city_overview_page(body, services, config)

    post_id = upsert_page(title, page_markup, wp_path, existing_id)
    set_rank_math_meta(post_id, meta, wp_path)

    log(f"{'Updated' if existing_id else 'Created'} ID {post_id} ‚Äî kw: {meta['focus_keyword']}")
    return {"title": title, "post_id": post_id, "action": "updated" if existing_id else "created", **meta}


# ============================================================
# STATIC PAGE BUILDERS
# ============================================================

def _build_two_col_outer(left_col, right_col, bg_color="var(\\u002d\\u002dast-global-color-5)"):
    """Full-width two-column content area (matches individual service page layout)."""
    outer_id = gen_id()
    return (
        f'<!-- wp:uagb/container {{"block_id":"{outer_id}","directionDesktop":"row",'
        f'"directionTablet":"column","alignItemsDesktop":"stretch",'
        f'"alignItemsTablet":"stretch","alignItemsMobile":"stretch",'
        f'"justifyContentDesktop":"flex-start",'
        f'"backgroundType":"color",'
        f'"backgroundColor":"{bg_color}",'
        f'"topPaddingDesktop":112,"bottomPaddingDesktop":112,'
        f'"leftPaddingDesktop":40,"rightPaddingDesktop":40,'
        f'"topPaddingTablet":80,"bottomPaddingTablet":80,'
        f'"leftPaddingTablet":32,"rightPaddingTablet":32,'
        f'"topPaddingMobile":64,"bottomPaddingMobile":64,'
        f'"leftPaddingMobile":24,"rightPaddingMobile":24,'
        f'"paddingLink":false,"variationSelected":true,'
        f'"rowGapDesktop":0,"rowGapTablet":0,"rowGapMobile":40,'
        f'"columnGapDesktop":72,"columnGapTablet":40,"columnGapMobile":0,'
        f'"isBlockRootParent":true,"equalHeight":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{outer_id} alignfull uagb-is-root-container">'
        f'<div class="uagb-container-inner-blocks-wrap">\n'
        f'{left_col}\n{right_col}\n'
        f'</div></div>\n<!-- /wp:uagb/container -->'
    )


def _build_left_col(content, width=65, bg_color=None):
    col_id = gen_id()
    bg_attrs = f'"backgroundType":"color","backgroundColor":"{bg_color}",' if bg_color else ""
    return (
        f'<!-- wp:uagb/container {{"block_id":"{col_id}","widthDesktop":{width},'
        f'"widthTablet":100,"alignItemsTablet":"center","alignItemsMobile":"center",'
        f'"justifyContentDesktop":"flex-start",'
        f'{bg_attrs}'
        f'"topPaddingDesktop":0,"bottomPaddingDesktop":0,'
        f'"leftPaddingDesktop":0,"rightPaddingDesktop":0,'
        f'"topPaddingTablet":0,"bottomPaddingTablet":0,'
        f'"leftPaddingTablet":0,"rightPaddingTablet":0,'
        f'"topPaddingMobile":0,"bottomPaddingMobile":0,'
        f'"leftPaddingMobile":0,"rightPaddingMobile":0,'
        f'"paddingLink":false,"variationSelected":true,'
        f'"rowGapDesktop":24,"rowGapTablet":24,"rowGapMobile":24,'
        f'"columnGapDesktop":0,"widthSetByUser":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{col_id}">\n'
        f'{content}\n'
        f'</div>\n<!-- /wp:uagb/container -->'
    )


def build_about_page(config):
    """Banner + two-column: left=H2+text+contact_block_ref, right=sidebar."""
    brand          = config.get("brand_name", "Our Company")
    niche          = config.get("niche", "Services")
    banner_cta_ref = config.get("banner_cta_ref", 0)
    sidebar_ref    = config.get("sidebar_block_ref", 0)
    contact_ref    = config.get("contact_block_ref", 0)

    banner = build_banner(
        f"About {brand}",
        f"Locally owned and operated {niche} you can trust.",
        banner_cta_ref
    )

    head_id = gen_id()
    left_content = (
        f'<!-- wp:uagb/advanced-heading {{"block_id":"{head_id}","classMigrate":true,'
        f'"headingDescToggle":false}} -->\n'
        f'<div class="wp-block-uagb-advanced-heading uagb-block-{head_id}">'
        f'<h2 class="uagb-heading-text">About {brand}</h2></div>\n'
        f'<!-- /wp:uagb/advanced-heading -->\n'
        f'<!-- wp:paragraph -->\n'
        f'<p>We are a locally owned and operated {niche} company serving homeowners and businesses in the area. '
        f'Our team is committed to fast, reliable service at fair prices. '
        f'Contact us today to schedule service or request a free quote.</p>\n'
        f'<!-- /wp:paragraph -->\n'
        f'<!-- wp:block {{"ref":{contact_ref}}} /-->'
    )

    left_col = _build_left_col(left_content, width=65)
    sidebar  = build_sidebar(sidebar_ref)
    return banner + "\n\n" + _build_two_col_outer(left_col, sidebar)


def build_faq_page(config):
    """Banner + two-column: left=H2+FAQ accordion, right=sidebar."""
    niche          = config.get("niche", "Services")
    banner_cta_ref = config.get("banner_cta_ref", 0)
    sidebar_ref    = config.get("sidebar_block_ref", 0)
    faqs           = config.get("faq_page_faqs", [
        {"question": "What areas do you serve?",
         "answer": "We serve the local area and surrounding communities. Contact us to confirm service to your location."},
        {"question": "How do I request a free quote?",
         "answer": "You can request a free quote by filling out our online form or calling us directly. We typically respond the same business day."},
        {"question": "How quickly can you schedule service?",
         "answer": "We offer flexible scheduling and typically respond to requests within one business day. Emergency service may be available."},
    ])

    banner = build_banner(
        "Frequently Asked Questions",
        f"Common questions about our {niche}.",
        banner_cta_ref
    )

    faq_block = build_faq_block(faqs)
    head_id   = gen_id()
    sep_id    = gen_id()
    left_content = (
        f'<!-- wp:uagb/advanced-heading {{"block_id":"{head_id}","classMigrate":true,'
        f'"headingDescToggle":false}} -->\n'
        f'<div class="wp-block-uagb-advanced-heading uagb-block-{head_id}">'
        f'<h2 class="uagb-heading-text">Your Questions Answered</h2></div>\n'
        f'<!-- /wp:uagb/advanced-heading -->\n'
        f'{faq_block}\n'
        f'{build_uagb_separator(sep_id)}'
    )

    left_col = _build_left_col(left_content, width=65)
    sidebar  = build_sidebar(sidebar_ref)
    return banner + "\n\n" + _build_two_col_outer(left_col, sidebar)


def build_contact_page(config):
    """Banner + two-column: left=contact_block_ref, right=Fluent Form."""
    banner_cta_ref = config.get("banner_cta_ref", 0)
    contact_ref    = config.get("contact_block_ref", 0)
    form_id        = str(config.get("contact_form_id", "1"))

    banner = build_banner(
        "Contact Us",
        "Get in touch for a free quote or to schedule service.",
        banner_cta_ref
    )

    left_content  = f'<!-- wp:block {{"ref":{contact_ref}}} /-->'

    form_head_id  = gen_id()
    right_content = (
        f'<!-- wp:uagb/advanced-heading {{"block_id":"{form_head_id}","classMigrate":true,'
        f'"headingDescToggle":false}} -->\n'
        f'<div class="wp-block-uagb-advanced-heading uagb-block-{form_head_id}">'
        f'<h2 class="uagb-heading-text">How can we help?</h2></div>\n'
        f'<!-- /wp:uagb/advanced-heading -->\n'
        f'<!-- wp:fluentfom/guten-block {{"formId":"{form_id}"}} /-->'
    )

    # Section background sits under the banner (#F2F5F7); the form's own
    # column is a white card standing out on top of it (#FFFFFF). Page body
    # background is left at the theme default (already white).
    left_col  = _build_left_col(left_content, width=45)
    right_col = _build_left_col(right_content, width=50, bg_color="#FFFFFF")
    return banner + "\n\n" + _build_two_col_outer(left_col, right_col, bg_color="#F2F5F7")


# ============================================================
# STATIC PAGE GENERATOR
# ============================================================

# ============================================================
# LANDING PAGE BUILDERS (Service Areas + Services)
# ============================================================

def _build_landing_card(icon, heading, desc, link, icon_color=None):
    """Single icon card: colored icon bg + info-box h3 + Learn More button."""
    card_id      = gen_id()
    icon_cont_id = gen_id()
    infobox_id   = gen_id()
    buttons_id   = gen_id()
    btn_child_id = gen_id()
    _ic = icon_color if icon_color else 'var:preset|color|ast-global-color-0'
    _cs = f',"color":{{"text":"{icon_color}"}}' if icon_color else ''
    _tc = '' if icon_color else ',"textColor":"ast-global-color-0"'
    return (
        f'<!-- wp:uagb/container {{"block_id":"{card_id}","widthDesktop":33,"widthTablet":31,'
        f'"alignItemsDesktop":"flex-start","justifyContentDesktop":"flex-start",'
        f'"backgroundType":"color","backgroundColor":"var(\\u002d\\u002dast-global-color-5)",'
        f'"boxShadowColor":"rgba(0,0,0,0.1)","boxShadowVOffset":4,"boxShadowBlur":8,'
        f'"boxShadowSpread":6,'
        f'"topPaddingDesktop":20,"bottomPaddingDesktop":20,'
        f'"leftPaddingDesktop":20,"rightPaddingDesktop":20,'
        f'"topPaddingTablet":16,"bottomPaddingTablet":16,'
        f'"leftPaddingTablet":16,"rightPaddingTablet":16,'
        f'"topPaddingMobile":16,"bottomPaddingMobile":16,'
        f'"leftPaddingMobile":16,"rightPaddingMobile":16,'
        f'"variationSelected":true,"rowGapDesktop":24,"rowGapTablet":24,"rowGapMobile":20,'
        f'"columnGapDesktop":0,"widthSetByUser":true,'
        f'"containerBorderTopLeftRadius":6,"containerBorderTopRightRadius":6,'
        f'"containerBorderBottomLeftRadius":6,"containerBorderBottomRightRadius":6,'
        f'"layout":"flex","isGridCssInParent":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-layout-flex uagb-block-{card_id}">'
        f'<!-- wp:uagb/container {{"block_id":"{icon_cont_id}",'
        f'"backgroundType":"color","backgroundColor":"var(\\u002d\\u002dast-global-color-4)",'
        f'"containerBorderTopWidth":1,"containerBorderLeftWidth":1,'
        f'"containerBorderRightWidth":1,"containerBorderBottomWidth":1,'
        f'"containerBorderStyle":"solid",'
        f'"containerBorderColor":"var(\\u002d\\u002dast-global-color-5)"}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{icon_cont_id}">'
        f'<!-- wp:icon {{"icon":"{icon}","align":"center",'
        f'"style":{{"dimensions":{{"width":"124px"}},'
        f'"elements":{{"link":{{"color":{{"text":"{_ic}"}}}}}},'
        f'"border":{{"radius":{{"topLeft":"12px","topRight":"12px",'
        f'"bottomLeft":"12px","bottomRight":"12px"}}}}{_cs}}}'
        f'{_tc}}} /-->\n'
        f'</div>\n<!-- /wp:uagb/container -->\n'
        f'<!-- wp:uagb/info-box {{"classMigrate":true,"tempHeadingDesc":"Abcd",'
        f'"headingAlign":"left",'
        f'"headingColor":"var(\\u002d\\u002dast-global-color-2)",'
        f'"subHeadingColor":"var(\\u002d\\u002dast-global-color-3)",'
        f'"headSpace":16,"subHeadSpace":4,"block_id":"{infobox_id}",'
        f'"imageWidth":120,"showIcon":false,'
        f'"headTopMargin":0,"headRightMargin":0,"headLeftMargin":0,'
        f'"headMarginTopTablet":0,"headMarginRightTablet":0,'
        f'"headTabletSpace":16,"headMarginLeftTablet":0,'
        f'"headMarginTopMobile":0,"headMarginRightMobile":0,'
        f'"headMobileSpace":12,"headMarginLeftMobile":0,'
        f'"blockTopPaddingTablet":0,"blockRightPaddingTablet":0,'
        f'"blockLeftPaddingTablet":0,"blockBottomPaddingTablet":0,'
        f'"subHeadTopMargin":0,"subHeadRightMargin":0,"subHeadLeftMargin":0,'
        f'"subHeadMarginTopTablet":0,"subHeadMarginRightTablet":0,'
        f'"subHeadTabletSpace":0,"subHeadMarginLeftTablet":0,'
        f'"subHeadMarginTopMobile":0,"subHeadMarginRightMobile":0,'
        f'"subHeadMobileSpace":0,"subHeadMarginLeftMobile":0,'
        f'"btnBorderTopWidth":1,"btnBorderLeftWidth":1,'
        f'"btnBorderRightWidth":1,"btnBorderBottomWidth":1,'
        f'"btnBorderTopLeftRadius":0,"btnBorderTopRightRadius":0,'
        f'"btnBorderBottomLeftRadius":0,"btnBorderBottomRightRadius":0,'
        f'"btnBorderStyle":"solid","btnBorderColor":"#333"}} -->\n'
        f'<div class="uagb-block-{infobox_id} uagb-infobox__content-wrap'
        f'  uagb-infobox-icon-above-title uagb-infobox-image-valign-top ">'
        f'<div class="uagb-ifb-content"><div class="uagb-ifb-title-wrap">'
        f'<h3 class="uagb-ifb-title">{heading}</h3></div>'
        f'<p class="uagb-ifb-desc">{desc}</p></div></div>\n'
        f'<!-- /wp:uagb/info-box -->\n'
        f'<!-- wp:uagb/buttons {{"block_id":"{buttons_id}","classMigrate":true,'
        f'"childMigrate":true,"align":"left","alignTablet":"left","alignMobile":"left","gap":0}} -->\n'
        f'<div class="wp-block-uagb-buttons uagb-buttons__outer-wrap'
        f' uagb-btn__default-btn uagb-btn-tablet__default-btn uagb-btn-mobile__default-btn'
        f' uagb-block-{buttons_id}"><div class="uagb-buttons__wrap uagb-buttons-layout-wrap ">'
        f'<!-- wp:uagb/buttons-child {{"block_id":"{btn_child_id}","label":"Learn More",'
        f'"link":"{link}",'
        f'"topPadding":7,"rightPadding":10,"bottomPadding":7,"leftPadding":13,'
        f'"paddingLink":false,"color":"#ffffff",'
        f'"hColor":"var(\\u002d\\u002dast-global-color-1)",'
        f'"hBackground":"var(\\u002d\\u002dast-global-color-7)",'
        f'"icon":"chevron-right","topMargin":0,"rightMargin":0,"bottomMargin":0,"leftMargin":0,'
        f'"iconColor":"var(\\u002d\\u002dast-global-color-5)",'
        f'"iconHColor":"var(\\u002d\\u002dast-global-color-1)",'
        f'"btnBorderTopWidth":1,"btnBorderLeftWidth":1,'
        f'"btnBorderRightWidth":1,"btnBorderBottomWidth":1,'
        f'"btnBorderTopLeftRadius":30,"btnBorderTopRightRadius":30,'
        f'"btnBorderBottomLeftRadius":30,"btnBorderBottomRightRadius":30,'
        f'"btnBorderStyle":"solid","btnBorderColor":"#333",'
        f'"btnBorderHColor":"#333","showIcon":true}} -->\n'
        f'<div class="wp-block-uagb-buttons-child uagb-buttons__outer-wrap'
        f' uagb-block-{btn_child_id} wp-block-button">'
        f'<div class="uagb-button__wrapper">'
        f'<a class="uagb-buttons-repeater wp-block-button__link"'
        f' aria-label="" href="{link}" rel="follow noopener" target="_self" role="button">'
        f'<div class="uagb-button__link">Learn More</div>'
        f'<span class="uagb-button__icon uagb-button__icon-position-after">'
        f'<svg xmlns="https://www.w3.org/2000/svg" viewBox="0 0 320 512"'
        f' aria-hidden="true" focussable="false">'
        f'<path d="M96 480c-8.188 0-16.38-3.125-22.62-9.375c-12.5-12.5-12.5-32.75 0-45.25'
        f'L242.8 256L73.38 86.63c-12.5-12.5-12.5-32.75 0-45.25s32.75-12.5 45.25 0'
        f'l192 192c12.5 12.5 12.5 32.75 0 45.25l-192 192'
        f'C112.4 476.9 104.2 480 96 480z"></path>'
        f'</svg></span></a></div></div>\n'
        f'<!-- /wp:uagb/buttons-child -->'
        f'</div></div>\n<!-- /wp:uagb/buttons -->'
        f'</div>\n<!-- /wp:uagb/container -->'
    )


def _build_card_grid(cards_markup):
    """2-column card grid container (auto width on desktop, 100% on tablet)."""
    col_id = gen_id()
    return (
        f'<!-- wp:uagb/container {{"block_id":"{col_id}","widthTablet":100,'
        f'"directionDesktop":"row","alignItemsDesktop":"flex-start",'
        f'"alignItemsTablet":"stretch","alignItemsMobile":"stretch",'
        f'"justifyContentDesktop":"flex-start","variationSelected":true,'
        f'"rowGapDesktop":40,"rowGapMobile":30,'
        f'"columnGapDesktop":24,"columnGapTablet":20,'
        f'"widthSetByUser":true,"childrenWidthDesktop":"equal",'
        f'"layout":"grid",'
        f'"gridColumnDesktop":['
        f'{{"default":"custom","min":{{"unit":"px","value":10}},'
        f'"max":{{"unit":"fr","value":1}},"custom":{{"unit":"fr","value":1}}}},'
        f'{{"default":"custom","min":{{"unit":"px","value":10}},'
        f'"max":{{"unit":"fr","value":1}},"custom":{{"unit":"fr","value":1}}}}'
        f']}} -->\n'
        f'<div class="wp-block-uagb-container uagb-layout-grid uagb-block-{col_id}">\n'
        f'{cards_markup}\n'
        f'</div>\n<!-- /wp:uagb/container -->'
    )


def _build_landing_outer(left_col, right_col):
    """Full-width two-column outer for landing pages (rowGapTablet:80, linkHoverColor)."""
    outer_id = gen_id()
    return (
        f'<!-- wp:uagb/container {{"block_id":"{outer_id}","directionDesktop":"row",'
        f'"directionTablet":"column","alignItemsDesktop":"stretch",'
        f'"alignItemsTablet":"stretch","alignItemsMobile":"stretch",'
        f'"justifyContentDesktop":"flex-start",'
        f'"backgroundType":"color",'
        f'"backgroundColor":"var(\\u002d\\u002dast-global-color-5)",'
        f'"topPaddingDesktop":112,"bottomPaddingDesktop":112,'
        f'"leftPaddingDesktop":40,"rightPaddingDesktop":40,'
        f'"topPaddingTablet":80,"bottomPaddingTablet":80,'
        f'"leftPaddingTablet":32,"rightPaddingTablet":32,'
        f'"topPaddingMobile":64,"bottomPaddingMobile":64,'
        f'"leftPaddingMobile":24,"rightPaddingMobile":24,'
        f'"paddingLink":false,"variationSelected":true,'
        f'"rowGapDesktop":0,"rowGapTablet":80,"rowGapMobile":40,'
        f'"columnGapDesktop":72,"columnGapTablet":40,"columnGapMobile":0,'
        f'"isBlockRootParent":true,'
        f'"linkHoverColor":"var(\\u002d\\u002dast-global-color-7)",'
        f'"equalHeight":true}} -->\n'
        f'<div class="wp-block-uagb-container uagb-block-{outer_id}'
        f' alignfull uagb-is-root-container">'
        f'<div class="uagb-container-inner-blocks-wrap">\n'
        f'{left_col}\n{right_col}\n'
        f'</div></div>\n<!-- /wp:uagb/container -->'
    )


# Icon map keyed on service slug (service.lower().replace(" ", "-").replace(",", ""))
_SERVICE_ICONS = {
    "drain-cleaning":          "core/tools",
    "clogged-drain-repair":    "core/settings",
    "hydro-jetting":           "core/cloud",
    "sewer-drain-cleaning":    "core/search",
    "emergency-drain-service": "core/warning",
    "main-drain-cleaning":     "core/home",
    "kitchen-drain-cleaning":  "core/filter",
    # extras for other niches
    "drain-repair":            "core/settings",
    "sewer-line-services":     "core/search",
    "grease-trap-cleaning":    "core/trash",
    "floor-drain-services":    "core/grid-view",
    "sump-pump-services":      "core/cloud",
    "pipe-repair":             "core/settings",
    "trenchless-repair":       "core/map-marker",
    "camera-inspection":       "core/search",
}
_SERVICE_ICON_DEFAULT = "core/star-filled"


def build_service_areas_page(config):
    """Card grid of all cities — one card per city linking to its overview page."""
    niche          = config.get("niche", "Services")
    niche_short    = niche.replace(" Services", "").replace(" Service", "")
    niche_slug     = niche_short.lower().replace(" ", "-")
    primary_city   = config.get("primary_city", "")
    primary_state  = config.get("primary_state", "")
    cities         = config.get("cities", [])
    banner_cta_ref = config.get("banner_cta_ref", 0)
    sidebar_ref    = config.get("sidebar_block_ref", 0)

    banner = build_banner(
        "Service Areas",
        f"Serving {primary_city}, {primary_state} and the surrounding region.",
        banner_cta_ref
    )

    # Primary city first, then alphabetical
    sorted_cities = sorted(cities, key=lambda c: (0 if c.get("is_primary") else 1, c["city"]))
    cards = []
    for city_data in sorted_cities:
        city       = city_data["city"]
        state      = city_data["state"]
        city_slug  = city.lower().replace(" ", "-").replace(".", "")
        state_slug = state.lower()
        url        = f"/{niche_slug}-services-in-{city_slug}-{state_slug}/"
        desc       = f"{niche_short} services in {city}, {state} and surrounding communities."
        cards.append(_build_landing_card("core/map-marker", city, desc, url, icon_color="#bdc9d1"))

    grid    = _build_card_grid("\n".join(cards))
    sidebar = build_sidebar(sidebar_ref)
    return banner + "\n\n" + _build_landing_outer(grid, sidebar)


def build_services_page(config):
    """Card grid of all services — one card per service with per-service icon."""
    niche          = config.get("niche", "Services")
    niche_short    = niche.replace(" Services", "").replace(" Service", "")
    primary_city   = config.get("primary_city", "")
    primary_state  = config.get("primary_state", "")
    services       = config.get("services", [])
    banner_cta_ref = config.get("banner_cta_ref", 0)
    sidebar_ref    = config.get("sidebar_block_ref", 0)
    svc_descs      = config.get("service_card_descs", {})
    img_base       = config.get("rar_image_base", "")
    service_images = config.get("service_images", {})
    city_slug      = f"{primary_city.lower().replace(' ', '-')}-{primary_state.lower()}"

    banner = build_banner(
        f"{niche_short} Services",
        f"Professional {niche_short.lower()} services in {primary_city}, {primary_state}.",
        banner_cta_ref
    )

    cards = []
    for svc in services:
        svc_slug = svc.lower().replace(" ", "-").replace(",", "")
        url      = f"/{svc_slug}-in-{city_slug}/"
        rect_file = service_images.get(svc_slug, {}).get("rect", "")
        img_url   = img_base + rect_file if rect_file else ""
        alt_text  = f"{svc} {primary_city} {primary_state}"
        desc      = svc_descs.get(svc) or (
            f"Professional {svc.lower()} serving {primary_city}, {primary_state}"
            f" and the surrounding area."
        )
        cards.append(build_service_card(svc, desc, url, img_url, alt_text,
                                         use_kadence=config.get("use_kadence", False)))

    grid    = _build_card_grid("\n".join(cards))
    sidebar = build_sidebar(sidebar_ref)
    return banner + "\n\n" + _build_landing_outer(grid, sidebar)









# ─── Homepage section builders (template-based — see templates/homepage.html)

"""
Homepage builder — template-based, loads templates/homepage.html from agency-toolkit.
All _hp_* section builders below are superseded by build_homepage() but kept for reference.
"""
import re, os


# ── Unicode escape decoder ─────────────────────────────────────────────────────

def _decode_safe_unicode_escapes(s):
    """
    Decode \\uXXXX JSON escapes that wp_insert_post would strip (breaking CSS vars).
    Skips \\u0022 (\") and \\u005c (\\) which would break JSON structure.
    """
    def _replace(m):
        code = m.group(1).lower()
        if code in ('0022', '005c'):  # " and \ — keep escaped
            return m.group(0)
        return chr(int(code, 16))
    return re.sub(r'\\u([0-9a-fA-F]{4})', _replace, s)


# ── Config helpers ─────────────────────────────────────────────────────────────

def _cfg_state_abbr(cfg):
    return cfg.get("state_abbr", "")

def _cfg_state_full(cfg):
    return cfg.get("state_full", cfg.get("state_abbr", ""))


# ── Homepage builder (template-based) ─────────────────────────────────────────

def build_homepage(cfg, wp_path):
    """
    Loads templates/homepage.html, applies config substitutions, and pushes
    the result to the homepage (page ID 66 or cfg['homepage_id']).
    """
    toolkit   = "/var/www/agency-toolkit"
    tmpl_path = os.path.join(toolkit, "templates", "homepage.html")

    with open(tmpl_path, "r") as f:
        content = f.read()

    # Decode JSON unicode escapes before pushing — wp_insert_post strips backslashes
    # via wp_unslash(), turning - → u002d (invalid CSS). Decode first so only
    # real characters reach WordPress.
    content = _decode_safe_unicode_escapes(content)

    # ── Config vars ────────────────────────────────────────────────────────────
    city       = cfg["primary_city"]
    state_abbr = cfg.get("state_abbr", cfg.get("primary_state", ""))
    city_slug  = city.lower().replace(" ", "-")
    state_slug = state_abbr.lower()
    phone      = cfg.get("phone", "(000) 000-0000")
    phone_tel  = re.sub(r"\D", "", phone)
    biz_name   = cfg.get("business_name", f"{city} Drain Cleaning")
    svc_name   = cfg.get("primary_service_name", "Drain Cleaning")
    rar_base   = cfg.get("rar_image_base", "")
    site_url   = re.sub(r"/wp-content/.*$", "", rar_base).rstrip("/") if rar_base else cfg.get("site_url", "")

    # Normalize services to list of dicts with slug key
    raw_services = cfg.get("services", [])
    services = []
    for svc in raw_services:
        if isinstance(svc, dict):
            services.append(svc)
        else:
            services.append({"slug": str(svc).lower().replace(" ", "-"), "name": str(svc)})

    # ── 1. Domain (covers all image URLs and media library refs) ──────────────
    content = content.replace("https://rar01-1vyi.1wp.site", site_url)

    # ── 1.5. Homepage image slots ──────────────────────────────────────────────
    # Replaces placeholder images with /rar/ slot images for each niche.
    # niche_slug derived from primary_service_name: "Drain Cleaning" → "drain-cleaning"
    niche_slug = svc_name.lower().replace(" ", "-")
    old_base   = f"{site_url}/wp-content/uploads/2026/07"

    # Hero background — replace all WP-sized variants; careful to exclude -2 variants
    hero_old = f"{old_base}/placeholder-image-rectangle"
    hero_new = f"{rar_base}home-hero-{niche_slug}-01.jpg"
    for sfx in (".png", "-1024x683.png", "-300x200.png", "-150x150.png"):
        content = content.replace(f"{hero_old}{sfx}", hero_new)

    # Summary section image — core wp:image block in 'Drain Cleaning Services Near You'
    # Uses same placeholder as about/trust-badges but is a separate core block (id 63).
    _old_summary_img  = f"{old_base}/placeholder-image-rectangle-2-1024x683.png"
    _old_summary_blk  = (
        '<!-- wp:image {"id":63,"sizeSlug":"large","linkDestination":"none"} -->\n'
        '<figure class="wp-block-image size-large">'
        f'<img src="{_old_summary_img}" alt="" class="wp-image-63"/></figure>\n'
        '<!-- /wp:image -->'
    )
    _new_summary_blk  = (
        '<!-- wp:image {"sizeSlug":"large","linkDestination":"none"} -->\n'
        '<figure class="wp-block-image size-large">'
        f'<img src="{rar_base}home-summary-{niche_slug}-01.jpg" alt=""/></figure>\n'
        '<!-- /wp:image -->'
    )
    content = content.replace(_old_summary_blk, _new_summary_blk, 1)

    # About section image — target only block 18d94f78 (not the 4 trust badge blocks
    # which share the same placeholder; those stay as-is until trust badge images are ready)
    about_marker = '<!-- wp:uagb/image {"block_id":"18d94f78"'
    about_start  = content.find(about_marker)
    if about_start >= 0:
        _end_tag  = "<!-- /wp:uagb/image -->"
        about_end = content.find(_end_tag, about_start) + len(_end_tag)
        chunk = content[about_start:about_end]
        chunk = chunk.replace(
            f"{old_base}/placeholder-image-rectangle-2",
            f"{rar_base}home-about-{niche_slug}-01"
        )
        # Fix extension: the new file is .jpg, sized variants now share the same .jpg
        chunk = chunk.replace(
            f"home-about-{niche_slug}-01-1024x683.png", f"home-about-{niche_slug}-01.jpg"
        )
        chunk = chunk.replace(
            f"home-about-{niche_slug}-01.png", f"home-about-{niche_slug}-01.jpg"
        )
        content = content[:about_start] + chunk + content[about_end:]

    # Parallax background — replace all WP-sized variants
    parallax_old = f"{old_base}/placeholder-wide-narrow-2"
    parallax_new = f"{rar_base}home-parallax-{niche_slug}-01.jpg"
    for sfx in (".jpg", "-1024x478.jpg", "-300x140.jpg", "-150x150.jpg"):
        content = content.replace(f"{parallax_old}{sfx}", parallax_new)

    # ── 2. Hero ────────────────────────────────────────────────────────────────
    content = content.replace(
        "Professional Drain Cleaning in Louisville, KY",
        f"Professional {svc_name} in {city}, {state_abbr}"
    )
    content = content.replace(
        "Fast, reliable drain cleaning services for homeowners and businesses "
        "in Louisville and surrounding areas. Available 24/7 for emergencies.",
        f"Fast, reliable {svc_name.lower()} services for homeowners and businesses "
        f"in {city} and surrounding areas. Available 24/7 for emergencies."
    )
    content = content.replace("(000) 000-0000", phone)
    content = content.replace("tel:10000000000", f"tel:1{phone_tel}")

    # ── 3. Credentials bar ────────────────────────────────────────────────────
    content = content.replace(
        "KY Licensed Contractor • Fully Bonded &amp; Insured",
        f"{city}'s Trusted {svc_name} Service • 24/7 Emergency Response"
    )

    # ── 4. About section ──────────────────────────────────────────────────────
    content = content.replace(
        "Your Local Drain Cleaning Experts",
        f"Your Local {svc_name} Experts"
    )
    # Handle both curly and straight apostrophes
    for apos in ["’", "'"]:
        content = content.replace(
            f"Louisville Drain Cleaning is Louisville{apos}s trusted source for professional drain cleaning services.",
            f"{biz_name} is {city}{apos}s trusted source for professional {svc_name.lower()} services."
        )
    content = content.replace(
        "throughout Louisville, KY and surrounding communities",
        f"throughout {city}, {state_abbr} and surrounding communities"
    )

    # ── 4b. Parallax section — full sentence rewritten in section 9 below ──────
    # (city-only substring replace removed; see "── 9. Parallax CTA" for the
    # complete, niche-aware replacement — leaving the partial replace here would
    # consume half the sentence before section 9 can match the whole thing)

    # ── 5/7. Service cards — title, description, and image (config-driven) ────
    # The template hardcodes all 7 cards to the original drain services: only
    # the image URL and link (section 6) were ever swapped per-niche, so a
    # non-drain site previously shipped with correct images/links but literal
    # drain-cleaning titles and descriptions. Walk the cards in file order,
    # anchored on each card's placeholder image (reliably unique to this
    # section), and rewrite title + description together with the image so
    # all three always agree.
    drain_img   = f"{site_url}/wp-content/uploads/rar/rect-drain-cleaning.jpg"
    title_open  = '<h3 class="uagb-ifb-title">'
    desc_open   = '<p class="uagb-ifb-desc">'
    tempdesc_kv = '"tempHeadingDesc":"'
    # Start right at the first card's own image block, not document position 0 —
    # the hero and 4 trust badges each have their own tempHeadingDesc/title
    # markup earlier in the page, and an anchor search starting at 0 would
    # lock onto the hero's tempHeadingDesc instead of card 1's.
    _pos = content.find(drain_img)
    if _pos == -1:
        _pos = 0
    for svc in services:
        slug      = svc.get("slug", "")
        svc_label = svc.get("name", slug.replace("-", " ").title())
        svc_lower = svc_label.lower()
        # avoid "Commercial Gutter Services services in ..." when the config
        # name already ends in "service"/"services"
        tail_word = "" if svc_lower.endswith("service") or svc_lower.endswith("services") else " services"
        new_img   = f"{rar_base}rect-{slug}.jpg"
        new_desc  = (
            f"Professional {svc_lower}{tail_word} in {city}, {state_abbr}. "
            "Fast, reliable, and affordable."
        )

        # Image block — verified (all 7 cards, identical structure) to contain
        # exactly this sequence: 3 JSON URL attrs (url/urlTablet/urlMobile),
        # then the JSON title attr, then 4 more URL occurrences (3 srcset
        # variants + rendered src), then the rendered title attr. The JSON
        # title attr sits BETWEEN two groups of URL occurrences, so a plain
        # "sweep all URLs, then look for title" approach skips past it — the
        # URL search jumps straight to the next URL match on the far side of
        # the title attr, without ever landing on the title text itself.
        # Processing the exact known sequence in order avoids that.
        card_ops = (
            [(drain_img, new_img)] * 3
            + [('"title":"Drain Cleaning"', f'"title":"{svc_label}"')]
            + [(drain_img, new_img)] * 4
            + [('title="Drain Cleaning"', f'title="{svc_label}"')]
        )
        for old, new in card_ops:
            idx = content.find(old, _pos)
            if idx == -1:
                continue  # tolerate template drift rather than hard-fail
            content = content[:idx] + new + content[idx + len(old):]
            _pos = idx + len(new)

        # tempHeadingDesc — the info-box block's cached JSON copy of the
        # description. Must be kept in sync with the rendered <p> below, or
        # reopening this block in the Gutenberg editor re-syncs the old
        # drain-cleaning text back into the page from this stale attribute.
        td_start = content.find(tempdesc_kv, _pos)
        if td_start >= 0:
            v_start = td_start + len(tempdesc_kv)
            v_end   = content.find('"', v_start)
            content = content[:v_start] + new_desc + content[v_end:]
            _pos = v_start + len(new_desc)

        # Title — first title tag at/after this card's image
        t_start = content.find(title_open, _pos)
        if t_start >= 0:
            t_text_start = t_start + len(title_open)
            t_text_end   = content.find("</h3>", t_text_start)
            content = content[:t_text_start] + svc_label + content[t_text_end:]
            _pos = t_text_start + len(svc_label)

        # Description — rendered <p> (replaces the entire original text,
        # including the "Clogged Drain Repair<br>..." duplicate-title case,
        # so no separate special-case is needed)
        d_start = content.find(desc_open, _pos)
        if d_start >= 0:
            d_text_start = d_start + len(desc_open)
            d_text_end   = content.find("</p>", d_text_start)
            content = content[:d_text_start] + new_desc + content[d_text_end:]
            _pos = d_text_start + len(new_desc)

    # ── 6. Service card links — replace "#" in config service order ───────────
    for svc in services:
        slug = svc.get("slug", "")
        link = f"/{slug}-in-{city_slug}-{state_slug}/"
        content = content.replace('"link":"#"', f'"link":"{link}"', 1)
        content = content.replace('href="#"', f'href="{link}"', 1)

    # ── 8. How It Works — fix step 2 (duplicate of step 1) ───────────────────
    anchor = "uagb-block-335d5f77"
    pos    = content.find(anchor)
    if pos >= 0:
        tail = content[pos:]
        tail = tail.replace(
            '<h4 class="wp-block-heading has-text-align-center">Call or Request Online</h4>',
            '<h4 class="wp-block-heading has-text-align-center">We Arrive &amp; Diagnose</h4>',
            1
        )
        for em in ["—", "--"]:
            tail = tail.replace(
                f"Contact us any time {em} we’re available 24/7. "
                "Tell us about your drain cleaning problem and we’ll schedule a fast visit.",
                f"A {svc_name.lower()} expert arrives at your door fast, pinpoints the exact cause "
                f"of the problem, and walks you through the solution {em} no surprises.",
                1
            )
            tail = tail.replace(
                f"Contact us any time {em} we're available 24/7. "
                "Tell us about your drain cleaning problem and we'll schedule a fast visit.",
                f"A {svc_name.lower()} expert arrives at your door fast, pinpoints the exact cause "
                f"of the problem, and walks you through the solution {em} no surprises.",
                1
            )
        content = content[:pos] + tail

    # ── 8b. How It Works — step 1 text (niche-generic; must run AFTER section 8,
    # since step 1 and step 2 start out as identical text and section 8 needs
    # the original duplicate intact to tell step 2 apart) ──────────────────────
    for em in ["—", "--"]:
        for apos in ["’", "'"]:
            content = content.replace(
                f"Contact us any time {em} we{apos}re available 24/7. "
                f"Tell us about your drain cleaning problem and we{apos}ll schedule a fast visit.",
                f"Contact us any time {em} we{apos}re available 24/7. "
                f"Tell us about your {svc_name.lower()} problem and we{apos}ll schedule a fast visit.",
                1
            )

    # ── 8c. How It Works — step 3 and section intro ───────────────────────────
    content = content.replace(
        "We clear the blockage, walk you through what we found, and clean up before we leave.",
        "We get the job done, walk you through what we found, and clean up before we leave."
    )
    for apos in ["’", "'"]:
        content = content.replace(
            f"Getting your drains fixed is simple — here{apos}s what to expect when you call us.",
            f"Getting the help you need is simple — here{apos}s what to expect when you call us."
        )

    # ── 8d. Trust badges — 3 of the 4 have drain-specific descriptions ────────
    content = content.replace(
        "Available today for drain cleaning, repairs, and emergency calls.",
        f"Available today for {svc_name.lower()}, repairs, and emergency calls."
    )
    for apos in ["’", "'"]:
        content = content.replace(
            f"Drain emergencies don{apos}t keep business hours — neither do we.",
            f"{svc_name} emergencies don{apos}t keep business hours — neither do we."
        )
    content = content.replace(
        "We arrive quickly and resolve your drain cleaning problem right the first time.",
        f"We arrive quickly and resolve your {svc_name.lower()} problem right the first time."
    )

    # ── 8e. About section — second paragraph (drops drain-specific examples) ──
    for apos in ["’", "'"]:
        content = content.replace(
            f"We use the latest equipment and proven techniques to diagnose and resolve "
            f"drainage problems fast. Whether it{apos}s a backed-up kitchen sink or a main "
            f"line blockage, we{apos}re here to help.",
            f"We use the latest equipment and proven techniques to get the job done right "
            f"the first time. No matter the size of the job, we{apos}re here to help."
        )

    # ── 8f. Parallax CTA — full heading + sentence (replaces the old partial
    # "local drain experts who know Louisville" substring replace) ────────────
    content = content.replace("Get It Fixed Today.", "Get Started Today.")
    content = content.replace(
        "Same-day service from local drain experts who know Louisville. Fast response, "
        "upfront pricing, and no runaround. Just the drain solution you need.",
        f"Same-day service from local {svc_name.lower()} experts who know {city}. Fast "
        f"response, upfront pricing, and no runaround. Just the {svc_name.lower()} "
        "solution you need."
    )



    # ── 10. Service areas map embed ───────────────────────────────────────────
    map_embed = cfg.get("google_maps_embed", "")
    if not map_embed:
        city_enc  = city.replace(" ", "+")
        map_embed = f"https://maps.google.com/maps?q={city_enc}+{state_slug}&output=embed"
    map_html = (
        f'<iframe src="{map_embed}" width="100%" height="400" '
        f'style="border:0;" allowfullscreen="" loading="lazy" '
        f'referrerpolicy="no-referrer-when-downgrade"></iframe>'
    )
    content = content.replace("<p>Hello</p>", map_html)

    # ── 11. Service areas headings / text ─────────────────────────────────────
    content = content.replace(
        "Serving Louisville, KY and Surrounding Areas",
        f"Serving {city}, {state_abbr} and Surrounding Areas"
    )
    content = content.replace(
        "Drain Cleaning Services Near You",
        f"{svc_name} Services Near You"
    )
    content = content.replace(
        "We proudly serve Louisville and communities throughout KY.",
        f"We proudly serve {city} and communities throughout {state_abbr}."
    )

    # ── 12. Push to WordPress via eval-file (avoids shell quoting issues) ─────
    page_id  = cfg.get("homepage_id", 66)
    import os as _os
    _pid = _os.getpid()
    tmp_html = f"/tmp/hp-content-{_pid}.html"
    tmp_php  = f"/tmp/hp-update-{_pid}.php"

    with open(tmp_html, "w") as f:
        f.write(content)

    php = (
        "<?php\n"
        # Ensure Spectra can write its CSS files (directory may not exist on new sites)
        "$upload = wp_upload_dir();\n"
        "$uagb_dir = $upload['basedir'] . '/uagb-blocks';\n"
        "if (!is_dir($uagb_dir)) { wp_mkdir_p($uagb_dir); }\n"
        f"$content = file_get_contents('{tmp_html}');\n"
        # Use $wpdb->update() instead of wp_update_post() to bypass wp_unslash(),
        # which strips backslashes from \uXXXX sequences inside JSON block attributes,
        # corrupting CSS variable names like --ast-global-color-N → u002du002dast-global-color-N.
        "global $wpdb;\n"
        f"$result = $wpdb->update($wpdb->posts, ['post_content' => $content, 'post_status' => 'publish'], ['ID' => {page_id}], ['%s', '%s'], ['%d']);\n"
        "if ($result === false) { echo '[!] DB error: ' . $wpdb->last_error . \"\\n\"; }\n"
        f"else {{ echo '[✓] Homepage (ID {page_id}) updated.' . \"\\n\"; }}\n"
    )
    with open(tmp_php, "w") as f:
        f.write(php)

    result = wp(f"eval-file {tmp_php}", wp_path)
    if result and result.strip():
        log(result.strip())

    # Trigger Spectra CSS regeneration for the homepage
    _spectra_php = (
        "<?php\n"
        f"$post_id = {page_id};\n"
        "if (!class_exists('UAGB_Post_Assets')) { echo '[!] Spectra not active\n'; exit; }\n"
        "delete_post_meta($post_id, '_uag_page_assets');\n"
        "delete_post_meta($post_id, '_uag_css_file_name');\n"
        "delete_post_meta($post_id, '_uag_js_file_name');\n"
        "$post = get_post($post_id);\n"
        "$assets = new UAGB_Post_Assets($post_id);\n"
        "$assets->prepare_assets($post);\n"
        "$assets->generate_asset_files();\n"
        "$meta = get_post_meta($post_id, '_uag_page_assets', true);\n"
        "if (!empty($meta['css'])) { echo '[✓] Spectra CSS regenerated (' . strlen($meta['css']) . ' bytes)\n'; }\n"
        "else { echo '[!] Spectra CSS meta empty after regeneration\n'; }\n"
    )
    _spectra_php_path = f"/tmp/spectra-css-{_pid}.php"
    with open(_spectra_php_path, "w") as _sf:
        _sf.write(_spectra_php)
    _sr = wp(f"eval-file {_spectra_php_path}", wp_path)
    if _sr and _sr.strip():
        log(_sr.strip())
    _os.unlink(_spectra_php_path)


def generate_static_pages(config, unlock_contact_page=False, unlock_header_banner=False,
                           unlock_images=False, config_path=None):
    """Create or update About, FAQ, and Contact pages; add footer map widget.

    Contact page and the header banner (below) are locked-by-default, same
    principle as the AI-content locks: once created/set, a plain run never
    touches them again. Only an explicit --unlock-* flag regenerates them,
    and the old value is snapshotted first. About/FAQ/Service Areas/Services
    and the Homepage are NOT locked — they're deterministic template output
    with nothing manually customized to protect, per the documented scope
    in project_content_protection_system.md."""
    wp_path = config["wp_path"]

    # Pool images must be placed before the homepage is built — it reads
    # the fixed filenames these picks are copied to.
    sync_pool_images(config, wp_path, config_path, unlock_images=unlock_images)

    # Homepage handles its own WP push via eval-file (returns None — not safe for upsert_page)
    build_homepage(config, wp_path)

    pages = [
        ("About",         build_about_page(config)),
        ("FAQ",           build_faq_page(config)),
        ("Service Areas", build_service_areas_page(config)),
        ("Services",      build_services_page(config)),
    ]
    for title, markup in pages:
        existing_id = get_existing_page_id(title, wp_path)
        post_id = upsert_page(title, markup, wp_path, existing_id)
        action = "Updated" if existing_id else "Created"
        log(f"{action} {title} page (ID: {post_id})")

    # Contact page — locked after first creation (see docstring above)
    contact_existing_id = get_existing_page_id("Contact", wp_path)
    if contact_existing_id and not unlock_contact_page:
        log(f"Contact page already exists (ID {contact_existing_id}) — locked, left untouched (use --unlock-contact-page to override)")
    else:
        if contact_existing_id:
            old_content = wp(f"post get {contact_existing_id} --field=post_content", wp_path)
            _save_pre_override_snapshot(config_path or wp_path, "Contact", "contact_page", old_content)
        contact_markup = build_contact_page(config)
        contact_post_id = upsert_page("Contact", contact_markup, wp_path, contact_existing_id)
        log(f"{'Updated' if contact_existing_id else 'Created'} Contact page (ID: {contact_post_id})")

    # Footer copyright + disclaimer
    _disclaimer = (
        "Copyright &copy; [current_year] [site_title]<br><br>"
        "This website shares information with local, licensed, and insured service providers "
        "who will reach out and contact you with the information provided here."
    )
    _disc_php = (
        "<?php\n"
        "$s = get_option('astra-settings', []);\n"
        f"$s['footer-copyright-editor'] = '{_disclaimer}';\n"
        "update_option('astra-settings', $s);\n"
        "echo 'ok';\n"
    )
    _disc_php_path = '/tmp/set_footer_disclaimer.php'
    with open(_disc_php_path, 'w') as _dph:
        _dph.write(_disc_php)
    wp(f'eval-file {_disc_php_path}', wp_path)
    import os as _os; _os.unlink(_disc_php_path)
    log('Footer disclaimer set')

    # Above-header bar (header-html-1) — city/state-specific "Serving X" text.
    # templates/astra-settings.json ships this hardcoded to the site it was
    # originally exported from ("Serving Raleigh, NC, and Surrounding
    # Communities"); every site must overwrite it with its own city/state at
    # provision time or it silently advertises the wrong service area.
    #
    # Locked-by-default after that first correction (same principle as the
    # Contact page above): only fires while the value still equals the known
    # bad template default. Once it's been corrected once — by this script
    # or by hand — a plain run never touches it again; --unlock-header-banner
    # forces it regardless, with the old value snapshotted first.
    _KNOWN_HEADER_PLACEHOLDER = "Serving Raleigh, NC, and Surrounding Communities"
    _city  = config.get("primary_city", "")
    _state = config.get("state_abbr", config.get("primary_state", ""))
    if _city and _state:
        _current_settings_raw = wp("option get astra-settings --format=json", wp_path)
        try:
            _current_settings = json.loads(_current_settings_raw) if _current_settings_raw.strip() else {}
        except json.JSONDecodeError:
            _current_settings = {}
        _current_header = _current_settings.get("header-html-1", "")

        if _current_header != _KNOWN_HEADER_PLACEHOLDER and not unlock_header_banner:
            log(f'Header "Serving" text already set ({_current_header!r}) — locked, left untouched (use --unlock-header-banner to override)')
        else:
            if _current_header and _current_header != _KNOWN_HEADER_PLACEHOLDER:
                _save_pre_override_snapshot(config_path or wp_path, "header", "header_banner", _current_header)
            _header_html = f"Serving {_city}, {_state}, and Surrounding Communities"
            # PHP single-quoted string escaping — real US city names (O'Fallon,
            # Coeur d'Alene, etc.) contain apostrophes that would otherwise break
            # out of the string and corrupt the eval'd PHP.
            _header_html_esc = _header_html.replace("\\", "\\\\").replace("'", "\\'")
            _hdr_php = (
                "<?php\n"
                "$s = get_option('astra-settings', []);\n"
                f"$s['header-html-1'] = '{_header_html_esc}';\n"
                "update_option('astra-settings', $s);\n"
                "echo 'ok';\n"
            )
            _hdr_php_path = '/tmp/set_header_html.php'
            with open(_hdr_php_path, 'w') as _hph:
                _hph.write(_hdr_php)
            wp(f'eval-file {_hdr_php_path}', wp_path)
            _os.unlink(_hdr_php_path)
            log(f'Header "Serving" text set to {_city}, {_state}')

    # Footer map widget (Column 4) — city-specific Google Maps embed
    city  = config.get("primary_city", "")
    state = config.get("primary_state", "")
    if city and state:
        map_query = f"{city},{state}".replace(" ", "+")
        map_html  = (
            f'<iframe src="https://maps.google.com/maps?q={map_query}&t=m&z=10&output=embed&iwloc=near" '
            'width="100%" height="250" style="border:0;border-radius:6px;" '
            'allowfullscreen="" loading="lazy"></iframe>'
        )
        try:
            existing = wp("widget list footer-widget-4 --format=json", wp_path)
            widgets  = json.loads(existing) if existing.strip().startswith("[") else []
            if widgets:
                wp(f"widget delete {widgets[0]['id']}", wp_path)
            # Add blank widget then set content via eval-file (no shell quoting issues)
            wp("widget add block footer-widget-4 1", wp_path)
            after_raw = wp("widget list footer-widget-4 --format=json", wp_path)
            after_widgets = json.loads(after_raw) if after_raw.strip().startswith("[") else []
            if after_widgets:
                instance_id = after_widgets[0]["id"].replace("block-", "")
                block_content = f"<!-- wp:html -->{map_html}<!-- /wp:html -->"
                block_php = block_content.replace("'", "\'")
                php_script = (
                    "<?php\n"
                    f"$opts = get_option('widget_block');\n"
                    f"$opts[{instance_id}]['content'] = '{block_php}';\n"
                    "update_option('widget_block', $opts);\n"
                    "echo 'ok';\n"
                )
                php_path = "/tmp/set_map_widget.php"
                with open(php_path, "w") as _fh:
                    _fh.write(php_script)
                result = wp(f"eval-file {php_path}", wp_path)
                import os; os.unlink(php_path)
                if "ok" in result:
                    log(f"Footer map widget updated: {city}, {state}")
                else:
                    warn(f"Footer map widget eval-file returned: {result}")
        except Exception as e:
            warn(f"Could not update footer map widget: {e}")

    # Footer contact widget (Column 3) — phone number placeholder patch only.
    # provision-site.sh creates this widget with a literal "(000) 000-0000"
    # placeholder that nothing else ever replaces, since it's a widget, not
    # page content — build_homepage()'s phone swap never reaches it. Patch
    # just the phone fields in place, leaving hours/email exactly as they
    # are: hours is a separate pending redesign, and email display is a
    # separate pending decision (see roadmap) — this must not get ahead of
    # either. Str-replace on the literal placeholder is naturally idempotent
    # and safe to re-run: once replaced, the placeholder no longer matches,
    # so a later run (or a manually-customized number) is left untouched.
    _phone = config.get("phone", "")
    if _phone:
        try:
            raw = wp("widget list footer-widget-6 --format=json", wp_path)
            widgets = json.loads(raw) if raw.strip().startswith("[") else []
            block_widgets = [w for w in widgets if w["id"].startswith("block-")]
            if block_widgets:
                instance_id = block_widgets[0]["id"].replace("block-", "")
                _phone_tel = re.sub(r"\D", "", _phone)
                _phone_esc = _phone.replace("\\", "\\\\").replace("'", "\\'")
                php_script = (
                    "<?php\n"
                    "$opts = get_option('widget_block');\n"
                    f"if (isset($opts[{instance_id}]['content'])) {{\n"
                    f"    $c = $opts[{instance_id}]['content'];\n"
                    "    $c = str_replace('tel:10000000000', 'tel:1" + _phone_tel + "', $c);\n"
                    "    $c = str_replace('(000) 000-0000', '" + _phone_esc + "', $c);\n"
                    f"    $opts[{instance_id}]['content'] = $c;\n"
                    "    update_option('widget_block', $opts);\n"
                    "    echo 'ok';\n"
                    "} else { echo 'not found'; }\n"
                )
                php_path = "/tmp/set_footer_contact_phone.php"
                with open(php_path, "w") as _fh:
                    _fh.write(php_script)
                result = wp(f"eval-file {php_path}", wp_path)
                import os; os.unlink(php_path)
                if "ok" in result:
                    log(f"Footer contact widget phone updated: {_phone}")
                else:
                    warn(f"Footer contact widget phone patch returned: {result}")
            else:
                warn("Footer contact widget (footer-widget-6) not found — phone not patched")
        except Exception as e:
            warn(f"Could not update footer contact widget phone: {e}")


# ============================================================
# NAV MENU UPDATER
# ============================================================

def update_nav_menus(config):
    """Populate Services and Service Areas dropdowns + Footer Services menu."""
    wp_path  = config["wp_path"]
    services = config["services"]
    cities   = config["cities"]
    niche    = config["niche"]
    niche_short = niche.replace(" Services", "").replace(" Service", "")

    primary_city_data = next((c for c in cities if c.get("is_primary")), cities[0])

    try:
        menus_raw = wp("menu list --fields=term_id,name --format=json", wp_path)
        menus = json.loads(menus_raw)
    except Exception as e:
        warn(f"Could not list menus: {e}")
        return

    primary_menu_id    = None
    footer_services_id = None
    for m in menus:
        if m["name"] == "Primary Menu":
            primary_menu_id = str(m["term_id"])
        if m["name"] == "Footer Services":
            footer_services_id = str(m["term_id"])

    if not primary_menu_id:
        warn("Primary Menu not found — skipping nav update")
        return

    try:
        items_raw = wp(
            f"menu item list {primary_menu_id} "
            "--fields=ID,title,menu_item_parent --format=json",
            wp_path
        )
        items = json.loads(items_raw)
    except Exception as e:
        warn(f"Could not read primary menu items: {e}")
        return

    services_parent_id  = None
    svc_areas_parent_id = None
    existing_services   = set()
    existing_areas      = set()

    for item in items:
        parent = str(item.get("menu_item_parent", "0"))
        if item["title"] == "Services" and parent == "0":
            services_parent_id = str(item["ID"])
        elif item["title"] == "Service Areas" and parent == "0":
            svc_areas_parent_id = str(item["ID"])

    for item in items:
        parent = str(item.get("menu_item_parent", "0"))
        if services_parent_id and parent == services_parent_id:
            existing_services.add(item["title"])
        if svc_areas_parent_id and parent == svc_areas_parent_id:
            existing_areas.add(item["title"])

    # populate Services dropdown
    if services_parent_id:
        city  = primary_city_data["city"]
        state = primary_city_data["state"]
        for service in services:
            if service in existing_services:
                continue
            page_id = get_existing_page_id(f"{service} in {city}, {state}", wp_path)
            if page_id:
                try:
                    wp(
                        f"menu item add-post {primary_menu_id} {page_id} "
                        f"--title='{shell_esc(service)}' --parent-id={services_parent_id}",
                        wp_path
                    )
                    log(f"Services menu: added {service}")
                except Exception as e:
                    warn(f"Could not add to Services menu: {service} — {e}")

    # populate Service Areas dropdown — primary city first, then rest
    if svc_areas_parent_id:
        sorted_cities = sorted(cities, key=lambda c: (0 if c.get("is_primary") else 1, cities.index(c)))
        for city_data in sorted_cities:
            city  = city_data["city"]
            state = city_data["state"]
            if city in existing_areas:
                continue
            page_title = f"{niche_short} Services in {city}, {state}"
            page_id = get_existing_page_id(page_title, wp_path)
            if page_id:
                try:
                    wp(
                        f"menu item add-post {primary_menu_id} {page_id} "
                        f"--title='{shell_esc(city)}' --parent-id={svc_areas_parent_id}",
                        wp_path
                    )
                    log(f"Service Areas menu: added {city}")
                except Exception as e:
                    warn(f"Could not add to Service Areas menu: {city} — {e}")

    # populate Footer Services menu
    if footer_services_id:
        try:
            fi_raw = wp(
                f"menu item list {footer_services_id} --fields=ID,title --format=json",
                wp_path
            )
            existing_footer = {i["title"] for i in json.loads(fi_raw)}
        except Exception:
            existing_footer = set()

        city  = primary_city_data["city"]
        state = primary_city_data["state"]
        for service in services:
            if service in existing_footer:
                continue
            page_id = get_existing_page_id(f"{service} in {city}, {state}", wp_path)
            if page_id:
                try:
                    wp(
                        f"menu item add-post {footer_services_id} {page_id} "
                        f"--title='{shell_esc(service)}'",
                        wp_path
                    )
                    log(f"Footer Services: added {service}")
                except Exception as e:
                    warn(f"Could not add to Footer Services: {service} — {e}")

    # Update "Service Areas" and "Services" parent items from # to real page URLs
    try:
        items_raw = wp(
            f"menu item list {primary_menu_id} --fields=db_id,title,url --format=json",
            wp_path
        )
        items = json.loads(items_raw) if items_raw.strip().startswith("[") else []
        url_map = {
            "Service Areas": "/service-areas/",
            "Services":      "/services/",
        }
        for item in items:
            target_url = url_map.get(item["title"])
            if target_url and item["url"] == "#":
                wp(f"menu item update {item['db_id']} --link={target_url}", wp_path)
                log(f"Primary Menu: '{item['title']}' link updated to {target_url}")
    except Exception as e:
        warn(f"Could not update parent menu item links: {e}")

    # Footer Navigation menu — add Services + Service Areas pages
    footer_nav_id = None
    for m in menus:
        if m["name"] == "Footer Navigation":
            footer_nav_id = str(m["term_id"])
    if footer_nav_id:
        try:
            fn_raw = wp(
                f"menu item list {footer_nav_id} --fields=db_id,title,url --format=json",
                wp_path
            )
            fn_items = json.loads(fn_raw) if fn_raw.strip().startswith("[") else []
            fn_titles = {i["title"] for i in fn_items}
            fn_pages = [
                ("Services",      "/services/"),
                ("Service Areas", "/service-areas/"),
            ]
            # Insert after Home (position 2 and 3), so find current max position
            # and just append — WP CLI assigns positions automatically
            for title, url in fn_pages:
                if title in fn_titles:
                    log(f"Footer Navigation: '{title}' already present")
                    continue
                # Find Home item to insert after
                home_item = next((i for i in fn_items if i["title"] == "Home"), None)
                if home_item:
                    wp(
                        f"menu item add-custom {footer_nav_id} '{title}' {url}",
                        wp_path
                    )
                    log(f"Footer Navigation: added '{title}'")
                else:
                    wp(
                        f"menu item add-custom {footer_nav_id} '{title}' {url}",
                        wp_path
                    )
                    log(f"Footer Navigation: added '{title}'")
            # Set correct positions: Home=1, Services=2, Service Areas=3, rest follow
            fn_raw2 = wp(
                f"menu item list {footer_nav_id} --fields=db_id,title --format=json",
                wp_path
            )
            fn_items2 = json.loads(fn_raw2) if fn_raw2.strip().startswith("[") else []
            order_map = {"Home": 1, "Services": 2, "Service Areas": 3,
                         "About": 4, "Contact": 5, "Free Quote": 6, "FAQ": 7}
            for item in fn_items2:
                pos = order_map.get(item["title"])
                if pos is not None:
                    wp(f"menu item update {item['db_id']} --position={pos}", wp_path)
            log("Footer Navigation: positions updated")
        except Exception as e:
            warn(f"Could not update Footer Navigation: {e}")

    log("Nav menus updated")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Generate rank-and-rent service pages (Option C)")
    parser.add_argument("--config",            required=True, help="Path to niche config JSON")
    parser.add_argument("--dry-run",           action="store_true", help="Show what would be created, no API calls or WP writes")
    parser.add_argument("--update",            action="store_true", help="Regenerate existing pages")
    parser.add_argument("--only-overviews",    action="store_true", help="Generate city overview pages only")
    parser.add_argument("--only-service-pages",action="store_true", help="Generate individual service pages only")
    parser.add_argument("--city",              help="Limit to a single city name (exact match)")
    parser.add_argument("--service",           help="Limit to a single service name (exact match)")
    parser.add_argument("--rebuild",           action="store_true", help="Re-render page HTML from cache/DB, no API calls (this is now the default for --update too — kept for backward compatibility, no longer has a distinct effect)")
    parser.add_argument("--static-pages",      action="store_true", help="Generate/update About, FAQ, and Contact pages + nav menus")
    parser.add_argument("--unlock-body",             action="store_true", help="Allow fresh AI regeneration of body copy on already-existing pages")
    parser.add_argument("--unlock-faqs",             action="store_true", help="Allow fresh AI regeneration of FAQs on already-existing pages")
    parser.add_argument("--unlock-meta-title",       action="store_true", help="Allow fresh AI regeneration of the SEO title on already-existing pages")
    parser.add_argument("--unlock-meta-description", action="store_true", help="Allow fresh AI regeneration of the meta description on already-existing pages")
    parser.add_argument("--unlock-contact-page",     action="store_true", help="Allow re-generating the Contact page on an already-provisioned site")
    parser.add_argument("--unlock-header-banner",    action="store_true", help="Allow re-setting the above-header 'Serving X' text on an already-provisioned site")
    parser.add_argument("--unlock-images",           action="store_true", help="Allow re-rolling image pool picks that were already selected for this site")
    parser.add_argument("--unlock-all",              action="store_true", help="Shorthand for all --unlock-* flags at once")
    parser.add_argument("--use-kadence",             action="store_true", help="Emit Kadence blocks instead of Spectra/uagb blocks for converted builders (migration in progress — see pre-kadence-migration plan). Default off so both code paths can coexist while the rest of the migration is still in progress.")
    args = parser.parse_args()

    # Content is locked by default (see project_content_protection_system):
    # --update alone never regenerates AI content anymore — only an explicit
    # --unlock-* flag does, and only for that specific element. This is the
    # fix for the original bug: --update without --rebuild used to silently
    # regenerate fresh (and different) wording on every already-ranking page.
    unlock_body             = args.unlock_all or args.unlock_body
    unlock_faqs             = args.unlock_all or args.unlock_faqs
    unlock_meta_title       = args.unlock_all or args.unlock_meta_title
    unlock_meta_description = args.unlock_all or args.unlock_meta_description
    unlock_contact_page     = args.unlock_all or args.unlock_contact_page
    unlock_header_banner    = args.unlock_all or args.unlock_header_banner
    unlock_images           = args.unlock_all or args.unlock_images
    if unlock_body or unlock_faqs or unlock_meta_title or unlock_meta_description or unlock_contact_page or unlock_header_banner or unlock_images:
        unlocked = [n for n, v in (
            ("body", unlock_body), ("faqs", unlock_faqs),
            ("meta title", unlock_meta_title), ("meta description", unlock_meta_description),
            ("contact page", unlock_contact_page), ("header banner", unlock_header_banner),
            ("images", unlock_images),
        ) if v]
        warn(f"UNLOCKED for this run: {', '.join(unlocked)} — a pre-override snapshot of the old value(s) will be saved before each is overwritten")

    with open(args.config) as f:
        config = json.load(f)
    config["use_kadence"] = args.use_kadence
    if args.use_kadence:
        warn("Using Kadence blocks (--use-kadence) — only build_service_card is converted so far; everything else still emits Spectra/uagb blocks on the same page")

    cache = _load_cache(args.config) if not args.dry_run else None

    services = config["services"]
    cities   = config["cities"]

    if args.service:
        services = [s for s in services if s == args.service]
        if not services:
            err(f"Service '{args.service}' not found in config")
    if args.city:
        cities = [c for c in cities if c["city"] == args.city]
        if not cities:
            err(f"City '{args.city}' not found in config")

    do_overviews = not args.only_service_pages
    do_services  = not args.only_overviews

    total_overviews = len(cities) if do_overviews else 0
    total_service   = len(services) * len(cities) if do_services else 0

    section(f"Rank & Rent Generator ‚Äî {config['niche']}")
    print(f"  Site:            {config['site_url']}")
    print(f"  Cities:          {len(cities)}")
    print(f"  Services:        {len(services)}")
    print(f"  Overview pages:  {total_overviews}")
    print(f"  Service pages:   {total_service}  ({len(services)} √ó {len(cities)} cities)")
    print(f"  Total:           {total_overviews + total_service} pages")

    if args.dry_run:
        warn("DRY RUN ‚Äî no WP writes, no API calls")
    if args.update or args.rebuild:
        warn("UPDATE MODE — existing pages will be re-pushed from cache; no AI content changes without an --unlock-* flag")

    results = []
    errors  = []

    # City overview pages ‚Äî skip the primary city (homepage handles it)
    if do_overviews:
        section("City Overview Pages")
        for city_data in cities:
            try:
                r = generate_city_overview_page(
                    city_data["city"], city_data["state"],
                    config, city_data, update=args.update or args.rebuild, dry_run=args.dry_run,
                    unlock_body=unlock_body,
                    unlock_meta_title=unlock_meta_title, unlock_meta_description=unlock_meta_description,
                    cache=cache, config_path=args.config
                )
                results.append(r)
            except Exception as e:
                msg = f"Overview failed: {city_data['city']} ‚Äî {e}"
                warn(msg); errors.append(msg)

    # Individual service √ó city pages
    if do_services:
        section("Individual Service Pages")
        for city_data in cities:
            for service in services:
                try:
                    r = generate_individual_service_page(
                        service, city_data["city"], city_data["state"],
                        config, city_data, update=args.update or args.rebuild, dry_run=args.dry_run,
                        unlock_body=unlock_body, unlock_faqs=unlock_faqs,
                        unlock_meta_title=unlock_meta_title, unlock_meta_description=unlock_meta_description,
                        cache=cache, config_path=args.config
                    )
                    results.append(r)
                except Exception as e:
                    msg = f"Service page failed: {service} in {city_data['city']} ‚Äî {e}"
                    warn(msg); errors.append(msg)

    created = [r for r in results if r.get("action") == "created"]
    updated = [r for r in results if r.get("action") == "updated"]
    skipped = [r for r in results if r.get("action") == "skipped"]

    section("Done")
    print(f"  Created:  {len(created)}")
    print(f"  Updated:  {len(updated)}")
    print(f"  Skipped:  {len(skipped)}")
    print(f"  Errors:   {len(errors)}")

    if errors:
        print(f"\n{YELLOW}Errors:{NC}")
        for e in errors:
            print(f"  {e}")

    if args.static_pages:
        section("Static Pages (About / FAQ / Contact)")
        generate_static_pages(config, unlock_contact_page=unlock_contact_page,
                              unlock_header_banner=unlock_header_banner,
                              unlock_images=unlock_images, config_path=args.config)

    if args.update or args.static_pages:
        section("Nav Menus")
        wp_path = config["wp_path"]
        # Set Home as the static front page
        try:
            _home_id = str(config.get("homepage_id", ""))
            if not _home_id:
                _home_raw = wp(
                    "post list --post_type=page --post_slug=home --field=ID --format=ids",
                    wp_path
                )
                _home_id = _home_raw.strip().split()[0] if _home_raw.strip() else ""
            if _home_id.isdigit():
                wp("option update show_on_front page", wp_path)
                wp(f"option update page_on_front {_home_id}", wp_path)
                log(f"Front page set to Home (ID {_home_id})")
            else:
                warn("Home page ID not found - set front page manually")
        except Exception as _fe:
            warn(f"Could not set front page: {_fe}")

        update_nav_menus(config)

    log_path = "/tmp/" + os.path.basename(args.config).replace(".json", "-results.json")
    try:
        with open(log_path, "w") as f:
            json.dump({"results": results, "errors": errors}, f, indent=2)
        log(f"Results log: {log_path}")
    except PermissionError:
        warn(f"Could not write results log (permission denied): {log_path}")


if __name__ == "__main__":
    main()
