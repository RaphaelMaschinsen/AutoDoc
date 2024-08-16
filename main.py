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
import os
import sys
import re

from openai import OpenAI
from typing import List, Dict, Tuple

# Initialize the OpenAI client
client = OpenAI(api_key="YOUR-API-KEY")

INTERMEDIATE_RESULTS_FILE = "intermediate_results.json"

def load_intermediate_results() -> Dict[str, Tuple[str, float]]:
    """Load intermediate results from a JSON file."""
    if os.path.exists(INTERMEDIATE_RESULTS_FILE):
        with open(INTERMEDIATE_RESULTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}

def save_intermediate_results(results: Dict[str, Tuple[str, float]]):
    """Save intermediate results to a JSON file."""
    with open(INTERMEDIATE_RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=4)

def list_files(root_dir: str, root_file_types: List[str], recursive_dirs: List[str], recursive_file_types: List[str]) -> Dict[str, List[str]]:
    """Lists files in the root directory non-recursively and in specified folders recursively."""
    project_structure = {}

    # Scan the root directory (non-recursively)
    print(f"Scanning root directory: {root_dir}")
    root_files = [os.path.join(root_dir, file) for file in os.listdir(root_dir) if
                  any(file.endswith(ft) for ft in root_file_types)]
    if root_files:
        project_structure[root_dir] = root_files
        print(f"Found files in root directory: {root_files}")

    # Scan the specified directories (recursively)
    for recursive_dir in recursive_dirs:
        print(f"Scanning directory: {recursive_dir}")
        for subdir, _, files in os.walk(recursive_dir):
            relevant_files = [os.path.join(subdir, file) for file in files if
                              any(file.endswith(ft) for ft in recursive_file_types)]
            if relevant_files:
                project_structure[subdir] = relevant_files
                print(f"Found files in {subdir}: {relevant_files}")

    return project_structure


def pair_header_and_source_files(files: List[str]) -> Dict[str, List[str]]:
    """Pairs .h and .cpp files with the same name, shader files, and identifies unpaired files."""
    paired_files = {}
    unpaired_files = []

    # Separate header, source, and shader files
    header_files = {os.path.splitext(os.path.basename(file))[0]: file for file in files if file.endswith(".h")}
    source_files = {os.path.splitext(os.path.basename(file))[0]: file for file in files if file.endswith(".cpp")}
    shader_files = {os.path.splitext(os.path.basename(file))[0]: file for file in files if file.endswith(".glsl")}

    # Pair header and source files
    for base_name in set(header_files.keys()).union(set(source_files.keys())):
        if base_name in header_files and base_name in source_files:
            paired_files[base_name] = [header_files[base_name], source_files[base_name]]
        elif base_name in header_files:
            unpaired_files.append(header_files[base_name])
        elif base_name in source_files:
            unpaired_files.append(source_files[base_name])

    # Pair shader files (both paired and unpaired)
    shader_pairs = {}
    for base_name, file in shader_files.items():
        if base_name.endswith("_fragment") or base_name.endswith("_vertex"):
            core_name = base_name.rsplit('_', 1)[0]
            if core_name in shader_pairs:
                shader_pairs[core_name].append(file)
            else:
                shader_pairs[core_name] = [file]
        else:
            # Handle unpaired shaders
            unpaired_files.append(file)

    # Add shader pairs to paired_files
    for core_name, files in shader_pairs.items():
        if len(files) > 1:
            paired_files[core_name] = files
        else:
            unpaired_files.extend(files)

    # Add any non-paired files (like CMakeLists.txt) to unpaired_files
    for file in files:
        if not file.endswith((".h", ".cpp", ".glsl")) and file not in unpaired_files:
            unpaired_files.append(file)

    return {**paired_files, "unpaired_files": unpaired_files}

def read_file(file_path: str) -> str:
    """Reads the content of a file."""
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()

def should_lower_relevance_due_to_tests(file_path: str, file_content: str) -> bool:
    """Determines if a file is likely a test file and should have lower relevance."""
    if 'test' in os.path.basename(file_path).lower() and 'main' in file_content.lower():
        return True
    return False

def create_prompt(file_names: List[str], file_content: str, project_overview: str, is_test_file: bool) -> str:
    """Creates a prompt for summarizing code files."""
    # Check if it's a single file or multiple files
    if len(file_names) == 1:
        file_intro = f"The following is a code file named {file_names[0]}.\n\n"
    else:
        file_intro = f"The following are code files named {', '.join(file_names)}.\n\n"

    base_prompt = (
        f"Here is an overview of the project structure:\n{project_overview}\n\n"
        f"{file_intro}"
        "Please provide a detailed summary. Start with a brief overview, then describe the public interface in detail, "
        "and finally explain the inner workings of the file(s). For the inner workings, also explain how the code is implemented. "
        "It should be structured into 5 sections: 1. Filename 2. Summary 3. Public Interface 4. Implementation 5. The relevance score. "
        "After the summary, always assign a relevance score from 1 to 10 indicating its importance to the overall project "
        "(1 being not important, 10 being critically important). Be especially critical and try to assign lower scores "
        "unless the file(s) are crucial to the main functionality of the project. The main file itself should "
        "always have a score of 10. "
        "Format the relevance score like this: "
        "[Relevance score: 7].\n\n"
        f"{file_content}"
    )

    if is_test_file:
        base_prompt += (
            "\n\nNote: This file appears to be a test file."
        )

    return base_prompt

def extract_relevance_score(summary: str) -> float:
    """Extracts the relevance score from the summary using regular expressions for robustness."""
    match = re.search(r'Relevance score:\s*(\d+)', summary)
    if match:
        return float(match.group(1))
    return 5.0  # Default to 5 if parsing fails

def summarize_files(file_paths: List[str], file_contents: List[str], results: Dict[str, Tuple[str, float]],
                    project_overview: str) -> Tuple[str, float]:
    """Uses OpenAI to summarize the combined content of related files and assign a relevance score."""
    combined_content = "\n\n".join(file_contents)
    file_key = '|'.join(sorted(file_paths))
    file_names = [os.path.basename(fp) for fp in file_paths]

    if file_key in results:
        print(f"Skipping {file_key}, already summarized.")
        return results[file_key]

    # Add a comment listing all filenames to help with proper identification
    combined_content = f"/* Combined files: {', '.join(file_names)} */\n\n" + combined_content

    is_test_file = any(should_lower_relevance_due_to_tests(fp, fc) for fp, fc in zip(file_paths, file_contents))
    prompt = create_prompt(file_names, combined_content, project_overview, is_test_file)

    print(f"Processing files: {file_paths}")
    completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant specialized in summarizing code files."
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

def generate_readme(summaries: Dict[str, Tuple[str, float]], project_structure: Dict[str, List[str]]) -> str:
    """Generates a final README by combining all summaries and project structure."""
    structure_description = "\n".join(
        [f"{key}:\n  " + "\n  ".join(files) for key, files in project_structure.items() if key != "unpaired_files"])

    # Sort summaries by relevance score
    sorted_summaries = sorted(summaries.items(), key=lambda item: item[1][1], reverse=True)

    summary_content = "\n\n".join(
        [f"## {os.path.basename(name)}\n\n{summary}" for name, (summary, _) in sorted_summaries])

    print("Generating final README...")
    final_summary = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant tasked with generating comprehensive README files."
            },
            {
                "role": "user",
                "content": f"Please generate a README file that includes: \n"
                           f"1. A project overview at the start and then \n"
                           f"2. A tree structure graph of the project and then \n"
                           f"3. The full summaries of the provided code (summaries with subsections for (Filename(s), "
                           f"Overview, Public Interface/Usage, Implementation) sorted by relevance (but don't mention "
                           f"those relevance scores).\n\n"
                           f"End the README immediately after the summaries and don't mention license, contribution "
                           f"or anything else after the summary of the last component.\n"
                           f"Format the titles of the components in a recognizable way.\n\n"
                           f"Project structure:\n{structure_description}\n\n"
                           f"Component summaries:\n{summary_content}"
            }
        ]
    )

    return final_summary.choices[0].message.content

def clean_up_readme(readme_content: str) -> str:
    """Cleans up the README content to ensure consistency and proper formatting."""
    print("Cleaning up README content...")
    completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant specialized in formatting and polishing written content."
            },
            {
                "role": "user",
                "content": f"Please fix the following README content: Improve the Overview and explain what the project"
                           f"does and how it functions. But don't use complimenting words like 'sophisticated' or "
                           f"'complex'. This readme is meant as documentation to understand the project better."
                           f" Also for the rest of the readme: Add contextual information "
                           f"and details where necessary.\n "
                           f"IMPORTANT: Keep the structure of the individual summaries"
                           f"(Filename(s), Overview, Public Interface/Usage, Implementation). And don't shorten those"
                           f"sections. If anything add contextual information about other parts of the readme if that"
                           f"helps with the understanding. \n IMPORTANT: Change the title of that section to a normal"
                           f"word that is not a filename nor a variable name. \n"
                           f"This is the first time it is being processed by an AI that"
                           f"has full access to all of those summaries of the code together."
                           f"Ensure consistency in formatting and fix any grammatical errors, and make sure the "
                           f"document is well-structured and professional:\n\n"
                           f"{readme_content}"
            }
        ]
    )
    return completion.choices[0].message.content

def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_readme.py <root_dir> <folder1> <folder2> ... <folderN>")
        sys.exit(1)

    root_dir = sys.argv[1]
    folders_to_analyze = sys.argv[2:]
    file_types = [".h", ".cpp", ".glsl", "CMakeLists.txt"]  # Add other relevant file types

    results = load_intermediate_results()

    # Step 1: List files in the root directory (non-recursively) and in specified folders (recursively)
    project_structure = list_files(root_dir, file_types, folders_to_analyze, file_types)
    project_overview = "\n".join([f"{subdir}:\n  " + "\n  ".join(files) for subdir, files in project_structure.items()])

    # Step 2: Pair .h and .cpp files and summarize each pair or single file
    summaries = {}
    for subdir, files in project_structure.items():
        paired_files = pair_header_and_source_files(files)

        for name, file_paths in paired_files.items():
            if name != "unpaired_files":
                file_contents = [read_file(file_path) for file_path in file_paths]
                summary, relevance = summarize_files(file_paths, file_contents, results, project_overview)
                summaries[name] = (summary, relevance)
                print(f"Processed {name} with relevance score {relevance}.")

        # Summarize unpaired files
        for file_path in paired_files.get("unpaired_files", []):
            file_content = read_file(file_path)
            summary, relevance = summarize_files([file_path], [file_content], results, project_overview)
            summaries[os.path.basename(file_path)] = (summary, relevance)
            print(f"Processed {file_path} with relevance score {relevance}.")

    # Step 3: Generate the final README
    readme_content = generate_readme(summaries, project_structure)

    # Step 4: Clean up the README content
    cleaned_readme_content = clean_up_readme(readme_content)

    # Step 5: Write the cleaned README to a file in the root directory with UTF-8 encoding
    readme_path = os.path.join(root_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as readme_file:
        readme_file.write(cleaned_readme_content)

    print(f"README.md has been generated and cleaned at {readme_path}")

if __name__ == "__main__":
    main()
