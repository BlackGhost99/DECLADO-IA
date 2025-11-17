from typing import Dict, List


class Suggestion:
    def __init__(self, code: str, score: float, keywords: List[str]):
        self.code = code
        self.score = float(score)
        self.keywords = keywords

    def to_dict(self) -> Dict:
        return {"code": self.code, "score": self.score, "keywords": self.keywords}
