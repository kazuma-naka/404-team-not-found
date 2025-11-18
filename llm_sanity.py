# llm_sanity.py
"""
smollm_client が使っている libllama.so / model をそのまま使って、
easy_llama が正しく動くか確認するためのテストスクリプト。
"""

from llm.smollm_client import generate_rewrite
import os
from pathlib import Path

import easy_llama as ez  # ここで import が通るかも確認
import llm.smollm_client as sm  # smollm_client の設定を使う


print("=== LLM sanity test ===")

# smollm_client 側で使っているパスをそのまま利用
LIBLLAMA_PATH: Path = sm.LIB_PATH          # native/libllama.so の絶対パス
MODEL_PATH: Path = Path(sm.get_current_model_path())  # 現在のモデルパス


print("LIBLLAMA_PATH:", LIBLLAMA_PATH)
print("MODEL_PATH   :", MODEL_PATH)

if not LIBLLAMA_PATH.is_file():
    print("ERROR: libllama.so not found at", LIBLLAMA_PATH)
    raise SystemExit(1)

if not MODEL_PATH.is_file():
    print("ERROR: model file not found at", MODEL_PATH)
    raise SystemExit(1)

# easy_llama が参照する環境変数を設定（smollm_client と合わせる）
os.environ["LIBLLAMA"] = str(LIBLLAMA_PATH)
print("LIBLLAMA env:", os.environ["LIBLLAMA"])

print("easy_llama imported OK")

# 実際にモデルロード
llm = ez.Llama(str(MODEL_PATH), verbose=True)
print("Model loaded OK")

# 1) 素の easy_llama でテキスト生成してみる
prompt = "Hello from the 404-team-not-found LLM sanity test."
tokens = llm.tokenize(
    prompt.encode("utf-8"),
    add_special=True,
    parse_special=False,
)
out = llm.generate(tokens, n_predict=32)
txt = llm.detokenize(out, special=True)

if isinstance(txt, bytes):
    txt = txt.decode("utf-8", errors="ignore")

print("Generated (raw):", repr(txt))

# 2) smollm_client の generate_rewrite もついでにテスト

rewritten = generate_rewrite("Please rewrite this sentence politely.")
print("generate_rewrite():", repr(rewritten))
