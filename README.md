# 🌳 Foltree

Foltree is a Python-based utility that helps you manage folder structures for your projects. It can:
- 📝 Generate folder structure documentation for README files
- 🔄 Convert AI-generated structures into actual folders
- 🎨 Provide a user-friendly GUI interface

> ⚠️ **Note**: Large structures may take a while to parse or might fail
> 
> 🐍 **Tested with**: Python 3.13.1

## ✨ Features

- 🖥️ Modern GUI interface using CustomTkinter
- 📂 Convert between folder structures and documentation
- 🔄 Bidirectional conversion (text to folders and folders to text)
- 🎯 Simple and intuitive user interface

## 🚀 Installation

### Prerequisites

- Python 3.13.1 or higher
- pip (Python package installer)

### Step 1: Create a Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/MacOS
python3 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash

# install from requirements.txt
pip install -r requirements.txt

# Or using pip
pip install customtkinter CTkToolTip
```

## 🎮 Usage

### Running with Python (Recommended)

1. Navigate to the project directory
2. Run the GUI application:
   ```bash
   python FoltreeGUI.py
   ```

### Building Executable (Optional)

Maybe later

## 🛠️ Development

### Project Structure

```
foltree/
├── FoltreeGUI.py    # Main application file
├── README.md        # This documentation
└── requirements.txt # The project's dependencies
```

## 💡 Future Improvements

- 📋 Copy button for easy structure copying
- 🔍 Search functionality for large structures
- 📤 Export/Import functionality

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.