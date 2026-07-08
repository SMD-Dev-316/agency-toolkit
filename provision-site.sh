#!/bin/bash
# ============================================================
# Rank & Rent Site Provisioning Script
# Usage: bash provision-site.sh <wordpress-path>
# Example: bash provision-site.sh /home/teqlynet/public_html/mysite
# ============================================================

set -uo pipefail

# --- Colors ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()     { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1" >&2; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${BLUE}--- $1 ---${NC}"; }

# ============================================================
# CONFIGURATION — edit these paths once, leave them
# ============================================================
TOOLKIT_DIR="/var/www/agency-toolkit"
PLUGINS_DIR="$TOOLKIT_DIR/assets"

# ============================================================
# VALIDATE INPUT
# ============================================================
WP_PATH="${1:?Error: Provide the WordPress path. Usage: bash provision-site.sh /path/to/wordpress}"

cd "$WP_PATH" || error "Cannot navigate to: $WP_PATH"
wp core is-installed 2>/dev/null || error "No WordPress installation found at: $WP_PATH"
log "WordPress confirmed at: $WP_PATH"

SITE_URL=$(wp option get siteurl)
log "Site URL: $SITE_URL"

# ============================================================
# WORDPRESS CORE SETTINGS
# ============================================================
section "WordPress Core Settings"

wp option update blogdescription ""                     # Clear default tagline
wp option update default_comment_status "closed"        # Disable comments on posts
wp option update default_ping_status "closed"           # Disable pingbacks
wp option update permalink_structure "/%postname%/"     # SEO-friendly URLs
wp option update blog_public 1                          # Allow search engines
wp option update default_pingback_flag 0                # No pingback notifications
wp option update comments_notify 0                      # No comment notifications
wp rewrite flush                                        # Apply permalink changes

log "Core settings configured"

# ============================================================
# REMOVE DEFAULT CONTENT
# ============================================================
section "Removing Default Content"

wp post delete 1 --force 2>/dev/null && log "Deleted: Hello World post" || warn "Hello World post not found (already deleted)"
wp post delete 2 --force 2>/dev/null && log "Deleted: Sample Page"      || warn "Sample Page not found (already deleted)"
wp comment delete 1 --force 2>/dev/null && log "Deleted: Default comment" || warn "Default comment not found"

# ============================================================
# THEME
# ============================================================
section "Installing Theme"

# Install Astra parent theme
if wp theme is-installed astra 2>/dev/null; then
    warn "Astra already installed"
else
    wp theme install astra
    log "Astra parent theme installed"
fi

# Install and activate Astra child theme
CHILD_ZIP="$PLUGINS_DIR/astra-child.zip"
if [ -f "$CHILD_ZIP" ]; then
    wp theme install "$CHILD_ZIP" --activate --force
    log "Astra child theme installed and activated"
else
    warn "astra-child.zip not found in $TOOLKIT_DIR/plugins — activating parent theme"
    wp theme activate astra
fi

# ============================================================
# FREE PLUGINS (WordPress.org)
# ============================================================
section "Installing Free Plugins"

FREE_PLUGINS=(
    "ultimate-addons-for-gutenberg"
    "header-footer-elementor"
    "seo-by-rank-math"
    "elementor"
    "wordfence"
    "disable-comments"
    "enable-media-replace"
    "fluentform"
    "fluent-smtp"
    "ga-google-analytics"
    "litespeed-cache"
)

for plugin in "${FREE_PLUGINS[@]}"; do
    if wp plugin is-installed "$plugin" 2>/dev/null; then
        warn "$plugin already installed — activating"
        wp plugin activate "$plugin" 2>/dev/null || true
    else
        wp plugin install "$plugin" --activate
        log "Installed + activated: $plugin"
    fi
done


# ============================================================
# PRO PLUGINS (Local ZIPs)
# Install free version first, then overwrite with Pro ZIP
# ============================================================
section "Installing Pro Plugins"

PRO_PLUGINS=(
    "astra-pro.zip"
    "spectra-pro.zip"
    "ultimate-addons-for-elementor-pro.zip"
    "rank-math-pro.zip"
    "fluent-forms-pro.zip"
)

for zip in "${PRO_PLUGINS[@]}"; do
    zip_path="$PLUGINS_DIR/$zip"
    if [ -f "$zip_path" ]; then
        wp plugin install "$zip_path" --activate --force
        log "Installed Pro: $zip"
    else
        warn "ZIP not found — skipping: $zip_path"
        warn "Upload $zip to $PLUGINS_DIR to enable Pro features"
    fi
done


# ============================================================
# DISABLE COMMENTS GLOBALLY
# ============================================================
section "Disabling Comments"

wp option update dc_settings 'a:1:{s:20:"disabled_everywhere";b:1;}' 2>/dev/null || true
log "Comments disabled globally"

# ============================================================
# RANK MATH — Base configuration
# ============================================================
section "Configuring Rank Math"

# Set SEO title separator and format
wp option patch update rank-math-options-titles title_separator "-"     2>/dev/null || true
wp option patch update rank-math-options-titles homepage_title "%sitename% %sep% %sitedesc%" 2>/dev/null || true

# Disable Rank Math on login/register pages
wp option patch update rank-math-options-general noindex_empty_taxonomies 1 2>/dev/null || true

log "Rank Math base configuration applied"

# ============================================================
# STANDARD PAGES
# ============================================================
section "Creating Standard Pages"

# Helper: get existing page ID or create it
get_or_create_page() {
    local title="$1"
    local existing_id
    existing_id=$(wp post list --post_type=page --post_status=publish --fields=ID,post_title --format=csv | grep -i ",\"\?${title}\"\?$" | cut -d, -f1 | head -1)
    if [ -n "$existing_id" ]; then
        warn "Page already exists: $title (ID: $existing_id)"
        echo "$existing_id"
    else
        wp post create --post_title="$title" --post_status=publish --post_type=page --porcelain
    fi
}

HOME_ID=$(get_or_create_page "Home")
log "Home page ready (ID: $HOME_ID)"

ABOUT_ID=$(get_or_create_page "About")
log "About page ready (ID: $ABOUT_ID)"

QUOTE_ID=$(get_or_create_page "Free Quote")
log "Free Quote page ready (ID: $QUOTE_ID)"

CONTACT_ID=$(get_or_create_page "Contact")
log "Contact page ready (ID: $CONTACT_ID)"

FAQ_ID=$(get_or_create_page "FAQ")
log "FAQ page ready (ID: $FAQ_ID)"

PRIVACY_ID=$(get_or_create_page "Privacy Policy")
log "Privacy Policy page ready (ID: $PRIVACY_ID)"

TERMS_ID=$(get_or_create_page "Terms of Service")
log "Terms of Service page ready (ID: $TERMS_ID)"

# Set static homepage
wp option update show_on_front "page"
wp option update page_on_front "$HOME_ID"
log "Static homepage set"

# ============================================================
# REUSABLE BLOCKS — Sidebar CTA + Banner CTA
# ============================================================
section "Creating Reusable Blocks"

SIDEBAR_TEMPLATE="$TOOLKIT_DIR/templates/sidebar-block.txt"
BANNER_TEMPLATE="$TOOLKIT_DIR/templates/banner-block.txt"

if [ -f "$SIDEBAR_TEMPLATE" ]; then
    SIDEBAR_ID=$(wp post create \
        --post_type=wp_block \
        --post_title="Sidebar CTA" \
        --post_status=publish \
        --post_content="$(cat "$SIDEBAR_TEMPLATE")" \
        --porcelain)
    log "Sidebar CTA block created (ID: $SIDEBAR_ID)"
    warn "Update sidebar_block_ref in this site's config JSON to: $SIDEBAR_ID"
else
    warn "sidebar-block.txt not found at $SIDEBAR_TEMPLATE"
    SIDEBAR_ID="NOT_CREATED"
fi

if [ -f "$BANNER_TEMPLATE" ]; then
    BANNER_ID=$(wp post create \
        --post_type=wp_block \
        --post_title="Banner CTA" \
        --post_status=publish \
        --post_content="$(cat "$BANNER_TEMPLATE")" \
        --porcelain)
    log "Banner CTA block created (ID: $BANNER_ID)"
    warn "Update banner_cta_ref in this site's config JSON to: $BANNER_ID"
else
    warn "banner-block.txt not found at $BANNER_TEMPLATE"
    BANNER_ID="NOT_CREATED"
fi

CONTACT_TEMPLATE="$TOOLKIT_DIR/templates/contact-block.txt"
if [ -f "$CONTACT_TEMPLATE" ]; then
    CONTACT_BLOCK_CONTENT=$(sed \
        -e "s/{{PHONE}}/(000) 000-0000/g" \
        -e "s/{{PHONE_DIGITS}}/10000000000/g" \
        -e "s/{{PRIMARY_CITY}}/Your City/g" \
        -e "s/{{PRIMARY_STATE}}/Your State/g" \
        "$CONTACT_TEMPLATE")
    CONTACT_BLOCK_ID=$(wp post create \
        --post_type=wp_block \
        --post_title="Contact Block 01" \
        --post_status=publish \
        --post_content="$CONTACT_BLOCK_CONTENT" \
        --porcelain)
    log "Contact Block 01 created (ID: $CONTACT_BLOCK_ID)"
    warn "Add contact_block_ref: $CONTACT_BLOCK_ID to this site's config JSON"
else
    warn "contact-block.txt not found at $CONTACT_TEMPLATE"
    CONTACT_BLOCK_ID="NOT_CREATED"
fi

# ============================================================
# PLACEHOLDER IMAGES
# ============================================================
section "Importing Placeholder Images"

PLACEHOLDER_SOURCE="/var/www/agency-toolkit/assets"
PLACEHOLDER_DEST="$WP_PATH/wp-content/uploads"
    mkdir -p "${WP_PATH}/wp-content/uploads/rar"
    log "Created /uploads/rar/ for agency images"

cp "$PLACEHOLDER_SOURCE/placeholder-wide-narrow.jpg" "$PLACEHOLDER_DEST/" 2>/dev/null \
    && wp media import "$PLACEHOLDER_DEST/placeholder-wide-narrow.jpg" \
    && log "Imported: placeholder-wide-narrow.jpg" \
    || warn "Could not import placeholder-wide-narrow — copy manually"

cp "$PLACEHOLDER_SOURCE/placeholder-image-rectangle.png" "$PLACEHOLDER_DEST/" 2>/dev/null \
    && wp media import "$PLACEHOLDER_DEST/placeholder-image-rectangle.png" \
    && log "Imported: placeholder-image-rectangle.png" \
    || warn "Could not import placeholder-image-rectangle — copy manually"

# ============================================================
# PLACEHOLDER LOGO
# ============================================================
section "Setting Placeholder Logo"

LOGO_BLACK="$PLUGINS_DIR/placeholder-logo-black.png"
LOGO_WHITE="$PLUGINS_DIR/placeholder-logo-white.png"

if [ -f "$LOGO_BLACK" ]; then
    LOGO_BLACK_ID=$(wp media import "$LOGO_BLACK" --porcelain)
    wp theme mod set custom_logo $LOGO_BLACK_ID
    log "Placeholder logo (black) set as site logo (ID: $LOGO_BLACK_ID)"
else
    warn "placeholder-logo-black.png not found in $PLUGINS_DIR — skipping"
fi

if [ -f "$LOGO_WHITE" ]; then
    LOGO_WHITE_ID=$(wp media import "$LOGO_WHITE" --porcelain)
    log "Placeholder logo (white) imported (ID: $LOGO_WHITE_ID)"
else
    warn "placeholder-logo-white.png not found in $PLUGINS_DIR — skipping"
fi

# ============================================================
# ASTRA THEME SETTINGS
# ============================================================
section "Importing Astra Theme Settings"

ASTRA_SETTINGS="$TOOLKIT_DIR/templates/astra-settings.json"
ASTRA_COLORS="$TOOLKIT_DIR/templates/astra-color-palettes.json"

if [ -f "$ASTRA_SETTINGS" ]; then
    cat > /tmp/import-astra.php << 'PHPEOF'
<?php
$settings = file_get_contents('/var/www/agency-toolkit/templates/astra-settings.json');
$settings_array = json_decode($settings, true);
update_option('astra-settings', $settings_array);
echo "Astra settings imported.\n";
PHPEOF
    wp eval-file /tmp/import-astra.php
    log "Astra settings imported"
else
    warn "astra-settings.json not found at $ASTRA_SETTINGS — skipping"
fi

if [ -f "$ASTRA_COLORS" ]; then
    cat > /tmp/import-astra-colors.php << 'PHPEOF'
<?php
$settings = file_get_contents('/var/www/agency-toolkit/templates/astra-color-palettes.json');
$settings_array = json_decode($settings, true);
update_option('astra-color-palettes', $settings_array);
echo "Astra color palettes imported.\n";
PHPEOF
    wp eval-file /tmp/import-astra-colors.php
    log "Astra color palettes imported"
else
    warn "astra-color-palettes.json not found at $ASTRA_COLORS — skipping"
fi

# ============================================================
# LITESPEED CACHE
# ============================================================
section "Confirming LiteSpeed Cache"

wp plugin is-active litespeed-cache 2>/dev/null \
    && log "LiteSpeed Cache active" \
    || warn "LiteSpeed Cache not active — activate in WP Admin"

# ============================================================
# ELEMENTOR SETTINGS
# ============================================================
section "Configuring Elementor"

wp option update elementor_disable_color_schemes yes
wp option update elementor_disable_typography_schemes yes
log "Elementor set to inherit theme colors and fonts"

# ============================================================
# FREE QUOTE PAGE
# ============================================================
section "Importing Free Quote page content"

FREE_QUOTE_TEMPLATE="$TOOLKIT_DIR/templates/free-quote.html"

if [ -f "$FREE_QUOTE_TEMPLATE" ]; then
    cat > /tmp/import-free-quote.php << 'PHPEOF'
<?php
$content = file_get_contents('/var/www/agency-toolkit/templates/free-quote.html');
$page_id = get_option('page_on_front');
$result = $GLOBALS['wpdb']->get_var("SELECT ID FROM {$GLOBALS['wpdb']->posts} WHERE post_title = 'Free Quote' AND post_type = 'page' LIMIT 1");
if ($result) {
    wp_update_post(['ID' => (int)$result, 'post_content' => $content]);
    echo "Free Quote page updated (ID: $result)\n";
} else {
    echo "Free Quote page not found — skipping\n";
}
PHPEOF
    wp eval-file /tmp/import-free-quote.php
    log "Free Quote page content imported"
else
    warn "free-quote.html not found at $FREE_QUOTE_TEMPLATE — skipping"
fi

# ============================================================
# MENUS
# ============================================================
section "Creating Menus"

PRIMARY_MENU_ID=$(wp menu list --format=csv | grep -i ",\"\?Primary Menu\"\?," | cut -d, -f1 | head -1)
if [ -z "$PRIMARY_MENU_ID" ]; then
    PRIMARY_MENU_ID=$(wp menu create "Primary Menu" --porcelain)
else
    warn "Menu already exists: Primary Menu (ID: $PRIMARY_MENU_ID)"
fi
wp menu item add-post   $PRIMARY_MENU_ID $HOME_ID    --title="Home"
wp menu item add-custom $PRIMARY_MENU_ID "Service Areas" "#"
wp menu item add-custom $PRIMARY_MENU_ID "Services" "#"
wp menu item add-post   $PRIMARY_MENU_ID $ABOUT_ID   --title="About"
wp menu item add-post   $PRIMARY_MENU_ID $FAQ_ID     --title="FAQ"
wp menu item add-post   $PRIMARY_MENU_ID $CONTACT_ID --title="Contact"
wp menu location assign $PRIMARY_MENU_ID primary
log "Primary menu created and assigned"

# Footer Navigation menu (Column 1 — same as primary)
FOOTER_NAV_ID=$(wp menu list --format=csv | grep -i ",\"\?Footer Navigation\"\?," | cut -d, -f1 | head -1)
if [ -z "$FOOTER_NAV_ID" ]; then
    FOOTER_NAV_ID=$(wp menu create "Footer Navigation" --porcelain)
else
    warn "Menu already exists: Footer Navigation (ID: $FOOTER_NAV_ID)"
fi
wp menu item add-post $FOOTER_NAV_ID $HOME_ID    --title="Home"
wp menu item add-post $FOOTER_NAV_ID $ABOUT_ID   --title="About"
wp menu item add-post $FOOTER_NAV_ID $FAQ_ID     --title="FAQ"
wp menu item add-post $FOOTER_NAV_ID $CONTACT_ID --title="Contact"
wp menu item add-post $FOOTER_NAV_ID $QUOTE_ID   --title="Free Quote"
wp widget add nav_menu footer-widget-3 1 --nav_menu=$FOOTER_NAV_ID --title="Navigation"
log "Footer Navigation menu created (Column 1)"

# Footer Help menu (Column 3)
FOOTER_HELP_ID=$(wp menu list --format=csv | grep -i ",\"\?Footer Help\"\?," | cut -d, -f1 | head -1)
if [ -z "$FOOTER_HELP_ID" ]; then
    FOOTER_HELP_ID=$(wp menu create "Footer Help" --porcelain)
else
    warn "Menu already exists: Footer Help (ID: $FOOTER_HELP_ID)"
fi
wp menu item add-post $FOOTER_HELP_ID $FAQ_ID     --title="FAQ"
wp menu item add-post $FOOTER_HELP_ID $CONTACT_ID --title="Contact"
wp menu item add-post $FOOTER_HELP_ID $QUOTE_ID   --title="Free Quote"
wp widget add nav_menu footer-widget-6 1 --nav_menu=$FOOTER_HELP_ID --title="Help"
log "Footer Help menu created (Column 3)"

# Footer Services menu (Column 2)
FOOTER_SERVICES_ID=$(wp menu list --format=csv | grep -i ",\"\?Footer Services\"\?," | cut -d, -f1 | head -1)
if [ -z "$FOOTER_SERVICES_ID" ]; then
    FOOTER_SERVICES_ID=$(wp menu create "Footer Services" --porcelain)
else
    warn "Menu already exists: Footer Services (ID: $FOOTER_SERVICES_ID)"
fi
wp widget add nav_menu footer-widget-4 1 --nav_menu=$FOOTER_SERVICES_ID --title="Services"
log "Footer Services menu created (Column 2) — items added by generate-pages.py"

# Footer Contact block (Column 3, below Help)
SITE_DOMAIN=$(wp option get siteurl | sed 's|https\?://||' | sed 's|www\.||')
wp widget add block footer-widget-6 2 --content="<h2 style=\"font-size: 22px;\">Contact</h2><a href=\"tel:10000000000\">(000) 000-0000</a> <a href=\"mailto:contact@${SITE_DOMAIN}\">contact@${SITE_DOMAIN}</a><p><strong>Hours:</strong> Mon–Fri 8am–6pm, Sat 9am–4pm</p>" 
log "Footer Contact block added (Column 3)"

# Footer legal menu (footer_menu location — Privacy + Terms)
FOOTER_MENU_ID=$(wp menu list --format=csv | grep -i ",\"\?Footer Menu\"\?," | cut -d, -f1 | head -1)
if [ -z "$FOOTER_MENU_ID" ]; then
    FOOTER_MENU_ID=$(wp menu create "Footer Menu" --porcelain)
else
    warn "Menu already exists: Footer Menu (ID: $FOOTER_MENU_ID)"
fi
wp menu item add-post $FOOTER_MENU_ID $PRIVACY_ID --title="Privacy Policy"
wp menu item add-post $FOOTER_MENU_ID $TERMS_ID   --title="Terms of Service"
wp menu location assign $FOOTER_MENU_ID footer_menu
log "Footer legal menu created and assigned"

# ============================================================
# SUMMARY
# ============================================================
echo ""
echo "============================================================"
echo " PROVISIONING COMPLETE"
echo "============================================================"
echo " Site:              $SITE_URL"
echo " Home:              ID $HOME_ID"
echo " About:             ID $ABOUT_ID"
echo " FAQ:               ID $FAQ_ID"
echo " Free Quote:        ID $QUOTE_ID"
echo " Contact:           ID $CONTACT_ID"
echo " Privacy:           ID $PRIVACY_ID"
echo " Terms:             ID $TERMS_ID"
echo " Sidebar Block:     ID $SIDEBAR_ID"
echo " Banner Block:      ID $BANNER_ID"
echo " Contact Block:     ID $CONTACT_BLOCK_ID"
echo ""
echo " MANUAL STEPS REMAINING:"
echo " 1. Upload Pro ZIPs to $PLUGINS_DIR (if not done):"
echo "    astra-child.zip | astra-pro.zip | spectra-pro.zip | ultimate-addons-for-elementor-pro.zip | rank-math-pro.zip | fluent-forms-pro.zip"
echo " 2. Update sidebar_block_ref in config JSON to: $SIDEBAR_ID"
echo " 3. Update banner_cta_ref in config JSON to: $BANNER_ID"
echo " 4. Update contact_block_ref in config JSON to: $CONTACT_BLOCK_ID"
echo " 5. Update phone/city/state in Contact Block 01 reusable block when renting"
echo " 6. Configure Fluent SMTP with this site's email settings"
echo " 7. Add GA4 Measurement ID in GA Google Analytics settings"
echo " 8. Run: python3 generate-pages.py --config <cfg> --static-pages"
echo " 9. Run: python3 generate-pages.py --config <cfg> --update"
echo "============================================================"
