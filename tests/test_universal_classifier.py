import pytest
from veil.classifier import UniversalClassifier

import random
import string



@pytest.fixture
def classifier():
    return UniversalClassifier()


def test_adult_classification(classifier):
    res = classifier.classify("https://pornhub.com/video/12345", "Adult video")
    assert res.is_sensitive
    assert res.category == "ADULT_EXPLICIT"
    assert res.confidence >= 0.9


def test_gambling_classification(classifier):
    res = classifier.classify("https://stake.com/casino", "Play Live Blackjack & Slots")
    assert res.is_sensitive
    assert res.category == "GAMBLING_WAGERING"
    assert res.confidence >= 0.9


def test_shock_violence_classification(classifier):
    res = classifier.classify("https://rotten.com/shock", "Graphic media")
    assert res.is_sensitive
    assert res.category == "SHOCK_VIOLENCE"


def test_illicit_substances_classification(classifier):
    res = classifier.classify("https://darknet.onion/market", "Buy research chemicals online darknet market")
    assert res.is_sensitive
    assert res.category == "ILLICIT_SUBSTANCES"


def test_safe_medical_immunization(classifier):
    res = classifier.classify("https://en.wikipedia.org/wiki/Breast_cancer", "Breast Cancer Pathology & Oncology")
    assert not res.is_sensitive
    assert res.category == "SAFE"


def test_safe_developer_domain(classifier):
    res = classifier.classify("https://github.com/torvalds/linux", "Linux Kernel Source Code")
    assert not res.is_sensitive
    assert res.category == "SAFE"


def test_whitelist_rule_override(classifier, tmp_path):
    clf = UniversalClassifier(rules_path=tmp_path / "rules.json")
    clf.add_whitelist_rule("pornhub.com")
    res = clf.classify("https://pornhub.com/video/12345")
    assert not res.is_sensitive
    assert res.matched_rule == "pornhub.com"


def test_blacklist_rule_override(classifier, tmp_path):
    clf = UniversalClassifier(rules_path=tmp_path / "rules.json")
    clf.add_blacklist_rule("example.com")
    res = clf.classify("https://example.com/clean-article")
    assert res.is_sensitive
    assert res.category == "ADULT_EXPLICIT"
    assert res.matched_rule == "example.com"


def test_invalid_urls_do_not_crash_classifier(tmp_path):
    classifier = UniversalClassifier(rules_path=tmp_path / 'rules.json')
    assert not classifier.classify_url('https://[').is_sensitive
    assert not classifier.classify_url(123).is_sensitive
    assert classifier.classify_url('https://pornhub.com/').is_sensitive
    assert not classifier.classify_url('https://github.com/repo').is_sensitive
    # Fuzz malformed authority, Unicode, fragment and encoding combinations.
    rng = random.Random(70513)
    alphabet = string.ascii_letters + string.digits + '%:#@[]\\/?\x00' + '🌙'
    for _ in range(1500):
        value = ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 90)))
        result = classifier.classify_url('https://' + value)
        assert isinstance(result.is_sensitive, bool)



def test_uk_news_domains_keep_their_full_suffix(tmp_path):
    matcher = UniversalClassifier(rules_path=tmp_path / "rules.json")
    # The old two-label shortcut saw `co.uk`, which wasn't in the safe list.
    page = matcher.classify_url("https://www.bbc.co.uk/news/health", "Medical research")
    assert not page.is_sensitive
    assert page.reason == "Verified safe domain"
    matcher.close()
