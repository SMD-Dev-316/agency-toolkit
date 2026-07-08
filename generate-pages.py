#!/usr/bin/env python3
# ============================================================
# Rank & Rent Page Generation Script ‚Äî Option C
# Generates: city overview pages + individual service/city pages
# Usage: python3 generate-pages.py --config configs/fence-tier1-cities.json
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --dry-run
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --update
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --only-overviews
#        python3 generate-pages.py --config configs/fence-tier1-cities.json --only-service-pages
# ============================================================

import os
import sys
import json
import re
import uuid
import time
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
    full_cmd = f"wp {command} --path={wp_path}"
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
# BLOCK BUILDERS ‚Äî Spectra / Gutenberg markup
# ============================================================


# ── Content cache ─────────────────────────────────────────────────────────────

def _cache_path(config_path):
    name = os.path.basename(config_path).replace(".json", "-content-cache.json")
    return os.path.join("/var/www/agency-toolkit/cache", name)

def _load_cache(config_path):
    path = _cache_path(config_path)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_cache(cache, config_path):
    path = _cache_path(config_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


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


def build_service_card(service_name, description, service_url, img_url, alt_text=""):
    """Single service card for city overview grid."""
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


def build_individual_service_page(c, config, service="", city="", state=""):
    """
    Assemble the full block markup for an individual service/city page.
    c = content dict from generate_individual_content()
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
        cards.append(build_service_card(svc, desc, svc_url, img_url, alt_text))

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


def generate_individual_content(service, city, state, county, nearby, niche, brand):
    """Call Claude to generate all text for an individual service/city page."""

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
  "service_area_paragraph": "2-3 sentences. Name the primary city, county, and at least 3 nearby towns from the list. Natural, not a list dump.",
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
        max_tokens=2000,
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

def generate_individual_service_page(service, city, state, config, city_data, update=False, dry_run=False, rebuild=False, cache=None, config_path=None):
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

    if rebuild and cache is not None and title in cache:
        content_data = cache[title]["content"]
        meta         = cache[title]["meta"]
    else:
        content_data = generate_individual_content(service, city, state, county, nearby, niche, brand)
        meta         = generate_seo_meta(focus_kw, city, state, brand)
        if cache is not None and config_path:
            cache[title] = {"content": content_data, "meta": meta}
            _save_cache(cache, config_path)
    page_markup  = build_individual_service_page(content_data, config, service, city, state)

    post_id = upsert_page(title, page_markup, wp_path, existing_id)
    set_rank_math_meta(post_id, meta, wp_path)

    log(f"{'Updated' if existing_id else 'Created'} ID {post_id} ‚Äî kw: {meta['focus_keyword']}")
    return {"title": title, "post_id": post_id, "action": "updated" if existing_id else "created", **meta}


def generate_city_overview_page(city, state, config, city_data, update=False, dry_run=False, rebuild=False, cache=None, config_path=None):
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

    if rebuild and cache is not None and title in cache:
        content_data = cache[title]["content"]
        meta         = cache[title]["meta"]
    else:
        content_data = generate_city_overview_content(city, state, services, niche, brand)
        content_data["_city"]  = city
        content_data["_state"] = state
        meta         = generate_seo_meta(focus_kw, city, state, brand)
        if cache is not None and config_path:
            cache[title] = {"content": content_data, "meta": meta}
            _save_cache(cache, config_path)
    page_markup  = build_city_overview_page(content_data, services, config)

    post_id = upsert_page(title, page_markup, wp_path, existing_id)
    set_rank_math_meta(post_id, meta, wp_path)

    log(f"{'Updated' if existing_id else 'Created'} ID {post_id} ‚Äî kw: {meta['focus_keyword']}")
    return {"title": title, "post_id": post_id, "action": "updated" if existing_id else "created", **meta}


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
    parser.add_argument("--rebuild",           action="store_true", help="Rebuild page HTML from cache (no API calls)")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

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

    total_overviews = len([c for c in cities if not c.get("is_primary")]) if do_overviews else 0
    total_service   = len(services) * len(cities) if do_services else 0

    section(f"Rank & Rent Generator ‚Äî {config['niche']}")
    print(f"  Site:            {config['site_url']}")
    print(f"  Cities:          {len(cities)}")
    print(f"  Services:        {len(services)}")
    print(f"  Overview pages:  {total_overviews}  (non-primary cities only)")
    print(f"  Service pages:   {total_service}  ({len(services)} √ó {len(cities)} cities)")
    print(f"  Total:           {total_overviews + total_service} pages")

    if args.dry_run:
        warn("DRY RUN ‚Äî no WP writes, no API calls")
    if args.update:
        warn("UPDATE MODE ‚Äî existing pages will be regenerated")
    if args.rebuild:
        n = len(cache) if cache else 0
        msg = f"REBUILD MODE — {n} pages in cache, no API calls" if n else "REBUILD MODE — cache empty, will call API"
        warn(msg)

    results = []
    errors  = []

    # City overview pages ‚Äî skip the primary city (homepage handles it)
    if do_overviews:
        section("City Overview Pages")
        for city_data in cities:
            if city_data.get("is_primary"):
                log(f"Skipping primary city overview (homepage covers it): {city_data['city']}")
                continue
            try:
                r = generate_city_overview_page(
                    city_data["city"], city_data["state"],
                    config, city_data, update=args.update or args.rebuild, dry_run=args.dry_run,
                    rebuild=args.rebuild, cache=cache, config_path=args.config
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
                        rebuild=args.rebuild, cache=cache, config_path=args.config
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

    log_path = "/tmp/" + os.path.basename(args.config).replace(".json", "-results.json")
    with open(log_path, "w") as f:
        json.dump({"results": results, "errors": errors}, f, indent=2)
    log(f"Results log: {log_path}")


if __name__ == "__main__":
    main()
