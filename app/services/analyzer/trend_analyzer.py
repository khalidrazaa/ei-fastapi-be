import re
from collections import defaultdict
from datetime import timedelta, datetime, timezone


STOPWORDS = {
    "the","a","an","is","are","was","were",
    "this","that","these","those",
    "why","how","when","where",
    "best","top","new",
    "vs","and","or","but",
    "with","without","for","from","into","onto",
    "you","your","our","their",
    "what","who",
    "my","me"
}

WEAK_WORDS = {
    "video","tutorial","explained","review","guide",
    "shorts","watch","live","clip","episode",
    "update","today","latest"
}

class TrendAnalyzer:

    def extract_phrases(self, text):

        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())

        # remove stopwords
        words = [w for w in words if w not in STOPWORDS]

        phrases = []

        for n in range(2,5):  # 2–4 word phrases
            for i in range(len(words)-n+1):

                phrase = " ".join(words[i:i+n])
                if self._is_valid_phrase(phrase):
                    phrases.append(phrase)

        return phrases
    
    def _is_valid_phrase(self, phrase: str) -> bool:
        words = phrase.split()
        
        # remove phrases with duplicate words
        if len(set(words)) != len(words):
            return False

        # remove phrases dominated by weak words
        weak_count = sum(1 for w in words if w in WEAK_WORDS)
    
        if weak_count >= len(words) - 1:
            return False

        return True

    # -------------------------------
    # Main analysis
    # -------------------------------
    def analyze(self, videos):
    
        phrase_score = defaultdict(float)
        phrase_count = defaultdict(int)
        phrase_times = defaultdict(list)
    
        for row in videos:
        
            title = row.title
            virality_score = row.virality_score
            scanned_at = row.scanned_at
    
            phrases = self.extract_phrases(title)
    
            weight = virality_score if virality_score else 1
    
            for phrase in phrases:
            
                phrase_score[phrase] += weight
                phrase_count[phrase] += 1
                phrase_times[phrase].append(scanned_at)
    
        results = []
    
        for phrase in phrase_score:
        
            burst = self._calculate_burst(phrase_times[phrase])
            acceleration = self._calculate_acceleration(phrase_times[phrase])
    
            results.append({
                "phrase": phrase,
                "score": round(phrase_score[phrase], 2),
                "burst_score": burst,
                "acceleration": acceleration,
                "count": phrase_count[phrase]
            })
    
        results.sort(
            key=lambda x: (x["burst_score"], x["acceleration"], x["score"]),
            reverse=True
        )
    
        return results[:30]

    # -------------------------------
    # Burst detection
    # -------------------------------
    def _calculate_burst(self, timestamps):

        if len(timestamps) < 3:
            return 0

        timestamps.sort()
        window = timedelta(minutes=30)
        max_burst = 0

        for i in range(len(timestamps)):

            count = 1
            for j in range(i + 1, len(timestamps)):

                if timestamps[j] - timestamps[i] <= window:
                    count += 1

            max_burst = max(max_burst, count)

        return max_burst
    
    def _calculate_acceleration(self, times):
        now = datetime.now(timezone.utc)
        last_1h = 0
        last_6h = 0

        for t in times:

            diff = now - t
            if diff <= timedelta(hours=1):
                last_1h += 1

            if diff <= timedelta(hours=6):
                last_6h += 1

        if last_6h == 0:
            return 0

        return round(last_1h / last_6h, 2)
    
