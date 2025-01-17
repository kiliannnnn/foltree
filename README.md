# Foltree

Foltree is a small program I made with python that aims to help me writing folders structure for the readme files of my projects instead of doing it manually or with AI. It can also do the other way job, convert structure given by AI tools into real folders.

To start the program, either use python
```python
python .\FoltreeGUI.py
```
Or double click the .exe program located inside the dist
***I experienced some problems using the executable version, you might use the python version for more stability***

***The program is working well but no security were added, avoid giving an enormous folder to the tool.***

## File structure

```
├── foltree
│   ├── FoltreeGUI.py
│   ├── FoltreeGUI.spec
│   ├── README.md
│   ├── build
│   │   ├── FoltreeGUI
│   │   │   ├── Analysis-00.toc
│   │   │   ├── base_library.zip
│   │   │   ├── EXE-00.toc
│   │   │   ├── FoltreeGUI.pkg
│   │   │   ├── PKG-00.toc
│   │   │   ├── PYZ-00.pyz
│   │   │   ├── PYZ-00.toc
│   │   │   ├── warn-FoltreeGUI.txt
│   │   │   ├── xref-FoltreeGUI.html
│   │   │   ├── localpycs
│   │   │   │   ├── pyimod01_archive.pyc
│   │   │   │   ├── pyimod02_importers.pyc
│   │   │   │   ├── pyimod03_ctypes.pyc
│   │   │   │   ├── pyimod04_pywin32.pyc
│   │   │   │   ├── struct.pyc
│   ├── dist
│   │   ├── FoltreeGUI.exe
```

***This structure was made using Foltree but the .git folder was removed by hand***

## Upgrade ideas

- Excluding the masked folders from the text view
- Smooth the edges with some polished characters (└─, └)
