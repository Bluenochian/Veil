"""Match URLs and page titles against local rules and the offline domain list.

User allowlist entries take priority. The keyword checks are imperfect,
so keep an eye out for false positives.
"""

import json
import os
import fnmatch
import sqlite3
import tempfile
import urllib.parse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class ClassificationResult:
    is_sensitive: bool
    category: str = "SAFE"
    confidence: float = 0.0
    reason: str = ""
    matched_rule: str = ""
    language: str = "en"

    @property
    def is_adult(self) -> bool:
        """Backward-compatibility helper."""
        return self.is_sensitive and self.category == "ADULT_EXPLICIT"


class UniversalClassifier:
    """Local classifier for the content categories Veil handles."""

    SENSITIVE_TLDS = {
        # Adult
        ".xxx", ".porn", ".adult", ".sex", ".sexy", ".cam", ".fet", ".tube",
        # Gambling
        ".casino", ".bet", ".poker", ".bingo"
    }

    SHORTENERS_AND_AGGREGATORS = {
        "bit.ly", "tinyurl.com", "t.co", "is.gd", "buff.ly", "ow.ly", "rebrand.ly",
        "goo.gl", "linktr.ee", "allmylinks.com", "beacons.ai", "snipfeed.co",
        "fans.link", "linkvertise.com", "adf.ly", "ouo.io", "shrinkme.io",
        "exe.io", "cuty.io", "shorte.st", "btc4link.com", "adshrink.it", "cutt.ly"
    }

    SAFE_DOMAINS = {
        "wikipedia.org", "wikimedia.org", "wiktionary.org", "wikidata.org",
        "britannica.com", "stanford.edu", "mit.edu", "harvard.edu", "ox.ac.uk",
        "cam.ac.uk", "mayoclinic.org", "webmd.com", "cdc.gov", "nih.gov", "who.int",
        "nhs.uk", "healthline.com", "medicalnewstoday.com", "ncbi.nlm.nih.gov",
        "pubmed.ncbi.nlm.nih.gov", "github.com", "gitlab.com", "stackoverflow.com",
        "superuser.com", "stackexchange.com", "news.ycombinator.com", "kernel.org",
        "chatgpt.com", "openai.com", "anthropic.com", "gemini.google.com",
        "dailyplaylists.com", "artist.tools", "bbc.com", "bbc.co.uk",
        "reuters.com", "apnews.com", "nytimes.com", "theguardian.com",
        "washingtonpost.com", "lemonde.fr", "dw.com", "spiegel.de", "nature.com",
        "sciencedirect.com", "springer.com", "wiley.com", "rockylinux.org",
        "fedoraproject.org", "archlinux.org", "ubuntu.com", "debian.org", "kde.org",
        "gnome.org", "freedesktop.org", "python.org", "mozilla.org", "brave.com",
        "almalinux.org", "linuxmint.com", "manjaro.org", "opensuse.org",
        "google.com", "duckduckgo.com", "bing.com", "youtube.com"
    }

    SEARCH_ENGINES = {
        "google.", "bing.", "duckduckgo.", "brave.com", "search.brave.com",
        "yahoo.", "yandex.", "ecosia.", "qwant.", "startpage.", "kagi.com"
    }

    SAFE_CONTEXT_TERMS = {
        "symptom", "treatment", "diagnosis", "disease", "cancer", "syndrome",
        "prevention", "medical", "medicine", "clinic", "hospital", "doctor",
        "physician", "therapy", "health", "biology", "anatomy", "education",
        "textbook", "curriculum", "pathology", "clinical", "oncology",
        "gynecology", "urology", "sexual health", "pediatric", "disorder",
        "surgery", "medication", "screening", "vaccine", "research paper",
        "analytics", "analyzer", "analysis", "playlist", "platform", "analog",
        "documentation", "tutorial", "algorithm", "developer", "repository",
        "law", "statute", "legislation", "police", "arrest", "court", "rights",
        "civil rights", "counseling", "helpline", "support", "advocacy",
        "investigation", "journalism", "documentary", "crime", "policy"
    }

    # Category 1: Explicit Adult & Mature Media
    ADULT_KEYWORDS = {
        "porn", "xxx", "creampie", "blowjob", "hardcore", "erome", "gangbang",
        "bukkake", "deepthroat", "dildo", "fleshlight", "orgasm", "hentai",
        "xhamster", "pornhub", "xvideos", "xnxx", "redtube", "youporn",
        "onlyfans", "fansly", "camsoda", "chaturbate", "stripchat", "bongacams",
        "エロ", "無修正", "ビデオ", "ポルノ", "中出し", "裏垢", "ハメ撮り", "フェラ",
        "无码", "流出", "内射", "做爱", "操逼", "福利姬", "黑料", "口交", "肛交",
        "야동", "섹스", "자位", "유출", "porno", "sexo", "erotik"
    }

    # Category 2: Gambling, Betting, & Skin Wagering
    GAMBLING_KEYWORDS = {
        "casino", "bet365", "stake.com", "1xbet", "pokerstars", "roulette",
        "blackjack", "slot machine", "sportsbook", "sports betting", "baccarat",
        "csgoroll", "csgoempire", "crypto casino", "online gambling", "jackpot",
        "kumar", "bahis", "canli casino", "iddaa", "slot oyna", "pari sportif"
    }

    # Category 3: Extreme Shock & Graphic Violence
    SHOCK_KEYWORDS = {
        "rotten.com", "bestgore", "kaotic", "goregrish", "seegore", "heavy-r",
        "shock site", "snuff video", "death video", "beheading video", "gory deaths"
    }

    # Category 4: Illicit Substances & Black Market
    ILLICIT_KEYWORDS = {
        "darknet market", "silk road market", "buy fentanyl online", "buy research chemicals",
        "onion drug market", "tor dark market", "alphabay market"
    }

    def __init__(self, db_path: str | Path | None = None, rules_path: str | Path | None = None):
        if db_path is None:
            default_db = Path(__file__).parent.parent / "data" / "adult_domains.db"
            self.db_path = default_db if default_db.exists() else None
        else:
            p = Path(db_path)
            self.db_path = p if p.exists() else None

        self.rules_path = Path(rules_path) if rules_path else Path.home() / ".config" / "veil" / "rules.json"
        self._rules = {"whitelist": [], "blacklist": []}
        self._load_rules()

        self._db_conn = None
        self._init_db()
        # Class-level @lru_cache would retain every classifier instance, its
        # sqlite connection and the rules from previous profiles indefinitely.
        self._cached_classify = lru_cache(maxsize=4096)(self._classify_uncached)

    def close(self):
        self._cached_classify.cache_clear()
        if self._db_conn is not None:
            self._db_conn.close()
            self._db_conn = None

    def __del__(self):
        # Init can fail halfway. Clean up whatever actually got opened.
        conn = getattr(self, "_db_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _init_db(self):
        if self.db_path and self.db_path.exists():
            try:
                self._db_conn = sqlite3.connect(
                    f"file:{self.db_path}?mode=ro",
                    uri=True,
                    check_same_thread=False
                )
            except Exception:
                self._db_conn = None

    def _load_rules(self):
        if self.rules_path.exists():
            try:
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        return
                    for kind in ("whitelist", "blacklist"):
                        entries = data.get(kind, [])
                        self._rules[kind] = (
                            [entry.lower() for entry in entries
                             if isinstance(entry, str) and 0 < len(entry) <= 512]
                            if isinstance(entries, list) else []
                        )
            except Exception:
                pass

    def reload_rules(self):
        self._load_rules()
        self._cached_classify.cache_clear()

    def classify_url(self, url: str, title: str = "") -> ClassificationResult:
        """Keep the cache per instance so one profile's rules dont leak into another."""
        if not isinstance(url, str) or not url:
            return ClassificationResult(is_sensitive=False, reason="Empty or invalid URL")
        if not isinstance(title, str):
            title = ""
        return self._cached_classify(url, title)

    def _classify_uncached(self, url: str, title: str = "") -> ClassificationResult:
        try:
            page = urllib.parse.urlparse(url)
            host = (page.hostname or "").lower()
        except ValueError:
            return ClassificationResult(False, reason="Malformed URL")

        if page.scheme.lower() in ("chrome", "chrome-extension", "brave", "edge", "about", "file", "moz-extension"):
            return ClassificationResult(False, reason="Internal scheme")

        lower_url = url.lower()
        for rule in self._rules["whitelist"]:
            if fnmatch.fnmatch(host, rule) or fnmatch.fnmatch(lower_url, rule):
                return ClassificationResult(False, reason="Allowlist match", matched_rule=rule)
        for rule in self._rules["blacklist"]:
            if fnmatch.fnmatch(host, rule) or fnmatch.fnmatch(lower_url, rule):
                return ClassificationResult(True, "ADULT_EXPLICIT", 1.0, "Blocklist match", rule)

        parts = host.split(".")
        # The old last-two-labels check missed bbc.co.uk and other domains
        # with a country-code suffix. Match the whole domain boundary instead.
        if any(host == domain or host.endswith("." + domain) for domain in self.SAFE_DOMAINS):
            if any(search in host for search in self.SEARCH_ENGINES):
                return self._classify_search_query(page.query, title)
            return ClassificationResult(False, reason="Verified safe domain")

        for tld in self.SENSITIVE_TLDS:
            if host.endswith(tld):
                category = "GAMBLING_WAGERING" if tld in (".casino", ".bet", ".poker", ".bingo") else "ADULT_EXPLICIT"
                return ClassificationResult(True, category, 0.98, f"Sensitive TLD: {tld}")

        text = f"{host} {page.path} {page.query} {title}".lower()
        safe_context = any(word in text for word in self.SAFE_CONTEXT_TERMS)
        checks = (
            (self.GAMBLING_KEYWORDS, "GAMBLING_WAGERING", 0.92, "Gambling keyword", True),
            (self.SHOCK_KEYWORDS, "SHOCK_VIOLENCE", 0.95, "Shock content keyword", False),
            (self.ILLICIT_KEYWORDS, "ILLICIT_SUBSTANCES", 0.93, "Illicit goods keyword", True),
            (self.ADULT_KEYWORDS, "ADULT_EXPLICIT", 0.94, "Adult keyword", True),
        )
        for keywords, category, confidence, label, respect_context in checks:
            if safe_context and respect_context:
                continue
            for keyword in keywords:
                if keyword in text:
                    return ClassificationResult(True, category, confidence, f"{label}: {keyword}")

        # Only look up the domain after the cheap checks above. The bundled
        # list is quite big, and most of my browsing isn't on it anyway.
        if self._db_conn and len(parts) > 1:
            domains = [".".join(parts[i:]) for i in range(len(parts) - 1)]
            placeholders = ",".join("?" for _ in domains)
            try:
                row = self._db_conn.execute(
                    f"SELECT domain FROM domains WHERE domain IN ({placeholders}) LIMIT 1", domains
                ).fetchone()
                if row:
                    return ClassificationResult(True, "ADULT_EXPLICIT", 0.99, f"Database match: {row[0]}")
            except sqlite3.Error:
                pass

        return ClassificationResult(False, reason="Unmatched clean content")

    def _classify_search_query(self, query_str: str, title: str) -> ClassificationResult:
        params = urllib.parse.parse_qs(query_str)
        q_vals = params.get("q", []) or params.get("p", []) or params.get("query", [])
        search_terms = " ".join(q_vals).lower()
        full_text = f"{search_terms} {title}".lower()

        has_safe_context = any(term in full_text for term in self.SAFE_CONTEXT_TERMS)
        if has_safe_context:
            return ClassificationResult(is_sensitive=False, reason="Safe search query context")

        for kw in self.ADULT_KEYWORDS:
            if kw in full_text:
                return ClassificationResult(is_sensitive=True, category="ADULT_EXPLICIT", confidence=0.91, reason=f"Search term: {kw}")
        for kw in self.GAMBLING_KEYWORDS:
            if kw in full_text:
                return ClassificationResult(is_sensitive=True, category="GAMBLING_WAGERING", confidence=0.90, reason=f"Search term: {kw}")

        return ClassificationResult(is_sensitive=False, reason="Clean search query")

    def classify(self, url: str, title: str = "") -> ClassificationResult:
        """Alias for classify_url."""
        return self.classify_url(url, title)

    @property
    def whitelist(self) -> list[str]:
        return list(self._rules.get("whitelist", []))

    @property
    def blacklist(self) -> list[str]:
        return list(self._rules.get("blacklist", []))

    def _save_rules(self):
        self.rules_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(dir=self.rules_path.parent, prefix=".rules-")
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(self._rules, file, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.rules_path)
            temporary = None
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def _change_rule(self, kind: str, domain: str, add: bool):
        rule = domain.strip().lower()
        rules = self._rules[kind]
        if not rule:
            return
        if add and rule not in rules:
            rules.append(rule)
        elif not add and rule in rules:
            rules.remove(rule)
        else:
            return
        self._save_rules()
        self.reload_rules()

    def add_whitelist_rule(self, domain: str):
        self._change_rule("whitelist", domain, add=True)

    def add_blacklist_rule(self, domain: str):
        self._change_rule("blacklist", domain, add=True)

    def remove_whitelist_rule(self, domain: str):
        self._change_rule("whitelist", domain, add=False)

    def remove_blacklist_rule(self, domain: str):
        self._change_rule("blacklist", domain, add=False)
