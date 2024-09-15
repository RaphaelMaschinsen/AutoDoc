"""
MIT License

Copyright (c) 2024 Raphael Maschinsen
raphaelmaschinsen@gmail.com

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import sys
import re
import os
from openai import OpenAI
from typing import List, Dict, Tuple, Any

# Initialize the OpenAI client
client = OpenAI(
    api_key="YOUR-API-KEY")

INTERMEDIATE_RESULTS_FILE = "intermediate_results.json"

def load_intermediate_results() -> Dict[str, Dict[str, Any]]:
    """Load intermediate results from a JSON file."""
    if os.path.exists(INTERMEDIATE_RESULTS_FILE):
        print("Loading intermediate results from file...")
        with open(INTERMEDIATE_RESULTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    print("No intermediate results found. Starting fresh...")
    return {}


def save_intermediate_results(results: Dict[str, Dict[str, Any]]):
    """Save intermediate results to a JSON file."""
    print("Saving intermediate results to file...")
    with open(INTERMEDIATE_RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=4)


def list_files(root_dir: str, root_file_types: List[str], recursive_dirs: List[str], recursive_file_types: List[str]) -> Dict[str, List[str]]:
    """Lists files in the root directory non-recursively and in specified folders recursively."""
    print(f"Listing files in {root_dir} and subdirectories...")
    project_structure = {}

    # Scan the root directory (non-recursively)
    root_files = [os.path.join(root_dir, file) for file in os.listdir(root_dir) if
                  any(file.endswith(ft) for ft in root_file_types)]
    if root_files:
        project_structure[root_dir] = root_files

    # Scan the specified directories (recursively)
    for recursive_dir in recursive_dirs:
        print(f"Recursively listing files in {recursive_dir}...")
        for subdir, _, files in os.walk(recursive_dir):
            relevant_files = [os.path.join(subdir, file) for file in files if
                              any(file.endswith(ft) for ft in recursive_file_types)]
            if relevant_files:
                project_structure[subdir] = relevant_files

    print(f"File listing complete. Found {sum(len(files) for files in project_structure.values())} files.")
    return project_structure


def pair_header_and_source_files(files: List[str]) -> Dict[str, List[str]]:
    """Pairs .h and .cpp files with the same name, shader files, and identifies unpaired files."""
    print("Pairing header, source, shader, and other files...")
    paired_files = {}
    unpaired_files = []

    header_files = {os.path.splitext(os.path.basename(f))[0]: f for f in files if f.endswith(".h")}
    source_files = {os.path.splitext(os.path.basename(f))[0]: f for f in files if f.endswith(".cpp")}
    shader_files = {os.path.splitext(os.path.basename(f))[0]: f for f in files if f.endswith(".glsl")}
    cmake_files = [f for f in files if "CMakeLists.txt" in os.path.basename(f)]

    # Pair header and source files
    for base_name in set(header_files.keys()).union(set(source_files.keys())):
        if base_name in header_files and base_name in source_files:
            paired_files[base_name] = [header_files[base_name], source_files[base_name]]
        elif base_name in header_files:
            unpaired_files.append(header_files[base_name])
        elif base_name in source_files:
            unpaired_files.append(source_files[base_name])

    # Pair shader files
    shader_pairs = pair_shader_files(shader_files)
    paired_files.update(shader_pairs)

    # Add CMake files
    for cmake_file in cmake_files:
        paired_files[os.path.basename(cmake_file)] = [cmake_file]

    # Add any unpaired files (shader files that weren't paired, or other files)
    unpaired_files.extend(
        f for f in files if f not in unpaired_files and not f.endswith((".h", ".cpp", ".glsl")) and f not in paired_files.values()
    )
    paired_files["unpaired_files"] = unpaired_files

    print(f"Pairing complete. Paired files: {len(paired_files) - 1}, Unpaired files: {len(unpaired_files)}")
    return paired_files


def pair_shader_files(shader_files: Dict[str, str]) -> Dict[str, List[str]]:
    """Pairs shader files based on naming conventions and sorts them to ensure paired shaders are next to each other."""
    print("Pairing shader files...")
    paired_files = {}
    unpaired_files = []

    for base_name, file_path in shader_files.items():
        if base_name.endswith("_fragment") or base_name.endswith("_vertex"):
            core_name = base_name.rsplit('_', 1)[0]
            if core_name in paired_files:
                paired_files[core_name].append(file_path)
                # Sort the shaders within the pair to ensure consistent order
                paired_files[core_name].sort()
            else:
                paired_files[core_name] = [file_path]
        else:
            paired_files[base_name] = [file_path]  # Ensure unpaired files are still included

    # Move unpaired shader files into the unpaired list if they have not been paired
    for core_name, files in list(paired_files.items()):
        if len(files) < 2:
            unpaired_files.extend(files)
            del paired_files[core_name]

    print(f"Shader pairing complete. Paired shaders: {len(paired_files)}, Unpaired shaders: {len(unpaired_files)}")
    paired_files["unpaired_shaders"] = unpaired_files  # Add unpaired shaders separately
    return paired_files


def read_file(file_path: str) -> str:
    """Reads the content of a file."""
    print(f"Reading file: {file_path}")
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def should_lower_relevance_due_to_tests(file_path: str, file_content: str) -> bool:
    """Determines if a file is likely a test file and should have lower relevance."""
    is_test_file = 'test' in os.path.basename(file_path).lower() and 'main' in file_content.lower()
    if is_test_file:
        print(f"File {file_path} identified as a test file.")
    return is_test_file


def create_component_summary_prompt(file_names: List[str], file_content: str, project_overview: str, is_test_file: bool) -> str:
    """Creates a prompt for summarizing code files with consistent formatting."""
    if not file_names:
        raise ValueError("The file_names list is empty. Cannot create a summary prompt without file names.")

    file_intro = f"The following are code files named {', '.join(file_names)}.\n\n" if len(
        file_names) > 1 else f"The following is a code file named {file_names[0]}.\n\n"

    base_prompt = (
        f"Here is an overview of the project structure:\n{project_overview}\n\n"
        f"{file_intro}"
        "Please provide a detailed summary. Start with a detailed overview, then describe the public interface in detail, "
        "and finally explain the inner workings of the file(s). For the inner workings, also explain how the code is "
        "implemented (mostly in words and avoid code snippets as much as possible)."
        "It should be structured into 4 sections: ## (this title has to be the filename(s) without the path and "
        "if there are several files they should be formatted like this 'file1 & file2' and neither the word "
        "filename nor title should appear in this section), ### Overview, "
        "### Public Interface, and ### Implementation."
        "After the summary, always assign a relevance score from 1 to 10 indicating its importance to the overall project "
        "(1 being not important, 10 being critically important). Be especially critical and try to assign lower scores "
        "unless the file(s) are crucial to the main functionality of the project. The main file itself should "
        "always have a score of 10. The CMakeLists.txt always a score of 0"
        "Format the relevance score exactly like this: [Relevance score: 7] but don't mention the relevance otherwise"
        "and don't add a title called Relevance, it should only be the score within the square brackets.\n\n"
        f"{file_content}"
    )

    if is_test_file:
        base_prompt += "\n\nNote: This file appears to be a test file."

    return base_prompt


def extract_relevance_score(summary: str) -> float:
    """Extracts the relevance score from the summary using regular expressions for robustness."""
    match = re.search(r'Relevance score:\s*(\d+)', summary)
    relevance = float(match.group(1)) if match else 5.0
    print(f"Extracted relevance score: {relevance}")
    return relevance


def summarize_component_files(file_paths: List[str], file_contents: List[str], results: Dict[str, Dict[str, Any]], project_overview: str) -> Tuple[str, float]:
    """Uses OpenAI to summarize the combined content of related files and assign a relevance score."""
    if not file_paths or not file_contents:
        print(f"file_paths: {file_paths}")  # Debugging statement
        print(f"file_contents: {file_contents}")  # Debugging statement
        raise ValueError("file_paths or file_contents is empty. Cannot summarize without valid file paths and contents.")

    file_paths = sorted(file_paths)
    file_key = '|'.join(file_paths)
    file_names = [os.path.basename(fp) for fp in file_paths]
    combined_content = "\n\n".join(file_contents)

    # Get current last modified times
    current_mtimes = [os.path.getmtime(fp) for fp in file_paths]

    if file_key in results:
        stored_data = results[file_key]
        stored_last_modified_times = stored_data.get('last_modified_times', [])

        if stored_last_modified_times == current_mtimes:
            print(f"Summary for {file_key} is up to date. Skipping...")
            return stored_data['summary'], stored_data['relevance']
        else:
            print(f"Files for {file_key} have been modified. Regenerating summary.")

    print(f"Summarizing files: {', '.join(file_names)}")
    combined_content = f"/* Combined files: {', '.join(file_names)} */\n\n" + combined_content

    is_test_file = any(should_lower_relevance_due_to_tests(fp, fc) for fp, fc in zip(file_paths, file_contents))
    prompt = create_component_summary_prompt(file_names, combined_content, project_overview, is_test_file)

    completion = client.chat.completions.create(
        model="gpt-4o",
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
    # Store the summary, relevance, and current_mtimes in results
    results[file_key] = {
        'summary': summary,
        'relevance': relevance,
        'last_modified_times': current_mtimes,
    }
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

    # Include all files in the structure description
    structure_description = "\n".join(
        [f"{key}:\n  " + "\n  ".join(files) for key, files in project_structure.items()]
    )

    print("Project overview and file tree generated.")
    return project_overview_content, structure_description


def extract_title_overview_and_tree(content: str) -> Tuple[str, str, str]:
    """Extracts the title, project overview, and file tree from the generated content."""
    print("Extracting title, project overview, and file tree...")
    title_marker = "Project Title:"
    overview_marker = "Project Overview:"
    file_tree_marker = "File Tree Graph:"

    title = extract_section(content, title_marker)
    overview = extract_section(content, overview_marker)
    file_tree = extract_section(content, file_tree_marker)

    print(f"Extracted title: {title}, overview: {overview[:30]}..., file tree: {file_tree[:30]}...")
    return title, overview, file_tree


def extract_section(content: str, marker: str) -> str:
    """Extracts a section from content based on a marker."""
    section_start = content.find(marker)
    if section_start == -1:
        return ""

    section_end = content.find("\n\n", section_start)
    if section_end == -1:
        section_end = len(content)

    section = content[section_start + len(marker):section_end].strip()

    return section


def generate_title_and_overview_with_tree(sorted_summaries: List[Tuple[str, Tuple[str, float]]], file_tree: str) -> Tuple[str, str, str]:
    """Generates the title, project overview, and file tree using GPT based on the 5 most relevant components."""
    print("Generating title, project overview, and file tree with GPT...")
    components_overview = "\n".join(
        [f"{os.path.basename(name)}: {summary.splitlines()[1]}" for name, (summary, _) in sorted_summaries])

    prompt = (
        f"Based on the following components and file tree, generate a project title, overview"
        f" and a file tree graph diagram with the root having the project name: \n\n"
        f"Components Overview: \n{components_overview}\n\n"
        f"File Tree: \n{file_tree}\n\n"
        f"Please ensure that the output includes a clear title, a detailed project overview, and the file tree diagram."
        f"Ensure that the the summary doesn't contain any markup characters and that the sections start with: "
        f"'Project Title:', 'Project Overview:' and 'File Tree Graph:'. Also ensure that the file tree graph is"
        f"surrounded by triple backticks."
    )

    completion = client.chat.completions.create(
        model="gpt-4o",
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

    title, overview, file_tree = extract_title_overview_and_tree(completion.choices[0].message.content)
    print(f"Generated title: {title}, overview length: {len(overview)}, file tree length: {len(file_tree)}")
    return title, overview, file_tree


def strip_markdown(text: str) -> str:
    """Strip markdown formatting, remove instances of 'Project Title' or 'Title', and strip colons, quotes, and leading spaces."""
    text = re.sub(r'\*\*|__|#|"|:|\s\s+', '', text)
    text = re.sub(r'\b(project title|title)\b', '', text, flags=re.IGNORECASE)
    return text.strip()


def generate_readme(title: str, project_overview: str, file_tree: str, summaries: Dict[str, Tuple[str, float]]) -> str:
    """Generates the final README by combining the title, project overview, file tree, and all component summaries."""
    print("Generating final README...")
    clean_title = strip_markdown(title)
    sorted_summaries = sorted(summaries.items(), key=lambda item: item[1][1], reverse=True)

    # Apply `remove_relevance_score` to each summary to properly format it
    summary_content_list = [remove_relevance_score(summary) for _, (summary, _) in sorted_summaries]
    summary_content = "\n\n".join(summary_content_list)

    readme_content = f"# {clean_title}\n\n## Project Overview\n\n{project_overview}\n\n## File Tree\n\n{file_tree}\n\n## Component Summaries\n\n{summary_content}"
    print("README content generated.")
    return readme_content


def remove_relevance_score(summary: str) -> str:
    """Remove the relevance score from the summary."""
    summary_lines = summary.splitlines()

    # Remove any line containing "Relevance score:"
    filtered_lines = [line for line in summary_lines if not re.search(r'Relevance score:', line)]

    return "\n".join(filtered_lines).strip()


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_readme.py <root_dir> <folder1> <folder2> ... <folderN>")
        sys.exit(1)

    root_dir = sys.argv[1]
    folders_to_analyze = sys.argv[2:]
    file_types = [".h", ".cpp", ".glsl", "CMakeLists.txt"]

    print("Loading intermediate results...")
    results = load_intermediate_results()

    print("Listing project files...")
    project_structure = list_files(root_dir, file_types, folders_to_analyze, file_types)
    project_overview = "\n".join([f"{subdir}:\n  " + "\n  ".join(files) for subdir, files in project_structure.items()])

    summaries = {}
    for subdir, files in project_structure.items():
        paired_files = pair_header_and_source_files(files)

        for name, file_paths in paired_files.items():
            if name != "unpaired_files" and file_paths:
                file_contents = [read_file(file_path) for file_path in file_paths if os.path.exists(file_path)]
                if file_contents:
                    summary, relevance = summarize_component_files(file_paths, file_contents, results, project_overview)
                    summaries[name] = (summary, relevance)
                else:
                    print(f"Warning: No content found for files {file_paths}. Skipping...")

        for file_path in paired_files.get("unpaired_files", []):
            file_content = read_file(file_path)
            summary, relevance = summarize_component_files([file_path], [file_content], results, project_overview)
            summaries[os.path.basename(file_path)] = (summary, relevance)

    print("Generating project overview and file tree...")
    project_overview_content, file_tree = generate_project_overview_and_file_tree(summaries, project_structure)

    print("Generating title, project overview, and file tree graph with GPT...")
    title, project_overview, file_tree_graph = generate_title_and_overview_with_tree(
        sorted(summaries.items(), key=lambda item: item[1][1], reverse=True)[:5], file_tree
    )

    print("Generating the final README...")
    readme_content = generate_readme(title, project_overview, file_tree_graph, summaries)
    readme_path = os.path.join(root_dir, "README.md")

    with open(readme_path, "w", encoding="utf-8") as readme_file:
        readme_file.write(readme_content)

    print(f"README.md has been generated at {readme_path}")


if __name__ == "__main__":
    main()
