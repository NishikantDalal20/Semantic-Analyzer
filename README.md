# TypeScope — Type Checker & Semantic Analyzer with Scope Detection

An educational compiler-design mini project built with Python, Flask, HTML, CSS and JavaScript.

## Features
- Lexical analysis with token kind and line/column positions; skips line and block comments
- Parser for a small C-like language
- Semantic type checking for `int`, `float`, `bool`, and `string`
- Undeclared-variable and same-scope redeclaration diagnostics
- Assignment and initialization compatibility checks (int can be promoted to float)
- Global and block scope symbol tables, including shadowed names
- Warnings for possible use before initialization
- Interactive AST viewer and token stream
- Three-address intermediate code generation
- Basic constant folding optimization
- Responsive interface and dark theme
- Error suggestions with line and column positions

## Run locally
Requires Python 3.9+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

## Language subset
Supports declarations (`int x = 4;`), assignments, `{ ... }` blocks, `if (...) ... else ...`, `while (...) ...`, arithmetic/comparison/logical expressions, parentheses, and `//` or `/* ... */` comments.

## Limitations
This is a teaching/demo compiler, not a full C compiler. Functions, arrays, structs, function calls, return statements, and complete control-flow code generation are not implemented. `if`/`while` intermediate code is illustrative rather than a complete jump-based representation. Constant folding handles numeric literal arithmetic only; division by zero is left unchanged. Definite-assignment analysis is a simple warning, not full control-flow analysis.
