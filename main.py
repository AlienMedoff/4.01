import json, math, requests, os, time
from datetime import datetime, timezone

# Данные берем из секретов Гитхаба
CONFIG = {
    'SPORTS_API_KEY': os.getenv('SPORTS_API_KEY'),
    'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY'),
    'TG_TOKEN': os.getenv('TG_TOKEN'),
    'TG_CHAT_ID': os.getenv('TG_CHAT_ID')
}

class PcmAutomator:
    def __init__(self):
        # Твоя база, которую ты положишь в папку database
        with open('database/patterns.json', 'r') as f:
            self.history = json.load(f)

    def get_math(self, h, x, a):
        matches = []
        for p in self.history:
            dist = math.sqrt((p['h']-h)**2 + (p['x']-x)**2 + (p['a']-a)**2)
            if dist < 0.35:
                matches.append(list(map(int, p['score'].split(':'))))
        if len(matches) < 5: return None
        ah, aa = sum(m[0] for m in matches)/len(matches), sum(m[1] for m in matches)/len(matches)
        return {"score": f"{round(ah)}:{round(aa)}", "samples": len(matches), "ah": ah, "aa": aa}

    def ask_boss(self, m_data, m_res):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CONFIG['GEMINI_API_KEY']}"
        prompt = (f"Матч: {m_data['home']}-{m_data['away']}. Кэфы: {m_data['h']}/{m_data['x']}/{m_data['a']}. "
                  f"PCM: {m_res['score']} (Мат: {round(m_res['ah'],2)}-{round(m_res['aa'],2)}). "
                  f"ИНСТРУКЦИЯ: Если фаворит гнилой (кэф < 1.7, а разница < 0.8) - ставь 🔴. "
                  f"Дай: Цвет(🔴/🟡/🟢), СТАВКА, СЧЕТ.")
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30).json()
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
        except: return "⚠️ Gemini Error"

    def run(self):
        # 1. Запрос линии
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
        headers = {'x-apisports-key': CONFIG['SPORTS_API_KEY']}
        fixtures = requests.get(url, headers=headers).json().get('response', [])
        
        output = []
        for f in fixtures:
            if f['league']['id'] not in [39, 140, 135, 61, 78, 94, 88]: continue
            
            # 2. Кэфы
            o_res = requests.get(f"https://v3.football.api-sports.io/odds?fixture={f['fixture']['id']}", headers=headers).json()
            if not o_res.get('response'): continue
            
            try:
                bookie = o_res['response'][0]['bookmakers'][0]
                h, x, a = 0, 0, 0
                for bet in bookie['bets']:
                    if bet['name'] in ['Match Winner', 'Full Time Result']:
                        v = {val['value']: float(val['odd']) for val in bet['values']}
                        h, x, a = v.get('Home', v.get('1')), v.get('Draw', v.get('X')), v.get('Away', v.get('2'))
                
                if h > 0:
                    m_res = self.get_math(h, x, a)
                    if m_res:
                        time.sleep(15) # Пауза 15 сек
                        verdict = self.ask_boss({'home':f['teams']['home']['name'], 'away':f['teams']['away']['name'], 'h':h, 'x':x, 'a':a}, m_res)
                        output.append({"match": f"{f['teams']['home']['name']}-{f['teams']['away']['name']}", "verdict": verdict})
            except: continue

        # 3. Сохраняем для Google Script
        os.makedirs('web_export', exist_ok=True)
        with open('web_export/today_prognosis.json', 'w', encoding='utf-8') as out:
            json.dump(output, out, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    PcmAutomator().run()
