import random

TEMPLATES = [
    "Why {trend} is exploding right now",
    "The truth about {trend}",
    "{trend} explained in 5 minutes",
    "Everyone is talking about {trend}",
    "Is {trend} worth it?",
    "What nobody tells you about {trend}",
    "{trend} vs the competition",
    "I tried {trend} so you don't have to",
    "The future of {trend}",
    "How {trend} is changing everything"
]


class IdeaGenerator:

    viral_words = [
        "why",
        "how",
        "vs",
        "truth",
        "mistake",
        "explained",
        "secret",
        "beginner",
    ]

    def score(self, idea):

        score = 1

        text = idea.lower()

        for word in self.viral_words:
            if word in text:
                score += 1

        return score

    def generate(self, phrase, count=3):
    
        ideas = [
            f"Why {phrase} is exploding",
            f"The truth about {phrase}",
            f"{phrase} explained simply",
        ]
    
        results = []
    
        for idea in ideas[:count]:
        
            score = self.score(idea)
    
            results.append({
                "title": idea,
                "score": score
            })
    
        return results