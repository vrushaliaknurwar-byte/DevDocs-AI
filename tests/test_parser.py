import tempfile
import os
from app.services.parser.python_parser import parse_python_file
from app.services.parser.js_parser import parse_javascript_file
from app.services.parser.parser_service import parse_code_file
from app.services.repo_cloner import is_binary_file


def test_python_function_and_class_chunking():
    code = """import os

def calculate_tax(income, rate=0.2):
    \"\"\"Calculate tax given income and rate.\"\"\"
    base = income * rate
    return base

class AccountManager:
    def __init__(self, owner):
        self.owner = owner
        self.balance = 0

    def deposit(self, amount):
        self.balance += amount
        return self.balance

async def fetch_user_data(user_id):
    return {"id": user_id, "name": "Test"}
"""
    chunks = parse_python_file(code, "services/account.py")

    assert len(chunks) == 3

    # Check function chunk
    tax_chunk = chunks[0]
    assert tax_chunk.name == "calculate_tax"
    assert tax_chunk.chunk_type == "function"
    assert tax_chunk.start_line == 3
    assert tax_chunk.end_line == 6
    assert "def calculate_tax" in tax_chunk.code_text
    assert tax_chunk.file_path == "services/account.py"

    # Check class chunk
    class_chunk = chunks[1]
    assert class_chunk.name == "AccountManager"
    assert class_chunk.chunk_type == "class"
    assert class_chunk.start_line == 8
    assert class_chunk.end_line == 15
    assert "class AccountManager:" in class_chunk.code_text
    assert "def deposit(self, amount):" in class_chunk.code_text

    # Check async function chunk
    async_chunk = chunks[2]
    assert async_chunk.name == "fetch_user_data"
    assert async_chunk.chunk_type == "function"
    assert async_chunk.start_line == 17
    assert async_chunk.end_line == 18
    assert "async def fetch_user_data" in async_chunk.code_text


def test_python_fallback_for_scripts_without_functions():
    code = """# Configuration script
DATABASE_HOST = "localhost"
DATABASE_PORT = 5432
APP_NAME = "DevDocs AI"
DEBUG = True
"""
    chunks = parse_python_file(code, "config/settings.py")
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert "DATABASE_HOST" in chunks[0].code_text


def test_javascript_function_and_class_chunking():
    code = """import React from 'react';

export function calculateDiscount(price, discountPercent) {
  if (discountPercent > 100) return 0;
  return price * (1 - discountPercent / 100);
}

export class CartService {
  constructor() {
    this.items = [];
  }

  addItem(item) {
    this.items.push(item);
  }
}

const formatCurrency = (val) => {
  return `$${val.toFixed(2)}`;
};

const logger = function(msg) {
  console.log(msg);
};
"""
    chunks = parse_javascript_file(code, "src/utils/cart.js")

    assert len(chunks) >= 3
    chunk_texts = [c.code_text for c in chunks]

    # Verify function declaration
    assert any("calculateDiscount" in t for t in chunk_texts)
    # Verify class declaration
    assert any("CartService" in t for t in chunk_texts)
    # Verify arrow function
    assert any("formatCurrency" in t for t in chunk_texts)


def test_parser_service_dispatcher():
    py_code = "def foo(): pass"
    js_code = "function bar() { return 1; }"

    py_chunks = parse_code_file(py_code, "app/main.py")
    assert len(py_chunks) == 1
    assert py_chunks[0].name == "foo"

    js_chunks = parse_code_file(js_code, "web/index.js")
    assert len(js_chunks) == 1
    assert js_chunks[0].name == "bar"

    # Unsupported file extension returns empty list
    other_chunks = parse_code_file("hello world", "readme.txt")
    assert other_chunks == []


def test_binary_file_detection():
    # Test extension check
    assert is_binary_file("image.png") is True
    assert is_binary_file("archive.zip") is True
    assert is_binary_file("compiled.exe") is True
    assert is_binary_file("script.py") is False
    assert is_binary_file("app.js") is False

    # Test null byte content check
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(b"Normal text file")
        tf.flush()
        text_path = tf.name

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(b"Binary\x00data\x01\x02")
        tf.flush()
        bin_path = tf.name

    try:
        assert is_binary_file(text_path) is False
        assert is_binary_file(bin_path) is True
    finally:
        os.remove(text_path)
        os.remove(bin_path)
