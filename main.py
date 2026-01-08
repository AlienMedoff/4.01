import json, math, requests, os, time
from datetime import datetime, timezone

# Конфигурация из секретов GitHub
CONFIG = {
    'SPORTS_API_KEY': os.getenv('SPORTS_API_KEY'),
    'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY'),
    'TG_TOKEN': os.getenv('TG_TOKEN'),
    'TG_CHAT_ID': os.getenv('TG_CHAT_ID'),
    'RADIUS': 0.35  # Радиус поиска похожих кэфов
}

class PcmSystemFinal:
    def __init__(self):
        # Загрузка базы на 40к матчей
        base_path = 'database/patterns.json'
        if not os.path.exists(base_path):
            raise FileNotFoundError("База patterns.json не найдена! Сначала залей базу из Colab.")
            
        with open(base_path, 'r') as f:
            self.history = json.load(f)
        self.headers = {'x-apisports-key': CONFIG['SPORTS_API_KEY']}

    def get_market_context(self, h, x, a):
        similar_matches = []
        for p in self.history:
            # Математическое расстояние между кэфами
            dist = math.sqrt((p['h']-h)**2 + (p['x']-x)**2 + (p['a']-a)**2)
            if dist < CONFIG['RADIUS']:
                similar_matches.append(p['score'])
        
        if len(similar_matches) < 5: 
            return None
        
        # Расчет среднего ожидания
        goals = [list(map(int, s.split(':'))) for s in similar_matches]
        ah = sum(g[0] for g in goals) / len(goals)
        aa = sum(g[1] for g in goals) / len(goals)
        
        return {
            "samples": len(similar_matches),
            "math": f"{round(ah,2)}-{round(aa,2)}",
            "raw_scores": ", ".join(similar_matches[:7]) # Только 7 примеров для экономии лимитов
        }

    def ask_gemini(self, match_name, odds, ctx):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
        
        # Ультра-короткий промпт для обхода лимитов
        prompt = f"""
        Match: {match_name} ({odds}). 
        History ({ctx['samples']} games): Exp Score {ctx['math']}. 
        Past scores: {ctx['raw_scores']}.
        Rule: If Fav odd < 1.7 and Exp Goal Diff < 0.8 = 🔴 LOBBY.
        Format: COLOR (🔴/🟡/🟢), BET, SCORE, REASON (1 short sentence).
        """
        
        for _ in range(2): # 2 попытки если API тупит
            try:
                res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30).json()
                if 'candidates' in res:
                    return res['candidates'][0]['content']['parts'][0]['text'].strip()
                print("⏳ Лимит запросов. Жду 30 сек...")
                time.sleep(30)
            except:
                time.sleep(10)
        return "⚠️ Limit Exceeded"

    def run(self):
        print("🚀 Запуск анализа линии...")
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        f_url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
        
        try:
            fixtures = requests.get(f_url, headers=self.headers).json().get('response', [])
        except:
            print("❌ Ошибка API Sports")
            return

        results = []
        # Топ-лиги: АПЛ, Ла Лига, Серия А, Бундеслига, Лиг 1, Эредивизи, Примейра
        top_leagues = [39, 140, 135, 78, 61, 88, 94]

        for f in fixtures:
            if f['league']['id'] not in top_leagues: 
                continue
            
            m_id = f['fixture']['id']
            m_name = f"{f['teams']['home']['name']} - {f['teams']['away']['name']}"
            
            # Получаем кэфы
            try:
                o_res = requests.get(f"https://v3.football.api-sports.io/odds?fixture={m_id}", headers=self.headers).json()
                if not o_res.get('response'): continue
                
                bookie = o_res['response'][0]['bookmakers'][0]
                # Берем кэфы на исход
                odds_list = next(bet for bet in bookie['bets'] if bet['name'] in ['Match Winner', 'Full Time Result'])
                v = {val['value']: float(val['odd']) for val in odds_list['values']}
                h, x, a = v.get('Home', v.get('1')), v.get('Draw', v.get('X')), v.get('Away', v.get('2'))
                
                # Математический контекст из базы
                ctx = self.get_market_context(h, x, a)
                
                if ctx:
                    print(f"📡 Анализирую: {m_name}")
                    verdict = self.ask_gemini(m_name, f"{h}/{x}/{a}", ctx)
                    
                    # Сохраняем результат
                    res_item = {"match": m_name, "verdict": verdict}
                    results.append(res_item)
                    
                    # Шлем в Телеграм
                    tg_msg = f"🎯 {m_name}\nКэфы: {h}/{x}/{a}\n\n{verdict}"
                    requests.post(f"https://api.telegram.org/bot{CONFIG['TG_TOKEN']}/sendMessage", 
                                  json={"chat_id": CONFIG['TG_CHAT_ID'], "text": tg_msg})
                    
                    # ЖЕСТКАЯ ПАУЗА ДЛЯ СТАБИЛЬНОСТИ
                    time.sleep(35) 
            except Exception as e:
                print(f"⚠️ Пропуск матча {m_name}: {e}")
                continue

        # Сохранение в JSON для телефона
        os.makedirs('web_export', exist_ok=True)
        with open('web_export/today_prognosis.json', 'w', encoding='utf-8') as out:
            json.dump(results, out, ensure_ascii=False, indent=4)
        print("✅ Все матчи обработаны.")

if __name__ == "__main__":
    PcmSystemFinal().run()
