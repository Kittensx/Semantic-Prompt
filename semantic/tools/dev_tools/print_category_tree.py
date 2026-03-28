import os

def build_tree(root):
    lines = []

    for current_path, dirs, files in os.walk(root):
        rel_path = os.path.relpath(current_path, root)
        depth = 0 if rel_path == "." else rel_path.count(os.sep) + 1

        indent = "  " * depth
        folder_name = os.path.basename(current_path)

        if rel_path == ".":
            lines.append(folder_name)
        else:
            lines.append(f"{indent}{folder_name}/")

    return lines


def write_tree(root, output_file="category_tree.txt"):
    tree_lines = build_tree(root)

    with open(output_file, "w", encoding="utf-8") as f:
        for line in tree_lines:
            f.write(line + "\n")

    print(f"Category tree written to: {output_file}")


if __name__ == "__main__":
    packs_root = r"C:\Programs\A1111\stable-diffusion-webui\extensions\semantic_prompt\semantic\packs"
    write_tree(packs_root)