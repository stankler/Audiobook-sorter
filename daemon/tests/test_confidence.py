from confidence import score_candidate, best_candidate

HOBBIT_CANDIDATE = {
    "id": "abc",
    "volumeInfo": {
        "title": "The Hobbit",
        "authors": ["J.R.R. Tolkien"],
        "publishedDate": "1937",
    }
}


class TestScoreCandidate:
    def test_exact_match_scores_high(self):
        s = score_candidate("The Hobbit", "J.R.R. Tolkien", HOBBIT_CANDIDATE)
        assert s >= 0.90

    def test_partial_title_match_scores_medium(self):
        s = score_candidate("Hobbit", "Tolkien", HOBBIT_CANDIDATE)
        assert 0.50 <= s < 0.90

    def test_wrong_book_scores_low(self):
        s = score_candidate("Harry Potter", "Rowling", HOBBIT_CANDIDATE)
        assert s < 0.30

    def test_no_author_query_still_scores_on_title(self):
        s = score_candidate("The Hobbit", None, HOBBIT_CANDIDATE)
        assert s >= 0.55

    def test_score_is_between_zero_and_one(self):
        s = score_candidate("anything", "anyone", HOBBIT_CANDIDATE)
        assert 0.0 <= s <= 1.0


class TestBestCandidate:
    def test_best_candidate_returns_match_above_threshold(self):
        candidates = [HOBBIT_CANDIDATE]
        best, score = best_candidate("The Hobbit", "J.R.R. Tolkien", candidates, 0.85)
        assert best is not None
        assert score >= 0.85

    def test_best_candidate_returns_none_below_threshold(self):
        candidates = [HOBBIT_CANDIDATE]
        best, score = best_candidate("Harry Potter", "Rowling", candidates, 0.85)
        assert best is None
