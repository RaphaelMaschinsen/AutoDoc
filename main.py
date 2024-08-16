import json
import os
import sys

from openai import OpenAI
from typing import List, Dict, Tuple

# Initialize the OpenAI client
client = OpenAI(api_key="sk-proj-C4yrFKiqJW2iYnUcTp6AofnM2AOqbC5n5SAqInNuy-MpNzGSDYFz95XKz8NH75vje6d6f2OzyoT3BlbkFJzIol"
                        "AXoDUFgNIPZ-OGw5JVefrYpDyUqyU19DEA_k-MM8JUXwxfG6Y2am-IGtLYMqQ8beyQKr8A")

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

def analyze_cmake(root_dir: str, results: Dict[str, Tuple[str, float]]) -> str:
    """Analyzes the CMakeLists.txt file in the root directory."""
    cmake_file = os.path.join(root_dir, "CMakeLists.txt")
    if not os.path.exists(cmake_file):
        print(f"No CMakeLists.txt found in {root_dir}")
        return ""

    if cmake_file in results:
        print(f"Skipping {cmake_file}, already summarized.")
        return results[cmake_file][0]

    cmake_content = read_file(cmake_file)
    summary, relevance = summarize_file(cmake_file, cmake_content, project_overview="")
    results[cmake_file] = (summary, relevance)
    save_intermediate_results(results)

    return summary

def list_files(root_dirs: List[str], file_types: List[str]) -> Dict[str, List[str]]:
    """Recursively lists files in the directories matching the file types."""
    project_structure = {}

    for root_dir in root_dirs:
        for subdir, _, files in os.walk(root_dir):
            relevant_files = [os.path.join(subdir, file) for file in files if
                              any(file.endswith(ft) for ft in file_types)]
            if relevant_files:
                project_structure[subdir] = relevant_files

    return project_structure

def pair_header_and_source_files(files: List[str]) -> Dict[str, List[str]]:
    """Pairs .h and .cpp files with the same name."""
    paired_files = {}
    unpaired_files = []

    for file in files:
        base_name = os.path.splitext(os.path.basename(file))[0]
        if file.endswith(".h"):
            paired_files[base_name] = [file]
        elif file.endswith(".cpp"):
            if base_name in paired_files:
                paired_files[base_name].append(file)
            else:
                paired_files[base_name] = [file]
        else:
            unpaired_files.append(file)

    return {**paired_files, "unpaired_files": unpaired_files}

def read_file(file_path: str) -> str:
    """Reads the content of a file."""
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()

def summarize_file(file_path: str, file_content: str, project_overview: str) -> Tuple[str, float]:
    """Uses OpenAI to summarize the file content and assign a relevance score."""
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant specialized in summarizing code files."
            },
            {
                "role": "user",
                "content": f"Here is an overview of the project structure:\n{project_overview}\n\n"
                           f"Please provide a detailed summary of the following code file. \n "
                           f"1. Start with an detailed overview (with the title 'Overview') "
                           f"in full sentences and then, \n"
                           f"2. describe the public interface (how the code is supposed to be used from outside of this"
                           f"file) in detail in a bullet point manner, and finally \n "
                           f"3. explain in detail the inner workings of the file again in full sentences. \n\n"
                           f"At the end, as the last thing of your answer, "
                           f"assign a relevance score from 1 to 10 indicating its"
                           f" importance to the overall project (1 being not important, 10 being critically important, "
                           f"the main should always be a 10 and test files below 5. Cmake files also below 5)."
                           f" Be especially critical and try to assign lower scores unless the file is crucial to the"
                           f" main functionality of the project. Format the relevance score like "
                           f"this: '[Relevance score:7]'.\n\n"
                           f"{file_content}"
            }
        ]
    )
    summary = completion.choices[0].message.content
    relevance_str = summary.split('Relevance score:')[-1].strip().replace("]", "")
    relevance = float(relevance_str) if relevance_str.isdigit() else 5.0  # Default to 5 if parsing fails
    return summary, relevance

def summarize_files(file_paths: List[str], file_contents: List[str], results: Dict[str, Tuple[str, float]],
                    project_overview: str) -> Tuple[str, float]:
    """Uses OpenAI to summarize the combined content of related files and assign a relevance score."""
    combined_content = "\n\n".join(file_contents)
    file_key = '|'.join(sorted(file_paths))

    if file_key in results:
        print(f"Skipping {file_key}, already summarized.")
        return results[file_key]

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant specialized in summarizing code files."
            },
            {
                "role": "user",
                "content": f"Here is an overview of the project structure:\n{project_overview}\n\n"
                           f"Please provide a detailed summary of the following code files."
                           f"1. Start with an detailed overview (with the title 'Overview') "
                           f"in full sentences and then, \n"
                           f"2. describe the public interface (how the code is supposed to be used from outside of this"
                           f"file) in detail in a bullet point manner, and finally \n "
                           f"3. explain in detail the inner workings of the file again in full sentences. \n\n"
                           f"At the end, as the last thing of your answer, "
                           f"assign a relevance score from 1 to 10 indicating its"
                           f" importance to the overall project (1 being not important, 10 being critically important, "
                           f"the main should always be a 10 and test files below 5. Cmake files also below 5)."
                           f" Be especially critical and try to assign lower scores unless the file is crucial to the"
                           f" main functionality of the project. Format the relevance score like "
                           f"this: '[Relevance score:7]'.\n\n"
                           f"{combined_content}"
            }
        ]
    )
    summary = completion.choices[0].message.content
    relevance_str = summary.split('Relevance score:')[-1].strip().replace("]", "")
    relevance = float(relevance_str) if relevance_str.isdigit() else 5.0  # Default to 5 if parsing fails
    results[file_key] = (summary, relevance)
    save_intermediate_results(results)
    return summary, relevance

def generate_readme(cmake_summary: str, summaries: Dict[str, Tuple[str, float]],
                    project_structure: Dict[str, List[str]]) -> str:
    """Generates a final README by combining all summaries and project structure."""
    structure_description = "\n".join(
        [f"{key}:\n  " + "\n  ".join(files) for key, files in project_structure.items() if key != "unpaired_files"])

    # Sort summaries by relevance score
    sorted_summaries = sorted(summaries.items(), key=lambda item: item[1][1], reverse=True)

    summary_content = "\n\n".join(
        [f"## {os.path.basename(name)}\n\n{summary}" for name, (summary, _) in sorted_summaries])

    final_summary = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant tasked with generating comprehensive README files."
            },
            {
                "role": "user",
                "content": f"Please generate a README file that includes: \n"
                           f"1. A detailed project overview/summary at the start that is based on your understanding of"
                           f" the Project Structure and the Component Summaries provided and then \n"
                           f"2. A simple tree structure graph of the project and then \n"
                           f"3. The summaries of the relevant components, sorted by relevance (but don't mention those "
                           f"relevance scores).\n\n"
                           f"End the README immediately after the summaries and don't mention license, contribution "
                           f"or anything else after the summary of the last component.\n"
                           f"Format the titles of the components in a recognizable way.\n\n"
                           f"Project structure:\n{structure_description}\n\n"
                           f"Component summaries:\n{summary_content}"
            }
        ]
    )

    return final_summary.choices[0].message.content

def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_readme.py <root_dir> <folder1> <folder2> ... <folderN>")
        sys.exit(1)

    root_dir = sys.argv[1]
    folders_to_analyze = sys.argv[2:]
    file_types = [".h", ".cpp", ".glsl", "CMakeLists.txt"]  # Add other relevant file types

    results = load_intermediate_results()

    # Step 1: Analyze the CMakeLists.txt file in the root directory
    cmake_summary = analyze_cmake(root_dir, results)

    # Step 2: List all relevant files in the specified folders
    project_structure = list_files(folders_to_analyze, file_types)
    project_overview = "\n".join([f"{subdir}:\n  " + "\n  ".join(files) for subdir, files in project_structure.items()])

    # Step 3: Pair .h and .cpp files and summarize each pair or single file
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

    # Step 4: Generate the final README
    readme_content = generate_readme(cmake_summary, summaries, project_structure)

    # Step 5: Write the README to a file in the root directory with UTF-8 encoding
    readme_path = os.path.join(root_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as readme_file:
        readme_file.write(readme_content)

    print(f"README.md has been generated at {readme_path}")

if __name__ == "__main__":
    main()
