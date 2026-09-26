#!/usr/bin/env python3
"""
Creates the empty image-pool folder skeleton for a niche, so real photos
can be dropped straight into pre-made folders instead of building the
folder tree by hand.

Usage:
    python3 create_image_pool_skeleton.py --config configs/drain-louisville.json
    python3 create_image_pool_skeleton.py --niche drain-cleaning --services "Drain Cleaning,Hydro Jetting,Kitchen Drain Cleaning"

Creates, under /var/www/rar-image-pool/<niche-slug>/:
    hero/  home-summary/  home-about/  home-parallax/  city/   (site-wide, homepage only)
    services/<service-slug>/rect/                              (this service's card photo)
    services/<service-slug>/wide-1/                             (1st body photo)
    services/<service-slug>/wide-2/                             (2nd body photo)
    services/<service-slug>/wide-3/                             (3rd body photo)

Each folder gets a NAMING_CONVENTION.txt with a concrete example filename
for that specific folder — the script doesn't read filenames at all (it
just lists whatever image files exist in a folder and picks one), so this
naming is purely for your own browsing; use whatever's easiest to find.
"""
import argparse
import json
import os
import sys

POOL_ROOT = "/var/www/rar-image-pool"

SITE_WIDE_PURPOSES = ["hero", "home-summary", "home-about", "home-parallax", "city"]
SERVICE_PURPOSES   = ["rect", "wide-1", "wide-2", "wide-3"]


def slugify(s):
    return str(s).lower().replace(" ", "-").replace(",", "")


def write_naming_hint(folder, example_name):
    path = os.path.join(folder, "NAMING_CONVENTION.txt")
    if os.path.exists(path):
        return  # don't clobber if it's already there (e.g. re-run for a new service)
    with open(path, "w") as f:
        f.write(
            "Drop real photos in this folder — any number of them, any names.\n"
            "The script only checks that image files exist here; it never reads\n"
            "the filename. Naming below is a suggestion for your own browsing,\n"
            "not a requirement:\n\n"
            f"    {example_name}\n"
        )


def main():
    ap = argparse.ArgumentParser(description="Create an empty image-pool folder skeleton for a niche")
    ap.add_argument("--config", help="Path to a site config JSON (reads niche + services from it)")
    ap.add_argument("--niche", help="Niche slug, e.g. drain-cleaning (used only if --config is not given)")
    ap.add_argument("--services", help="Comma-separated service names (used only if --config is not given)")
    args = ap.parse_args()

    if args.config:
        with open(args.config) as f:
            cfg = json.load(f)
        niche_slug = slugify(cfg.get("primary_service_name") or cfg.get("niche", ""))
        services   = cfg.get("services", [])
        if not niche_slug:
            print("Config has no primary_service_name/niche field — pass --niche explicitly instead.")
            sys.exit(1)
    elif args.niche and args.services:
        niche_slug = slugify(args.niche)
        services   = [s.strip() for s in args.services.split(",") if s.strip()]
    else:
        print("Provide either --config <path>, or both --niche and --services.")
        sys.exit(1)

    niche_root = os.path.join(POOL_ROOT, niche_slug)
    created = []

    for purpose in SITE_WIDE_PURPOSES:
        folder = os.path.join(niche_root, purpose)
        os.makedirs(folder, exist_ok=True)
        write_naming_hint(folder, f"{niche_slug}-{purpose}-1.jpg")
        created.append(folder)

    for service in services:
        svc_slug = slugify(service)
        for purpose in SERVICE_PURPOSES:
            folder = os.path.join(niche_root, "services", svc_slug, purpose)
            os.makedirs(folder, exist_ok=True)
            write_naming_hint(folder, f"{niche_slug}-{purpose}-{svc_slug}-1.jpg")
            created.append(folder)

    print(f"Created/verified {len(created)} folders under {niche_root}")
    for c in created:
        print(f"  {c}")


if __name__ == "__main__":
    main()
