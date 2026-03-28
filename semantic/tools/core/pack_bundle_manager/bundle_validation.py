def validate_bundle_dependencies(db, bundle_id):
    bundle_cat_ids = db.get_bundle_cat_ids(bundle_id)
    problems = []

    for cat_id in sorted(bundle_cat_ids):
        deps = db.get_dependencies(cat_id)
        for depends_on_cat_id, dependency_type in deps:
            if dependency_type == "requires" and depends_on_cat_id not in bundle_cat_ids:
                problems.append({
                    "cat_id": cat_id,
                    "missing_dependency": depends_on_cat_id,
                    "dependency_type": dependency_type,
                })

    return problems