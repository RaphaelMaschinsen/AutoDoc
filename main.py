import json
import os
import sys
import re

from openai import OpenAI
from typing import List, Dict, Tuple

# Initialize the OpenAI client
client = OpenAI(api_key="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")

INTERMEDIATE_RESULTS_FILE = "intermediate_results.json"


def load_intermediate_results() -> Dict[str, Tuple[str, float]]:
    """Load intermediate results from a JSON file."""
    if os.path.exists(INTERMEDIATE_RESULTS_FILE):
        print("Loading intermediate results...")
        with open(INTERMEDIATE_RESULTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}


def save_intermediate_results(results: Dict[str, Tuple[str, float]]):
    """Save intermediate results to a JSON file."""
    print("Saving intermediate results...")
    with open(INTERMEDIATE_RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=4)


def list_files(root_dir: str, root_file_types: List[str], recursive_dirs: List[str], recursive_file_types: List[str]) -> \
Dict[str, List[str]]:
    """Lists files in the root directory non-recursively and in specified folders recursively."""
    print("Listing files in the project...")
    project_structure = {}

    # Scan the root directory (non-recursively)
    root_files = [os.path.join(root_dir, file) for file in os.listdir(root_dir) if
                  any(file.endswith(ft) for ft in root_file_types)]
    if root_files:
        project_structure[root_dir] = root_files

    # Scan the specified directories (recursively)
    for recursive_dir in recursive_dirs:
        for subdir, _, files in os.walk(recursive_dir):
            relevant_files = [os.path.join(subdir, file) for file in files if
                              any(file.endswith(ft) for ft in recursive_file_types)]
            if relevant_files:
                project_structure[subdir] = relevant_files

    print(f"Project structure: {project_structure}")
    return project_structure


def pair_header_and_source_files(files: List[str]) -> Dict[str, List[str]]:
    """Pairs .h and .cpp files with the same name, shader files, and identifies unpaired files."""
    print("Pairing header and source files...")
    paired_files = {}
    unpaired_files = []

    header_files = {os.path.splitext(os.path.basename(file))[0]: file for file in files if file.endswith(".h")}
    source_files = {os.path.splitext(os.path.basename(file))[0]: file for file in files if file.endswith(".cpp")}
    shader_files = {os.path.splitext(os.path.basename(file))[0]: file for file in files if file.endswith(".glsl")}

    for base_name in set(header_files.keys()).union(set(source_files.keys())):
        if base_name in header_files and base_name in source_files:
            paired_files[base_name] = [header_files[base_name], source_files[base_name]]
        elif base_name in header_files:
            unpaired_files.append(header_files[base_name])
        elif base_name in source_files:
            unpaired_files.append(source_files[base_name])

    shader_pairs = {}
    for base_name, file in shader_files.items():
        if base_name.endswith("_fragment") or base_name.endswith("_vertex"):
            core_name = base_name.rsplit('_', 1)[0]
            if core_name in shader_pairs:
                shader_pairs[core_name].append(file)
            else:
                shader_pairs[core_name] = [file]
        else:
            unpaired_files.append(file)

    for core_name, files in shader_pairs.items():
        if len(files) > 1:
            paired_files[core_name] = files
        else:
            unpaired_files.extend(files)

    for file in files:
        if not file.endswith((".h", ".cpp", ".glsl")) and file not in unpaired_files:
            unpaired_files.append(file)

    paired_files["unpaired_files"] = unpaired_files

    print(f"Paired files: {paired_files}")
    return paired_files


def read_file(file_path: str) -> str:
    """Reads the content of a file."""
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def should_lower_relevance_due_to_tests(file_path: str, file_content: str) -> bool:
    """Determines if a file is likely a test file and should have lower relevance."""
    if 'test' in os.path.basename(file_path).lower() and 'main' in file_content.lower():
        return True
    return False


def create_component_summary_prompt(file_names: List[str], file_content: str, project_overview: str, is_test_file: bool) -> str:
    """Creates a prompt for summarizing code files with consistent formatting."""
    if len(file_names) == 1:
        file_intro = f"The following is a code file named {file_names[0]}.\n\n"
    else:
        file_intro = f"The following are code files named {', '.join(file_names)}.\n\n"

    base_prompt = (
        f"Here is an overview of the project structure:\n{project_overview}\n\n"
        f"{file_intro}"
        "Please provide a detailed summary. Start with a brief overview, then describe the public interface in detail, "
        "and finally explain the inner workings of the file(s). For the inner workings, also explain how the code is implemented. "
        "It should be structured into 4 sections: ### Filename(s), #### Overview, #### Public Interface, and #### Implementation. "
        "After the summary, always assign a relevance score from 1 to 10 indicating its importance to the overall project "
        "(1 being not important, 10 being critically important). Be especially critical and try to assign lower scores "
        "unless the file(s) are crucial to the main functionality of the project. The main file itself should "
        "always have a score of 10. The CMakeLists.txt always a score of 0"
        "Format the relevance score like this: "
        "[Relevance score: 7].\n\n"
        f"{file_content}"
    )

    if is_test_file:
        base_prompt += "\n\nNote: This file appears to be a test file."

    return base_prompt


def extract_relevance_score(summary: str) -> float:
    """Extracts the relevance score from the summary using regular expressions for robustness."""
    match = re.search(r'Relevance score:\s*(\d+)', summary)
    if match:
        return float(match.group(1))
    return 5.0  # Default to 5 if parsing fails


def summarize_component_files(file_paths: List[str], file_contents: List[str], results: Dict[str, Tuple[str, float]],
                              project_overview: str) -> Tuple[str, float]:
    """Uses OpenAI to summarize the combined content of related files and assign a relevance score."""
    combined_content = "\n\n".join(file_contents)
    file_key = '|'.join(sorted(file_paths))
    file_names = [os.path.basename(fp) for fp in file_paths]

    if file_key in results:
        print(f"Skipping {file_key}, already summarized.")
        return results[file_key]

    print(f"Summarizing files: {file_names}")
    combined_content = f"/* Combined files: {', '.join(file_names)} */\n\n" + combined_content

    is_test_file = any(should_lower_relevance_due_to_tests(fp, fc) for fp, fc in zip(file_paths, file_contents))
    prompt = create_component_summary_prompt(file_names, combined_content, project_overview, is_test_file)

    completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant specialized in summarizing code files. "
                           "Please format the summaries with consistent markdown, including: "
                           "### Filename(s), #### Overview, #### Public Interface, #### Implementation."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )
    summary = completion.choices[0].message.content
    relevance = extract_relevance_score(summary)
    results[file_key] = (summary, relevance)
    save_intermediate_results(results)
    return summary, relevance


def generate_project_overview_and_file_tree(summaries: Dict[str, Tuple[str, float]],
                                            project_structure: Dict[str, List[str]]) -> Tuple[str, str]:
    """Generates a project overview and file tree using the 5 most relevant components."""
    print("Generating project overview and file tree...")
    sorted_summaries = sorted(summaries.items(), key=lambda item: item[1][1], reverse=True)[:5]

    project_overview_content = "This project consists of several components, with the following being the most crucial:\n"
    for name, (summary, relevance) in sorted_summaries:
        project_overview_content += f"- **{os.path.basename(name)}**: {summary.splitlines()[1]} [Relevance: {relevance}]\n"

    structure_description = "\n".join(
        [f"{key}:\n  " + "\n  ".join(files) for key, files in project_structure.items() if any(
            os.path.basename(name) in file for file in files for name, _ in sorted_summaries)]
    )

    print("Project overview content and structure description generated.")
    return project_overview_content, structure_description


def generate_title_and_overview_with_tree(sorted_summaries: List[Tuple[str, Tuple[str, float]]],
                                          file_tree: str) -> Tuple[str, str]:
    """Generates the title, project overview, and file tree using GPT based on the 5 most relevant components."""
    print("Generating title, project overview, and file tree with GPT...")

    components_overview = "\n".join([f"{os.path.basename(name)}: {summary.splitlines()[1]}"
                                     for name, (summary, _) in sorted_summaries])

    prompt = (
        f"Based on the following components and file tree, generate a project title, overview, and a file tree graph: \n\n"
        f"Components Overview: \n{components_overview}\n\n"
        f"File Tree: \n{file_tree}"
    )

    completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant specialized in generating project titles, overviews, and file tree graphs."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    result = completion.choices[0].message.content.split("\n\n")
    title = result[0].strip() if result else "Project Title"
    overview = result[1].strip() if len(result) > 1 else components_overview
    file_tree_graph = result[2].strip() if len(result) > 2 else file_tree

    return title, overview, file_tree_graph

def strip_markdown(text: str) -> str:
    """Strip markdown formatting, remove instances of 'Project Title' or 'Title', and strip colons and leading spaces."""
    # Remove markdown bold, italic, headers, extra spaces, and colons
    text = re.sub(r'\*\*|__|#|"|:|\s\s+', '', text)
    # Remove any instance of "Project Title" or "Title" (case insensitive)
    text = re.sub(r'\b(project title|title)\b', '', text, flags=re.IGNORECASE)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text

def generate_readme(title: str, project_overview: str, file_tree: str, summaries: Dict[str, Tuple[str, float]]) -> str:
    """Generates the final README by combining the title, project overview, file tree, and all component summaries."""
    print("Generating final README...")

    # Strip any markdown formatting and unwanted words from the title
    clean_title = strip_markdown(title)

    # Sort summaries by relevance
    sorted_summaries = sorted(summaries.items(), key=lambda item: item[1][1], reverse=True)

    summary_content_list = []

    for name, (summary, _) in sorted_summaries:
        # Remove the filename line (title) from the summary
        summary_lines = summary.splitlines()

        # Ensure there are at least two lines before attempting to remove the title
        if len(summary_lines) > 1:
            summary_without_title = "\n".join(summary_lines[1:]).strip()
        else:
            summary_without_title = summary.strip()

        # Add each component summary with consistent formatting
        summary_content_list.append(f"## {os.path.basename(name)}\n\n{summary_without_title}")

    # Join the component summaries with two newlines between each for clarity
    summary_content = "\n\n".join(summary_content_list)

    # Assemble the final README content
    readme_content = (
        f"# {clean_title}\n\n"  # Use the cleaned title
        f"## Project Overview\n\n{project_overview}\n\n"
        f"## File Tree\n\n{file_tree}\n\n"
        f"## Component Summaries\n\n{summary_content}"
    )

    print("Final README generated.")
    return readme_content


def main():
    print("Starting README generation process...")
    if len(sys.argv) < 3:
        print("Usage: python generate_readme.py <root_dir> <folder1> <folder2> ... <folderN>")
        sys.exit(1)

    root_dir = sys.argv[1]
    folders_to_analyze = sys.argv[2:]
    file_types = [".h", ".cpp", ".glsl", "CMakeLists.txt"]

    results = load_intermediate_results()

    print("Listing project files...")
    project_structure = list_files(root_dir, file_types, folders_to_analyze, file_types)
    project_overview = "\n".join([f"{subdir}:\n  " + "\n  ".join(files) for subdir, files in project_structure.items()])

    summaries = {}
    for subdir, files in project_structure.items():
        paired_files = pair_header_and_source_files(files)

        for name, file_paths in paired_files.items():
            if name != "unpaired_files":
                file_contents = [read_file(file_path) for file_path in file_paths]
                summary, relevance = summarize_component_files(file_paths, file_contents, results, project_overview)
                summaries[name] = (summary, relevance)

        for file_path in paired_files.get("unpaired_files", []):
            file_content = read_file(file_path)
            summary, relevance = summarize_component_files([file_path], [file_content], results, project_overview)
            summaries[os.path.basename(file_path)] = (summary, relevance)

    print("Generating project overview and file tree...")
    project_overview_content, file_tree = generate_project_overview_and_file_tree(summaries, project_structure)

    print("Generating title, project overview, and file tree graph with GPT...")
    title, project_overview, file_tree_graph = generate_title_and_overview_with_tree(sorted(summaries.items(), key=lambda item: item[1][1], reverse=True)[:5], file_tree)

    print("Generating the final README...")
    readme_content = generate_readme(title, project_overview, file_tree_graph, summaries)

    readme_path = os.path.join(root_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as readme_file:
        readme_file.write(readme_content)

    print(f"README.md has been generated at {readme_path}")


if __name__ == "__main__":
    main()
