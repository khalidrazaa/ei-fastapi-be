import re
from collections import defaultdict
from datetime import timedelta


class TrendAnalyzer:

    WORD_REGEX = re.compile(r"\b[a-zA-Z]{3,}\b")

    # -------------------------------
    # Extract bigrams
    # -------------------------------
    def extract_phrases(self, text: str):

        words = self.WORD_REGEX.findall(text.lower())

        phrases = []

        for i in range(len(words) - 1):
            phrases.append(f"{words[i]} {words[i+1]}")

        return phrases

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
    
            results.append({
                "phrase": phrase,
                "score": round(phrase_score[phrase], 2),
                "burst_score": burst,
                "count": phrase_count[phrase]
            })
    
        results.sort(
            key=lambda x: (x["burst_score"], x["score"]),
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