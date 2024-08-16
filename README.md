# AutoDoc

## Overview

**AutoDoc** is a tool designed to automatically generate detailed and structured documentation for your codebase. By analyzing the structure of your project and examining the code files, AutoDoc produces a comprehensive README file that provides an overview of your project, summaries of individual components, and details on how they interact. This makes it easier for developers to understand and navigate your codebase.

## Features

- **Automatic Documentation Generation**: Generates a detailed README based on your project's code structure.
- **Code Summaries**: Provides summaries for individual files, including details on their public interface and implementation.
- **Support for Paired Files**: Automatically pairs related files (e.g., `.h` and `.cpp`, shader files) and generates combined summaries.
- **Customizable Structure**: Ensures that the README structure can be easily tailored to your project's needs.
- **Intelligent Relevance Scoring**: Assigns relevance scores to different components of your project to prioritize critical files.

## Installation

To install AutoDoc, clone the repository and install the required dependencies:

    git clone https://github.com/yourusername/AutoDoc.git
    cd AutoDoc
    pip install -r requirements.txt

## Usage

To generate documentation for your project, run the `main.py` script with the root directory of your project and any subdirectories you want to include:

    python main.py <root_dir> <folder1> <folder2> ... <folderN>

### Example

    python main.py MyProject MyProject/src MyProject/include

This will generate a `README.md` file in the root directory of your project, containing an overview of the project structure and summaries of the relevant components.

## Configuration

AutoDoc is designed to be flexible and can be configured to meet your specific documentation needs. The default file types to be processed are `.h`, `.cpp`, `.glsl`, and `CMakeLists.txt`. You can modify this in the script as needed.

## Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
