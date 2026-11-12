"""Match URLs and page titles against local rules and the offline domain list.

User allowlist entries take priority. The keyword checks are imperfect,
so keep an eye out for false positives.
"""

import json
import os
import re
import fnmatch
import sqlite3
import urllib.parse
from dataclasses import dataclass, field
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
        """Check URL and title. Sometimes the hostname doesnt tell the whole story."""
        if not isinstance(url, str) or not url:
            return ClassificationResult(is_sensitive=False, reason="Empty or invalid URL")
        if not isinstance(title, str):
            title = ""

        # Invalid IPv6 syntax and malformed authorities raise ValueError in
        # urllib; extension-supplied URLs must not kill the IPC connection.
        try:
            parsed = urllib.parse.urlparse(url)
            netloc = (parsed.hostname or "").lower()
        except ValueError:
            return ClassificationResult(is_sensitive=False, reason="Malformed URL")

        # Ignore local/browser URLs. They're not normal destinations.
        scheme = parsed.scheme.lower()
        if scheme in ("chrome", "chrome-extension", "brave", "edge", "about", "file", "moz-extension"):
            return ClassificationResult(is_sensitive=False, reason="Internal scheme")

        # Whitelist goes first; the user's override shoudnt be second-guessed.
        for w in self._rules["whitelist"]:
            if fnmatch.fnmatch(netloc, w.lower()) or fnmatch.fnmatch(url.lower(), w.lower()):
                return ClassificationResult(is_sensitive=False, reason="Allowlist match", matched_rule=w)

        # Then check the user's blocklist.
        for b in self._rules["blacklist"]:
            if fnmatch.fnmatch(netloc, b.lower()) or fnmatch.fnmatch(url.lower(), b.lower()):
                return ClassificationResult(is_sensitive=True, category="ADULT_EXPLICIT", confidence=1.0, reason="Blocklist match", matched_rule=b)

        # 3. Known Safe Domains
        domain_parts = netloc.split(".")
        if len(domain_parts) >= 2:
            base_domain = ".".join(domain_parts[-2:])
            if base_domain in self.SAFE_DOMAINS:
                # A normal search site can still carry a pretty telling querry.
                if any(se in netloc for se in self.SEARCH_ENGINES):
                    return self._classify_search_query(parsed.query, title)
                return ClassificationResult(is_sensitive=False, reason="Verified safe domain")

        # 4. Sensitive TLD Check
        for tld in self.SENSITIVE_TLDS:
            if netloc.endswith(tld):
                cat = "GAMBLING_WAGERING" if tld in (".casino", ".bet", ".poker", ".bingo") else "ADULT_EXPLICIT"
                return ClassificationResult(is_sensitive=True, category=cat, confidence=0.98, reason=f"Sensitive TLD: {tld}")

        # 5. Keyword and Path Classification
        combined_text = f"{netloc} {parsed.path} {parsed.query} {title}".lower()

        # Check safe phrases before the broad keywrod scan.
        has_safe_context = any(term in combined_text for term in self.SAFE_CONTEXT_TERMS)

        for kw in self.GAMBLING_KEYWORDS:
            if kw in combined_text and not has_safe_context:
                return ClassificationResult(is_sensitive=True, category="GAMBLING_WAGERING", confidence=0.92, reason=f"Gambling keyword: {kw}")

        for kw in self.SHOCK_KEYWORDS:
            if kw in combined_text:
                return ClassificationResult(is_sensitive=True, category="SHOCK_VIOLENCE", confidence=0.95, reason=f"Shock content keyword: {kw}")

        for kw in self.ILLICIT_KEYWORDS:
            if kw in combined_text and not has_safe_context:
                return ClassificationResult(is_sensitive=True, category="ILLICIT_SUBSTANCES", confidence=0.93, reason=f"Illicit goods keyword: {kw}")

        for kw in self.ADULT_KEYWORDS:
            if kw in combined_text and not has_safe_context:
                return ClassificationResult(is_sensitive=True, category="ADULT_EXPLICIT", confidence=0.94, reason=f"Adult keyword: {kw}")

        # Final stop: local SQLite lookup. Fast enought for repeat checks.
        if self._db_conn and len(domain_parts) >= 2:
            candidate_domains = []
            for i in range(len(domain_parts) - 1):
                candidate_domains.append(".".join(domain_parts[i:]))

            try:
                cur = self._db_conn.cursor()
                placeholders = ",".join("?" for _ in candidate_domains)
                cur.execute(f"SELECT domain FROM domains WHERE domain IN ({placeholders}) LIMIT 1", candidate_domains)
                row = cur.fetchone()
                if row:
                    return ClassificationResult(is_sensitive=True, category="ADULT_EXPLICIT", confidence=0.99, reason=f"Database match: {row[0]}")
            except Exception:
                pass

        return ClassificationResult(is_sensitive=False, reason="Unmatched clean content")

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
        try:
            self.rules_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.rules_path, "w", encoding="utf-8") as f:
                json.dump(self._rules, f, indent=2)
        except Exception:
            pass

    def add_whitelist_rule(self, domain: str):
        dom = domain.strip().lower()
        if dom and dom not in self._rules["whitelist"]:
            self._rules["whitelist"].append(dom)
            self._save_rules()
            self.reload_rules()

    def add_blacklist_rule(self, domain: str):
        dom = domain.strip().lower()
        if dom and dom not in self._rules["blacklist"]:
            self._rules["blacklist"].append(dom)
            self._save_rules()
            self.reload_rules()

    def remove_whitelist_rule(self, domain: str):
        dom = domain.strip().lower()
        if dom in self._rules["whitelist"]:
            self._rules["whitelist"].remove(dom)
            self._save_rules()
            self.reload_rules()

    def remove_blacklist_rule(self, domain: str):
        dom = domain.strip().lower()
        if dom in self._rules["blacklist"]:
            self._rules["blacklist"].remove(dom)
            self._save_rules()
            self.reload_rules()

