import json, math, requests, os, time
from datetime import datetime, timezone

CONFIG = {
    'SPORTS_API_KEY': os.getenv('SPORTS_API_KEY'),
    'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY'),
    'TG_TOKEN': os.getenv('TG_TOKEN'),
    'TG_CHAT_ID': os.getenv('TG_CHAT_ID'),
    'RADIUS': 0.35
}

class PcmSystemV2:
    def __init__(self):
        with open('database/patterns.json', 'r') as f:
            self.history = json.load(f)
        self.headers = {'x-apisports-key': CONFIG['SPORTS_API_KEY']}

    def get_market_context(self, h, x, a):
        # Собираем все совпадения из 40к матчей
        similar_matches = []
        for p in self.history:
            dist = math.sqrt((p['h']-h)**2 + (p['x']-x)**2 + (p['a']-a)**2)
            if dist < CONFIG['RADIUS']:
                similar_matches.append(p['score'])
        
        if len(similar_matches) < 5: return None
        
        # Считаем мат-ожидание для ориентира
        goals = [list(map(int, s.split(':'))) for s in similar_matches]
        ah = sum(g[0] for g in goals) / len(goals)
        aa = sum(g[1] for g in goals) / len(goals)
        
        return {
            "samples": len(similar_matches),
            "avg_score": f"{round(ah)}:{round(aa)}",
            "raw_scores": ", ".join(similar_matches[:15]), # Даем Боссу первые 15 примеров
            "math": f"{round(ah,2)}-{round(aa,2)}"
        }

    def ask_boss(self, match_name, odds, ctx):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
        
        prompt = f"""
        АНАЛИЗ МАТЧА: {match_name}
        РЫНОК (кэфы): {odds}
        ИСТОРИЧЕСКАЯ ВЫБОРКА (из 40,000 игр):
        - Найдено похожих игр: {ctx['samples']}
        - Мат. ожидание счета: {ctx['math']}
        - Реальные счета из базы: {ctx['raw_scores']}

        ТВОЯ ЗАДАЧА:
        Используй 'Урок Челси': если кэф на фаворита < 1.7, а разница в мат. ожидании голов < 0.8 — это 🔴 ЛОВУШКА.
        Дай вердикт строго в формате:
        ЦВЕТ: (🟢/🟡/🔴)
        СТАВКА: (твоя рекомендация)
        ОБОСНОВАНИЕ: (1 короткое предложение)
        """
        
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30).json()
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        except:
            return "⚠️ Ошибка API (Limit)"

    def run(self):
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        f_url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
        fixtures = requests.get(f_url, headers=self.headers).json().get('response', [])
        
        results = []
        # Только топ-лиги, чтобы не спамить
        leagues = [39, 140, 135, 61, 78, 94, 88]

        for f in fixtures:
            if f['league']['id'] not in leagues: continue
            
            m_id = f['fixture']['id']
            m_name = f"{f['teams']['home']['name']} - {f['teams']['away']['name']}"
            
            # 1. Тянем кэфы
            o_res = requests.get(f"https://v3.football.api-sports.io/odds?fixture={m_id}", headers=self.headers).json()
            if not o_res.get('response'): continue
            
            try:
                bookie = o_res['response'][0]['bookmakers'][0]
                odds_data = {v['value']: float(v['odd']) for v in bookie['bets'][0]['values']}
                h, x, a = odds_data.get('Home', odds_data.get('1')), odds_data.get('Draw', odds_data.get('X')), odds_data.get('Away', odds_data.get('2'))
                
                # 2. Готовим выборку
                ctx = self.get_market_context(h, x, a)
                
                if ctx:
                    print(f"📡 Анализирую {m_name}...")
                    # 3. Отправляем Боссу
                    verdict = self.ask_boss(m_name, f"{h}/{x}/{a}", ctx)
                    
                    results.append({"match": m_name, "verdict": verdict})
                    
                    # Отправка в Телегу сразу
                    msg = f"🎯 {m_name}\nКэфы: {h}/{x}/{a}\n{verdict}"
                    requests.post(f"https://api.telegram.org/bot{CONFIG['TG_TOKEN']}/sendMessage", 
                                  json={"chat_id": CONFIG['TG_CHAT_ID'], "text": msg})
                    
                    # 4. ПАУЗА 15 СЕКУНД (чтобы Gemini не выбило)
                    time.sleep(15)
            except: continue

        # Сохраняем итоговый файл
        os.makedirs('web_export', exist_ok=True)
        with open('web_export/today_prognosis.json', 'w', encoding='utf-8') as out:
            json.dump(results, out, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    PcmSystemV2().run()
