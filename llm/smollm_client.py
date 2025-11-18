# llm/smollm_client.py
import json
import os
import sys
import threading
from pathlib import Path
from typing import Optional

import easy_llama as ez  # pip install easy_llama


def resource_path(rel: str) -> Path:
    """
    Dev と PyInstaller 両対応のパス解決。
    app.py と同じロジックをここにもコピーしておく。
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # プロジェクトルート（このファイルの 2 つ上の階層）を基準にする
        base = Path(__file__).resolve().parents[1]
    return base / rel


# ---- libllama.so の場所を設定 ---------------------------------------------

LIB_PATH = resource_path("native/libllama.so")
os.environ.setdefault("LIBLLAMA", str(LIB_PATH))

# ---- 設定ファイル ---------------------------------------------------------

# ユーザーごとの設定をホームディレクトリに保存
CONFIG_PATH = Path.home() / ".404_team_not_found_llm.json"


def _load_config_model_path() -> Optional[Path]:
    """設定ファイルから model_path を読み込む。なければ None。"""
    if not CONFIG_PATH.is_file():
        return None

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        path_str = data.get("model_path")
        if not path_str:
            return None
        return Path(path_str)
    except Exception:
        # 壊れた JSON などは無視
        return None


def _save_config_model_path(path: Path) -> None:
    """設定ファイルに model_path を保存する。"""
    try:
        CONFIG_PATH.write_text(
            json.dumps({"model_path": str(path)},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # 設定保存に失敗してもアプリ自体は動かしたいので握りつぶす
        pass


# ---- モデルパス関連 --------------------------------------------------------

# デフォルトモデル（従来通り）
_DEFAULT_MODEL_REL = "models/SmolLM2-1.7B-Instruct-Q2_K_L.gguf"

# 優先順位:
# 1. 設定ファイルに保存されている model_path
# 2. 環境変数 SMOLLM_MODEL_PATH
# 3. デフォルトの相対パス
_saved_model = _load_config_model_path()
_env_model = os.environ.get("SMOLLM_MODEL_PATH")

if _saved_model is not None:
    _MODEL_PATH: Path = _saved_model
elif _env_model:
    _MODEL_PATH = (
        Path(_env_model)
        if Path(_env_model).is_absolute()
        else resource_path(_env_model)
    )
else:
    _MODEL_PATH = resource_path(_DEFAULT_MODEL_REL)

# easy_llama の Llama インスタンス（遅延ロード）
_llm: Optional[ez.Llama] = None
_model_lock = threading.Lock()


def _load_model(model_path: Path) -> ez.Llama:
    """
    model_path のモデルをロードし、グローバルに保持する。
    すでに同じパスでロード済みなら再利用。
    """
    global _llm, _MODEL_PATH

    with _model_lock:
        # すでに同じパスでロード済みならそのまま返す
        if _llm is not None and _MODEL_PATH == model_path:
            return _llm  # type: ignore[return-value]

        # 存在チェック
        if not model_path.is_file():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        # 新しくロード
        _llm = ez.Llama(str(model_path), verbose=False)
        _MODEL_PATH = model_path

        # 設定ファイルにも保存（絶対パスにしておく）
        try:
            resolved = model_path.resolve()
        except Exception:
            resolved = model_path
        _save_config_model_path(resolved)

        return _llm


def set_model_path(path: str | Path, *, relative_to_project: bool = False) -> None:
    """
    使用するモデルファイルのパスを動的に変更する。

    Parameters
    ----------
    path : str | Path
        モデル(.gguf)へのパス。
        - absolute path: そのまま使用
        - relative_to_project=True の場合は project root からの相対パスとみなす
    relative_to_project : bool
        True の場合は resource_path() を通してプロジェクトルートからの相対パスとして解決。
        False の場合は渡されたパスをそのまま Path(path) として扱う。
    """
    if isinstance(path, Path):
        p = path
    else:
        if relative_to_project:
            p = resource_path(path)
        else:
            p = Path(path)

    # ロードしてグローバルを差し替え（この中で設定保存も行う）
    _load_model(p)


def get_current_model_path() -> str:
    """
    現在使用しているモデルファイルのフルパスを文字列で返す。
    UI から表示したいときなどに使う想定。
    """
    return str(_MODEL_PATH)


def reset_to_default_model() -> None:
    """
    デフォルトのモデル（_DEFAULT_MODEL_REL）に戻すヘルパー。
    """
    set_model_path(_DEFAULT_MODEL_REL, relative_to_project=True)


def _get_llm() -> ez.Llama:
    """
    内部用: 現在の _MODEL_PATH に対応する Llama インスタンスを取得。
    未ロードならここでロードする（遅延ロード）。
    """
    return _load_model(_MODEL_PATH)


def _run_llm(prompt: str, max_tokens: int) -> str:
    """共通の LLM 呼び出し処理。"""
    llm = _get_llm()

    in_tokens = llm.tokenize(
        prompt.encode("utf-8"),
        add_special=True,
        parse_special=False,
    )

    out_tokens_raw = llm.generate(in_tokens, n_predict=max_tokens)

    if hasattr(out_tokens_raw, "tolist"):
        out_tokens: list[int] = out_tokens_raw.tolist()
    else:
        out_tokens = list(out_tokens_raw)

    out_text = llm.detokenize(out_tokens, special=True)

    # bytes -> str に統一
    if isinstance(out_text, bytes):
        raw_text = out_text.decode("utf-8", errors="ignore")
    else:
        raw_text = str(out_text)

    # ------ ここから「掃除」処理 -----------------------------------------
    text = raw_text.strip()

    # 先頭に付くかもしれないお約束トークンを軽く削除
    # 必要最低限に絞る（Rewritten / Assistant だけ）
    for prefix in ("Rewritten:", "Assistant:"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()

    # 両端のクォートもついでに削る
    text = text.strip().strip('"').strip("'")

    # 掃除しすぎて空になった場合は、元のテキストをそのまま返す
    if not text:
        text = raw_text.strip()

    return text


def generate_rewrite(user_message: str, max_tokens: int = 128) -> str:
    """
    英文を書き換える専用プロンプト。
    UI の「Rewrite」タブから呼び出す想定。
    """
    prompt = (
        "Rewrite the following text in natural, professional and polite English.\n"
        "- Keep the original meaning.\n"
        "- Fix grammar and word choice.\n"
        "- Answer with the rewritten sentence only.\n\n"
        f"Text: \"{user_message.strip()}\"\n"
        "Rewritten:"
    )
    return _run_llm(prompt, max_tokens=max_tokens)


def generate_qa_answer(user_message: str, max_tokens: int = 256) -> str:
    """
    質問に答える用のプロンプト。
    UI の「Q&A」タブから呼び出す想定。
    """
    prompt = (
        "You are a helpful AI assistant running locally.\n"
        "Answer the user's question clearly and concisely.\n"
        "If the user asks about tasks or studying, give practical advice.\n\n"
        f"User: {user_message.strip()}\n"
        "Assistant:"
    )
    return _run_llm(prompt, max_tokens=max_tokens)


# 互換性のためのエイリアス（既存コードが generate_reply を呼んでも動くように）
def generate_reply(user_message: str, max_tokens: int = 64) -> str:
    """
    Backward-compatible alias.
    以前のコードと同じように、英文の書き換えとして動作します。
    """
    return generate_rewrite(user_message, max_tokens=max_tokens)
