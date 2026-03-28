import argparse
from pathlib import Path

from .bundle_db import BundleDB
from .bundle_importer import import_from_packs
from .bundle_exporter import export_bundle
from .bundle_diff import diff_bundle_vs_folder
from .bundle_versioning import compute_bundle_hash
from .bundle_validation import validate_bundle_dependencies

def cmd_create_db(args):
    db = BundleDB(args.db)
    db.initialize()
    print(f"Created bundle database: {args.db}")


def cmd_list_bundles(args):
    db = BundleDB(args.db)
    for bundle in db.list_bundles():
        print(bundle)


def cmd_import(args):
    db = BundleDB(args.db)
    import_from_packs(db, Path(args.packs_root), args.bundle)


def cmd_export(args):
    db = BundleDB(args.db)
    export_bundle(db, args.bundle, Path(args.out))


def cmd_diff(args):
    db = BundleDB(args.db)
    diff_bundle_vs_folder(db, args.bundle, Path(args.packs_root))
def cmd_validate(args):
    db = BundleDB(args.db)
    problems = validate_bundle_dependencies(db, args.bundle)

    if not problems:
        print(f"Bundle '{args.bundle}' passed dependency validation.")
        return

    print(f"Bundle '{args.bundle}' has missing dependencies:")
    for problem in problems:
        print(
            f"  {problem['cat_id']} -> missing {problem['missing_dependency']}"
        )


def cmd_bundle_info(args):
    db = BundleDB(args.db)
    info = db.get_bundle_info(args.bundle)
    if not info:
        print(f"Bundle not found: {args.bundle}")
        return

    (
        bundle_id,
        name,
        description,
        version,
        bundle_hash,
        min_app_version,
        schema_version,
        author,
    ) = info

    print(f"bundle_id: {bundle_id}")
    print(f"name: {name}")
    print(f"description: {description}")
    print(f"version: {version}")
    print(f"bundle_hash: {bundle_hash}")
    print(f"min_app_version: {min_app_version}")
    print(f"schema_version: {schema_version}")
    print(f"author: {author}")


def cmd_refresh_hash(args):
    db = BundleDB(args.db)
    packs = db.get_bundle_packs(args.bundle)
    bundle_hash = compute_bundle_hash(packs)
    db.update_bundle_hash(args.bundle, bundle_hash)
    print(f"Updated bundle hash for '{args.bundle}': {bundle_hash}")

def build_parser():
    parser = argparse.ArgumentParser(prog="pack_bundle_manager")

    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("create-bundle-db")
    p.add_argument("db")
    p.set_defaults(func=cmd_create_db)

    p = sub.add_parser("list-bundles")
    p.add_argument("--db", required=True)
    p.set_defaults(func=cmd_list_bundles)

    p = sub.add_parser("import-from-packs")
    p.add_argument("--db", required=True)
    p.add_argument("--packs-root", required=True)
    p.add_argument("--bundle", required=True)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("export-bundle")
    p.add_argument("--db", required=True)
    p.add_argument("--bundle", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("diff-bundle-vs-folder")
    p.add_argument("--db", required=True)
    p.add_argument("--bundle", required=True)
    p.add_argument("--packs-root", required=True)
    p.set_defaults(func=cmd_diff)
    
    p = sub.add_parser("bundle-info")
    p.add_argument("--db", required=True)
    p.add_argument("--bundle", required=True)
    p.set_defaults(func=cmd_bundle_info)

    p = sub.add_parser("refresh-bundle-hash")
    p.add_argument("--db", required=True)
    p.add_argument("--bundle", required=True)
    p.set_defaults(func=cmd_refresh_hash)

    p = sub.add_parser("validate-bundle")
    p.add_argument("--db", required=True)
    p.add_argument("--bundle", required=True)
    p.set_defaults(func=cmd_validate)

    return parser



def main():
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()