# gitreview-gpt

`gitreview-gpt` reviews your git changes with ChatGPT 3.5 from command line and provides detailed review comments with line number references.

## ✨ Features

- **Reviews all your committed changes against the main branch**
- **Reviews your staged changes only**
- **Reviews your changed files separately**
- **Creates a commit message for your changes**

## 🚀 Usage

- `rgpt review`: Reviews all your changes against the `main` branch
- `rgpt review --staged`: Reviews all your staged changes
- `rgpt commit`: Creates a commit message for your staged changes

## 📋 Requirements

- Python >= 3.11

## 🔧 Installation

#### Create your personal OpenAI Api key and add it to your environment with:

```
export OPENAI_API_KEY=<YOUR_API_KEY>
```

#### Install `gitreview-gpt` with `pipx`:

```
pipx install git+https://github.com/fynnfluegge/gitreview-gpt.git
```
