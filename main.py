import joblib, os, requests, json, math
import numpy as np
from datetime import datetime, timezone

# Конфиг для уведомлений и API
CONFIG = {
    'SPORTS_API_KEY': os.getenv('SPORTS_API_KEY'),
    'TG_TOKEN': os.getenv('TG_TOKEN'),
    'TG_CHAT_ID': os.getenv('TG_CHAT_ID'),
    'MODEL_PATH': 'football_model.pkl'
}

class PcmAutonomousSystem:
    def __init__(self):
        # Загружаем твои обученные мозги
        self.model = joblib.load(CONFIG['MODEL_PATH'])
        self.headers = {'x-apisports-key': CONFIG['SPORTS_API_KEY']}

    def analyze(self, h, x, a):
        # Нейронка предсказывает вероятности [П1, Х, П2]
        features = np.array([[h, x, a]])
        probs = self.model.predict_proba(features)[0]
        
        # Индексы: 0:П1, 1:Х, 2:П2
        outcomes = ['П1', 'X', 'П2']
        idx = np.argmax(probs)
        pred_label = outcomes[idx]
        pred_prob = probs[idx]

        # Расчет Margin Correction (Edge)
        # Сравниваем вероятность нейронки с вероятностью бука (1/кэф)
        bookie_odds = [h, x, a]
        bookie_prob = 1 / bookie_odds[idx]
        edge = pred_prob - bookie_prob

        # "Урок Челси" вшит в логику Цвета:
        # Если фаворит (кэф < 1.7), но перевес нейронки (edge) слишком мал (< 5%) - это ловушка
        color = "🔴"
        if edge > 0.07: color = "🟢"
        elif edge > 0.03: color = "🟡"
        
        # Дополнительный фильтр ловушки (Урок Челси)
        if (h < 1.7 or a < 1.7) and edge < 0.05:
            color = "🔴 (Ловушка)"

        return {
            "verdict": pred_label,
            "prob": f"{round(pred_prob*100)}%",
            "edge": f"{round(edge*100, 1)}%",
            "color": color
        }

    def run(self):
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
        fixtures = requests.get(url, headers=self.headers).json().get('response', [])
        
        results = []
        top_leagues = [39, 140, 135, 78, 61, 88, 94]

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

                # МОМЕНТАЛЬНЫЙ АНАЛИЗ НЕЙРОНКОЙ
                res = self.analyze(h, x, a)
                
                msg = (f"{res['color']} {m_name}\n"
                       f"Кэфы: {h} | {x} | {a}\n"
                       f"Прогноз: {res['verdict']} ({res['prob']})\n"
                       f"Перевес: {res['edge']}")
                
                # Шлем в телегу
                requests.post(f"https://api.telegram.org/bot{CONFIG['TG_TOKEN']}/sendMessage", 
                              json={"chat_id": CONFIG['TG_CHAT_ID'], "text": msg})
                
                results.append({"match": m_name, "analysis": res})
                
            except: continue

        # Сохраняем отчет
        os.makedirs('web_export', exist_ok=True)
        with open('web_export/today_prognosis.json', 'w', encoding='utf-8') as out:
            json.dump(results, out, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    PcmAutonomousSystem().run()
