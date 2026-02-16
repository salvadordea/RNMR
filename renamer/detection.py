"""Detection state machine for TMDB identification.

Pure Python -- no Qt imports.  The DetectionController drives one
BatchDetection through a deterministic state machine.  The caller
(ScanWorker) is a thin dispatch loop that emits signals and blocks
when the controller requests user input.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .cleaner import clean_for_search
from .metadata_extractor import extract_metadata, find_best_title
from .models import TMDBSeries, TMDBMovie, TMDBEpisode

# Minimum match confidence below which fallback logic is triggered.
CONFIDENCE_THRESHOLD = 0.6


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------

class DetectionState(Enum):
    PARSED = "parsed"
    TYPE_PENDING = "type_pending"
    SEARCHING = "searching"
    SELECTION_PENDING = "selection_pending"
    CONFIRMED = "confirmed"
    SKIPPED = "skipped"
    UNIDENTIFIED = "unidentified"


class Action(Enum):
    CONTINUE = "continue"
    NEED_MEDIA_TYPE = "need_media_type"
    NEED_SELECTION = "need_selection"
    NEED_FALLBACK = "need_fallback"
    DONE = "done"


# ------------------------------------------------------------------
# BatchContext -- shared by detection and Phase 3 formatting
# ------------------------------------------------------------------

@dataclass
class BatchContext:
    """Resolved TMDB metadata shared by all files with the same parsed title.

    Contains everything needed to format filenames.  No further TMDB
    calls are required once this object is built.
    """
    series: TMDBSeries | None = None
    movie: TMDBMovie | None = None
    media_type: str | None = None
    mapped: bool = False
    skipped: bool = False
    metadata_source: str = "inferred"  # "tmdb" | "ffprobe" | "inferred" | "unidentified"
    metadata_language: str = "en-US"
    episode_cache: dict[tuple[int, int], TMDBEpisode] = field(default_factory=dict)


# ------------------------------------------------------------------
# BatchDetection -- mutable state for one title group
# ------------------------------------------------------------------

@dataclass
class BatchDetection:
    """All mutable state for one batch traversing the state machine."""
    group_key: str
    entries: list[tuple[Path, Any]]
    state: DetectionState = DetectionState.PARSED
    media_type: str | None = None
    series: TMDBSeries | None = None
    movie: TMDBMovie | None = None
    confidence: float = 0.0
    candidates: list[dict] = field(default_factory=list)
    mapped: bool = False
    skipped: bool = False
    metadata_source: str = "inferred"
    metadata_language: str = "en-US"
    episode_cache: dict[tuple[int, int], TMDBEpisode] = field(default_factory=dict)

    # Internal flags
    _search_attempted: bool = False
    _ffprobe_attempted: bool = False
    _raw_result_count: int = 0  # how many TMDB results the last search returned

    @property
    def first_filepath(self) -> Path:
        return self.entries[0][0]

    @property
    def first_parsed(self) -> Any:
        return self.entries[0][1]

    @property
    def is_series(self) -> bool:
        return self.media_type == "series"

    @property
    def found(self) -> bool:
        return self.series is not None or self.movie is not None

    def signal_info(self) -> dict:
        """Build the dict emitted with worker signals."""
        first_parsed = self.first_parsed
        seasons = sorted({
            p.season for _, p in self.entries
            if p.season is not None
        })
        info: dict[str, Any] = {
            "filepath": str(self.first_filepath),
            "parsed_title": first_parsed.title_guess,
            "media_type": self.media_type or first_parsed.media_type,
            "seasons": seasons,
            "year": first_parsed.year,
            "file_count": len(self.entries),
        }
        if self.candidates:
            info["is_movie"] = not self.is_series
            info["results"] = self.candidates
        return info

    def to_batch_context(self) -> BatchContext:
        """Convert final state into a BatchContext for Phase 3."""
        return BatchContext(
            series=self.series,
            movie=self.movie,
            media_type=self.media_type,
            mapped=self.mapped,
            skipped=self.skipped,
            metadata_source=self.metadata_source,
            metadata_language=self.metadata_language,
            episode_cache=dict(self.episode_cache),
        )


# ------------------------------------------------------------------
# DetectionController -- pure logic, no Qt
# ------------------------------------------------------------------

class DetectionController:
    """Drives BatchDetection instances through the detection state machine.

    Constructor args:
        tmdb_client: TMDBClient instance (provides search/fetch/candidates).
        id_mapping:  IDMapping instance for reading/writing mapped IDs.
        settings:    dict with keys ``always_ask_media_type``,
                     ``always_confirm_tmdb``, ``interactive_fallback``.
        log_fn:      Optional callable for log messages.
    """

    def __init__(self, tmdb_client, id_mapping, settings: dict, log_fn=None):
        self._tmdb = tmdb_client
        self._id_mapping = id_mapping
        self._settings = settings
        self._log = log_fn or (lambda msg: None)

    # -- Public API ------------------------------------------------

    def create_batch(
        self,
        group_key: str,
        entries: list[tuple[Path, Any]],
        metadata_language: str,
    ) -> BatchDetection:
        first_parsed = entries[0][1]
        return BatchDetection(
            group_key=group_key,
            entries=entries,
            media_type=first_parsed.media_type,
            metadata_language=metadata_language,
        )

    def step(self, batch: BatchDetection) -> Action:
        """Advance the state machine one step. Returns the next Action."""
        if batch.state == DetectionState.PARSED:
            return self._step_parsed(batch)
        elif batch.state == DetectionState.TYPE_PENDING:
            # Caller must call set_media_type/skip before stepping again.
            # If we reach here the type was already set (state moved to SEARCHING).
            return Action.CONTINUE
        elif batch.state == DetectionState.SEARCHING:
            return self._step_searching(batch)
        elif batch.state in (
            DetectionState.SELECTION_PENDING,
            DetectionState.CONFIRMED,
            DetectionState.SKIPPED,
            DetectionState.UNIDENTIFIED,
        ):
            return Action.DONE
        return Action.DONE

    def set_media_type(self, batch: BatchDetection, media_type: str) -> None:
        """After the user picks a media type, set it and advance to SEARCHING."""
        batch.media_type = media_type
        batch.state = DetectionState.SEARCHING

    def set_selection(self, batch: BatchDetection, result_dict: dict) -> None:
        """After the user picks a TMDB result from candidates."""
        tmdb_id = result_dict.get("tmdb_id")
        media_type = result_dict.get("media_type")
        if tmdb_id and media_type:
            batch.media_type = media_type
            self._resolve_by_id(batch, tmdb_id, media_type)
            batch.state = DetectionState.CONFIRMED
        else:
            batch.state = DetectionState.SKIPPED
            batch.skipped = True

    def set_fallback_result(self, batch: BatchDetection, result_dict: dict) -> None:
        """After manual search / ID entry from the fallback dialog."""
        tmdb_id = result_dict.get("tmdb_id")
        media_type = result_dict.get("media_type")
        title = result_dict.get("title")
        if tmdb_id and media_type:
            # Save mapping for future scans
            self._id_mapping.set_id(
                batch.first_filepath.name, tmdb_id, media_type, title,
            )
            self._log(
                f"Saved mapping for '{batch.group_key}': "
                f"{media_type}:{tmdb_id}"
            )
            batch.mapped = True
            batch.media_type = media_type
            self._resolve_by_id(batch, tmdb_id, media_type)
            batch.state = DetectionState.CONFIRMED
        else:
            batch.state = DetectionState.SKIPPED
            batch.skipped = True

    def skip(self, batch: BatchDetection) -> None:
        """Mark batch as skipped, clear results."""
        batch.skipped = True
        batch.series = None
        batch.movie = None
        batch.state = DetectionState.SKIPPED

    # -- State handlers --------------------------------------------

    def _step_parsed(self, batch: BatchDetection) -> Action:
        # Check for a mapped ID first
        mapped_id, mapped_type = self._check_mapped_id(batch)
        if mapped_id and mapped_type:
            self._log(
                f"Using mapped ID for '{batch.group_key}': "
                f"{mapped_type}:{mapped_id}"
            )
            batch.mapped = True
            batch.media_type = mapped_type
            self._resolve_by_id(batch, mapped_id, mapped_type)
            batch.state = DetectionState.CONFIRMED
            return Action.CONTINUE

        # Ask media type if setting enabled
        if self._settings.get("always_ask_media_type", False):
            batch.state = DetectionState.TYPE_PENDING
            return Action.NEED_MEDIA_TYPE

        # Otherwise go straight to search
        batch.state = DetectionState.SEARCHING
        return Action.CONTINUE

    def _step_searching(self, batch: BatchDetection) -> Action:
        if not batch._search_attempted:
            batch._search_attempted = True
            self._do_search(batch)

        found = batch.found
        always_confirm = self._settings.get("always_confirm_tmdb", False)
        interactive = self._settings.get("interactive_fallback", False)
        multiple_results = batch._raw_result_count > 1

        # -- TMDB returned results ---------------------------------

        if found and multiple_results:
            # >1 results: ALWAYS show selection modal, never auto-select.
            self._build_candidates(batch)
            if batch.candidates:
                batch.state = DetectionState.SELECTION_PENDING
                return Action.NEED_SELECTION
            # Defensive: candidates empty despite raw results (shouldn't happen)
            batch.state = DetectionState.CONFIRMED
            return Action.CONTINUE

        if found and not multiple_results:
            # Exactly 1 result (or cached hit with _raw_result_count==0).
            if always_confirm and not batch.mapped:
                self._build_candidates(batch)
                if batch.candidates:
                    batch.state = DetectionState.SELECTION_PENDING
                    return Action.NEED_SELECTION
            # Auto-select the single result.
            batch.state = DetectionState.CONFIRMED
            return Action.CONTINUE

        # -- No match found ----------------------------------------

        # Try ffprobe metadata fallback
        if not batch._ffprobe_attempted:
            batch._ffprobe_attempted = True
            probe_result = self._try_ffprobe(batch)
            if probe_result:
                batch.metadata_source = "ffprobe"
                # ffprobe re-ran a search; check its result count too
                probe_multiple = batch._raw_result_count > 1
                if probe_multiple or always_confirm:
                    self._build_candidates(batch)
                    if batch.candidates:
                        batch.state = DetectionState.SELECTION_PENDING
                        return Action.NEED_SELECTION
                batch.state = DetectionState.CONFIRMED
                return Action.CONTINUE

        # ffprobe failed -- interactive fallback or give up
        if interactive:
            return Action.NEED_FALLBACK
        batch.state = DetectionState.UNIDENTIFIED
        return Action.DONE

    # -- Internal helpers ------------------------------------------

    def _check_mapped_id(self, batch: BatchDetection) -> tuple[int | None, str | None]:
        for filepath, _parsed in batch.entries:
            mid, mtype = self._id_mapping.get_id(filepath.name)
            if mid and mtype:
                return mid, mtype
        return None, None

    def _resolve_by_id(self, batch: BatchDetection, tmdb_id: int, media_type: str) -> None:
        if media_type == "series":
            batch.series = self._fetch_series(tmdb_id)
            batch.movie = None
        else:
            batch.movie = self._fetch_movie(tmdb_id)
            batch.series = None
        if batch.series or batch.movie:
            batch.confidence = 1.0

    def _fetch_series(self, tmdb_id: int) -> TMDBSeries | None:
        data = self._tmdb._request(f"/tv/{tmdb_id}")
        if not data:
            return None
        first_air_date = data.get("first_air_date", "")
        return TMDBSeries(
            id=data["id"],
            name=data.get("name", ""),
            original_name=data.get("original_name", ""),
            first_air_year=int(first_air_date[:4]) if first_air_date else None,
            overview=data.get("overview", ""),
            original_language=data.get("original_language", ""),
        )

    def _fetch_movie(self, tmdb_id: int) -> TMDBMovie | None:
        data = self._tmdb._request(f"/movie/{tmdb_id}")
        if not data:
            return None
        release_date = data.get("release_date", "")
        return TMDBMovie(
            id=data["id"],
            title=data.get("title", ""),
            original_title=data.get("original_title", ""),
            year=int(release_date[:4]) if release_date else None,
            overview=data.get("overview", ""),
        )

    def _do_search(self, batch: BatchDetection) -> None:
        """Perform TMDB search with clean title + retry logic."""
        first_parsed = batch.first_parsed
        is_series = batch.is_series

        if is_series:
            clean_title, _ = clean_for_search(
                first_parsed.title_guess, is_series=True,
            )
            search_title = clean_title or first_parsed.title_guess
            self._log(f"[CLEAN] Series search: '{search_title}'")
            batch.series = self._tmdb.search_series(search_title)
            batch._raw_result_count = len(self._tmdb.last_raw_results)

            # Retry with parser title if cleaner gave different text
            if not batch.series and search_title != first_parsed.title_guess:
                self._log(
                    f"[CLEAN] Retry with parser title: "
                    f"'{first_parsed.title_guess}'"
                )
                batch.series = self._tmdb.search_series(
                    first_parsed.title_guess,
                )
                batch._raw_result_count = len(self._tmdb.last_raw_results)
        else:
            clean_title, clean_year = clean_for_search(
                first_parsed.raw_name, is_series=False,
            )
            search_title = clean_title or first_parsed.title_guess
            search_year = (
                clean_year if clean_year is not None else first_parsed.year
            )
            self._log(
                f"[CLEAN] Movie search: '{search_title}'"
                + (f" year={search_year}" if search_year else "")
            )
            batch.movie = self._tmdb.search_movie(search_title, search_year)
            batch._raw_result_count = len(self._tmdb.last_raw_results)

            # Retry with parser title if cleaner gave different text
            if not batch.movie and search_title != first_parsed.title_guess:
                self._log(
                    f"[CLEAN] Retry with parser title: "
                    f"'{first_parsed.title_guess}'"
                )
                batch.movie = self._tmdb.search_movie(
                    first_parsed.title_guess, first_parsed.year,
                )
                batch._raw_result_count = len(self._tmdb.last_raw_results)

        # Update confidence
        found = batch.series or batch.movie
        batch.confidence = found.confidence if found else 0.0
        if found:
            self._log(
                f"[MATCH] '{batch.group_key}' -> "
                f"confidence={batch.confidence:.2f}, "
                f"raw_results={batch._raw_result_count}"
            )

    def _build_candidates(self, batch: BatchDetection) -> None:
        """Populate batch.candidates from last_raw_results (no API calls)."""
        first_parsed = batch.first_parsed
        candidates = self._tmdb.scored_candidates(
            first_parsed.title_guess,
            year=first_parsed.year,
            is_movie=not batch.is_series,
        )
        batch.candidates = candidates

    def _try_ffprobe(self, batch: BatchDetection) -> bool:
        """Try ffprobe metadata fallback. Returns True if a match was found."""
        filepath = batch.first_filepath
        is_series = batch.is_series

        tags = extract_metadata(filepath)
        if not tags:
            return False

        title = find_best_title(tags)
        if not title:
            return False

        self._log(f"[PROBE] Trying ffprobe title: '{title}'")

        clean_title, clean_year = clean_for_search(title, is_series=is_series)
        search_title = clean_title or title

        if is_series:
            result = self._tmdb.search_series(search_title)
        else:
            result = self._tmdb.search_movie(search_title, clean_year)
        batch._raw_result_count = len(self._tmdb.last_raw_results)

        if result and result.confidence >= CONFIDENCE_THRESHOLD:
            self._log(
                f"[PROBE] Match: confidence={result.confidence:.2f}, "
                f"raw_results={batch._raw_result_count}"
            )
            if is_series:
                batch.series = result
            else:
                batch.movie = result
            batch.confidence = result.confidence
            return True

        return False
