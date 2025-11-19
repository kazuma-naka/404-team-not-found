# llm/smollm_client.py

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional


def _ensure_stdio() -> None:
    """
    Ensure that sys.stdout / sys.stderr and their "original" counterparts
    (sys.__stdout__ / sys.__stderr__) are valid file-like objects.

    In a PyInstaller --windowed build on Windows, these can be None,
    and libraries like llama.cpp may call .fileno() on them.
    This helper assigns a write-only "null" stream when they are missing.
    """
    need_null = (
        getattr(sys, "stdout", None) is None
        or getattr(sys, "stderr", None) is None
        or getattr(sys, "__stdout__", None) is None
        or getattr(sys, "__stderr__", None) is None
    )

    null_stream = None
    if need_null:
        null_stream = open(os.devnull, "w", encoding="utf-8")

    # Normal streams
    if getattr(sys, "stdout", None) is None and null_stream is not None:
        sys.stdout = null_stream
    if getattr(sys, "stderr", None) is None and null_stream is not None:
        sys.stderr = null_stream

    # Original streams (used by some libraries)
    if getattr(sys, "__stdout__", None) is None:
        sys.__stdout__ = sys.stdout
    if getattr(sys, "__stderr__", None) is None:
        sys.__stderr__ = sys.stderr


# Make stdio safe as soon as this module is imported
_ensure_stdio()


# Lazy-loaded easy_llama module (to avoid top-level import reordering)
_ez_module: Optional[Any] = None


def _get_easy_llama():
    """
    Import easy_llama lazily.

    We do this instead of a top-level `import easy_llama as ez` so that:
      - we can guarantee stdio has been fixed first,
      - code formatters (isort, etc.) do not move the import to the top again.
    """
    _ensure_stdio()  # safety: ensure stdio is valid before importing
    global _ez_module
    if _ez_module is None:
        import easy_llama as ez  # type: ignore[import-untyped]
        _ez_module = ez
    return _ez_module


# Debug flag: set DEBUG_LLM=1 in environment to enable verbose logging
DEBUG_LLM = os.environ.get("DEBUG_LLM", "0") == "1"


def resource_path(rel: str) -> Path:
    """
    Resolve a path relative to the project root.

    This works both in development and when packaged with PyInstaller.
    It follows the same logic as app.py.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # Use the project root (two levels above this file) as the base
        base = Path(__file__).resolve().parents[1]
    return base / rel


# ---- libllama shared library setup ----------------------------------------

if sys.platform.startswith("win"):
    _LIB_NAME = "llama.dll"
elif sys.platform == "darwin":
    _LIB_NAME = "libllama.dylib"
else:
    _LIB_NAME = "libllama.so"

_DEV_LIB_PATH = resource_path(f"native/{_LIB_NAME}")

# Only set LIBLLAMA automatically if the user has not provided one.
if "LIBLLAMA" not in os.environ:
    if getattr(sys, "frozen", False):
        # In a PyInstaller bundle:
        #  - the shared library is embedded via --add-binary
        #  - PyInstaller patches ctypes so that using just the base name
        #    (e.g. "llama.dll") resolves to the bundled file inside _MEIPASS.
        os.environ["LIBLLAMA"] = _LIB_NAME
    else:
        # In development, prefer the native/ folder if the file exists.
        if _DEV_LIB_PATH.is_file():
            os.environ["LIBLLAMA"] = str(_DEV_LIB_PATH)
        # Otherwise we leave LIBLLAMA unset and let easy_llama fall back
        # to its own internal logic.


# ---- Config file -----------------------------------------------------------

# Store user-specific model path in the home directory
CONFIG_PATH = Path.home() / ".404_team_not_found_llm.json"


def _load_config_model_path() -> Optional[Path]:
    """
    Load model_path from the config file.

    Returns:
        Path if found and valid, otherwise None.
    """
    if not CONFIG_PATH.is_file():
        return None

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        path_str = data.get("model_path")
        if not path_str:
            return None
        return Path(path_str)
    except Exception:
        # Ignore corrupted JSON or unexpected errors
        return None


def _save_config_model_path(path: Path) -> None:
    """
    Save model_path to the config file.

    Failures are silently ignored so the app can still run.
    """
    try:
        CONFIG_PATH.write_text(
            json.dumps({"model_path": str(path)},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # Do not crash the app if saving the config fails
        pass


# ---- Model path handling ---------------------------------------------------

# Default model (used when nothing else is configured)
_DEFAULT_MODEL_REL = "models/SmolLM2-1.7B-Instruct-Q2_K_L.gguf"

# Priority:
# 1. model_path stored in the config file
# 2. environment variable SMOLLM_MODEL_PATH
# 3. default relative path
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

# Global Llama instance (lazy-loaded)
_llm: Optional[Any] = None
_model_lock = threading.Lock()


def _load_model(model_path: Path) -> Any:
    """
    Load a model from model_path and keep it globally.

    If the same path is already loaded, reuse the existing instance.
    """
    global _llm, _MODEL_PATH

    with _model_lock:
        # Reuse if the requested model is already loaded
        if _llm is not None and _MODEL_PATH == model_path:
            return _llm

        # Check existence
        if not model_path.is_file():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        # Import easy_llama only when actually needed
        ez = _get_easy_llama()

        # Load new model
        _llm = ez.Llama(str(model_path), verbose=False)
        _MODEL_PATH = model_path

        # Save absolute path to config
        try:
            resolved = model_path.resolve()
        except Exception:
            resolved = model_path
        _save_config_model_path(resolved)

        return _llm


def set_model_path(path: str | Path, *, relative_to_project: bool = False) -> None:
    """
    Change the model file path dynamically.

    Args:
        path: Path to the GGUF model file.
              - If absolute, it is used as is.
              - If relative_to_project=True, it is resolved via resource_path().
        relative_to_project:
              True: treat path as relative to project root.
              False: treat path as-is (Path(path)).
    """
    if isinstance(path, Path):
        p = path
    else:
        if relative_to_project:
            p = resource_path(path)
        else:
            p = Path(path)

    # Load model and update globals (also saves to config)
    _load_model(p)


def get_current_model_path() -> str:
    """
    Return the full path of the currently used model file as a string.
    """
    return str(_MODEL_PATH)


def reset_to_default_model() -> None:
    """
    Reset the model path to the default model (_DEFAULT_MODEL_REL).
    """
    set_model_path(_DEFAULT_MODEL_REL, relative_to_project=True)


def _get_llm() -> Any:
    """
    Internal helper: obtain the Llama instance for the current _MODEL_PATH.

    If not loaded yet, load it lazily.
    """
    return _load_model(_MODEL_PATH)


SPECIAL_MARKERS = ("<|im_end|>", "<|endoftext|>", "<|im_start|>")


def _d(msg: str) -> None:
    """
    Simple debug logger for LLM-related messages.
    Prints to stderr when DEBUG_LLM is True.
    """
    if not DEBUG_LLM:
        return
    print(msg, file=sys.stderr, flush=True)


def _run_llm(prompt: str, max_tokens: int) -> str:
    """
    Low-level function that:
      1. tokenizes the prompt,
      2. generates tokens,
      3. detokenizes the output,
      4. performs basic cleaning.
    """
    llm = _get_llm()

    _d("=== [_run_llm] called ===")
    _d(f"  MODEL_PATH:   {_MODEL_PATH}")
    _d(f"  max_tokens:   {max_tokens}")
    _d(f"  prompt:       {repr(prompt[:200])}...(len={len(prompt)})")

    # ---- tokenize ---------------------------------------------------------
    in_tokens = llm.tokenize(
        prompt.encode("utf-8"),
        add_special=True,
        parse_special=False,
    )
    _d(f"  in_tokens ({len(in_tokens)}): {in_tokens}")

    # ---- generate ---------------------------------------------------------
    out_tokens_raw = llm.generate(in_tokens, n_predict=max_tokens)

    if hasattr(out_tokens_raw, "tolist"):
        out_tokens: list[int] = out_tokens_raw.tolist()
    else:
        out_tokens = list(out_tokens_raw)

    _d(f"  out_tokens ({len(out_tokens)}): {out_tokens}")

    # ---- detokenize -------------------------------------------------------
    out_text = llm.detokenize(out_tokens, special=True)

    # Normalize to str
    if isinstance(out_text, bytes):
        raw_text = out_text.decode("utf-8", errors="ignore")
    else:
        raw_text = str(out_text)

    _d(f"  raw_text: {repr(raw_text)}")

    if any(marker in raw_text for marker in SPECIAL_MARKERS):
        _d(
            "  [LLM DEBUG] raw_text contains special marker(s): "
            + ", ".join(m for m in SPECIAL_MARKERS if m in raw_text)
        )

    # ---- cleaning ---------------------------------------------------------
    text = raw_text.strip()

    # Strip known prefixes
    for prefix in ("Rewritten:", "Assistant:", "Corrected:"):
        if text.startswith(prefix):
            _d(f"  stripping prefix: {repr(prefix)}")
            text = text[len(prefix):].lstrip()

    # Remove special markers
    for marker in SPECIAL_MARKERS:
        if marker in text:
            _d(f"  removing marker: {marker}")
            text = text.replace(marker, " ")

    # Strip surrounding quotes if any
    before_quotes = text
    text = text.strip().strip('"').strip("'")
    if text != before_quotes:
        _d("  stripped surrounding quotes")

    # Normalize repeated spaces
    text = " ".join(text.split())

    # Fallback: if we over-cleaned and got empty, use a cleaned raw_text
    if not text:
        _d("  [WARN] text became empty after cleaning, using fallback")
        fallback = raw_text
        for marker in SPECIAL_MARKERS:
            fallback = fallback.replace(marker, " ")
        text = " ".join(fallback.split()).strip()

    _d(f"  final text: {repr(text)}")
    _d("=== [_run_llm] end ===")

    return text


def generate_rewrite(user_message: str, max_tokens: int = 128) -> str:
    """
    Rewrite English text in natural, professional, and polite English.

    Intended for the "Rewrite" tab in the UI.
    """
    prompt = (
        "Rewrite the following text in natural, professional and polite English.\n"
        "- Keep the original meaning.\n"
        "- Fix grammar and word choice to be kind and polite.\n"
        f'Text: "{user_message.strip()}"\n'
        "Rewritten:"
    )
    return _run_llm(prompt, max_tokens=max_tokens)


def generate_spellcheck(user_message: str, max_tokens: int = 128) -> str:
    """
    Fix English spelling and simple typing mistakes with minimal changes.

    The goal is to keep the original wording and style as much as possible
    and only correct typos, spacing, and basic grammar issues.
    """
    prompt = (
        "You are an assistant that ONLY corrects spelling and obvious typing mistakes "
        "in English text.\n"
        "- Keep the original wording, tone, and sentence structure as much as possible.\n"
        "- Do NOT rewrite or rephrase; just fix spelling, spacing, and simple grammar errors.\n"
        "- Output only the corrected text without explanations.\n"
        f'Text: "{user_message.strip()}"\n'
        "Corrected:"
    )
    return _run_llm(prompt, max_tokens=max_tokens)


def generate_qa_answer(user_message: str, max_tokens: int = 256) -> str:
    """
    Answer a user question.

    Intended for the "Q&A" tab in the UI.
    """
    prompt = (
        "You are a helpful AI assistant running locally.\n"
        "Answer the user's question clearly and concisely.\n"
        "If the user asks about tasks or studying, give practical advice.\n\n"
        f"User: {user_message.strip()}\n"
        "Assistant:"
    )
    return _run_llm(prompt, max_tokens=max_tokens)


def generate_reply(user_message: str, max_tokens: int = 64) -> str:
    """
    Backward-compatible alias for older code.

    Behaves like generate_rewrite().
    """
    return generate_rewrite(user_message, max_tokens=max_tokens)
