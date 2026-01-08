import joblib, os, requests, json, math
import numpy as np
from datetime import datetime, timezone

# Конфиг тянется из Secrets репозитория
CONFIG = {
    'SPORTS_API_KEY': os.getenv('SPORTS_API_KEY'),
    'TG_TOKEN': os.getenv('TG_TOKEN'),
    'TG_CHAT_ID': os.getenv('TG_CHAT_ID'),
    'MODEL_PATH': 'football_model.pkl' # Файл, который прилетел из Colab
}

class PcmAutonomousSystem:
    def __init__(self):
        # Проверка наличия мозгов
        if not os.path.exists(CONFIG['MODEL_PATH']):
            raise FileNotFoundError("Нейронная модель .pkl не найдена в корне репозитория!")
        
        self.model = joblib.load(CONFIG['MODEL_PATH'])
        self.headers = {'x-apisports-key': CONFIG['SPORTS_API_KEY']}

    def analyze(self, h, x, a):
        # Нейронка предсказывает вероятности [П1, Х, П2]
        features = np.array([[h, x, a]])
        probs = self.model.predict_proba(features)[0]
        
        outcomes = ['П1', 'X', 'П2']
        idx = np.argmax(probs)
        pred_label = outcomes[idx]
        pred_prob = probs[idx]

        # Сравниваем с вероятностью букмекера (Edge)
        bookie_odds = [h, x, a]
        bookie_prob = 1 / bookie_odds[idx]
        edge = pred_prob - bookie_prob

        # Логика светофора + "Урок Челси"
        color = "🔴"
        if edge > 0.07: color = "🟢"
        elif edge > 0.03: color = "🟡"
        
        # Если фаворит (кэф < 1.7), но перевес нейронки слабый — это ловушка
        if (h < 1.7 or a < 1.7) and edge < 0.05:
            color = "🔴 (LOBBY/Trap)"

        return {
            "verdict": pred_label,
            "prob": f"{round(pred_prob*100)}%",
            "edge": f"{round(edge*100, 1)}%",
            "color": color
        }

    def run(self):
        print("🚀 Запуск автономного анализа...")
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
        
        try:
            fixtures = requests.get(url, headers=self.headers).json().get('response', [])
        except Exception as e:
            print(f"❌ Ошибка API Sports: {e}")
            return
        
        results = []
        top_leagues = [39, 140, 135, 78, 61, 88, 94] # АПЛ, Ла Лига, Италия, Германия, Франция, Голландия, Португалия

        for f in fixtures:
            if f['league']['id'] not in top_leagues: continue
            
            try:
                m_id = f['fixture']['id']
                m_name = f"{f['teams']['home']['name']} - {f['teams']['away']['name']}"
                
                # Кэфы
                o_res = requests.get(f"https://v3.football.api-sports.io/odds?fixture={m_id}", headers=self.headers).json()
                if not o_res.get('response'): continue
                
                bookie = o_res['response'][0]['bookmakers'][0]
                odds_list = next(bet for bet in bookie['bets'] if bet['name'] in ['Match Winner', 'Full Time Result'])
                v = {val['value']: float(val['odd']) for val in odds_list['values']}
                h, x, a = v.get('Home', v.get('1')), v.get('Draw', v.get('X')), v.get('Away', v.get('2'))

                # Моментальный расчет
                res = self.analyze(h, x, a)
                
                msg = (f"{res['color']} {m_name}\n"
                       f"📊 {h} | {x} | {a}\n"
                       f"🎯 Прогноз: {res['verdict']} ({res['prob']})\n"
                       f"📈 Edge: {res['edge']}")
                
                print(f"✅ Обработан: {m_name}")
                requests.post(f"https://api.telegram.org/bot{CONFIG['TG_TOKEN']}/sendMessage", 
                              json={"chat_id": CONFIG['TG_CHAT_ID'], "text": msg})
                
                results.append({"match": m_name, "analysis": res})
            except: continue

        # Сохранение отчета
        os.makedirs('web_export', exist_ok=True)
        with open('web_export/today_prognosis.json', 'w', encoding='utf-8') as out:
            json.dump(results, out, ensure_ascii=False, indent=4)
        print("🏁 Работа завершена.")

if __name__ == "__main__":
    PcmAutonomousSystem().run()
