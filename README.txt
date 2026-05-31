LSP Backend Project Generator

How to use:
1. Save this file as generate_lsp_project.py
2. Run: python generate_lsp_project.py
3. Open the new folder named lsp_python_project in VS Code
4. In terminal:
   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install -r requirements.txt
   python -m uvicorn app.main:app --reload

Important:
- Use a stable Python version like 3.12 or 3.13
- Do not use Python alpha builds
- This is a starter backend scaffold
