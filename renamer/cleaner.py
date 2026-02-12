"""Aggressive filename cleaning for TMDB search queries.

Provides heavier cleaning than ``parser.remove_noise()``, specifically
optimised for building accurate TMDB search queries from noisy
scene-release filenames.

The *parser* module handles structural extraction (media-type detection,
season/episode parsing, basic noise removal).  This module focuses
solely on producing the best possible search string for the TMDB API.
"""

import re

# ---------------------------------------------------------------------------
# Pattern groups
# ---------------------------------------------------------------------------

# Resolution / quality
_RESOLUTION = r'\b(720p|1080p|1080i|2160p|4320p|4[kK]|UHD|SD|HD|FHD|QHD)\b'

# Video codec
_CODEC = (
    r'\b(x\.?264|x\.?265|[hH]\.?264|[hH]\.?265|HEVC|AVC|XVID|DIVX|AV1|VP9'
    r'|MPEG[24]?|VC-?1|DVDR)\b'
)

# Audio codec / channels
_AUDIO = (
    r'\b(AAC|AC3|EAC3|E-AC-?3|DTS(?:-?HD)?|DTS-?X|TrueHD|Atmos'
    r'|DD[P+]?5\.?1|DD[P+]?7\.?1|DD[P+]?2\.?0|DD[P+]?'
    r'|LPCM|PCM|FLAC|OPUS|MP3|OGG|WMA'
    r'|2\.0|5\.1|7\.1)(?:ch)?\b'
)

# Source / rip type
_SOURCE = (
    r'\b(WEB[- ]?DL|WEBRip|WEB[- ]?Cap|WEB'
    r'|Blu[- ]?[Rr]ay|BDRip|BRRip|BDREMUX'
    r'|HDTV|HDRip|DVDRip|DVD[Rr]?|PDTV|SDTV|TVRip|VHSRip'
    r'|R5|CAMRip|CAM|TELESYNC|TS|TC|SCR|SCREENER'
    r'|PPVRip|VODRip|HC|HDCAM)\b'
)

# HDR / bit-depth
_HDR = (
    r'\b(HDR10\+?|HDR|DV|Dolby[- ]?Vision|HLG|SDR'
    r'|10[- ]?bit|8[- ]?bit)\b'
)

# Streaming-service tags
_STREAMING = (
    r'\b(AMZN|NF|Netflix|DSNP|Disney\+?|HULU|ATVP|AppleTV\+?'
    r'|PMTP|Paramount\+?|PCOK|Peacock|HMAX|HBO[- ]?Max|MAX'
    r'|STAN|iT|iTunes|RED|CRAV|MA|VUDU|CR|Crunchyroll'
    r'|APTV|APTX|MUBI|CRITERION)\b'
)

# Language / subtitle tags
_LANG = (
    r'\b(Dual[- ]?Lat|Latino|Castellano|Spanish|English|French|German'
    r'|Italian|Portuguese|Russian|Japanese|Korean|Chinese|Hindi|Arabic'
    r'|MULTi[- ]?SUBS?|MULTi|SUB(?:BED|S)?|DUB(?:BED)?)\b'
)

# Release / edition tags
_RELEASE = (
    r'\b(REPACK|PROPER|RERIP|REAL|EXTENDED|UNRATED|UNCUT'
    r'|DC|DIRECTORS?[- ]?CUT|THEATRICAL|IMAX|OPEN[- ]?MATTE'
    r'|REMUX|HYBRID|REMASTERED|RESTORED|ANNIVERSARY|CRITERION'
    r'|COMPLETE|FINAL|LIMITED|INTERNAL|SAMPLE)\b'
)

# Common scene release groups
_GROUPS = (
    r'\b(YIFY|YTS|RARBG|SPARKS|GECKOS|FGT|EVO|ETTV|ETRG|PSA|AMIABLE'
    r'|QxR|ION10|NTb|NTG|CMRG|MeGusta|TIGOLE|GalaxyRG|GalaxyTV'
    r'|pahe|iFT|MZABI|SiGMA|AMRAP|FLUX|CUPCAKES|NOGRP|BONSAI'
    r'|LAW|DEFLATE|SHITBOX|PLAYWEB|RAPIDCOWS|SUJAIDR)\b'
)

# Website watermarks
_WEBSITE = r'(?:www\.)\S+\.\S+|\bYTS\.(?:MX|AM|AG|LT)\b|\bEZTV\b|\b1337x\b'

# Trailing release group after dash  (e.g.  "-SPARKS")
_TRAILING_GROUP = r'-[A-Za-z0-9]+$'

# Bracketed content  [anything]
_BRACKETS = r'\[[^\]]*\]'

# Parenthesised noise (parens containing known-tag keywords)
_PAREN_NOISE_KW = (
    r'rip|sub|dub|lat|720|1080|2160|x264|x265|hevc|bluray|web|hdr'
    r'|remux|amzn|yify|yts|cam|ts(?:$|\s)|hc'
)
_PAREN_NOISE = rf'\([^)]*(?:{_PAREN_NOISE_KW})[^)]*\)'

# Year inside optional parens/brackets
_YEAR = r'[\(\[]?((?:19|20)\d{2})[\)\]]?'

# Collected noise patterns (order matters: brackets/parens first)
_ALL_NOISE = [
    _BRACKETS,
    _PAREN_NOISE,
    _RESOLUTION,
    _CODEC,
    _AUDIO,
    _SOURCE,
    _HDR,
    _STREAMING,
    _LANG,
    _RELEASE,
    _GROUPS,
    _WEBSITE,
    _TRAILING_GROUP,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_for_search(
    raw_name: str,
    *,
    is_series: bool = False,
) -> tuple[str, int | None]:
    """Aggressively clean a raw filename stem for TMDB search.

    Parameters
    ----------
    raw_name:
        The filename stem (no extension).
    is_series:
        When *True*, skip the movie-specific "truncate at year" heuristic
        so that years embedded in series titles are not lost.

    Returns
    -------
    (cleaned_title, year)
        *year* is ``None`` when no plausible release year was found.
    """
    name = raw_name

    # 1. Strip bracketed content first (before separator normalisation so
    #    that e.g. "[YTS.MX]" is removed as a unit).
    name = re.sub(_BRACKETS, ' ', name)

    # 2. Remove website watermarks while dots are still intact
    #    (e.g. "www.1337x.to" must be caught before dots become spaces).
    name = re.sub(_WEBSITE, ' ', name, flags=re.IGNORECASE)

    # 3. Normalise separators (dots, underscores -> spaces).
    name = re.sub(r'[._]', ' ', name)
    name = re.sub(r'--+', ' ', name)

    # 4. Extract year (last occurrence -- usually the release year).
    year: int | None = None
    matches = list(re.finditer(_YEAR, name))
    if matches:
        m = matches[-1]
        y = int(m.group(1))
        if 1900 <= y <= 2100:
            year = y
            if not is_series:
                # For movies, everything after the year is almost always
                # codec / source / group noise -- truncate there.
                name = name[:m.start()]
            else:
                # For series, just strip the year token.
                name = name[:m.start()] + name[m.end():]

    # 5. Apply all noise patterns.
    for pattern in _ALL_NOISE:
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)

    # 6. Remove empty parens/brackets left behind.
    name = re.sub(r'\(\s*\)', '', name)
    name = re.sub(r'\[\s*\]', '', name)

    # 7. Final clean-up: keep word chars, spaces, apostrophes, hyphens,
    #    colons, and ampersands (all valid in movie/series titles).
    name = re.sub(r"[^\w\s'\-:&]", ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'^[\s\-]+|[\s\-]+$', '', name)

    return name, year
