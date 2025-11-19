# session/session.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Small helper class that persists a single logged-in user's ID to disk.

    - The file is a plain text file that contains only an integer, e.g. "42\n".
    - If the file is missing, empty, invalid, or non-positive, load() returns None.
    - This is NOT a security feature; it is just a convenience to remember the
      last logged-in user on this local desktop app.
    """

    def __init__(self, session_file: str | Path = "session.txt"):
        """
        Initialize the session manager.

        Parameters
        ----------
        session_file : str | Path
            Path to the session file. It can be a relative or absolute path.
        """
        self.session_path = Path(session_file)

    def save(self, user_id: int) -> None:
        """
        Save the given user_id to disk.

        Parameters
        ----------
        user_id : int
            Positive integer representing the logged-in user.

        Raises
        ------
        ValueError
            If user_id is not a positive integer.
        """
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive int")

        self.session_path.write_text(f"{user_id}\n", encoding="utf-8")
        logger.info(
            "Session saved for user_id=%s at %s",
            user_id,
            self.session_path.resolve(),
        )

    def load(self) -> Optional[int]:
        """
        Load the stored user_id from disk, if available.

        Returns
        -------
        Optional[int]
            The stored user_id if the file exists and contains a valid
            positive integer. Otherwise returns None.
        """
        try:
            if not self.session_path.exists():
                return None

            raw = self.session_path.read_text(encoding="utf-8").strip()
            if not raw:
                return None

            user_id = int(raw)
            if user_id <= 0:
                return None

            return user_id
        except Exception:
            # Any error in reading/parsing is treated as "no valid session".
            logger.warning(
                "Invalid or unreadable session file; ignoring it.",
                exc_info=True,
            )
            return None

    def clear(self) -> None:
        """
        Remove the session file from disk (log out).

        Any errors are logged, but not raised, to avoid breaking the app
        during logout.
        """
        try:
            if self.session_path.exists():
                self.session_path.unlink()
                logger.info(
                    "Session cleared (file removed: %s).",
                    self.session_path.resolve(),
                )
        except Exception:
            logger.warning(
                "Failed to remove session file %s",
                self.session_path,
                exc_info=True,
            )
